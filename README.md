# AWS Docker Automation Tasks

Repositori ini berisi framework otomasi berbasis **Python (Boto3)** dan **Cloud-Init / User Data** untuk membuat, mengonfigurasi, dan men-deploy praktikum kontainerisasi **Docker** serta **Docker Compose** secara otomatis pada cloud **Amazon Web Services (AWS EC2)**.

---

## 🚀 Fitur & Modul Praktikum

| Modul / Tugas | Deskripsi Praktikum | Port Layanan | Stack Teknologi |
|---|---|:---:|---|
| **LKPD 1** | Standalone Container Web | `8080` | Docker, HTTP Server |
| **LKPD 2** | Multi-Container Web & Database Manual | `8088` | PHP Apache + MariaDB, Bridge Network |
| **LKPD 3** | Custom Image Build via Dockerfile | `8001` | Ubuntu 24.04, Apache2, PHP MySQL |
| **LKPD 4** | Siklus Docker Hub (Push, Pull & Run) | `8002` | Docker Hub Registry Integration |
| **LKPD 5** | Multi-Container Orchestration Compose | `8088` | Docker Compose, MariaDB, AppToko |
| **Tugas 2** | Deploy Aplikasi App ID Card | `8080` | Docker Compose, AppIDcard, MariaDB |
| **Tugas 3** | Deploy Aplikasi Reservasi Ruangan | `8083` | Docker Compose, `php:8.2-apache`, `mariadb:11-jammy` |

---

## 🏛️ Arsitektur & Alur Kerja

```text
[ Developer / CLI ]
       │
       ▼  (Boto3 API: VPC, Subnet, Security Group, AMI Resolver, EC2)
[ AWS EC2 Instance (Ubuntu 24.04 LTS x86_64) ]
       │
       ▼  (Cloud-Init UserData: bootstrap.sh)
[ Docker Engine & Docker Compose Plugin ]
       │
       ├─► LKPD 1-5  : Praktikum Mandiri Kontainer Docker
       ├─► Tugas 2   : Docker Compose (App ID Card)
       └─► Tugas 3   : Docker Compose (Aplikasi Reservasi Ruangan)
```

---

## 📋 Prasyarat

1. **Python 3.10+**
2. **Akun AWS** (didukung penuh untuk akun reguler maupun **AWS Academy Learner Lab / Vocareum**)
3. Dependencies Python:
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Panduan Konfigurasi Awal

1. Salin template konfigurasi `.env.example` menjadi `.env`:
   ```bash
   cp .env.example .env
   # Atau pada Windows PowerShell:
   Copy-Item .env.example .env
   ```

2. Buka file `.env` dan lengkapi kredensial AWS aktif Anda:
   ```ini
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=ASIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_SESSION_TOKEN=IQoJ...  # Wajib jika menggunakan AWS Academy
   ```

3. *(Opsional)* Jika ingin menguji push image pada LKPD 4, isi token Docker Hub:
   ```ini
   DOCKERHUB_USERNAME=username_anda
   DOCKERHUB_TOKEN=dckr_pat_...
   ```

> [!IMPORTANT]
> Jangan pernah meng-commit file `.env` atau file kredensial (*.pem, *.key) ke Git repository. File-file tersebut telah otomatis diabaikan oleh `.gitignore`.

---

## 💻 Penggunaan Perintah CLI

Seluruh kontrol otomasi dijalankan melalui file utama `main.py`:

### 1. Pre-Flight Validation (Uji Kredensial & Resource)
Memverifikasi kredensial AWS STS, VPC default, subnet, AMI Ubuntu, Key Pair `vockey`, IAM Profile, dan aturan Security Group sebelum membuat instance:
```bash
python main.py validate
```

### 2. Membuat Instance & Menjalankan Otomasi Deployment (`create`)

- **Deploy Tugas 3 (Aplikasi Reservasi Ruangan):**
  ```bash
  python main.py create --tugas3
  ```
- **Deploy Tugas 2 (App ID Card):**
  ```bash
  python main.py create --tugas2
  ```
- **Deploy LKPD Tertentu (Contoh LKPD 1 sampai 5):**
  ```bash
  python main.py create --lkpd 1
  ```
- **Deploy Seluruh LKPD 1 sampai 5 Sekaligus:**
  ```bash
  python main.py create --all
  ```

### 3. Memeriksa Status Instance & IP Publik (`status`)

- **Melihat seluruh instance aktif:**
  ```bash
  python main.py status
  ```
- **Filter khusus Tugas 3:**
  ```bash
  python main.py status --tugas3
  ```

### 4. Diagnosa Runtime Mendalam (`inspect`)
Menginspeksi status respon HTTP langsung dari luar, status Cloud-Init `/opt/lkpd/status.json`, serta daftar kontainer Docker aktif via AWS Systems Manager (SSM):
```bash
python main.py inspect
```

### 5. Menghapus / Terminasi Instance (`terminate`)
Setelah selesai sesi praktikum atau penilaian, terminate instance agar menghemat kuota lab:
```bash
python main.py terminate --tugas3   # Khusus instance Tugas 3
python main.py terminate --tugas2   # Khusus instance Tugas 2
python main.py terminate --lkpd 1   # Khusus LKPD 1
python main.py terminate --all      # Hapus semua instance LKPD
```

---

## 📂 Struktur Direktori

```text
aws-docker-automation-tasks/
├── aws/                   # Modul interaksi AWS SDK (Boto3)
│   ├── ami.py             # Resolver AMI Ubuntu resmi via SSM Parameter Store
│   ├── diagnostics.py     # Engine inspeksi live status runtime & HTTP check
│   ├── ec2.py             # Lifecycle EC2 (Launch, Wait, Status, Terminate)
│   └── network.py         # Resolver VPC, Subnet, dan sync Security Group rules
├── config/
│   └── settings.py        # Pengelola variabel konfigurasi environment
├── lkpd/                  # Definisi kelas controller masing-masing modul
│   ├── base.py            # Base abstract class LKPD runner
│   ├── lkpd1.py s.d lkpd5.py
│   ├── tugas2.py          # Controller Tugas 2 (App ID Card)
│   └── tugas3.py          # Controller Tugas 3 (App Reservasi Ruangan)
├── templates/             # Shell script Cloud-Init yang dieksekusi di EC2
│   ├── bootstrap.sh       # Inisialisasi Docker, Git, Tools & health helper
│   ├── lkpd1.sh s.d lkpd5.sh
│   ├── tugas2_idcard.sh
│   └── tugas3_reservasi.sh
├── output/                # Ringkasan hasil deployment (summary.json)
├── .env.example           # Template variabel environment
├── .gitignore             # Proteksi berkas sensitif dan artefak lokal
├── main.py                # CLI Entrypoint aplikasi
├── requirements.txt       # Daftar dependensi Python
└── README.md
```

---

## 📄 Lisensi

Proyek ini dibuat untuk kebutuhan pembelajaran dan otomatisasi praktikum cloud computing AWS.
