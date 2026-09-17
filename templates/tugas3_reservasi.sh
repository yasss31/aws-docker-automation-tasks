#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

TASK_NAME="tugas3"
echo "=== MEMULAI EKSEKUSI TUGAS 3: DEPLOY APLIKASI RESERVASI RUANGAN (HAPROXY + 2 WEBSERVERS + MARIADB) ==="
update_status "${TASK_NAME}" "in_progress" "init" "Memulai inisialisasi Tugas 3 Reservasi Ruangan (HAProxy Load Balancer)"

USER_HOME="/home/ubuntu"
if [ ! -d "${USER_HOME}" ]; then
    USER_HOME="/root"
fi
APP_DIR="${USER_HOME}/appReservasi"
REPO_URL="https://github.com/paknux/appReservasi.git"

# 1. Menyiapkan direktori kerja & clone repositori
update_status "${TASK_NAME}" "in_progress" "git_clone" "Meng-clone repository appReservasi dari ${REPO_URL}"
if [ ! -d "${APP_DIR}/.git" ]; then
    rm -rf "${APP_DIR}"
    retry_cmd 3 5 git clone "${REPO_URL}" "${APP_DIR}" || {
        update_status "${TASK_NAME}" "failed" "clone_failed" "Gagal meng-clone repository ${REPO_URL}"
        exit 1
    }
fi

cd "${APP_DIR}"

# 2. Deteksi file SQL inisialisasi
SQL_FILE=$(find "${APP_DIR}" -maxdepth 1 -name "*.sql" | head -n 1)
SQL_BASENAME="reservasi_ruangan.sql"
if [ -n "${SQL_FILE}" ]; then
    SQL_BASENAME=$(basename "${SQL_FILE}")
fi
echo "[SQL DETECT] File inisialisasi database: ${SQL_BASENAME}"

# 3. Menyesuaikan konfigurasi koneksi database PHP (dbserver & root123)
update_status "${TASK_NAME}" "in_progress" "config_db" "Mengatur host database ke 'dbserver' dan password 'root123'"
CONFIG_FILE="${APP_DIR}/config/database.php"
if [ ! -f "${CONFIG_FILE}" ]; then
    update_status "${TASK_NAME}" "failed" "config_missing" "File konfigurasi ${CONFIG_FILE} tidak ditemukan"
    exit 1
fi

sed -i "s/\$DB_HOST = 'localhost';/\$DB_HOST = 'dbserver';/g" "${CONFIG_FILE}"
sed -i 's/\$DB_HOST = "localhost";/\$DB_HOST = "dbserver";/g' "${CONFIG_FILE}"
sed -i "s/\$DB_PASS = '';/\$DB_PASS = 'root123';/g" "${CONFIG_FILE}"
sed -i 's/\$DB_PASS = "";/\$DB_PASS = "root123";/g' "${CONFIG_FILE}"

echo "[CONFIG] Konfigurasi database.php:"
cat "${CONFIG_FILE}"

# 4. Membuat Dockerfile untuk webserver (Apache + PHP 8.2 + pdo_mysql)
update_status "${TASK_NAME}" "in_progress" "write_dockerfile" "Membuat Dockerfile php:8.2-apache dengan ekstensi pdo_mysql"
cat <<'EOF' > "${APP_DIR}/Dockerfile"
FROM php:8.2-apache

RUN docker-php-ext-install pdo_mysql

RUN a2enmod rewrite

WORKDIR /var/www/html

EXPOSE 80
EOF

# 5. Membuat konfigurasi HAProxy (haproxy.cfg)
update_status "${TASK_NAME}" "in_progress" "write_haproxy_cfg" "Membuat haproxy.cfg (Frontend :8080 -> Backend webserver1:80 & webserver2:80 roundrobin)"
cat <<'EOF' > "${APP_DIR}/haproxy.cfg"
global
    log stdout format raw local0

defaults
    log global
    mode http
    option httplog
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend http_front
    bind *:8080
    default_backend web_servers

backend web_servers
    balance roundrobin
    option httpchk GET /
    server webserver1 webserver1:80 check
    server webserver2 webserver2:80 check
EOF

