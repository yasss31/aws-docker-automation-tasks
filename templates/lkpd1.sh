#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=1
echo "=== MEMULAI EKSEKUSI LKPD 1: DASAR DOCKER & HTTPD ==="

# Langkah 3 PDF: hello-world test
update_status ${LKPD_NUM} "in_progress" "hello_world_test" "Menguji docker run hello-world"
retry_cmd 3 3 docker run --rm hello-world || {
    update_status ${LKPD_NUM} "failed" "docker_test_failed" "Gagal menjalankan container hello-world"
    exit 1
}

# Langkah 4 PDF: Folder mount
update_status ${LKPD_NUM} "in_progress" "prepare_mount" "Membuat direktori /var/mywww dan index.html"
mkdir -p /var/mywww
echo "<h1>Hello dari Docker HTTP</h1>" > /var/mywww/index.html

# Langkah 5 PDF: Jalankan container httpd:alpine (Idempotent cleanup)
update_status ${LKPD_NUM} "in_progress" "container_run" "Menjalankan container web-http (httpd:alpine) di port 8080"
docker rm -f web-http 2>/dev/null || true

retry_cmd 3 5 docker run -d \
  --name web-http \
  -p 8080:80 \
  -v /var/mywww:/usr/local/apache2/htdocs \
  --restart unless-stopped \
  httpd:alpine || {
    update_status ${LKPD_NUM} "failed" "run_failed" "Gagal docker run httpd:alpine"
    exit 1
}

# Langkah 6 PDF: Stop dan Start test
echo "Uji coba stop dan start container web-http sesuai petunjuk PDF..."
docker stop web-http
sleep 2
docker start web-http
sleep 3

# Validasi HTTP
if check_http_status "http://localhost:8080" "200" 12 3; then
    RESP_BODY=$(curl -s http://localhost:8080 || echo "")
    if echo "$RESP_BODY" | grep -q "Hello dari Docker HTTP"; then
        update_status ${LKPD_NUM} "success" "verified" "Container web-http running di port 8080 dan melayani 200 OK"
    else
        docker logs web-http 2>/dev/null || true
        update_status ${LKPD_NUM} "failed" "body_mismatch" "Respon HTTP 200 tetapi konten index.html tidak cocok"
        exit 1
    fi
else
    docker logs web-http 2>/dev/null || true
    update_status ${LKPD_NUM} "failed" "verification_failed" "Container gagal merespon 200 OK di port 8080"
    exit 1
fi
