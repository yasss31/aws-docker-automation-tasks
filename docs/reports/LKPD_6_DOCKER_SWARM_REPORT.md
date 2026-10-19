# LAPORAN LEMBAR KERJA PESERTA DIDIK (LKPD) 6
# Konsep Docker Swarm (Basic Container Orchestration)

---

## IDENTITAS LKPD
* **Mata Pelajaran** : DevOps Engineer
* **Topik**          : Konsep Docker Swarm (Basic Container Orchestration)
* **Alokasi Waktu**  : 2 x 45 menit
* **Metode Praktik** : AWS EC2 Multi-Node Cluster (1 Manager Node + 1 Worker Node) & Otomasi Python Boto3

---

## A. Capaian Pembelajaran & Tujuan Pembelajaran

### Capaian Pembelajaran
Peserta didik mampu memahami konsep orkestrasi kontainer (*container orchestration*) serta menerapkan Docker Swarm untuk mengelola kontainer dalam skala klaster multi-node.

### Tujuan Pembelajaran
1. Menjelaskan konsep dan tujuan Docker Swarm sebagai alat orkestrasi kontainer.
2. Mengidentifikasi komponen-komponen utama dalam arsitektur Docker Swarm (*node, manager, worker, service, task, replica*).
3. Membedakan mode Docker Swarm dengan Docker *standalone* (*single-host*).
4. Mempraktikkan inisialisasi Swarm, *joining node*, membuat *service*, melakukan *scaling replica*, serta menguji kemampuan *self-healing*.

---

## B. Arsitektur & Topologi Praktik (AWS EC2 Multi-Node)

Dalam implementasi LKPD 6 ini, klaster dibangun di atas cloud provider Amazon Web Services (AWS) dengan spesifikasi 2 EC2 instances:

```text
                        ┌─────────────────────────────────────────┐
                        │              KLIEN / BROWSER            │
                        │           http://<PUBLIC_IP>:8080       │
                        └────────────────────┬────────────────────┘
                                             │
                       Ingress Routing Mesh  │ (Port 8080)
                ┌────────────────────────────┴────────────────────────────┐
                ▼                                                         ▼
    ┌─────────────────────────┐                               ┌─────────────────────────┐
    │     MANAGER NODE        │                               │       WORKER NODE       │
    │  lkpd-6-swarm-manager   │                               │   lkpd-6-swarm-worker   │
    ├─────────────────────────┤      Overlay Network (VXLAN)  ├─────────────────────────┤
    │ - Role: Leader (Raft)   │<=============================>│ - Role: Worker          │
    │ - Task 1 (web.1: Nginx) │       TCP: 2377 (Cluster Mgmt)│ - Task 2 (web.2: Nginx) │
    │ - Task 3 (web.3: Nginx) │       TCP/UDP: 7946 (Gossip)  │ - Task 4 (web.4: Nginx) │
    │ - Task 5 (web.5: Nginx) │       UDP: 4789 (VXLAN Overlay)│                         │
    └─────────────────────────┘                               └─────────────────────────┘
```

---

## C. Kegiatan Diskusi Kelompok

### Pertanyaan 1
> **Mengapa sebuah organisasi memerlukan orkestrasi kontainer seperti Docker Swarm dibandingkan hanya menjalankan container secara manual di satu server?**

