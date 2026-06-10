"""Диагностический скрипт для запуска внутри контейнера."""

import os
import socket

# 1. Информация о процессе
print("=== PID 1 ===")
try:
    with open("/proc/1/comm") as f:
        print(f"comm: {f.read().strip()}")
    with open("/proc/1/wchan") as f:
        print(f"wchan: {f.read().strip()}")
except Exception as e:
    print(f"Ошибка чтения: {e}")

# 2. Потоки
print("\n=== Потоки ===")
for tid in sorted(int(t) for t in os.listdir("/proc/1/task/")):
    try:
        with open(f"/proc/1/task/{tid}/comm") as f:
            comm = f.read().strip()
        with open(f"/proc/1/task/{tid}/wchan") as f:
            wchan = f.read().strip()
        print(f"TID {tid}: comm={comm}, wchan={wchan}")
    except Exception as e:
        print(f"TID {tid}: error={e}")

# 3. Сетевые тесты
print("\n=== Сеть ===")
targets = [
    ("api.telegram.org", 443),
    ("google.com", 443),
    ("8.8.8.8", 53),
]
for host, port in targets:
    # DNS
    try:
        ai = socket.getaddrinfo(host, port)
        dns = f"DNS OK: {ai[0][4]}"
    except Exception as e:
        dns = f"DNS FAIL: {e}"
    # TCP
    try:
        s = socket.create_connection((host, port), timeout=5)
        tcp = f"TCP OK: {s.getpeername()}"
        s.close()
    except Exception as e:
        tcp = f"TCP FAIL: {e}"
    print(f"{host}:{port} → {dns} | {tcp}")

# 4. Проверка открытых портов внутри контейнера
print("\n=== Открытые порты ===")
for port in [8080, 9090]:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        print(f"Порт {port}: ОТКРЫТ ({s.getpeername()})")
        s.close()
    except Exception as e:
        print(f"Порт {port}: ЗАКРЫТ ({type(e).__name__})")

print("\n=== ГОТОВО ===")
