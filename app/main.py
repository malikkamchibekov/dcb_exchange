import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.database import Base, async_session_factory, engine, get_session
from app.external_service import QrServiceError, generate_qr
from app.logging_config import log_exchange, setup_exchange_logging
from app.models import EXTERNAL_STATUS_MAP
from app.schemas import PaymentCallback, PaymentIn, PaymentOut

logger = logging.getLogger("payments")

# Инициализация файла логов обменов до старта приложения.
setup_exchange_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Создание таблиц при старте — удобно для docker compose up "из коробки".
    # create_all идемпотентен (не трогает существующие таблицы), но НЕ выполняет
    # миграции схемы: для продакшена замени на Alembic.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="QR Payment Service", lifespan=lifespan)


@app.middleware("http")
async def log_exchanges_middleware(request: Request, call_next):
    """Логирует все входящие обмены: запрос от 1С / callback от QR-сервиса и наш ответ.

    Middleware, а не логирование внутри эндпоинтов, потому что так в лог
    попадают в том числе ответы 401/404/422 (ошибки авторизации и валидации),
    которые до кода эндпоинта не доходят.
    """
    # Логируем только API-эндпоинты, пропуская служебные (/docs, /openapi.json).
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # Направление входящего: callback от QR-сервиса или запрос от 1С.
    inbound = "QR->US" if "webhook" in request.url.path else "1C->US"
    request_body = await request.body()
    log_exchange(inbound, request.url.path, request_body)

    response = await call_next(request)

    # Ответ FastAPI — стрим; вычитываем его целиком, чтобы записать в лог,
    # затем собираем заново, т.к. итератор одноразовый.
    response_body = b"".join([chunk async for chunk in response.body_iterator])
    outbound = "US->QR" if inbound == "QR->US" else "US->1C"
    log_exchange(outbound, request.url.path, response_body, response.status_code)

    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )

# auto_error=False — чтобы самим вернуть 401 с понятным detail,
# а не дефолтную 403 от FastAPI при отсутствии заголовка.
bearer_scheme = HTTPBearer(auto_error=False)


def verify_webhook_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Dependency: проверяет заголовок "Authorization: Bearer <token>" на вебхуке.

    hmac.compare_digest вместо "==" — сравнение за постоянное время,
    защищает от timing-атак на подбор токена.
    """
    if credentials is None or not hmac.compare_digest(
        credentials.credentials, settings.webhook_bearer_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )


async def process_payment(item: PaymentIn) -> PaymentOut:
    """Полный цикл обработки одного платежа: upsert в БД -> запрос QR -> запись результата.

    Каждый платёж обрабатывается в своей собственной сессии/транзакции,
    чтобы ошибка одного элемента батча (например, недоступность внешнего
    сервиса для одного guid) не откатывала остальные успешные платежи.
    """
    async with async_session_factory() as session:
        # Шаг 1: пишем/обновляем запись в БД ДО похода во внешний сервис —
        # так платёж не теряется, даже если QR-сервис недоступен.
        payment, needs_qr = await crud.upsert_payment(session, item.guid, item.amount)
        await session.commit()
        await session.refresh(payment)  # подтягиваем created_at/updated_at, выставленные БД

        if not needs_qr:
            # Сумма не менялась и QR уже был успешно сгенерирован ранее —
            # повторный поход во внешний сервис не нужен, просто отдаём то, что есть.
            return PaymentOut.model_validate(payment)

        # Шаг 2: запрашиваем QR у внешнего сервиса.
        try:
            qr = await generate_qr(payment.guid, payment.amount)
        except QrServiceError as exc:
            logger.error("QR generation failed for guid=%s: %s", payment.guid, exc)
            await crud.set_qr_error(session, payment)
            await session.commit()
            await session.refresh(payment)
            # Не роняем весь запрос 500-й ошибкой — 1С получит статус qr_error
            # по конкретному guid и сможет решить, что делать (повторить позже и т.п.).
            return PaymentOut.model_validate(payment).model_copy(update={"error": str(exc)})

        # Шаг 3: сохраняем результат генерации (external_id нужен для будущего callback).
        await crud.set_qr_result(session, payment, qr.external_id, qr.data)
        await session.commit()
        await session.refresh(payment)
        return PaymentOut.model_validate(payment)


@app.post("/api/v1/payments", response_model=list[PaymentOut])
async def receive_payments(items: list[PaymentIn]) -> list[PaymentOut]:
    # Основной эндпоинт для 1С: принимает список платежей, для каждого
    # проходит полный цикл upsert -> QR -> ответ.
    if not items:
        raise HTTPException(status_code=400, detail="Empty payments list")

    # Обрабатываем платежи батча параллельно (у каждого своя сессия в process_payment),
    # это ускоряет ответ, когда во внешний сервис уходит несколько запросов.
    results = await asyncio.gather(*(process_payment(item) for item in items))
    return list(results)


@app.post(
    "/api/v1/webhook/payment-status",
    status_code=204,
    dependencies=[Depends(verify_webhook_token)],  # без валидного Bearer — 401
)
async def payment_callback(
    payload: PaymentCallback,
    session: AsyncSession = Depends(get_session),
) -> None:
    # Сюда стучится внешний QR-сервис при смене статуса оплаты (см. PaymentCallback).
    payment = await crud.find_for_callback(session, payload.id, payload.guid_from_metadata)
    if payment is None:
        # 404 заставит QR-сервис повторить попытку (экспоненциальный бэкофф,
        # до 10 раз) — это страхует от редкого race condition, когда callback
        # пришёл раньше, чем наш commit с external_qr_id успел завершиться.
        raise HTTPException(status_code=404, detail="Payment not found")

    status = EXTERNAL_STATUS_MAP.get(payload.status)
    if status is None:
        # Неизвестный статус — логируем для разбора, но отвечаем 2xx,
        # чтобы сервис не долбил повторами по статусу, который мы не умеем обработать.
        logger.warning("Unknown callback status '%s' for id=%s", payload.status, payload.id)
        return

    await crud.update_status(session, payment, status)
    await session.commit()