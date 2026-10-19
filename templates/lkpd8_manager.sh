#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=8
echo "=== MEMULAI BOOTSTRAP LKPD 8: SWARM MANAGER NODE ==="

update_status ${LKPD_NUM} "in_progress" "node_init" "Mengatur hostname manager dan menginisialisasi Docker"

# 1. Atur Hostname
hostnamectl set-hostname manager
echo "Hostname diatur: manager"

# 2. Pastikan Docker terpasang dan service aktif
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker ubuntu || true
systemctl enable --now docker

# 3. Deteksi IP Private Manager
MANAGER_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    MANAGER_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
elif command -v ip &>/dev/null; then
    MANAGER_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $(NF-2); exit}' || true)
fi
if [ -z "$MANAGER_IP" ]; then
    MANAGER_IP=$(hostname -I | awk '{print $1}')
fi

echo "Inisialisasi Swarm Manager dengan advertise-addr ${MANAGER_IP}..."
docker swarm init --advertise-addr "${MANAGER_IP}" || true

WORKER_TOKEN=$(docker swarm join-token worker -q 2>/dev/null || echo "")

mkdir -p /opt/lkpd
cat <<EOF > /opt/lkpd/swarm_info.json
{
  "role": "manager",
  "private_ip": "${MANAGER_IP}",
  "worker_token": "${WORKER_TOKEN}",
  "join_command": "docker swarm join --token ${WORKER_TOKEN} ${MANAGER_IP}:2377",
  "updated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

# 4. Siapkan direktori mywww dan index.php (Info Server)
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

# 5. Pre-pull image untuk mempercepat deployment
docker pull trafex/php-nginx &>/dev/null &

update_status ${LKPD_NUM} "ready" "manager_ready" "Swarm Manager siap menerima worker node"
echo "=== BOOTSTRAP MANAGER NODE SELESAI ==="
