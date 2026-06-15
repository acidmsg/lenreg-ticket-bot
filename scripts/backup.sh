#!/usr/bin/env bash
# ==============================================================================
# Скрипт резервного копирования SQLite (bot.db)
#
# Использование:
#   chmod +x scripts/backup.sh
#   bash scripts/backup.sh [daily|weekly|monthly]
#
# Что делает:
#   1. Блокирует параллельный запуск (lock-файл /tmp/backup.lock)
#   2. Создаёт бэкап SQLite через .backup (безопасно при WAL)
#   3. Верифицирует бэкап: integrity_check + количество таблиц
#   4. Сохраняет в трёхуровневую структуру: daily/ → weekly/ → monthly/
#   5. Ротирует старые бэкапы сверх лимита в каждой категории
#   6. Отправляет алерты через NTFY при ошибках
#
# Переменные окружения (с дефолтами для хоста):
#   SQLITE_DB_PATH   — путь к исходной БД (default: data/bot.db)
#   BACKUP_DIR       — корневая директория бэкапов (default: data/backups)
#   BACKUP_DAILY_RETENTION   — хранить N daily-бэкапов (default: 7)
#   BACKUP_WEEKLY_RETENTION  — хранить N weekly-бэкапов (default: 4)
#   BACKUP_MONTHLY_RETENTION — хранить N monthly-бэкапов (default: 3)
#   NTFY_BACKUP_TOPIC        — URL NTFY-топика для алертов (default: пусто)
#
# Cron (ежедневно в 03:00 МСК = 00:00 UTC):
#   0 0 * * * /root/lenreg-ticket-bot/scripts/backup.sh daily >> /root/backups/backup.log 2>&1
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Параметризация через переменные окружения
# ---------------------------------------------------------------------------
DB_PATH="${SQLITE_DB_PATH:-data/bot.db}"
BACKUP_DIR="${BACKUP_DIR:-data/backups}"
RETENTION_DAYS="${BACKUP_DAILY_RETENTION:-7}"
RETENTION_WEEKS="${BACKUP_WEEKLY_RETENTION:-4}"
RETENTION_MONTHS="${BACKUP_MONTHLY_RETENTION:-3}"
NTFY_URL="${NTFY_BACKUP_TOPIC:-}"

# Аргумент командной строки: daily (по умолчанию), weekly, monthly
BACKUP_TYPE="${1:-daily}"

# Ручной бэкап: если MANUAL_BACKUP=true, файл кладётся в manual/ вместо daily/
MANUAL_BACKUP="${MANUAL_BACKUP:-false}"
BACKUP_MANUAL_RETENTION="${BACKUP_MANUAL_RETENTION:-10}"

# Временные метки
TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
DATE_SUFFIX=$(date '+%Y-%m-%d')
DAY_OF_WEEK=$(date '+%u')   # 1=Пн ... 7=Вс
DAY_OF_MONTH=$(date '+%d')  # 01..31

# Имя файла бэкапа
BACKUP_FILENAME="bot_${TIMESTAMP}.db"

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

