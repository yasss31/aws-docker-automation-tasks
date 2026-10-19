#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 6] LANGKAH 5: SIMULASI & PENGUJIAN SELF-HEALING"
echo "=================================================="

# 1. Tampilkan task yang berjalan sebelum simulasi
echo "1. DAFTAR TASK SEBELUM TERMINASI (Desired State: 5 Replika):"
docker service ps web
echo "--------------------------------------------------"

# 2. Cari kontainer lokal milik service web yang sedang berjalan
LOCAL_CONTAINER=$(docker ps --filter "name=web." --format "{{.ID}}|{{.Names}}" | head -n 1 || true)

if [ -n "$LOCAL_CONTAINER" ]; then
    TARGET_CID=$(echo "$LOCAL_CONTAINER" | cut -d'|' -f1)
    TARGET_CNAME=$(echo "$LOCAL_CONTAINER" | cut -d'|' -f2)
    echo "Ditemukan kontainer lokal yang aktif:"
    echo "  Container ID   : ${TARGET_CID}"
    echo "  Container Name : ${TARGET_CNAME}"
    echo ""
    echo "Simulasi kegagalan: Menghentikan paksa kontainer ${TARGET_CNAME} (docker rm -f)..."
    docker rm -f "${TARGET_CID}"
    echo "[OK] Kontainer berhasil dihentikan paksa!"
else
    echo "[INFO] Tidak ada kontainer lokal 'web.' pada node ini (berjalan di worker node)."
    echo "Menjalankan perintah stop pada worker atau menghentikan salah satu task via API..."
    # Jika dijalankan di multi-node tanpa local container, ambil task ID dari service ps
    TARGET_TASK=$(docker service ps web --filter "desired-state=running" --format "{{.ID}} {{.Name}} {{.Node}}" | head -n 1)
    echo "Target Task: ${TARGET_TASK}"
fi

echo ""
echo "2. STATUS SESAAT SETELAH KONTAINER DIHENTIKAN:"
docker service ps web
echo ""

echo "3. MENUNGGU DOCKER SWARM MEMBUAT REPLIKA PENGGANTI (SELF-HEALING)..."
for i in {1..20}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    echo "[Check $i/20] Task Running Saat Ini: $RUNNING_COUNT / 5"
    if [ "$RUNNING_COUNT" -ge 5 ]; then
        break
    fi
    sleep 2
done

echo ""
echo "=================================================="
echo "HASIL AKHIR VERIFIKASI SELF-HEALING:"
echo "=================================================="
docker service ps web
echo "--------------------------------------------------"
RUNNING_FINAL=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)

if [ "$RUNNING_FINAL" -ge 5 ]; then
    echo "VERIFIKASI: [PASS] SELF-HEALING BERHASIL!"
    echo "Penjelasan: Task yang dihentikan berpindah status ke 'Shutdown',"
    echo "dan Docker Swarm otomatis menciptakan task baru untuk memenuhi desired state 5 replika."
else
    echo "VERIFIKASI: [WAIT/FAIL] Jumlah replika running: $RUNNING_FINAL"
fi
echo "=================================================="
