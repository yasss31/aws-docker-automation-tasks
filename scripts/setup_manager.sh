#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 6] LANGKAH 1: SETUP DOCKER SWARM MANAGER"
echo "=================================================="

# 1. Pastikan Docker berjalan
if ! systemctl is-active --quiet docker; then
    echo "Menjalankan service Docker..."
    sudo systemctl start docker
fi

# 2. Deteksi Private IP Node Manager
# Prioritas: AWS Instance Metadata -> Default Route Interface IP -> hostname -I
MANAGER_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    MANAGER_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
elif command -v ip &>/dev/null; then
    MANAGER_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $(NF-2); exit}' || true)
fi

if [ -z "$MANAGER_IP" ]; then
    MANAGER_IP=$(hostname -I | awk '{print $1}')
fi

echo "Detected Manager IP: ${MANAGER_IP}"

# 3. Inisialisasi Swarm jika belum aktif
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")

if [ "$SWARM_STATE" = "active" ]; then
    echo "[INFO] Node ini sudah menjadi bagian dari Swarm ($SWARM_STATE)."
    IS_MANAGER=$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo "false")
    if [ "$IS_MANAGER" != "true" ]; then
        echo "[WARN] Node aktif tapi bukan manager. Mereset swarm..."
        docker swarm leave -f 2>/dev/null || true
        docker swarm init --advertise-addr "${MANAGER_IP}"
    fi
else
    echo "Menginisialisasi Swarm Manager dengan advertise-addr: ${MANAGER_IP}..."
    docker swarm init --advertise-addr "${MANAGER_IP}"
fi

# 4. Ambil Join Token untuk Worker
WORKER_TOKEN=$(docker swarm join-token worker -q)
JOIN_CMD="docker swarm join --token ${WORKER_TOKEN} ${MANAGER_IP}:2377"

# 5. Simpan metadata untuk otomasi dan status
sudo mkdir -p /opt/lkpd
cat <<EOF | sudo tee /opt/lkpd/swarm_info.json > /dev/null
{
  "manager_ip": "${MANAGER_IP}",
  "worker_token": "${WORKER_TOKEN}",
  "join_command": "${JOIN_CMD}",
  "initialized_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

echo ""
echo "=================================================="
echo "DOCKER SWARM MANAGER BERHASIL DIINISIALISASI!"
echo "=================================================="
echo "Daftar Node saat ini:"
docker node ls
echo "--------------------------------------------------"
echo "Command untuk Worker Node bergabung (Langkah 2):"
echo "${JOIN_CMD}"
echo "=================================================="
