import uuid
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.config import settings
from app.logging_config import log_exchange


class QrServiceError(Exception):
    # Единая ошибка для всех проблем с внешним сервисом:
    # сетевые сбои, таймауты, HTTP-ошибки, неожиданный формат ответа.
    pass


@dataclass
class QrResult:
    external_id: str  # "id" из ответа — по нему придёт callback об оплате
    data: str          # "data" из ответа — при representation=URL это готовый url QR-кода


async def generate_qr(guid: uuid.UUID, amount: Decimal) -> QrResult:
    """POST /web-api/{version}/qr — создание динамического QR-кода.

    representation=URL — чтобы в ответе сразу пришла ссылка, а не бинарный QR.
    metadata.guid передаёт наш guid и вернётся обратно в callback —
    подстраховка на случай, если матчинг по external_qr_id не сработает.
    """
    payload: dict = {
        "type": "QR_DYNAMIC",       # нужен, т.к. только динамический QR поддерживает callback_url
        "amount": str(amount),      # строкой, чтобы не потерять точность при сериализации
        "representation": "URL",
        "callback_url": settings.callback_url,
        "metadata": {"guid": str(guid)},
    }
    # Условные/опциональные поля добавляем, только если они заданы в конфиге —
    # если не передавать их вовсе, сервис применит поведение по умолчанию.
    if settings.qr_point_id is not None:
        payload["point"] = settings.qr_point_id
    if settings.qr_service_id is not None:
        payload["service_id"] = settings.qr_service_id
    if settings.qr_currency:
        payload["currency"] = settings.qr_currency

    # Логируем исходящий запрос ДО отправки — чтобы он остался в логе,
    # даже если сервис не ответит (таймаут/сетевая ошибка).
    log_exchange("US->QR", settings.qr_service_url, payload)

    try:
        async with httpx.AsyncClient(timeout=settings.qr_service_timeout) as client:
            response = await client.post(settings.qr_service_url, json=payload)
            response.raise_for_status()  # бросит исключение при статусе 4xx/5xx
    except httpx.HTTPError as exc:
        # Сюда попадают и таймауты, и сетевые ошибки, и HTTP-ошибки статусов.
        # Логируем сам факт ошибки; если сервер успел ответить телом — оно тоже попадёт в лог.
        error_body = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        error_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "ERROR"
        log_exchange("QR->US", settings.qr_service_url, error_body, error_status)
        raise QrServiceError(f"QR service request failed: {exc}") from exc

    body = response.json()
    log_exchange("QR->US", settings.qr_service_url, body, response.status_code)

    external_id = body.get("id")
    data = body.get("data")
    if not external_id or not data:
        # Сервис ответил 2xx, но без ожидаемых полей — тоже считаем ошибкой,
        # чтобы не записать в БД пустой/битый qr_url.
        raise QrServiceError(f"Непредвиденная ошибка: {body}")

    return QrResult(external_id=external_id, data=data)