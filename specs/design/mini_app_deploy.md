# Инструкция по деплою Telegram Mini App на VPS

> **Статус:** Актуально
> **Версия:** 1.0.0
> **Целевая ветка:** `mini_app_beta`
> **Связанные документы:** [`mini_app_plan.md`](mini_app_plan.md), [`ARCHITECTURE.md`](../ARCHITECTURE.md)

## 1. Предварительные требования

Перед началом деплоя убедитесь, что выполнены следующие условия:

- **VPS** с Linux (Германия или любой другой регион), root-доступ или sudo.
- **Docker** и **Docker Compose** установлены на VPS (см. раздел [Подготовка VPS](#6-подготовка-vps)).
- **Домен** `acidbox.top` добавлен в Cloudflare и управляется через него.
- **Порт 8080** открыт в файрволе VPS (инструкции ниже).
- Порт **443** занят xray/VLESS — это нормально, Cloudflare будет терминировать SSL.
- У вас есть **BOT_TOKEN** Telegram-бота (получить у [@BotFather](https://t.me/BotFather)).

## 2. Быстрая установка (рекомендуется)

Установочный скрипт [`scripts/install.sh`](../../scripts/install.sh) автоматизирует весь процесс: проверяет зависимости, клонирует репозиторий, интерактивно настраивает `.env` и запускает Docker-контейнеры.

### На VPS (одна команда)

Репозиторий приватный — для установки нужен [GitHub Personal Access Token](https://github.com/settings/tokens) с правом `repo`.

```bash
# Установить переменную с токеном
export GITHUB_TOKEN="ghp_ваш_токен_здесь"

# Запустить установку
curl -sSL -H "Authorization: token $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/acidmsg/lenreg_ticket_bot/mini_app_beta/scripts/install.sh | \
  GITHUB_TOKEN=$GITHUB_TOKEN bash
```

Или клонировать вручную и запустить скрипт:

```bash
# Через HTTPS с токеном
git clone https://$GITHUB_TOKEN@github.com/acidmsg/lenreg_ticket_bot.git
cd lenreg_ticket_bot
git checkout mini_app_beta
GITHUB_TOKEN=$GITHUB_TOKEN bash scripts/install.sh

# Или через SSH (если настроен SSH-ключ)
git clone git@github.com:acidmsg/lenreg_ticket_bot.git
cd lenreg_ticket_bot
git checkout mini_app_beta
bash scripts/install.sh
```

Скрипт последовательно запросит:

1. **BOT_TOKEN** — токен бота от @BotFather
2. **API_TOKEN** — API-токен zdrav.lenreg
3. **ADMIN_IDS** — Telegram ID администраторов
4. **MINI_APP_URL** — URL Mini App (например, `https://lenregbot.acidbox.top/app/`)
5. Опциональные параметры (порт, пароли, Sentry DSN и др.)

После ввода данных скрипт автоматически сгенерирует `.env`, соберёт Docker-образ и запустит контейнеры.

> **Примечание:** Перед запуском скрипта необходимо выполнить [настройку Cloudflare](#3-настройка-cloudflare) и [файрвола](#4-настройка-файрвола-vps).

## 3. Настройка Cloudflare

### 3.1. Создание DNS-записи

1. Войдите в панель управления Cloudflare.
2. Перейдите в раздел **DNS** → **Records**.
3. Создайте новую запись:

   | Параметр  | Значение                      |
   | --------- | ----------------------------- |
   | **Type**  | A                             |
   | **Name**  | `bot`                         |
   | **IPv4**  | IP-адрес вашей VPS            |
   | **Proxy** | Proxied (🟠 оранжевое облако) |
   | **TTL**   | Auto                          |

4. Нажмите **Save**.

### 3.2. Настройка SSL/TLS

1. Перейдите в раздел **SSL/TLS** → **Overview**.
2. Установите режим: **Full** (не Flexible, не Full Strict).

**Почему именно Full?**

| Режим         | Поведение                                                     | Проблема для нашей схемы                            |
| ------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| Flexible      | Cloudflare ↔ Origin: **HTTP** (порт 80)                       | У нас нет nginx на 80, запросы идут на 8080         |
| **Full**      | Cloudflare ↔ Origin: **HTTPS**, но сертификат не валидируется | ✅ Работает: Cloudflare терминирует SSL → HTTP:8080 |
| Full (Strict) | Cloudflare ↔ Origin: **HTTPS** с валидацией сертификата       | ❌ Требует валидный сертификат на VPS               |

Схема работы с **Full**:

```text
Telegram Client
       │
       ▼
https://lenregbot.acidbox.top/app/
       │
       ▼
Cloudflare (SSL terminated)
       │
       ▼
HTTP → VPS_IP:8080 → Docker (FastAPI)
```

### 3.3. Cloudflare Proxy и поддерживаемые порты

Cloudflare Proxy поддерживает ограниченный набор портов для HTTP/HTTPS. Порт **8080** входит в список поддерживаемых. Полный список: [Cloudflare network ports](https://developers.cloudflare.com/fundamentals/reference/network-ports/).

Поддерживаемые HTTP-порты через Proxy: `80`, `8080`, `8880`, `2052`, `2082`, `2086`, `2095`.

## 4. Настройка файрвола VPS

Необходимо открыть порт **8080** для входящих соединений от Cloudflare.

### 4.1. Рекомендуемый способ: ограничение по IP Cloudflare

Рекомендуется ограничить доступ к порту 8080 только с IP-адресов Cloudflare, чтобы исключить прямой доступ к контейнеру в обход прокси.

Актуальный список IP Cloudflare: [https://www.cloudflare.com/ips/](https://www.cloudflare.com/ips/).

### 4.2. Вариант A: ufw (рекомендуется)

```bash
# Базовое правило (без ограничения по IP — проще, но менее безопасно)
sudo ufw allow 8080/tcp

# С ограничением по IP Cloudflare (рекомендуется)
sudo ufw allow from 173.245.48.0/20 to any port 8080 proto tcp
sudo ufw allow from 103.21.244.0/22 to any port 8080 proto tcp
sudo ufw allow from 103.22.200.0/22 to any port 8080 proto tcp
sudo ufw allow from 103.31.4.0/22 to any port 8080 proto tcp
sudo ufw allow from 141.101.64.0/18 to any port 8080 proto tcp
sudo ufw allow from 108.162.192.0/18 to any port 8080 proto tcp
sudo ufw allow from 190.93.240.0/20 to any port 8080 proto tcp
sudo ufw allow from 188.114.96.0/20 to any port 8080 proto tcp
sudo ufw allow from 197.234.240.0/22 to any port 8080 proto tcp
sudo ufw allow from 198.41.128.0/17 to any port 8080 proto tcp
sudo ufw allow from 162.158.0.0/15 to any port 8080 proto tcp
sudo ufw allow from 104.16.0.0/13 to any port 8080 proto tcp
sudo ufw allow from 104.24.0.0/14 to any port 8080 proto tcp
sudo ufw allow from 172.64.0.0/13 to any port 8080 proto tcp
sudo ufw allow from 131.0.72.0/22 to any port 8080 proto tcp

# Активировать ufw (если ещё не активен)
sudo ufw enable

# Проверить правила
sudo ufw status numbered
```

### 4.3. Вариант B: iptables (если ufw не используется)

```bash
# Базовое правило
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# С ограничением по IP Cloudflare (рекомендуется)
sudo iptables -A INPUT -p tcp --dport 8080 -s 173.245.48.0/20 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -s 103.21.244.0/22 -j ACCEPT
# ... (повторить для всех диапазонов Cloudflare)
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP  # запретить остальным

# Сохранить правила
sudo iptables-save > /etc/iptables/rules.v4
```

## 5. Конфигурация проекта на VPS

### 5.1. Переменные окружения (`.env`)

Создайте файл `.env` на основе [`.env.example`](../../.env.example) и заполните следующие ключи, относящиеся к Mini App:

```bash
# === Web Dashboard (F5) ===
WEB_DASHBOARD_ENABLED=True
WEB_DASHBOARD_PORT=8080
WEB_DASHBOARD_API_KEY=your_dashboard_api_key_here

# === Mini App (F10) ===
MINI_APP_ENABLED=True
MINI_APP_INITDATA_MAX_AGE=86400
MINI_APP_URL=https://lenregbot.acidbox.top/app/

# === Environment ===
ENVIRONMENT=production
```

**Пояснение ключей:**

| Ключ                        | Значение                             | Назначение                                                                                       |
| --------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `WEB_DASHBOARD_PORT`        | `8080`                               | Порт, на котором FastAPI слушает входящие соединения                                             |
| `MINI_APP_URL`              | `https://lenregbot.acidbox.top/app/` | Полный URL Mini App (используется в кнопке `web_app`)                                            |
| `MINI_APP_ENABLED`          | `True`                               | Включает middleware `initData`, роутер `/api/user/*` и статику `/app/`                           |
| `ENVIRONMENT`               | `production`                         | Отключает dev-bypass в middleware [`TelegramInitDataMiddleware`](../../src/web/auth_initdata.py) |
| `MINI_APP_INITDATA_MAX_AGE` | `86400`                              | Максимальный возраст `initData` в секундах (24 часа)                                             |

> **Важно:** При `ENVIRONMENT=production` middleware **не** принимает заголовок `X-Telegram-InitData: bypass` и требует валидную подпись HMAC-SHA256 от Telegram.

### 5.2. docker-compose.yml

Файл [`docker-compose.yml`](../../docker-compose.yml) уже настроен корректно:

- Порт `8080` проброшен как `0.0.0.0:8080:8080` в сервисе `bot` (строка 67).
- Порт `9090` проброшен как `127.0.0.1:9090:9090` для Prometheus-метрик (только localhost).
- Сервис `bot` зависит от `redis` (healthy) и `qdrant` (started).

Фрагмент конфигурации портов в [`docker-compose.yml:64-69`](../../docker-compose.yml:64):

```yaml
ports:
  - '127.0.0.1:9090:9090'
  # Mini App / веб-дашборд — открыт для Cloudflare Proxy (порт 8080)
  - '0.0.0.0:8080:8080'
```

Никаких изменений в `docker-compose.yml` не требуется.

## 6. Подготовка VPS

Данный раздел выполняется **один раз** при первоначальной настройке VPS. Если VPS уже подготовлена, переходите сразу к разделу [Деплой](#7-деплой-пошагово).

### 6.1. Проверка Docker и Docker Compose

```bash
# Проверить Docker
docker --version

# Проверить Docker Compose (v2 — плагин Docker)
docker compose version

# Если docker compose не найден — установить плагин
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Альтернатива: проверить standalone docker-compose (v1)
docker-compose --version
```

В проекте используется [`docker-compose.yml`](../../docker-compose.yml), совместимый и с `docker compose` (v2 plugin) и с `docker-compose` (v1 standalone). Рекомендуется использовать v2 plugin (`docker compose`).

### 6.2. Настройка SSH-ключа для GitHub

Для клонирования приватного репозитория необходимо добавить SSH-ключ VPS в GitHub.

```bash
# Сгенерировать ключ (если нет)
ssh-keygen -t ed25519 -C "vps-deploy"

# Показать публичный ключ
cat ~/.ssh/id_ed25519.pub
```

Скопируйте вывод и добавьте ключ в GitHub:

1. Откройте [GitHub → Settings → SSH and GPG keys](https://github.com/settings/keys).
2. Нажмите **New SSH key**.
3. Вставьте публичный ключ и сохраните.

### 6.3. Клонирование проекта

```bash
# Клонировать репозиторий
git clone git@github.com:acidmsg/lenreg_ticket_bot.git
cd lenreg-ticket-bot

# Переключиться на ветку mini_app_beta
git checkout mini_app_beta
```

> Репозиторий: `acidmsg/lenreg_ticket_bot`.

### 6.4. Подготовка `.env`

Файл `.env` содержит все переменные окружения, необходимые для работы бота. Его можно либо передать с локальной машины, либо создать из шаблона.

#### Вариант A: передать готовый `env.vps` с локальной машины

```bash
# С локальной машины (Windows PowerShell):
scp env.vps user@VPS_IP:/path/to/lenreg-ticket-bot/.env
```

Замените `user`, `VPS_IP` и `/path/to/zdrav.lenreg` на актуальные значения.

#### Вариант B: создать из шаблона и заполнить вручную

```bash
# Скопировать шаблон
cp .env.example .env

# Отредактировать — заполнить все обязательные ключи
nano .env
```

Обязательно проверьте:

- `BOT_TOKEN` — токен вашего бота.
- `MINI_APP_URL=https://lenregbot.acidbox.top/app/`
- `WEB_DASHBOARD_PORT=8080`
- `MINI_APP_ENABLED=True`
- `ENVIRONMENT=production`
- `REDIS_PASSWORD` — придумайте надёжный пароль.
- `ADMIN_IDS` — ваш Telegram ID.
- `DISCOVERY_PATIENT_ID_ADULT` и `DISCOVERY_PATIENT_ID_CHILD` — ID пациентов для discovery.

### 6.5. Создание директорий для данных

```bash
mkdir -p data logs
```

## 7. Деплой (пошагово)

### 7.1. Сборка и запуск

```bash
# Собрать образ
docker compose build

# Запустить в фоне (detached mode)
docker compose up -d

# Проверить, что все контейнеры запущены
docker compose ps
```

Ожидаемый вывод `docker compose ps`:

```text
NAME                STATUS
lenreg_ticket_redis         Up (healthy)
lenreg_ticket_qdrant        Up
lenreg_ticket_bot           Up
```

### 7.2. Проверка логов

```bash
# Логи бота (последние 50 строк, следовать за логами)
docker compose logs -f --tail=50 bot

# Если нужны логи всех сервисов
docker compose logs -f
```

В логах должны появиться строки:

```text
INFO     | FastAPI приложение запущено на порту 8080
INFO     | Middleware initData активирован (ENVIRONMENT=production)
```

### 7.3. Перезапуск после изменений

```bash
docker compose down && docker compose up -d --build
```

## 8. Обновление на VPS

Для обновления проекта при выходе новых изменений в ветке `mini_app_beta`:

```bash
# Подключиться к VPS
ssh user@VPS_IP

# Перейти в директорию проекта
cd /path/to/lenreg-ticket-bot

# Получить последние изменения
git pull origin mini_app_beta

# Пересобрать и перезапустить
docker compose down
docker compose up -d --build

# Проверить логи
docker compose logs -f --tail=50 bot
```

Замените `user`, `VPS_IP` и `/path/to/lenreg-ticket-bot` на актуальные значения.

## 9. Регистрация Mini App в BotFather

### 9.1. Настройка Menu Button

Бот уже отправляет ReplyKeyboard с кнопкой [`KeyboardButton.web_app`](../../src/keyboards/inline.py) при команде `/start`. Дополнительно можно настроить постоянную кнопку меню через BotFather:

1. Откройте [@BotFather](https://t.me/BotFather).
2. `/mybots` → выберите вашего бота.
3. **Bot Settings** → **Menu Button**.
4. Выберите **Configure menu button**.
5. Введите URL: `https://lenregbot.acidbox.top/app/`
6. Введите название кнопки (например, «🌐 Веб-интерфейс»).

Альтернативно через команду:

```text
/setmenubutton
```

И следуйте инструкциям BotFather.

### 9.2. Важное замечание

URL Mini App **обязан** быть HTTPS. Cloudflare Proxy обеспечивает HTTPS на поддомене `lenregbot.acidbox.top`, даже если на VPS контейнер слушает HTTP на порту 8080.

## 10. Проверка работоспособности

### 10.1. Проверка через браузер

Откройте в браузере:

```text
https://lenregbot.acidbox.top/app/
```

Ожидаемый результат: загружается HTML-страница Mini App (статический [`index.html`](../../src/web/static/app/index.html)). Если страница не загружается — см. раздел [Устранение неполадок](#11-устранение-неполадок-troubleshooting).

### 10.2. Проверка API через curl

```bash
# Без initData — должен вернуть 401 (Unauthorized)
curl -i https://lenregbot.acidbox.top/api/user/profile
```

Ожидаемый ответ:

```text
HTTP/2 401
{"detail": "Missing X-Telegram-InitData header"}
```

### 10.3. Проверка в Telegram

1. Откройте бота в Telegram.
2. Нажмите кнопку **🌐 Веб-интерфейс** (в ReplyKeyboard).
3. Должно открыться Mini App с интерфейсом мониторинга врачей.

### 10.4. Проверка внутри контейнера

```bash
# Зайти в контейнер
docker exec -it lenreg_ticket_bot bash

# Проверить, что FastAPI слушает порт
curl -s http://localhost:8080/app/ | head -20

# Проверить health endpoint (если есть)
curl -s http://localhost:8080/api/health
```

## 11. Устранение неполадок (Troubleshooting)

### 11.1. ERR_CONNECTION_REFUSED (браузер)

**Причина:** Порт 8080 закрыт в файрволе VPS, или контейнер `lenreg_ticket_bot` не запущен.

**Решение:**

```bash
# Проверить, запущен ли контейнер
docker compose ps

# Проверить, слушает ли порт 8080 внутри контейнера
docker exec lenreg_ticket_bot ss -tlnp | grep 8080

# Проверить файрвол
sudo ufw status
# или
sudo iptables -L -n | grep 8080
```

### 11.2. 522 Connection timed out (Cloudflare)

**Причина:** Cloudflare не может достучаться до `VPS_IP:8080`.

**Решение:**

1. Проверьте, что контейнер запущен: `docker compose ps`.
2. Проверьте, что порт 8080 открыт в файрволе (см. раздел [4](#4-настройка-файрвола-vps)).
3. Проверьте, что в `docker-compose.yml` порт проброшен как `0.0.0.0:8080:8080` (не `127.0.0.1`).
4. Проверьте доступность напрямую (с другого хоста): `curl -v http://VPS_IP:8080/app/`.

### 11.3. 525 SSL handshake failed

**Причина:** В Cloudflare установлен режим **Full (Strict)**, который требует валидный сертификат на origin-сервере.

**Решение:** Переключите режим SSL/TLS в Cloudflare на **Full** (не Strict). См. раздел [3.2](#32-настройка-ssltls).

### 11.4. Mini App не открывается в Telegram

**Причина:** URL Mini App должен быть HTTPS.

**Решение:**

1. Проверьте, что `MINI_APP_URL` в `.env` начинается с `https://`.
2. Проверьте, что DNS-запись `bot` в Cloudflare имеет **Proxy** (оранжевое облако).
3. Проверьте, что сертификат Cloudflare активен (раздел **SSL/TLS** → **Edge Certificates**).

### 11.5. 403 Forbidden от middleware

**Причина:** `initData` невалидный или истёк.

**Решение:**

1. Проверьте `MINI_APP_INITDATA_MAX_AGE` в `.env` — значение по умолчанию 86400 (24 часа).
2. Убедитесь, что `BOT_TOKEN` в `.env` совпадает с токеном бота в BotFather.
3. Проверьте, что `ENVIRONMENT=production` (при `development` middleware принимает заголовок `bypass`, что допустимо только для локальной отладки).
4. Проверьте логи контейнера: `docker compose logs bot | grep -i "initdata\|403\|hash"`.

### 11.6. Контейнер lenreg_ticket_bot перезапускается (restart loop)

**Решение:**

```bash
# Посмотреть логи
docker compose logs --tail=100 bot

# Частые причины:
# - BOT_TOKEN не задан или невалидный
# - Redis недоступен (проверить: docker compose logs redis)
# - Ошибка в .env (опечатка в имени переменной)
```

### 11.7. Порт 8080 занят другим процессом

**Причина:** На VPS уже есть процесс, слушающий порт 8080.

**Решение:**

```bash
# Найти процесс, занимающий порт
sudo ss -tlnp | grep 8080

# Если это не нужный процесс — остановить его
sudo kill -9 <PID>

# Или изменить порт в .env (WEB_DASHBOARD_PORT=8081) и в docker-compose.yml
```

Для смены порта потребуется также обновить проброс в [`docker-compose.yml:67`](../../docker-compose.yml:67) и DNS/Cloudflare на новый порт (убедитесь, что новый порт поддерживается Cloudflare Proxy).
