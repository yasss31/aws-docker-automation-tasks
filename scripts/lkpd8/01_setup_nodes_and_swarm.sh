#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] LANGKAH 1, 2, 3: SETUP CLUSTER DOCKER SWARM 3 NODE"
echo "=================================================="

# 1. Pastikan Docker berjalan
if ! systemctl is-active --quiet docker; then
    echo "Menjalankan service Docker..."
    sudo systemctl start docker
fi

# 2. Deteksi IP Private Manager
MANAGER_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    MANAGER_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
elif command -v ip &>/dev/null; then
    MANAGER_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $(NF-2); exit}' || true)
fi
if [ -z "$MANAGER_IP" ]; then
    MANAGER_IP=$(hostname -I | awk '{print $1}')
fi

echo "IP Private Manager: ${MANAGER_IP}"

# 3. Inisialisasi Swarm jika belum aktif
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")

if [ "$SWARM_STATE" = "active" ]; then
    echo "[INFO] Swarm Manager sudah aktif di node ini."
else
    echo "Menginisialisasi Docker Swarm Manager..."
    docker swarm init --advertise-addr "${MANAGER_IP}"
fi

WORKER_TOKEN=$(docker swarm join-token worker -q)
echo ""
echo "=================================================="
echo "TOKEN GABUNG WORKER (Jalankan ini di worker1 dan worker2):"
echo "docker swarm join --token ${WORKER_TOKEN} ${MANAGER_IP}:2377"
echo "=================================================="
echo ""
echo "STATUS NODE SAAT INI:"
docker node ls || true
