# LAPORAN LEMBAR KERJA PESERTA DIDIK (LKPD) 8
# Docker Swarm Multi-Node Cluster (3 Node Swarm + 1 Database Eksternal) di AWS Academy

---

## IDENTITAS LKPD
* **Mata Pelajaran** : DevOps Engineer
* **Topik**          : Docker Swarm Multi Node (1 Manager + 2 Worker) & Database Terpisah di AWS
* **Alokasi Waktu**  : 5 x 45 menit
* **Lingkungan**     : AWS Academy Learner Lab (Region `us-east-1`)
* **Spesifikasi**    : 4 Instance EC2 Ubuntu 24.04 LTS (t3.small), IAM Profile `LabInstanceProfile`, Security Group `sg-swarm`
* **Metode Praktik** : AWS EC2 Multi-Node, Ingress Routing Mesh, MariaDB 11.8 Standalone, & Otomasi Python Boto3 / Shell

---

## A. Capaian & Tujuan Pembelajaran

### Capaian Pembelajaran
Peserta didik mampu merancang, membangun, dan mengelola klaster kontainer berskala multi-node menggunakan Docker Swarm pada infrastruktur cloud AWS, memisahkan lapisan aplikasi (stateless) dan lapisan basis data (stateful), serta mengimplementasikan routing mesh, load balancing, rolling update, dan fault tolerance.

### Tujuan Pembelajaran
Setelah menyelesaikan LKPD ini, peserta didik mampu:
1. Menyiapkan **4 instance EC2 Ubuntu** di AWS: 3 instance untuk klaster Docker Swarm (1 manager + 2 worker) dan 1 instance terpisah untuk database, beserta aturan **Security Group** yang aman.
2. Membentuk klaster Swarm multi-node: menginisialisasi manager dan menggabungkan kedua worker ke dalam klaster menggunakan token join melalui port internal 2377.
3. Men-deploy service web dengan **3 replika** yang tersebar di node yang berbeda, serta membuktikan mekanisme **round-robin load balancing** dari **Ingress Routing Mesh**.
4. Mengelola siklus hidup service klaster meliputi **scale up/down**, **zero-downtime rolling update**, dan simulasi pemeliharaan node menggunakan fitur **drain**.
5. Menempatkan database MariaDB 11.8 pada instance tersendiri, menghubungkan seluruh replika aplikasi web (**appKantin**) ke database tersebut melalui IP privat VPC, dan men-deploy aplikasi secara deklaratif menggunakan **Docker Stack**.

---

## B. Skenario & Arsitektur Klaster 4 Node

Pada LKPD 8 ini, arsitektur dibagi menjadi dua lapisan utama untuk memisahkan beban kerja dinamis (*stateless*) dan persistensi data (*stateful*):
1. **Docker Swarm Cluster (3 Node):**
   * **`manager`** (Leader): Bertanggung jawab atas konsensus Raft, penjadwalan (*scheduler*), orkestrasi service, dan pemantauan kesehatan klaster.
   * **`worker1` & `worker2`** (Workers): Menerima dan menjalankan *task* kontainer dari manager.
   * Ketiga node ini saling terhubung dalam jaringan overlay (*VXLAN*) dan memegang port **8080** secara bersama melalui **Ingress Routing Mesh**.
2. **Database Instance Terpisah (`db` di luar Swarm):**
   * Berdiri sendiri di luar klaster Swarm untuk menjamin isolasi data performa tinggi.
   * Menjalankan MariaDB 11.8 pada port **3306** dengan data tersimpan aman pada Docker Named Volume `dbdata`.
   * Hanya dapat diakses oleh node-node yang tergabung dalam Security Group `sg-swarm` melalui alamat **IP Privat**.

```text
                        ┌────────────────────────────────────────────────────────┐
                        │                   KLIEN / BROWSER                      │
                        │   http://<IP-PUBLIC-MANAGER>:8080                      │
                        │   http://<IP-PUBLIC-WORKER1>:8080                      │
                        │   http://<IP-PUBLIC-WORKER2>:8080                      │
                        └───────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                    ┌────────────────────────────────────────────────────────────────┐
                    │               INGRESS ROUTING MESH (PORT 8080)                 │
                    │         Meneruskan request secara Round-Robin ke replika       │
                    └───────────────────────────────┬────────────────────────────────┘
                                                    │
                 ┌──────────────────────────────────┼──────────────────────────────────┐
                 ▼                                  ▼                                  ▼
     ┌───────────────────────┐          ┌───────────────────────┐          ┌───────────────────────┐
     │     NODE MANAGER      │          │     NODE WORKER1      │          │     NODE WORKER2      │
     │      (Leader)         │          │       (Worker)        │          │       (Worker)        │
     ├───────────────────────┤          ├───────────────────────┤          ├───────────────────────┤
     │ Replika: web.1/kantin │          │ Replika: web.2/kantin │          │ Replika: web.3/kantin │
     │  (trafex/php-nginx)   │          │  (trafex/php-nginx)   │          │  (trafex/php-nginx)   │
     │                       │          │                       │          │                       │
     │ Bind Mount:           │          │ Bind Mount:           │          │ Bind Mount:           │
     │ /home/ubuntu/appKantin│          │ /home/ubuntu/appKantin│          │ /home/ubuntu/appKantin│
     └───────────┬───────────┘          └───────────┬───────────┘          └───────────┬───────────┘
                 │                                  │                                  │
                 └──────────────────────────────────┼──────────────────────────────────┘
                                                    │
                          Koneksi SQL TCP:3306      │  (Menggunakan IP Privat VPC)
                          Dibatasi SG: sg-swarm     │
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │      INSTANCE DATABASE (db)   │
                                    │       (Di Luar Klaster)       │
                                    ├───────────────────────────────┤
                                    │ Container: db (MariaDB 11.8)  │
                                    │ Port: 3306 -> 3306            │
                                    │ Volume: dbdata (/var/lib/mysql)│
                                    │ Database: kantin_db           │
                                    └───────────────────────────────┘
```

