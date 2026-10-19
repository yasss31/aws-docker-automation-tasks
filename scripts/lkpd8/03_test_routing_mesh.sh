#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_HOST="${1:-localhost}"
TARGET_PORT="${2:-8080}"

echo "=================================================="
echo "[LKPD 8] LANGKAH 7: UJI ROUTING MESH & LOAD BALANCING"
echo "Target URL: http://${TARGET_HOST}:${TARGET_PORT}/index.php"
echo "=================================================="

echo "Menjalankan 6x request berturut-turut untuk membuktikan Round-Robin:"
echo ""
printf "%-12s | %-30s | %-25s\n" "Request Ke-" "Hostname Replika (Container ID)" "Status HTTP"
printf "%-12s-+-%-30s-+-%-25s\n" "------------" "------------------------------" "-------------------------"

for i in {1..6}; do
    RESPONSE=$(curl -s "http://${TARGET_HOST}:${TARGET_PORT}/index.php" || true)
    HOSTNAME_VAL=$(echo "$RESPONSE" | grep -o '<b>[^<]*</b>' | head -1 | sed 's/<\/\?b>//g' || echo "N/A")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${TARGET_HOST}:${TARGET_PORT}/index.php" || echo "ERR")
    printf "%-12s | %-30s | HTTP %s\n" "Request $i" "$HOSTNAME_VAL" "$HTTP_CODE"
    sleep 0.3
done

echo ""
echo "=================================================="
echo "Analisis: Swarm Routing Mesh mendistribusikan trafik"
echo "secara round-robin ke seluruh replika (web.1, web.2, web.3)."
echo "=================================================="
