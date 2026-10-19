# 🚀 Dari EC2 Kosong Jadi Aplikasi Reservasi: Docker Compose + HAProxy di AWS

### Tutorial Lengkap Tugas 3 — Deploy App Reservasi dengan 2 Web Server, HAProxy, MariaDB, dan Docker Volume

Bagaimana cara menjalankan sebuah aplikasi PHP di AWS dengan **dua web server**, database MariaDB, dan HAProxy sebagai load balancer?

Pada tutorial ini, kita akan membangun semuanya **secara manual dari nol**, mulai dari konfigurasi AWS sampai aplikasi Reservasi dapat diakses melalui browser.

Arsitektur akhirnya akan menggunakan:

* AWS EC2
* Default VPC
* Ubuntu 22.04 LTS
* Docker
* Docker Compose
* HAProxy
* 2 web server Apache + PHP
* MariaDB
* Docker Volume

Tidak menggunakan automation script. Semua konfigurasi dilakukan satu per satu agar setiap bagian infrastrukturnya dapat dipahami.

---

# 1. Gambaran Arsitektur

Arsitektur Tugas 3 yang akan kita buat:

```text
                         USER
                      Web Browser
                           │
                           │ HTTP :8083
                           ▼
                       INTERNET
                           │
                           ▼
                ┌─────────────────────┐
                │     DEFAULT VPC     │
                │                     │
                │   Public Subnet     │
                │                     │
                │  ┌───────────────┐  │
                │  │ Security Group│  │
                │  │               │  │
                │  │ TCP 22        │  │
                │  │ TCP 8083      │  │
                │  └───────┬───────┘  │
                │          │           │
                │          ▼           │
                │  ┌────────────────┐ │
                │  │      EC2       │ │
                │  │ tugas-3-       │ │
                │  │ reservasi      │ │
                │  │                │ │
                │  │ Docker Compose │ │
                │  └───────┬────────┘ │
                │          │           │
                └──────────┼───────────┘
                           │
                    Docker Network
                           │
                    ┌──────▼──────┐
                    │   HAProxy   │
                    │    :8080    │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼─────┐ ┌─────▼─────┐
              │ Webserver1│ │ Webserver2│
              │ Apache PHP│ │ Apache PHP│
              │    :80    │ │    :80    │
              └─────┬─────┘ └─────┬─────┘
                    │             │
                    └──────┬──────┘
                           ▼
                    ┌────────────┐
                    │  MariaDB   │
                    │    :3306   │
                    └─────┬──────┘
                          │
                    ┌─────▼──────┐
                    │ Docker     │
                    │ Volume     │
                    │  db_data   │
                    └────────────┘
```

---

# 2. Bagaimana Request Berjalan?

Ketika pengguna membuka:

```text
http://PUBLIC-IP-EC2:8083
```

request akan berjalan seperti berikut:

```text
Browser
   ↓
Internet
   ↓
EC2 Public IP :8083
   ↓
HAProxy :8080
   ↓
┌─────────────┐
│             │
▼             ▼
Webserver1  Webserver2
   │             │
   └──────┬──────┘
          ▼
       MariaDB
          │
          ▼
       db_data
```

Port publik `8083` diarahkan ke port `8080` milik HAProxy:

```text
EC2 :8083
   ↓
HAProxy :8080
```

Kemudian HAProxy meneruskan request ke salah satu web server pada port `80`.

---

# 3. Komponen yang Digunakan

| Komponen | Konfigurasi |
| :--- | :--- |
| Cloud | AWS |
| Region | `ap-southeast-1` |
| VPC | Default VPC |
| Subnet | Default Subnet |
| EC2 | `t3.small` |
| OS | Ubuntu 22.04 LTS |
| Key Pair | `vockey` |
| Container Engine | Docker |
| Orchestration | Docker Compose |
| Load Balancer | HAProxy |
| Web Server | Apache + PHP 8.2 |
| Database | MariaDB 11 |
| Database Volume | `db_data` |
| Public Port | `8083` |
| HAProxy Port | `8080` |
| Web Server Port | `80` |
| Database Port | `3306` |

---

# 4. Memilih Region AWS

Buka **AWS Management Console**.

Pada bagian region di kanan atas pilih:

```text
Asia Pacific (Singapore)
ap-southeast-1
```

Pastikan seluruh proses dilakukan pada region:

```text
ap-southeast-1
```

---

