#!/usr/bin/env bash
# ===========================================================================
# Интерактивный установочный скрипт zdrav.lenreg
#
# Поддерживает два режима запуска:
#   1. Из клонированного репозитория:  bash scripts/install.sh
#   2. Через curl pipe:                curl -sSL <raw-url> | bash
#
# Для приватного репозитория используйте:
#   GITHUB_TOKEN=ghp_xxx curl -sSL -H "Authorization: token $GITHUB_TOKEN" \
#     https://raw.githubusercontent.com/acidmsg/lenreg_ticket_bot/mini_app_beta/scripts/install.sh | \
#     GITHUB_TOKEN=$GITHUB_TOKEN bash
#
# Совместимость: Ubuntu 20.04+, Debian 11+
# ===========================================================================
set -euo pipefail

# ===========================================================================
# Этап 0: Цвета и утилиты
# ===========================================================================

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функции логирования
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

# Запрос ввода с значением по умолчанию
# Аргументы: $1 — текст вопроса, $2 — значение по умолчанию, $3 — имя переменной (для присваивания через eval)
ask() {
    local prompt="$1"
    local default="$2"
    local varname="$3"

    if [ -n "$default" ]; then
        read -rp "$(echo -e "${CYAN}[?]${NC} ${prompt} [${default}]: ")" input
    else
        read -rp "$(echo -e "${CYAN}[?]${NC} ${prompt}: ")" input
    fi

    # Если ввод пустой — использовать default
    if [ -z "$input" ]; then
        input="$default"
    fi

    # Присвоить значение переменной через eval
    eval "$varname=\"$input\""
}

# Баннер
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}   Установка zdrav.lenreg — Telegram бот + Mini App          ${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""

# ===========================================================================
# Этап 1: Проверка зависимостей
# ===========================================================================

info "Проверка зависимостей..."

# Проверить Docker
if ! command -v docker >/dev/null 2>&1; then
    error "Docker не установлен."
    echo ""
    echo "  Установите Docker:"
    echo "    curl -fsSL https://get.docker.com | sudo bash"
    echo "    sudo usermod -aG docker \$USER"
    echo "  Затем перезайдите в систему и запустите скрипт снова."
    exit 1
fi
success "Docker найден: $(docker --version)"

# Проверить Docker Compose (v2 plugin)
if ! docker compose version >/dev/null 2>&1; then
    error "Docker Compose (v2 plugin) не установлен."
    echo ""
    echo "  Установите:"
    echo "    sudo apt-get update && sudo apt-get install -y docker-compose-plugin"
    exit 1
fi
success "Docker Compose найден: $(docker compose version --short 2>/dev/null || echo 'v2')"

# Проверить git
if ! command -v git >/dev/null 2>&1; then
    error "git не установлен."
    echo ""
    echo "  Установите:"
    echo "    sudo apt-get update && sudo apt-get install -y git"
    exit 1
fi
success "git найден: $(git --version)"

echo ""

# ===========================================================================
# Этап 2: Клонирование / обновление репозитория
# ===========================================================================

# URL репозитория — используем HTTPS с токеном для приватных репозиториев
GITHUB_OWNER="acidmsg"
GITHUB_REPO="lenreg_ticket_bot"
BRANCH="mini_app_beta"

# Если передан GITHUB_TOKEN — используем HTTPS, иначе SSH
if [ -n "${GITHUB_TOKEN:-}" ]; then
    REPO_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git"
    info "Используется HTTPS с токеном для клонирования"
else
    REPO_URL="git@github.com:${GITHUB_OWNER}/${GITHUB_REPO}.git"
    info "Используется SSH для клонирования"
fi
INSTALL_DIR="${HOME}/zdrav.lenreg"

# Определяем, запущен ли скрипт изнутри репозитория
# Признак: наличие docker-compose.yml и .env.example в текущей директории
IN_REPO=false
if [ -f "docker-compose.yml" ] && [ -f ".env.example" ]; then
    IN_REPO=true
fi

if [ "$IN_REPO" = true ]; then
    info "Обнаружен существующий репозиторий в текущей директории."
    INSTALL_DIR="$(pwd)"
    cd "$INSTALL_DIR"

    # Обновить до актуальной версии
    info "Обновление репозитория (ветка: ${BRANCH})..."
    git fetch origin 2>/dev/null || warn "Не удалось выполнить git fetch (возможно, нет доступа к GitHub)"
    git checkout "$BRANCH" 2>/dev/null || warn "Не удалось переключиться на ветку ${BRANCH}"
    git pull origin "$BRANCH" 2>/dev/null || warn "Не удалось выполнить git pull"
    success "Репозиторий обновлён."
else
    info "Клонирование репозитория в ${INSTALL_DIR}..."

    if [ -d "$INSTALL_DIR" ]; then
        warn "Директория ${INSTALL_DIR} уже существует."
        ask "Обновить существующий проект? (y/n)" "y" UPDATE
        if [ "$UPDATE" = "y" ] || [ "$UPDATE" = "Y" ]; then
            cd "$INSTALL_DIR"
            info "Обновление репозитория (ветка: ${BRANCH})..."
            git fetch origin 2>/dev/null || warn "Не удалось выполнить git fetch"
            git checkout "$BRANCH" 2>/dev/null || warn "Не удалось переключиться на ветку ${BRANCH}"
            git pull origin "$BRANCH" 2>/dev/null || warn "Не удалось выполнить git pull"
            success "Репозиторий обновлён."
        else
            info "Пропуск обновления. Использую существующую директорию."
            cd "$INSTALL_DIR"
        fi
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        git checkout "$BRANCH" 2>/dev/null || warn "Не удалось переключиться на ветку ${BRANCH}"
        success "Репозиторий клонирован."
    fi
fi

echo ""

# ===========================================================================
# Этап 3: Интерактивная настройка .env
# ===========================================================================

info "Настройка конфигурации (.env)..."
echo ""

# --- Обязательные параметры ---

BOT_TOKEN=""
while [ -z "$BOT_TOKEN" ]; do
    ask "Введите токен бота (от @BotFather)" "" BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        error "BOT_TOKEN не может быть пустым. Попробуйте снова."
    fi
done

API_TOKEN=""
while [ -z "$API_TOKEN" ]; do
    ask "Введите API-токен для zdrav.lenreg" "" API_TOKEN
    if [ -z "$API_TOKEN" ]; then
        error "API_TOKEN не может быть пустым. Попробуйте снова."
    fi
done

ADMIN_IDS=""
while [ -z "$ADMIN_IDS" ]; do
    ask "Введите Telegram ID администраторов (через запятую)" "" ADMIN_IDS
    if [ -z "$ADMIN_IDS" ]; then
        error "ADMIN_IDS не может быть пустым. Попробуйте снова."
    fi
done

MINI_APP_URL=""
while [ -z "$MINI_APP_URL" ]; do
    ask "Введите URL Mini App (например, https://lenregbot.acidbox.top/app/)" "" MINI_APP_URL
    if [ -z "$MINI_APP_URL" ]; then
        error "MINI_APP_URL не может быть пустым. Попробуйте снова."
    fi
done

echo ""

# --- Опциональные параметры ---

ask "Порт веб-дашборда" "8080" WEB_DASHBOARD_PORT

ask "API-ключ для дашборда (оставьте пустым для генерации)" "" WEB_DASHBOARD_API_KEY
if [ -z "$WEB_DASHBOARD_API_KEY" ]; then
    WEB_DASHBOARD_API_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "")
    if [ -n "$WEB_DASHBOARD_API_KEY" ]; then
        success "Сгенерирован API-ключ дашборда: ${WEB_DASHBOARD_API_KEY}"
    else
        warn "Не удалось сгенерировать API-ключ (нет openssl и python3). Ключ оставлен пустым."
    fi
