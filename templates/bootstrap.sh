#!/usr/bin/env bash
set -Eeuo pipefail

install -d -m 0755 /opt/lkpd
LOGFILE="/var/log/lkpd-runner.log"
exec > >(tee -a "${LOGFILE}" /dev/console) 2>&1

echo "=================================================="
echo "[BOOTSTRAP] Inisialisasi Environment EC2 & Helper"
echo "Waktu: $(date -u)"
echo "=================================================="

update_status() {
    local lkpd_num="$1"
    local status="$2"
    local stage="$3"
    local message="$4"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat <<EOF > /opt/lkpd/status.json
{
  "lkpd": "${lkpd_num}",
  "status": "${status}",
  "stage": "${stage}",
  "message": "${message}",
  "updated_at": "${now}"
}
EOF
    echo "[STATUS] LKPD ${lkpd_num} | ${status} | ${stage} | ${message}"
}

retry_cmd() {
    local max_attempts="$1"
    local delay="$2"
    shift 2
    local attempt=1
    until "$@"; do
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "[RETRY ERROR] Gagal mengeksekusi '$*' setelah ${max_attempts} kali percobaan." >&2
            return 1
        fi
        echo "[RETRY] Percobaan $attempt gagal! Menunggu ${delay}s sebelum mencoba ulang..." >&2
        sleep "$delay"
        attempt=$((attempt + 1))
    done
    return 0
}

check_http_status() {
    local url="$1"
    local expected_pattern="$2"
    local attempts="${3:-15}"
    local delay="${4:-3}"
    local code=""

    for ((i=1; i<=attempts; i++)); do
        code="$(curl -sS -o /dev/null -w "%{http_code}" "$url" || true)"
        if [[ "$code" =~ ^($expected_pattern)$ ]]; then
            echo "[HTTP OK] $url merespon $code pada percobaan $i"
            return 0
        fi
        echo "[HTTP WAITING] Percobaan $i/$attempts: $url merespon $code (ekspektasi: $expected_pattern). Menunggu ${delay}s..."
        sleep "$delay"
    done
    echo "[HTTP ERROR] $url gagal mencapai status $expected_pattern setelah $attempts percobaan." >&2
    return 1
}

export DEBIAN_FRONTEND=noninteractive

echo "[1/4] Update apt & instalasi paket prasyarat..."
retry_cmd 5 5 apt-get update -y
retry_cmd 5 5 apt-get install -y git nano curl links mc docker.io nmap jq net-tools

retry_cmd 3 5 apt-get install -y docker-compose-v2 || retry_cmd 3 5 apt-get install -y docker-compose || true

if ! command -v docker-compose &> /dev/null; then
    if docker compose version &> /dev/null; then
        cat << 'EOF' > /usr/local/bin/docker-compose
#!/bin/sh
exec docker compose "$@"
EOF
        chmod +x /usr/local/bin/docker-compose
    fi
fi

echo "[2/4] Menjalankan dan mengaktifkan service Docker..."
systemctl start docker
systemctl enable docker

if id "ubuntu" &>/dev/null; then
    usermod -aG docker ubuntu
fi

echo "[3/4] Memastikan Docker daemon siap..."
retry_cmd 5 3 docker info >/dev/null

echo "[4/4] Bootstrap selesai."
