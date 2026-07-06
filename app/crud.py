import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentStatus


async def get_by_guid(session: AsyncSession, guid: uuid.UUID) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.guid == guid))
    return result.scalar_one_or_none()


async def get_by_external_id(session: AsyncSession, external_id: str) -> Payment | None:
    # Поиск по id, который вернул QR-сервис — основной способ матчинга в callback.
    result = await session.execute(select(Payment).where(Payment.external_qr_id == external_id))
    return result.scalar_one_or_none()


async def upsert_payment(session: AsyncSession, guid: uuid.UUID, amount: Decimal) -> tuple[Payment, bool]:
    """Создаёт запись либо обновляет сумму, если она изменилась.

    Возвращает (payment, needs_qr_generation).
    needs_qr_generation = True, если запись новая, сумма изменилась,
    либо QR ещё не был сгенерирован ранее (например, прошлый запрос упал с ошибкой).
    """
    payment = await get_by_guid(session, guid)

    if payment is None:
        # Новый guid — просто создаём запись со статусом NEW.
        # created_at/updated_at проставит сама БД (server_default в модели).
        payment = Payment(guid=guid, amount=amount, status=PaymentStatus.NEW)
        session.add(payment)
        await session.flush()  # чтобы получить payment.id/created_at до commit
        return payment, True

    # Запись уже была — проверяем, не пришла ли новая сумма по тому же guid.
    amount_changed = payment.amount != amount
    if amount_changed:
        # Сумма изменилась — считаем это новым платёжным намерением:
        # сбрасываем QR и статус, чтобы обязательно перегенерировать QR.
        payment.amount = amount
        payment.status = PaymentStatus.NEW
        payment.qr_url = None
        payment.external_qr_id = None

    # Если сумма не менялась, но QR почему-то ещё не был получен
    # (например, прошлая попытка упала с QR_ERROR) — тоже надо повторить генерацию.
    needs_qr = amount_changed or payment.qr_url is None
    return payment, needs_qr


async def set_qr_result(session: AsyncSession, payment: Payment, external_id: str, qr_url: str) -> None:
    # Вызывается после успешного ответа от внешнего QR-сервиса.
    payment.external_qr_id = external_id
    payment.qr_url = qr_url
    payment.status = PaymentStatus.QR_GENERATED


async def set_qr_error(session: AsyncSession, payment: Payment) -> None:
    # Вызывается, если внешний сервис недоступен/вернул ошибку.
    # Запись остаётся в БД со статусом QR_ERROR — её можно переотправить позже.
    payment.status = PaymentStatus.QR_ERROR


async def find_for_callback(
    session: AsyncSession, external_id: str, metadata_guid: uuid.UUID | None
) -> Payment | None:
    """Ищет платёж сначала по external_qr_id (основной ключ callback),
    затем по guid из metadata (подстраховка на случай рассинхрона)."""
    payment = await get_by_external_id(session, external_id)
    if payment is not None:
        return payment
    if metadata_guid is not None:
        return await get_by_guid(session, metadata_guid)
    return None


async def update_status(session: AsyncSession, payment: Payment, status: PaymentStatus) -> None:
    # updated_at обновится автоматически благодаря onupdate=func.now() в модели.
    payment.status = status
