#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] LANGKAH 8, 9, 10: UJI SKALABILITAS, ROLLING UPDATE, & KETAHANAN"
echo "=================================================="

# 1. Langkah 8: Scale Up ke 6 Replika
echo "=== [1/4] LANGKAH 8: SCALE UP KE 6 REPLIKA ==="
docker service scale web=6
sleep 5
docker service ps web

echo ""
echo "Mengembalikan ke 3 replika..."
docker service scale web=3
sleep 3
docker service ps web

# 2. Langkah 9: Rolling Update
echo ""
echo "=== [2/4] LANGKAH 9: ROLLING UPDATE (PARALLELISM 1, DELAY 10s) ==="
docker service update --force --update-parallelism 1 --update-delay 10s web
echo "Status Rolling Update Selesai:"
docker service ps web

# 3. Langkah 10a: Container Mati (Simulasi Crash & Auto-Healing)
echo ""
echo "=== [3/4] LANGKAH 10a: SIMULASI CONTAINER CRASH ==="
TARGET_CID=$(docker ps --filter "name=web" --format "{{.ID}}" | head -1 || echo "")
if [ -n "$TARGET_CID" ]; then
    echo "Menghapus paksa container ${TARGET_CID}..."
    docker rm -f "${TARGET_CID}"
    sleep 3
    echo "Pemeriksaan Swarm Self-Healing (Replika baru dibuat otomatis):"
    docker service ps web
else
    echo "[INFO] Container lokal tidak ditemukan di node ini (mungkin berjalan di worker lain)."
fi

# 4. Langkah 10b: Drain Node worker2
echo ""
echo "=== [4/4] LANGKAH 10b: DRAIN NODE WORKER2 & REBALANCE ==="
if docker node ls | grep -q "worker2"; then
    echo "Mengubah status worker2 menjadi DRAIN..."
    docker node update --availability drain worker2
    sleep 3
    echo "Task dipindahkan dari worker2:"
    docker service ps web

    echo ""
    echo "Mengembalikan ketersediaan worker2 menjadi ACTIVE..."
    docker node update --availability active worker2
    sleep 2

    echo "Melakukan rebalance ulang task ke seluruh node..."
    docker service update --force web
    sleep 4
    docker service ps web
else
    echo "[INFO] Node worker2 belum terdaftar di klaster."
fi

echo "=================================================="
echo "UJI KETAHANAN KLASTER SELESAI"
echo "=================================================="
