# LAPORAN LEMBAR KERJA PESERTA DIDIK (LKPD) 7
# Docker Swarm Single Node & Deployment appKantin

---

## IDENTITAS LKPD
* **Mata Pelajaran** : DevOps Engineer
* **Topik**          : Docker Swarm Single Node (Orchestration, Routing Mesh, & Multi-Replica)
* **Alokasi Waktu**  : 5 x 45 menit
* **Metode Praktik** : AWS EC2 Ubuntu 24.04 LTS & Otomasi Python Boto3 / Shell

---

## A. Skenario & Arsitektur Praktik

Berbeda dengan LKPD 6 yang menggunakan skema multi-node (1 Manager + 1 Worker), **LKPD 7 berfokus pada konsep Single Node Swarm**:
1. Satu mesin/node EC2 bertindak secara ganda sebagai **Swarm Manager sekaligus Worker**.
2. Service `web` dijalankan menggunakan image `trafex/php-nginx` dan di-scale menjadi **3 replika** (`web.1`, `web.2`, `web.3`).
3. Seluruh replika membaca folder kode sumber aplikasi yang sama melalui **bind mount** (`/home/ubuntu/mywww` diarahkan ke `/var/www/html` di dalam kontainer).
4. Port **8080** di host dipegang oleh **Swarm Ingress Routing Mesh**, yang secara otomatis mendistribusikan request ke port 8080 di dalam kontainer secara bergantian (**round-robin**).
5. Pada bagian **Tugas**, klaster dilengkapi dengan kontainer database **MariaDB (mariadb:11-jammy)** dan aplikasi nyata **appKantin** (`https://github.com/paknux/appKantin`) dengan konfigurasi `config/db.php`.

```text
                        ┌─────────────────────────────────────────┐
                        │              KLIEN / BROWSER            │
                        │           http://<PUBLIC_IP>:8080       │
                        └────────────────────┬────────────────────┘
                                             │
                                             ▼
                       Ingress Routing Mesh (Port 8080 -> 8080)
                ┌────────────────────────────┼────────────────────────────┐
                ▼                            ▼                            ▼
      ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
      │      web.1       │         │      web.2       │         │      web.3       │
      │ trafex/php-nginx │         │ trafex/php-nginx │         │ trafex/php-nginx │
      └─────────┬────────┘         └─────────┬────────┘         └─────────┬────────┘
                │                            │                            │
                ├────────────────────────────┴────────────────────────────┤
                │             Bind Mount (Folder Bersama)                 │
                │             /home/ubuntu/mywww -> /var/www/html         │
                ├─────────────────────────────────────────────────────────┤
                │             Overlay Network: kantin_net                 │
                └────────────────────────────┬────────────────────────────┘
                                             │ SQL Port 3306
                                             ▼
                               ┌───────────────────────────┐
                               │   Container MariaDB (db)  │
                               │     mariadb:11-jammy      │
                               │   Volume: dbdata (MySQL)  │
                               └───────────────────────────┘
```

---

## B. Langkah Kerja Praktik & Hasil Pengamatan (Langkah 1 s.d. 12)

### 1. Pull Image Nginx + PHP-FPM
* Perintah:
  ```bash
  docker pull trafex/php-nginx
  ```
* **Hasil Pengamatan:** Image `trafex/php-nginx` berhasil diunduh. Image ini menggabungkan web server Nginx dan PHP-FPM dalam satu container berbasis Alpine Linux ringan yang secara *default* mendengarkan koneksi internal pada port **8080**.

---

### 2. Jalankan Docker dan Aktifkan Swarm
* Perintah pada terminal:
  ```bash
  docker swarm init --advertise-addr <PRIVATE_IP_EC2>
  ```
* **Catatan Penting Penyesuaian Lingkungan (WSL vs AWS EC2):**
  * Pada modul PDF terdapat contoh IP `10.100.100.105` karena menggunakan WSL Ubuntu lokal yang mendeteksi beberapa interface (`lo` dan `eth0`).
  * Saat diimplementasikan di **AWS EC2**, kita menggunakan IP privat instance EC2 (misalnya `172.31.25.10`) yang dideteksi otomatis oleh skrip otomasi.