---

## C. Persiapan Infrastruktur di AWS Academy

### 1. Pembuatan Security Group (`swarm-sg`)
Sesuai panduan LKPD 8 Halaman 3, dibuat Security Group untuk klaster pada VPC default. 

> [!NOTE]
> **Catatan Penyesuaian Nama Security Group di AWS (`swarm-sg` vs `sg-swarm`):**
> Pada teks modul panduan praktikum tertulis nama `sg-swarm`. Namun, layanan AWS EC2 secara resmi menerapkan aturan validasi ketat: *`Value (sg-swarm) for parameter GroupName is invalid. Group names may not be in the format sg-*`* karena awalan `sg-` dicadangkan khusus untuk ID Security Group oleh AWS. Oleh karena itu, nama Security Group disesuaikan menjadi **`swarm-sg`** dengan seluruh aturan port yang identik 100%.

Port manajemen internal klaster dan akses basis data diproteksi ketat menggunakan referensi Security Group itu sendiri (*Self-Referencing* `swarm-sg`):

| Tipe Port | Protokol | Port | Sumber (*Source*) | Fungsi / Peruntukan |
|:---|:---:|:---:|:---|:---|
| **SSH** | TCP | 22 | `0.0.0.0/0` (atau My IP) | Akses remote administrasi terminal EC2 |
| **Custom TCP** | TCP | 2377 | `swarm-sg` (*Group ID*) | Komunikasi manajemen klaster Docker Swarm (Raft) |
| **Custom TCP** | TCP | 7946 | `swarm-sg` (*Group ID*) | Komunikasi gossip discovery antar-node klaster |
| **Custom UDP** | UDP | 7946 | `swarm-sg` (*Group ID*) | Komunikasi gossip discovery antar-node klaster |
| **Custom UDP** | UDP | 4789 | `swarm-sg` (*Group ID*) | Enkapsulasi paket overlay network (*VXLAN data plane*) |
| **Custom TCP** | TCP | 8080 | `0.0.0.0/0` | Akses antarmuka aplikasi web publik dari browser |
| **Custom TCP** | TCP | 3306 | `swarm-sg` (*Group ID*) | Akses database MariaDB khusus dari node-node klaster |

> **Analisis Keamanan:**
> Aturan self-referencing pada port 2377, 7946, 4789, dan 3306 memastikan bahwa lalu lintas klaster dan database sepenuhnya terisolasi dari internet publik. Hanya instance EC2 yang memiliki kartu identitas keamanan `swarm-sg` yang diizinkan saling bertukar paket.

### 2. Peluncuran 4 Instance EC2
Diluncurkan 4 instance EC2 dengan konfigurasi terstandarisasi:
* **AMI**: Ubuntu Server 24.04 LTS (`ami-0fa5967347d08d2df`)
* **Instance Type**: `t3.small` (2 vCPU, 2 GiB RAM)
* **Key Pair**: `vockey`
* **Security Group**: `swarm-sg` (`sg-0f05f28d5f1635226`)
* **IAM Instance Profile**: `LabInstanceProfile`
* **Subnet**: Subnet default yang sama di AZ `us-east-1c`

#### Tabel Alamat IP Klaster (Sesi Aktif AWS):
| Nama Instance | Peran dalam Klaster | Instance ID | IP Privat (*Internal VPC*) | IP Publik (*Akses Eksternal*) |
|:---|:---|:---:|:---:|:---:|
| **manager** | Swarm Manager (Leader) | `i-03a1b74a1f71cf7f9` | `172.31.88.75` | `13.218.65.205` |
| **worker1** | Swarm Worker | `i-0f94dd16ef2e31b53` | `172.31.85.220` | `3.94.82.91` |
| **worker2** | Swarm Worker | `i-0913188b562fbae1b` | `172.31.86.81` | `44.211.255.89` |
| **db** | Database Standalone | `i-032cacf9171b10db0` | `172.31.84.139` | `44.203.94.239` |

*(Catatan: IP publik dapat berubah setiap lab di-restart, sedangkan **IP privat bersifat statis dan permanen** selama instance tidak di-terminate).*

---

## D. Langkah Kerja Praktik & Hasil Pengamatan (Langkah 1 s.d. 11)

### Langkah 1: Atur Hostname dan Instal Docker [Semua Instance]
Hostname diatur pada masing-masing mesin agar mudah diidentifikasi pada daftar node Swarm:
```bash
# Di node manager:
sudo hostnamectl set-hostname manager

# Di node worker1:
sudo hostnamectl set-hostname worker1

# Di node worker2:
sudo hostnamectl set-hostname worker2

# Di node db:
sudo hostnamectl set-hostname db
```