# 6. Membuat docker-compose.yml (4 Kontainer: haproxy + webserver1 + webserver2 + dbserver)
update_status "${TASK_NAME}" "in_progress" "write_compose" "Membuat docker-compose.yml (haproxy:8083, webserver1, webserver2, dbserver)"
cat <<EOF > "${APP_DIR}/docker-compose.yml"
services:
  haproxy:
    image: haproxy:latest
    container_name: haproxy
    ports:
      - "8083:8080"
    volumes:
      - ./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    depends_on:
      - webserver1
      - webserver2
    restart: unless-stopped

  webserver1:
    build:
      context: .
      dockerfile: Dockerfile
    image: appreservasi-webserver:latest
    container_name: webserver1
    expose:
      - "80"
    volumes:
      - ./:/var/www/html
    depends_on:
      - dbserver
    restart: unless-stopped

  webserver2:
    image: appreservasi-webserver:latest
    container_name: webserver2
    expose:
      - "80"
    volumes:
      - ./:/var/www/html
    depends_on:
      - dbserver
    restart: unless-stopped

  dbserver:
    image: mariadb:11-jammy
    container_name: dbserver
    environment:
      MARIADB_ROOT_PASSWORD: root123
      MARIADB_DATABASE: db_reservasi_ruangan
    volumes:
      - db_data:/var/lib/mysql
      - ./${SQL_BASENAME}:/docker-entrypoint-initdb.d/${SQL_BASENAME}:ro
    restart: unless-stopped

volumes:
  db_data:
EOF

# Set permissions
chown -R ubuntu:ubuntu "${APP_DIR}" 2>/dev/null || true
chmod -R 775 "${APP_DIR}"

# 7. Menjalankan Docker Compose Build & Up
update_status "${TASK_NAME}" "in_progress" "compose_up" "Membangun dan menjalankan 4 container dengan docker compose up -d --build"
retry_cmd 3 5 docker pull haproxy:latest || true
docker compose down 2>/dev/null || true
retry_cmd 3 5 docker compose up -d --build || {
    update_status "${TASK_NAME}" "failed" "compose_failed" "Gagal menjalankan docker compose up -d --build"
    exit 1
}

# 8. Menunggu kesiapan MariaDB (dbserver)
update_status "${TASK_NAME}" "in_progress" "wait_db" "Menunggu database MariaDB di dbserver siap melayani koneksi"
DB_READY=false
for i in $(seq 1 40); do
    if docker exec dbserver mariadb -u root -proot123 -e "SELECT 1;" &>/dev/null; then
        echo "[DB READY] MariaDB siap pada iterasi $i"
        DB_READY=true
        break
    fi
    echo "[DB WAITING] Menunggu MariaDB (iterasi $i/40)..."
    sleep 3
done

if [ "${DB_READY}" != "true" ]; then
    update_status "${TASK_NAME}" "failed" "db_timeout" "Database MariaDB tidak kunjung siap setelah 120 detik"
    exit 1
fi

# 9. Verifikasi inisialisasi tabel di db_reservasi_ruangan
TABLE_CHECK=$(docker exec dbserver mariadb -u root -proot123 -e "USE db_reservasi_ruangan; SHOW TABLES;" 2>/dev/null || true)
echo "[DB TABLES] Tabel yang ditemukan:"
echo "${TABLE_CHECK}"

if ! echo "${TABLE_CHECK}" | grep -qE "rooms|bookings|users"; then
    echo "[DB IMPORT] Tabel belum terbuat oleh entrypoint, melakukan import manual dari ${SQL_BASENAME}..."
    docker exec -i dbserver mariadb -u root -proot123 db_reservasi_ruangan < "${APP_DIR}/${SQL_BASENAME}" || true
fi

# Restart webserver1, webserver2 & haproxy untuk memastikan koneksi segar
docker restart webserver1 webserver2 haproxy
sleep 4

# 10. Verifikasi HTTP Status Port 8083 melalui HAProxy
update_status "${TASK_NAME}" "in_progress" "http_check" "Menguji HTTP response pada port 8083 via HAProxy Load Balancer"
if ! check_http_status "http://localhost:8083" "200|302" 20 3; then
    update_status "${TASK_NAME}" "failed" "http_failed" "Aplikasi pada http://localhost:8083 tidak merespon HTTP 200/302 via HAProxy"
    docker logs haproxy --tail 30
    exit 1
fi

# 11. Finalisasi status sukses
update_status "${TASK_NAME}" "verified" "ready" "Tugas 3 Aplikasi Reservasi Ruangan (HAProxy + 2 Webservers + MariaDB) aktif di port 8083"
echo "=== DEPLOYMENT TUGAS 3 HAPROXY BERHASIL (4 KONTANER AKTIF)! ==="
