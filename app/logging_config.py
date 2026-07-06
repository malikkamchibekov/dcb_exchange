import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from app.config import settings

# Отдельный логгер для обменов, чтобы в файл попадали только записи об обменах
exchange_logger = logging.getLogger("exchange")


def setup_exchange_logging() -> None:
    """Настраивает запись всех обменов в файл с ротацией.
    Ротация по размеру: файл до 10 МБ, храним 5 архивов
    (exchange.log, exchange.log.1, ... exchange.log.5)
    Вызывается один раз при старте приложения.
    """
    exchange_logger.setLevel(logging.INFO)

    # Защита от дублирования хендлеров при повторном вызове (например, в тестах).
    if exchange_logger.handlers:
        return

    handler = RotatingFileHandler(
        settings.exchange_log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    exchange_logger.addHandler(handler)
    # Не пробрасываем записи в корневой логгер иначе они продублируются в stdout
    exchange_logger.propagate = False


def _serialize(body: Any) -> str:
    # Единообразная сериализация тела: dict/list -> JSON,
    # bytes -> строка, всё остальное -> str
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, default=str)
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def log_exchange(
    direction: str,       # "1C->FastAPI" | "FastAPI->1C" | "FastAPI->QR" | "QR->FastAPI"
    endpoint: str,        # URL или путь эндпоинта
    body: Any,            # тело запроса/ответа
    status: int | str = "",  # HTTP-статус (для ответов)
) -> None:
    """Пишет одну строку обмена в файл.

    Формат: время | направление | эндпоинт | статус | тело
    По этим строкам легко грепать разборы инцидентов:
    grep "QR->US" exchange.log — все callback'и от QR-сервиса.
    """
    exchange_logger.info("%s | %s | %s | %s", direction, endpoint, status, _serialize(body))
