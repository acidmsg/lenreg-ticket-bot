# Деплой на VPS

## Источник кода

Код для деплоя берётся **только из публичного репо**:
`https://github.com/acidmsg/lenreg-ticket-bot.git` (ветка `main`)

## Параметры подключения

См. [`.roo/rules/vps.md`](.roo/rules/vps.md) и [`.roo/rules/.env`](.roo/rules/.env).

```powershell
ssh -i C:/Users/acidgrip/.ssh/vps_lenreg_ticket_nopass -p 2244 root@195.58.39.52
```

Проект на VPS: `/srv/bots/lenreg-ticket-bot`

## Процедура деплоя

### 1. Остановка

```bash
cd /srv/bots/lenreg-ticket-bot
docker compose down
```

### 2. Бэкап .env и данных

```bash
cp .env /tmp/lenreg-env-backup
cp -r data /tmp/lenreg-data-backup 2>/dev/null || true
```

### 3. Очистка старых файлов

```bash
find . -mindepth 1 -maxdepth 1 ! -name '.env' ! -name 'data' -exec rm -rf {} \;
```

### 4. Клонирование публичного репо

```bash
git clone https://github.com/acidmsg/lenreg-ticket-bot.git /tmp/lenreg-fresh
cp -r /tmp/lenreg-fresh/* /srv/bots/lenreg-ticket-bot/
cp -r /tmp/lenreg-fresh/.[!.]* /srv/bots/lenreg-ticket-bot/ 2>/dev/null || true
rm -rf /tmp/lenreg-fresh
```

### 5. Восстановление .env и данных

```bash
cp /tmp/lenreg-env-backup .env
cp -r /tmp/lenreg-data-backup/* data/ 2>/dev/null || true
```

### 6. Права

```bash
chown -R 1000:1000 data/ logs/ 2>/dev/null || chmod -R 777 data/ logs/
```

### 7. Сборка и запуск

```bash
docker compose up -d --build
```

### 8. Проверка

```bash
sleep 5
docker compose ps
docker compose logs --tail=20
```

## Что попадает на VPS

**Только** файлы из публичного репо:

- `src/` — исходный код
- `locales/` — файлы локализации
- `Dockerfile`, `docker-compose.yml` — инфраструктура
- `README.md`, `pyproject.toml`, `poetry.lock`, `.env.example` — метаданные
- `.dockerignore`, `.gitattributes` — конфиги сборки

**Плюс** сохраняемые с предыдущего деплоя:

- `.env` — конфиденциальные настройки
- `data/` — база данных (SQLite)

## Что НЕ попадает на VPS

Никакие dev-файлы: `.roo/`, `.agents/`, `specs/`, `tests/`, `scripts/`, `_design_lab/`, `plans/`, `artifacts/`, CI/CD, конфиги линтеров.