# 5. Menggunakan Default VPC

Kita **tidak membuat VPC baru**.

Masuk ke:

```text
AWS Console
→ VPC
→ Your VPCs
```

Cari VPC dengan:

```text
Default VPC = Yes
```

Gunakan VPC tersebut.

Kemudian buka:

```text
VPC
→ Subnets
```

Cari salah satu subnet yang berada di dalam Default VPC.

Gunakan Default Subnet tersebut ketika membuat EC2.

> Karena menggunakan Default VPC, kita tidak perlu menentukan atau mengarang CIDR seperti `10.0.0.0/16`. Gunakan konfigurasi Default VPC yang memang tersedia pada akun AWS.

---

# 6. Menggunakan Shared Security Group

Pada Tugas 3 kita **tidak membuat Security Group baru**.

Gunakan Shared Security Group yang sebelumnya digunakan untuk tugas-tugas LKPD.

Nama Security Group dapat berupa:

```text
lkpd-docker-sg
```

atau:

```text
sg-lkpd-docker
```

sesuai yang tersedia pada akun.

Karena Security Group tersebut digunakan bersama beberapa tugas, terdapat beberapa port di dalamnya.

Namun untuk tutorial Tugas 3, kita fokus pada port yang berhubungan dengan deployment ini.

## Inbound Rule — SSH

```text
Type: SSH
Port: 22
Protocol: TCP
Source: 0.0.0.0/0
```

Port `22` digunakan untuk akses ke EC2.

## Inbound Rule — HTTP

```text
Type: HTTP
Port: 80
Protocol: TCP
Source: 0.0.0.0/0
```

Port HTTP standar yang tersedia pada Shared Security Group.

## Inbound Rule — HTTPS

```text
Type: HTTPS
Port: 443
Protocol: TCP
Source: 0.0.0.0/0
```

Port HTTPS yang tersedia pada Shared Security Group.

## Inbound Rule — Port Aplikasi

Yang paling penting untuk Tugas 3:

```text
Type: Custom TCP
Port: 8083
Protocol: TCP
Source: 0.0.0.0/0
```

Port ini menjadi pintu masuk publik menuju HAProxy.

## Inbound Rule — Database

Shared Security Group juga memiliki:

```text
Type: Custom TCP
Port: 3306
Protocol: TCP
Source: 0.0.0.0/0
```

Namun pada arsitektur ini, komunikasi aplikasi dengan MariaDB dilakukan melalui jaringan internal Docker.

Jadi pengguna tidak perlu mengakses:

```text
PUBLIC-IP:3306
```

---

# 7. Outbound Rule

Outbound menggunakan:

```text
All Traffic
Destination: 0.0.0.0/0
```

Rule ini memungkinkan EC2 melakukan koneksi keluar seperti:

* update Ubuntu,
* download package,
* clone repository,
* pull Docker image,
* dan kebutuhan koneksi lainnya.

---

# 8. Membuat EC2 Instance

Masuk ke:

```text
EC2
→ Instances
→ Launch instance
```

Pada bagian Name isi:

```text
tugas-3-reservasi
```

---

# 9. Memilih AMI

Pada bagian AMI pilih:

```text
Ubuntu Server 22.04 LTS
```

Gunakan versi 64-bit.

---

# 10. Memilih Instance Type

Gunakan:

```text
t3.small
```

Instance ini nantinya menjalankan:

```text
HAProxy
Webserver1
Webserver2
MariaDB
```

dalam Docker.

---

# 11. Memilih Key Pair

Pada bagian Key Pair pilih:

```text
vockey
```

Kita menggunakan Key Pair yang sudah tersedia dan tidak membuat Key Pair baru.

---

# 12. Konfigurasi Network EC2

Pada bagian Network Settings:

### VPC

```text
Default VPC
```

### Subnet

```text
Default Subnet
```

### Auto-assign Public IP

```text
Enable
```

EC2 membutuhkan Public IP agar aplikasi dapat diakses dari internet.

---

# 13. Memilih Shared Security Group

Pada Security Group pilih:

```text
Select existing security group
```

Kemudian pilih Shared Security Group yang digunakan sebelumnya, misalnya:

```text
lkpd-docker-sg
```

atau:

```text
sg-lkpd-docker
```

Tidak perlu membuat Security Group baru.

---

# 14. Launch Instance

Setelah konfigurasi selesai, klik:

```text
Launch instance
```

