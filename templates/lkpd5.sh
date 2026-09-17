#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=5
echo "=== MEMULAI EKSEKUSI LKPD 5: DOCKER COMPOSE ==="

mkdir -p /var/mywww
echo "<h1>Aplikasi Berjalan Menggunakan Docker Compose - LKPD 5</h1>" > /var/mywww/index.html

mkdir -p /root/compose-app
cd /root/compose-app

cat <<'EOF' > /root/compose-app/Dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y \
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

cat <<'EOF' > /root/compose-app/docker-compose.yml
version: "3.9"

services:
  dbserver:
    image: mariadb:11-jammy
    container_name: dbserver
    environment:
      MYSQL_ROOT_PASSWORD: pass123
    networks:
      - mynet
    volumes:
      - db-data:/var/lib/mysql

  webserver:
    build: .
    container_name: webserver
    ports:
      - "8088:80"
    volumes:
      - /var/mywww:/var/www/html
    depends_on:
      - dbserver
    networks:
      - mynet
    restart: unless-stopped

networks:
  mynet:

volumes:
  db-data:
EOF

update_status ${LKPD_NUM} "in_progress" "compose_validation" "Validasi file docker-compose.yml"
docker compose config || docker-compose config || {
    update_status ${LKPD_NUM} "failed" "compose_syntax_error" "Sintaks docker-compose.yml tidak valid"
    exit 1
}

# Bersihkan compose lama jika ada
docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true

update_status ${LKPD_NUM} "in_progress" "compose_up" "Mengeksekusi docker compose up -d --build"
retry_cmd 3 5 docker compose up -d --build || retry_cmd 3 5 docker-compose up -d --build || {
    update_status ${LKPD_NUM} "failed" "compose_up_failed" "Gagal docker compose up -d"
    exit 1
}

# Pemeriksaan State Terstruktur: dbserver & webserver harus berstatus 'running'
echo "Memeriksa status container compose..."
COMPOSE_OK=false
for i in {1..20}; do
    DB_STATE=$(docker inspect -f '{{.State.Status}}' dbserver 2>/dev/null || docker inspect -f '{{.State.Status}}' compose-app-dbserver-1 2>/dev/null || docker compose ps dbserver --format '{{.State}}' 2>/dev/null || echo "missing")
    WEB_STATE=$(docker inspect -f '{{.State.Status}}' webserver 2>/dev/null || echo "missing")
    echo "[Check $i/20] dbserver: $DB_STATE | webserver: $WEB_STATE"

    if [ "$DB_STATE" = "running" ] && [ "$WEB_STATE" = "running" ]; then
        COMPOSE_OK=true
        break
    fi
    sleep 3
done

if [ "$COMPOSE_OK" != true ]; then
    echo "ERROR: Service compose tidak mencapai status running stabil!"
    docker compose logs 2>/dev/null || docker-compose logs 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "services_unhealthy" "Salah satu service compose gagal atau exited"
    exit 1
fi

# Validasi HTTP Response Port 8088
if check_http_status "http://localhost:8088" "200|302" 15 3; then
    update_status ${LKPD_NUM} "success" "verified" "Stack Docker Compose (MariaDB + Web) running & terverifikasi di port 8088"
else
    echo "ERROR: Webserver compose gagal merespon di port 8088."
    docker compose logs webserver 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "verification_failed" "Webserver compose gagal merespon di port 8088"
    exit 1
fi
