#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] LANGKAH 1 & 2: INISIALISASI DOCKER SWARM SINGLE NODE"
echo "=================================================="

# 1. Pastikan Docker aktif
if ! systemctl is-active --quiet docker; then
    echo "Menjalankan service Docker..."
    sudo systemctl start docker
fi

# 2. Deteksi IP Advertised (AWS Private IP / Interface IP)
# Hindari IP statis WSL (seperti 10.100.100.105 pada contoh PDF) jika berjalan di EC2
NODE_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    NODE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
elif command -v ip &>/dev/null; then
    NODE_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $(NF-2); exit}' || true)
fi

if [ -z "$NODE_IP" ]; then
    NODE_IP=$(hostname -I | awk '{print $1}')
fi

echo "Alamat IP yang digunakan (--advertise-addr): ${NODE_IP}"

# 3. Inisialisasi Swarm jika belum aktif
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")

if [ "$SWARM_STATE" = "active" ]; then
    echo "[INFO] Node sudah aktif di Docker Swarm ($SWARM_STATE)."
else
    echo "Menginisialisasi Swarm Single Node..."
    docker swarm init --advertise-addr "${NODE_IP}"
fi

echo ""
echo "=================================================="
echo "STATUS SWARM NODE:"
echo "=================================================="
docker node ls
echo "Node ini berperan ganda sebagai Manager sekaligus Worker (Single Node)."
echo "=================================================="
