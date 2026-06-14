#!/usr/bin/env bash
# ==============================================================================
# Скрипт проверки здоровья системы бэкапов
#
# Использование:
#   bash scripts/backup_healthcheck.sh
#
# Проверяет:
#   1. Последний daily-бэкап не старше 24 часов
#   2. Последний бэкап проходит PRAGMA integrity_check
#   3. В BACKUP_DIR есть минимум 100MB свободного места
#   4. Количество бэкапов в каждой категории
#
# Вывод: JSON с результатом проверки
# Код возврата: 0 — всё ok, 1 — есть проблемы
#
# Переменные окружения:
#   BACKUP_DIR              — корневая директория бэкапов (default: data/backups)
#   BACKUP_MAX_AGE_HOURS    — макс. возраст последнего бэкапа в часах (default: 24)
#   BACKUP_MIN_FREE_MB      — мин. свободного места в MB (default: 100)
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Параметризация
# ---------------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-data/backups}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-24}"
MIN_FREE_MB="${BACKUP_MIN_FREE_MB:-100}"

# ---------------------------------------------------------------------------
# Инициализация JSON-ответа
# ---------------------------------------------------------------------------
STATUS="ok"
ISSUES=()

# Функция для экранирования строк в JSON
json_escape() {
    local s="${1//\\/\\\\}"
    s="${s//\"/\\\"}"
    echo -n "${s}"
}

# ---------------------------------------------------------------------------
# Поиск последнего daily-бэкапа
# ---------------------------------------------------------------------------
LATEST_DAILY=$(ls -1t "${BACKUP_DIR}/daily"/bot_*.db 2>/dev/null | head -1 || true)

if [ -z "${LATEST_DAILY}" ]; then
    STATUS="fail"
    ISSUES+=("Нет ни одного daily-бэкапа в ${BACKUP_DIR}/daily/")
    LAST_BACKUP="none"
    LAST_SIZE="0"
    LAST_SIZE_HUMAN="0 B"
    AGE_HOURS="N/A"
else
    LAST_BACKUP=$(basename "${LATEST_DAILY}")
    LAST_SIZE=$(stat -c%s "${LATEST_DAILY}" 2>/dev/null || stat -f%z "${LATEST_DAILY}" 2>/dev/null || echo 0)
    LAST_SIZE_HUMAN=$(numfmt --to=iec --suffix=B "${LAST_SIZE}" 2>/dev/null || echo "${LAST_SIZE} bytes")

    # Возраст последнего бэкапа в часах
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS: stat -f %m
        FILE_MTIME=$(stat -f %m "${LATEST_DAILY}" 2>/dev/null)
    else
        # Linux: stat -c %Y
        FILE_MTIME=$(stat -c %Y "${LATEST_DAILY}" 2>/dev/null)
    fi
    NOW_EPOCH=$(date +%s)
    AGE_SECONDS=$((NOW_EPOCH - FILE_MTIME))
    AGE_HOURS=$((AGE_SECONDS / 3600))

    if [ "${AGE_HOURS}" -gt "${MAX_AGE_HOURS}" ]; then
        STATUS="fail"
        ISSUES+=("Последний бэкап старше ${MAX_AGE_HOURS} часов: возраст ${AGE_HOURS}ч (${LAST_BACKUP})")
    fi

    # Проверка целостности последнего бэкапа
    INTEGRITY_RESULT=$(sqlite3 "${LATEST_DAILY}" "PRAGMA integrity_check" 2>&1 || echo "ERROR: sqlite3 failed")
    if [ "${INTEGRITY_RESULT}" != "ok" ]; then
        STATUS="fail"
        ISSUES+=("integrity_check для ${LAST_BACKUP}: ${INTEGRITY_RESULT}")
    fi
    INTEGRITY="${INTEGRITY_RESULT}"
fi

