#!/usr/bin/env bash
# ==============================================================================
# Скрипт резервного копирования SQLite (bot.db) и Redis (dump.rdb)
#
# Использование:
#   chmod +x scripts/backup.sh
#   ./scripts/backup.sh
#
# Что делает:
#   1. Создаёт бэкап SQLite через .backup (безопасно при активных транзакциях)
#   2. Выполняет Redis SAVE и копирует dump.rdb из Docker-тома
#   3. Хранит последние 7 ежедневных бэкапов в /root/backups/
#   4. Удаляет бэкапы старше 7 дней
#
# Cron (ежедневно в 03:00 МСК):
#   0 3 * * * /root/zdrav.lenreg/scripts/backup.sh >> /root/backups/backup.log 2>&1
#
# Восстановление SQLite:
#   cp /root/backups/bot_YYYYMMDD.db /root/zdrav.lenreg/data/bot.db
#   docker compose -f /root/zdrav.lenreg/docker-compose.yml restart bot
#
# Восстановление Redis:
#   docker compose -f /root/zdrav.lenreg/docker-compose.yml stop redis
#   cp /root/backups/redis_dump_YYYYMMDD.rdb /root/zdrav.lenreg/data/redis/dump.rdb
#   docker compose -f /root/zdrav.lenreg/docker-compose.yml start redis
# ==============================================================================

set -euo pipefail

PROJECT_DIR="/root/zdrav.lenreg"
BACKUP_DIR="/root/backups"
DATE_SUFFIX=$(date +%Y%m%d)
KEEP_DAYS=7

# Создать директорию для бэкапов, если её нет
mkdir -p "${BACKUP_DIR}"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Запуск резервного копирования ==="

# ---------------------------------------------------------------------------
# 1. Бэкап SQLite
# ---------------------------------------------------------------------------
SQLITE_SRC="${PROJECT_DIR}/data/bot.db"
SQLITE_DST="${BACKUP_DIR}/bot_${DATE_SUFFIX}.db"

if [ -f "${SQLITE_SRC}" ]; then
    sqlite3 "${SQLITE_SRC}" ".backup '${SQLITE_DST}'"
    echo "[OK] SQLite: ${SQLITE_DST} (${SIZE})"
else
    echo "[WARN] SQLite: файл ${SQLITE_SRC} не найден, пропуск"
fi

# ---------------------------------------------------------------------------
# 2. Бэкап Redis (SAVE + копирование dump.rdb из тома)
# ---------------------------------------------------------------------------
# Redis слушает на 127.0.0.1:6379, пароль из переменной окружения.
# Если docker-compose использует именованный том, dump.rdb лежит
# в /var/lib/docker/volumes/zdravlenreg_redis_data/_data/dump.rdb
# (имя тома зависит от COMPOSE_PROJECT_NAME; по умолчанию — имя директории).

if command -v redis-cli &> /dev/null; then
    REDIS_PASS="${REDIS_PASSWORD:-}"
    if [ -n "${REDIS_PASS}" ]; then
        redis-cli -a "${REDIS_PASS}" --no-auth-warning SAVE
    else
        redis-cli SAVE
    fi
    echo "[OK] Redis: SAVE выполнен"
else
    echo "[WARN] redis-cli не найден, пропуск Redis SAVE"
fi

# Копирование dump.rdb из Docker-тома
# Пытаемся найти том автоматически
REDIS_VOLUME_PATH=$(docker volume inspect zdravlenreg_redis_data --format '{{.Mountpoint}}' 2>/dev/null || true)
if [ -n "${REDIS_VOLUME_PATH}" ] && [ -f "${REDIS_VOLUME_PATH}/dump.rdb" ]; then
    cp "${REDIS_VOLUME_PATH}/dump.rdb" "${BACKUP_DIR}/redis_dump_${DATE_SUFFIX}.rdb"
    echo "[OK] Redis dump.rdb: ${BACKUP_DIR}/redis_dump_${DATE_SUFFIX}.rdb"
else
    echo "[WARN] Redis: том или dump.rdb не найден (путь: ${REDIS_VOLUME_PATH:-<не определён>})"
fi

# ---------------------------------------------------------------------------
# 3. Ротация: удалить бэкапы старше KEEP_DAYS дней
# ---------------------------------------------------------------------------
DELETED_COUNT=0
for old_file in "${BACKUP_DIR}"/bot_*.db "${BACKUP_DIR}"/redis_dump_*.rdb; do
    # Пропустить, если файл не существует (glob не раскрылся)
    [ -f "${old_file}" ] || continue

    # Извлечь дату из имени файла
    FILE_DATE=$(basename "${old_file}" | grep -oP '\d{8}' || true)
    if [ -z "${FILE_DATE}" ]; then
        continue
    fi

    FILE_EPOCH=$(date -d "${FILE_DATE}" +%s 2>/dev/null || true)
    CUTOFF_EPOCH=$(date -d "${KEEP_DAYS} days ago" +%s)

    if [ -n "${FILE_EPOCH}" ] && [ "${FILE_EPOCH}" -lt "${CUTOFF_EPOCH}" ]; then
        rm -f "${old_file}"
        echo "[ROTATE] Удалён старый бэкап: ${old_file}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done

if [ "${DELETED_COUNT}" -eq 0 ]; then
    echo "[ROTATE] Старых бэкапов для удаления нет"
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Резервное копирование завершено ==="