Tunggu sampai instance dibuat.

---

# 15. Memastikan EC2 Berjalan

Masuk:

```text
EC2
→ Instances
```

Pilih:

```text
tugas-3-reservasi
```

Pastikan:

```text
Instance state: Running
```

dan:

```text
Status checks: 2/2 checks passed
```

Catat:

```text
Public IPv4 address
```

Misalnya:

```text
34.xxx.xxx.xxx
```

---

# 16. Connect ke EC2 dengan EC2 Instance Connect

Kita tidak perlu menggunakan Windows PowerShell untuk koneksi.

Pada halaman EC2:

```text
EC2
→ Instances
→ tugas-3-reservasi
→ Connect
```

Pilih:

```text
EC2 Instance Connect
```

Kemudian klik:

```text
Connect
```

AWS akan membuka terminal Ubuntu langsung di browser.

Jika berhasil, terminal akan terlihat seperti:

```text
ubuntu@ip-172-31-xx-xx:~$
```

Mulai dari sini seluruh konfigurasi server dilakukan langsung melalui terminal EC2 tersebut.

---

# 17. Update Ubuntu

Jalankan:

```bash
sudo apt update
```

Kemudian:

```bash
sudo apt upgrade -y
```

Tunggu sampai proses selesai.

---

# 18. Install Docker

Install Docker:

```bash
sudo apt install docker.io -y
```

Aktifkan Docker:

```bash
sudo systemctl enable docker
```

Jalankan Docker:

```bash
sudo systemctl start docker
```

Cek:

```bash
docker --version
```

Jika versi Docker muncul, instalasi berhasil.

---

# 19. Memberikan Permission Docker

Tambahkan user `ubuntu` ke Docker group:

```bash
sudo usermod -aG docker ubuntu
```

Keluar dari EC2 Instance Connect:

```bash
exit
```

Kemudian connect kembali:

```text
EC2
→ Instances
→ tugas-3-reservasi
→ Connect
→ EC2 Instance Connect
→ Connect
```

Tes:

```bash
docker ps
```

Jika tidak ada error permission, Docker siap digunakan.

---

# 20. Install Git

Jalankan:

```bash
sudo apt install git -y
```

Cek:

```bash
git --version
```

---

# 21. Clone Repository App Reservasi

Gunakan repository:

```bash
git clone https://github.com/paknux/appReservasi.git
```

Kemudian:

```bash
cd appReservasi
```

Cek isi directory:

```bash
ls
```

Sekarang kita sudah berada di dalam source code aplikasi Reservasi.

---

# 22. Memahami Struktur Project

Project aplikasi memiliki source code PHP.

Kita akan menambahkan beberapa konfigurasi Docker secara manual.

File penting yang akan kita gunakan adalah:

```text
appReservasi/
│
├── config/
│   └── database.php
│
├── Dockerfile
├── docker-compose.yml
├── haproxy.cfg
├── reservasi_ruangan.sql
│
└── file aplikasi lainnya
```

Tiga file Docker utama:

```text
Dockerfile
docker-compose.yml
haproxy.cfg
```

Dan satu konfigurasi aplikasi yang sangat penting:

```text
config/database.php
```

---

# 23. Konfigurasi Koneksi Database PHP

**Ini merupakan langkah yang sangat penting.**

Aplikasi PHP pada repository awalnya menggunakan konfigurasi database lokal.

Jika dibiarkan, PHP akan mencoba mencari database di:

```text
localhost
```

Masalahnya, PHP berjalan di container `webserver1` atau `webserver2`, sedangkan MariaDB berada di container yang berbeda:

```text
webserver1
webserver2
     │
     ▼
  dbserver
```

Karena itu PHP harus diarahkan ke nama container database:

```text
dbserver
```

Buka file:

```bash
nano config/database.php
```

Sesuaikan konfigurasi database menjadi:

```php
$DB_HOST = 'dbserver';
$DB_USER = 'root';
$DB_PASS = 'root123';
$DB_NAME = 'db_reservasi_ruangan';
```

Simpan:

```text
CTRL + O
ENTER
CTRL + X
```

### Kenapa `localhost` diganti `dbserver`?

Karena dalam Docker Compose, service database bernama:

```text
dbserver
```

Docker menyediakan DNS internal sehingga container web dapat mengaksesnya menggunakan:

```text
dbserver
```

Jadi alurnya:

```text
PHP
 ↓
dbserver:3306
 ↓
MariaDB
```

