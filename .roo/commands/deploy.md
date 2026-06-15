---
description: "Безопасный деплой: линтинг + тесты → деплой на VPS → проверка"
---

Ты должен выполнить безопасный деплой проекта на VPS в три этапа.

**Этап 1 — Проверки локально:**

- Запусти lint (ruff check --fix + ruff format + mypy) и тесты (pytest tests/) параллельно, делегировав их в code и debug режимы соответственно.
- Если любой из этапов упадёт — остановись, сообщи об ошибках, деплой не выполняй.

**Этап 2 — Деплой на VPS:**

- Только если Этап 1 прошёл успешно.
- Подключись по SSH: `ssh -i C:/Users/acidgrip/.ssh/vps_zdrav_nopass -p 2244 root@195.58.39.52`
- Выполни: `cd /srv/bots/lenreg-ticket-bot && git pull origin mini_app_beta && docker compose up -d --build bot`

**Этап 3 — Проверка:**

- Выполни: `docker compose -f /srv/bots/lenreg-ticket-bot/docker-compose.yml logs bot --tail=30`
- Убедись что бот запустился без ошибок.
- Сообщи результат пользователю.

Важно: Этап 2 выполняется только при успешном Этапе 1. Используй `execute_command` для SSH-команд.
