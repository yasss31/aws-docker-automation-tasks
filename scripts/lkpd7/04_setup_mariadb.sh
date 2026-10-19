#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] TUGAS 1: DEPLOYMENT MARIADB DATABASE"
echo "=================================================="

# 1. Pastikan network kantin_net tersedia
if ! docker network inspect kantin_net &>/dev/null; then
    docker network create --driver overlay --attachable kantin_net
fi

# 2. Hapus container db lama jika ada
if docker ps -a --format '{{.Names}}' | grep -q '^db$'; then
    echo "Membersihkan container MariaDB 'db' lama..."
    docker rm -f db
fi

# 3. Jalankan MariaDB sesuai instruksi Tugas LKPD 7:
# Menggunakan image mariadb:11-jammy (stabil & kompatibel)
echo "Menjalankan container MariaDB (nama: db, port 3306)..."
docker run -d \
  --name db \
  --network kantin_net \
  -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=rahasia \
  -e MARIADB_DATABASE=kantin_db \
  -v dbdata:/var/lib/mysql \
  --restart unless-stopped \
  mariadb:11-jammy

echo "Menunggu MariaDB siap menerima koneksi..."
for i in {1..20}; do
    if docker exec db mariadb-admin ping -uroot -prahasia &>/dev/null || docker exec db mysqladmin ping -uroot -prahasia &>/dev/null; then
        echo "[OK] MariaDB berhasil terhubung pada percobaan $i!"
        break
    fi
    echo "[Wait $i/20] Inisialisasi MariaDB..."
    sleep 3
done

echo ""
echo "=================================================="
echo "STATUS CONTAINER DATABASE:"
echo "=================================================="
docker ps --filter "name=db" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
echo "=================================================="