# ---------------------------------------------------------------------------
# Функция: верификация бэкапа
# ---------------------------------------------------------------------------
verify_backup() {
    local backup_file="$1"

    # 1. Файл существует и не пуст
    if [ ! -s "${backup_file}" ]; then
        echo "[FAIL] Бэкап ${backup_file} пуст или отсутствует"
        return 1
    fi

    # 2. PRAGMA integrity_check — ожидаем ровно "ok"
    local integrity_result
    integrity_result=$(sqlite3 "${backup_file}" "PRAGMA integrity_check" 2>&1)
    if [ "${integrity_result}" != "ok" ]; then
        echo "[FAIL] integrity_check для ${backup_file}: ${integrity_result}"
        return 1
    fi
    echo "[VERIFY] integrity_check: ok"

    # 3. Проверка количества таблиц (минимум 5)
    local table_count
    table_count=$(sqlite3 "${backup_file}" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'" 2>&1)
    if [ -z "${table_count}" ] || [ "${table_count}" -lt 5 ]; then
        echo "[FAIL] Слишком мало таблиц в ${backup_file}: ${table_count:-0}"
        return 1
    fi
    echo "[VERIFY] Количество таблиц: ${table_count}"

    echo "[OK] Бэкап ${backup_file} прошёл верификацию"
    return 0
}

# ---------------------------------------------------------------------------
# Функция: ротация — оставить N последних файлов по маске
# ---------------------------------------------------------------------------
rotate_by_count() {
    local dir="$1"
    local pattern="$2"
    local keep="$3"

    # Собираем файлы, сортированные по времени (новые первыми)
    local files
    # shellcheck disable=SC2207
    files=($(ls -1t "${dir}"/${pattern} 2>/dev/null || true))

    if [ ${#files[@]} -gt "${keep}" ]; then
        for ((i = keep; i < ${#files[@]}; i++)); do
            rm -f "${files[$i]}"
            echo "[ROTATE] Удалён: ${files[$i]}"
        done
        echo "[ROTATE] Категория ${dir}: удалено $((${#files[@]} - keep)) файлов, оставлено ${keep}"
    else
        echo "[ROTATE] Категория ${dir}: файлов ${#files[@]}, лимит ${keep} — удалять нечего"
    fi
}

# ---------------------------------------------------------------------------
# Защита от параллельного запуска
# ---------------------------------------------------------------------------
LOCK_FILE="/tmp/backup.lock"

# Trap для вывода строки с ошибкой при падении (set -e)
trap 'echo "[ERROR] Скрипт упал на строке ${LINENO:-?}, код выхода ${?}" >&2' ERR

exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    echo "[SKIP] Бэкап уже выполняется (lock-файл ${LOCK_FILE} занят)"
    exit 0
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Запуск резервного копирования (тип: ${BACKUP_TYPE}) ==="

# ---------------------------------------------------------------------------
# Проверка исходной БД
# ---------------------------------------------------------------------------
if [ ! -f "${DB_PATH}" ]; then
    echo "[FAIL] Исходная БД не найдена: ${DB_PATH}"
    send_alert "Backup FAILED" "Исходная БД не найдена: ${DB_PATH}"
    exit 1
fi

# ---------------------------------------------------------------------------
# Создание директорий
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}/daily"
mkdir -p "${BACKUP_DIR}/weekly"
mkdir -p "${BACKUP_DIR}/monthly"
mkdir -p "${BACKUP_DIR}/manual"

# ---------------------------------------------------------------------------
# 1. Создание бэкапа через sqlite3 .backup
# ---------------------------------------------------------------------------
# Определяем целевую директорию: manual/ если MANUAL_BACKUP=true, иначе daily/
if [ "${MANUAL_BACKUP}" = "true" ]; then
    TARGET_DIR="${BACKUP_DIR}/manual"
    echo "[BACKUP] Ручной бэкап → manual/"
else
    TARGET_DIR="${BACKUP_DIR}/daily"
fi

BACKUP_FILE="${TARGET_DIR}/${BACKUP_FILENAME}"

echo "[BACKUP] Создание бэкапа: ${BACKUP_FILE}"
sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"

# Размер созданного бэкапа
BACKUP_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null || echo 0)
BACKUP_SIZE_HUMAN=$(numfmt --to=iec --suffix=B "${BACKUP_SIZE}" 2>/dev/null || echo "${BACKUP_SIZE} bytes")
echo "[BACKUP] Размер: ${BACKUP_SIZE_HUMAN}"

# ---------------------------------------------------------------------------
# 2. Верификация бэкапа
# ---------------------------------------------------------------------------
if ! verify_backup "${BACKUP_FILE}"; then
    echo "[FAIL] Верификация не пройдена — удаляю битый бэкап"
    # Создаём маркер .integrity_fail
    touch "${BACKUP_FILE}.integrity_fail"
    rm -f "${BACKUP_FILE}"
    send_alert "Backup FAILED" "Бэкап ${BACKUP_FILE} не прошёл верификацию и был удалён. Требуется проверка."
    exit 1
fi

# Создаём маркер .integrity_ok — сигнал для API, что бэкап проверен
touch "${BACKUP_FILE}.integrity_ok"
echo "[MARKER] Создан ${BACKUP_FILE}.integrity_ok"

# ---------------------------------------------------------------------------
# 3. Копирование в weekly/monthly по расписанию (только для daily-бэкапов)
# ---------------------------------------------------------------------------
if [ "${MANUAL_BACKUP}" != "true" ]; then
    # Воскресенье (day of week = 7) → weekly
    if [ "${DAY_OF_WEEK}" = "7" ]; then
        cp "${BACKUP_FILE}" "${BACKUP_DIR}/weekly/${BACKUP_FILENAME}"
        touch "${BACKUP_DIR}/weekly/${BACKUP_FILENAME}.integrity_ok"
        echo "[COPY] Воскресный бэкап сохранён в weekly/"
    fi

    # 1-е число месяца → monthly
    if [ "${DAY_OF_MONTH}" = "01" ]; then
        cp "${BACKUP_FILE}" "${BACKUP_DIR}/monthly/${BACKUP_FILENAME}"
        touch "${BACKUP_DIR}/monthly/${BACKUP_FILENAME}.integrity_ok"
        echo "[COPY] Месячный бэкап (1-е число) сохранён в monthly/"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Ротация старых бэкапов
# ---------------------------------------------------------------------------
echo "[ROTATE] Начало ротации..."
rotate_by_count "${BACKUP_DIR}/daily" "bot_*.db" "${RETENTION_DAYS}"
rotate_by_count "${BACKUP_DIR}/weekly" "bot_*.db" "${RETENTION_WEEKS}"
rotate_by_count "${BACKUP_DIR}/monthly" "bot_*.db" "${RETENTION_MONTHS}"
rotate_by_count "${BACKUP_DIR}/manual" "bot_*.db" "${BACKUP_MANUAL_RETENTION}"

# Чистим осиротевшие маркерные файлы (без соответствующего .db)
for cat_dir in "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" "${BACKUP_DIR}/monthly" "${BACKUP_DIR}/manual"; do
    for marker in "${cat_dir}"/bot_*.db.integrity_*; do
        [ -f "${marker}" ] || continue
        db_file="${marker%.integrity_*}"
        if [ ! -f "${db_file}" ]; then
            rm -f "${marker}"
        fi
    done
done 2>/dev/null

# ---------------------------------------------------------------------------
# 5. Ежедневная сводка (только при daily-запуске, не для manual)
# ---------------------------------------------------------------------------
if [ "${BACKUP_TYPE}" = "daily" ] && [ "${MANUAL_BACKUP}" != "true" ]; then
    DAILY_COUNT=$(ls -1 "${BACKUP_DIR}/daily"/bot_*.db 2>/dev/null | wc -l)
    WEEKLY_COUNT=$(ls -1 "${BACKUP_DIR}/weekly"/bot_*.db 2>/dev/null | wc -l)
    MONTHLY_COUNT=$(ls -1 "${BACKUP_DIR}/monthly"/bot_*.db 2>/dev/null | wc -l)
    MANUAL_COUNT=$(ls -1 "${BACKUP_DIR}/manual"/bot_*.db 2>/dev/null | wc -l)
    TOTAL_COUNT=$((DAILY_COUNT + WEEKLY_COUNT + MONTHLY_COUNT + MANUAL_COUNT))

    # Суммарный размер всех бэкапов
    TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1 || echo "N/A")

    SUMMARY="Ежедневная сводка бэкапов:
• Последний бэкап: ${BACKUP_FILENAME} (${BACKUP_SIZE_HUMAN})
• Статус последнего: ok (integrity_check пройден)
• Количество: daily=${DAILY_COUNT}, weekly=${WEEKLY_COUNT}, monthly=${MONTHLY_COUNT}, manual=${MANUAL_COUNT} (всего: ${TOTAL_COUNT})
• Общий размер: ${TOTAL_SIZE}"

    echo "[SUMMARY] ${SUMMARY}"
    if [ -n "${NTFY_URL}" ]; then
        curl -s -H "Title: Backup Daily Summary" \
             -H "Priority: low" \
             -H "Tags: floppy_disk" \
             -d "${SUMMARY}" \
             "${NTFY_URL}" > /dev/null 2>&1 || true
    fi
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Резервное копирование завершено успешно ==="

# Lock-файл освободится при выходе из скрипта (exec 200>)
exit 0