Bukan:

```text
PHP
 ↓
localhost:3306
```

---

# 24. Membuat Dockerfile

Repository `appReservasi` merupakan source code PHP, sehingga kita membuat Dockerfile secara manual.

Jalankan:

```bash
nano Dockerfile
```

Masukkan:

```dockerfile
FROM php:8.2-apache

RUN docker-php-ext-install pdo_mysql

RUN a2enmod rewrite

WORKDIR /var/www/html

EXPOSE 80
```

Simpan:

```text
CTRL + O
ENTER
CTRL + X
```

---

# 25. Memahami Dockerfile

Sekarang kita pahami setiap bagian.

### Base Image

```dockerfile
FROM php:8.2-apache
```

Kita menggunakan image PHP 8.2 yang sudah dilengkapi Apache.

Jadi kita tidak perlu memasang Apache dan PHP secara manual satu per satu.

---

### Install PDO MySQL

```dockerfile
RUN docker-php-ext-install pdo_mysql
```

Aplikasi PHP membutuhkan driver `pdo_mysql` agar dapat berkomunikasi dengan MariaDB/MySQL.

Tanpa extension ini, koneksi database dapat gagal.

---

### Mengaktifkan Apache Rewrite

```dockerfile
RUN a2enmod rewrite
```

Command ini mengaktifkan Apache `mod_rewrite`.

Modul ini diperlukan oleh aplikasi PHP yang menggunakan URL rewriting.

---

### Working Directory

```dockerfile
WORKDIR /var/www/html
```

Directory kerja Apache diarahkan ke:

```text
/var/www/html
```

Source code aplikasi nantinya akan di-mount ke directory tersebut.

---

### Expose Port

```dockerfile
EXPOSE 80
```

Menunjukkan bahwa web server di dalam container menggunakan port:

```text
80
```

---

# 26. Membuat docker-compose.yml

Sekarang kita membuat konfigurasi untuk seluruh container.

Jalankan:

```bash
nano docker-compose.yml
```

Masukkan:

```yaml
services:
  # 1. Load Balancer Publik (HAProxy)
  haproxy:
    image: haproxy:latest
    container_name: haproxy
    ports:
      - "8083:8080"
    volumes:
      - ./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    depends_on:
      - webserver1
      - webserver2
    restart: unless-stopped

  # 2. Web Server Node 1 (Apache + PHP 8.2)
  webserver1:
    build:
      context: .
      dockerfile: Dockerfile
    image: appreservasi-webserver:latest
    container_name: webserver1
    expose:
      - "80"
    volumes:
      - ./:/var/www/html
    depends_on:
      - dbserver
    restart: unless-stopped

  # 3. Web Server Node 2 (Apache + PHP 8.2)
  webserver2:
    image: appreservasi-webserver:latest
    container_name: webserver2
    expose:
      - "80"
    volumes:
      - ./:/var/www/html
    depends_on:
      - dbserver
    restart: unless-stopped

  # 4. Database Server (MariaDB 11)
  dbserver:
    image: mariadb:11-jammy
    container_name: dbserver
    environment:
      MARIADB_ROOT_PASSWORD: root123
      MARIADB_DATABASE: db_reservasi_ruangan
    volumes:
      - db_data:/var/lib/mysql
      - ./reservasi_ruangan.sql:/docker-entrypoint-initdb.d/reservasi_ruangan.sql:ro
    restart: unless-stopped

# Named Volume untuk persistensi data database
volumes:
  db_data:
```

Simpan:

```text
CTRL + O
ENTER
CTRL + X
```

---

# 27. Memahami Service HAProxy

Bagian:

```yaml
haproxy:
  image: haproxy:latest
```

menggunakan image HAProxy.

Container diberi nama:

```yaml
container_name: haproxy
```

Kemudian terdapat:

```yaml
ports:
  - "8083:8080"
```

Formatnya:

```text
HOST:CONTAINER
```

Sehingga:

```text
8083:8080
```

berarti:

```text
EC2 Host :8083
     ↓
HAProxy Container :8080
```

---

# 28. Konfigurasi Webserver 1

Service:

```yaml
webserver1:
```

menggunakan:

```yaml
build:
  context: .
  dockerfile: Dockerfile
```

Artinya image dibuat dari Dockerfile yang kita buat sebelumnya.

Image diberi nama:

```yaml
image: appreservasi-webserver:latest
```

