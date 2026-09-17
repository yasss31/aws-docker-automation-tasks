#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=4
echo "=== MEMULAI EKSEKUSI LKPD 4: PUBLIKASI KE DOCKER HUB ==="

if ! docker network inspect mynet &>/dev/null; then
    docker network create mynet
fi

mkdir -p /var/mywww
echo "<h1>LKPD 4 - Publikasi Docker Image ke Docker Hub</h1>" > /var/mywww/index.html

# Pastikan image dasar ubuntu-ws:v1 tersedia
if ! docker image inspect ubuntu-ws:v1 &>/dev/null; then
    mkdir -p /root/bws
    cat <<'EOF' > /root/bws/Dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y apache2 php curl && apt clean && rm -rf /var/lib/apt/lists/*
EXPOSE 80
CMD ["apache2ctl", "-D", "FOREGROUND"]
EOF
    retry_cmd 3 5 docker build -t ubuntu-ws:v1 /root/bws/
fi

DH_USER="${DOCKERHUB_USERNAME}"
DH_TOKEN="${DOCKERHUB_TOKEN}"
DH_REPO="${DOCKERHUB_REPOSITORY:-ubuntu-ws}"
DH_TAG="${DOCKERHUB_TAG:-v1}"

if [ -n "${DH_USER}" ] && [ -n "${DH_TOKEN}" ] && [ "${DOCKERHUB_SKIP_PUSH}" != "true" ]; then
    update_status ${LKPD_NUM} "in_progress" "docker_login" "Login ke Docker Hub sebagai ${DH_USER}"
    printf '%s' "${DH_TOKEN}" | docker login -u "${DH_USER}" --password-stdin || {
        update_status ${LKPD_NUM} "failed" "login_failed" "Gagal autentikasi ke Docker Hub"
        exit 1
    }

    TARGET_IMAGE="${DH_USER}/${DH_REPO}:${DH_TAG}"
    update_status ${LKPD_NUM} "in_progress" "docker_tag_push" "Tagging & Pushing image ke ${TARGET_IMAGE}"
    docker tag ubuntu-ws:v1 "${TARGET_IMAGE}"
    retry_cmd 3 5 docker push "${TARGET_IMAGE}" || {
        update_status ${LKPD_NUM} "failed" "push_failed" "Gagal docker push ke ${TARGET_IMAGE}"
        exit 1
    }

    # PEMBUKTIAN REMOTE: Hapus tag lokal dan verifikasi image benar-benar terhapus sebelum pull
    echo "Menghapus tag lokal ${TARGET_IMAGE} untuk pembuktian pull..."
    docker rm -f webserver2 2>/dev/null || true
    docker rmi "${TARGET_IMAGE}" || true

    update_status ${LKPD_NUM} "in_progress" "docker_pull" "Melakukan docker pull image dari Docker Hub..."
    retry_cmd 3 5 docker pull "${TARGET_IMAGE}" || {
        update_status ${LKPD_NUM} "failed" "pull_failed" "Gagal pull image dari Docker Hub setelah dipush"
        exit 1
    }

    # Run container webserver2 dari image hasil pull di port 8002
    update_status ${LKPD_NUM} "in_progress" "container_run" "Menjalankan container webserver2 di port 8002"
    retry_cmd 3 3 docker run -d \
      --name webserver2 \
      --network mynet \
      -p 8002:80 \
      -v /var/mywww:/var/www/html \
      --restart unless-stopped \
      "${TARGET_IMAGE}" || {
        update_status ${LKPD_NUM} "failed" "run_failed" "Gagal menjalankan webserver2"
        exit 1
    }

    if check_http_status "http://localhost:8002" "200" 12 2; then
        update_status ${LKPD_NUM} "success" "verified" "Siklus penuh Docker Hub (Push -> Rmi -> Pull -> Run) SUKSES di port 8002"
    else
        docker logs webserver2 2>/dev/null || true
        update_status ${LKPD_NUM} "failed" "verification_failed" "Container webserver2 gagal merespon di port 8002"
        exit 1
    fi
else
    # Status JUJUR jika kredensial Docker Hub tidak ada
    echo "CATATAN: Kredensial Docker Hub tidak tersedia di .env."
    TARGET_IMAGE="${DH_USER:-local}/${DH_REPO}:${DH_TAG}"
    docker rm -f webserver2 2>/dev/null || true
    docker tag ubuntu-ws:v1 "${TARGET_IMAGE}"
    docker run -d \
      --name webserver2 \
      --network mynet \
      -p 8002:80 \
      -v /var/mywww:/var/www/html \
      --restart unless-stopped \
      "${TARGET_IMAGE}"
    update_status ${LKPD_NUM} "partial" "credentials_skipped" "Tagging lokal selesai (port 8002). Push dilewati karena kredensial Docker Hub belum diisi."
fi