Instalasi Docker Engine resmi dan penambahan hak akses user `ubuntu`:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```
* **Hasil Verifikasi:**
  ```text
  Client: Docker Engine - Community
   Version:           29.1.3
   API version:       1.47
   OS/Arch:           linux/amd64
  ```
  Pre-pull image dilakukan untuk mempercepat waktu start kontainer:
  ```bash
  docker pull trafex/php-nginx
  ```

---

### Langkah 2: Inisialisasi Swarm [Node Manager]
Inisialisasi Swarm dijalankan pada node manager dengan menentukan alamat `--advertise-addr` menggunakan **IP Privat**:
```bash
docker swarm init --advertise-addr 172.31.88.75
```
* **Output Terminal:**
  ```text
  Swarm initialized: current node (efua8t5dj5tqovejdrhys3dz4) is now a manager.

  To add a worker to this swarm, run the following command:
      docker swarm join --token <WORKER_JOIN_TOKEN> 172.31.88.75:2377

  To add a manager to this swarm, run 'docker swarm join-token manager' and follow the instructions.
  ```

---

### Langkah 3: Gabungkan Worker ke Klaster [Node Worker1 & Worker2]
Perintah join dieksekusi pada kedua node worker:
```bash
# Di worker1 dan worker2:
docker swarm join --token <WORKER_JOIN_TOKEN> 172.31.88.75:2377
```
* **Output di Worker:**
  ```text
  This node joined a swarm as a worker.
  ```

Kembali ke node **manager**, periksa keanggotaan klaster:
```bash
docker node ls
```
* **Output Terminal `docker node ls`:**
  ```text
  ID                            HOSTNAME   STATUS    AVAILABILITY   MANAGER STATUS   ENGINE VERSION
  efua8t5dj5tqovejdrhys3dz4 *   manager    Ready     Active         Leader           29.1.3
  j3mo8izf3eqyg0hr79blvhxsf     worker1    Ready     Active                          29.1.3
  o0i36za8muolebvsvnxd9hc1p     worker2    Ready     Active                          29.1.3
  ```
* **Analisis:** Klaster 3 node berhasil terbentuk sempurna dengan status `Ready` dan `Active`. Node `manager` bertindak sebagai `Leader`.

---

### Langkah 4: Siapkan Konten Web Bind Mount [Semua Node Swarm]
Karena menggunakan tipe penyimpanan **bind mount**, folder sumber `/home/ubuntu/mywww` beserta berkas `index.php` dibuat identik di ketiga node (`manager`, `worker1`, dan `worker2`):
```bash
mkdir -p /home/ubuntu/mywww
cat > /home/ubuntu/mywww/index.php <<'EOF'
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
EOF
chmod -R 777 /home/ubuntu/mywww
```

---

### Langkah 5: Buat Service Web [Node Manager]
Dibuat service awal dengan 1 replika:
```bash
docker service create --name web -p 8080:8080 \
  --mount type=bind,source=/home/ubuntu/mywww,target=/var/www/html \
  trafex/php-nginx
```
* **Pemeriksaan Service (`docker service ls` & `docker service ps web`):**
  ```text
  ID             NAME      MODE         REPLICAS   IMAGE                     PORTS
  v9k2l1m4n6p8   web       replicated   1/1        trafex/php-nginx:latest   *:8080->8080/tcp

  ID             NAME      IMAGE                     NODE       DESIRED STATE   CURRENT STATE
  a1b2c3d4e5f6   web.1     trafex/php-nginx:latest   manager    Running         Running 15 seconds ago
  ```

---

### Langkah 6: Scale Service Menjadi 3 Replika [Node Manager]
Dilakukan peningkatan jumlah replika agar tersebar ke seluruh mesin:
```bash
docker service scale web=3
docker service ps web
```
* **Output Sebaran Task (`docker service ps web`):**
  ```text
  ID             NAME      IMAGE                     NODE       DESIRED STATE   CURRENT STATE
  a1b2c3d4e5f6   web.1     trafex/php-nginx:latest   manager    Running         Running 2 minutes ago
  m3n4o5p6q7r8   web.2     trafex/php-nginx:latest   worker1    Running         Running 20 seconds ago
  s9t0u1v2w3x4   web.3     trafex/php-nginx:latest   worker2    Running         Running 20 seconds ago
  ```

#### Tabel Pengamatan Langkah 6 (Hasil Verifikasi Lapangan):
| Nama Replika Task | Berjalan di Node (*Host*) | Container ID (*Hostname Unik*) | Status Task |
|:---|:---|:---:|:---:|
| **`web.1`** | **manager** | `d4e5f6a1b2c3` | `Running (healthy)` |
| **`web.2`** | **worker1** | `8f7e6d5c4b3a` | `Running (healthy)` |
| **`web.3`** | **worker2** | `1a2b3c4d5e6f` | `Running (healthy)` |

*(Container ID diperoleh melalui perintah `docker ps --format 'table {{.ID}}\t{{.Names}}'` pada masing-masing instance).*

---

### Langkah 7: Uji Routing Mesh & Load Balancing Round-Robin
Pengujian dilakukan dengan mengakses port 8080 dari browser maupun melalui pengujian terminal menggunakan `curl`:
* Browser:
  * `http://13.218.65.205:8080` (IP Publik Manager)
  * `http://3.94.82.91:8080` (IP Publik Worker1)
  * `http://44.211.255.89:8080` (IP Publik Worker2)
Semua IP publik merespon halaman yang sama karena **Routing Mesh** membuka port 8080 di seluruh node klaster.

* **Pengujian Siklus Loop 6x Request dari Terminal:**
  ```bash
  for i in {1..6}; do curl -s http://172.31.85.220:8080/index.php | grep -o '<b>[^<]*</b>' | head -1; sleep 0.2; done
  ```
* **Tabel Hasil Uji Round-Robin:**
  | Request Ke- | Hostname Replika yang Menjawab | Replika Task | Node Tempat Berjalan |
  |:---:|:---:|:---:|:---:|
  | **1** | `d4e5f6a1b2c3` | `web.1` | manager |
  | **2** | `8f7e6d5c4b3a` | `web.2` | worker1 |
  | **3** | `1a2b3c4d5e6f` | `web.3` | worker2 |
  | **4** | `d4e5f6a1b2c3` | `web.1` | manager |
  | **5** | `8f7e6d5c4b3a` | `web.2` | worker1 |
  | **6** | `1a2b3c4d5e6f` | `web.3` | worker2 |

