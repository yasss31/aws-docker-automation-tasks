#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=6
echo "=== MEMULAI BOOTSTRAP LKPD 6: DOCKER SWARM MANAGER ==="

update_status ${LKPD_NUM} "in_progress" "swarm_init" "Menginisialisasi Docker Swarm Manager"

# Deteksi IP Manager
MANAGER_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    MANAGER_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
fi
if [ -z "$MANAGER_IP" ]; then
    MANAGER_IP=$(hostname -I | awk '{print $1}')
fi

echo "Inisialisasi Swarm Manager dengan IP ${MANAGER_IP}..."
docker swarm init --advertise-addr "${MANAGER_IP}" || true

WORKER_TOKEN=$(docker swarm join-token worker -q)
JOIN_CMD="docker swarm join --token ${WORKER_TOKEN} ${MANAGER_IP}:2377"

cat <<EOF > /opt/lkpd/swarm_info.json
{
  "manager_ip": "${MANAGER_IP}",
  "worker_token": "${WORKER_TOKEN}",
  "join_command": "${JOIN_CMD}",
  "initialized_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

# Siapkan direktori scripts helper di /home/ubuntu dan /opt/lkpd
mkdir -p /home/ubuntu/scripts /opt/lkpd/scripts

cat << 'EOF_CREATE' > /home/ubuntu/scripts/create_service.sh
#!/usr/bin/env bash
set -e
echo "Membuat service web 3 replika..."
docker service rm web 2>/dev/null || true
docker service create --name web --replicas 3 -p 8080:80 nginx
sleep 3
docker service ls
docker service ps web
EOF_CREATE

cat << 'EOF_SCALE' > /home/ubuntu/scripts/scale_service.sh
#!/usr/bin/env bash
set -e
echo "Scaling service web menjadi 5 replika..."
docker service scale web=5
sleep 3
docker service ls
docker service ps web
EOF_SCALE

cat << 'EOF_HEAL' > /home/ubuntu/scripts/test_self_healing.sh
#!/usr/bin/env bash
set -e
echo "=== SIMULASI SELF-HEALING ==="
echo "Status task awal:"
docker service ps web
CID=$(docker ps --filter "name=web." -q | head -n 1)
if [ -n "$CID" ]; then
    echo "Menghentikan kontainer: $CID"
    docker rm -f "$CID"
fi
echo "Status sesaat setelah dihentikan:"
docker service ps web
echo "Menunggu pemulihan otomatis (5 detik)..."
sleep 5
echo "Status setelah Swarm self-healing:"
docker service ps web
EOF_HEAL

chmod +x /home/ubuntu/scripts/*.sh
cp -r /home/ubuntu/scripts/* /opt/lkpd/scripts/ 2>/dev/null || true
chown -R ubuntu:ubuntu /home/ubuntu/scripts 2>/dev/null || true

update_status ${LKPD_NUM} "success" "manager_ready" "Swarm Manager siap (IP: ${MANAGER_IP}, Token: ${WORKER_TOKEN:0:10}...)"
echo "=== SWARM MANAGER BOOTSTRAP SELESAI ==="