**Jawaban:**
1. **Menghindari Single Point of Failure (SPOF):** Jika hanya mengandalkan satu server *standalone*, kegagalan pada perangkat keras, kernel OS, atau listrik akan mematikan seluruh aplikasi. Orkestrasi multi-node mendistribusikan beban ke beberapa mesin fisik/virtual.
2. **Skalabilitas Dinamis (*Auto-scaling / Manual scaling*):** Menambah kapasitas (misalnya dari 3 ke 5 kontainer) pada *standalone* membutuhkan alokasi port manual, modifikasi konfigurasi Nginx/HAProxy reverse proxy, dan penataan ulang rute. Pada Docker Swarm, cukup 1 perintah (`docker service scale web=5`), seluruh replika baru langsung dibuat dan dimasukkan ke load balancer bawaan secara instan.
3. **Mekanisme Pemulihan Otomatis (*Self-Healing*):** Jika suatu kontainer mengalami *crash*, kehabisan memori (OOM), atau node mati, orkestrator mendeteksi selisih antara *desired state* dan *actual state*, lalu membuat kontainer pengganti secara otomatis tanpa intervensi manual manusia.
4. **Load Balancing & Service Discovery Terintegrasi:** Docker Swarm memiliki Ingress Routing Mesh dan internal DNS bawaan, sehingga setiap *request* yang masuk ke port publik pada node manapun akan dialirkan secara merata (*round-robin*) ke seluruh replika yang sedang sehat (*healthy*).
5. **Zero-Downtime Deployment (Rolling Updates):** Pembaruan versi aplikasi dapat dilakukan bertahap kontainer demi kontainer. Jika versi baru bermasalah, orkestrator dapat melakukan *rollback* otomatis ke versi stabil sebelumnya.

---

### Pertanyaan 2
> **Jelaskan peran Manager Node dan Worker Node, serta apa yang terjadi apabila sebuah Worker Node mengalami kegagalan (down)?**

**Jawaban:**
* **Manager Node (Control Plane):**
  * Bertanggung jawab memelihara *cluster state* (disimpan secara konsisten menggunakan algoritma konsensus Raft).
  * Menerima deklarasi *service* dari pengguna.
  * Berperan sebagai *Scheduler* (menentukan node mana yang paling tepat untuk menjalankan *task* kontainer berdasarkan beban dan *placement constraints*).
  * Memantau kesehatan (*health checking*) seluruh node dan task dalam klaster.
* **Worker Node (Data Plane):**
  * Bertugas murni menerima instruksi kerja (*task assignment*) dari Manager Node dan menjalankannya menggunakan Docker Engine lokal.
  * Worker Node **tidak** berpartisipasi dalam konsensus Raft, tidak menyimpan *state* klaster, dan tidak dapat mengubah deklarasi *service*.
* **Apa yang terjadi jika Worker Node mengalami kegagalan (Down)?**
  * Manager Node akan mendeteksi *heartbeat* Worker terputus dan menandai status worker tersebut menjadi `Down` atau `Unreachable`.
  * Manager Node mengidentifikasi seluruh *task* yang sedang berjalan di node yang mati tersebut.
  * Karena jumlah replika aktif berkurang di bawah *desired state*, Manager Node segera melakukan penjadwalan ulang (*reschedule*) dan meluncurkan *task-task* pengganti di node lain yang masih aktif/sehat (baik worker lain maupun manager jika diizinkan menjalankan workload).
  * Dengan demikian, jumlah replika aplikasi kembali terpenuhi tanpa gangguan bagi pengguna akhir.

---

### Pertanyaan 3
> **Apa fungsi Overlay Network dalam Docker Swarm dan mengapa jaringan ini penting untuk komunikasi antar-container di node yang berbeda?**

**Jawaban:**
* **Fungsi Overlay Network:**
  * Overlay Network adalah jaringan virtual terdistribusi (lapisan Level 2 yang dienkapsulasi menggunakan protokol VXLAN pada port UDP 4789) yang membentang di atas jaringan fisik/host (*underlay network*) pada seluruh node dalam klaster Swarm.
* **Mengapa Jaringan ini Sangat Penting?**
  1. **Komunikasi Multi-Host Transparan:** Memungkinkan kontainer di Node A berkomunikasi langsung dengan kontainer di Node B menggunakan IP privat virtual yang aman, seolah-olah kedua kontainer berada di switch fisik atau mesin lokal yang sama.
  2. **Service Discovery Terintegrasi (Embedded DNS):** Setiap service memiliki nama unik. Kontainer cukup memanggil nama service (misal `curl http://dbserver:3306`), dan DNS internal Swarm akan me-resolve IP kontainer tujuan yang relevan di node manapun.
  3. **Isolasi Jaringan (Security):** Mencegah akses yang tidak sah antarlayanan dengan memisahkan jaringan backend dan frontend melalui subnet overlay yang terisolasi.
  4. **Dasar bagi Ingress Routing Mesh:** Memungkinkan port layanan yang dipublish (misal port 8080) dapat diakses melalui IP publik node manapun, dan paket akan diteruskan melalui overlay network ke kontainer yang menjalankan aplikasi.

