#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 6] LANGKAH 4: SCALING SERVICE MENJADI 5 REPLIKAS"
echo "=================================================="

# 1. Pastikan dijalankan pada Manager Node
IS_MANAGER=$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo "false")
if [ "$IS_MANAGER" != "true" ]; then
    echo "ERROR: Perintah ini hanya bisa dijalankan pada Docker Swarm Manager Node!"
    exit 1
fi

if ! docker service inspect web &>/dev/null; then
    echo "ERROR: Service 'web' tidak ditemukan. Jalankan create_service.sh terlebih dahulu!"
    exit 1
fi

echo "--- Kondisi SEBELUM Scaling ---"
docker service ls --filter "name=web"
echo ""

# 2. Eksekusi scaling sesuai instruksi LKPD:
# docker service scale web=5
echo "Mengeksekusi scaling service:"
echo "$ docker service scale web=5"
docker service scale web=5

echo ""
echo "Menunggu seluruh 5 task/replika berstatus 'Running'..."
for i in {1..30}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    echo "[Check $i/30] Replika Running: $RUNNING_COUNT / 5"
    if [ "$RUNNING_COUNT" -ge 5 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "STATUS SERVICE SETELAH SCALING (docker service ls):"
echo "=================================================="
docker service ls

echo ""
echo "=================================================="
echo "DISTRIBUSI 5 TASK (docker service ps web):"
echo "=================================================="
docker service ps web
echo "=================================================="
echo "[PENJELASAN PENGAMATAN]"
echo "Docker Swarm menambahkan 2 task baru (web.4 dan web.5) secara otomatis"
echo "dan mendistribusikannya ke seluruh node yang tersedia agar beban terbagi merata."
echo "=================================================="