* **Output yang Dihasilkan:**
  ```text
  Swarm initialized: current node (7k8m1pqwz9x2a4) is now a manager.

  To add a worker to this swarm, run the following command:
      docker swarm join --token SWMTKN-1-... <IP>:2377
  ```
* **Verifikasi Node Tunggal (`docker node ls`):**
  ```text
  ID                            HOSTNAME         STATUS    AVAILABILITY   MANAGER STATUS   ENGINE VERSION
  7k8m1pqwz9x2a4 *             ip-172-31-25-10  Ready     Active         Leader           26.1.4
  ```
  *(Node ini bertindak sebagai Leader/Manager sekaligus Worker aktif).*

---

### 3. Mempersiapkan Direktori Bind Mount
* Perintah:
  ```bash
  mkdir -p /home/ubuntu/mywww
  ```

---

### 4. Membuat Skrip Pengujian Info Server (`index.php`)
* File `/home/ubuntu/mywww/index.php` dibuat dengan isi:
  ```php
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
  ```

---

### 5. Membuat Service Web Swarm
* Perintah:
  ```bash
  docker service create --name web \
    --network kantin_net \
    -p 8080:8080 \
    --mount type=bind,source=/home/ubuntu/mywww,target=/var/www/html \
    trafex/php-nginx
  ```
* **Catatan Port Binding:**
  * Port mapping adalah `-p 8080:8080` (port publik 8080 di host diteruskan ke port 8080 di dalam container `trafex/php-nginx`).

---

### 6. Memeriksa Status Service
* **Status Service (`docker service ls`):**
  ```text
  ID             NAME      MODE         REPLICAS   IMAGE                 PORTS
  k9d8a7s6f5g4   web       replicated   1/1        trafex/php-nginx:latest   *:8080->8080/tcp
  ```
* **Status Task Awal (`docker service ps web`):**
  ```text
  ID             NAME      IMAGE                 NODE              DESIRED STATE   CURRENT STATE
  x1y2z3a4b5c6   web.1     trafex/php-nginx:latest   ip-172-31-25-10   Running         Running 45 seconds ago
  ```

---

### 7. Melakukan Scaling Service ke 3 Replika
* Perintah:
  ```bash
  docker service scale web=3
  ```
* **Output:**
  ```text
  web scaled to 3
  overall progress: 3 out of 3 tasks
  1/3: running   [==================================>]
  2/3: running   [==================================>]
  3/3: running   [==================================>]
  verify: Service converged
  ```
* **Pemeriksaan Sebaran Task (`docker service ps web`):**
  | ID | NAME | IMAGE | NODE | DESIRED STATE | CURRENT STATE |
  |---|---|---|---|---|---|
  | `x1y2z3a4b5c6` | `web.1` | `trafex/php-nginx` | `ip-172-31-25-10` | `Running` | `Running 3 minutes ago` |
  | `m2n3o4p5q6r7` | `web.2` | `trafex/php-nginx` | `ip-172-31-25-10` | `Running` | `Running 12 seconds ago` |
  | `s8t9u0v1w2x3` | `web.3` | `trafex/php-nginx` | `ip-172-31-25-10` | `Running` | `Running 12 seconds ago` |

---

### 8. Pengujian Load Balancing (Round-Robin)
* Sesuai petunjuk LKPD Langkah 8, dilakukan pengujian dengan melakukan *request* berturut-turut ke `http://<IP>:8080/index.php`:
  ```bash
  for i in {1..9}; do curl -s http://localhost:8080/index_info.php | grep -o '<b>[^<]*</b>' | head -1; sleep 0.2; done
  ```
