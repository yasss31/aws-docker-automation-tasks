# AWS Docker & Docker Swarm Automation Tasks 🚀

Selamat datang di repository **AWS Docker & Docker Swarm Automation Tasks**! Repository ini dirancang khusus untuk mempermudah siapa saja—termasuk **pemula yang baru belajar cloud computing, Docker, dan DevOps**—dalam mempraktikkan kontainerisasi dan orkestrasi aplikasi secara otomatis di atas infrastruktur cloud **Amazon Web Services (AWS EC2 & AWS Academy Learner Lab)**.

Proyek ini menyatukan seluruh modul praktikum **LKPD 1 hingga LKPD 8** (Dasar Docker, Multi-Container, Dockerfile, Docker Hub, Docker Compose, serta **Docker Swarm Single-Node & Multi-Node Cluster**) dan **Tugas Aplikasi Produksi (Tugas 2 App ID Card & Tugas 3 HAProxy Load Balancing)** ke dalam satu framework CLI otomasi terpadu berbasis **Python (Boto3)**, **Cloud-Init (User Data)**, dan **Modular Shell Scripts**.

---

## 📚 Modul & Lembar Kerja Peserta Didik (LKPD)

Seluruh dokumen materi panduan resmi tersedia dalam format PDF di folder [`docs/pdf/`](docs/pdf/). Laporan praktikum komprehensif tersedia di folder [`docs/reports/`](docs/reports/). Berikut adalah penjelasan cerita dan kompetensi di balik setiap modul:

### 1. [LKPD 1 - Dasar Docker dan Web Server HTTP](docs/pdf/LKPD%201%20-%20Dasar%20Docker.pdf)
* **Kisah & Tujuan**: Memulai langkah pertama di dunia kontainer. Anda diajak memahami arsitektur daemon Docker pada Linux Ubuntu, perintah lifecycle kontainer (`pull`, `run`, `ps`, `stop`, `rm`), teknik port binding (`-p 8080:80`), dan volume mounting dari host ke kontainer (`-v /var/mywww:/var/www/html`).
* **Hasil Akhir**: Web server Apache HTTPD berjalan di container dan melayani halaman web di port **8080**.

### 2. [LKPD 2 - Deploy Aplikasi PHP dan MySQL (Multi-Container)](docs/pdf/LKPD%202%20-%20Deploy%20App%20Multi%20Container.pdf)
* **Kisah & Tujuan**: Aplikasi modern tidak pernah menyatukan kode PHP dan database MySQL dalam satu mesin monolitik. Di LKPD 2, kita memisahkan arsitektur menjadi dua kontainer terisolasi: `webserver` (AppToko PHP) dan `dbserver` (`mariadb:11-jammy`).
* **Konsep Kunci**: Custom bridge network (`mynet`) agar kedua kontainer bisa saling berkomunikasi menggunakan nama hostname internal (`dbserver:3306`) tanpa membuka port database ke internet publik.
* **Hasil Akhir**: Aplikasi AppToko berjalan terhubung dengan database di port **8088**.

### 3. [LKPD 3 - Membangun Image dengan Dockerfile](docs/pdf/LKPD%203%20-%20Dockerfile.pdf)
* **Kisah & Tujuan**: Membuat kontainer manual dengan `docker commit` memiliki kelemahan: tidak terdokumentasi dan sulit diulang (*reproducible*). Di LKPD 3, kita mempelajari **Infrastructure as Code (IaC)** untuk kontainer menggunakan `Dockerfile`.
* **Konsep Kunci**: Penggunaan instruksi `FROM ubuntu:24.04`, `ENV`, `RUN apt update && apt install ...`, `EXPOSE 80`, dan `CMD ["apache2ctl", "-D", "FOREGROUND"]`.
* **Hasil Akhir**: Image buatan sendiri `ubuntu-ws:v1` yang siap menjalankan aplikasi web di port **8001**.

### 4. [LKPD 4 - Publikasi Docker Image ke Docker Hub](docs/pdf/LKPD%204%20-%20Publikasi%20Docker%20Image%20ke%20Docker%20Hub.pdf)
* **Kisah & Tujuan**: Image yang sudah kita bangun di LKPD 3 perlu dibagikan ke tim pengembang lain atau server produksi. Kita menghubungkan terminal server dengan registri publik **Docker Hub**.
* **Konsep Kunci**: Autentikasi CLI (`docker login`), penamaan tag sesuai namespace (`username/ubuntu-ws:v1`), proses `docker push`, pengujian hapus image lokal (`docker rmi`), dan membuktikan image dapat di-pull ulang dari internet lalu dijalankan di port **8002**.
* **Hasil Akhir**: Kontainer `webserver2` live menggunakan image dari Docker Hub di port **8002**.

