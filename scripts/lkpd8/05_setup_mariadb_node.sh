#!/usr/bin/env bash
set -Eeuo pipefail

DB_PRIVATE_IP="${1:-}"

echo "=================================================="
echo "[LKPD 8] TUGAS 1 & 2: SETUP & TEST KONEKSI MARIADB 11.8"
echo "=================================================="

# Jika dijalankan di instance db:
if [ "$(hostname)" = "db" ] || [ -z "$DB_PRIVATE_IP" ]; then
    echo "Memeriksa status container MariaDB di instance database..."
    if ! docker ps --filter "name=db" --format "{{.Names}}" | grep -q "^db$"; then
        echo "Menjalankan container MariaDB 11.8 (Tugas 1)..."
        docker run -d \
          --name db \
          --restart unless-stopped \
          -p 3306:3306 \
          -e MARIADB_ROOT_PASSWORD=rahasia \
          -v dbdata:/var/lib/mysql \
          mariadb:11.8
    fi
    docker ps --filter "name=db"
    echo "Container MariaDB aktif di instance db."
fi

# Jika diberikan parameter IP Private DB (pengujian dari Swarm Manager):
if [ -n "$DB_PRIVATE_IP" ]; then
    echo ""
    echo "=== TUGAS 2: UJI KONEKSI DARI SWARM NODE KE DB (${DB_PRIVATE_IP}:3306) ==="
    docker run --rm mariadb:11.8 mariadb -h "${DB_PRIVATE_IP}" -uroot -prahasia -e "SELECT VERSION();"
    echo "Koneksi database sukses!"
fi

echo "=================================================="
