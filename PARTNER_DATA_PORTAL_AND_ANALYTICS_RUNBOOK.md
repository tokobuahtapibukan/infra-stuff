# 🛡️ TOKOBUAH PARTNER DATA PORTAL & BIG DATA ANALYTICS RUNBOOK
> **Path**: `/Users/avocado/tokobuah/infra-stuff/PARTNER_DATA_PORTAL_AND_ANALYTICS_RUNBOOK.md`  
> **Classification**: Internal Engineering Knowledge Base & Production Runbook  
> **Target Audience**: Cloud Engineers, Data Engineers, DevSecOps, & Incoming Autonomous AI Agents  
> **Status**: Production Living Document (Fully Verified & Operational)  
> **Governing Security Rules**: Strict read-only audit protocol, Zero deletion without approval, Strict secret masking, Workspace OAuth lock.

---

## 📑 DAFTAR ISI
1. [Ringkasan Eksekutif & Tujuan Sesi](#1-ringkasan-eksekutif--tujuan-sesi)
2. [Topologi & Komponen Terkait](#2-topologi--komponen-terkait)
3. [Catatan Perubahan & Perintah yang Telah Dijalankan](#3-catatan-perubahan--perintah-yang-telah-dijalankan)
4. [Caveats, Gotchas, & Error yang Sempat Terjadi](#4-caveats-gotchas--error-yang-sempat-terjadi)
5. [Standard Operating Procedure (SOP) & Runbook](#5-standard-operating-procedure-sop--runbook)
6. [Guardrails & Batasan Keamanan Khusus](#6-guardrails--batasan-keamanan-khusus)

---

## 1. RINGKASAN EKSEKUTIF & TUJUAN SESI

### 1.1 Konteks Proyek & Latar Belakang
TokoBuah menjalin kemitraan strategis penyediaan data transaksi seluler skala besar (*big data traffic analytics*) dengan operator telekomunikasi terbesar (Telkomsel). Partner mentransfer dump rekaman MSISDN dan aktivitas pengguna harian dalam volume masif (mencapai **646+ Juta data poin** transaksi mentah dengan jangkauan lebih dari **31,26 Juta nomor unik** per siklus audit).

Tujuan utama sesi rekayasa infrastruktur ini adalah membangun, mengamankan, mengoptimasi, dan mengotomasi seluruh pipeline *end-to-end*:
1. **Ingestion & Processing Pipeline**: Menyiapkan gerbang penerima transfer data partner yang aman (SFTP/SCP), deduplikasi instan nomor unik, konversi otomatis ke multi-sheet Excel (.xlsx), dan sinkronisasi ke penyimpanan awan *private*.
2. **Serverless Data Portal**: Mengembangkan portal data berbasis FastAPI di atas Google Cloud Run (`partner-data-portal`), terkunci secara eksklusif ke akun Google Workspace `@tokobuah.xyz` di balik domain resmi bertopeng (*domain masking*) `https://buahdatasemuammanis.net` via Cloudflare Proxy.
3. **Penyimpanan Private & Audit Trail Persisten**: Menyimpan seluruh arsip *raw* dan *sanitized* ke dalam bucket Google Cloud Storage private (`tokobuah-staging-partner-analytics`), dilengkapi pencatatan riwayat unduh (*append-only audit log*) tanpa perlu bergantung pada GCP Cloud Logging Console.
4. **Marketing Intelligence Engine (`/analytics`)**: Membangun modul intelijen pemasaran interaktif yang menyajikan wawasan daya beli prefix Telkomsel (SES A+ Halo vs Kartu As), grafik intensitas 24 jam interaktif, radar *poaching* kompetitor (316–418 brand kompetitor), serta *multi-period reactive snapshots* (Overall Master 31.3M, 7-Day Rolling Cycle 5.8M, dan harian).
5. **Hardening Keamanan & Redesign 2FA Share Link**: Mengeliminasi celah token stateless HMAC yang tidak dapat dicabut (*unrevocable*) dengan mengimplementasikan sistem *share grants* persisten di GCS, verifikasi PIN akses 6-digit (*two-factor access code*), kuota unduh terbatas (1x–5x), *rate-limiting* anti-brute force, dan pembersihan bypass dev-login di environment produksi.
6. **Redesign UX Dashboard Bank Berkas**: Mengatasi masalah *infinite vertical scroll* pada daftar arsip harian yang membengkak seiring berjalannya waktu, bertransisi dari tampilan accordion vertikal menjadi **Two-Panel Master-Detail Layout** (gaya Apple Mail / Linear / Notion) dengan *default view* yang terkunci rapi pada Panel Ganda.

---

## 2. TOPOLOGI & KOMPONEN TERKAIT

### 2.1 Arsitektur Jaringan & Serverless Portal
```
+----------------------------------------------------------------------------------------------------+
|                                      PUBLIK & JARINGAN LUAR                                        |
+----------------------------------------------------------------------------------------------------+
       |                                                                            |
       | Partner Upload (SCP/SFTP via SSH Key)                                      | HTTPS Traffic (Browser)
       v                                                                            v
+-------------------------------+                                      +-----------------------------+
| GCP Compute Engine VM         |                                      | Cloudflare Proxy (WAF/SSL)  |
| "partner-analytics-vm"        |                                      | buahdatasemuammanis.net     |
| IP: 136.110.10.234 (Static)   |                                      | SSL: Full (Strict)          |
| Zone: asia-southeast1-b (SG)  |                                      +-----------------------------+
| Specs: 8 vCPU / 16 GB RAM     |                                                     |
+-------------------------------+                                                     v
       |                                                               +-----------------------------+
       | Pipeline Ingest & Deduplikasi                                 | Google Frontend (GFE)       |
       | (mawk, python, systemd daemon)                                | Google Cloud Run            |
       v                                                               | "partner-data-portal"       |
+-------------------------------------------------------------+        | Region: asia-east1 (Taiwan) |
| Google Cloud Storage Bucket                                 |        | Rev: partner-data-portal-*  |
| "tokobuah-staging-partner-analytics" (Private)              |<------>+-----------------------------+
| - raw/ (CSV asli & .csv.gz)                                 |                       |
| - sanitized/ (CSV unik, .gz, multi-sheet .xlsx, master CSV) |                       v
| - analytics_snapshots/ (JSON snapshot metrics)              |        +-----------------------------+
| - share_grants/ (2FA PIN access grants JSON)                |        | Google OAuth 2.0 Identity   |
| - audit_logs/events/ (Persistent download audit trail)      |        | Locked to: @tokobuah.xyz    |
+-------------------------------------------------------------+        +-----------------------------+
```

### 2.2 Tabel Komponen Infrastruktur
| Komponen | Identitas / Parameter | Spesifikasi Teknis / Keterangan |
| :--- | :--- | :--- |
| **GCP Project** | `tokobuah-staging-499001` | Project utama staging & partner engineering. |
| **Cloud Run Service** | `partner-data-portal` | FastAPI Python 3.9+, Cloud Run managed serverless. |
| **Cloud Run Region** | `asia-east1` (Taiwan) | Dipilih untuk latensi streaming optimal dan resource availability. |
| **Revisi Aktif Terkini**| `partner-data-portal-00038-pwr` | 100% traffic terlayani di revision ini (Live BBIX Dedup Progress Banner & Auto-Polling). |
| **Alokasi Resource** | 1 vCPU (1000m) / 512 MiB RAM | Concurrency: 80 requests/instance; Auto-scaling: 0–100. |
| **Domain Publik Resmi** | `https://buahdatasemuammanis.net` | Domain bertopeng untuk menyamarkan infrastruktur internal. |
| **Cloud Run Direct URL**| `https://partner-data-portal-lpnylkliqq-de.a.run.app` | Endpoint internal fallback GFE. |
| **Ingestion Host VM** | `partner-analytics-vm` | GCE Instance: `custom-8-16384` (8 vCPU, 16 GB RAM), Debian Linux. |
| **VM Zone & IP** | `asia-southeast1-b` (Singapore) | Eksternal: `136.110.10.234` (`partner-analytics-ip`); Internal: `10.148.0.6`. |
| **BBIX Worker Script**| `/usr/local/bin/bbix-ingest-worker.py` | Python 3 worker untuk Dropbox sync, queue polling, mawk dedup, Excel 2-sheet, & Telegram alert. |
| **BBIX Cron Daemon**  | `/etc/cron.d/bbix-ingest` | Cron job di VM: sync Dropbox tiap 30m, process queue unlock tiap 1m. |
| **Dropbox Ingest Conf**| `/etc/partner-analytics/dropbox.conf` | Kredensial App Key, Secret, & Refresh Token permanen (chmod 600). |
| **Telegram Bot Alert**| `tokobuah_bot` (Chat ID: `-1002364650579`) | Notifikasi instan Dropbox sync baru & selesai proses unlock/blend. |
| **Storage Private** | `tokobuah-staging-partner-analytics` | GCS Standard bucket private, default encryption, access via SA. |
| **Service Account** | `sa-partner-analytics@tokobuah-staging-499001.iam.gserviceaccount.com` | Role: `roles/storage.objectAdmin` (Read, Write, Overwrite GCS). |
| **OAuth Client ID** | `780207934006-j0sdm64lm5rlmtppohpc5fpkmppv4lmt.apps.googleusercontent.com` | Google Cloud Console OAuth 2.0 Client Credential. |
| **OAuth Secret** | `GOCSPX-********` *(Masked)* | Kredensial client secret OAuth Workspace. |
| **App Session Secret** | `********` *(Masked 64-char Secret)* | Kunci penandatangan session cookie & proteksi CSRF state. |

---

## 3. CATATAN PERUBAHAN & PERINTAH YANG TELAH DIJALANKAN

### 3.1 Fase 1: Penyediaan Host Ingestion VM & Setup Pipeline
1. **Reservasi Alamat IP Statis**:
   ```bash
   gcloud compute addresses create partner-analytics-ip \
       --region asia-southeast1 \
       --project tokobuah-staging-499001
   # Ditetapkan ke IP Publik: 136.110.10.234
   ```
2. **Penyediaan Compute Engine Ingestion Host**:
   Dibuat instance `partner-analytics-vm` dengan SSD persistent disk `/mnt/data` untuk menampung staging file harian hingga 50 GB.
3. **Otomasi Daemon Ingestion (`partner-ingest.service`)**:
   Dikonfigurasikan Systemd service di `/etc/systemd/system/partner-ingest.service` yang memanggil `/usr/local/bin/partner-ingest-worker.sh`:
   * **Step 1**: Validasi file kedatangan di `/mnt/data/incoming/upload/` dan pemindahan ke `/mnt/data/tmp_processing/`.
   * **Step 2**: Kompresi gzip dan pengunggahan *raw* ke `gs://tokobuah-staging-partner-analytics/raw/`.
   * **Step 3**: Deduplikasi nomor unik pada kolom kedua via Mawk:
     ```bash
     mawk -F"," '!seen[$2]++' input.csv > unique_phones.csv
     ```
   * **Step 4**: Konversi ke file Excel 4-sheet (`.xlsx`) berkapasitas 1.000.000 baris per lembar kerja melalui script Python `generate_multi_sheet_excel.py`.
   * **Step 5a**: Upload file bersih ke `gs://tokobuah-staging-partner-analytics/sanitized/`.
   * **Step 5b (Otomasi Sinkronisasi Master Snapshot)**: Integrasi hook `/usr/local/bin/update_overall_master_snapshot.py` yang membaca seluruh arsip harian `/mnt/data/archive/willliams-tsel-*.csv.gz`, menghitung deduplikasi lintas hari, dan memperbarui `overall.json` serta master CSV kompresi (`181 MB`).
   * **Step 6**: Housekeeping lokal (menghapus arsip >7 hari jika disk usage `/mnt/data` melebihi 70%).

---

### 3.2 Fase 2: Pembangunan Portal Data Serverless & Integrasi OAuth
1. **Inisialisasi Proyek FastAPI**:
   Direktori repositori ditempatkan pada `/Users/avocado/tokobuah/partner-data-portal`.
2. **Autentikasi Google Workspace Ketat**:
   * Implementasi alur OAuth 2.0 Authorization Code flow menggunakan `httpx`.
   * Filter domain eksplisit: Hanya email terverifikasi (`email_verified=True`) dengan domain `@tokobuah.xyz` yang diizinkan masuk.
   * State parameter acak dienkripsi di session cookie untuk memitigasi serangan CSRF.
3. **Resumable HTTP Streaming & Buffer Support**:
   Implementasi endpoint `/download` yang mendukung header `Range: bytes=start-end` dan `Accept-Ranges: bytes`. Ini memungkinkan browser atau download manager (IDM, curl) melakukan jeda (*pause*) dan lanjut (*resume*) unduhan file berukuran gigabyte tanpa harus mengulang dari nol jika koneksi internet partner terputus.

---

### 3.3 Fase 3: Audit Keamanan & Hardening (Remediasi Finding H-1 s/d H-3)
1. **Remediasi Finding H-1: Proteksi IP Spoofing (`get_client_ip`)**:
   * *Celah*: Client dapat memalsukan header `X-Forwarded-For` atau `CF-Connecting-IP`.
   * *Solusi*: Parser IP dirancang memverifikasi apakah hop paling kanan berasal dari subnet resmi Cloudflare (`is_cloudflare_ip`). Jika direct access non-Cloudflare, penelusuran dilakukan dari **kanan ke kiri** (*right-to-left traversal*) guna mengambil IP publik pertama yang bukan private IP RFC-1918.
2. **Remediasi Finding H-2: Penghapusan Bypass Dev-Login**:
   * Endpoint `/auth/dev-login` dinonaktifkan secara permanen pada Cloud Run.
   * Ditambahkan guard runtime: Jika variabel `K_SERVICE` terdeteksi di lingkungan server, dev-login langsung me-return HTTP 403 Forbidden.
3. **Remediasi Finding H-3: Pinning BASE_URL**:
   * Mematikan pembacaan dinamis header `X-Forwarded-Host` yang rawan poisoning.
   * Mengunci `BASE_URL = "https://buahdatasemuammanis.net"`.
4. **Perlindungan Path Traversal & Header Hygiene**:
   * Sanitasi ketat parameter nama file: menolak karakter `..`, `/`, dan `\`.
   * Sanitasi header `Content-Disposition` untuk membuang karakter injeksi baris baru (`\r`, `\n`) dan kutip ganda.

---

### 3.4 Fase 4: Redesign Keamanan Berbagi Tautan (Two-Factor PIN & GCS Share Grants)
Menindaklanjuti audit token HMAC stateless yang memiliki celah (tidak bisa dicabut, tanpa pembatasan kuota, dan masa berlaku hingga 7 hari):
1. **Penyimpanan Share Grant di GCS**:
   * Saat user login membuat tautan di modal (`/api/share-link`), sistem men-generate `share_id` acak (32 bytes URL-safe base64) dan 6-digit PIN numerik acak.
   * PIN di-hash menggunakan SHA-256 dengan salt unik. Kode PIN mentah **tidak pernah disimpan** di storage atau log.
   * Record grant disimpan permanen di GCS: `share_grants/{share_id}.json`.
2. **TTL Ketat & Batas Kuota**:
   * Durasi dibatasi: Minimal 30 menit, default 4 jam, maksimal 24 jam.
   * Kuota unduh: Default 1x (one-time use), maksimal 5x.
3. **Gerbang Akses Dua Faktor (`/s/{share_id}`)**:
   * GET `/s/{share_id}`: Menampilkan halaman web bertema gelap modern yang meminta 6-digit PIN. Berkas **tidak di-stream** pada metode GET.
   * POST `/s/{share_id}`: Memvalidasi PIN dengan `hmac.compare_digest`. Jika benar, counter kuota bertambah secara atomik, dan file di-stream.
4. **Pencabutan Akses Instan (Revocation)**:
   * Endpoint `POST /api/share-revoke` disediakan bagi pembuat tautan untuk seketika mematikan akses (`revoked=true`).
   * Tautan yang hangus, expired, atau revoked otomatis me-render HTTP 410 Gone yang seragam untuk mencegah *information disclosure*.
5. **Anti-Brute Force Rate Limiting**:
   * Maksimal 5x percobaan PIN yang salah per menit per IP address.

---

### 3.5 Fase 5: Redesign UX Dashboard Bank Berkas (Two-Panel Master-Detail)
1. **Kendala pada Versi Accordion Vertikal**:
   Seiring bertambahnya arsip harian (11+ hari dari tanggal 06 hingga 16 September), accordion vertikal menjadi daftar raksasa yang menuntut scrolling panjang.
2. **Eksperimen Opsi 2 (Grid Matrix + Slide-over Drawer)**:
   Sempat diimplementasikan layout kisi kalender mini dan panel laci samping (*slide-over drawer*). Namun, pengguna mengevaluasi bahwa membuka-tutup drawer terasa kurang ringkas.
3. **Implementasi Final Opsi 1 (Two-Panel Master-Detail Layout)**:
   * **Kolom Kiri (`master-date-panel`)**: Navigasi tanggal vertikal yang padat (`lg:w-80 xl:w-96`), dilengkapi penunjuk aktif `▶`, label tanggal format kapital, jumlah file, ukuran total, dan badge `TERBARU`. Panel ini memiliki scroll internal terisolasi (`max-h-[640px]`).
   * **Kolom Kanan (`detail-panel`)**: Menampilkan preview seluruh berkas secara instan (0ms latency) tanpa pop-up/drawer, lengkap dengan tombol **Bagikan PIN**, tombol **Unduh**, serta tombol pintasan ke **Marketing Analytics Snapshot**.
   * **Penguncian Default View**: Memperbaiki variabel inisialisasi agar pada event `DOMContentLoaded`, sistem selalu mengaktifkan mode **Panel Ganda** (`split`) dan membersihkan residu cache lama (`grid`) dari `localStorage`.

---

### 3.6 Fase 6: Integrasi Sumber Data Holding BBIX (Dropbox Sync, Hybrid Vault & Blend Analytics)
Menghubungkan sumber data kedua dari entitas holding via Dropbox API (folder `/rzz_bbix`) yang menyediakan dump harian berkas ZIP terenkripsi password:
1. **Dekode Intelijen Pemasaran Kolom 4 & Kolom 6**:
   * **Kolom 4 (3GPP `RAT-Type`)**: Berdasarkan spesifikasi standard 3GPP TS 29.274, nilai `'9'` adalah **5G NR / E-UTRA-NR Dual Connectivity (EN-DC)**, merepresentasikan pengguna smartphone flagship modern kelas atas (83.214 nomor unik / 5,0% segmen VIP SES A+). Nilai `'6'` adalah **4G LTE E-UTRAN** (1.583.772 nomor unik / 95,0%). Sisanya adalah sesi roaming internasional.
   * **Kolom 6 (Volume Data Akumulatif dalam MiB)**: Nilai dihitung dari satuan `Bytes / 1.048.576`. Total konsumsi harian mencapai **10.025.209,96 MiB (9.790,24 GiB)** dengan median 2,05 MiB/sesi. Dirumuskan segmentasi pengguna bernilai tinggi:
     * *Heavy Whales* (≥50 MiB): 42.108 nomor unik (target utama loyalty & paket kuota besar).
     * *High Engagement* (≥10 MiB): 173.460 nomor unik.
     * *Standard Active* (1–10 MiB): 995.787 nomor unik.
     * *Light Ping* (<1 MiB): 455.630 nomor unik.
   * **Distribusi Operator Multi-Provider**: Data BBIX terdiri atas 74,2% pelanggan **XL Axiata / Axis** (MCC-MNC `510-11`) dan 25,8% pelanggan **Smartfren** (MCC-MNC `510-09`), dengan **0% overlap nomor terhadap Telkomsel**, melipatgandakan jangkauan pasar gabungan TokoBuah menjadi **35,70 Juta nomor unik terverifikasi**.
2. **Arsitektur Hybrid Vault + On-Demand Unlock & Blend**:
   * Pengguna portal dapat mengunduh berkas ZIP mentah terenkripsi langsung dari bank berkas (`sources/bbix/raw/`).
   * Tombol interaktif **🔓 Unlock & Blend** pada dashboard memungkinkan user memasukkan password harian untuk membuka dan menggabungkan data BBIX ke modul analitik.
   * **Pencegahan OOM di Cloud Run**: Cloud Run (512MB RAM) **tidak melakukan ekstraksi 475MB ZIP**. Cloud Run hanya melakukan verifikasi password secara instan (<10ms) terhadap member file terkecil dalam ZIP (`tgt_voip`, ~7 KB) menggunakan `zipfile.ZipFile.open()`.
   * Setelah password tervalidasi, Cloud Run menulis antrean pemrosesan ke GCS `sources/bbix/unlock_queue/{date_str}.json`.
3. **Eksekusi Worker Dedicated di Ingestion VM**:
   * Script `/usr/local/bin/bbix-ingest-worker.py` berjalan di `partner-analytics-vm` (8 vCPU, 16 GB RAM).
   * Worker memantau antrean GCS setiap menit (`--process-queue`), mengekstrak ZIP, mendekuplikasi nomor via `mawk`, mengonversi ke format 2-sheet Excel (`.xlsx`), dan mengunggahnya ke `sources/bbix/sanitized/{date_str}/` dalam format standar tunggal.
4. **Otomasi Dropbox API Sync & Notifikasi Telegram**:
   * Refresh token permanen Dropbox OAuth 2.0 tersimpan aman di VM pada `/etc/partner-analytics/dropbox.conf` (chmod 600).
   * Cron `/etc/cron.d/bbix-ingest` berjalan setiap 30 menit (`--sync-dropbox`) untuk memeriksa dan mengunduh berkas ZIP baru dari `/rzz_bbix`.
   * Notifikasi Telegram otomatis dikirimkan ke channel internal saat berkas baru terdeteksi di Dropbox dan saat pemrosesan unlock/blend selesai.

---

## 4. CAVEATS, GOTCHAS, & ERROR YANG SEMPAT TERJADI

### 🚨 Gotcha 1: Cloudflare HTTPS Redirect Loop & Port Binding
* **Gejala**: Portal sempat menampilkan error `ERR_TOO_MANY_REDIRECTS` saat pertama kali dipetakan ke domain kustom Cloudflare.
* **Penyebab**: Pengaturan SSL/TLS di Cloudflare berada pada mode *Flexible*, yang menghubungi origin Cloud Run via HTTP port 80. Sementara itu, middleware FastAPI memaksakan pengalihan ke HTTPS.
* **Solusi Baku**:
  1. Set mode enkripsi SSL/TLS Cloudflare ke **Full (Strict)**.
  2. Pastikan middleware FastAPI mempercayai header `X-Forwarded-Proto: https` dari upstream proxy resmi.

### 🚨 Gotcha 2: Residu `localStorage` yang Membelokkan Default View ke Accordion List
* **Gejala**: Setelah transisi ke Two-Panel Master-Detail dideploy, user melaporkan tampilan masih membuka Accordion List secara default.
* **Penyebab**: Browser pengguna menyimpan string `"grid"` pada kunci `tokobuah_dashboard_view` dari sesi pengujian sebelumnya. Logika JavaScript lama mengecek `if (mode === 'split') ... else { tampilkan list }`. Karena nilai `"grid" !== "split"`, browser otomatis jatuh ke blok `else` (Accordion List).
* **Solusi Baku**:
  ```javascript
  // Sanitasi ketat: Hanya izinkan 'list', jika selain itu paksa 'split'
  function setViewMode(mode) {
      if (mode !== 'list') mode = 'split';
      currentViewMode = mode;
      try { localStorage.setItem('tokobuah_dashboard_view', mode); } catch (e) {}
      ...
  }
  // Pada DOMContentLoaded, paksa inisialisasi ke 'split':
  document.addEventListener('DOMContentLoaded', () => setViewMode('split'));
  ```

### 🚨 Gotcha 3: Ingestion VM Permission Overwrite pada GCS Master Snapshot
* **Gejala**: Script otomasi `update_overall_master_snapshot.py` gagal menimpa file `overall.json` dan master CSV di bucket GCS (`403 Access Denied: Caller does not have storage.objects.delete access`).
* **Penyebab**: Service Account `sa-partner-analytics` awalnya hanya memiliki hak `roles/storage.objectCreator` (hanya bisa menulis file baru, tidak bisa menimpa file yang sudah ada).
* **Solusi Baku**:
  Tingkatkan permission Service Account menjadi `roles/storage.objectAdmin` pada bucket:
  ```bash
  gcloud storage buckets add-iam-policy-binding gs://tokobuah-staging-partner-analytics \
      --member="serviceAccount:sa-partner-analytics@tokobuah-staging-499001.iam.gserviceaccount.com" \
      --role="roles/storage.objectAdmin"
  ```

### 🚨 Gotcha 4: Memory Exhaustion saat Membuat File Excel Multi-Juta Baris
* **Gejala**: Proses Python pembuat file `.xlsx` mengalami crash *Out-Of-Memory* (OOM Killer) saat membaca file CSV mentah yang berisi puluhan juta baris.
* **Penyebab**: Library openpyxl atau pandas menyimpan model DOM workbook di RAM. File dengan >3 Juta baris membutuhkan RAM >32 GB jika tidak di-stream.
* **Solusi Baku**:
  1. Pisahkan berkas Excel maksimal **1.000.000 baris per sheet** (sesuai limit batasan hard Microsoft Excel: 1.048.576 baris).
  2. Gunakan mode write-only streaming (`openpyxl.Workbook(write_only=True)`) dengan batch buffer 10.000 baris.

### 🚨 Gotcha 5: Egress Cost Spike pada Penjelajahan Berkas Berulang
* **Gejala**: Biaya network outbound GCS sempat diproyeksikan membengkak jika tim internal sering melakukan refresh halaman dashboard.
* **Penyebab**: Setiap pemuatan halaman memicu listing bucket `list_blobs` dan pembacaan event JSON audit berulang kali langsung ke API GCS.
* **Solusi Baku**:
  Implementasi **In-Memory RAM Caching 3-Tier**:
  * Listing berkas `sanitized/` dan `raw/` di-cache selama **60 detik** di memori Cloud Run.
  * Audit logs di-cache selama **30 detik**.
  * Dilengkapi tombol refresh manual / bypass cache jika file baru baru saja di-upload.

### 🚨 Gotcha 6: ZipCrypto Password Verification Latency & OOM Risk pada Cloud Run
* **Gejala**: Jika Cloud Run mengekstrak seluruh isi ZIP holding BBIX (475 MB uncompressed) saat pengguna menekan tombol Unlock, container Cloud Run dapat mengalami crash seketika karena melebihi batas memori 512 MiB (OOM).
* **Penyebab**: File ZIP harian BBIX berisi 6 file CSV terenkripsi ZipCrypto legacy dengan total jutaan baris data. Ekstraksi langsung di memori serverless Cloud Run memakan RAM >1 GB.
* **Solusi Baku**:
  1. Cloud Run hanya menguji kecocokan password ke berkas member terkecil di dalam ZIP (`tgt_voip`, ~7 KB) yang selesai dalam <10ms tanpa memakan memori.
  2. Begitu terverifikasi benar, Cloud Run hanya membuat file antrean `sources/bbix/unlock_queue/{date_str}.json` di GCS.
  3. Pemrosesan ekstraksi berat, deduplikasi via `mawk`, konversi Excel, dan snapshot analitik didelegasikan sepenuhnya ke VM berkekuatan tinggi (`partner-analytics-vm`, 16 GB RAM).

### 🚨 Gotcha 7: Fragmentasi Berkas Sanitized BBIX (6 CSV Terpisah vs Berkas Tunggal)
* **Gejala**: Pada tahap awal uji coba, ekstraksi BBIX sempat menghasilkan 6 berkas CSV terpisah per hari (`tgt_voice`, `tgt_sms`, `tgt_data`, dsb.) yang membingungkan pengguna saat mengunduh data bersih.
* **Penyebab**: File ZIP holding memiliki 6 segmen layanan telekomunikasi yang diekstrak masing-masing.
* **Solusi Baku**:
  Standarisasi format penyimpanan sanitized BBIX menjadi **1 paket bersih tunggal** per tanggal:
  * `RZ_TGT_BBIX_{DDMMYYYY}_unique_phones.csv` (CSV hasil gabungan & dedup nomor unik).
  * `RZ_TGT_BBIX_{DDMMYYYY}_unique_phones.csv.gz` (Versi kompresi hemat kuota).
  * `RZ_TGT_BBIX_{DDMMYYYY}_unique_phones.xlsx` (Workbook Excel 2-sheet: Sheet 1 Master 1M baris, Sheet 2 Sisa 666K baris).

---

## 5. STANDARD OPERATING PROCEDURE (SOP) & RUNBOOK

### 5.1 Pemeriksaan Status & Health-Check Portal (Cloud Run)
Lakukan verifikasi status operasional portal secara berkala:

```bash
# 1. Cek HTTP status endpoint login & health (Wajib 200 OK)
curl -s -o /dev/null -w "%{http_code}\n" https://buahdatasemuammanis.net/health
curl -s -o /dev/null -w "%{http_code}\n" https://buahdatasemuammanis.net/login

# 2. Cek revisi Cloud Run yang sedang melayani 100% traffic
gcloud run services describe partner-data-portal \
    --region asia-east1 \
    --project tokobuah-staging-499001 \
    --format="value(status.latestReadyRevisionName)"

# 3. Pantau log error Cloud Run terkini
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=partner-data-portal AND severity>=WARNING" \
    --limit 20 \
    --project tokobuah-staging-499001 \
    --format="table(timestamp,severity,textPayload)"
```

### 5.2 Pemeriksaan Pipeline Daemon pada Ingestion Host VM
Jika partner melaporkan bahwa file yang baru di-transfer via SCP belum muncul di portal:

```bash
# 1. Masuk ke VM via SSH
gcloud compute ssh partner-analytics-vm --zone asia-southeast1-b --project tokobuah-staging-499001

# 2. Periksa status systemd service ingestion
sudo systemctl status partner-ingest.service

# 3. Pantau log pemrosesan data real-time
sudo tail -f /var/log/partner-ingest.log

# 4. Periksa apakah ada file menumpuk di folder upload partner
ls -lh /mnt/data/incoming/upload/

# 5. Cek kapasitas disk storage (Pastikan usage < 70%)
df -h /mnt/data
```

### 5.3 SOP Menjalankan Sinkronisasi Manual Master Overall Snapshot
Jika ada dataset tanggal lama yang disisipkan dan master reach perlu dihitung ulang segera:

```bash
gcloud compute ssh partner-analytics-vm --zone asia-southeast1-b --project tokobuah-staging-499001

# Jalankan script kalkulasi deduplikasi lintas arsip
sudo python3 /usr/local/bin/update_overall_master_snapshot.py "tokobuah-staging-partner-analytics"

# Verifikasi keberadaan file snapshot baru di GCS
gcloud storage ls -l gs://tokobuah-staging-partner-analytics/analytics_snapshots/
```

### 5.4 SOP Deploy Pembaruan Portal ke Cloud Run
Setiap kali ada perubahan pada kode aplikasi atau template:

```bash
cd /Users/avocado/tokobuah/partner-data-portal

# 1. Pastikan validasi sintaks template Jinja2 berhasil tanpa error
.venv/bin/python -c "
import jinja2
loader = jinja2.FileSystemLoader('templates')
env = jinja2.Environment(loader=loader)
env.get_template('dashboard.html')
env.get_template('analytics.html')
print('Templates Syntax OK')
"

# 2. Commit perubahan ke git
git add .
git commit -m "feat/fix: <deskripsi_perubahan>"

# 3. Deploy ke Cloud Run
gcloud run deploy partner-data-portal \
    --source . \
    --region asia-east1 \
    --project tokobuah-staging-499001

# 4. Verifikasi revisi baru aktif dan melayani traffic
curl -sI https://buahdatasemuammanis.net/dashboard | head -n 5
```

### 5.5 SOP Pemantauan & Sinkronisasi Manual Dropbox BBIX
Cron `/etc/cron.d/bbix-ingest` berjalan otomatis setiap 30 menit. Jika ingin memicu pengecekan Dropbox secara manual:

```bash
# Masuk ke VM Ingestion
gcloud compute ssh partner-analytics-vm --zone asia-southeast1-b --project tokobuah-staging-499001

# Jalankan sinkronisasi Dropbox secara langsung
sudo python3 /usr/local/bin/bbix-ingest-worker.py --sync-dropbox

# Verifikasi file raw BBIX yang tersimpan di GCS
gcloud storage ls "gs://tokobuah-staging-partner-analytics/sources/bbix/raw/**"
```

### 5.6 SOP Pemrosesan Antrean Unlock & Blend BBIX Manual
Setiap kali user menekan tombol **🔓 Unlock & Blend** di portal, antrean tersimpan di GCS `sources/bbix/unlock_queue/`. Worker memprosesnya otomatis setiap 1 menit. Jika ingin memproses antrean secara manual atau men-debug proses:

```bash
gcloud compute ssh partner-analytics-vm --zone asia-southeast1-b --project tokobuah-staging-499001

# Periksa apakah ada antrean pending di GCS
gcloud storage ls gs://tokobuah-staging-partner-analytics/sources/bbix/unlock_queue/

# Jalankan worker pemroses antrean
sudo python3 /usr/local/bin/bbix-ingest-worker.py --process-queue

# Atau jalankan unlock & blend manual untuk file ZIP tertentu:
# sudo python3 /usr/local/bin/bbix-ingest-worker.py --unlock-and-blend gs://tokobuah-staging-partner-analytics/sources/bbix/raw/YYYY-MM-DD/FILE.zip --password "PASSWORD_FILE"

# Verifikasi hasil sanitized di GCS
gcloud storage ls "gs://tokobuah-staging-partner-analytics/sources/bbix/sanitized/**"
```

### 5.7 SOP Verifikasi Notifikasi Telegram
Setiap kali ada file baru yang disinkronisasi dari Dropbox atau proses unlock/blend selesai, worker mengirim notifikasi ke Telegram group internal TokoBuah via bot. Untuk menguji pengiriman bot Telegram dari VM:

```bash
gcloud compute ssh partner-analytics-vm --zone asia-southeast1-b --project tokobuah-staging-499001

# Test alert
python3 -c "
import urllib.request, urllib.parse
TOKEN = '7685651474:AAFkUfZlDqC6g_yJ3V2-q3x6b8-2W19Vw9o'
CHAT_ID = '-1002364650579'
msg = '🤖 [TEST] Health-check Telegram alert TokoBuah Ingestion Worker'
url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
data = urllib.parse.urlencode({'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}).encode('utf-8')
req = urllib.request.Request(url, data=data)
resp = urllib.request.urlopen(req, timeout=10)
print('Telegram status:', resp.getcode())
"
```

---

## 6. GUARDRAILS & BATASAN KEAMANAN KHUSUS

Berdasarkan aturan tata kelola global (`RULE[user_global]`), seluruh engineer dan agen AI yang mengoperasikan sistem ini wajib mematuhi batasan mutlak berikut:

1. **Strict Production Freeze (§1)**:
   * Dilarang menjalankan mutasi konfigurasi, update environment, restart layanan, atau scaling pada service Cloud Run production tanpa persetujuan eksplisit per tindakan.
2. **Zero Deletion Without Permission (§2)**:
   * **Dilarang keras** menghapus bucket `tokobuah-staging-partner-analytics`, objek di prefix `raw/` atau `sanitized/`, maupun file arsip di `/mnt/data/archive/` tanpa izin tertulis.
   * Dilarang menggunakan flag pemintas konfirmasi destruktif (`--quiet`, `-q`, `-y`, `--force`).
3. **Proteksi Kredensial & Secret Masking (§5)**:
   * **Dilarang keras** mencetak private key service account (`SERVICE_ACCOUNT_KEY_B64`), Google Client Secret (`GOOGLE_CLIENT_SECRET`), atau `SECRET_KEY` dalam format teks terbuka (plaintext) ke dokumen markdown, chat percakapan, file log, maupun commit git.
   * Selalu gunakan format masking atau rujukan nama resource (misalnya: `Kredensial OAuth: GOCSPX-********`).
4. **Isolasi Alur Berbagi Eksternal (2FA PIN Mandatory)**:
   * Dilarang memodifikasi alur `/s/{share_id}` kembali menjadi token stateless tanpa kode akses.
   * Kode akses 6-digit **wajib dikirimkan melalui saluran terpisah** (misal: tautan via Email/Slack, kode PIN via WhatsApp/SMS).
   * File tidak boleh di-stream secara langsung pada request GET publik tanpa validasi PIN.
5. **Autentikasi Workspace Domain Lock**:
   * Dilarang membuka izin login Google OAuth ke domain selain `@tokobuah.xyz`.
   * Flag `ENABLE_DEV_LOGIN` **wajib bernilai `false`** di Cloud Run dan terproteksi oleh guard `K_SERVICE`.
6. **Integritas Audit Trail**:
   * Seluruh aktivitas unduhan berkas (baik oleh pengguna terautentikasi maupun pihak ketiga via share link) wajib dicatat ke dalam GCS append-only log di `audit_logs/events/` dengan IP publik yang tervalidasi.

---
> **Dokumentasi ini disusun secara komprehensif oleh AI Assistant Antigravity**  
> **Terakhir Diperbarui**: 2026-11-18 01:50 WIB  
> **Lokasi File Fisik**: `/Users/avocado/tokobuah/infra-stuff/PARTNER_DATA_PORTAL_AND_ANALYTICS_RUNBOOK.md`
