#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] LANGKAH 3-7: SETUP WEB SERVICE & SCALE 3 REPLIKA"
echo "=================================================="

# 1. Tentukan direktori mywww (support ubuntu user atau root)
MYWWW_DIR="/home/ubuntu/mywww"
if [ ! -d "/home/ubuntu" ]; then
    MYWWW_DIR="$HOME/mywww"
fi

echo "Menyiapkan direktori bind mount: ${MYWWW_DIR}"
mkdir -p "${MYWWW_DIR}"

# 2. Buat index.php sesuai spesifikasi LKPD 7 (Langkah 4)
cat << 'EOF' > "${MYWWW_DIR}/index.php"
<?php
$hostname = gethostname();
$ip = gethostbyname($hostname);
?>
<!DOCTYPE html>
<html>
<head><title>Info Server</title></head>
<body style="font-family: sans-serif;">
<h2>Info Server</h2>
<p>Hostname: <b><?= htmlspecialchars($hostname) ?></b></p>
<p>IP server: <b><?= htmlspecialchars($ip) ?></b></p>
<p>IP client: <b><?= htmlspecialchars($_SERVER['REMOTE_ADDR']) ?></b></p>
</body>
</html>
EOF

chmod -R 777 "${MYWWW_DIR}"
echo "[OK] File index.php berhasil dibuat!"

# 3. Buat overlay network yang attachable agar service web dan container MariaDB dapat saling berkomunikasi
if ! docker network inspect kantin_net &>/dev/null; then
    echo "Membuat attachable overlay network 'kantin_net'..."
    docker network create --driver overlay --attachable kantin_net
fi

# 4. Hapus service web lama jika ada
if docker service inspect web &>/dev/null; then
    echo "Membersihkan service web lama..."
    docker service rm web
    sleep 3
fi

# 5. Buat service web (trafex/php-nginx) pada port 8080:8080
echo "Mengeksekusi pembuatan service web:"
echo "$ docker service create --name web --network kantin_net -p 8080:8080 --mount type=bind,source=${MYWWW_DIR},target=/var/www/html trafex/php-nginx"
docker service create \
  --name web \
  --network kantin_net \
  -p 8080:8080 \
  --mount type=bind,source="${MYWWW_DIR}",target=/var/www/html \
  trafex/php-nginx

echo "Menunggu container inisialisasi..."
sleep 5

# 6. Scaling ke 3 replika sesuai Langkah 7 LKPD
echo "Mengeksekusi scaling service ke 3 replika:"
echo "$ docker service scale web=3"
docker service scale web=3

echo "Menunggu seluruh 3 replika berstatus 'Running'..."
for i in {1..30}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    echo "[Check $i/30] Replika Running: $RUNNING_COUNT / 3"
    if [ "$RUNNING_COUNT" -ge 3 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "STATUS SERVICE (docker service ls):"
echo "=================================================="
docker service ls

echo ""
echo "=================================================="
echo "DISTRIBUSI TASK (docker service ps web):"
echo "=================================================="
docker service ps web
echo "=================================================="
