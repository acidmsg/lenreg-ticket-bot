# =============================================================================
# Dockerfile — lenreg-ticket-bot Telegram Bot
# =============================================================================
# Основа: python:3.12-slim (минимальный образ, ~120MB)
# Запуск: python -m src.main (асинхронный поллинг aiogram)
#
# Стратегия кэширования (Docker BuildKit):
#   1. apt-пакеты: cache mount на /var/cache/apt + /var/lib/apt
#   2. poetry/pip: cache mount на /root/.cache/pip + /root/.cache/pypoetry
#   3. Зависимости Python: COPY pyproject.toml+poetry.lock ДО кода —
#      слой пересобирается только при изменении этих файлов
#   4. Код приложения: COPY scripts/ → locales/ → src/ ПОСЛЕ установки
#      зависимостей — редко меняющиеся директории кэшируются,
#      при каждом деплое пересобирается только слой src/
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — установка Python-зависимостей
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

LABEL maintainer="acidmsg"
LABEL description="Telegram-бот для мониторинга талонов zdrav.lenreg.ru"
LABEL version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/acidmsg/lenreg_ticket_bot"

# Системные зависимости для сборки Python-пакетов (gcc, libc6-dev).
# BuildKit cache mounts сохраняют скачанные .deb между сборками.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем ТОЛЬКО файлы зависимостей — этот слой кэшируется Docker'ом,
# пока pyproject.toml и poetry.lock не изменились.
COPY pyproject.toml poetry.lock ./

# Установка poetry и Python-зависимостей.
# --mount=cache сохраняет pip и poetry кэш между сборками BuildKit —
# при повторной сборке без изменений в зависимостях:
#   - pip/poetry wheel не скачиваются заново
#   - все пакеты берутся из кэша
# --no-root: проект не устанавливается как пакет (package-mode = false)
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/pypoetry \
    pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# =============================================================================
# Stage 2: Runtime — минимальный образ для запуска
# =============================================================================
FROM python:3.12-slim

LABEL maintainer="acidmsg"
LABEL description="Telegram-бот для мониторинга талонов zdrav.lenreg.ru"
LABEL version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/acidmsg/lenreg_ticket_bot"

# Рантайм-зависимости: procps (pgrep для healthcheck), redis-tools (redis-cli),
# sqlite3 (отладка БД).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        procps \
        redis-tools \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь для рантайма
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin -c "App User" appuser

# Копирование Python-пакетов из builder-слоя (установлены системно в site-packages)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# ---------------------------------------------------------------------------
# Копирование исходного кода — порядок от редко меняющихся к часто
# меняющимся: scripts → locales → src.
# При изменении только src/ (самый частый случай) слои scripts/ и locales/
# берутся из кэша, пересобирается только последний слой COPY src/.
# Все вышележащие слои (системные пакеты, Python-зависимости)
# уже закэшированы Docker'ом и не пересобираются.
# ---------------------------------------------------------------------------
WORKDIR /app
COPY scripts/ scripts/
COPY locales/ locales/
COPY src/ src/

RUN chmod +x /app/scripts/docker-entrypoint.sh

# Директории для runtime-данных (монтируются извне через docker-compose volumes)
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 9090
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python -m src.main" > /dev/null 2>&1 && redis-cli -h redis ping > /dev/null 2>&1 || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["python", "-m", "src.main"]
