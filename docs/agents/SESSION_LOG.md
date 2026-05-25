# Лог текущей сессии

## 2026-05-25 — Деплой конфигурации Mini App

### Выполненные задачи

1. **Подготовка конфигурации деплоя для VPS через Cloudflare Proxy**
   - Изменён [`docker-compose.yml`](../../docker-compose.yml) — порт `0.0.0.0:8080:8080` (было `127.0.0.1:8090:8090`)
   - Изменён [`Dockerfile`](../../Dockerfile) — добавлен `EXPOSE 8080`
   - Изменён [`src/config.py`](../../src/config.py) — `WEB_DASHBOARD_PORT` по умолчанию 8080
   - Обновлён [`.env`](../../.env) — `WEB_DASHBOARD_PORT=8080`, `MINI_APP_URL=https://lenregbot.acidbox.top/app/`
   - Обновлён [`.env.example`](../../.env.example) — плейсхолдер для `MINI_APP_URL`, комментарий о портах Cloudflare

2. **Создана инструкция по деплою**
   - Создан [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md) — пошаговая инструкция (8 разделов):
     - Предварительные требования
     - Настройка Cloudflare (A-запись, Proxy, SSL/TLS → Full)
     - Настройка файрвола VPS (ufw/iptables, ограничение по IP Cloudflare)
     - Конфигурация проекта (.env)
     - Деплой (git checkout → docker-compose up)
     - Регистрация в BotFather
     - Проверка работоспособности
     - Troubleshooting (6 типовых проблем)

3. **Замена домена `bot.acidbox.top` → `lenregbot.acidbox.top`**
   - Заменены все 10 вхождений в 3 файлах: [`.env`](../../.env), [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md), [`docs/agents/SESSION_LOG.md`](SESSION_LOG.md)

4. **Создан [`env.vps`](../../env.vps) — готовый .env для VPS**
   - Все реальные значения из `.env`, `PROXY_URL` пустой (на VPS в Германии прокси не нужен)
   - `ENVIRONMENT=production`, `WEB_DASHBOARD_PORT=8080`, `MINI_APP_URL=https://lenregbot.acidbox.top/app/`
   - Файл добавлен в [`.gitignore`](../../.gitignore)

5. **Создан установочный скрипт [`scripts/install.sh`](../../scripts/install.sh)**
   - Интерактивная установка на VPS одной командой
   - Проверка зависимостей (Docker, Docker Compose v2, git)
   - Клонирование репозитория, интерактивный опрос параметров
   - Автогенерация `.env`, сборка и запуск Docker-контейнеров
   - Обновлена инструкция [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md) — добавлен раздел «Быстрая установка»

### Изменённые файлы

| Файл                                                             | Тип изменения                       |
| ---------------------------------------------------------------- | ----------------------------------- |
| [`docker-compose.yml`](../../docker-compose.yml)                 | Изменён порт на 8080                |
| [`Dockerfile`](../../Dockerfile)                                 | Добавлен EXPOSE 8080                |
| [`src/config.py`](../../src/config.py)                           | WEB_DASHBOARD_PORT=8080             |
| [`.env`](../../.env)                                             | Порт и MINI_APP_URL                 |
| [`.env.example`](../../.env.example)                             | Плейсхолдер и комментарий           |
| [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md) | Создан                              |
| [`.env`](../../.env)                                             | Домен `lenregbot.acidbox.top`       |
| [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md) | Домен `lenregbot.acidbox.top`       |
| [`env.vps`](../../env.vps)                                       | Создан                              |
| [`.gitignore`](../../.gitignore)                                 | Добавлен `env.vps`                  |
| [`scripts/install.sh`](../../scripts/install.sh)                 | Создан                              |
| [`docs/design/mini_app_deploy.md`](../design/mini_app_deploy.md) | Добавлен раздел «Быстрая установка» |

### Тесты

Тесты не запускались (изменения только в конфигурации и документации).