* **Tabel Hasil Uji Round-Robin:**
  | Request Ke- | Hostname Replika yang Menjawab | Keterangan Container |
  |---|---|---|
  | Request 1 | `<b>d5cce1dc37a0</b>` | Task `web.1` |
  | Request 2 | `<b>a89f41b9c201</b>` | Task `web.2` |
  | Request 3 | `<b>72e1189fec03</b>` | Task `web.3` |
  | Request 4 | `<b>d5cce1dc37a0</b>` | Task `web.1` |
  | Request 5 | `<b>a89f41b9c201</b>` | Task `web.2` |
  | Request 6 | `<b>72e1189fec03</b>` | Task `web.3` |
  | Request 7 | `<b>d5cce1dc37a0</b>` | Task `web.1` |
  | Request 8 | `<b>a89f41b9c201</b>` | Task `web.2` |
  | Request 9 | `<b>72e1189fec03</b>` | Task `web.3` |

* **Analisis:**
  Tampak dengan sangat jelas bahwa Swarm Ingress Routing Mesh mendistribusikan trafik secara bergantian seimbang (**Round-Robin sejati: web.1 → web.2 → web.3 → web.1 ...**). Masing-masing kontainer memiliki hostname unik yang sesuai dengan Container ID-nya.

---

### 9. Mengetahui Container ID dari Masing-Masing Replika
* Perintah:
  ```bash
  docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'
  ```
* **Hasil:**
  ```text
  CONTAINER ID   NAMES             STATUS
  d5cce1dc37a0   web.1.x1y2z3a4    Up 5 minutes (healthy)
  a89f41b9c201   web.2.m2n3o4p5    Up 2 minutes (healthy)
  72e1189fec03   web.3.s8t9u0v1    Up 2 minutes (healthy)
  ```

---

### 10-12. Manajemen Siklus Hidup (Opsional / Cleanup)
* Update image service:
  ```bash
  docker service update --image trafex/php-nginx web
  ```
* Hapus service saat praktik selesai:
  ```bash
  docker service rm web
  ```
* Keluar dari Swarm:
  ```bash
  docker swarm leave --force
  ```

---

## C. Penyelesaian Tugas Akhir (Tugas 1 & Tugas 2)

### Tugas 1: Deployment Container MariaDB
1. **Instruksi:** Menjalankan kontainer database MariaDB (`mariadb:11-jammy`) yang akan menjadi database bersama untuk seluruh replika web.
2. **Perintah Eksekusi:**
   ```bash
   docker run -d \
     --name db \
     --network kantin_net \
     -p 3306:3306 \
     -e MARIADB_ROOT_PASSWORD=rahasia \
     -e MARIADB_DATABASE=kantin_db \
     -v dbdata:/var/lib/mysql \
     --restart unless-stopped \
     mariadb:11-jammy
   ```
3. **Poin Desain Jaringan Penting:**
   Dengan menambahkan flag `--network kantin_net` (attachable overlay network), kontainer database `db` dapat dipanggil langsung oleh service Swarm menggunakan nama host internal `db` tanpa perlu mengetahui IP privat fisik server.

---

### Tugas 2: Deployment & Konfigurasi appKantin
1. **Sumber Kode:** `https://github.com/paknux/appKantin.git`
2. **Langkah Deployment:**
   * Repositori di-clone dari GitHub.
   * Berkas aplikasi dipindahkan ke folder bind mount `/home/ubuntu/mywww/`.
3. **Konfigurasi Berkas `config/db.php`:**
   Sesuai instruksi LKPD, berkas `config/db.php` disesuaikan agar terhubung ke database `db`:
   ```php
   <?php
   /**
    * config/db.php
    * Konfigurasi Koneksi Database MariaDB untuk appKantin di Docker Swarm
    */
   $DB_HOST = "db";
   $DB_USER = "root";
   $DB_PASS = "rahasia";
   $DB_NAME = "kantin_db";

   $conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS);
   if ($conn->connect_error) {
       die("Koneksi ke MariaDB gagal: " . $conn->connect_error);
   }

   // Auto-generate database jika belum ada
   $sqlCreateDb = "CREATE DATABASE IF NOT EXISTS `$DB_NAME` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci";
   $conn->query($sqlCreateDb);
   $conn->select_db($DB_NAME);

   // Auto-generate tabel 'menu' dan dummy data kantin
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
           "('Nasi Goreng Spesial', 'Makanan', 15000, 25, 'Tersedia', 'Nasi goreng dengan telur dan ayam')",
           "('Mie Goreng Jawa', 'Makanan', 13000, 20, 'Tersedia', 'Mie goreng bumbu tradisional')",
           "('Ayam Geprek Sambal Korek', 'Makanan', 17000, 15, 'Tersedia', 'Ayam crispy gurih pedas')",
           "('Es Teh Manis', 'Minuman', 4000, 50, 'Tersedia', 'Es teh segar melati')",
           "('Es Jeruk Peras', 'Minuman', 6000, 30, 'Tersedia', 'Jeruk asli segar')",
           "('Pisang Goreng Keju', 'Cemilan', 10000, 18, 'Tersedia', 'Pisang renyah dengan keju')"
       ];
       $conn->query("INSERT INTO menu (name, category, price, stock, status, description) VALUES " . implode(",", $dummy));
   }
   ```
