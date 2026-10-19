#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 8] LANGKAH 11: PEMBERSIHAN SERVICE & SWARM"
echo "=================================================="

echo "Menghapus service web dan kantin..."
docker service rm web 2>/dev/null || true
docker service rm kantin 2>/dev/null || true
docker stack rm kantin 2>/dev/null || true

echo "Status Service saat ini:"
docker service ls

echo ""
echo "Catatan:"
echo "Jika ingin keluar total dari swarm:"
echo "Di worker1 dan worker2: docker swarm leave"
echo "Di manager: docker swarm leave --force"
echo "=================================================="
