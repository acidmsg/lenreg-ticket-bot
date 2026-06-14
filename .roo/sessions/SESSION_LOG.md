# SESSION LOG

## 2026-06-14 — Проектирование и реализация механизма резервного копирования БД

**Режим:** architect (фаза 0 — проектирование), code (фазы 1-4 — реализация, линтинг, финализация)
**Задача:** Спроектировать и реализовать трёхуровневый механизм автоматического резервного копирования базы данных с удалённым хранением, верификацией, REST API и веб-интерфейсом управления.

### Фаза 0 — Проектирование (architect)

- Спроектирован трёхуровневый ротационный механизм бэкапа: daily (7 копий), weekly (4 копии), monthly (12 копий)
- Определён инструментарий: `sqlite3 .backup` для атомарного копирования БД без блокировок
- Спроектирована удалённая репликация через SCP на защищённый хост (`backup.lenreg.ru`)
- Разработана cron-автоматизация: ежедневный запуск в 03:00 MSK с ротацией
- Спроектирована верификация целостности: `PRAGMA integrity_check` после каждого бэкапа
- Спроектирована система алертов: NTFY (критические сбои) + Sentry (ошибки верификации)
- Определены требования к ssh-ключам и конфигурации удалённого хоста
- Зафиксированы критерии приёмки (10 пунктов)
- Дополнение дизайна: гибридное управление бэкапами (shell + веб-дашборд) — 4 REST API эндпоинта, двухфакторное подтверждение restore, UI-компоненты

**Изменённые файлы (фаза 0):**

- [`specs/design/database_backup_design.md`](../../specs/design/database_backup_design.md) — создан, затем дополнен разделом «12. Гибридное управление (Shell + Веб-дашборд)»

### Фаза 1 — Shell-скрипты и конфигурация (code)

- Переписан [`scripts/backup.sh`](scripts/backup.sh): трёхуровневая ротация, SCP-репликация, integrity check, NTFY/Sentry алерты
- Создан [`scripts/restore.sh`](scripts/restore.sh): интерактивное восстановление с выбором бэкапа, .broken-сохранение, integrity check
- Создан [`scripts/backup_healthcheck.sh`](scripts/backup_healthcheck.sh): проверка доступности директорий, ssh-хоста, дискового пространства, целостности бэкапов
- Добавлены 6 backup-полей в [`src/config.py`](src/config.py): `BACKUP_DIR`, `BACKUP_RETENTION_DAILY`, `BACKUP_RETENTION_WEEKLY`, `BACKUP_RETENTION_MONTHLY`, `BACKUP_REMOTE_HOST`, `BACKUP_REMOTE_PATH`
- Добавлены ключи в `.env` и `.env.example`: `BACKUP_DIR`, `BACKUP_RETENTION_*`, `BACKUP_REMOTE_HOST`, `BACKUP_REMOTE_PATH`

**Изменённые файлы (фаза 1):**

- [`scripts/backup.sh`](scripts/backup.sh) — переписан
- [`scripts/restore.sh`](scripts/restore.sh) — создан
- [`scripts/backup_healthcheck.sh`](scripts/backup_healthcheck.sh) — создан
- [`src/config.py`](src/config.py) — добавлены 6 полей в класс `Settings`
- `.env` — добавлены backup-ключи
- `.env.example` — добавлены backup-ключи

### Фаза 2 — Python REST API (code)

- Создан [`src/web/routers/backup_api.py`](src/web/routers/backup_api.py): 4 эндпоинта:
  - `GET /api/backups` — список бэкапов с пагинацией
  - `GET /api/backups/status` — статус (последний бэкап, свободное место, количество)
  - `POST /api/backups/create` — запуск ручного бэкапа
  - `POST /api/backups/restore` — восстановление из бэкапа с двухфакторным подтверждением
- Зарегистрирован роутер `backup_api` в [`src/web/app.py`](src/web/app.py)
- Добавлен route `/backups` в [`src/web/routers/pages.py`](src/web/routers/pages.py)

**Изменённые файлы (фаза 2):**

- [`src/web/routers/backup_api.py`](src/web/routers/backup_api.py) — создан
- [`src/web/app.py`](src/web/app.py) — регистрация роутера `backup_api`
- [`src/web/routers/pages.py`](src/web/routers/pages.py) — добавлен route `/backups`

### Фаза 3 — Фронтенд и Docker (code)

- Создан шаблон [`src/web/templates/backups.html`](src/web/templates/backups.html): таблица бэкапов, модальные окна восстановления, панель статуса, пагинация
- Создан JS-модуль [`src/web/static/app/js/views/backups.js`](src/web/static/app/js/views/backups.js): загрузка списка, статуса, обработка кнопок «Создать бэкап» / «Восстановить», двухфакторное подтверждение
- Дополнен CSS [`src/web/static/app/css/style.css`](src/web/static/app/css/style.css): стили для `.backup-status-panel`, `.backup-table`, `.backup-modal`, `.confirm-code-input`
- Обновлён [`docker-compose.yml`](docker-compose.yml): добавлен `user: 1000:1000` для контейнера, bind-mount `./scripts:/app/scripts:ro`

**Изменённые файлы (фаза 3):**

- [`src/web/templates/backups.html`](src/web/templates/backups.html) — создан
- [`src/web/static/app/js/views/backups.js`](src/web/static/app/js/views/backups.js) — создан
- [`src/web/static/app/css/style.css`](src/web/static/app/css/style.css) — дополнен стилями бэкапов
- [`docker-compose.yml`](docker-compose.yml) — добавлен `user` и bind-mount `scripts`

### Фаза 4 — Линтинг, тесты, финализация (code)

- **Ruff:** `src/web/routers/backup_api.py`, `src/web/app.py`, `src/web/routers/pages.py`, `src/config.py` — 0 errors
- **Bash syntax check:** `scripts/backup.sh`, `scripts/restore.sh`, `scripts/backup_healthcheck.sh` — 0 errors
- **Prettier:** `backups.html`, `backups.js`, `style.css`, `docker-compose.yml` — отформатированы
- **Markdownlint:** [`specs/design/database_backup_design.md`](../../specs/design/database_backup_design.md) — 0 errors (исправлено 2 ошибки MD040: добавлен `text` язык для ASCII-диаграмм)

### Результаты проверок

| Инструмент   | Файлы                                                           | Результат |
| ------------ | --------------------------------------------------------------- | --------- |
| Ruff         | `backup_api.py`, `app.py`, `pages.py`, `config.py`              | 0 errors  |
| Bash -n      | `backup.sh`, `restore.sh`, `backup_healthcheck.sh`              | 0 errors  |
| Prettier     | `backups.html`, `backups.js`, `style.css`, `docker-compose.yml` | OK        |
| Markdownlint | `database_backup_design.md`                                     | 0 errors  |
