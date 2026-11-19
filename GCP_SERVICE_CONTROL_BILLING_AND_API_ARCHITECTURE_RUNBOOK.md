# 🌐 GCP SERVICE CONTROL BILLING INCIDENT, API GATEWAY ARCHITECTURE, & TRANSACTIONAL ENGINE RUNBOOK
> **Path**: `/Users/avocado/tokobuah/infra-stuff/GCP_SERVICE_CONTROL_BILLING_AND_API_ARCHITECTURE_RUNBOOK.md`  
> **Classification**: Incident Post-Mortem, SRE Knowledge Base, & Architectural Engineering Guide  
> **Target Audience**: SREs, Platform Engineers, Backend Developers, Frontend Engineers, & AI Agents  
> **Status**: Approved & Active Production Runbook  
> **Governing Guardrails**: Strict Secret Masking, Zero Deletion Without Permission, Production Freeze Protocol.

---

## 📑 DAFTAR ISI
1. [Ringkasan Eksekutif & Tujuan Sesi](#1-ringkasan-eksekutif--tujuan-sesi)
2. [Topologi & Komponen Terkait](#2-topologi--komponen-terkait)
3. [Catatan Perubahan & Kronologi Implementasi](#3-catatan-perubahan--kronologi-implementasi)
4. [Caveats, Gotchas, & Root Cause Analysis (RCA)](#4-caveats-gotchas--root-cause-analysis-rca)
5. [Standard Operating Procedure (SOP) & Runbook Operasional](#5-standard-operating-procedure-sop--runbook-operasional)
   - [5.1 Diagnostik & Monitoring Billing GCP Service Control](#51-diagnostik--monitoring-billing-gcp-service-control)
   - [5.2 Mitigasi & Optimasi Frontend Admin Panel](#52-mitigasi--optimasi-frontend-admin-panel)
   - [5.3 Arsitektur Asynchronous Server-Side Export (Backend Go + GCS + Redis)](#53-arsitektur-asynchronous-server-side-export-backend-go--gcs--redis)
   - [5.4 Standarisasi In-House WebSocket Game Engine & DevOps Readiness](#54-standarisasi-in-house-websocket-game-engine--devops-readiness)
   - [5.5 Audit & Health-Check BullMQ Registration Queue](#55-audit--health-check-bullmq-registration-queue)
   - [5.6 Prosedur Verifikasi Data Referral BigQuery](#56-prosedur-verifikasi-data-referral-bigquery)
6. [Guardrails & Batasan Keamanan Khusus](#6-guardrails--batasan-keamanan-khusus)

---

## 1. RINGKASAN EKSEKUTIF & TUJUAN SESI

Sesi investigasi, forensik teknis, dan perancangan arsitektur ini dipicu oleh dua prioritas operasional utama:
1. **Insiden Lonjakan Tagihan Tak Terduga pada Google Cloud Platform (GCP)**:  
   Invoice pada GCP project `tokobuah-production` melonjak dari baseline rata-rata **~$5/hari** menjadi **~$40+/hari** ($221.52 per 18 Oktober, mencapai $289.11 per 20 Oktober). Kategori layanan di Google Cloud Console tercatat sebagai **"Apigee API Platform"**, namun investigasi mendalam membuktikan bahwa sumber biaya riil berasal dari SKU **`Google Service Control - Operations` (SKU ID: `F31D-9645-41B5`)** dengan volume panggilan mencapai **75,839,035 operasi** (ditagih $3.00 per 1M operasi setelah batas gratis 2M/bulan).
2. **Insiden Registrasi Member Drop & Pemantauan Antrean BullMQ**:  
   Adanya keluhan registrasi player yang gagal/tercecer (contoh kasus member `ayunieka20`), yang mengharuskan deployment sistem monitoring serverless otomatis untuk memantau status antrean BullMQ dan menyiarkan peringatan ke kanal operasional Telegram.

### Hasil Temuan Kunci (Root Cause Summary):
- **ESPv2 Sidecar Reporting Loop**:  
  Seluruh request menuju API gateway multi-tenant (`transactional.tokobuahapi.store`) melewati Google Cloud Endpoints ESPv2 proxy (`gcr.io/endpoints-release/endpoints-runtime:2`). Setiap request HTTP secara default memicu pelaporan telemetri dan audit kuota ke `servicecontrol.googleapis.com`.
- **Pelaku Bukan Traffic Pemain / Eksternal**:  
  Dari sampling log audit, traffic genuine player hanya mencakup **1.5%**. Sebaliknya, **84.4% volume panggilan berasal dari User-Agent `node`** yang keluar melalui satu IP Google Cloud NAT (`34.1.138.144`). Ini merupakan panggilan internal dari SSR API routes Next.js pada repo `admin-panel`.
- **Regresi Kode pada `admin-panel` Release `v0.0.67` & `v0.0.69`**:  
  - Di file `member-game-daily.tsx` dan `run-with-concurrency.ts`, ekspor data diubah menjadi looping sequential dengan potongan sangat kecil (`limit=100`). Untuk mengekspor 50.000 baris, satu aksi CS memicu **500 HTTP call terpisah** ke backend.
  - Batasan keamanan halaman (`TX_MAX_PAGES = 20` dan `maxPages = 100`) dihapus menjadi perulangan tanpa batas (`for (let page = 0; ; page++)`).
  - Ditemukan pola anti-pattern **N+1 Query Loop** di `src/app/api/admin/players/route.ts` yang memanggil `/admin/players/{id}/bank-accounts` untuk setiap player (hingga puluhan ribu pemanggilan API serial).
  - Background polling pada `notifications-provider.tsx` berjalan setiap 5 detik ke 3 endpoint berat (`/transactions?limit=200`, `/manual-transactions?limit=200`, `/kyc/documents`) tanpa mengecek status visibilitas tab browser (`document.hidden`). Dengan 50+ tab CS yang terbuka selama 24 jam di 11 tenant, tercipta badai jutaan request per hari.

### Keputusan Strategis yang Diambil:
1. **Frontend Optimization**: Menghidupkan kembali hard-cap pagination, menaikkan chunk export ke `limit=1000` s/d `2000`, serta menerapkan Smart Polling berbasis Page Visibility API.
2. **Server-Side Asynchronous Export Pipeline**: Merombak pola ekspor data dari browser-driven pagination menjadi job asinkron di backend Go (`transactional-engine-go`) yang men-stream data database cursor (`rows.Next()`) langsung ke Google Cloud Storage (GCS) melalui `io.Pipe()`, menghasilkan GCS Signed URL, dan dipantau via Redis job status.
3. **Automasi BullMQ Serverless Alerting**: Membangun dan mendeploy Cloud Run Job `registration-bullmq-monitor` yang dipicu setiap 5 menit oleh Cloud Scheduler menuju Telegram Supergroup **"It tok"** (Thread: **Backend Core**).
4. **DevOps Readiness untuk In-House WebSocket Game Engine**: Menyusun standar arsitektur koneksi persisten (GKE Ingress BackendConfig timeout 24 jam, bypass ESPv2, tuning socket Linux kernel, HPA berbasis connection metric, dan Redis pub/sub backplane).

---

## 2. TOPOLOGI & KOMPONEN TERKAIT

Arsitektur sistem yang diaudit mencakup interaksi multi-cluster GKE, serverless compute, database relasional, antrean pesan, dan gateway API.

```mermaid
flowchart TD
    subgraph ClientAndAdmin ["Client & Administrative Tier"]
        PlayerWeb["Player Web Frontend<br/>(user-site)"]
        AdminUI["CS / Admin Panel<br/>(Cloud Run SSR Next.js)"]
        NAT["Cloud NAT Gateway<br/>IP: 34.1.138.144"]
        AdminUI --> NAT
    end

    subgraph GCPInfrastructure ["GCP Project: tokobuah-production"]
        subgraph GKECluster ["GKE Clusters: prod-client-cluster / prod-core-cluster"]
            Ingress["GKE Ingress / Cloud Load Balancing"]
            
            subgraph PodMultiTenant ["11 Tenant Namespaces (33 Pods)"]
                ESPv2["ESPv2 Proxy Container<br/>gcr.io/endpoints-release/endpoints-runtime:2"]
                NewBackend["Transactional Engine<br/>(new-backend Go / Port 8080)"]
                ESPv2 -->|Localhost Reverse Proxy| NewBackend
            end
            
            Ingress --> ESPv2
        end
        
        ServiceControl["Google Service Control API<br/>(servicecontrol.googleapis.com)<br/>SKU: F31D-9645-41B5 ($3/1M ops)"]
        ESPv2 -.->|Report Operations & Telemetry| ServiceControl
        
        subgraph StorageAndData ["Data & Caching Tier"]
            CloudSQL["PostgreSQL OLTP<br/>(Cloud SQL / HAProxy)"]
            RedisCore["Redis Memorystore<br/>(Session, Cache, BullMQ)"]
            GCSBucket["Google Cloud Storage (GCS)<br/>Reports & Export Artifacts"]
            BigQuery["BigQuery Data Warehouse<br/>Dataset: game_reports"]
        end
        
        NewBackend --> CloudSQL
        NewBackend --> RedisCore
        NewBackend --> GCSBucket
    end

    subgraph AlertingAndMonitoring ["Monitoring & Alerting Subsystem"]
        Scheduler["Cloud Scheduler<br/>trigger-registration-bullmq-monitor<br/>(Cron: */5 * * * *)"]
        RunJob["Cloud Run Job<br/>registration-bullmq-monitor<br/>(asia-southeast1)"]
        Telegram["Telegram Supergroup: It tok<br/>Topic: Backend Core (ID: 6)<br/>Bot: @tokobuah_crawler_bot"]
        
        Scheduler --> RunJob
        RunJob --> RedisCore
        RunJob --> Telegram
    end

    NAT --> Ingress
    PlayerWeb --> Ingress
```

### Tabel Rincian Komponen & Kredensial Terkait:

| Komponen / Resource | Lingkungan / Target | Spesifikasi & Konfigurasi | Keterangan / Fungsi |
| :--- | :--- | :--- | :--- |
| **GCP Project Utama** | `tokobuah-production` | Region: `asia-southeast1` | Host seluruh cluster GKE production & Cloud SQL |
| **GCP Project Staging** | `tokobuah-staging-499001` | Region: `asia-southeast1` | Host monitoring SA & staging environment |
| **GKE Clusters** | `prod-client-cluster`, `prod-core-cluster`, `game-cluster` | Kubernetes v1.28+, VPC-native | Cluster penampung 11 tenant dan core backend |
| **11 Tenant Namespaces** | `client`, `cinabotak`, `cinasuper`, `hambabet`, `ikn788`, `omsipit`, `pengenwd`, `rumushoki`, `tapakhoki`, `terbangwd`, `terios88` | Namespace per white-label brand | Menjalankan deployment `backend-company` (~33 pods total) |
| **API Gateway Proxy** | `ESPv2` (Cloud Endpoints) | Container image: `gcr.io/endpoints-release/endpoints-runtime:2` | Sidecar container di setiap pod tenant; memvalidasi request & melaporkan ke Service Control |
| **Backend Service** | `new-backend` (Go) | Host: `transactional.tokobuahapi.store` | Core engine ledger transaksi double-entry |
| **Cloud NAT Outbound IP** | `34.1.138.144` | Static Cloud NAT IP | IP publik egress yang digunakan Cloud Run SSR Next.js saat memanggil backend |
| **Cloud Run Job** | `registration-bullmq-monitor` | Memory: 512MiB, CPU: 1 | Worker node pemantau antrean registrasi member |
| **Cloud Scheduler** | `trigger-registration-bullmq-monitor` | `*/5 * * * *` (Setiap 5 menit) | Trigger otomatis Cloud Run Job via OIDC |
| **Telegram Alert Target** | Supergroup **It tok** (`-1003992607433`) | Topic: **Backend Core** (`message_thread_id: 6`) | Bot pengirim: `@tokobuah_crawler_bot` (Token: `8502149317:********`) |
| **Service Account SRE** | `hermes-monitor-sa@tokobuah-staging-499001.iam.gserviceaccount.com` | Key: `/Users/avocado/tokobuah/hermes-deploy/crawler/gcp_key.json` | Memiliki role cross-project viewer & container reader |
| **BigQuery Dataset** | `tokobuah-production.game_reports` | Tabel: `public_players` | Sinkronisasi harian dari database OLTP untuk audit |

---

## 3. CATATAN PERUBAHAN & KRONOLOGI IMPLEMENTASI

Berikut adalah urutan kronologis investigasi, audit komit, diagnosis teknis, dan langkah perbaikan yang telah dieksekusi:

### 1. Forensik Lonjakan Tagihan GCP Apigee / Service Control
- **Deteksi Awal**: Menganalisis invoice Google Cloud Platform yang menunjukkan kenaikan tajam pada grup layanan "Apigee API Platform" hingga $289.11 per 20 Oktober 2026.
- **Isolasi SKU**: Melakukan breakdown SKU billing GCP dan mengonfirmasi bahwa biaya berasal dari SKU `F31D-9645-41B5` (`Google Service Control - Operations`), dengan volume pemanggilan menembus 75.839.035 kali.
- **Pemetaan Arsitektur Pod**: Menginspeksi GKE cluster menggunakan service account `hermes-monitor-sa`. Ditemukan bahwa 11 namespace tenant menjalankan pod dengan sidecar container `espv2` yang dikonfigurasi untuk melaporkan setiap transaksi ke API Google Service Control.
- **Analisis Distribusi User-Agent**: Mengekstrak log ingress dan pod ESPv2. Ditemukan anomali ekstrem di mana 84.4% request membawa header `User-Agent: node` dan bersumber dari Cloud NAT `34.1.138.144` (Cloud Run SSR Next.js admin panel). Traffic browser pemain asli hanya sebesar 1.5%.

### 2. Audit Git Commit History pada Repository `admin-panel`
Pemeriksaan log commit mengarahkan akar masalah ke rilis **`v0.0.67`** (10 Oktober 2026, PR #198) dan **`v0.0.69`** (12 Oktober 2026):
- **Commit `24f3e05` & `71d972d`**:
  - Di file `src/components/reports/member-game-daily.tsx`, developer memecah proses pengambilan data ekspor menjadi perulangan sequential per `limit=100`. Untuk laporan dengan 50.000 record, browser admin CS secara berurutan menembakkan 500 HTTP request independen.
  - Di file `src/lib/run-with-concurrency.ts`, konkurensi request dinaikkan tanpa pembatasan *rate limiting*.
  - Di file `src/components/common/export-button.tsx`, pengaman `maxPages = 100` dihapus.
- **N+1 Query Loop di API Routes**:
  - Di file `src/app/api/admin/players/route.ts`, fungsi `fetchAllPlayerPages` mengeksekusi request induk untuk mengambil list player, lalu secara otomatis mengeksekusi request anak `GET /admin/players/{id}/bank-accounts` untuk setiap player satu per satu (mencakup hingga puluhan ribu player).
- **Unbounded Polling**:
  - Di file `src/providers/notifications-provider.tsx`, polling notifikasi transaksi dijalankan menggunakan `setTimeout(poll, 5000)` terhadap 3 endpoint berat (`/transactions?limit=200`, `/manual-transactions?limit=200`, `/kyc/documents`) tanpa validasi `document.hidden`.

### 3. Implementasi Monitoring Serverless BullMQ
- Menyelidiki kegagalan registrasi pemain untuk username `ayunieka20` di mana job registrasi menumpuk di queue BullMQ tanpa terproses segera oleh worker.
- Merancang dan memvalidasi script monitoring antrean BullMQ berbasis Node.js yang membaca panjang antrean (`waiting`, `active`, `failed`, `delayed`).
- Mem-build container image dan men-deploy **Cloud Run Job** `registration-bullmq-monitor` di region `asia-southeast1`.
- Membuat jadwal berkala via **Cloud Scheduler** `trigger-registration-bullmq-monitor` dengan frekuensi 5 menit.
- Mengonfigurasi broadcast alert Telegram via `@tokobuah_crawler_bot` ke grup supergroup **"It tok"** (Thread: **Backend Core**, ID: `6`). Telah dilakukan uji coba broadcast dan status berhasil terkonfirmasi aktif.

### 4. Perancangan Blueprint Asynchronous Server-Side Export
- Menyusun arsitektur transisi dari client-side chunking ke server-side streaming export untuk backend transactional Go:
  - Client hanya mengirimkan satu command: `POST /api/admin/reports/export`.
  - Backend Go menjalankan goroutine mandiri yang men-query database PostgreSQL secara cursor streaming (`rows.Next()`).
  - Stream data dikonversi ke CSV dan dipompa langsung ke Google Cloud Storage melalui `io.Pipe()`, tanpa membebani memory (RAM) pod backend.
  - Progress job disimpan di Redis (`export:job:{job_id}`). Setelah selesai, backend meng-generate GCS Signed URL yang langsung diunduh oleh browser admin panel.

### 5. Audit Data Referral di BigQuery
- Memeriksa schema dan isi dataset `tokobuah-production.game_reports.public_players` yang disinkronisasikan oleh job ETL `sync-db-to-bigquery`.
- Memastikan bahwa struktur data referral (`referral_code`, `referred_by`, `company_code`, `username`, `id`, `created_at`) tersimpan lengkap di BigQuery dengan puluhan ribu record historis.
- Mengidentifikasi keterbatasan bahwa tabel ledger komisi pencairan bonus (`referral_payouts`) belum masuk ke dalam pipeline BigQuery dan masih berada secara eksklusif di database relasional PostgreSQL OLTP.

---

## 4. CAVEATS, GOTCHAS, & ROOT CAUSE ANALYSIS (RCA)

Bagian ini mendokumentasikan jebakan teknis, anomali diagnostik, serta bug kritis yang ditemukan selama investigasi.

```mermaid
flowchart LR
    A["Next.js SSR API Routes<br/>(v0.0.67 PR #198)"] -->|1. Micro-Chunking limit=100| B["Cloud NAT<br/>34.1.138.144"]
    A -->|2. Polling 5s Unthrottled| B
    A -->|3. N+1 Bank Accounts Loop| B
    B -->|Massive HTTP Ingress| C["ESPv2 Sidecar Proxy<br/>(33 Pods in 11 Tenants)"]
    C -->|1 Request = 1 Telemetry Check| D["Google Service Control<br/>servicecontrol.googleapis.com"]
    D -->|Over Free Tier 2M| E["Billing Spike: $289.11<br/>75,839,035 Ops ($3/1M)"]
```

### 1. Jebakan Kategori Billing: "Apigee API Platform" vs Service Control
- **Gotcha**: Di halaman Google Cloud Billing Overview, kategori tagihan tertulis secara umum sebagai **"Apigee API Platform"**. Hal ini sering memicu salah sangka bahwa tim DevOps secara keliru mengaktifkan langganan berbayar enterprise Apigee X/Hybrid ($1.000+/bulan).
- **Fakta Teknis**: Google Cloud mengelompokkan produk Cloud Endpoints dan ESPv2 di bawah payung bisnis Apigee. Biaya riil bukan berasal dari instance Apigee, melainkan SKU mikro **`Google Service Control - Operations` (SKU ID: `F31D-9645-41B5`)**. Tarifnya adalah **$3.00 per 1.000.000 pemanggilan** setelah melewati jatah gratis 2.000.000 pemanggilan per bulan per akun penagihan.

### 2. Autentikasi CLI Headless & Service Account Bypass
- **Gotcha**: Saat menjalankan perintah `gcloud` atau `bq` dari CLI lokal/container, perintah sering kali hang atau gagal dengan pesan kesalahan:
  `ERROR: (gcloud.auth.print-access-token) There was a problem refreshing your credentials... Reauthentication required`.
- **Penyebab**: Akun user Google Workspace (`admin@tokobuah.xyz`) memiliki masa berlaku sesi terbatas dan mewajibkan Web Browser SSO login interaktif.
- **Resolusi**: Jangan bergantung pada sesi user interaktif. Gunakan service account key file yang tersedia di server (`hermes-monitor-sa@tokobuah-staging-499001.iam.gserviceaccount.com` pada `/Users/avocado/tokobuah/hermes-deploy/crawler/gcp_key.json`). Generate token akses secara programmatic via gcloud auth activate atau JWT grant, lalu injeksikan langsung ke `kubectl --token=<TOKEN>` atau header REST API.

### 3. Container ESPv2 Bersifat Distroless (No Shell / No Curl)
- **Gotcha**: Mencoba masuk ke dalam container ESPv2 menggunakan `kubectl exec -it <pod> -c espv2 -- sh` atau `curl` akan langsung menghasilkan error:
  `OCI runtime exec failed: exec: "curl": not found: unknown` atau `exec: "sh": executable file not found in $PATH`.
- **Penyebab**: Container image `gcr.io/endpoints-release/endpoints-runtime:2` dibangun menggunakan base distroless/scratch untuk keamanan dan minimalisir footprint. Tidak ada shell, coreutils, maupun curl di dalamnya.
- **Resolusi**: Audit status ESPv2 wajib dilakukan melalui ekstraksi log container (`kubectl logs <pod> -c espv2`) atau menempelkan ephemeral debug container (`kubectl debug`), atau menganalisis stream JSON access log secara eksternal.

### 4. Masking IP Akibat Cloud NAT Egress
- **Gotcha**: Tim keamanan jaringan melihat lonjakan jutaan request harian yang berasal dari satu alamat IP eksternal `34.1.138.144` dan mencurigainya sebagai serangan Brute Force atau DDoS crawler pihak ketiga.
- **Fakta Teknis**: Alamat IP `34.1.138.144` adalah Gateway Cloud NAT resmi milik VPC production Tokobuah. Serverless compute (Cloud Run Next.js SSR) keluar menuju internet publik melalui Cloud NAT tersebut sebelum kembali masuk ke GKE Load Balancer. Request tersebut sepenuhnya adalah *self-inflicted traffic* dari internal Next.js server-side code.

### 5. Client-Side Chunking Menyebabkan Browser OOM Crash
- **Gotcha**: Pendekatan export yang memecah 50.000 baris menjadi looping `limit=100` di browser CS tidak hanya melipatgandakan request HTTP ke backend, tetapi juga memaksa browser menampung 500 payload JSON mentah ke dalam memori tab JavaScript sebelum dikonversi ke Excel/CSV.
- **Dampak**: Tab browser CS pada mesin dengan spesifikasi standar (RAM 8GB) kerap mengalami freeze atau crash (OOM / *Aw, Snap!*) saat melakukan filter laporan rentang bulanan.

---

## 5. STANDARD OPERATING PROCEDURE (SOP) & RUNBOOK OPERASIONAL

---

### 5.1 DIAGNOSTIK & MONITORING BILLING GCP SERVICE CONTROL

Jika terjadi indikasi kenaikan biaya pada kategori "Apigee API Platform", jalankan protokol verifikasi berikut:

#### Langkah 1: Autentikasi Headless Menggunakan Service Account
```bash
# Set path service account key yang valid
export GOOGLE_APPLICATION_CREDENTIALS="/Users/avocado/tokobuah/hermes-deploy/crawler/gcp_key.json"

# Aktivasi service account di gcloud
gcloud auth activate-service-account \
  --key-file="/Users/avocado/tokobuah/hermes-deploy/crawler/gcp_key.json"

# Dapatkan bearer token untuk pemanggilan API langsung
export GCP_ACCESS_TOKEN=$(gcloud auth print-access-token)
```

#### Langkah 2: Audit Volume Panggilan Service Control via Cloud Monitoring Metrics
Gunakan Google Cloud Monitoring MQL (Monitoring Query Language) untuk melihat rate pemanggilan Service Control:
```bash
# Periksa rate request service control per service
gcloud monitoring timeseries list \
  --project="tokobuah-production" \
  --filter='metric.type="serviceruntime.googleapis.com/api/request_count" AND resource.type="consumed_api"' \
  --interval-start="$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)" \
  --interval-end="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --aggregation-alignment-period="3600s" \
  --aggregation-per-series-aligner="ALIGN_RATE"
```

#### Langkah 3: Ekstraksi Sample Access Log dari Pod ESPv2 di GKE
Untuk melihat pola pemanggil dan User-Agent dominan di salah satu tenant:
```bash
# Dapatkan konteks cluster produksi
kubectl get pods -n hambabet -l app=backend-company \
  --token="$GCP_ACCESS_TOKEN" \
  -o jsonpath='{.items[0].metadata.name}' > /tmp/sample_pod.txt

SAMPLE_POD=$(cat /tmp/sample_pod.txt)

# Stream 500 baris access log terakhir dari container espv2
kubectl logs "$SAMPLE_POD" -n hambabet -c espv2 --tail=500 \
  --token="$GCP_ACCESS_TOKEN" > /tmp/espv2_access.log

# Hitung distribusi User-Agent
awk -F'"' '{print $6}' /tmp/espv2_access.log | sort | uniq -c | sort -nr
```
> **Kriteria Normal**: User-Agent `node` tidak boleh melebihi 20% dari total traffic API gateway. Jika `node` mendominasi di atas 70%, segera periksa job batch atau infinite loop di Next.js SSR admin panel.

---

### 5.2 MITIGASI & OPTIMASI FRONTEND ADMIN PANEL

Perbaikan mendesak pada repository `/Users/avocado/tokobuah/admin-panel` harus memenuhi 3 klausul perubahan berikut:

#### 1. Perbesar Chunk Size Pagination & Pasang Hard Safety Cap
Edit file pelaporan (misal: `src/components/reports/member-game-daily.tsx` dan `src/lib/run-with-concurrency.ts`):
- **Wajib menaikkan chunk size**: Ubah dari `limit=100` menjadi `limit=1000` atau `limit=2000`. Hal ini langsung memangkas 90%–95% volume HTTP request ke backend.
- **Pasang Safety Guard Max Pages**: Jangan biarkan loop berjalan tanpa batas (`while (true)` atau `for (page=0;;)`). Pasang batas maksimal:
```typescript
const MAX_EXPORT_PAGES = 50; // Maksimal 50.000 baris per ekspor langsung
let currentPage = 1;
const CHUNK_LIMIT = 1000;

while (currentPage <= MAX_EXPORT_PAGES) {
  const res = await fetchReportChunk(currentPage, CHUNK_LIMIT);
  if (!res.data || res.data.length === 0) break;
  accumulateData(res.data);
  if (res.data.length < CHUNK_LIMIT) break;
  currentPage++;
}
```

#### 2. Optimasi Polling Notifikasi dengan Page Visibility API
Edit `src/providers/notifications-provider.tsx`. Polling dilarang keras menembak backend saat tab browser berada di latar belakang atau terminimalkan:
```typescript
useEffect(() => {
  let timerId: NodeJS.Timeout;

  const executePoll = async () => {
    // Abaikan jika user sedang tidak membuka tab (tab inactive / minimized)
    if (document.hidden) {
      timerId = setTimeout(executePoll, 15000); // Backoff lambat saat hidden
      return;
    }

    try {
      await fetchPendingNotifications();
    } catch (err) {
      console.error("Polling notification error:", err);
    } finally {
      timerId = setTimeout(executePoll, 10000); // Polling normal setiap 10 detik
    }
  };

  timerId = setTimeout(executePoll, 10000);

  // Pasang listener saat tab kembali aktif (focus)
  const handleVisibilityChange = () => {
    if (!document.hidden) {
      executePoll();
    }
  };

  document.addEventListener("visibilitychange", handleVisibilityChange);
  return () => {
    clearTimeout(timerId);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  };
}, []);
```

#### 3. Eliminasi Pola N+1 Query pada Player Route
Di `src/app/api/admin/players/route.ts`:
- **DILARANG**: Menjalankan perulangan `for (const player of players) { await fetchBankAccount(player.id); }`.
- **WAJIB**: Meminta tim backend menyediakan endpoint batch (misalnya: `POST /admin/players/bank-accounts/batch` dengan payload `player_ids: [...]`), atau menyertakan relasi bank account langsung di payload induk (`JOIN` pada query SQL backend).

---

### 5.3 ARSITEKTUR ASYNCHRONOUS SERVER-SIDE EXPORT (BACKEND GO + GCS + REDIS)

Untuk file laporan berukuran besar (>10.000 baris), pemrosesan **tidak boleh** ditangani oleh browser. Gunakan pipeline asinkron berikut:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin / CS Panel
    participant BE as Transactional Backend (Go)
    participant Redis as Redis Memorystore
    participant DB as PostgreSQL OLTP
    participant GCS as Google Cloud Storage

    Admin->>BE: POST /api/admin/reports/export (filters, format)
    BE->>Redis: SET export:job:{job_id} (Status: PENDING)
    BE-->>Admin: 202 Accepted (job_id, status: PENDING)
    
    critical Asynchronous Goroutine Worker
        BE->>DB: Query DB Cursor (rows.Next())
        BE->>Redis: SET export:job:{job_id} (Status: PROCESSING, progress: 25%)
        BE->>GCS: Stream CSV via io.Pipe() (cloud.google.com/go/storage)
        GCS-->>BE: Upload Finished
        BE->>GCS: Generate Signed URL (TTL 24h)
        BE->>Redis: SET export:job:{job_id} (Status: COMPLETED, download_url)
    end

    loop Poll Status (Interval 2-3s)
        Admin->>BE: GET /api/admin/reports/export/{job_id}
        BE->>Redis: GET export:job:{job_id}
        BE-->>Admin: {status: PROCESSING, progress: 65%}
    end

    Admin->>BE: GET /api/admin/reports/export/{job_id}
    BE->>Redis: GET export:job:{job_id}
    BE-->>Admin: {status: COMPLETED, download_url: "https://storage.googleapis.com/..."}
    Admin->>GCS: Direct Browser Download (Signed URL)
```

#### 1. Format Skema Redis Job
Kunci Redis: `export:job:{job_id}`, tipe data: `STRING` (JSON Serialized), TTL: `86400` (24 jam).
```json
{
  "job_id": "exp_7f9a2b1c-8e4d-4a11-b0e2-9d3c8a11b0e2",
  "company_code": "hambabet",
  "report_type": "member_game_daily",
  "status": "COMPLETED",
  "progress_percentage": 100,
  "total_rows": 48250,
  "file_name": "member_game_daily_20261018.csv",
  "download_url": "https://storage.googleapis.com/tokobuah-production-reports/exports/exp_7f9a2b1c.csv?Expires=...",
  "error_message": null,
  "created_at": "2026-10-18T10:15:30Z",
  "updated_at": "2026-10-18T10:16:02Z"
}
```

#### 2. Implementasi Pola Streaming Go ke GCS via `io.Pipe()`
Pola ini menjamin pod Go tidak mengalami memory leak / OOM saat memproses 500.000 baris data:
```go
package exportservice

import (
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"time"

	"cloud.google.com/go/storage"
	"github.com/google/uuid"
)

func StreamExportToGCS(ctx context.Context, gcsClient *storage.Client, bucketName string, jobID string) (string, error) {
	objectName := fmt.Sprintf("exports/%s.csv", jobID)
	bucket := gcsClient.Bucket(bucketName)
	obj := bucket.Object(objectName)

	pr, pw := io.Pipe()

	// Goroutine 1: Tulis data CSV ke PipeWriter dari database cursor
	go func() {
		defer pw.Close()
		csvWriter := csv.NewWriter(pw)
		defer csvWriter.Flush()

		// Tulis Header
		_ = csvWriter.Write([]string{"TransactionID", "Username", "Amount", "Status", "CreatedAt"})

		// Contoh simulasi iterasi cursor database (rows.Next())
		for i := 0; i < 50000; i++ {
			record := []string{
				fmt.Sprintf("TX-%d", i),
				fmt.Sprintf("player_%d", i),
				"150000.00",
				"SUCCESS",
				time.Now().UTC().Format(time.RFC3339),
			}
			if err := csvWriter.Write(record); err != nil {
				_ = pw.CloseWithError(err)
				return
			}
		}
	}()

	// Eksekusi upload stream langsung ke GCS Storage Writer
	gcsWriter := obj.NewWriter(ctx)
	if _, err := io.Copy(gcsWriter, pr); err != nil {
		_ = gcsWriter.Close()
		return "", fmt.Errorf("failed to pipe data to GCS: %w", err)
	}
	if err := gcsWriter.Close(); err != nil {
		return "", fmt.Errorf("failed to finalize GCS writer: %w", err)
	}

	// Buat V4 Signed URL untuk diunduh langsung oleh client
	opts := &storage.SignedURLOptions{
		Scheme:  storage.SigningSchemeV4,
		Method:  "GET",
		Expires: time.Now().Add(24 * time.Hour),
	}
	signedURL, err := bucket.SignedURL(objectName, opts)
	if err != nil {
		return "", fmt.Errorf("failed to generate signed URL: %w", err)
	}

	return signedURL, nil
}
```

---

### 5.4 STANDARISASI IN-HOUSE WEBSOCKET GAME ENGINE & DEVOPS READINESS

Jika Tokobuah mengimplementasikan game in-house real-time berbasis WebSocket, infrastruktur wajib memenuhi standar konfigurasi berikut:

#### 1. GKE Ingress & BackendConfig Timeout
Load Balancer GCP secara default memutus koneksi idle setelah **30 detik**. Untuk WebSocket persisten:
Buat manifest `BackendConfig` khusus di namespace game engine:
```yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: websocket-backend-config
  namespace: game-engine
spec:
  timeoutSec: 86400 # 24 Jam (mencegah TCP disconnect sepihak)
  connectionDraining:
    drainingTimeoutSec: 60
  healthCheck:
    type: HTTP
    requestPath: /healthz
    port: 8080
```
Tautkan `BackendConfig` ke Service Kubernetes via annotation:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: game-websocket-service
  namespace: game-engine
  annotations:
    cloud.google.com/backend-config: '{"default": "websocket-backend-config"}'
spec:
  type: NodePort
  selector:
    app: game-websocket-engine
  ports:
    - port: 8080
      targetPort: 8080
      name: ws
```

#### 2. Wajib Mem-Bypass ESPv2 Proxy untuk WebSocket Traffic
> [!CAUTION]
> **DILARANG** merutekan traffic WebSocket melalui sidecar ESPv2 (Google Cloud Endpoints).  
> Service Control tidak didesain untuk transaksi persisten duplex, akan memutus stream, dan akan mengenakan billing astronomis jika frame dihitung sebagai discrete operations. Traffic WebSocket harus langsung menuju Ingress/NodePort game pod.

#### 3. Linux Kernel & Socket Tuning pada Node Pool
Setiap instance GKE Node Pool yang menangani WebSocket wajib di-tune melalui DaemonSet atau `nodeConfig.kubeletConfig`:
```bash
# Tingkatkan limit open file descriptors
sysctl -w fs.file-max=2097152

# Perbesar backlog buffer koneksi TCP
sysctl -w net.core.somaxconn=65535
sysctl -w net.ipv4.tcp_max_syn_backlog=65535

# Perlebar alokasi ephemeral local port range
sysctl -w net.ipv4.ip_local_port_range="1024 65535"

# Optimasi TCP keepalive untuk deteksi dead connection lebih cepat
sysctl -w net.ipv4.tcp_keepalive_time=300
sysctl -w net.ipv4.tcp_keepalive_intvl=15
sysctl -w net.ipv4.tcp_keepalive_probes=5
```
Di level Pod Container spec, set ulimit:
```yaml
securityContext:
  sysctls:
    - name: net.core.somaxconn
      value: "65535"
```

#### 4. Autoscaling Pod (HPA) Berbasis Active Connection Metric
WebSocket adalah aplikasi stateful/koneksi persisten. Autoscaling berbasis CPU/RAM tidak akurat karena 100.000 koneksi idle memakan CPU rendah namun menghabiskan socket memory.  
Gunakan **Prometheus Adapter** untuk HPA berbasis metric `websocket_active_connections`:
- Target HPA: Maksimal **5.000–10.000 koneksi aktif per pod**.
- Gunakan **Redis Pub/Sub** atau **Redis Cluster** sebagai event backplane untuk broadcast event antar pod.

#### 5. Graceful Connection Draining & Zero Downtime Deployment
Saat pod di-restart (rolling update):
```yaml
spec:
  terminationGracePeriodSeconds: 120 # Beri waktu 2 menit bagi koneksi untuk berpindah
  containers:
    - name: game-ws
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 10"]
```
Aplikasi wajib mendengarkan sinyal `SIGTERM`, mengirimkan frame penutup WebSocket (`CloseFrame` Code `1001 Going Away`), dan meminta client me-reconnect secara smooth dengan jitter acak.

---

### 5.5 AUDIT & HEALTH-CHECK BULLMQ REGISTRATION QUEUE

Untuk memastikan antrean pendaftaran player berjalan normal dan memverifikasi alerting Telegram:

#### 1. Eksekusi Manual Cloud Run Job
```bash
# Trigger eksekusi job secara manual untuk pengujian
gcloud run jobs execute registration-bullmq-monitor \
  --project="tokobuah-production" \
  --region="asia-southeast1" \
  --wait
```

#### 2. Periksa Log Eksekusi Terakhir
```bash
# Baca output log eksekusi job
gcloud beta run jobs executions logs read \
  --project="tokobuah-production" \
  --region="asia-southeast1" \
  --limit=50
```

#### 3. Format Payload Alert Telegram (Group: It tok / Topic: Backend Core)
Notifikasi dikirimkan dalam format Markdown berikut:
```text
⚠️ [ALERT] BullMQ Player Registration Backlog Detected!
Tenant: ALL / Multi-Tenant
Queue: player-registration
Waiting Jobs: 48
Active Jobs: 12
Failed Jobs: 3 (Last error: DB Connection Timeout)
Delayed Jobs: 0
Timestamp: 2026-10-20 14:05:00 UTC
Action Required: Segera periksa worker consumer auth-engine & koneksi PostgreSQL.
```

---

### 5.6 PROSEDUR VERIFIKASI DATA REFERRAL BIGQUERY

Untuk memverifikasi integritas sinkronisasi data referral di Google BigQuery:

#### 1. Jalankan Query Verifikasi Schema & Sample Record
```sql
SELECT 
    id,
    company_code,
    username,
    referral_code,
    referred_by,
    created_at
FROM 
    `tokobuah-production.game_reports.public_players`
WHERE 
    referred_by IS NOT NULL 
    AND referred_by != ''
ORDER BY 
    created_at DESC
LIMIT 10;
```

#### 2. Keterbatasan & Batasan Sinkronisasi (Audit Note):
- **Tersedia di BigQuery**: Pohon relasi jaringan referral (siapa mereferensikan siapa) tersinkronisasi secara harian dari tabel `players` / `public_players`.
- **Hanya di PostgreSQL OLTP**: Tabel transaksi finansial pembayaran komisi (`referral_payouts`, `referral_commission_ledger`) belum diekspor ke BigQuery. Jika tim finance membutuhkan rekonsiliasi nilai rupiah/komisi yang telah dibayarkan, query wajib diarahkan ke database relasional PostgreSQL (Cloud SQL) melalui read-replica.

---

## 6. GUARDRAILS & BATASAN KEAMANAN KHUSUS

Seluruh engineer, operator SRE, dan Autonomous AI Agent yang beroperasi di workspace ini wajib mematuhi batasan mutlak berikut:

> [!IMPORTANT]
> **1. Production Freeze Protocol (§1)**:  
> Dilarang keras melakukan rollout, restart massal, perubahan konfigurasi Ingress, atau modifikasi deployment Kubernetes di namespace produksi tanpa rencana tertulis, kalkulasi blast radius, dan izin eksplisit (*"gas"*, *"proceed"*, *"lanjutkan"*) dari user.

> [!CAUTION]
> **2. Zero Deletion Without Permission (§2)**:  
> - DILARANG menghapus Pod, Service, Ingress, ConfigMap, atau Namespace di GKE.
> - DILARANG menjalankan `gcloud endpoints services delete` atau mematikan API Google Service Control secara sepihak karena akan langsung memutus seluruh akses API gateway 11 tenant.
> - DILARANG menghapus index atau queue di Redis Memorystore.

> [!WARNING]
> **3. Strict Secret Masking (§5)**:  
> Dilarang menampilkan atau menuliskan kredensial dalam bentuk plaintext pada percakapan, file runbook, commit git, maupun log:
> - Telegram Bot Token: `8502149317:AAFB6ue5...` -> Masked: `8502149317:********`
> - Database Connection: `postgresql://user:password@host...` -> Masked: `postgresql://user:********@host...`
> - Private Key GCP Service Account: Wajib menggunakan environment variable atau file path terproteksi.

> [!NOTE]
> **4. Isolasi Cloud NAT & Egress (§7)**:  
> IP `34.1.138.144` adalah lifeline komunikasi Cloud Run menuju cluster internal. Dilarang mengubah alokasi subnet, routing table, atau firewall rules Cloud NAT tanpa koordinasi menyeluruh dengan tim infrastruktur jaringan.

---

*Dokumen ini disusun dan distandarisasi untuk menjamin stabilitas arsitektur API, efisiensi biaya infrastruktur cloud, dan kesinambungan operasional platform Tokobuah.*
