#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] VERIFIKASI LENGKAP KLASTER SWARM & DATABASE"
echo "=================================================="

echo "=== 1. STATUS NODE KLASTER (docker node ls) ==="
docker node ls

echo ""
echo "=== 2. STATUS SERVICES & STACKS ==="
docker service ls
docker stack ls 2>/dev/null || true

echo ""
echo "=== 3. RESPON HTTP PORT 8080 ==="
curl -I http://localhost:8080 || true

echo ""
echo "=== 4. PENGUJIAN QUERY DATABASE DARI MANAGER ==="
if [ -f "/home/ubuntu/appKantin/config/db.php" ]; then
    DB_IP=$(grep '\$DB_HOST' /home/ubuntu/appKantin/config/db.php | cut -d'"' -f2)
    echo "Query ke MariaDB di ${DB_IP}:"
    docker run --rm mariadb:11.8 mariadb -h "${DB_IP}" -uroot -prahasia -e "USE kantin_db; SHOW TABLES; SELECT id, name, category, price FROM menu LIMIT 5;" || true
fi

echo "=================================================="
echo "VERIFIKASI SELESAI"
echo "=================================================="