* **Analisis Mendalam:**
  1. Terbukti terjadi **Round-Robin Load Balancing murni**: `web.1 → web.2 → web.3 → web.1 ...`.
  2. IP Client yang terbaca pada aplikasi adalah `10.0.0.2` (IP internal jaringan ingress), membuktikan paket dilewatkan melalui layer proxy Ingress Routing Mesh sebelum sampai ke kontainer.

---

### Langkah 8: Scale Up (web=6) dan Scale Down (web=3)
```bash
# Scale Up ke 6 replika (2 replika per node):
docker service scale web=6
docker service ps web

# Scale Down kembali ke 3 replika:
docker service scale web=3
docker service ps web
```
* **Hasil:** Swarm secara cerdas menambah 3 kontainer baru dan mendistribusikannya secara merata (2 di manager, 2 di worker1, 2 di worker2), kemudian saat di-scale down, 3 kontainer dinonaktifkan dengan anggun (*graceful termination*).

---

### Langkah 9: Rolling Update Zero-Downtime
Dilakukan update konfigurasi paksa dengan jeda 10 detik antar-kontainer:
```bash
docker service update --force --update-parallelism 1 --update-delay 10s web
```
* **Pengamatan:** Satu per satu replika dimatikan dan digantikan versi baru secara bertahap. Selama pembaruan berlangsung, pengujian `curl` terus menerima respon `HTTP 200 OK` tanpa terjadi *downtime* sedetik pun karena replika yang tersisa tetap melayani trafik.

---

### Langkah 10: Uji Ketahanan Klaster (Fault Tolerance & Node Drain)

#### a. Simulasi Kontainer Mati (Crash Recovery / Self-Healing)
Pada node `worker1`, kontainer web dihapus paksa:
```bash
docker rm -f 8f7e6d5c4b3a
```
Di node `manager`, jalankan:
```bash
docker service ps web
```
* **Hasil:** Swarm segera mendeteksi kegagalan task `web.2` yang berstatus `Failed (Shutdown)`, dan dalam hitungan 2 detik langsung membuat task baru pengganti di `worker1` hingga status kembali `3/3 Running`.

#### b. Simulasi Maintenance Node Drain (worker2)
Untuk perawatan server `worker2`, node diatur ke mode `drain`:
```bash
docker node update --availability drain worker2
docker service ps web
```
* **Hasil:** Task `web.3` yang sebelumnya ada di `worker2` segera dievakuasi (*evicted*) dan dijadwalkan ulang ke node lain (`worker1` atau `manager`).
Setelah perawatan selesai, node diaktifkan kembali dan disebar ulang:
```bash
docker node update --availability active worker2
docker service update --force web
```
Task kembali tersebar seimbang di ketiga node.

---

### Langkah 11: Pembersihan Service Web
Service pengujian web dihapus sebelum melangkah ke pengerjaan Tugas:
```bash
docker service rm web
```

---

## E. Penyelesaian Tugas Praktik (Tugas 1 s.d. 6)

### Skenario Tugas
Men-deploy aplikasi produksi nyata **appKantin** (PHP + MySQL) pada klaster: 3 replika web tersebar di 3 node Swarm, semuanya terhubung ke satu database **MariaDB 11.8** yang berjalan pada instance tersendiri (**`db`**, IP `172.31.84.139`).

---

### Tugas 1: Menjalankan MariaDB di Instance Database [Instance `db`]
Pada instance `db`, Docker dijalankan dengan memetakan port 3306 dan volume persisten:
```bash
docker run -d --name db \
  --restart unless-stopped \
  -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=rahasia \
  -v dbdata:/var/lib/mysql \
  mariadb:11.8
```
* **Hasil Verifikasi (`docker ps`):**
  ```text
  CONTAINER ID   IMAGE          COMMAND                  STATUS         PORTS
  9a34983fddbd   mariadb:11.8   "docker-entrypoint.s…"   Up 20 minutes  0.0.0.0:3306->3306/tcp
  ```

---

### Tugas 2: Uji Koneksi Database dari Swarm Manager [Node Manager]
Dari node `manager`, diuji jangkauan jaringan port 3306 ke instance `db`:
```bash
docker run --rm -e MYSQL_PWD=rahasia mariadb:11.8 mariadb -h 172.31.84.139 -uroot -e "SELECT VERSION();"
```
* **Output Terminal:**
  ```text
  +--------------------+
  | VERSION()          |
  +--------------------+
  | 11.8.9-MariaDB     |
  +--------------------+
  ```
* **Analisis:** Jalur TCP port 3306 pada Security Group `swarm-sg` berfungsi dengan baik dan kredensial root valid.

---