Container:

```yaml
container_name: webserver1
```

Port:

```yaml
expose:
  - "80"
```

Port `80` hanya digunakan untuk komunikasi internal Docker.

---

# 29. Konfigurasi Webserver 2

Webserver kedua menggunakan image yang sama:

```yaml
webserver2:
  image: appreservasi-webserver:latest
```

Jadi kita memiliki:

```text
appreservasi-webserver:latest
          │
          ├── webserver1
          │
          └── webserver2
```

Keduanya menjalankan aplikasi yang sama.

---

# 30. Mount Source Code

Kedua webserver menggunakan:

```yaml
volumes:
  - ./:/var/www/html
```

Artinya directory project pada EC2 di-mount ke:

```text
/var/www/html
```

di dalam container.

Dengan demikian Apache dapat membaca source code aplikasi.

---

# 31. Konfigurasi MariaDB

Database menggunakan:

```yaml
image: mariadb:11-jammy
```

Container:

```yaml
container_name: dbserver
```

Database root password:

```yaml
MARIADB_ROOT_PASSWORD: root123
```

Database:

```yaml
MARIADB_DATABASE: db_reservasi_ruangan
```

---

# 32. Database Volume

Bagian:

```yaml
- db_data:/var/lib/mysql
```

menghubungkan named volume:

```text
db_data
```

ke directory:

```text
/var/lib/mysql
```

di dalam MariaDB.

Tujuannya agar data database tidak hanya berada di dalam container.

---

# 33. Import Database

Bagian:

```yaml
- ./reservasi_ruangan.sql:/docker-entrypoint-initdb.d/reservasi_ruangan.sql:ro
```

menghubungkan file SQL:

```text
reservasi_ruangan.sql
```

ke directory initialization MariaDB:

```text
/docker-entrypoint-initdb.d/
```

Dengan demikian database dapat diinisialisasi berdasarkan SQL yang sudah disediakan.

---

# 34. Membuat Konfigurasi HAProxy

Sekarang buat:

```bash
nano haproxy.cfg
```

Masukkan:

```text
global
    log stdout format raw local0

defaults
    mode http
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend http_front
    bind *:8080
    default_backend web_backend

backend web_backend
    balance roundrobin

    option httpchk GET /

    server webserver1 webserver1:80 check
    server webserver2 webserver2:80 check
```

Simpan:

```text
CTRL + O
ENTER
CTRL + X
```

---

# 35. Memahami Konfigurasi HAProxy

Frontend:

```text
frontend http_front
    bind *:8080
```

HAProxy menerima request pada port `8080`.

Kemudian:

```text
default_backend web_backend
```

mengarahkan request ke backend.

Backend:

```text
backend web_backend
```

menggunakan:

```text
balance roundrobin
```

Artinya request dibagi secara bergantian.

Dua backend yang digunakan:

```text
webserver1:80
webserver2:80
```

Sehingga:

```text
Request 1 → webserver1
Request 2 → webserver2
Request 3 → webserver1
Request 4 → webserver2
```

---

# 36. Health Check HAProxy

Pada konfigurasi terdapat:

```text
option httpchk GET /
```

HAProxy akan melakukan HTTP health check terhadap backend.

Jika webserver dapat memberikan response yang sesuai, backend dianggap tersedia.

---

# 37. Mengecek File Sebelum Build

Sebelum menjalankan Docker Compose:

```bash
ls -lah
```

Pastikan file penting tersedia:

```text
Dockerfile
docker-compose.yml
haproxy.cfg
reservasi_ruangan.sql
```

Dan konfigurasi database:

```text
config/database.php
```

sudah diarahkan ke:

```text
dbserver
```

---

# 38. Build Docker Image

Sekarang jalankan:

```bash
docker compose build
```

Docker akan membaca:

```text
Dockerfile
```

dan membuat image:

```text
appreservasi-webserver:latest
```

Setelah selesai:

```bash
docker images
```

Cari:

```text
appreservasi-webserver
```

---

# 39. Menjalankan Semua Container

Jalankan:

```bash
docker compose up -d
```

atau:

```bash
docker compose up -d --build
```

Docker Compose akan menjalankan:

```text
haproxy
webserver1
webserver2
dbserver
```

---

# 40. Mengecek Container

Jalankan:

```bash
docker compose ps
```

atau:

```bash
docker ps
```

Target:

