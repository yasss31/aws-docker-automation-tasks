#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=8
echo "=== MEMULAI BOOTSTRAP LKPD 8: DATABASE NODE (MARIADB 11.8) ==="

update_status ${LKPD_NUM} "in_progress" "node_init" "Mengatur hostname db dan menginstal Docker"

# 1. Atur Hostname
hostnamectl set-hostname db
echo "Hostname diatur: db"

# 2. Pastikan Docker terpasang dan service aktif
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker ubuntu || true
systemctl enable --now docker

# 3. Jalankan container MariaDB 11.8 (Tugas 1)
update_status ${LKPD_NUM} "in_progress" "mariadb_run" "Menjalankan container MariaDB 11.8 pada port 3306"
docker rm -f db 2>/dev/null || true
docker run -d \
  --name db \
  --restart unless-stopped \
  -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=rahasia \
  -v dbdata:/var/lib/mysql \
  mariadb:11.8

# 4. Simpan status
update_status ${LKPD_NUM} "ready" "db_ready" "Database MariaDB 11.8 siap menerima koneksi port 3306"
echo "=== BOOTSTRAP DATABASE NODE SELESAI ==="
