#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=8
WORKER_NAME="${WORKER_NAME:-worker1}"
echo "=== MEMULAI BOOTSTRAP LKPD 8: SWARM WORKER NODE (${WORKER_NAME}) ==="

update_status ${LKPD_NUM} "in_progress" "node_init" "Mengatur hostname ${WORKER_NAME} dan menginstal Docker"

# 1. Atur Hostname
hostnamectl set-hostname "${WORKER_NAME}"
echo "Hostname diatur: ${WORKER_NAME}"

# 2. Pastikan Docker terpasang dan service aktif
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker ubuntu || true
systemctl enable --now docker

# 3. Siapkan direktori bind mount mywww dan index.php (identik dengan Manager)
MYWWW_DIR="/home/ubuntu/mywww"
mkdir -p "${MYWWW_DIR}"
cat << 'EOF_INFO' > "${MYWWW_DIR}/index.php"
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
EOF_INFO
cp "${MYWWW_DIR}/index.php" "${MYWWW_DIR}/index_info.php"
chown -R ubuntu:ubuntu "${MYWWW_DIR}"
chmod -R 755 "${MYWWW_DIR}"

# 4. Pre-pull image trafex/php-nginx
docker pull trafex/php-nginx &>/dev/null &

update_status ${LKPD_NUM} "ready" "worker_ready" "${WORKER_NAME} siap bergabung ke Swarm cluster"
echo "=== BOOTSTRAP WORKER NODE SELESAI ==="