```text
haproxy
webserver1
webserver2
dbserver
```

semuanya harus berada dalam kondisi:

```text
Up
```

---

# 41. Mengecek Port HAProxy

Jalankan:

```bash
docker ps
```

Pada container HAProxy harus terlihat mapping seperti:

```text
0.0.0.0:8083->8080/tcp
```

Artinya:

```text
Public/Host
8083
  ↓
Container
8080
```

---

# 42. Mengecek Docker Network

Jalankan:

```bash
docker network ls
```

Docker Compose akan membuat network default untuk service-service tersebut.

Untuk melihat detailnya:

```bash
docker network inspect appreservasi_default
```

Jika nama network berbeda, lihat nama sebenarnya melalui:

```bash
docker network ls
```

Container:

```text
haproxy
webserver1
webserver2
dbserver
```

harus dapat berkomunikasi dalam network Docker tersebut.

---

# 43. Mengecek HAProxy

Jalankan:

```bash
docker exec haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
```

Command ini digunakan untuk memastikan konfigurasi HAProxy valid.

---

# 44. Mengecek Webserver 1

```bash
docker logs webserver1
```

Periksa apakah Apache/PHP berjalan tanpa error fatal.

---

# 45. Mengecek Webserver 2

```bash
docker logs webserver2
```

Pastikan webserver kedua juga berjalan normal.

---

# 46. Mengecek MariaDB

Jalankan:

```bash
docker logs dbserver
```

Kemudian masuk ke database:

```bash
docker exec -it dbserver mariadb -uroot -proot123
```

Jalankan:

```sql
SHOW DATABASES;
```

Pastikan database:

```text
db_reservasi_ruangan
```

tersedia.

Keluar:

```sql
exit;
```

---

# 47. Memastikan Koneksi PHP ke MariaDB

Bagian ini penting karena sebelumnya aplikasi menggunakan:

```text
localhost
```

Sekarang konfigurasi sudah diubah menjadi:

```php
$DB_HOST = 'dbserver';
$DB_USER = 'root';
$DB_PASS = 'root123';
$DB_NAME = 'db_reservasi_ruangan';
```

Maka alurnya menjadi:

```text
webserver1
    │
    │ dbserver:3306
    ▼
MariaDB
```

dan:

```text
webserver2
    │
    │ dbserver:3306
    ▼
MariaDB
```

Kedua web server menggunakan database container yang sama.

---

# 48. Pengujian dari EC2

Tes HAProxy dari dalam EC2:

```bash
curl http://localhost:8083
```

Request akan melewati:

```text
localhost:8083
       ↓
HAProxy:8080
       ↓
Webserver1 / Webserver2
```

Jika response HTML aplikasi muncul, berarti jalur request sudah bekerja.

---

# 49. Pengujian dari Browser

Ambil Public IPv4 EC2.

Contoh:

```text
34.xxx.xxx.xxx
```

Kemudian buka:

```text
http://34.xxx.xxx.xxx:8083
```

Ganti IP dengan Public IPv4 milik EC2.

Jika semua konfigurasi berhasil, aplikasi **App Reservasi** akan tampil.

---

# 50. Pengujian Load Balancing

Karena HAProxy menggunakan:

```text
balance roundrobin
```

request akan dibagi ke dua web server.

Untuk melihat aktivitas HAProxy:

```bash
docker logs -f haproxy
```

Kemudian akses aplikasi beberapa kali melalui browser.

Log dapat digunakan untuk melihat aktivitas request dan membantu memastikan HAProxy bekerja.

Tekan:

```text
CTRL + C
```

untuk menghentikan tampilan log realtime.

---

# 51. Mengecek Log Webserver

Webserver pertama:

```bash
docker logs webserver1
```

Webserver kedua:

```bash
docker logs webserver2
```

Dengan melihat log keduanya, kita dapat mengetahui aktivitas masing-masing backend.

---

# 52. Troubleshooting — Container Tidak Berjalan

Pertama:

```bash
docker compose ps
```

Kemudian:

```bash
docker compose logs
```

Atau per container:

```bash
docker logs haproxy
docker logs webserver1
docker logs webserver2
docker logs dbserver
```

Cari error pada service yang statusnya tidak `Up`.

---

# 53. Troubleshooting — Website Tidak Bisa Dibuka

Periksa EC2:

```text
Instance state = Running
```

Pastikan Public IPv4 tersedia.

Kemudian periksa Security Group.

