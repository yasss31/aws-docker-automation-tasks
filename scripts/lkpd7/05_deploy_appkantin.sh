#!/usr/bin/env bash
set -Eeuo pipefail

echo "=================================================="
echo "[LKPD 7] TUGAS 2: DEPLOY APPKANTIN KE DOCKER SWARM"
echo "=================================================="

MYWWW_DIR="/home/ubuntu/mywww"
if [ ! -d "/home/ubuntu" ]; then
    MYWWW_DIR="$HOME/mywww"
fi

TMP_REPO="/tmp/appKantin"

# 1. Simpan index.php lama (Info Server) jika ingin diuji kembali nanti
if [ -f "${MYWWW_DIR}/index.php" ]; then
    echo "Menyimpan backup Info Server sebagai index_info.php..."
    cp "${MYWWW_DIR}/index.php" "${MYWWW_DIR}/index_info.php"
fi

# 2. Clone repositori appKantin dari GitHub
echo "Mengunduh kode sumber appKantin dari GitHub..."
rm -rf "${TMP_REPO}"
git clone https://github.com/paknux/appKantin.git "${TMP_REPO}"

# 3. Salin berkas aplikasi ke direktori bind mount Swarm
echo "Memindahkan berkas aplikasi ke ${MYWWW_DIR}..."
cp -r "${TMP_REPO}"/* "${MYWWW_DIR}/"

# 4. Konfigurasi file config/db.php sesuai instruksi LKPD:
# Arahkan $DB_HOST ke "db" (nama container MariaDB di network kantin_net)
echo "Mengonfigurasi ${MYWWW_DIR}/config/db.php..."
cat << 'EOF' > "${MYWWW_DIR}/config/db.php"
<?php
/**
 * config/db.php
 * Konfigurasi Koneksi Database MariaDB untuk LKPD 7 Docker Swarm
 */
$DB_HOST = "db";
$DB_USER = "root";
$DB_PASS = "rahasia";
$DB_NAME = "kantin_db";

// 1. Konek ke MySQL/MariaDB
$conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS);
if ($conn->connect_error) {
    die("Koneksi ke MariaDB gagal: " . $conn->connect_error);
}

// 2. Buat database jika belum ada
$sqlCreateDb = "CREATE DATABASE IF NOT EXISTS `$DB_NAME` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci";
if (!$conn->query($sqlCreateDb)) {
    die("Gagal membuat database: " . $conn->error);
}

// 3. Pilih database
$conn->select_db($DB_NAME);

// 4. Buat tabel 'menu' jika belum ada
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

    // Dummy data menu kantin
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
EOF

# 5. Atur permission agar bisa diakses oleh Nginx & PHP-FPM
chmod -R 777 "${MYWWW_DIR}"

# 6. Validasi inisialisasi aplikasi melalui HTTP request
echo "Memvalidasi akses aplikasi appKantin di http://localhost:8080..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ || echo "ERR")

if [ "$HTTP_CODE" = "200" ]; then
    echo "[SUCCESS] appKantin berhasil berjalan di port 8080! (HTTP 200 OK)"
else
    echo "[WARN] Respon HTTP: $HTTP_CODE. Menunggu inisialisasi tabel..."
fi

echo ""
echo "=================================================="
echo "DEPLOYMENT APPKANTIN SELESAI!"
echo "Aplikasi dilayani oleh 3 replika Swarm secara load-balanced."
echo "URL Info Server asli : http://localhost:8080/index_info.php"
echo "URL appKantin utama : http://localhost:8080/"
echo "=================================================="
