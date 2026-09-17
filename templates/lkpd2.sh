#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=2
echo "=== MEMULAI EKSEKUSI LKPD 2: MULTI-CONTAINER PHP + MARIADB ==="

# Bagian A.3 PDF: Network mynet
update_status ${LKPD_NUM} "in_progress" "network_create" "Membuat docker network mynet"
if ! docker network inspect mynet &>/dev/null; then
    docker network create mynet || {
        update_status ${LKPD_NUM} "failed" "network_failed" "Gagal membuat network mynet"
        exit 1
    }
fi

# Bagian A.4 & A.5 PDF: Persiapkan folder & clone repository
update_status ${LKPD_NUM} "in_progress" "clone_app" "Clone repository aplikasi ke /var/mywww"
mkdir -p /var/mywww
cd /var/mywww
rm -rf * .git* 2>/dev/null || true
retry_cmd 5 5 git clone ${APP_REPOSITORY:-https://github.com/paknux/apptoko.git} . || {
    update_status ${LKPD_NUM} "failed" "git_failed" "Gagal clone repository ${APP_REPOSITORY}"
    exit 1
}

# Konfigurasi config.php: sesuaikan DB_HOST, DB_USER, DB_PASS persis instruksi LKPD 2
if [ -f "/var/mywww/config.php" ]; then
    sed -i "s/define('DB_HOST', .*/define('DB_HOST', 'dbserver');/" /var/mywww/config.php
    sed -i "s/define('DB_USER', .*/define('DB_USER', 'root');/" /var/mywww/config.php
    sed -i "s/define('DB_PASS', .*/define('DB_PASS', 'pass123');/" /var/mywww/config.php
    sed -i "s/define('DB_NAME', .*/define('DB_NAME', 'toko_db');/" /var/mywww/config.php
else
    cat <<'EOF' > /var/mywww/config.php
<?php
define('DB_HOST', 'dbserver');
define('DB_USER', 'root');
define('DB_PASS', 'pass123');
define('DB_NAME', 'toko_db');
define('APP_NAME', 'Toko Sederhana');
define('UPLOAD_DIR', __DIR__ . '/uploads/');
define('UPLOAD_URL', 'uploads/');
$conn = new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);
EOF
fi

# Bagian B PDF: Jalankan Container MariaDB (Idempotent cleanup)
update_status ${LKPD_NUM} "in_progress" "mariadb_run" "Menjalankan container dbserver (mariadb:11-jammy)"
docker rm -f dbserver 2>/dev/null || true

retry_cmd 3 5 docker run -d \
  --name dbserver \
  --network mynet \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=pass123 \
  --restart unless-stopped \
  mariadb:11-jammy || {
    update_status ${LKPD_NUM} "failed" "db_run_failed" "Gagal menjalankan container dbserver"
    exit 1
}

# Tunggu MariaDB benar-benar siap menerima koneksi query
echo "Menunggu service MariaDB siap menerima query..."
DB_READY=false
for i in {1..40}; do
    if docker exec dbserver mariadb -u root -ppass123 -e "SELECT 1;" &>/dev/null; then
        DB_READY=true
        echo "MariaDB dbserver siap dan menerima koneksi!"
        break
    fi
    echo "[MariaDB Check $i/40] Menunggu database siap..."
    sleep 3
done

if [ "$DB_READY" != true ]; then
    docker logs dbserver 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "db_timeout" "Timeout menunggu MariaDB siap di dbserver"
    exit 1
fi

# Buat database toko_db
docker exec dbserver mariadb -u root -ppass123 -e "CREATE DATABASE IF NOT EXISTS toko_db;" || {
    update_status ${LKPD_NUM} "failed" "db_create_failed" "Gagal membuat database toko_db"
    exit 1
}

# Import SQL dan Verifikasi Keberadaan Tabel
if [ -s "/var/mywww/toko_db.sql" ]; then
    echo "Mengimpor skema /var/mywww/toko_db.sql ke dbserver..."
    IMPORT_SUCCESS=false
    for attempt in {1..5}; do
        if docker exec -i dbserver mariadb -u root -ppass123 toko_db < /var/mywww/toko_db.sql; then
            IMPORT_SUCCESS=true
            echo "Import skema toko_db.sql berhasil!"
            break
        fi
        echo "[Import Attempt $attempt/5] Gagal impor, mencoba kembali dalam 3 detik..."
        sleep 3
    done

    if [ "$IMPORT_SUCCESS" != true ]; then
        update_status ${LKPD_NUM} "failed" "sql_import_failed" "Gagal mengimpor file toko_db.sql ke MariaDB"
        exit 1
    fi

    # Verifikasi isi tabel database
    echo "Memverifikasi tabel di dalam database toko_db..."
    TABLE_COUNT=$(docker exec dbserver mariadb -u root -ppass123 -N -s -e "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'toko_db';")
    echo "Ditemukan $TABLE_COUNT tabel di toko_db."
    if [ "$TABLE_COUNT" -le 0 ]; then
        update_status ${LKPD_NUM} "failed" "tables_empty" "Import SQL selesai tetapi tabel di database toko_db kosong"
        exit 1
    fi
