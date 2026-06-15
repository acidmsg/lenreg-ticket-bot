#!/usr/bin/env bash
# ==============================================================================
# Скрипт восстановления БД из бэкапа
#
# Использование:
#   bash scripts/restore.sh <путь_к_файлу_бэкапа>
#
# Пример:
#   bash scripts/restore.sh data/backups/daily/bot_2026-06-14_120000.db
#
# Переменные окружения:
#   SQLITE_DB_PATH          — путь к рабочей БД (default: data/bot.db)
#   BACKUP_DIR              — корневая директория бэкапов (default: data/backups)
#   RESTORE_IN_CONTAINER    — если true, просто копирует БД без docker compose
#                             (default: false)
#   NTFY_BACKUP_TOPIC       — URL NTFY-топика для алертов (default: пусто)
#
# Логика:
#   1. Проверить существование файла бэкапа
#   2. Проверить целостность бэкапа (PRAGMA integrity_check)
#   3. Создать аварийный pre-restore бэкап текущей БД
#   4. Скопировать бэкап поверх рабочей БД
#   5. При RESTORE_IN_CONTAINER=false — перезапустить бота через docker compose
#   6. Отправить алерт через NTFY
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Параметризация через переменные окружения
# ---------------------------------------------------------------------------
DB_PATH="${SQLITE_DB_PATH:-data/bot.db}"
BACKUP_DIR="${BACKUP_DIR:-data/backups}"
RESTORE_IN_CONTAINER="${RESTORE_IN_CONTAINER:-false}"
NTFY_URL="${NTFY_BACKUP_TOPIC:-}"

# ---------------------------------------------------------------------------
# Проверка аргументов
# ---------------------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "ОШИБКА: Не указан путь к файлу бэкапа."
    echo "Использование: bash scripts/restore.sh <путь_к_файлу_бэкапа>"
    echo "Пример: bash scripts/restore.sh data/backups/daily/bot_2026-06-14_120000.db"
    exit 1
fi

BACKUP_FILE="$1"

# ---------------------------------------------------------------------------
# Функция: отправка алерта через NTFY
# ---------------------------------------------------------------------------
send_alert() {
    local title="$1"
    local message="$2"
    local priority="${3:-high}"

    if [ -n "${NTFY_URL}" ]; then
        curl -s -H "Title: ${title}" \
             -H "Priority: ${priority}" \
             -H "Tags: warning,rotate" \
             -d "${message}" \
             "${NTFY_URL}" > /dev/null 2>&1 || true
    fi
}

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Запуск восстановления из бэкапа ==="
echo "[RESTORE] Файл бэкапа: ${BACKUP_FILE}"

# ---------------------------------------------------------------------------
# 1. Проверить существование файла бэкапа
# ---------------------------------------------------------------------------
if [ ! -f "${BACKUP_FILE}" ]; then
    echo "[FAIL] Файл бэкапа не найден: ${BACKUP_FILE}"
    send_alert "Restore FAILED" "Файл бэкапа не найден: ${BACKUP_FILE}"
    exit 1
fi

BACKUP_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null || echo 0)
BACKUP_SIZE_HUMAN=$(numfmt --to=iec --suffix=B "${BACKUP_SIZE}" 2>/dev/null || echo "${BACKUP_SIZE} bytes")
echo "[RESTORE] Размер бэкапа: ${BACKUP_SIZE_HUMAN}"

