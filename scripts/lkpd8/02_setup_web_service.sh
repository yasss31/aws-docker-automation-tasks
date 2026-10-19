#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] LANGKAH 4, 5, 6: SETUP SERVICE WEB 3 REPLIKA"
echo "=================================================="

MYWWW_DIR="/home/ubuntu/mywww"
mkdir -p "${MYWWW_DIR}"

# 1. Pastikan skrip info server ada
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

# 2. Hapus service web lama jika ada
docker service rm web 2>/dev/null || true
sleep 2

# 3. Buat service web (Langkah 5)
echo "Membuat service web awal (trafex/php-nginx port 8080)..."
docker service create \
  --name web \
  -p 8080:8080 \
  --mount type=bind,source="${MYWWW_DIR}",target=/var/www/html \
  trafex/php-nginx

sleep 3
echo ""
echo "Status Service Awal:"
docker service ls
docker service ps web

# 4. Scale menjadi 3 replika (Langkah 6)
echo ""
echo "Melakukan scaling service web ke 3 replika..."
docker service scale web=3

# Tunggu konvergensi replika
echo "Menunggu ketiga replika running..."
for i in {1..30}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    if [ "$RUNNING_COUNT" -ge 3 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "HASIL SCALING SERVICE WEB (3 REPLIKA):"
echo "=================================================="
docker service ps web
echo "=================================================="