fi

# Bagian C PDF: Buat Image Ubuntu dengan Apache + PHP via Docker Commit
update_status ${LKPD_NUM} "in_progress" "build_commit_image" "Membangun image kustom ubuntu:v1 via docker commit"
docker rm -f ubuntu 2>/dev/null || true
docker run -d --name ubuntu ubuntu:24.04 tail -f /dev/null

# Install paket (default-mysql-client menjamin executable mysql/mariadb tersedia di Ubuntu 24.04)
docker exec ubuntu bash -c "apt update && DEBIAN_FRONTEND=noninteractive apt install -y nano apache2 php php-mysqli php-mysql libapache2-mod-php default-mysql-client curl" || {
    update_status ${LKPD_NUM} "failed" "commit_install_failed" "Gagal install paket di container ubuntu builder"
    docker rm -f ubuntu 2>/dev/null || true
    exit 1
}

docker exec ubuntu apache2ctl start
docker exec ubuntu apache2ctl stop
docker commit ubuntu ubuntu:v1
docker rm -f ubuntu 2>/dev/null || true

# Pengujian Ketat Image ubuntu:v1 pada port 81 (Wajib lolos sebelum commit ke v2)
update_status ${LKPD_NUM} "in_progress" "test_v1_port_81" "Menguji image ubuntu:v1 pada port 81"
docker rm -f ubuntuv1 2>/dev/null || true
docker run -d --name ubuntuv1 -p 81:80 ubuntu:v1 apache2ctl -D FOREGROUND

if ! check_http_status "http://localhost:81" "200" 12 2; then
    echo "ERROR: Image ubuntu:v1 gagal merespon 200 OK di port 81!"
    docker logs ubuntuv1 2>/dev/null || true
    docker rm -f ubuntuv1 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "v1_test_failed" "Image ubuntu:v1 gagal validasi HTTP 200 di port 81"
    exit 1
fi

echo "Uji coba port 81 berhasil! Melakukan commit ke image final ubuntu:v2..."
docker commit ubuntuv1 ubuntu:v2
docker rm -f ubuntuv1 2>/dev/null || true

# Bagian D PDF: Jalankan Container Web Server Final di port 8088
update_status ${LKPD_NUM} "in_progress" "webserver_run" "Menjalankan container webserver di port 8088"
docker rm -f webserver 2>/dev/null || true

retry_cmd 3 5 docker run -d \
  --name webserver \
  --network mynet \
  -p 8088:80 \
  -v /var/mywww:/var/www/html \
  --restart unless-stopped \
  ubuntu:v2 \
  apache2ctl -D FOREGROUND || {
    update_status ${LKPD_NUM} "failed" "webserver_run_failed" "Gagal docker run container webserver"
    exit 1
}

# Bagian E PDF: Deteksi & Eksekusi Client Database Terstruktur
echo "Memeriksa client database di container webserver..."
DB_CLIENT=""
if docker exec webserver which mysql >/dev/null 2>&1; then
    DB_CLIENT="mysql"
elif docker exec webserver which mariadb >/dev/null 2>&1; then
    DB_CLIENT="mariadb"
else
    update_status ${LKPD_NUM} "failed" "client_missing" "Executable mysql/mariadb client tidak ditemukan di webserver"
    exit 1
fi

echo "Menguji koneksi database antarkontainer menggunakan $DB_CLIENT..."
retry_cmd 5 3 docker exec webserver "$DB_CLIENT" -h dbserver -u root -ppass123 -e "SHOW DATABASES;" || {
    update_status ${LKPD_NUM} "failed" "db_connection_failed" "Webserver gagal melakukan query ke dbserver"
    exit 1
}

# Validasi HTTP Web Application Port 8088
if check_http_status "http://localhost:8088" "200|302" 15 3; then
    update_status ${LKPD_NUM} "success" "verified" "Multi-container PHP + MariaDB running & terhubung di port 8088"
else
    docker logs webserver 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "app_http_failed" "Aplikasi toko gagal merespon 200/302 di port 8088"
    exit 1
fi