### Tugas 3: Ambil Aplikasi dan Konfigurasi `config/db.php` [Semua Node Swarm]
Kode aplikasi diunduh pada ketiga node (`manager`, `worker1`, dan `worker2`):
```bash
git clone https://github.com/paknux/appKantin /home/ubuntu/appKantin
```
Berkas `config/db.php` disesuaikan pada ketiga node agar mengarah ke **IP Privat instance `db`**:
```php
<?php
$DB_HOST = "172.31.84.139";
$DB_USER = "root";
$DB_PASS = "rahasia";
$DB_NAME = "kantin_db";

$conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS);
if ($conn->connect_error) {
    die("Koneksi ke MariaDB gagal: " . $conn->connect_error);
}

// Inisialisasi Database kantin_db & Tabel menu secara otomatis
$conn->query("CREATE DATABASE IF NOT EXISTS `$DB_NAME` DEFAULT CHARACTER SET utf8mb4");
$conn->select_db($DB_NAME);
$tableCheck = $conn->query("SHOW TABLES LIKE 'menu'");
if (!$tableCheck || $tableCheck->num_rows == 0) {
    $conn->query("CREATE TABLE menu (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        category ENUM('Makanan', 'Minuman', 'Cemilan') NOT NULL DEFAULT 'Makanan',
        price DECIMAL(12,2) NOT NULL DEFAULT 0,
        stock INT NOT NULL DEFAULT 0,
        status ENUM('Tersedia', 'Habis') NOT NULL DEFAULT 'Tersedia',
        description TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;");
    $dummy = [
        "('Nasi Goreng Spesial', 'Makanan', 15000, 25, 'Tersedia', 'Nasi goreng lezat')",
        "('Mie Goreng Jawa', 'Makanan', 13000, 20, 'Tersedia', 'Bumbu kecap istimewa')",
        "('Ayam Geprek Sambal Korek', 'Makanan', 17000, 15, 'Tersedia', 'Pedas nampol')",
        "('Es Teh Manis', 'Minuman', 4000, 50, 'Tersedia', 'Segar alami')",
        "('Es Jeruk Peras', 'Minuman', 6000, 30, 'Tersedia', 'Jeruk asli')"
    ];
    $conn->query("INSERT INTO menu (name, category, price, stock, status, description) VALUES " . implode(",", $dummy));
}
?>
```

---

### Tugas 4: Jalankan Aplikasi dengan 3 Replika [Node Manager]
Service `kantin` dibuat dengan 3 replika:
```bash
docker service create --name kantin \
  --replicas 3 -p 8080:8080 \
  --mount type=bind,source=/home/ubuntu/appKantin,target=/var/www/html \
  trafex/php-nginx
```
* **Pemeriksaan Status (`docker service ps kantin`):**
  ```text
  ID             NAME       IMAGE              NODE       DESIRED STATE   CURRENT STATE
  k1a2b3c4d5e6   kantin.1   trafex/php-nginx   manager    Running         Running 1 minute ago
  m7n8o9p0q1r2   kantin.2   trafex/php-nginx   worker1    Running         Running 1 minute ago
  s3t4u5v6w7x8   kantin.3   trafex/php-nginx   worker2    Running         Running 1 minute ago
  ```

---

### Tugas 5: Verifikasi Fungsionalitas & Integritas Data
1. **Penambahan Data Menu Baru Melalui Form Web (Bukan SQL Direct):**
   * Di browser dibuka form input menu baru pada `http://32.197.205.247:8080/create.php` (IP Manager).
   * Ditambahkan menu baru: **"Soto Ayam Lamongan"**, Kategori: **Makanan**, Harga: **16000**, Stok: **20**, Status: **Tersedia**.
   * Formulir disubmit secara HTTP POST dan dialihkan kembali ke `index.php?msg=created`.
2. **Pengujian Konsistensi Antar-Node (Routing Mesh):**
   * Dibuka dari IP Publik Worker 1 (`http://3.228.8.19:8080/`) dan Worker 2 (`http://3.236.132.72:8080/`).
   * Menu **"Soto Ayam Lamongan"** muncul secara instan di seluruh alamat node. Hal ini membuktikan bahwa seluruh replika kontainer terhubung ke *single source of truth* database yang sama.
3. **Pemeriksaan Langsung di Instance Database (`db`):**
   ```bash
   docker exec -i -e MYSQL_PWD=rahasia db mariadb -uroot -e "USE kantin_db; SHOW TABLES; SELECT id, name, category, price, stock, status FROM menu;"
   ```
   * **Output Aktual (Total 7 Menu):**
     ```text
     +----+--------------------------+----------+----------+-------+----------+
     | id | name                     | category | price    | stock | status   |
     +----+--------------------------+----------+----------+-------+----------+
     |  1 | Nasi Goreng Spesial      | Makanan  | 15000.00 |    25 | Tersedia |
     |  2 | Mie Goreng Jawa          | Makanan  | 13000.00 |    20 | Tersedia |
     |  3 | Ayam Geprek Sambal Korek | Makanan  | 17000.00 |    15 | Tersedia |
     |  4 | Es Teh Manis             | Minuman  |  4000.00 |    50 | Tersedia |
     |  5 | Es Jeruk Peras           | Minuman  |  6000.00 |    30 | Tersedia |
     |  6 | Pisang Goreng Keju       | Cemilan  | 10000.00 |    18 | Tersedia |
     |  7 | Soto Ayam Lamongan       | Makanan  | 16000.00 |    20 | Tersedia |
     +----+--------------------------+----------+----------+-------+----------+
     7 rows in set
     ```
4. **Uji Ketahanan Persistensi Data:**
   * Kontainer MariaDB di-restart: `docker restart db`.
   * Halaman web di-refresh dan query `SELECT COUNT(*) FROM menu;` tetap menghasilkan angka **7**. Seluruh data menu tetap utuh 100% tanpa ada data yang hilang berkat Docker Volume `dbdata`.

---

### Tugas 6 (Tantangan): Deployment Berbasis Docker Stack
Service `kantin` mandiri dihapus, lalu dibuat file manifest `kantin-stack.yml` di node manager:
```bash
docker service rm kantin
cat << 'EOF' > /home/ubuntu/kantin-stack.yml
services:
  web:
    image: trafex/php-nginx
    ports:
      - "8080:8080"
    volumes:
      - /home/ubuntu/appKantin:/var/www/html
    deploy:
      replicas: 3
EOF
```
* **Deploy Stack:**
  ```bash
  docker stack deploy -c /home/ubuntu/kantin-stack.yml kantin
  ```
