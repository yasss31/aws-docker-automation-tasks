# LAPORAN LEMBAR KERJA PESERTA DIDIK (LKPD) 9
# CI/CD Docker Swarm dengan GitHub Actions

---

## IDENTITAS LKPD
* **Mata Pelajaran** : DevOps Engineer
* **Topik**          : CI/CD Docker Swarm dengan GitHub Actions
* **Alokasi Waktu**  : 5 x 45 menit
* **Lingkungan**     : AWS Academy Learner Lab (Cluster Swarm LKPD 8: 1 Manager + 2 Worker + 1 Dedicated DB MariaDB 11.8)
* **Repository CI/CD**: `https://github.com/yasss31/appKantin`
* **Metode Praktik** : GitHub Actions Self-Hosted Runner on Swarm Manager, Docker Hub Registry, Docker Config, Zero-Downtime Rolling Update, & Quality Gate Linting

---

## A. Capaian & Tujuan Pembelajaran

### Capaian Pembelajaran
Peserta didik mampu merancang, mengonfigurasi, dan mengoperasikan pipeline Continuous Integration dan Continuous Deployment (CI/CD) terotomatisasi menggunakan GitHub Actions untuk aplikasi web terdistribusi di atas klaster Docker Swarm pada infrastruktur cloud AWS.

### Tujuan Pembelajaran
1. Membuat `Dockerfile` dan `.dockerignore` yang efisien untuk mengemas source code aplikasi web PHP-Nginx ke dalam container image yang *portable* dan *immutable*.
2. Membangun workflow GitHub Actions (`deploy.yml`) yang mengotomatisasi proses pengujian sintaksis, build multi-tag (`latest` dan `<github.sha>`), serta penerbitan image ke Docker Hub Registry.
3. Menerapkan pemisahan konfigurasi dan rahasia dari source code (*Decoupled Secrets*) menggunakan fitur **Docker Config** Swarm (`kantin_db_php`).
4. Mengonfigurasi mekanisme deployment otomatis dengan teknik **Zero-Downtime Rolling Update** (`--update-parallelism 1 --update-delay 10s`) serta prosedur pemulihan cepat (**Instant Rollback**).
5. Mengimplementasikan **Quality Gate Pipeline** menggunakan pemeriksaan sintaks otomatis (`php -l`) untuk mencegah kegagalan aplikasi di lingkungan produksi.

---

## B. Arsitektur Pipeline & Komponen Teknis

```text
       [Developer]
            │
            │ git commit & push (branch: main)
            ▼
┌──────────────────────────────────────────────────────────────┐
│           GITHUB REPOSITORY (yasss31/appKantin)              │
│  - Dockerfile (Base: trafex/php-nginx)                       │
│  - .dockerignore (.git, .github, README.md)                  │
│  - .github/workflows/deploy.yml                             │
│  - Secrets: DOCKERHUB_USERNAME, DOCKERHUB_TOKEN              │
└──────────────────────────────┬───────────────────────────────┘
                               │ [Webhook Trigger]
                               ▼
┌──────────────────────────────────────────────────────────────┐
│       GITHUB ACTIONS RUNNER (Self-Hosted on Manager)         │
│  Labels: [self-hosted, swarm-manager]                        │
│                                                              │
│  [JOB 1: BUILD]                                              │
│  1. actions/checkout@v4                                      │
│  2. Quality Gate: Cek sintaks PHP (php -l "$f")              │
│  3. docker/setup-buildx-action@v3                            │
│  4. docker/login-action@v3 (Docker Hub Secrets)              │
│  5. docker/build-push-action@v6                              │
│     Tags: <user>/appkantin:latest & :<github.sha>            │
│                                                              │
│  [JOB 2: DEPLOY] (Needs: build)                              │
│  1. Check Service Existence (docker service inspect)         │
│  2. Execute Rolling Update via local Docker Socket:          │
│     docker service update --image ...:<sha>                  │
│       --update-parallelism 1 --update-delay 10s kantin       │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│              AWS EC2 INFRASTRUCTURE & SWARM                  │
│                                                              │
│  ┌────────────────────────┐      ┌────────────────────────┐  │
│  │     Swarm Manager      │      │     Swarm Worker 1     │  │
│  │ (Runner + Task 1)      │◄────►│ (Task 2)               │  │
│  └───────────┬────────────┘      └───────────┬────────────┘  │
│              │                               │               │
│              │          ┌────────────────┐   │               │
│              └─────────►│ Swarm Worker 2 │◄──┘               │
│                         │ (Task 3)       │                   │
│                         └────────┬───────┘                   │
│                                  │ (Port 3306 Private IP)    │
│                                  ▼                           │
│                     ┌────────────────────────┐               │
│                     │ Dedicated DB Server    │               │
│                     │ (MariaDB 11.8)         │               │
│                     └────────────────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

---

## C. Rincian Pelaksanaan Praktikum & Tugas

### 1. Langkah 1: Dockerfile & .dockerignore
Dibuat berkas `Dockerfile` berbasis `trafex/php-nginx`:
```dockerfile
FROM trafex/php-nginx
COPY --chown=nobody . /var/www/html/
```
Kode disalin dengan kepemilikan non-root `nobody:nobody` agar aman dijalankan oleh Nginx dan PHP-FPM. Berkas `.dockerignore` ditambahkan untuk mengecualikan `.git`, `.github`, dan `README.md`.

### 2. Langkah 2: Workflow CI & Registrasi Secrets
Kredensial Docker Hub disimpan pada GitHub Secrets:
* `DOCKERHUB_USERNAME`: Username Docker Hub
* `DOCKERHUB_TOKEN`: Personal Access Token (Read & Write)

Pipeline menghasilkan dua tag setiap push: `:latest` dan `:<github.sha>`.

### 3. Langkah 3 & 4: Pemisahan Konfigurasi & Inisialisasi Service
Untuk menjaga kerahasiaan password dan IP database AWS:
```bash
docker config create kantin_db_php /home/ubuntu/appKantin/config/db.php
docker service create --name kantin \
  --replicas 3 -p 8080:8080 \
  --config source=kantin_db_php,target=/var/www/html/config/db.php \
  ${DOCKERHUB_USERNAME}/appkantin:latest
