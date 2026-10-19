#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] TUGAS 6 (TANTANGAN): DEPLOY KANTIN MENGGUNAKAN DOCKER STACK"
echo "=================================================="

KANTIN_DIR="/home/ubuntu/appKantin"
STACK_FILE="/home/ubuntu/kantin-stack.yml"

# 1. Hapus service mandiri sebelumnya jika ada
echo "Menghapus service kantin sebelumnya (jika ada)..."
docker service rm kantin 2>/dev/null || true
sleep 3

# 2. Buat file kantin-stack.yml di manager
echo "Membuat file manifest stack di ${STACK_FILE}..."
cat << 'EOF' > "${STACK_FILE}"
services:
  web:
    image: trafex/php-nginx
    ports:
      - "8080:8080"
    volumes:
      - /home/ubuntu/appKantin:/var/www/html
    deploy:
      replicas: 3
EOF

# 3. Deploy stack
echo "Men-deploy Docker Stack kantin..."
docker stack deploy -c "${STACK_FILE}" kantin

sleep 5

echo ""
echo "=================================================="
echo "STATUS STACK SERVICES:"
echo "=================================================="
docker stack services kantin

echo ""
echo "=================================================="
echo "STATUS TASK / REPLIKA DALAM STACK:"
echo "=================================================="
docker stack ps kantin
echo "=================================================="