# ---------------------------------------------------------------------------
# Проверка свободного места
# ---------------------------------------------------------------------------
if [ -d "${BACKUP_DIR}" ]; then
    # Пытаемся получить свободное место в байтах
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS: df -k и умножаем на 1024
        FREE_KB=$(df -k "${BACKUP_DIR}" 2>/dev/null | tail -1 | awk '{print $4}' || echo 0)
        FREE_BYTES=$((FREE_KB * 1024))
    else
        # Linux: df --output=avail -B1
        FREE_BYTES=$(df --output=avail -B1 "${BACKUP_DIR}" 2>/dev/null | tail -1 || echo 0)
    fi
    FREE_MB=$((FREE_BYTES / 1048576))
    FREE_HUMAN=$(numfmt --to=iec --suffix=B "${FREE_BYTES}" 2>/dev/null || echo "${FREE_MB} MB")

    if [ "${FREE_MB}" -lt "${MIN_FREE_MB}" ]; then
        STATUS="fail"
        ISSUES+=("Мало свободного места: ${FREE_HUMAN} (мин. ${MIN_FREE_MB} MB)")
    fi
else
    FREE_BYTES=0
    FREE_MB=0
    FREE_HUMAN="N/A"
    STATUS="fail"
    ISSUES+=("Директория бэкапов не существует: ${BACKUP_DIR}")
fi

# ---------------------------------------------------------------------------
# Подсчёт бэкапов
# ---------------------------------------------------------------------------
# Используем find вместо ls — не падает при пустой директории и не требует || echo 0,
# что при set -euo pipefail давало двойной вывод (wc + echo).
DAILY_COUNT=$(find "${BACKUP_DIR}/daily" -maxdepth 1 -name "bot_*.db" -type f 2>/dev/null | wc -l)
DAILY_COUNT=$(echo -n "${DAILY_COUNT}" | tr -d '[:space:]')
DAILY_COUNT=${DAILY_COUNT:-0}
WEEKLY_COUNT=$(find "${BACKUP_DIR}/weekly" -maxdepth 1 -name "bot_*.db" -type f 2>/dev/null | wc -l)
WEEKLY_COUNT=$(echo -n "${WEEKLY_COUNT}" | tr -d '[:space:]')
WEEKLY_COUNT=${WEEKLY_COUNT:-0}
MONTHLY_COUNT=$(find "${BACKUP_DIR}/monthly" -maxdepth 1 -name "bot_*.db" -type f 2>/dev/null | wc -l)
MONTHLY_COUNT=$(echo -n "${MONTHLY_COUNT}" | tr -d '[:space:]')
MONTHLY_COUNT=${MONTHLY_COUNT:-0}
MANUAL_COUNT=$(find "${BACKUP_DIR}/manual" -maxdepth 1 -name "bot_*.db" -type f 2>/dev/null | wc -l)
MANUAL_COUNT=$(echo -n "${MANUAL_COUNT}" | tr -d '[:space:]')
MANUAL_COUNT=${MANUAL_COUNT:-0}
TOTAL_COUNT=$((DAILY_COUNT + WEEKLY_COUNT + MONTHLY_COUNT + MANUAL_COUNT))

# ---------------------------------------------------------------------------
# Формирование JSON
# ---------------------------------------------------------------------------
# Формируем массив issues вручную (без jq, только bash)
ISSUES_JSON="["
for i in "${!ISSUES[@]}"; do
    if [ "$i" -gt 0 ]; then
        ISSUES_JSON+=", "
    fi
    ISSUES_JSON+="\"$(json_escape "${ISSUES[$i]}")\""
done
ISSUES_JSON+="]"

cat <<EOF
{
  "status": "${STATUS}",
  "last_backup": "$(json_escape "${LAST_BACKUP:-none}")",
  "last_size_bytes": ${LAST_SIZE:-0},
  "last_size_human": "$(json_escape "${LAST_SIZE_HUMAN:-0 B}")",
  "last_integrity": "$(json_escape "${INTEGRITY:-N/A}")",
  "age_hours": ${AGE_HOURS:-0},
  "max_age_hours": ${MAX_AGE_HOURS},
  "free_space_bytes": ${FREE_BYTES:-0},
  "free_space_human": "$(json_escape "${FREE_HUMAN:-N/A}")",
  "free_space_mb": ${FREE_MB:-0},
  "min_free_mb": ${MIN_FREE_MB},
  "backup_count": ${TOTAL_COUNT},
  "daily_count": ${DAILY_COUNT},
  "weekly_count": ${WEEKLY_COUNT},
  "monthly_count": ${MONTHLY_COUNT},
  "manual_count": ${MANUAL_COUNT},
  "issues": ${ISSUES_JSON}
}
EOF

# ---------------------------------------------------------------------------
# Код возврата
# ---------------------------------------------------------------------------
if [ "${STATUS}" = "ok" ]; then
    exit 0
else
    exit 1
fi