```
Docker Config dimuat langsung ke filesystem container secara aman tanpa tersimpan di image.

### 4. Langkah 5 & 6: Alur CD Otomatis & Rolling Update
Pada workflow `deploy.yml`, job `deploy` dijalankan langsung di node Manager menggunakan self-hosted runner. Perintah update:
```bash
docker service update \
  --image ${DOCKERHUB_USERNAME}/appkantin:${{ github.sha }} \
  --update-parallelism 1 --update-delay 10s \
  kantin
```
Sistem memperbarui replika secara bergiliran (1 kontainer per 10 detik). Saat satu replika di-update, dua replika lainnya tetap melayani request pengguna di port 8080.

### 5. Tugas 1: Rilis Fitur Kecil (Hostname Container)
Pada file `footer.php`, ditambahkan elemen penampil hostname:
```php
<small class="text-primary font-monospace">Dilayani oleh: <?= htmlspecialchars(gethostname(), ENT_QUOTES, 'UTF-8') ?></small>
```
* **Hasil Verifikasi**: Perubahan di-push ke branch `main` (`commit 62a3b18`, run ID `39210789153`). Workflow CI/CD berhasil berjalan hijau. Saat halaman web di-refresh berulang kali, teks hostname berganti-ganti sesuai ID kontainer replika yang menangani request, membuktikan fungsi Ingress Routing Mesh round-robin bekerja sempurna.

### 6. Tugas 2: Simulasi Kode Rusak & Pembuktian Rollback
* **Skenario**: Kesalahan sintaksis sengaja dimasukkan ke dalam kode PHP (menghilangkan tanda titik koma `;` pada baris kode).
* **Temuan**: Tanpa adanya tahapan pengecekan sintaks (linting) pada pipeline CI, Docker tetap sukses mem-build image yang rusak dan mem-push-nya ke Docker Hub. Akibatnya, server men-deploy container rusak dan pengguna menerima respons HTTP 500 (Internal Server Error).
* **Solusi Pemulihan**: Aplikasi dipulihkan dalam hitungan detik menggunakan perintah:
  ```bash
  docker service rollback kantin
  ```
  Docker Swarm secara otomatis mengembalikan task container ke image SHA sebelumnya yang stabil.

### 7. Tugas 3 (Tantangan): Quality Gate Pipeline (PHP Syntax Linting)
Untuk mencegah kode rusak sampai ke server, ditambahkan tahapan linting sebelum proses build:
```yaml
- name: Cek sintaks PHP
  run: |
    for f in $(find . -name '*.php'); do
      php -l "$f" || exit 1
    done
