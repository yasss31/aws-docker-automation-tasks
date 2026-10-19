#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] LANGKAH 11 & 12: CLEANUP SWARM SERVICE & LEAVE"
echo "=================================================="

# 1. Hapus service web
if docker service inspect web &>/dev/null; then
    echo "Menghapus service 'web' (Langkah 11)..."
    docker service rm web
    sleep 3
    echo "[OK] Service web berhasil dihapus."
fi

# 2. Hapus container database
if docker ps -a --format '{{.Names}}' | grep -q '^db$'; then
    echo "Menghentikan dan menghapus container MariaDB 'db'..."
    docker rm -f db
    echo "[OK] Container db berhasil dihapus."
fi

# 3. Hapus network kantin_net jika ada
if docker network inspect kantin_net &>/dev/null; then
    echo "Menghapus network kantin_net..."
    docker network rm kantin_net 2>/dev/null || true
fi

# 4. Keluar dari Swarm (Langkah 12)
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")
if [ "$SWARM_STATE" = "active" ]; then
    echo "Keluar dari Docker Swarm (Langkah 12: docker swarm leave --force)..."
    docker swarm leave --force
    echo "[OK] Node berhasil keluar dari Docker Swarm."
fi

echo ""
echo "=================================================="
echo "CLEANUP LKPD 7 BERHASIL!"
echo "Semua container, service, dan Swarm state telah dibersihkan."
echo "=================================================="
