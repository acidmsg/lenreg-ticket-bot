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

| Переменная                  | Назначение                                                 | По умолчанию          |
| --------------------------- | ---------------------------------------------------------- | --------------------- |
| `WEB_DASHBOARD_PORT`        | Порт веб-дашборда                                          | `8080`                |
| `REDIS_PASSWORD`            | Пароль Redis                                               | генерируется          |
| `SENTRY_DSN`                | Sentry DSN для отслеживания ошибок                         | _(пусто — отключено)_ |
| `NTFY_TOPIC_URL`            | NTFY-топик для push-уведомлений                            | _(пусто — отключено)_ |
| `LOG_LEVEL`                 | Уровень логирования                                        | `INFO`                |
| `API_PINNED_IP`             | Зафиксированный IP API-хоста (пиннинг через `extra_hosts`) | `185.65.149.54`       |
| `DNS_WATCHDOG_INTERVAL_SEC` | Интервал проверки расхождения пиннинга и DNS, сек          | `1800.0`              |

Полный перечень — в [`.env.example`](.env.example).

При смене IP API-хоста (`API_PINNED_IP`) контейнер нужно пересоздать: `extra_hosts` применяется
только при создании контейнера. Порядок действий — в [`WIKI.md`](WIKI.md).

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

Порт дашборда (8080) наружу не открывается: он публикуется только на loopback
(`WEB_BIND_ADDR` = `127.0.0.1`, `WEB_BIND_ADDR_V6` = `[::1]`), а публичный вход
обеспечивает Cloudflare Tunnel (или профиль `caddy`). Разрешающие правила UFW для
8080 не нужны.

```bash
# Проверка: правил для 8080 быть не должно
sudo ufw status
```

При использовании Cloudflare Proxy (без туннеля) порт origin должен быть из списка
поддерживаемых: `80`, `8080`, `8880`, `2052`, `2082`, `2086`, `2095` (HTTP). Для
Cloudflare Tunnel ограничение не действует: ingress идёт на `http://localhost:8080`.

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

## Проверки кода

Полный цикл блокирующих гейтов (MI-гейт `code_health.py --fail-under-mi 20` и гейт мёртвого кода `python -m vulture src`) — через [`Makefile`](Makefile:1) (Linux/macOS) или [`tasks.ps1`](tasks.ps1:1) (Windows). Неблокирующий полный отчёт о здоровье кода — цель `metrics`.

```bash
make lint      # ruff check src tests, mypy src, lint-imports, MI-гейт, vulture, markdownlint, ruff format --check, prettier --check
make check     # lint + pytest (полный CI-цикл)
make metrics   # полный отчёт radon + vulture (MI в режиме warning, неблокирующий)
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 check
.\tasks.ps1 metrics
```

### Python

```bash
poetry install --with dev
pytest          # гейт покрытия задан в pyproject.toml: --cov-fail-under=50 (факт — 71 %)
ruff check src tests
mypy src
lint-imports    # архитектурные контракты слоёв (import-linter)
python -m vulture src  # гейт мёртвого кода, конфигурация [tool.vulture]
```

### Фронтенд Mini App (JS)

JS-модули Mini App (`src/web/static/app/js`) покрыты Jest-тестами (`tests/js/`).

```bash
npm ci          # установка dev-зависимостей
npm run lint:js # ESLint
npm test        # Jest-тесты
```

## Соглашения о коммитах

Заголовок коммита — Conventional Commits (`<type>: <description>`): английский язык, нижний регистр,
без завершающей точки, до 72 символов; перечень типов — в [`.roo/rules/naming.md`](.roo/rules/naming.md:1).

Тело коммита обязательно и отвечает на три вопроса:

- **Почему** — причина изменения: дефект, требование, риск.
- **Что изменено** — перечень затронутых модулей, таблиц и документов.
- **Как проверено** — выполненные проверки: команды гейтов, тесты, ручной сценарий.

```text
feat: add clinic slot scans history

Почему: не было истории сканов, аналитика всплесков талонов невозможна.
Что изменено: миграция v23 (clinic_slot_scans), repo_slots.sync_clinic_slots, тесты.
Как проверено: pytest tests/database/test_repo_slots.py; make lint.
```

Коммит без тела или с незаполненным любым из трёх блоков не принимается: три пункта — минимальный
проверяемый состав сообщения.

## Лицензия

ISC. Подробнее — в [`pyproject.toml`](pyproject.toml:7).
