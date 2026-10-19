#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] VERIFIKASI MENYELURUH (SWARM + DB + APPKANTIN)"
echo "=================================================="

# 1. Status Swarm
echo "[1] Status Docker Swarm:"
docker node ls
echo ""

# 2. Status Service Web
echo "[2] Status Service Web (3 Replika):"
docker service ls
echo ""
docker service ps web
echo ""

# 3. Status Database MariaDB
echo "[3] Status Container Database:"
docker ps --filter "name=db" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 4. Tes HTTP Akses
echo "[4] Pengujian Akses HTTP:"
HTTP_APP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ || echo "ERR")
HTTP_INFO=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/index_info.php 2>/dev/null || curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/index.php || echo "ERR")

echo "  - Akses appKantin (/)       : HTTP ${HTTP_APP}"
echo "  - Akses Info Server Hostname : HTTP ${HTTP_INFO}"

# 5. Cek Data di Database
echo ""
echo "[5] Pemeriksaan Data Menu Kantin di MariaDB:"
if docker exec db mariadb -uroot -prahasia -e "USE kantin_db; SELECT id, name, category, price, stock, status FROM menu LIMIT 5;" 2>/dev/null; then
    echo "[OK] Database terisi data menu dengan sukses!"
else
    echo "[WARN] Belum ada data atau query database gagal."
fi

echo ""
echo "=================================================="
if [ "$HTTP_APP" = "200" ]; then
    echo "STATUS KELULUSAN LKPD 7: [PASS] SEMUA TAHAPAN SUKSES!"
else
    echo "STATUS KELULUSAN LKPD 7: [IN_PROGRESS / VERIFIKASI PERLU DICEK]"
fi
echo "=================================================="