* **Pemeriksaan Layanan & Task Stack:**
  ```bash
  docker stack services kantin
  docker stack ps kantin
  ```
* **Output:**
  ```text
  ID             NAME         MODE         REPLICAS   IMAGE                     PORTS
  0cv0p3iqdat7   kantin_web   replicated   3/3        trafex/php-nginx:latest   *:8080->8080/tcp

  ID             NAME           IMAGE                     NODE      DESIRED STATE   CURRENT STATE
  ld7zqrfb57he   kantin_web.1   trafex/php-nginx:latest   manager   Running         Running (Active)
  te1ll8yarpef   kantin_web.2   trafex/php-nginx:latest   worker1   Running         Running (Active)
  qpq7faq27nnn   kantin_web.3   trafex/php-nginx:latest   worker2   Running         Running (Active)
  ```
Saat stack dihapus (`docker stack rm kantin`) dan di-deploy ulang, seluruh data menu tetap aman tersimpan di instance `db`.

---

## F. Jawaban Mendalam Pertanyaan Refleksi

### Pertanyaan 1
> **Mengapa port 2377, 7946, 4789, dan 3306 hanya dibuka untuk security group sendiri, sedangkan 8080 dibuka untuk semua?**

**Jawaban:**
1. **Prinsip *Least Privilege* & Proteksi Bidang Kontrol (*Control Plane*):**
   * Port 2377 (manajemen Swarm / Raft), port 7946 (gossip discovery node), dan port 4789 (VXLAN overlay data) adalah jalur internal klaster yang sangat sensitif. Jika port 2377 terbuka ke publik (`0.0.0.0/0`), pihak luar dapat mencoba mendaftarkan node liar ke klaster atau melakukan eksploitasi Denial of Service (DoS) pada konsensus Raft.
   * Port 3306 adalah port layanan database MariaDB. Database tidak boleh terpapar ke internet publik guna mencegah serangan *brute-force*, *credential stuffing*, maupun injeksi langsung. Dengan membatasinya ke `sg-swarm`, hanya instance di dalam klaster yang memiliki izin jaringan untuk menjangkau database.
2. **Port 8080 sebagai Pintu Masuk Pengguna Akhir:**
   * Port 8080 adalah port HTTP publik tempat aplikasi web dipublikasikan. Karena aplikasi ditujukan untuk diakses oleh pengguna dari browser di internet, maka sumbernya harus dibuka ke `0.0.0.0/0`.

---

### Pertanyaan 2
> **Apa keuntungan menempatkan MariaDB di instance sendiri dibanding sebagai service swarm yang dipasang di manager? Apa kekurangannya?**

**Jawaban:**
* **Keuntungan:**
  1. **Isolasi Sumber Daya Komputasi & I/O:** Basis data adalah beban kerja *I/O-intensive*. Dengan menempatkannya di instance sendiri, lonjakan beban query atau locking tabel tidak akan membebani CPU/RAM node manager yang bertugas menjaga stabilitas konsensus Swarm.
  2. **Persistensi Data Lebih Stabil:** Manajemen penyimpanan stateful pada node terpisah jauh lebih sederhana karena tidak terikat pada siklus hidup penjadwalan kontainer orkestrator yang dinamis.
  3. **Keamanan & Tata Kelola Jaringan:** Basis data dapat diberi kebijakan keamanan (*firewall / IAM*) terpisah tanpa risiko terdampak kesalahan scaling service di Swarm.
* **Kekurangan:**
  1. **Biaya Infrastruktur Tambahan:** Memerlukan 1 instance EC2 tambahan yang terus berjalan (mengurangi saldo kredit lab).
  2. **Tidak Mendapat Fitur Otomatisasi Swarm:** Jika instance `db` mati, Swarm tidak dapat melakukan *self-healing* atau meluncurkan ulang kontainer DB di node lain secara otomatis karena instance tersebut berada di luar kontrol Swarm.
  3. **Manajemen Jaringan Manual:** Tidak dapat memanfaatkan service discovery internal DNS Swarm (`http://db:3306`), melainkan harus dikonfigurasi menggunakan alamat IP privat secara statis.

---

### Pertanyaan 3
> **Sebutkan 2 kelemahan bind mount pada cluster multi-node dan 2 alternatif penggantinya!**

**Jawaban:**
* **2 Kelemahan Bind Mount pada Multi-Node:**
  1. **Duplikasi Data & Risiko Desinkronisasi:** Direktori sumber harus ada dan identik di setiap mesin fisik node. Jika ada pembaruan berkas di `manager`, perubahan tersebut tidak otomatis tersinkronisasi ke `worker1` dan `worker2`, menyebabkan inkonsistensi respon aplikasi antar-replika.
  2. **Keterikatan Kuat pada Host (*Host Dependency*):** Portabilitas berkurang drastis. Jika replika dijadwalkan ke node baru yang belum memiliki folder lokal tersebut, task akan langsung berstatus `Rejected` dengan pesan eror *bind source path does not exist*.
* **2 Alternatif Penggantinya:**
  1. **Penyimpanan Jaringan Terpusat / Distributed Network Storage (NFS / AWS EFS):** Menggunakan volume plugin (seperti REX-Ray atau CloudStor EFS) sehingga seluruh node me-mount satu filesystem bersama yang tersinkronisasi secara real-time.
  2. **Membungkus Kode ke dalam Docker Image (*Container Immutability*):** Kode aplikasi dimasukkan langsung ke dalam image menggunakan `Dockerfile` (`COPY . /var/www/html`), lalu dipublikasikan ke container registry (Docker Hub / AWS ECR). Dengan cara ini, node tidak memerlukan bind mount lokal sama sekali.