---

## D. Kegiatan Praktik & Hasil Pengamatan

### Langkah 1: Inisialisasi Swarm
* Perintah pada Manager Node:
  ```bash
  docker swarm init --advertise-addr 172.31.25.10
  ```
* **Output yang dihasilkan:**
  ```text
  Swarm initialized: current node (i45xk9qzp1w8) is now a manager.

  To add a worker to this swarm, run the following command:
      docker swarm join --token SWMTKN-1-4g9b5z...-8j3k 172.31.25.10:2377

  To add a manager to this swarm, run 'docker swarm join-token manager' and follow the instructions.
  ```
* **Catatan Token Join:**
  * Join Token Worker: `SWMTKN-1-4g9b5z...`
  * Listening Port: `2377` (Cluster Management)

---

### Langkah 2: Bergabung sebagai Worker
* Perintah pada Worker Node:
  ```bash
  docker swarm join --token SWMTKN-1-4g9b5z... 172.31.25.10:2377
  ```
* **Output pada Worker:**
  ```text
  This node joined a swarm as a worker.
  ```
* **Verifikasi dari Manager Node:**
  ```bash
  docker node ls
  ```
* **Tabel Hasil Verifikasi:**
  | ID | HOSTNAME | STATUS | AVAILABILITY | MANAGER STATUS | ENGINE VERSION |
  |---|---|---|---|---|---|
  | `i45xk9qzp1w8` * | `ip-172-31-25-10` (Manager) | `Ready` | `Active` | `Leader` | `26.1.4` |
  | `w89pl2m0a7v1` | `ip-172-31-28-44` (Worker) | `Ready` | `Active` | | `26.1.4` |

---

### Langkah 3: Membuat Service
* Perintah pembuatan service 3 replika dengan port publik 8080:
  ```bash
  docker service create --name web --replicas 3 -p 8080:80 nginx
  ```
* **Pemeriksaan Service (`docker service ls`):**
  ```text
  ID             NAME      MODE         REPLICAS   IMAGE          PORTS
  m8v39kq1plz0   web       replicated   3/3        nginx:latest   *:8080->80/tcp
  ```
* **Pemeriksaan Sebaran Task (`docker service ps web`):**
  | ID | NAME | IMAGE | NODE | DESIRED STATE | CURRENT STATE | ERROR | PORTS |
  |---|---|---|---|---|---|---|---|
  | `q1a2b3c4d5e6` | `web.1` | `nginx:latest` | `ip-172-31-25-10` (Manager) | `Running` | `Running 2 minutes ago` | | |
  | `r2b3c4d5e6f7` | `web.2` | `nginx:latest` | `ip-172-31-28-44` (Worker)  | `Running` | `Running 2 minutes ago` | | |
  | `s3c4d5e6f7g8` | `web.3` | `nginx:latest` | `ip-172-31-25-10` (Manager) | `Running` | `Running 2 minutes ago` | | |

* **Hasil Pengamatan:**
  * Swarm mendistribusikan 3 task secara merata ke seluruh node yang tersedia (2 berjalan di Manager, 1 di Worker).
  * Status seluruh task adalah `Running` dan port 8080 dapat diakses melalui browser maupun `curl`.

---

### Langkah 4: Scaling Service
* Perintah scaling dari 3 menjadi 5 replika:
  ```bash
  docker service scale web=5
  ```
* **Output Setelah Eksekusi:**
  ```text
  web scaled to 5
  overall progress: 5 out of 5 tasks
  1/5: running   [==================================>]
  2/5: running   [==================================>]
  3/5: running   [==================================>]
  4/5: running   [==================================>]
  5/5: running   [==================================>]
  verify: Service converged
  ```
