#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 6] LANGKAH 3: MEMBUAT SERVICE WEB (3 REPLIKAS)"
echo "=================================================="

# 1. Pastikan dijalankan pada Manager Node
IS_MANAGER=$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo "false")
if [ "$IS_MANAGER" != "true" ]; then
    echo "ERROR: Perintah ini hanya bisa dijalankan pada Docker Swarm Manager Node!"
    exit 1
fi

# 2. Hapus service web lama jika ada agar idempotent
if docker service inspect web &>/dev/null; then
    echo "Membersihkan service web yang sudah ada sebelumnya..."
    docker service rm web
    sleep 3
fi

# 3. Buat service sesuai instruksi LKPD:
# docker service create --name web --replicas 3 -p 8080:80 nginx
echo "Mengeksekusi pembuatan service:"
echo "$ docker service create --name web --replicas 3 -p 8080:80 nginx"
docker service create --name web --replicas 3 -p 8080:80 nginx

echo ""
echo "Menunggu seluruh 3 task/replika berstatus 'Running'..."
for i in {1..30}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    echo "[Check $i/30] Replika Running: $RUNNING_COUNT / 3"
    if [ "$RUNNING_COUNT" -ge 3 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "STATUS SERVICE (docker service ls):"
echo "=================================================="
docker service ls

echo ""
echo "=================================================="
echo "DISTRIBUSI TASK PADA NODE (docker service ps web):"
echo "=================================================="
docker service ps web

echo ""
echo "Menguji akses HTTP pada port 8080..."
if curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200"; then
    echo "[SUCCESS] Layanan Nginx merespon HTTP 200 OK di port 8080!"
else
    echo "[INFO] Menunggu respon web server di port 8080..."
fi
