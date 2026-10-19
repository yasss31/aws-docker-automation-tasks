#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=6
echo "=== MEMULAI BOOTSTRAP LKPD 6: DOCKER SWARM WORKER ==="

update_status ${LKPD_NUM} "in_progress" "worker_bootstrap" "Menyiapkan environment Docker Worker Node"

mkdir -p /home/ubuntu/scripts /opt/lkpd/scripts

cat << 'EOF_WORKER' > /home/ubuntu/scripts/setup_worker.sh
#!/usr/bin/env bash
set -e
TOKEN="${1:-${SWARM_JOIN_TOKEN:-}}"
MANAGER_IP="${2:-${MANAGER_IP:-}}"

if [ -z "$TOKEN" ] || [ -z "$MANAGER_IP" ]; then
    echo "Usage: sudo $0 <SWARM_TOKEN> <MANAGER_IP>"
    exit 1
fi

docker swarm leave -f 2>/dev/null || true
echo "Bergabung ke Swarm manager $MANAGER_IP:2377..."
docker swarm join --token "$TOKEN" "$MANAGER_IP:2377"
echo "Worker node successfully joined Swarm!"
EOF_WORKER

chmod +x /home/ubuntu/scripts/*.sh
cp -r /home/ubuntu/scripts/* /opt/lkpd/scripts/ 2>/dev/null || true
chown -R ubuntu:ubuntu /home/ubuntu/scripts 2>/dev/null || true

update_status ${LKPD_NUM} "success" "worker_ready" "Docker Worker Node siap untuk bergabung ke Swarm cluster"
echo "=== SWARM WORKER BOOTSTRAP SELESAI ==="