Pastikan:

```text
TCP 8083
0.0.0.0/0
```

tersedia.

Kemudian:

```bash
docker ps
```

Pastikan HAProxy aktif dan memiliki mapping:

```text
8083->8080
```

---

# 54. Troubleshooting — Database Connection Refused

Jika aplikasi menampilkan error seperti:

```text
SQLSTATE[HY000] [2002] Connection refused
```

periksa:

```bash
nano config/database.php
```

Pastikan:

```php
$DB_HOST = 'dbserver';
$DB_USER = 'root';
$DB_PASS = 'root123';
$DB_NAME = 'db_reservasi_ruangan';
```

**Jangan menggunakan:**

```php
$DB_HOST = 'localhost';
```

karena database berada pada container berbeda.

Kemudian pastikan:

```bash
docker compose ps
```

menunjukkan:

```text
dbserver    Up
```

---

# 55. Troubleshooting — HAProxy Tidak Menemukan Webserver

Jalankan:

```bash
docker exec haproxy getent hosts webserver1
```

Kemudian:

```bash
docker exec haproxy getent hosts webserver2
```

Jika Docker dapat melakukan resolve nama tersebut, komunikasi antar-container melalui network berjalan.

---

# 56. Troubleshooting — Database Tidak Berjalan

Cek:

```bash
docker logs dbserver
```

Kemudian:

```bash
docker compose ps
```

Pastikan `dbserver` berstatus:

```text
Up
```

---

# 57. Troubleshooting — SQL Tidak Terimport

Perlu diperhatikan bahwa:

```text
reservasi_ruangan.sql
```

dijalankan oleh MariaDB pada proses **inisialisasi database pertama kali**.

Jika volume:

```text
db_data
```

sudah berisi database sebelumnya, file SQL initialization tidak otomatis dijalankan kembali.

Jika memang ingin mengulang database dari awal dan **data lama tidak diperlukan**, dapat menggunakan:

```bash
docker compose down -v
```

Kemudian:

```bash
docker compose up -d
```

> **Perhatian:** `docker compose down -v` menghapus named volume dan data database yang tersimpan di dalamnya. Gunakan hanya ketika memang ingin menginisialisasi database kembali.

---

# 58. Mengecek Docker Volume

Jalankan:

```bash
docker volume ls
```

Cari:

```text
db_data
```

Volume tersebut digunakan untuk menyimpan data MariaDB.

---

# 59. Verifikasi Akhir

Jalankan seluruh pemeriksaan berikut:

```bash
docker compose ps
```

```bash
docker images
```

```bash
docker volume ls
```

```bash
docker network ls
```

Kemudian:

```bash
docker exec haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
```

Dan:

```bash
docker logs dbserver
```

Terakhir buka:

```text
http://PUBLIC-IP-EC2:8083
```

---

# 60. Hasil Akhir

Jika semuanya berhasil, struktur infrastrukturnya menjadi:

```text
AWS
│
└── Default VPC
    │
    └── Default Subnet
        │
        └── EC2
            │
            ├── Ubuntu 22.04 LTS
            │
            └── Docker Compose
                │
                ├── HAProxy
                │   └── :8080
                │
                ├── Webserver1
                │   └── Apache + PHP 8.2
                │       └── :80
                │
                ├── Webserver2
                │   └── Apache + PHP 8.2
                │       └── :80
                │
                └── MariaDB
                    └── :3306
                        │
                        └── db_data
```

Akses publik:

```text
http://PUBLIC-IP-EC2:8083
```

---

# 61. Alur Lengkap Sistem

Secara keseluruhan:

```text
                    INTERNET
                        │
                        ▼
                EC2 PUBLIC IP
                     :8083
                        │
                        ▼
                  ┌──────────┐
                  │ HAProxy  │
                  │  :8080   │
                  └────┬─────┘
                       │
                 Round Robin
                  ┌────┴────┐
                  ▼         ▼
             Webserver1  Webserver2
             Apache/PHP  Apache/PHP
                  │         │
                  └────┬────┘
                       │
                       ▼
                  ┌─────────┐
                  │ MariaDB │
                  │  :3306  │
                  └────┬────┘
                       │
                       ▼
                  ┌─────────┐
                  │ db_data │
                  └─────────┘
```

---

# 62. Checklist Tugas 3

Sebelum tugas dianggap selesai, pastikan:

```text
☑ Region = ap-southeast-1
☑ Menggunakan Default VPC
☑ Menggunakan Default Subnet
☑ EC2 = tugas-3-reservasi
☑ Ubuntu 22.04 LTS
☑ Instance type = t3.small
☑ Key Pair = vockey
☑ Menggunakan Shared Security Group
☑ Port 22 tersedia
☑ Port 8083 tersedia
☑ EC2 Running
☑ Status Checks 2/2 passed
☑ Public IP tersedia
☑ EC2 Instance Connect berhasil
☑ Docker terinstall
☑ Git terinstall
☑ Repository appReservasi berhasil di-clone
☑ config/database.php sudah menggunakan dbserver
☑ Dockerfile berhasil dibuat
☑ PDO MySQL berhasil dipasang melalui Dockerfile
☑ Apache rewrite berhasil diaktifkan
☑ docker-compose.yml berhasil dibuat
☑ haproxy.cfg berhasil dibuat
☑ reservasi_ruangan.sql tersedia
☑ Image appreservasi-webserver berhasil dibuat
☑ Container haproxy berjalan
☑ Container webserver1 berjalan
☑ Container webserver2 berjalan
☑ Container dbserver berjalan
☑ Docker volume db_data tersedia
☑ Database db_reservasi_ruangan tersedia
☑ HAProxy configuration valid
☑ Port mapping 8083:8080 berjalan
☑ Aplikasi dapat diakses melalui PUBLIC-IP:8083
☑ Load balancing HAProxy dapat diuji
```

---

# 63. Screenshot yang Perlu Didokumentasikan

Agar tutorial Medium terlihat seperti dokumentasi pengerjaan nyata, masukkan screenshot pada tahap-tahap penting.

### 1. Topologi

Gunakan **gambar topologi yang kamu kirim tadi**.

Letakkan setelah bagian:

> **Gambaran Arsitektur**

Caption:

> **Topologi Infrastruktur Tugas 3 — App Reservasi menggunakan Docker Compose dan HAProxy pada AWS EC2.**

### 2. EC2

Screenshot yang menunjukkan:

```text
tugas-3-reservasi
Running
Ubuntu 22.04
Public IPv4
```

### 3. Security Group

Tampilkan Shared Security Group dan rule yang relevan.

### 4. EC2 Instance Connect

Tampilkan terminal Ubuntu setelah berhasil connect.

### 5. Docker

```bash
docker --version
```

### 6. Repository

```bash
ls
```

### 7. Database Configuration

Tampilkan:

```text
config/database.php
```

dengan host:

```text
dbserver
```

### 8. Dockerfile

Tampilkan isi Dockerfile.

### 9. Docker Compose

Tampilkan `docker-compose.yml`.

### 10. HAProxy

Tampilkan `haproxy.cfg`.

### 11. Build

```bash
docker compose build
```

### 12. Container

```bash
docker compose ps
```

### 13. Database

```sql
SHOW DATABASES;
```

### 14. Volume

```bash
docker volume ls
```

### 15. HAProxy Validation

```bash
docker exec haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
```

### 16. Hasil Akhir

Screenshot browser:

```text
http://PUBLIC-IP-EC2:8083
```

yang menunjukkan aplikasi Reservasi berhasil tampil.

---

# 64. Kesimpulan

Pada Tugas 3 ini kita membangun aplikasi Reservasi secara manual di AWS EC2 menggunakan Docker Compose.

Arsitektur yang dibuat terdiri dari:

```text
HAProxy
   ↓
Webserver1 + Webserver2
   ↓
MariaDB
   ↓
Docker Volume
```

HAProxy digunakan sebagai load balancer dengan algoritma:

```text
roundrobin
```

sehingga request dapat diteruskan ke dua web server.

Hal penting lainnya adalah konfigurasi aplikasi PHP harus diarahkan ke:

```text
dbserver
```

bukan `localhost`, karena MariaDB berada di container terpisah.

Dengan Docker Compose, seluruh service dapat dijalankan dan dikelola sebagai satu kesatuan.

Hasil akhirnya adalah aplikasi Reservasi yang dapat diakses melalui:

```text
http://PUBLIC-IP-EC2:8083
```

dengan alur:

```text
User
 ↓
AWS EC2 :8083
 ↓
HAProxy :8080
 ↓
Webserver1 / Webserver2 :80
 ↓
MariaDB :3306
 ↓
Docker Volume
```
