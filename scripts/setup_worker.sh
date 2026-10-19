#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 6] LANGKAH 2: SETUP DOCKER SWARM WORKER"
echo "=================================================="

# 1. Pastikan Docker berjalan
if ! systemctl is-active --quiet docker; then
    echo "Menjalankan service Docker..."
    sudo systemctl start docker
fi

# 2. Ambil parameter Token dan Manager IP
TOKEN="${1:-${SWARM_JOIN_TOKEN:-}}"
MANAGER_IP="${2:-${MANAGER_IP:-}}"

# Jika belum diberikan, coba cek file /opt/lkpd/swarm_info.json
if [ -z "$TOKEN" ] || [ -z "$MANAGER_IP" ]; then
    if [ -f /opt/lkpd/swarm_info.json ]; then
        TOKEN=$(jq -r '.worker_token' /opt/lkpd/swarm_info.json 2>/dev/null || true)
        MANAGER_IP=$(jq -r '.manager_ip' /opt/lkpd/swarm_info.json 2>/dev/null || true)
    fi
fi

if [ -z "$TOKEN" ] || [ -z "$MANAGER_IP" ]; then
    echo "ERROR: Token join atau IP Manager belum ditentukan!"
    echo "Penggunaan: $0 <SWARM_TOKEN> <MANAGER_IP>"
    echo "Atau set environment variable SWARM_JOIN_TOKEN dan MANAGER_IP."
    exit 1
fi

echo "Target Manager IP : ${MANAGER_IP}:2377"
echo "Menggunakan Token : ${TOKEN:0:15}..."

# 3. Keluar dari Swarm sebelumnya jika pernah join
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")
if [ "$SWARM_STATE" = "active" ]; then
    echo "Node sudah terdaftar di Swarm, me-reset keanggotaan..."
    docker swarm leave -f 2>/dev/null || true
    sleep 2
fi

# 4. Bergabung ke Swarm klaster
echo "Menjalankan docker swarm join..."
docker swarm join --token "${TOKEN}" "${MANAGER_IP}:2377"

# 5. Verifikasi status lokal
CURRENT_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}')
if [ "$CURRENT_STATE" = "active" ]; then
    echo ""
    echo "=================================================="
    echo "WORKER BERHASIL BERGABUNG KE SWARM CLUSTER!"
    echo "State Node: ${CURRENT_STATE}"
    echo "=================================================="
else
    echo "ERROR: Gagal bergabung ke Swarm cluster. State: ${CURRENT_STATE}"
    exit 1
fi
