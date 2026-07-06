# Слим-образ достаточен: у нас нет системных зависимостей для сборки
# (asyncpg и httpx ставятся готовыми wheel'ами).
FROM python:3.12-slim

# Логи Python сразу в stdout без буферизации (важно для docker logs),
# и не создавать .pyc-файлы в контейнере.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

# Сначала только requirements — этот слой кешируется,
# и при изменении кода зависимости не переустанавливаются.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код приложения.
COPY app ./app

# Не работаем под root внутри контейнера.
# Каталог /srv/logs — для файла логов обменов (см. EXCHANGE_LOG_FILE).
RUN useradd --create-home appuser \
    && mkdir -p /srv/logs \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]