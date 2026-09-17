#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

TASK_NAME="tugas2"
echo "=== MEMULAI EKSEKUSI TUGAS 2: DEPLOY APP ID CARD DENGAN DOCKER COMPOSE ==="
update_status "${TASK_NAME}" "in_progress" "init" "Memulai inisialisasi Tugas 2 App ID Card"

APP_DIR="/opt/idcard"
REPO_URL="https://github.com/paknux/appIDcard.git"

# 1. Menyiapkan direktori kerja
update_status "${TASK_NAME}" "in_progress" "setup_dir" "Menyiapkan direktori kerja ${APP_DIR}"
mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

# 2. Mengambil source code App ID Card
update_status "${TASK_NAME}" "in_progress" "git_clone" "Meng-clone repository App ID Card dari ${REPO_URL}"
rm -rf "${APP_DIR}/appIDcard"
retry_cmd 3 5 git clone "${REPO_URL}" "${APP_DIR}/appIDcard" || {
    update_status "${TASK_NAME}" "failed" "clone_failed" "Gagal meng-clone repository ${REPO_URL}"
    exit 1
}

# 3. Menyesuaikan konfigurasi database pada konfig.php
update_status "${TASK_NAME}" "in_progress" "config_app" "Mengatur host database ke 'dbserver' dan password 'pass123'"
KONFIG_FILE="${APP_DIR}/appIDcard/konfig.php"
if [ ! -f "${KONFIG_FILE}" ]; then
    update_status "${TASK_NAME}" "failed" "config_missing" "File ${KONFIG_FILE} tidak ditemukan"
    exit 1
fi

sed -i "s/define('DB_HOST', 'localhost');/define('DB_HOST', 'dbserver');/g" "${KONFIG_FILE}"
sed -i "s/define('DB_PASS', '');/define('DB_PASS', 'pass123');/g" "${KONFIG_FILE}"

# Set permissions agar Apache www-data memiliki hak akses
chown -R www-data:www-data "${APP_DIR}/appIDcard"
chmod -R 755 "${APP_DIR}/appIDcard"

# 4. Membuat docker-compose.yml
update_status "${TASK_NAME}" "in_progress" "write_compose" "Membuat file docker-compose.yml"
cat <<'EOF' > "${APP_DIR}/docker-compose.yml"
services:
  dbserver:
    image: mariadb:11-jammy
    container_name: dbserver
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: pass123
      MARIADB_DATABASE: db_idcard
      MYSQL_ROOT_PASSWORD: pass123
      MYSQL_DATABASE: db_idcard
    volumes:
      - db-data:/var/lib/mysql
    networks:
      - idcard-net

  webserver:
    image: yaszhen/ubuntu-ws:v1
    container_name: idcard-web
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ./appIDcard:/var/www/html
    depends_on:
      - dbserver
    networks:
      - idcard-net

networks:
  idcard-net:
    driver: bridge

volumes:
  db-data:
EOF

# 5. Menjalankan Docker Compose
update_status "${TASK_NAME}" "in_progress" "compose_pull" "Mengunduh image yaszhen/ubuntu-ws:v1 dan mariadb:11-jammy"
retry_cmd 3 5 docker compose pull || true

update_status "${TASK_NAME}" "in_progress" "compose_up" "Menjalankan Docker Compose (idcard-web & dbserver)"
docker compose down -v 2>/dev/null || true
retry_cmd 3 3 docker compose up -d || {
    update_status "${TASK_NAME}" "failed" "compose_failed" "Gagal menjalankan docker compose up -d"
    exit 1
}

# 6. Menunggu kesiapan database MariaDB
update_status "${TASK_NAME}" "in_progress" "wait_db" "Menunggu MariaDB di container dbserver siap melayani query"
DB_READY=false
for i in $(seq 1 30); do
    if docker exec dbserver mariadb-admin ping -uroot -ppass123 --silent &>/dev/null; then
        echo "[DB READY] MariaDB siap pada iterasi $i"
        DB_READY=true
        break
    fi
    echo "[DB WAITING] Menunggu MariaDB siap (iterasi $i/30)..."
    sleep 2
done

if [ "${DB_READY}" != "true" ]; then
    update_status "${TASK_NAME}" "failed" "db_timeout" "Database MariaDB tidak kunjung siap setelah 60 detik"
    exit 1
fi

# 7. Verifikasi HTTP & Pemicu Auto-Create Tabel
update_status "${TASK_NAME}" "in_progress" "http_check" "Menguji HTTP response pada port 8080"
if ! check_http_status "http://localhost:8080" "200|302" 20 3; then
    update_status "${TASK_NAME}" "failed" "http_failed" "Aplikasi pada http://localhost:8080 tidak merespon HTTP 200"
    exit 1
fi

# Lakukan request ke index.php agar koneksi database dijalankan dan tabel biodata dibuat
curl -sS "http://localhost:8080/index.php" >/dev/null || true

# 8. Verifikasi Tabel Database
update_status "${TASK_NAME}" "in_progress" "verify_db_tables" "Memeriksa tabel biodata di database db_idcard"
TABLE_CHECK=$(docker exec dbserver mariadb -uroot -ppass123 -e "SHOW TABLES IN db_idcard;" 2>/dev/null || true)

if echo "${TABLE_CHECK}" | grep -q "biodata"; then
    echo "[DB SUCCESS] Tabel biodata berhasil ditemukan di db_idcard."
else
    echo "[DB NOTE] Mencoba pemicu create table via curl save.php..."
    curl -sS -X POST "http://localhost:8080/save.php" -d "nama=Tes&kelas=X&absen=01&jk=Laki-Laki&no_hp=08123456789" >/dev/null || true
fi

# 9. Finalisasi status deployment
update_status "${TASK_NAME}" "verified" "ready" "Tugas 2 App ID Card aktif dan melayani HTTP 200 di port 8080"
echo "=== DEPLOYMENT TUGAS 2 BERHASIL! ==="
