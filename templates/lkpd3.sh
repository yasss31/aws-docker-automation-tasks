#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=3
echo "=== MEMULAI EKSEKUSI LKPD 3: MEMBANGUN IMAGE DENGAN DOCKERFILE ==="

if ! docker network inspect mynet &>/dev/null; then
    docker network create mynet
fi

# Database MariaDB jika belum berjalan
if ! docker ps -a --format '{{.Names}}' | grep -Eq "^dbserver$"; then
    retry_cmd 3 5 docker run -d \
      --name dbserver \
      --network mynet \
      -e MYSQL_ROOT_PASSWORD=pass123 \
      --restart unless-stopped \
      mariadb:11-jammy
fi

mkdir -p /var/mywww
echo "<h1>Aplikasi Berjalan dari Image Dockerfile - LKPD 3</h1>" > /var/mywww/index.html

# Tulis Dockerfile
update_status ${LKPD_NUM} "in_progress" "write_dockerfile" "Menulis Dockerfile di ~/bws"
mkdir -p /root/bws
cat <<'EOF' > /root/bws/Dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    nano \
    apache2 \
    php \
    php-mysqli \
    php-mysql \
    libapache2-mod-php \
    default-mysql-client \
    curl \
    && apt clean && rm -rf /var/lib/apt/lists/*

EXPOSE 80

CMD ["apache2ctl", "-D", "FOREGROUND"]
EOF

# Build Image
update_status ${LKPD_NUM} "in_progress" "docker_build" "Membangun image ubuntu-ws:v1 dari Dockerfile"
retry_cmd 3 5 docker build -t ubuntu-ws:v1 /root/bws/ || {
    update_status ${LKPD_NUM} "failed" "build_failed" "Gagal docker build image ubuntu-ws:v1"
    exit 1
}

# Jalankan container webserver1 (Idempotent cleanup)
update_status ${LKPD_NUM} "in_progress" "container_run" "Menjalankan container webserver1 di port 8001"
docker rm -f webserver1 2>/dev/null || true

retry_cmd 3 3 docker run -d \
  --name webserver1 \
  --network mynet \
  -p 8001:80 \
  -v /var/mywww:/var/www/html \
  --restart unless-stopped \
  ubuntu-ws:v1 || {
    update_status ${LKPD_NUM} "failed" "run_failed" "Gagal menjalankan container webserver1"
    exit 1
}

# Validasi Jaringan: Resolusi DNS hostname dbserver dari dalam webserver1
echo "Validasi resolusi DNS antar-kontainer (webserver1 -> dbserver)..."
retry_cmd 5 2 docker exec webserver1 getent hosts dbserver || {
    update_status ${LKPD_NUM} "failed" "dns_resolution_failed" "webserver1 tidak dapat menemukan hostname dbserver di network mynet"
    exit 1
}

# Validasi HTTP Response Port 8001
if check_http_status "http://localhost:8001" "200|302" 12 2; then
    update_status ${LKPD_NUM} "success" "verified" "Image Dockerfile ubuntu-ws:v1 berhasil dibuild dan aktif di port 8001"
else
    docker logs webserver1 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "verification_failed" "webserver1 gagal merespon 200/302 di port 8001"
    exit 1
fi