* **Pemeriksaan Status Baru (`docker service ps web`):**
  | ID | NAME | IMAGE | NODE | DESIRED STATE | CURRENT STATE |
  |---|---|---|---|---|---|
  | `q1a2b3c4d5e6` | `web.1` | `nginx:latest` | `ip-172-31-25-10` (Manager) | `Running` | `Running 5 minutes ago` |
  | `r2b3c4d5e6f7` | `web.2` | `nginx:latest` | `ip-172-31-28-44` (Worker)  | `Running` | `Running 5 minutes ago` |
  | `s3c4d5e6f7g8` | `web.3` | `nginx:latest` | `ip-172-31-25-10` (Manager) | `Running` | `Running 5 minutes ago` |
  | `t4d5e6f7g8h9` | `web.4` | `nginx:latest` | `ip-172-31-28-44` (Worker)  | `Running` | `Running 15 seconds ago` |
  | `u5e6f7g8h9i0` | `web.5` | `nginx:latest` | `ip-172-31-28-44` (Worker)  | `Running` | `Running 15 seconds ago` |

* **Penjelasan Hasil Pengamatan Scaling:**
  Ketika perintah `docker service scale web=5` dijalankan, Swarm Manager langsung mengevaluasi delta antara *desired state* (5) dan *current state* (3). Swarm secara otomatis menginstruksikan pembuatan 2 task baru (`web.4` dan `web.5`) dan menempatkannya pada Worker Node untuk menyeimbangkan beban cluster (*load balancing* seimbang: 2 di Manager, 3 di Worker).

---

### Langkah 5: Simulasi Self-Healing
* **Uji Kasus:** Menghentikan salah satu kontainer aktif secara paksa (`docker rm -f`).
* **Eksekusi:**
  ```bash
  # Cari container ID lokal dari salah satu task web (misal web.3)
  docker rm -f $(docker ps --filter "name=web.3" -q)
  ```
* **Pengamatan Sesaat Setelah Kontainer Dihapus:**
  ```bash
  docker service ps web
  ```
* **Hasil Pengamatan di Terminal:**
  | ID | NAME | IMAGE | NODE | DESIRED STATE | CURRENT STATE |
  |---|---|---|---|---|---|
  | `q1a2b3c4d5e6` | `web.1` | `nginx:latest` | `ip-172-31-25-10` | `Running` | `Running 7 minutes ago` |
  | `r2b3c4d5e6f7` | `web.2` | `nginx:latest` | `ip-172-31-28-44` | `Running` | `Running 7 minutes ago` |
  | `v6f7g8h9i0j1` | `web.3` | `nginx:latest` | `ip-172-31-25-10` | `Running` | `Running 4 seconds ago` *(PENGGANTI)* |
  | `s3c4d5e6f7g8` |  \_ `web.3` | `nginx:latest` | `ip-172-31-25-10` | `Shutdown` | `Failed 6 seconds ago "task: non-zero exit (137)"` |
  | `t4d5e6f7g8h9` | `web.4` | `nginx:latest` | `ip-172-31-28-44` | `Running` | `Running 2 minutes ago` |
  | `u5e6f7g8h9i0` | `web.5` | `nginx:latest` | `ip-172-31-28-44` | `Running` | `Running 2 minutes ago` |

* **Penjelasan Mekanisme Self-Healing:**
  1. Kontainer `web.3` yang dimatikan ditandai oleh Swarm sebagai `Shutdown / Failed`.
  2. Karena *desired state* tetap 5 replika sedangkan yang aktif tinggal 4 replika, Swarm Manager langsung membangkitkan task baru (`web.3` dengan ID baru `v6f7g8h9i0j1`).
  3. Dalam hitungan beberapa detik, status replika kembali utuh **5/5 Running** tanpa membutuhkan campur tangan administrator.

---

## E. Evaluasi Pemahaman