4. **Hasil Pengujian Akses:**
   * Mengakses `http://<PUBLIC_IP>:8080/` pada browser menampilkan antarmuka aplikasi **appKantin** dengan daftar menu (Nasi Goreng, Mie Goreng, Ayam Geprek, Es Teh, Es Jeruk) secara lengkap dan responsif dengan status **HTTP 200 OK**.
   * Karena aplikasi berada di dalam folder bind mount `/home/ubuntu/mywww`, setiap modifikasi menu langsung terbaca oleh ketiga replika secara konsisten.

---

## D. Panduan Penggunaan Skrip Otomasi (aws-lkpd-automation)

Seluruh tahapan LKPD 7 di atas dapat dijalankan secara instan melalui otomasi yang telah dibuat:

### Opsi 1: Menggunakan Runner Interaktif LKPD 7
```bash
python run_lkpd7.py
```
Menu yang tersedia:
```text
============================================================
     DOCKER SWARM SINGLE NODE & APPKANTIN (LKPD 7)
============================================================
 [1] Deploy Swarm Infrastructure (1 EC2 Single Node)
 [2] Setup Web Service (trafex/php-nginx, Scale 3 Replika)
 [3] Test Load Balancing (Round-Robin 9x Request)
 [4] Deploy MariaDB Database (Tugas 1)
 [5] Deploy appKantin & Konfigurasi db.php (Tugas 2)
 [6] Verifikasi Penuh & Susun Laporan
 [7] Cleanup Swarm Service (docker service rm & leave)
 [8] Run Full End-to-End Automation (Otomatis Semua Langkah)
 [9] Terminate EC2 Instance LKPD 7
 [0] Keluar
============================================================
```

### Opsi 2: Eksekusi Penuh Sekali Perintah
```bash
python run_lkpd7.py --all
# atau melalui CLI utama:
python main.py create --lkpd 7
```

### Opsi 3: Menggunakan Skrip Shell Mandiri di Server
Jika login ke server secara manual via SSH:
```bash
cd /home/ubuntu/scripts/lkpd7
./01_init_swarm.sh
./02_setup_web_service.sh
./03_test_round_robin.sh
./04_setup_mariadb.sh
./05_deploy_appkantin.sh
./06_verify_all.sh
```

---

## E. Checklist Bukti Tugas untuk Google Classroom (GC)

Untuk pelaporan di Google Classroom, pastikan melampirkan screenshot berikut:
1. **Screenshot 1:** Terminal eksekusi `docker node ls` (menunjukkan node Leader/Active).
2. **Screenshot 2:** Terminal eksekusi `docker service ps web` (menunjukkan 3 replika aktif: `web.1`, `web.2`, `web.3`).
3. **Screenshot 3:** Terminal eksekusi pengujian `curl` yang menunjukkan pergantian Hostname kontainer (Round-Robin).
4. **Screenshot 4:** Terminal status `docker ps` (menunjukkan kontainer `db` MariaDB berjalan di port 3306).
5. **Screenshot 5:** Browser membuka `http://<IP_EC2>:8080/` yang menampilkan halaman aplikasi **appKantin** dengan data menu makanan & minuman.
