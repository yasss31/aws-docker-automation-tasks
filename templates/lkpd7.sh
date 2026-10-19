#!/usr/bin/env bash
source /opt/lkpd/bootstrap.sh

LKPD_NUM=7
echo "=== MEMULAI BOOTSTRAP LKPD 7: DOCKER SWARM SINGLE NODE & APPKANTIN ==="

update_status ${LKPD_NUM} "in_progress" "swarm_init" "Menginisialisasi Docker Swarm Single Node"

# 1. Deteksi IP Node EC2
NODE_IP=""
if curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 &>/dev/null; then
    NODE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
fi
if [ -z "$NODE_IP" ]; then
    NODE_IP=$(hostname -I | awk '{print $1}')
fi

echo "Inisialisasi Swarm Single Node dengan advertise-addr ${NODE_IP}..."
docker swarm init --advertise-addr "${NODE_IP}" || true

# 2. Siapkan direktori mywww dan index.php (Info Server)
MYWWW_DIR="/home/ubuntu/mywww"
mkdir -p "${MYWWW_DIR}"

cat << 'EOF_INFO' > "${MYWWW_DIR}/index.php"
<?php
$hostname = gethostname();
$ip = gethostbyname($hostname);
?>
<!DOCTYPE html>
<html>
<head><title>Info Server</title></head>
<body style="font-family: sans-serif;">
<h2>Info Server</h2>
<p>Hostname: <b><?= htmlspecialchars($hostname) ?></b></p>
<p>IP server: <b><?= htmlspecialchars($ip) ?></b></p>
<p>IP client: <b><?= htmlspecialchars($_SERVER['REMOTE_ADDR']) ?></b></p>
</body>
</html>
EOF_INFO
cp "${MYWWW_DIR}/index.php" "${MYWWW_DIR}/index_info.php"
chmod -R 777 "${MYWWW_DIR}"

# 3. Buat overlay network 'kantin_net' yang attachable
docker network create --driver overlay --attachable kantin_net 2>/dev/null || true

# 4. Buat service web dan scale ke 3 replika (Langkah 5-7)
update_status ${LKPD_NUM} "in_progress" "service_create" "Membuat service web 3 replika (trafex/php-nginx)"
docker service rm web 2>/dev/null || true
docker service create \
  --name web \
  --network kantin_net \
  -p 8080:8080 \
  --mount type=bind,source="${MYWWW_DIR}",target=/var/www/html \
  trafex/php-nginx

sleep 4
docker service scale web=3

# Tunggu replika running
for i in {1..25}; do
    RUNNING_COUNT=$(docker service ps web --filter "desired-state=running" --format "{{.CurrentState}}" 2>/dev/null | grep -ic "running" || echo 0)
    if [ "$RUNNING_COUNT" -ge 3 ]; then
        break
    fi
    sleep 2
done

# 5. Jalankan MariaDB (Tugas 1)
update_status ${LKPD_NUM} "in_progress" "database_setup" "Deploy database MariaDB untuk Swarm"
docker rm -f db 2>/dev/null || true
docker run -d \
  --name db \
  --network kantin_net \
  -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=rahasia \
  -e MARIADB_DATABASE=kantin_db \
  -v dbdata:/var/lib/mysql \
  --restart unless-stopped \
  mariadb:11-jammy

# Tunggu MariaDB siap
for i in {1..20}; do
    if docker exec db mariadb-admin ping -uroot -prahasia &>/dev/null || docker exec db mysqladmin ping -uroot -prahasia &>/dev/null; then
        break
    fi
    sleep 3
done

# 6. Deploy appKantin (Tugas 2)
update_status ${LKPD_NUM} "in_progress" "deploy_kantin" "Clone dan konfigurasi appKantin dari GitHub"
TMP_KANTIN="/tmp/appKantin"
rm -rf "${TMP_KANTIN}"
git clone https://github.com/paknux/appKantin.git "${TMP_KANTIN}"
cp -r "${TMP_KANTIN}"/* "${MYWWW_DIR}/"

cat << 'EOF_DB' > "${MYWWW_DIR}/config/db.php"
<?php
$DB_HOST = "db";
$DB_USER = "root";
$DB_PASS = "rahasia";
$DB_NAME = "kantin_db";

$conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS);
if ($conn->connect_error) {
    die("Koneksi ke MariaDB gagal: " . $conn->connect_error);
}

$sqlCreateDb = "CREATE DATABASE IF NOT EXISTS `$DB_NAME` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci";
if (!$conn->query($sqlCreateDb)) {
    die("Gagal membuat database: " . $conn->error);
}
$conn->select_db($DB_NAME);

$tableCheck = $conn->query("SHOW TABLES LIKE 'menu'");
if (!$tableCheck || $tableCheck->num_rows == 0) {
    $sqlCreateTable = "
        CREATE TABLE menu (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            category ENUM('Makanan', 'Minuman', 'Cemilan') NOT NULL DEFAULT 'Makanan',
            price DECIMAL(12,2) NOT NULL DEFAULT 0,
            stock INT NOT NULL DEFAULT 0,
            status ENUM('Tersedia', 'Habis') NOT NULL DEFAULT 'Tersedia',
            description TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ";
    $conn->query($sqlCreateTable);

    $dummy = [
        "('Nasi Goreng Spesial', 'Makanan', 15000, 25, 'Tersedia', 'Nasi goreng dengan telur dan ayam suwir')",
        "('Mie Goreng Jawa', 'Makanan', 13000, 20, 'Tersedia', 'Mie goreng bumbu tradisional')",
        "('Ayam Geprek Sambal Korek', 'Makanan', 17000, 15, 'Tersedia', 'Ayam crispy pedas gurih')",
        "('Es Teh Manis', 'Minuman', 4000, 50, 'Tersedia', 'Es teh segar melati')",
        "('Es Jeruk Peras', 'Minuman', 6000, 30, 'Tersedia', 'Jeruk asli segar')",
        "('Pisang Goreng Keju', 'Cemilan', 10000, 18, 'Tersedia', 'Pisang renyah dengan taburan keju')"
    ];
    $conn->query("INSERT INTO menu (name, category, price, stock, status, description) VALUES " . implode(",", $dummy));
}
EOF_DB

chmod -R 777 "${MYWWW_DIR}"
chown -R ubuntu:ubuntu "${MYWWW_DIR}" 2>/dev/null || true

# 7. Salin skrip helper ke /home/ubuntu/scripts
mkdir -p /home/ubuntu/scripts /opt/lkpd/scripts
cat << 'EOF_HELPER' > /home/ubuntu/scripts/test_round_robin.sh
#!/bin/bash
for i in {1..9}; do
    curl -s http://localhost:8080/index_info.php | grep -o '<b>[^<]*</b>' | head -1
    sleep 0.3
done
EOF_HELPER
chmod +x /home/ubuntu/scripts/*.sh
chown -R ubuntu:ubuntu /home/ubuntu/scripts 2>/dev/null || true

# 8. Validasi HTTP Response di Port 8080
if check_http_status "http://localhost:8080" "200" 15 3; then
    update_status ${LKPD_NUM} "success" "verified" "Docker Swarm Single Node (3 Replika) & appKantin dengan MariaDB aktif di port 8080"
else
    update_status ${LKPD_NUM} "failed" "verification_failed" "Gagal mengakses appKantin di port 8080"
    exit 1
fi

echo "=== BOOTSTRAP LKPD 7 SELESAI DENGAN SUKSES ==="
