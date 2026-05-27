# VPS — параметры подключения

## SSH

| Параметр     | Значение                                |
| ------------ | --------------------------------------- |
| Хост         | 195.58.39.52                            |
| Порт         | 2244                                    |
| Пользователь | root                                    |
| Ключ         | C:/Users/acidgrip/.ssh/vps_zdrav_nopass |

## Команда подключения

```powershell
ssh -i C:/Users/acidgrip/.ssh/vps_zdrav_nopass -p 2244 root@195.58.39.52
```

## Проект на VPS

| Параметр           | Значение                              |
| ------------------ | ------------------------------------- |
| Директория проекта | /root/zdrav.lenreg                    |
| Ветка              | mini_app_beta                         |
| Docker Compose     | /root/zdrav.lenreg/docker-compose.yml |

## Полезные команды

```bash
# Логи бота
docker compose -f /root/zdrav.lenreg/docker-compose.yml logs bot --tail=50

# Статус контейнеров
docker compose -f /root/zdrav.lenreg/docker-compose.yml ps

# Перезапуск бота
docker compose -f /root/zdrav.lenreg/docker-compose.yml restart bot

# Деплой
cd /root/zdrav.lenreg && git pull origin mini_app_beta && docker compose up -d --build bot

# Проверить БД
sqlite3 /root/zdrav.lenreg/data/bot.db ".tables"
```
