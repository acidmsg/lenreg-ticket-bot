# VPS — параметры подключения

> **Чувствительные данные:** Все реальные значения вынесены в [`.env`](.env).
> Формат переменных см. в [`.env.example`](.env.example).

## SSH

| Параметр     | Значение                        |
| ------------ | ------------------------------- |
| Хост         | см. `.env` → `VPS_SSH_HOST`     |
| Порт         | см. `.env` → `VPS_SSH_PORT`     |
| Пользователь | см. `.env` → `VPS_SSH_USER`     |
| Ключ         | см. `.env` → `VPS_SSH_KEY_PATH` |

## Команда подключения

```powershell
ssh -i $env:VPS_SSH_KEY_PATH -p $env:VPS_SSH_PORT $env:VPS_SSH_USER@$env:VPS_SSH_HOST
```

## Проект на VPS

| Параметр           | Значение                               |
| ------------------ | -------------------------------------- |
| Директория проекта | см. `.env` → `VPS_PROJECT_DIR`         |
| Ветка              | см. `.env` → `VPS_BRANCH`              |
| Docker Compose     | см. `.env` → `VPS_DOCKER_COMPOSE_FILE` |

## Полезные команды

> Переменные `$VPS_PROJECT_DIR`, `$VPS_BRANCH`, `$VPS_DOCKER_COMPOSE_FILE` —
> из [`.env`](.env). Перед выполнением загрузи их в окружение:
>
> ```powershell
> Get-Content .roo/rules/.env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
> ```

```bash
# Логи бота
docker compose -f $VPS_DOCKER_COMPOSE_FILE logs bot --tail=50

# Статус контейнеров
docker compose -f $VPS_DOCKER_COMPOSE_FILE ps

# Перезапуск бота
docker compose -f $VPS_DOCKER_COMPOSE_FILE restart bot

# Деплой
cd $VPS_PROJECT_DIR && git pull origin $VPS_BRANCH && docker compose up -d --build bot

# Проверить БД
sqlite3 $VPS_PROJECT_DIR/data/bot.db ".tables"
```
