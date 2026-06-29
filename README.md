# lenreg-ticket-bot — Telegram-бот мониторинга слотов записи к врачу (Ленинградская область)

Telegram-бот для отслеживания свободных талонов на портале [zdrav.lenreg.ru](https://zdrav.lenreg.ru). Позволяет выбирать врача, настраивать фоновый мониторинг и получать уведомления при появлении или исчезновении слотов.

Подробная документация: [`WIKI.md`](WIKI.md), архитектура: [`specs/ARCHITECTURE.md`](specs/ARCHITECTURE.md).

## Быстрый старт

### Docker (рекомендуемый способ)

```bash
bash <(curl -Ls https://raw.githubusercontent.com/acidmsg/lenreg-ticket-bot/main/scripts/install.sh) --fresh
```

<details>
<summary>Флаги, переменные окружения, сервисы и полезные команды</summary>

**Флаги установочного скрипта:**

| Флаг                     | Назначение                               |
| ------------------------ | ---------------------------------------- |
| _(без флагов)_           | Быстрый деплой с кэшем (~10–30 сек)      |
| `--fresh` / `--no-cache` | Полная пересборка Docker-образа без кэша |
| `--clean`                | Сброс `data/` и `logs/` (чистая БД)      |

**Обязательные переменные окружения** (скрипт запросит их в интерактивном режиме или прочитает из переменных окружения):

| Переменная     | Описание                                                              |
| -------------- | --------------------------------------------------------------------- |
| `BOT_TOKEN`    | Токен Telegram-бота (получить у [@BotFather](https://t.me/BotFather)) |
| `API_TOKEN`    | API-токен для портала zdrav.lenreg.ru                                 |
| `ADMIN_IDS`    | Telegram ID администраторов (через запятую)                           |
| `MINI_APP_URL` | Публичный URL Telegram Mini App (HTTPS)                               |

**Опциональные переменные** (если не заданы — скрипт сгенерирует автоматически или предложит значение по умолчанию):

| Переменная              | Назначение                         | По умолчанию          |
| ----------------------- | ---------------------------------- | --------------------- |
| `WEB_DASHBOARD_PORT`    | Порт веб-дашборда                  | `8080`                |
| `WEB_DASHBOARD_API_KEY` | API-ключ для дашборда              | генерируется          |
| `REDIS_PASSWORD`        | Пароль Redis                       | генерируется          |
| `SENTRY_DSN`            | Sentry DSN для отслеживания ошибок | _(пусто — отключено)_ |
| `NTFY_TOPIC_URL`        | NTFY-топик для push-уведомлений    | _(пусто — отключено)_ |
| `LOG_LEVEL`             | Уровень логирования                | `INFO`                |

Полный перечень — в [`.env.example`](.env.example).

**Сервисы:**

| Сервис  | Назначение                           | Порты                      |
| ------- | ------------------------------------ | -------------------------- |
| `redis` | FSM-хранилище и кэш                  | `127.0.0.1:6379`           |
| `bot`   | Telegram-бот (polling) + веб-дашборд | `127.0.0.1:9090` (метрики) |

**Полезные команды:**

```bash
# Просмотр логов
docker compose logs -f bot

# Статус контейнеров
docker compose ps

# Перезапуск после изменения .env
docker compose up -d --force-recreate bot

# Остановка всех контейнеров
docker compose down
```

**Настройка файрвола (UFW):**

```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

При использовании Cloudflare Proxy порт веб-дашборда должен быть из списка поддерживаемых: `80`, `8080`, `8880`, `2052`, `2082`, `2086`, `2095` (HTTP).

</details>

<details>
<summary>Ручная установка (без Docker)</summary>

**Требования:** Python 3.11+, Redis, Poetry (рекомендуется) или pip.

```bash
# 1. Клонирование
git clone https://github.com/acidmsg/lenreg-ticket-bot.git
cd lenreg-ticket-bot

# 2. Настройка окружения
cp .env.example .env
# Заполните BOT_TOKEN, PROXY_URL, ADMIN_IDS и другие обязательные переменные

# 3. Установка зависимостей
poetry install

# 4. Запуск Redis
redis-server

# 5. Запуск бота
poetry run python -m src.main
```

</details>

## Лицензия

ISC. Подробнее — в [`pyproject.toml`](pyproject.toml:7).