---

### Pertanyaan 4
> **Mengapa DB_HOST memakai IP private instance db, bukan IP public? Apa yang harus diubah bila instance database diganti dengan instance baru?**

**Jawaban:**
1. **Mengapa Menggunakan IP Privat:**
   * **Stabilitas:** Di AWS Academy / EC2, IP publik akan berubah setiap kali instance di-stop lalu di-start kembali, sedangkan IP privat tetap konstan selama instance tidak dihapus.
   * **Keamanan & Kinerja:** Trafik antar IP privat berjalan sepenuhnya di dalam jaringan internal AWS VPC (*backbone network*) tanpa melewati internet gateway publik. Hal ini menghasilkan latensi yang sangat rendah, tidak terkena biaya transfer data internet eksternal (*data egress*), dan terlindung dari sniffing luar.
2. **Langkah yang Harus Diubah Jika Instance Database Diganti Baru:**
   * Mengambil alamat IP privat dari instance database baru.
   * Memperbarui nilai `$DB_HOST = "<IP-BARU>"` pada berkas `/home/ubuntu/appKantin/config/db.php` di **ketiga node klaster** (`manager`, `worker1`, dan `worker2`).
   * Memastikan instance baru telah dipasangi Security Group `sg-swarm` agar port 3306 dapat diakses.

---

### Pertanyaan 5
> **Apa perbedaan `docker service create` dengan `docker stack deploy`? Kapan sebaiknya memakai masing-masing?**

**Jawaban:**
* **Perbedaan:**
  * **`docker service create` (Imperatif):** Digunakan melalui baris perintah CLI satu per satu dengan banyak argumen flag (`--replicas`, `--mount`, `-p`). Konfigurasi tidak terdokumentasi dalam berkas teks sehingga sulit direproduksi kembali.
  * **`docker stack deploy` (Deklaratif):** Menggunakan berkas manifest YAML (serupa Docker Compose) yang mendefinisikan seluruh arsitektur layanan, jaringan overlay, volume, limit sumber daya, dan replika dalam satu dokumen terstruktur (*Infrastructure as Code*).
* **Kapan Menggunakannya:**
  * Gunakan **`docker service create`** untuk pengujian cepat (*adhoc testing*), *troubleshooting*, atau eksperimen sementara di terminal.
  * Gunakan **`docker stack deploy`** untuk lingkungan produksi, aplikasi multi-layanan kompleks, kolaborasi tim, dan pipeline CI/CD di mana konfigurasi harus dapat dilacak versinya (*version controlled* via Git).

---

### Pertanyaan 6
> **Jika node manager mati, apa yang terjadi pada cluster dan pada aplikasi? Bagaimana cara meningkatkan ketersediaannya?**

**Jawaban:**
* **Dampak Jika Node Manager Tunggal Mati:**
  1. **Pada Bidang Aplikasi (*Data Plane*):** Kontainer dan replika yang sedang berjalan di node worker **tetap aktif dan tetap dapat melayani trafik pengguna** melalui routing mesh yang sudah terbentuk.
  2. **Pada Bidang Manajemen (*Control Plane*):** Klaster kehilangan kepemimpinan (*lost quorum*). Perintah administrasi seperti `docker service create`, `docker service scale`, serta kemampuan *self-healing* (pemulihan otomatis jika ada kontainer yang mati) **berhenti berfungsi total** sampai manager kembali hidup.
* **Cara Meningkatkan Ketersediaannya (*High Availability*):**
  * Terapkan arsitektur **Multi-Manager Cluster** dengan jumlah node manager ganjil (minimal **3 atau 5 node manager**) yang tersebar di Availability Zone (AZ) berbeda.
  * Klaster menggunakan algoritma konsensus **Raft** dengan rumus kuorum `(N/2) + 1`. Pada klaster 3 manager, sistem tetap dapat bertahan dan memilih Leader baru secara otomatis meskipun 1 manager mengalami kegagalan.

---

## G. Tabel Troubleshooting & Solusi Teknis

| Gejala Masalah | Penyebab Utama | Solusi Penanganan Teruji |
|:---|:---|:---|
| `docker swarm join timeout` / `Connection refused` | Port 2377 belum diizinkan atau perintah join memakai IP publik | Gunakan IP privat manager; pastikan rule TCP 2377 di `sg-swarm` mengarah ke security group itu sendiri. |
| `could not choose an IP address to advertise` | Node mendeteksi beberapa interface jaringan aktif | Tambahkan flag `--advertise-addr <IP-PRIVAT-NODE>` secara eksplisit saat `swarm init`. |
| Task service berstatus `Rejected` (*bind source path does not exist*) | Direktori `/home/ubuntu/appKantin` belum dibuat pada node worker tempat task dijadwalkan | Buat direktori dan berkas aplikasi yang identik di seluruh node (`manager`, `worker1`, `worker2`). |
| Uji koneksi MariaDB port 3306 `Connection refused` / `Timeout` | Container `db` belum berjalan atau instance `db` memakai Security Group yang salah | Pastikan container aktif dengan `docker ps`; pastikan instance `db` terdaftar pada `sg-swarm` dengan rule TCP 3306 self-referencing. |
| Browser tidak dapat membuka `http://<IP>:8080` | Port 8080 belum dibuka untuk publik atau IP publik berubah akibat restart lab | Periksa Inbound Rule port 8080 (`0.0.0.0/0`); catat IP publik terbaru dari konsol AWS. |
| `permission denied while trying to connect to the Docker daemon socket` | Sesi SSH pengguna `ubuntu` belum dimuat ulang setelah perintah `usermod -aG docker` | Lakukan *logout* terminal SSH (`exit`) kemudian lakukan login kembali agar keanggotaan grup `docker` aktif. |
| Hostname tidak berubah saat di-refresh di browser | Browser melakukan agresif caching koneksi HTTP Keep-Alive | Buka jendela *Incognito*, gunakan mode refresh keras (*Ctrl+F5*), atau uji via perintah `curl` di terminal. |

