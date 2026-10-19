#!/usr/bin/env bash
set -Eeuo pipefail

DB_PRIVATE_IP="${1:-}"

if [ -z "$DB_PRIVATE_IP" ]; then
    echo "Penggunaan: $0 <IP-PRIVATE-DB>"
    exit 1
fi

echo "=================================================="
echo "[LKPD 8] TUGAS 3 & 4: DEPLOY APPKANTIN 3 REPLIKA DI SWARM"
echo "Target DB Host: ${DB_PRIVATE_IP}"
echo "=================================================="

KANTIN_DIR="/home/ubuntu/appKantin"

# 1. Clone appKantin jika belum ada
if [ ! -d "${KANTIN_DIR}/.git" ]; then
    echo "Mengunduh appKantin dari GitHub..."
    rm -rf "${KANTIN_DIR}"
    git clone https://github.com/paknux/appKantin.git "${KANTIN_DIR}"
fi

# 2. Konfigurasi config/db.php sesuai instruksi Tugas 3
echo "Mengatur konfigurasi database di ${KANTIN_DIR}/config/db.php..."
sed -i "s/\\\$DB_HOST = \"localhost\";/\\\$DB_HOST = \"${DB_PRIVATE_IP}\";/" "${KANTIN_DIR}/config/db.php"
sed -i 's/\$DB_PASS = "";/\$DB_PASS = "rahasia";/' "${KANTIN_DIR}/config/db.php"

chmod -R 777 "${KANTIN_DIR}"

# 3. Hapus service web lama jika ada (Langkah 11 / Persiapan Tugas)
echo "Membersihkan service web lama..."
docker service rm web 2>/dev/null || true
docker service rm kantin 2>/dev/null || true
sleep 3

# 4. Deploy service kantin dengan 3 replika (Tugas 4)
echo "Membuat service kantin 3 replika..."
docker service create \
  --name kantin \
  --replicas 3 \
  -p 8080:8080 \
  --mount type=bind,source="${KANTIN_DIR}",target=/var/www/html \
  trafex/php-nginx

# Tunggu service converged
echo "Menunggu replika kantin aktif..."
for i in {1..30}; do
    RUNNING_COUNT=$(docker service ps kantin --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    if [ "$RUNNING_COUNT" -ge 3 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "STATUS SERVICE KANTIN:"
echo "=================================================="
docker service ps kantin
echo "=================================================="