fi

ask "Пароль Redis (оставьте пустым для генерации)" "" REDIS_PASSWORD
if [ -z "$REDIS_PASSWORD" ]; then
    REDIS_PASSWORD=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || echo "")
    if [ -n "$REDIS_PASSWORD" ]; then
        success "Сгенерирован пароль Redis: ${REDIS_PASSWORD}"
    else
        error "Не удалось сгенерировать пароль Redis (нет openssl и python3)."
        error "Установите openssl (sudo apt-get install -y openssl) и запустите скрипт снова."
        exit 1
    fi
fi

ask "Sentry DSN (оставьте пустым для отключения)" "" SENTRY_DSN

ask "NTFY URL для уведомлений (оставьте пустым для отключения)" "" NTFY_TOPIC_URL

ask "Уровень логирования" "INFO" LOG_LEVEL

echo ""

# ===========================================================================
# Этап 4: Генерация .env
# ===========================================================================

info "Генерация .env файла..."

# Если .env уже существует — делаем бэкап
if [ -f ".env" ]; then
    BACKUP=".env.backup.$(date +%Y%m%d_%H%M%S)"
    cp .env "$BACKUP"
    warn "Существующий .env сохранён в ${BACKUP}"
fi

cat > .env << ENVEOF
# =============================================================================
# .env — сгенерирован автоматически скриптом install.sh
# Дата генерации: $(date '+%Y-%m-%d %H:%M:%S %Z')
# =============================================================================

# === Telegram Bot ===
BOT_TOKEN=${BOT_TOKEN}

# === API здоров.ленрег ===
API_TOKEN=${API_TOKEN}

# === Proxy Configuration ===
# VPS в Германии — прокси не требуется
PROXY_URL=

# === File Paths ===
SQLITE_DB_PATH=data/bot.db
CACHE_PATH=data/monitoring_cache.json

# === Redis ===
# Внутри Docker используется hostname сервиса redis
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}

