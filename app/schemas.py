import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import PaymentStatus


class PaymentIn(BaseModel):
    # Формат элемента входного списка от 1С: [{"guid": "...", "amount": 127.25}, ...]
    guid: uuid.UUID
    amount: Decimal


class PaymentOut(BaseModel):
    # from_attributes=True — позволяет строить схему прямо из ORM-объекта Payment
    # (model_validate(payment_orm_instance)), а не только из dict.
    model_config = ConfigDict(from_attributes=True)

    guid: uuid.UUID
    amount: Decimal
    status: PaymentStatus
    qr_url: str | None = None
    error: str | None = None  # заполняется, если генерация QR не удалась,
    # чтобы 1С видела причину, а не просто отсутствие qr_url


class PaymentCallback(BaseModel):
    """Формат callback, который присылает QR-сервис при смене статуса оплаты:

    POST $callback_url
    {"id": "0123456789abcdefghjkmnpqrs", "status": "PAID", "metadata": {}}
    """
    id: str                          # external_qr_id, основной ключ для поиска платежа
    status: str                      # сырое значение статуса от QR-сервиса
    metadata: dict[str, str] = {}    # то, что мы передали в metadata при создании QR

    @property
    def guid_from_metadata(self) -> uuid.UUID | None:
        # Запасной способ найти платёж, если по какой-то причине
        # external_qr_id в нашей БД не совпал (например, ручное вмешательство).
        raw = self.metadata.get("guid")
        return uuid.UUID(raw) if raw else None
