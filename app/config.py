from dotenv import load_dotenv
import os
from pydantic_settings import BaseSettings

# Все настройки берутся из файла .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_BEARER_TOKEN = os.getenv("WEBHOOK_BEARER_TOKEN")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")

class Settings(BaseSettings):
    # Строка подключения к БД
    database_url: str = DATABASE_URL

    qr_service_base_url: str = "https://external-qr-service.example.com"
    qr_service_version: str = "v1"
    qr_service_timeout: float = 10.0  # таймаут HTTP-запроса к QR-сервису, сек.

    qr_point_id: int | None = None
    qr_service_id: int | None = None
    qr_currency: str | None = None  # например "KGS"

    callback_base_url: str = CALLBACK_BASE_URL

    webhook_bearer_token: str = WEBHOOK_BEARER_TOKEN

    class Config:
        env_file = ".env"

    @property
    def qr_service_url(self) -> str:
        return f"{self.qr_service_base_url}/web-api/{self.qr_service_version}/qr"

    @property
    def callback_url(self) -> str:
        return f"{self.callback_base_url}/api/v1/webhook/payment-status"

settings = Settings()