# === Qdrant (Codebase Indexing) ===
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# === Patient IDs for doctor discovery ===
DISCOVERY_PATIENT_ID_ADULT=
DISCOVERY_PATIENT_ID_CHILD=

# === Admin Telegram ID(s) ===
ADMIN_IDS=${ADMIN_IDS}

# === Error notifications (M2) ===
ERROR_NOTIFY_ENABLED=True
NTFY_TOPIC_URL=${NTFY_TOPIC_URL}
SENTRY_DSN=${SENTRY_DSN}
ENVIRONMENT=production

# === Logging ===
LOG_LEVEL=${LOG_LEVEL}

# === Slot formatting thresholds ===
SLOT_DETAIL_THRESHOLD=10
SLOT_COMPACT_THRESHOLD=15

# === Rate limiting (M3) ===
USER_RATE_LIMIT_MAX=30
USER_RATE_LIMIT_PERIOD=60

# === Metrics (Prometheus) ===
METRICS_PORT=9090

# === API Versioning ===
API_VERSION=1.0.0
API_VALIDATE_RESPONSES=True

# === i18n ===
BOT_LANGUAGE=ru

# === API zdrav.lenreg.ru ===
API_BASE_URL=https://zdrav.lenreg.ru/api
REFERER_URL=https://zdrav.lenreg.ru/signup/free/
ORIGIN_URL=https://zdrav.lenreg.ru
CSRF_TOKEN=NOTPROVIDED
DISTRICT_ID=4

# === Default identifiers ===
DEFAULT_CLINIC_ID=272
DENTAL_CLINIC_ID=272
DEFAULT_BIRTHDAY=1990-01-01
SIGNUP_URL=https://zdrav.lenreg.ru/signup/free/

# === Intervals ===
CHECK_INTERVAL=300
DISCOVERY_INTERVAL=1800
CLEANUP_INTERVAL=3600

# === API Schema Change Detection (F8) ===
SCHEMA_CHECK_INTERVAL=3600
SCHEMA_CHECK_ENABLED=true

# === Web Dashboard (F5) ===
WEB_DASHBOARD_ENABLED=True
WEB_DASHBOARD_PORT=${WEB_DASHBOARD_PORT}
WEB_DASHBOARD_API_KEY=${WEB_DASHBOARD_API_KEY}

# === Mini App (F10) ===
MINI_APP_ENABLED=True
MINI_APP_URL=${MINI_APP_URL}
MINI_APP_INITDATA_MAX_AGE=86400

# === Python / Encoding ===
PYTHONUTF8=1
ENVEOF

success ".env сгенерирован."
echo ""

# ===========================================================================
# Этап 5: Создание директорий
# ===========================================================================

info "Создание рабочих директорий..."
mkdir -p data logs
success "Директории data/ и logs/ созданы."
echo ""

# ===========================================================================
# Этап 6: Сборка и запуск Docker-контейнеров
# ===========================================================================

info "Сборка Docker-образа..."
docker compose build

info "Запуск контейнеров..."
docker compose up -d

echo ""

# ===========================================================================
# Этап 7: Проверка файрвола и финальные сообщения
# ===========================================================================

success "Установка завершена!"
echo ""

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Полезные команды:${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Проверить логи бота:"
echo -e "    ${CYAN}docker compose logs -f bot${NC}"
echo ""
echo "  Проверить статус всех контейнеров:"
echo -e "    ${CYAN}docker compose ps${NC}"
echo ""
echo "  Перезапустить бота после изменения .env:"
echo -e "    ${CYAN}docker compose up -d --force-recreate bot${NC}"
echo ""
echo "  Остановить все контейнеры:"
echo -e "    ${CYAN}docker compose down${NC}"
echo ""
echo "  Mini App доступен по адресу:"
echo -e "    ${GREEN}${MINI_APP_URL}${NC}"
echo ""
echo "  Веб-дашборд доступен на порту ${WEB_DASHBOARD_PORT}:"
echo -e "    ${GREEN}http://<ip-сервера>:${WEB_DASHBOARD_PORT}/${NC}"
echo ""

# Подсказка про файрвол
if command -v ufw >/dev/null 2>&1; then
    warn "Не забудьте открыть порт ${WEB_DASHBOARD_PORT} в файрволе (ufw):"
    echo ""
    echo -e "    ${CYAN}sudo ufw allow ${WEB_DASHBOARD_PORT}/tcp${NC}"
    echo -e "    ${CYAN}sudo ufw reload${NC}"
    echo ""
fi

# Подсказка про Cloudflare Proxy
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  При использовании Cloudflare Proxy:${NC}"
echo -e "${YELLOW}  Порт ${WEB_DASHBOARD_PORT} должен быть одним из поддерживаемых:${NC}"
echo -e "${YELLOW}  80, 8080, 8880, 2052, 2082, 2086, 2095 (HTTP)${NC}"
echo -e "${YELLOW}  Если порт другой — измените WEB_DASHBOARD_PORT в .env${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

success "Готово! Бот запущен в production-режиме."