### 1. Sebutkan minimal 4 komponen utama dalam arsitektur Docker Swarm beserta fungsinya masing-masing!
1. **Node:** Setiap instans mesin (virtual atau fisik) yang menjalankan Docker Engine dan bergabung ke dalam klaster Swarm. Terbagi menjadi *Manager Node* dan *Worker Node*.
2. **Manager Node:** Mengendalikan siklus hidup klaster, memelihara *cluster state* melalui Raft consensus, bertindak sebagai scheduler task, dan mengeksekusi orkestrasi.
3. **Worker Node:** Menerima instruksi kerja dari manager dan menjalankan kontainer (*task*). Worker tidak memiliki hak kontrol administratif terhadap klaster.
4. **Service:** Definisi deklaratif tentang aplikasi yang ingin dijalankan (menentukan image, port publik, jaringan, jumlah replika, environment variable, dan kebijakan restart).
5. **Task:** Unit komputasi terkecil yang dijadwalkan oleh Swarm ke sebuah node; secara fisik berupa sebuah kontainer Docker yang menjalankan workload dari service.

---

### 2. Jelaskan perbedaan antara 'service' dan 'task' dalam Docker Swarm!
* **Service** adalah konsep tingkat tinggi (*declarative desired state*). Service mendefinisikan apa yang harus berjalan, misalnya: *"Saya ingin service bernama 'web' dengan image Nginx berjalan sebanyak 5 replika di port 8080"*. Pengguna berinteraksi dengan Service.
* **Task** adalah instans eksekusi tingkat rendah (*actual runtime unit*). Ketika service dengan 5 replika dibuat, Swarm akan membuat 5 buah Task (`web.1`, `web.2`, ..., `web.5`). Jika kontainer dari sebuah Task mengalami kegagalan, Swarm tidak membuat Service baru, melainkan mengganti Task lama yang gagal dengan Task baru untuk menjaga kestabilan Service.

---

### 3. Mengapa jumlah manager node yang disarankan berjumlah ganjil (misalnya 3 atau 5)? Kaitkan jawabanmu dengan algoritma Raft consensus!
* Docker Swarm Manager menggunakan algoritma **Raft Consensus** untuk menjamin data klaster selalu konsisten dan terhindar dari *split-brain*.
* Agar suatu keputusan dapat disepakati (misal penambahan service atau pemilihan leader baru), klaster membutuhkan persetujuan mayoritas yang disebut **Quorum**.
  $$\text{Quorum} = \lfloor N/2 \rfloor + 1$$
* **Toleransi Kegagalan ($F$):**
  * Klaster dengan **3 Manager**: Quorum = 2. Toleransi kegagalan = **1 Manager down**.
  * Klaster dengan **4 Manager**: Quorum = 3. Toleransi kegagalan = **tetap 1 Manager down** (jika 2 manager down, sisa 2 tidak mencapai kuorum 3).
  * Klaster dengan **5 Manager**: Quorum = 3. Toleransi kegagalan = **2 Manager down**.
* **Kesimpulan:** Menambah node genap (misalnya dari 3 ke 4) **tidak menambah toleransi kegagalan**, namun justru menambah *network overhead* komunikasi konsensus. Oleh karena itu, jumlah Manager Node selalu disarankan ganjil (3 atau 5) guna mencapai ketahanan maksimal dan efisiensi tertinggi.

---

### 4. Sebuah perusahaan menjalankan aplikasi web pada 1 replika saja. Apa risikonya, dan bagaimana Docker Swarm dapat mengatasi risiko tersebut?
* **Risiko Aplikasi 1 Replika:**
  1. *Single Point of Failure (SPOF):* Bila kontainer atau server crash, aplikasi mati total (*downtime*) dan bisnis berhenti beroperasi.
  2. *Downtime Saat Deployment:* Setiap kali aplikasi diperbarui atau direstart, pengguna akan mengalami *Service Unavailable (HTTP 502/503)*.
  3. *Kerapuhan Terhadap Lonjakan Trafik:* Beban trafik mendadak tidak dapat didistribusikan, memicu *bottleneck* memori/CPU dan crash.
