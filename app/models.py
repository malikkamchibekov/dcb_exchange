import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PaymentStatus(str, enum.Enum):
    NEW = "new"                # запись только создана, QR ещё не запрашивали
    QR_GENERATED = "qr_generated"  # QR успешно получен от внешнего сервиса
    QR_ERROR = "qr_error"      # внешний сервис не ответил / вернул ошибку
    PAID = "paid"               # пришёл callback об оплате
    CANCELED = "canceled"     # платёж отменён/отклонён
    EXPIRED = "expired"  # истёк срок действия QR
    ERROR = "error" # ошибка
    TIMEOUT = "timeout" # Таймаут Присваивается при нефинализировании платежа в течение 5 минут после подтверждения
    VOID = "void" # Недействительно


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # guid приходит от 1С и однозначно идентифицирует платёж с нашей стороны.
    # unique+index — чтобы быстро искать при повторном приёме того же guid.
    guid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True, nullable=False)

    # Numeric(18, 2), а не float — чтобы не терять точность в деньгах.
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.NEW,
        nullable=False,
    )

    # Ссылка на готовый QR (или url), которую отдаём обратно 1С.
    qr_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # "id" из ответа QR-сервиса (поле "id", строка <=26 символов).
    # Именно этот id приходит обратно в теле callback, а не наш guid,
    # поэтому по нему матчим платёж в вебхуке (см. crud.find_for_callback).
    external_qr_id: Mapped[str | None] = mapped_column(String(26), unique=True, index=True, nullable=True)

    # server_default=func.now() — время проставляет сама БД при INSERT.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # onupdate=func.now() — БД обновляет время при любом UPDATE строки.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# Соответствие статусов из callback QR-сервиса нашим внутренним статусам.
# Из документации подтверждён только "PAID", остальные — по аналогии
# с типовым QR-эквайрингом, нужно сверить с провайдером.
EXTERNAL_STATUS_MAP: dict[str, PaymentStatus] = {
    "PAID": PaymentStatus.PAID,
    "ERROR": PaymentStatus.ERROR,
    "CANCELED": PaymentStatus.CANCELED,
    "TIMEOUT": PaymentStatus.TIMEOUT,
    "VOID": PaymentStatus.VOID,
    "EXPIRED": PaymentStatus.EXPIRED
}