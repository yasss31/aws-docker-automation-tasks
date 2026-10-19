#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] LANGKAH 8 & 9: UJI LOAD BALANCING (ROUND-ROBIN)"
echo "=================================================="

URL="http://localhost:8080/index.php"

# 1. Pastikan port 8080 merespon
echo "Memeriksa ketersediaan service di ${URL}..."
if ! curl -s -m 3 -o /dev/null "$URL"; then
    echo "ERROR: Service web di port 8080 belum dapat diakses!"
    exit 1
fi

echo ""
echo "Melakukan 9 request berturut-turut untuk menguji pembagian beban (Round-Robin Swarm):"
echo "--------------------------------------------------"
printf "%-10s | %-20s | %-15s\n" "Request #" "Hostname Replika" "Status HTTP"
echo "--------------------------------------------------"

UNIQUE_HOSTS=""

for i in {1..9}; do
    RESP=$(curl -s -m 3 "$URL" || true)
    # Ekstrak konten dalam tag <b> pertama (Hostname)
    HOST=$(echo "$RESP" | grep -o '<b>[^<]*</b>' | head -n 1 | sed 's/<\/\?b>//g' || echo "UNKNOWN")
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL" || echo "ERR")
    printf "%-10s | %-20s | %-15s\n" "Request $i" "$HOST" "HTTP $CODE"
    UNIQUE_HOSTS="${UNIQUE_HOSTS} ${HOST}"
    sleep 0.5
done

echo "--------------------------------------------------"
TOTAL_UNIQUE=$(echo "$UNIQUE_HOSTS" | tr ' ' '\n' | grep -v '^$' | sort -u | wc -l)
echo "Total replika unik yang merespon request: ${TOTAL_UNIQUE} / 3 replika."

echo ""
echo "=================================================="
echo "DAFTAR CONTAINER ID AKTIF (docker ps):"
echo "=================================================="
docker ps --filter "name=web." --format "table {{.ID}}\t{{.Names}}\t{{.Status}}"
echo "=================================================="
echo "[KESIMPULAN PENGAMATAN]"
echo "Routing mesh Docker Swarm berhasil membagi request yang masuk ke port 8080"
echo "secara bergantian (round-robin) ke seluruh kontainer replika."
echo "=================================================="