# ---------------------------------------------------------------------------
# 2. Проверить целостность бэкапа
# ---------------------------------------------------------------------------
echo "[RESTORE] Проверка целостности бэкапа..."
INTEGRITY_RESULT=$(sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check" 2>&1)
if [ "${INTEGRITY_RESULT}" != "ok" ]; then
    echo "[FAIL] Бэкап не прошёл integrity_check: ${INTEGRITY_RESULT}"
    send_alert "Restore FAILED" "Бэкап ${BACKUP_FILE} повреждён (integrity_check: ${INTEGRITY_RESULT}). Восстановление отменено."
    exit 1
fi
echo "[RESTORE] integrity_check: ok"

# Проверка количества таблиц
TABLE_COUNT=$(sqlite3 "${BACKUP_FILE}" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'" 2>&1)
if [ -z "${TABLE_COUNT}" ] || [ "${TABLE_COUNT}" -lt 5 ]; then
    echo "[FAIL] Слишком мало таблиц в бэкапе: ${TABLE_COUNT:-0}"
    send_alert "Restore FAILED" "Бэкап ${BACKUP_FILE} содержит всего ${TABLE_COUNT:-0} таблиц. Восстановление отменено."
    exit 1
fi
echo "[RESTORE] Количество таблиц в бэкапе: ${TABLE_COUNT}"

# ---------------------------------------------------------------------------
# 3. Создать аварийный pre-restore бэкап текущей БД
# ---------------------------------------------------------------------------
EMERGENCY_DIR="${BACKUP_DIR}/emergency"
mkdir -p "${EMERGENCY_DIR}"

if [ -f "${DB_PATH}" ]; then
    EMERGENCY_TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
    EMERGENCY_FILE="${EMERGENCY_DIR}/pre_restore_${EMERGENCY_TIMESTAMP}.db"
    echo "[RESTORE] Создание аварийного бэкапа текущей БД: ${EMERGENCY_FILE}"

    # Используем .backup для консистентности (если БД читаема)
    if sqlite3 "${DB_PATH}" ".backup '${EMERGENCY_FILE}'" 2>/dev/null; then
        echo "[RESTORE] Аварийный бэкап создан успешно"
    else
        # Если .backup не сработал — простое копирование (БД может быть повреждена)
        cp "${DB_PATH}" "${EMERGENCY_FILE}"
        # Копируем WAL/SHM если есть
        cp "${DB_PATH}-wal" "${EMERGENCY_FILE}-wal" 2>/dev/null || true
        cp "${DB_PATH}-shm" "${EMERGENCY_FILE}-shm" 2>/dev/null || true
        echo "[RESTORE] Аварийный бэкап создан через cp (БД могла быть недоступна для .backup)"
    fi
else
    echo "[RESTORE] Текущая БД не найдена (${DB_PATH}) — аварийный бэкап не требуется"
fi

# ---------------------------------------------------------------------------
# 4. Остановка бота (если не в контейнере)
# ---------------------------------------------------------------------------
if [ "${RESTORE_IN_CONTAINER}" = "false" ]; then
    echo "[RESTORE] Остановка бота через docker compose..."
    if docker compose -f /srv/bots/lenreg-ticket-bot/docker-compose.yml stop bot 2>/dev/null; then
        echo "[RESTORE] Бот остановлен"
    else
        echo "[WARN] Не удалось остановить бота через docker compose (возможно, docker не запущен)"
        echo "[WARN] Продолжаем восстановление, но бот может писать в БД"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Удаление WAL/SHM и копирование бэкапа
# ---------------------------------------------------------------------------
echo "[RESTORE] Удаление WAL/SHM файлов..."
rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"

echo "[RESTORE] Копирование бэкапа → ${DB_PATH}..."
cp "${BACKUP_FILE}" "${DB_PATH}"

# ---------------------------------------------------------------------------
# 6. Проверка целостности восстановленной БД
# ---------------------------------------------------------------------------
echo "[RESTORE] Проверка целостности восстановленной БД..."
FINAL_INTEGRITY=$(sqlite3 "${DB_PATH}" "PRAGMA integrity_check" 2>&1)
if [ "${FINAL_INTEGRITY}" != "ok" ]; then
    echo "[FAIL] Восстановленная БД не прошла integrity_check: ${FINAL_INTEGRITY}"
    send_alert "Restore FAILED" "После восстановления БД из ${BACKUP_FILE} integrity_check вернул: ${FINAL_INTEGRITY}. Попробуйте другой бэкап."
    exit 1
fi
echo "[RESTORE] Финальный integrity_check: ok"

# ---------------------------------------------------------------------------
# 7. Права доступа (если запущено от root на хосте)
# ---------------------------------------------------------------------------
if [ "$(id -u)" = "0" ] && [ "${RESTORE_IN_CONTAINER}" = "false" ]; then
    echo "[RESTORE] Установка прав доступа (1000:1000) для data/..."
    chown -R 1000:1000 "$(dirname "${DB_PATH}")" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 8. Запуск бота (если не в контейнере)
# ---------------------------------------------------------------------------
if [ "${RESTORE_IN_CONTAINER}" = "false" ]; then
    echo "[RESTORE] Запуск бота через docker compose..."
    if docker compose -f /srv/bots/lenreg-ticket-bot/docker-compose.yml start bot 2>/dev/null; then
        echo "[RESTORE] Бот запущен"
    else
        echo "[WARN] Не удалось запустить бота через docker compose"
        echo "[WARN] Запустите вручную: docker compose -f /srv/bots/lenreg-ticket-bot/docker-compose.yml start bot"
    fi
else
    echo "[RESTORE] Режим in-container: бот сам переподключится через WAL, перезапуск не требуется"
fi

# ---------------------------------------------------------------------------
# 9. Алерт об успешном восстановлении
# ---------------------------------------------------------------------------
echo "[RESTORE] Восстановление завершено успешно"
send_alert "Restore OK" "БД восстановлена из бэкапа:
• Файл: ${BACKUP_FILE}
• Размер: ${BACKUP_SIZE_HUMAN}
• Аварийный бэкап: ${EMERGENCY_DIR}/
• Статус: ok" "high"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Восстановление завершено ==="
exit 0