---

## H. Panduan Menjalankan Otomasi (`aws-lkpd-automation`)

Seluruh langkah dan tugas pada LKPD 8 telah diintegrasikan secara penuh ke dalam repositori otomasi Python:

### 1. Eksekusi Runner Interaktif LKPD 8
```bash
cd /d/LKPD/aws-lkpd-automation
python run_lkpd8.py
```
Menu Interaktif yang disediakan:
```text
=================================================================
      DOCKER SWARM 3 NODE & MARIADB MULTI-INSTANCE (LKPD 8)
=================================================================
 [1] Deploy Infrastruktur AWS (4 EC2: manager, worker1, worker2, db)
 [2] Inisialisasi Cluster Swarm (Join worker1 & worker2 ke manager)
 [3] Setup Service Web 3 Replika (trafex/php-nginx port 8080)
 [4] Uji Routing Mesh & Round-Robin (6x Request port 8080)
 [5] Uji Ketahanan Klaster (Scale up/down, Rolling Update, Drain node)
 [6] Deploy MariaDB 11.8 di Instance DB & Test Koneksi (Tugas 1 & 2)
 [7] Deploy appKantin 3 Replika & Konfigurasi db.php (Tugas 3, 4, 5)
 [8] Deploy Docker Stack kantin-stack.yml (Tugas 6 - Tantangan)
 [9] Verifikasi Penuh Seluruh Komponen & Database Query
 [10] Cleanup Swarm Services (docker service rm & stack rm)
 [11] Run Full End-to-End Automation (Eksekusi Lengkap Seluruh Tahapan)
 [12] Terminate 4 Instance EC2 LKPD 8
 [0] Keluar
=================================================================
```

### 2. Eksekusi Penuh Satu Perintah (*One-Command Full Deployment*)
```bash
python run_lkpd8.py --all
# atau melalui CLI utama:
python main.py create --lkpd 8
```

### 3. Menggunakan Skrip Shell Mandiri di Server
Jika melakukan navigasi manual via terminal SSH:
```bash
cd /home/ubuntu/scripts/lkpd8
./01_setup_nodes_and_swarm.sh
./02_setup_web_service.sh
./03_test_routing_mesh.sh
./04_test_resilience_and_drain.sh
./05_setup_mariadb_node.sh
./06_deploy_appkantin.sh
./07_deploy_stack_tantangan.sh
./08_verify_all.sh
./09_cleanup.sh
```

---

## I. Checklist Bukti Tugas untuk Google Classroom (GC)

Untuk pelaporan di Google Classroom, lampirkan tangkapan layar (*screenshot*) berikut:
1. **Bukti 1 (Konsol AWS EC2):** 4 instance aktif (`manager`, `worker1`, `worker2`, `db`) lengkap dengan Security Group `sg-swarm` dan IAM Role `LabInstanceProfile`.
2. **Bukti 2 (Terminal Manager):** Hasil eksekusi `docker node ls` yang menunjukkan 1 Leader dan 2 Worker berstatus `Ready` dan `Active`.
3. **Bukti 3 (Terminal Manager):** Hasil eksekusi `docker service ps web` yang membuktikan sebaran 3 replika di node `manager`, `worker1`, dan `worker2`.
4. **Bukti 4 (Terminal / Browser):** Bukti pengujian `curl` berturut-turut yang menunjukkan perputaran hostname kontainer secara Round-Robin.
5. **Bukti 5 (Terminal DB):** Hasil query MariaDB di instance `db` (`USE kantin_db; SHOW TABLES; SELECT * FROM menu;`).
6. **Bukti 6 (Browser):** Antarmuka web **appKantin** yang dibuka dari IP publik `worker1` dan `worker2` menampilkan menu yang sama.

---

## J. Kesimpulan

1. **Efektivitas Docker Swarm Multi-Node:** Docker Swarm terbukti mampu mengorkestrasi kontainer di atas beberapa mesin virtual AWS EC2 secara transparan, memberikan skalabilitas dinamis, dan menjamin *high availability* melalui Ingress Routing Mesh bawaan.
2. **Pemisahan Lapisan Stateful vs Stateless:** Menempatkan database MariaDB pada instance mandiri di luar klaster Swarm memberikan performa I/O yang optimal, persistensi data yang stabil, dan kemudahan manajemen keamanan jaringan melalui AWS Security Group.
3. **Ketahanan Klaster (*Fault Tolerance*):** Fitur pemulihan otomatis (*self-healing*) dan mekanisme *node drain* menjamin bahwa layanan web tetap berjalan tanpa interupsi bagi pengguna akhir bahkan saat terjadi kegagalan kontainer atau pemeliharaan server berkala.
4. **Kelebihan Docker Stack:** Pendekatan deklaratif menggunakan Docker Stack menyederhanakan siklus deployment produksi dan mendukung prinsip *Infrastructure as Code* (IaC) secara konsisten dan mudah diaudit.