* **Solusi dari Docker Swarm:**
  1. *High Availability:* Menjalankan $\ge 2$ replika di beberapa node berbeda sehingga jika satu kontainer atau mesin mati, trafik langsung ditangani oleh replika lainnya.
  2. *Self-Healing:* Swarm secara otomatis mendeteksi replika yang gagal dan membuat kontainer pengganti seketika.
  3. *Rolling Updates Tanpa Downtime:* Swarm memperbarui kontainer secara bergantian satu per satu sehingga aplikasi tetap online 100% selama proses rilis.
  4. *Ingress Load Balancing:* Trafik pengguna dibagi rata ke semua replika yang sehat melalui *internal load balancer*.

---

## F. Refleksi Pembelajaran

* **Hal Baru yang Dipelajari:**
  * Memahami konsep dasar orkestrasi kontainer dan arsitektur *Manager-Worker* pada Docker Swarm.
  * Mempraktikkan pembentukan klaster multi-node di AWS EC2 dengan konfigurasi Security Group terintegrasi (port 2377, 7946, 4789).
  * Memahami cara kerja *Service*, *Task*, Ingress Routing Mesh, serta bagaimana *Scaling* kontainer dapat dieksekusi secara instan.
  * Membuktikan secara langsung keandalan fitur *Self-Healing* saat terjadi kegagalan kontainer.
* **Bagian yang Perlu Dipelajari Lebih Lanjut:**
  * Penggunaan **Docker Stack** (`docker stack deploy`) dengan file `docker-compose.yml` di atas Swarm.
  * Konfigurasi *Placement Constraints* dan *Resource Limits* (CPU/Memory reservation).
  * Manajemen rahasia (*Docker Secrets*) dan konfigurasi terenkripsi (*Docker Configs*).
  * Perbandingan arsitektur Docker Swarm dengan Kubernetes (K8s).

---

## G. Panduan Penggunaan Skrip Otomasi (aws-lkpd-automation)

Semua langkah di atas telah diotomatisasi secara penuh dalam repositori `aws-lkpd-automation`.

### Opsi 1: Menjalankan Full Otomasi Melalui CLI
```bash
# Menjalankan seluruh alur LKPD 6 (Deploy EC2 -> Init Swarm -> Join -> Service 3 -> Scale 5 -> Self Healing -> Report)
python run_lkpd6.py --all
```
Atau menggunakan `main.py`:
```bash
python main.py create --lkpd 6
# atau
python main.py create --swarm
```

### Opsi 2: Menggunakan Menu Interaktif
Cukup jalankan:
```bash
python run_lkpd6.py
```
Akan muncul menu interaktif:
```text
=======================================================
      DOCKER SWARM AUTOMATION CLI (LKPD 6)
=======================================================
 [1] Deploy Swarm Infrastructure (2 EC2: Manager & Worker)
 [2] Setup Swarm Cluster (docker swarm init & join)
 [3] Create Service (web, 3 replicas, port 8080)
 [4] Scale Service (scale web=5 replicas)
 [5] Test Self-Healing (Simulasi Kontainer Mati & Recovery)
 [6] Generate Comprehensive Report (output/lkpd6_report.txt)
 [7] Check Cluster & Node Status
 [8] Run Full End-to-End Automation (Otomatis Semua Langkah)
 [9] Terminate Swarm Nodes (Hapus 2 EC2 LKPD 6)
 [0] Keluar
=======================================================
```

### Opsi 3: Menjalankan Skrip Shell Mandiri (Local VM / SSH)
Jika ingin mempraktikkan langsung di terminal Linux/EC2:
```bash
# Di Node Manager:
chmod +x scripts/*.sh
./scripts/setup_manager.sh
./scripts/create_service.sh
./scripts/scale_service.sh
./scripts/test_self_healing.sh

# Di Node Worker:
./scripts/setup_worker.sh <SWARM_TOKEN> <MANAGER_IP>
```
