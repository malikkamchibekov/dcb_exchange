from dotenv import load_dotenv
import os
from pydantic_settings import BaseSettings

# Все настройки берутся из файла .env

class Settings(BaseSettings):
    # Строка подключения к БД
    database_url: str

    qr_service_base_url: str
    qr_service_version: str = "v1"
    qr_service_timeout: float = 10.0  # таймаут HTTP-запроса к QR-сервису, сек.

    qr_retry_interval: int = 30

    callback_base_url: str

    webhook_bearer_token: str
    exchange_log_file: str
    class Config:
        env_file = ".env"

    @property
    def qr_service_url(self) -> str:
        return f"{self.qr_service_base_url}/web-api/{self.qr_service_version}/qr"

    @property
    def callback_url(self) -> str:
        return f"{self.callback_base_url}/api/v1/webhook/payment-status"

settings = Settings()