```
* **Hasil Uji Coba**: Pada commit pengujian dengan syntax error (run ID `39214535842`), step `Cek sintaks PHP` mendeteksi error dan seketika menggagalkan job `build`. Karena job `deploy` memiliki dependensi `needs: build`, tahapan deployment otomatis dibatalkan (*aborted*), image rusak tidak dibuat, dan aplikasi di server produksi tetap berjalan normal tanpa gangguan (HTTP 200 OK).

---

## D. Jawaban Pertanyaan Refleksi

### 1. Mengapa image diberi tag `github.sha` dan tidak hanya `latest`? Apa yang sulit dilakukan jika hanya ada `latest`?
* **Jawaban**:
  1. **Auditability & Traceability**: Tag `github.sha` menautkan secara pasti versi image yang sedang berjalan di klaster dengan commit commit spesifik di Git repository.
  2. **Immutability**: Tag `latest` bersifat dinamis (*mutable*) dan dapat ditimpa sewaktu-waktu. Jika hanya menggunakan `latest`, Docker Swarm tidak dapat membedakan apakah image berubah jika nama tag-nya sama, sehingga rolling update tidak terpicu secara andal.
  3. **Kemudahan Rollback**: Jika terjadi kerusakan di produksi, administrator atau orkestrator dapat melakukan rollback instan ke SHA spesifik yang diketahui stabil. Tanpa tag unik, melacak dan menarik kembali versi lama yang bekerja menjadi sangat sulit.

### 2. Bandingkan cara ini dengan bind mount + git pull terjadwal (LKPD 8). Sebutkan 2 keunggulan dan 1 kekurangan memakai image!
* **Jawaban**:
  * **Keunggulan 1 (Portabilitas & Konsistensi Dependensi)**: Seluruh runtime, ekstensi PHP, konfigurasi Nginx, dan kode terbungkus rapi dalam satu artefak mandiri (*container image*). Tidak ada risiko perbedaan environment antar node worker.
  * **Keunggulan 2 (Zero-Downtime & Multi-Node Distribution)**: Node worker tidak perlu memiliki akses SSH atau Git ke repository privat untuk menarik kode. Swarm mendistribusikan image secara otomatis ke seluruh node klaster melalui container registry.
  * **Kekurangan**: Memerlukan waktu build image dan transmisi jaringan (*push/pull*) ke Docker Hub untuk setiap perubahan kode, dibandingkan metode bind mount lokal yang langsung terlihat seketika.

### 3. Mengapa `config/db.php` disimpan sebagai Docker config dan tidak dimasukkan ke image atau repository?
* **Jawaban**:
  Sesuai prinsip **The Twelve-Factor App (III. Config)**: Kredensial (seperti IP private database, username, dan password) tidak boleh pernah dimasukkan ke dalam version control maupun image container publik. Jika file tersebut masuk ke image di Docker Hub yang bersifat publik, rahasia database akan terekspos. Menggunakan **Docker Config** memastikan rahasia tetap berada di lingkungan server Swarm yang aman dan di-mount secara in-memory ke path yang dibutuhkan kontainer.

### 4. Apa risiko membuka port 22 untuk `0.0.0.0/0`? Bagaimana self-hosted runner pada node manager dapat menghindari kebutuhan ini?
* **Jawaban**:
  * **Risiko Port 22 Publik**: Membuka port SSH ke `0.0.0.0/0` mengekspos instance ke seluruh internet, memicu serangan *brute force*, eksploitasi celah zero-day SSH, dan pemindaian port otomatis dari bot berbahaya.
  * **Solusi Self-Hosted Runner**: Runner terinstal langsung di dalam node manager dan berkomunikasi ke GitHub menggunakan koneksi keluar (*outbound HTTPS polling* port 443). Dengan demikian, Security Group tidak perlu membuka port 22 ke publik sama sekali; seluruh eksekusi deployment Swarm berjalan lokal melalui unix socket `docker.sock`.

### 5. Jelaskan mana yang disebut CI dan mana yang CD pada workflow ini!
* **Jawaban**:
  * **CI (Continuous Integration)**: Tahap pada job `build` yang mencakup checkout kode, validasi sintaks otomatis (`php -l`), penyiapan Buildx, kompilasi image Docker, dan penerbitan image ke Docker Hub. Tujuannya memastikan kode terintegrasi dan siap rilis.
  * **CD (Continuous Deployment)**: Tahap pada job `deploy` yang mengambil artefak image hasil CI (`appkantin:<github.sha>`) dan secara otomatis menerapkannya ke klaster produksi Docker Swarm menggunakan teknik rolling update bertahap tanpa intervensi manual.

### 6. Pada Tugas 2, mengapa Swarm tidak otomatis rollback walaupun aplikasi rusak? Apa yang perlu ditambahkan agar kerusakan terdeteksi sebelum atau saat deploy?
* **Jawaban**:
  * **Penyebab**: Docker Swarm secara default hanya memantau status kesehatan level proses container (apakah process PID 1 / Nginx masih berjalan). Pada kasus syntax error PHP, web server Nginx tetap berhasil menyala dan tidak crash (exit 0), meskipun mengembalikan halaman error HTTP 500 kepada pengguna. Karena kontainer berstatus `running`, Swarm menganggap tugas berjalan sehat.
  * **Solusi**:
    1. **Quality Gate di CI**: Menambahkan step linting sintaks (`php -l`) sebelum image dibuat (telah berhasil diterapkan di Tugas 3).
    2. **Docker Healthcheck**: Menambahkan instruksi `HEALTHCHECK` pada `Dockerfile` atau saat membuat service (`--health-cmd "curl -f http://localhost:8080/ || exit 1"`). Jika healthcheck gagal, Swarm akan mendeteksi status `unhealthy` dan dapat memicu `--update-failure-action rollback` secara otomatis.

---

## E. Kesimpulan Praktikum
Praktikum LKPD 9 berhasil membuktikan implementasi alur DevOps modern berbasis CI/CD pipeline pada klaster Docker Swarm di AWS. Seluruh alur mulai dari quality gate sintaksis, pembuatan image immutable ber-tag SHA commit, pemisahan konfigurasi via Docker Config, hingga otomatisasi deployment zero-downtime rolling update dan verifikasi rollback telah berjalan sempurna dan tervalidasi penuh.