### 5. [LKPD 5 - Multi-Container Orchestration dengan Docker Compose](docs/pdf/LKPD%205%20-%20Docker%20Compose.pdf)
* **Kisah & Tujuan**: Mengetik puluhan perintah `docker run` dengan banyak parameter flags sangat rawan kesalahan manusia (*human error*). Solusinya adalah **Docker Compose**: satu file deklaratif `docker-compose.yml` untuk mengelola seluruh stack aplikasi (web, database, volume, network).
* **Konsep Kunci**: Struktur file Compose (`version`, `services`, `environment`, `depends_on`, `volumes`), dan perintah manajemen `docker compose up -d`, `docker compose ps`, dan `docker compose down`.
* **Hasil Akhir**: Orkestrasi multi-kontainer otomatis berjalan rapi di port **8088**.

### 6. Tugas 2 - Aplikasi ID Card (Docker Compose)
* **Kisah & Tujuan**: Praktik deployment aplikasi formulir dan pencetak kartu identitas siswa ([paknux/appIDcard](https://github.com/paknux/appIDcard)).
* **Stack**: Docker Compose, PHP webserver, MariaDB 11, auto database configuration (`konfig.php`), melayani di port **8080**.

### 7. Tugas 3 - Aplikasi Reservasi Ruangan (HAProxy Load Balancer + 2 Webservers + 1 Database)
* **Kisah & Tujuan**: Deployment aplikasi reservasi ruangan rapat dan fasilitas hotel ([paknux/appReservasi](https://github.com/paknux/appReservasi)) dengan arsitektur *High Availability & Load Balancing*.
* **Arsitektur (Total 4 Kontainer)**:
  - **`haproxy`**: Load balancer / reverse proxy publik (`haproxy:latest`) yang menerima trafik HTTP di port **8083** dan membagi beban ke backend dengan algoritma `roundrobin`.
  - **`webserver1`**: Kontainer Apache + PHP 8.2 + PDO MySQL (port 80 internal).
  - **`webserver2`**: Kontainer Apache + PHP 8.2 + PDO MySQL (port 80 internal) menggunakan image yang sama.
  - **`dbserver`**: Database `mariadb:11-jammy` (port 3306 internal) dengan volume persistent `db_data` dan auto-import `reservasi_ruangan.sql`.
* **Hasil Akhir**: Akses publik aman satu pintu melalui HAProxy di port **8083**, beban trafik didistribusikan bergantian ke `webserver1` dan `webserver2`.
* **Dokumentasi & Tutorial Lengkap**: Lihat panduan artikel Medium di [`docs/articles/TUGAS_3_MEDIUM_ARTICLE.md`](docs/articles/TUGAS_3_MEDIUM_ARTICLE.md).

### 8. [LKPD 6 - Pengantar Konsep Docker Swarm (Multi-Node Cluster)](docs/pdf/LKPD%206%20-%20Pengantar%20Konsep%20Docker%20Swarm.pdf)
* **Kisah & Tujuan**: Mengelola kontainer pada skala multi-server membutuhkan orkestrator tangguh. Pada LKPD 6, kita membangun klaster 2-node di atas AWS EC2: **1 Manager Node** dan **1 Worker Node**.
* **Konsep Kunci**: Inisialisasi Swarm (`docker swarm init`), worker joining via token (`docker swarm join --token ...`), pembuatan service dengan multi-replika (`docker service create --replicas 3`), horizontal scaling (`docker service scale web=5`), serta pembuktian kemampuan pemulihan mandiri (**self-healing**) saat kontainer dihentikan paksa.
* **Hasil Akhir & Laporan**: Klaster aktif teruji fault-tolerant di port **8080**. Baca selengkapnya di [`docs/reports/LKPD_6_DOCKER_SWARM_REPORT.md`](docs/reports/LKPD_6_DOCKER_SWARM_REPORT.md).

### 9. [LKPD 7 - Docker Swarm Single Node & Deployment appKantin](docs/pdf/LKPD%207%20-%20Docker%20Swarm%20Single%20Node.pdf)
* **Kisah & Tujuan**: Memahami orkestrasi internal Swarm pada single host: ingress routing mesh, persistent bind mounts, multi-replika PHP Nginx (`trafex/php-nginx`), serta integrasi dengan kontainer database MariaDB untuk aplikasi nyata **appKantin** ([paknux/appKantin](https://github.com/paknux/appKantin)).
* **Konsep Kunci**: Port routing mesh internal 8080:8080, pembagian trafik round-robin antar replika, konfigurasi otomatis `config/db.php`, dan impor database menu kantin.
* **Hasil Akhir & Laporan**: Aplikasi appKantin melayani di port **8080** dengan database terhubung. Baca selengkapnya di [`docs/reports/LKPD_7_DOCKER_SWARM_REPORT.md`](docs/reports/LKPD_7_DOCKER_SWARM_REPORT.md).

### 10. [LKPD 8 - Docker Swarm 3 Node Cluster & Dedicated MariaDB di AWS Academy](docs/pdf/LKPD%208%20-%20Docker%20Swarm%203%20Node%20AWS%20Academy.pdf)
* **Kisah & Tujuan**: Standar industri memisahkan layer stateless (aplikasi web klaster) dan layer stateful (database server terisolasi). Di LKPD 8, kita mengorkestrasi **4 instance EC2 Ubuntu 24.04** di AWS Academy Learner Lab:
  - **1 Swarm Manager** (`swarm-manager`)
  - **2 Swarm Workers** (`swarm-worker1`, `swarm-worker2`)
  - **1 Dedicated Database Server** (`swarm-db` MariaDB 11.8)
* **Fitur Utama**: Ingress Routing Mesh round-robin lintas node fisik, uji ketahanan node maintenance dengan `docker node update --availability drain`, deployment deklaratif via **Docker Stack** ([`kantin-stack.yml`](kantin-stack.yml)), dan verifikasi koneksi SQL via private IP AWS VPC.
* **Hasil Akhir & Laporan**: Klaster 3-node enterprise-ready melayani di port **8080**. Baca selengkapnya di [`docs/reports/LKPD_8_DOCKER_SWARM_REPORT.md`](docs/reports/LKPD_8_DOCKER_SWARM_REPORT.md).

---

## 🧭 Tutorial Step-by-Step untuk Pemula

Panduan ini disusun langkah demi langkah agar Anda dapat langsung menjalankannya dari laptop/komputer Anda:

### Langkah 1: Klon Repositori & Persiapan Python
Buka terminal (Git Bash, Command Prompt, atau PowerShell), lalu jalankan:
```bash
# 1. Clone repository ini
git clone https://github.com/yasss31/aws-docker-automation-tasks.git
cd aws-docker-automation-tasks

# 2. Instal library Python yang dibutuhkan
pip install -r requirements.txt
```

---

### Langkah 2: Menyiapkan Kredensial AWS di File `.env`
1. Gandakan file `.env.example` menjadi `.env`:
   ```bash
   # Di Linux / macOS:
   cp .env.example .env

   # Di Windows PowerShell:
   Copy-Item .env.example .env
   ```
2. Buka file `.env` menggunakan teks editor (misal VS Code atau Notepad).
3. Jika Anda menggunakan **AWS Academy Learner Lab**:
   - Buka halaman lab AWS Academy Anda.
   - Klik tombol **AWS Details**, lalu lihat bagian **AWS CLI**.
   - Salin dan tempelkan nilainya ke `.env`:
     ```ini
     AWS_REGION=us-east-1
     AWS_ACCESS_KEY_ID=ASIA...
     AWS_SECRET_ACCESS_KEY=...
     AWS_SESSION_TOKEN=IQoJ...
     ```
   *(Catatan: Token sesi AWS Academy bersifat sementara dan perlu diperbarui jika sesi lab dimulai ulang).*

---

### 🩺 Langkah 2.1: Audit & Diagnosa Kredensial Otomatis (AWS Doctor)
Jika Anda baru memperbarui kredensial dari Cloud Labs / AWS Academy atau ingin memastikan AWS CLI, boto3, region `us-east-1`, serta izin IAM/SSM sinkron dan sehat tanpa mengganggu server yang sedang berjalan:
```bash
python main.py aws-doctor --repair --verify
```
Fitur ini akan:
1. **Audit Mendalam**: Memeriksa konsistensi antara `~/.aws/credentials`, `.env` proyek, dan environment variables.
2. **Safe Auto-Repair**: Menyelaraskan region `us-east-1` dan menyinkronkan kredensial yang valid dengan backup otomatis (`.bak`), tanpa menimpa variabel proyek lainnya.
3. **Keamanan File Kunci SSH**: Mengamankan izin ACL NTFS file private key (`vockey.pem` dan `labsuser.pem`) ke `Read-Only` khusus akun user.
4. **Validasi Izin API**: Menguji izin STS, EC2, SSM, dan IAM (`LabInstanceProfile`).
5. **Audit Runtime EC2 & SSM**: Membedakan masalah kredensial lokal dari masalah IAM Instance Profile, SSM Agent offline, atau jaringan.
6. **Live Verification**: Menguji eksekusi remote command ke instance aktif melalui AWS Systems Manager.

---

### Langkah 3: Melakukan Pre-Flight Validation
Sebelum membuat mesin EC2 nyata di cloud, jalankan validasi otomatis untuk memastikan akun AWS dan konfigurasi sudah valid:
```bash
python main.py validate
```
Skrip ini akan memeriksa:
- [x] Koneksi STS AWS
- [x] Default VPC & Subnet
- [x] Ketersediaan AMI Ubuntu 24.04 LTS
- [x] Key Pair `vockey`
- [x] IAM Instance Profile `LabInstanceProfile`
- [x] Sinkronisasi Security Group `lkpd-docker-sg`

Jika muncul pesan `SEMUA VALIDASI BERHASIL!`, lingkungan siap digunakan!

---

### Langkah 4: Meluncurkan Praktikum / Tugas Pilihan

Anda dapat memilih tugas mana yang ingin dibuatkan server EC2-nya secara otomatis:

#### Ingin Menjalankan Tugas 3 (Aplikasi Reservasi Ruangan)?
```bash
python main.py create --tugas3
```
Skrip akan membuat EC2 bernama `tugas-3-reservasi`, menginstal Docker, meng-clone repositori, menyiapkan `Dockerfile`, `haproxy.cfg`, dan `docker-compose.yml`, melakukan import SQL, dan menjalankan 4 kontainer (HAProxy, 2 webservers, dan 1 MariaDB) hingga teruji HTTP 200 OK.

> [!TIP]
> **Memperbarui Instance Tugas 3 yang Sudah Berjalan Tanpa Buat EC2 Baru:**
> Jika EC2 `tugas-3-reservasi` sudah aktif dan Anda ingin memperbarui atau menerapkan arsitektur HAProxy secara instan:
> ```bash
> python main.py update --tugas3
> ```


#### Ingin Menjalankan Tugas 2 (Aplikasi ID Card)?
```bash
python main.py create --tugas2
```

#### Ingin Menjalankan Docker Swarm 3 Node + MariaDB Standalone (LKPD 8)?
```bash
python run_lkpd8.py
# Atau jalankan otomasi penuh sekali perintah:
python run_lkpd8.py --all
# Atau melalui CLI utama:
python main.py create --lkpd 8
```
*(Menyiapkan klaster 3 node Swarm: 1 Manager + 2 Worker, serta 1 EC2 terpisah untuk MariaDB 11.8, routing mesh round-robin, dan deployment appKantin via Docker Stack)*.

#### Ingin Menjalankan Docker Swarm Single Node (LKPD 7)?
```bash
python run_lkpd7.py
# Atau melalui CLI utama:
python main.py create --lkpd 7
```

#### Ingin Menjalankan Docker Swarm Multi-Node (LKPD 6)?
```bash
python run_lkpd6.py
# Atau melalui CLI utama:
python main.py create --swarm
```

#### Ingin Menjalankan Salah Satu LKPD Standalone (Misal LKPD 1)?
```bash
python main.py create --lkpd 1
```
*(Ganti angka `1` dengan nomor LKPD `2`, `3`, `4`, atau `5` sesuai kebutuhan)*.

#### Ingin Menjalankan Seluruh LKPD Sekaligus?
```bash
python main.py create --all
```

---

### Langkah 5: Memeriksa Status & Membuka di Web Browser

1. **Cek IP Publik Server:**
   ```bash
   python main.py status
   ```
   Atau cek khusus tugas tertentu:
   ```bash
   python main.py status --tugas3
   ```
   Anda akan melihat tabel berisi **Instance ID**, **State (running)**, dan **Public IP**.

2. **Diagnosa Runtime (Live Inspect):**
   ```bash
   python main.py inspect
   ```
   Perintah ini akan mengetes respon HTTP langsung dari luar dan membaca log kontainer Docker yang sedang aktif di dalam server.

3. **Buka di Browser:**
   Ambil **Public IP** instance Anda, lalu buka browser:
   - **Tugas 3:** `http://<PUBLIC_IP>:8083` *(Login default: admin / admin123)*
   - **Tugas 2:** `http://<PUBLIC_IP>:8080`
   - **LKPD 1:** `http://<PUBLIC_IP>:8080`
   - **LKPD 2:** `http://<PUBLIC_IP>:8088`
   - **LKPD 3:** `http://<PUBLIC_IP>:8001`
   - **LKPD 4:** `http://<PUBLIC_IP>:8002`
   - **LKPD 5:** `http://<PUBLIC_IP>:8088`

---

### Langkah 6: Menghapus / Mematikan Server (Terminate)

> [!TIP]
> Kuota saldo di AWS Academy atau cloud publik terbatas. Jika sesi praktikum atau penilaian sudah selesai, selalu hapus instance yang tidak lagi digunakan.

- **Hapus instance Tugas 3 saja:**
  ```bash
  python main.py terminate --tugas3
  ```
- **Hapus instance Tugas 2 saja:**
  ```bash
  python main.py terminate --tugas2
  ```
- **Hapus LKPD tertentu:**
  ```bash
  python main.py terminate --lkpd 1
  ```
- **Hapus seluruh instance LKPD yang berjalan:**
  ```bash
  python main.py terminate --all
  ```

---

## 🛡️ Port Mapping & Keamanan Jaringan

Security Group (`lkpd-docker-sg` & `swarm-sg`) secara otomatis dikonfigurasi oleh sistem:

| Port | Protokol | Akses | Peruntukan |
|:---:|:---:|:---:|---|
| **22** | TCP | Publik (`0.0.0.0/0`) | Akses Terminal Remote via SSH |
| **80** / **443** | TCP | Publik (`0.0.0.0/0`) | Standar Web HTTP / HTTPS |
| **8080** | TCP | Publik (`0.0.0.0/0`) | LKPD 1 (Docker HTTP), Tugas 2 (App ID Card), LKPD 6, 7, 8 (Docker Swarm Ingress) |
| **8088** | TCP | Publik (`0.0.0.0/0`) | LKPD 2 (Multi-Container) & LKPD 5 (Docker Compose) |
| **8001** | TCP | Publik (`0.0.0.0/0`) | LKPD 3 (Custom Image Dockerfile) |
| **8002** | TCP | Publik (`0.0.0.0/0`) | LKPD 4 (Docker Hub Image) |
| **8083** | TCP | Publik (`0.0.0.0/0`) | Tugas 3 (HAProxy Load Balancer ke 2 Webservers) |
| **2377** | TCP | Internal Klaster | Docker Swarm Cluster Management Communication |
| **7946** | TCP/UDP | Internal Klaster | Docker Swarm Node-to-Node Discovery |
| **4789** | UDP | Internal Klaster | Docker Swarm Overlay Network Traffic (Ingress Mesh) |
| **3306** | TCP | Internal / VPC | MariaDB / MySQL Dedicated Database Server |

---

## 📁 Struktur Direktori Repository

```text
aws-docker-automation-tasks/
├── docs/
│   ├── pdf/               # Panduan Resmi LKPD 1 s.d. 8 (PDF)
│   │   ├── LKPD 1 - Dasar Docker.pdf
│   │   ├── LKPD 2 - Deploy App Multi Container.pdf
│   │   ├── LKPD 3 - Dockerfile.pdf
│   │   ├── LKPD 4 - Publikasi Docker Image ke Docker Hub.pdf
│   │   ├── LKPD 5 - Docker Compose.pdf
│   │   ├── LKPD 6 - Pengantar Konsep Docker Swarm.pdf
│   │   ├── LKPD 7 - Docker Swarm Single Node.pdf
│   │   └── LKPD 8 - Docker Swarm 3 Node AWS Academy.pdf
│   ├── reports/           # Laporan Praktikum Komprehensif Markdown
│   │   ├── LKPD_6_DOCKER_SWARM_REPORT.md
│   │   ├── LKPD_7_DOCKER_SWARM_REPORT.md
│   │   └── LKPD_8_DOCKER_SWARM_REPORT.md
│   └── articles/          # Publikasi Tutorial Arsitektur & Artikel Medium
│       ├── TUGAS_3_MEDIUM_ARTICLE.md
│       ├── infra tugas 3.png
│       └── topologi_tugas3.png
├── aws/                   # Modul SDK AWS Boto3
│   ├── ami.py             # SSM Parameter Store AMI Resolver
│   ├── diagnostics.py     # Live Runtime Inspector (HTTP & SSM Logs)
│   ├── doctor.py          # AWS Doctor (Kredensial, STS, EC2, SSM, Auto-Repair)
│   ├── ec2.py             # EC2 Management (Run, Describe, Terminate)
│   └── network.py         # VPC, Subnet, dan Security Group Rule Sync (Self-Referencing SG)
├── config/
│   └── settings.py        # Environment Configuration Loader & Dynamic Reloader
├── lkpd/                  # Controllers Modul LKPD & Tugas
│   ├── base.py            # Base abstract class & template renderer
│   ├── lkpd1.py s.d lkpd5.py
│   ├── lkpd6.py           # Controller Swarm Multi-Node (Manager + Worker)
│   ├── lkpd7.py           # Controller Swarm Single-Node (AppKantin)
│   ├── lkpd8.py           # Orchestrator Swarm 3-Node Cluster + Dedicated MariaDB
│   ├── tugas2.py          # Controller Tugas 2 (App ID Card)
│   └── tugas3.py          # Controller Tugas 3 (App Reservasi + HAProxy)
├── scripts/               # Modular Shell Execution Scripts
│   ├── lkpd7/             # Script Otomasi LKPD 7 (01 s.d. 07)
│   ├── lkpd8/             # Script Otomasi LKPD 8 (01 s.d. 09)
│   ├── setup_manager.sh   # Helper Inisialisasi Swarm Manager
│   ├── setup_worker.sh    # Helper Join Swarm Worker
│   ├── create_service.sh  # Helper Deployment Service Swarm
│   ├── scale_service.sh   # Helper Scaling Service Replicas
│   └── test_self_healing.sh
├── templates/             # Script UserData Cloud-Init
│   ├── bootstrap.sh       # Inisialisasi dependensi & health helper
│   ├── lkpd1.sh s.d lkpd5.sh
│   ├── lkpd6_manager.sh / lkpd6_worker.sh
│   ├── lkpd7.sh
│   ├── lkpd8_manager.sh / lkpd8_worker.sh / lkpd8_db.sh
│   ├── tugas2_idcard.sh   # Script otomasi Tugas 2
│   └── tugas3_reservasi.sh# Script otomasi Tugas 3 (HAProxy Multi-Backend)
├── output/                # Artefak lokal hasil eksekusi (summary.json)
├── kantin-stack.yml       # Docker Stack Compose Specification (Tantangan LKPD 8)
├── main.py                # File utama (CLI Entrypoint Lengkap)
├── run_lkpd6.py           # Standalone Interactive Runner LKPD 6
├── run_lkpd7.py           # Standalone Interactive Runner LKPD 7
├── run_lkpd8.py           # Standalone Interactive Runner LKPD 8
├── requirements.txt       # Daftar pustaka Python
├── .env.example           # Template kredensial tanpa rahasia
├── .gitignore             # Proteksi berkas sensitif (.env, .pem, dsb.)
└── README.md              # Dokumentasi lengkap proyek
```

---

## ❓ Tanya Jawab & Troubleshooting Pemula (FAQ)

1. **Bagaimana jika halaman web tidak mau terbuka di browser?**
   - Pastikan status instance sudah `running` (`python main.py status`).
   - Tunggu 1–2 menit setelah instance running karena server butuh waktu untuk bootstrap mengunduh Docker dan image aplikasi.
   - Cek apakah port yang diakses sudah sesuai (misal Tugas 3 pada port `:8083`).
   - Gunakan `python main.py inspect` untuk melihat apakah server sudah merespon `HTTP 200 OK`.

2. **Muncul error `ExpiredToken` dari AWS?**
   - Jika Anda menggunakan AWS Academy, session token hanya bertahan beberapa jam.
   - Buka kembali tombol **AWS Details** pada AWS Academy, salin `aws_access_key_id`, `aws_secret_access_key`, dan `aws_session_token` yang baru, lalu perbarui di file `.env`.

3. **Apakah file `.env` saya aman?**
   - Sangat aman. File `.env` dan file kunci `*.pem` telah didaftarkan di dalam `.gitignore`, sehingga tidak akan pernah terunggah ke repositori publik GitHub.

---

Selamat belajar dan berpraktik Docker & Cloud Computing! 🎉
