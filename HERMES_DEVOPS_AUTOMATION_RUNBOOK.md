# 🛠️ HERMES DEVOPS AGENT & INFRASTRUCTURE AUTOMATION RUNBOOK
> **Path**: `/Users/avocado/tokobuah/infra-stuff/HERMES_DEVOPS_AUTOMATION_RUNBOOK.md`  
> **Classification**: Internal Engineering Knowledge Base & SRE Operations Runbook  
> **Target Audience**: SREs, Platform Engineers, DevOps, & Incoming Autonomous AI Agents  
> **Status**: Living Document (Updated Post-Incident & Post-Migration)  
> **Governing Rules**: Strict read-only audit protocol, Zero deletion without approval, Strict secret masking.

---

## 📑 DAFTAR ISI
1. [Ringkasan Eksekutif & Tujuan Sesi](#1-ringkasan-eksekutif--tujuan-sesi)
2. [Topologi & Komponen Terkait](#2-topologi--komponen-terkait)
3. [Catatan Perubahan & Kronologi Implementasi](#3-catatan-perubahan--kronologi-implementasi)
4. [Caveats, Gotchas, & Post-Mortem Insiden](#4-caveats-gotchas--post-mortem-insiden)
5. [Standard Operating Procedure (SOP) & Runbook Operasional](#5-standard-operating-procedure-sop--runbook-operasional)
6. [Guardrails & Batasan Keamanan Khusus](#6-guardrails--batasan-keamanan-khusus)

---

## 1. RINGKASAN EKSEKUTIF & TUJUAN SESI

Sesi rekayasa dan operasional ini berfokus pada penguatan arsitektur otomasi agen AI internal Tokobuah (**Hermes Agent Stack**), stabilisasi jalur interaksi messaging (Telegram Gateway), pengamanan database OLTP production dari beban query pelaporan, serta standarisasi deploy serverless di Google Cloud Platform.

### Masalah Pokok yang Diselesaikan:
1. **Cloud SQL Production Overload**:
   Query pelaporan harian (`daily_game_engine_bulletin.py`) pada instance `prod-game-mysql` (database `game_engine`) men-scan **38,7 juta baris** (37–41 detik CPU time) per eksekusi karena ketiadaan index leading pada kolom `created_at` di tabel terpartisi `game_transactions`. Masalah ini dieliminasi dengan memindahkan sumber data ke Kafka event streaming (`game-transaction-*`) dan point-lookup PK tanpa menyentuh beban scan database OLTP.
2. **Isolasi & Kontrol Interaksi Bot di Forum Topic Telegram**:
   Eksperimen penempatan bot Project Management (`tokobuah-pm` / ID: `8502149317`) ke grup supergroup forum `It tok` (Topic 30 / `DevSecOps Area 18+`). Dikonfigurasikan pembatasan ketat: hanya user `8838704666` (`@Ibeibe69`) yang dapat memberikan perintah, penolakan sopan otomatis untuk user lain, dan penekanan output perantara (*suppression of intermediate tool progress*) di grup agar tidak membanjiri chat. Pada akhirnya, user memutuskan untuk membatalkan penempatan grup dan mengembalikan bot murni ke interaksi private DM yang bersih dan stabil.
3. **Container Ephemeral Reset & Tool Recovery**:
   Insiden hilangnya CLI binary kritis (`gcloud`, `kubectl`, `gke-gcloud-auth-plugin`) di dalam container `hermes-pm` setelah proses `docker-compose recreate`. Diidentifikasi bahwa root filesystem container bersifat *ephemeral*, sedangkan dependensi eksternal belum dipetakan ke direktori persisten. Dipulihkan secara permanen dengan menempatkan Google Cloud SDK mandiri di `/opt/data/gcloud-sdk/` yang bertahan lintas siklus hidup container.
4. **Resiliensi Konektivitas Telegram & Upstream Model 9Router**:
   Penanganan kegagalan berseri: error upstream provider DeepSeek (HTTP 503 `response_format unavailable`), flood control Telegram API, hingga stall koneksi HTTP/2 pada endpoint fallback `149.154.166.110` yang sempat memicu reconnect loop 60 detik.

---

## 2. TOPOLOGI & KOMPONEN TERKAIT

### 2.1 Host Infrastructure & Virtual Machine
| Atribut | Nilai / Spesifikasi |
| :--- | :--- |
| **GCP Project** | `tokobuah-production` / `tokobuah-staging-499001` |
| **VM Instance Host** | `hermes-agent-host` |
| **Public IP** | `34.87.88.43` |
| **Region / Zone** | `asia-southeast1-b` (Singapore) |
| **OS / Kernel** | Debian GNU/Linux 13 (Trixie/Sid) / Linux 6.x x86_64 |
| **System User** | `avocado` |
| **Deployment Root** | `/home/avocado/hermes-deploy` |
| **SSH Identity Path** | `/Users/avocado/.ssh/google_compute_engine` |

### 2.2 Docker Compose Stack (`/home/avocado/hermes-deploy/docker-compose.yml`)
* **`hermes-pm`** (Agent 2 - Project Management Bot):
  * Image: `nousresearch/hermes-agent:latest`
  * Bot Telegram: `@tokobuah_pm_bot` (Bot ID: `8502149317`)
  * Data Volume: `./pm:/opt/data` (persistent state, sessions, custom tools, and SDKs)
  * Code Volume: `./src:/opt/src`
  * Process Supervisor: s6-svscan (`/package/admin/s6/command/s6-svscan`)
  * Runtime Process: Python virtual environment `/opt/hermes/.venv/bin/hermes gateway run --replace`
* **`hermes-crawler`** (Agent 3 - Asset Scraper & Monitoring Bot):
  * Image: `nousresearch/hermes-agent:latest`
  * Bot Telegram: `@tokobuah_crawler_bot`
  * Tugas: Kafka consumer lag monitor, partner-schema watchdog, alert notifications.
* **`hermes-pga`** (Agent 1 - PGA Operations Bot):
  * Image: `nousresearch/hermes-agent:latest`
  * Bot Telegram: `@joyboy_QA` / PGA Agent Bot.
* **`9router`** (Local LLM Gateway / Proxy Router):
  * Image: `decolua/9router:latest`
  * Port Binding: `0.0.0.0:20128` (Internal Docker network: `http://9router:20128/v1`)
  * Routing Combo: `free-combo` (Round-robin antara `deepseek/deepseek-v4-flash` dan `deepseek/deepseek-v4-pro-max`).
* **`tokobuah-agentic-hub`**:
  * Host network proxy and orchestration bridge.

### 2.3 Jaringan & Platform Eksternal
* **Telegram Messaging**:
  * Authorized Operator ID: `8838704666` (`@Ibeibe69` / display: `Avocado`).
  * Target Supergroup: `It tok` (Chat ID: `-1003992607433`, Forum Supergroup).
  * Target Forum Thread: Topic ID `30` (`DevSecOps Area 18+`).
  * Telegram Bot API Host: `api.telegram.org` (Resolved via IPv4 `149.154.166.110` / IPv6 `2001:67c:4e8:f004::9`).
* **Database Target**:
  * Cloud SQL: `prod-game-mysql` (Instance DB OLTP game).
  * Target Schema: `game_engine`.
  * Target Table: `game_transactions` (Partisi bulanan: `PARTITION BY RANGE (to_days(created_at))`).
* **Event Broker**:
  * Confluent Cloud Kafka (Cluster multi-region).
  * Ingestion Topics: `game-transaction-{tenant}`, `transactional-engine-ledger`.

---

## 3. CATATAN PERUBAHAN & KRONOLOGI IMPLEMENTASI

### 3.1 Eliminasi Beban Cloud SQL MySQL (Query Hash `15340764381075562213`)
* **Kondisi Awal**:
  Script `daily_game_engine_bulletin.py` mengeksekusi:
  ```sql
  SELECT p.code, COUNT(*) AS cnt
  FROM game_transactions gt
  JOIN providers p ON gt.provider_id = p.id
  WHERE gt.created_at >= NOW() - INTERVAL 24 HOUR
  GROUP BY p.code;
  ```
  Menghasilkan *Full Partition Scan* pada partisi berjalan bulan Oktober/November (~38,7 juta baris), memakan CPU hingga 40,9 detik, dan masuk sebagai top load query di Query Insights.
* **Tindakan Perbaikan**:
  1. Script bulletin dicabut dari ketergantungan scan tabel `game_transactions`.
  2. Perhitungan agregat dialihkan dengan membaca statistik streaming dari Kafka consumer metrics (`game-transaction-*`).
  3. Baris `success: ~... req processed` dipertahankan dengan mekanisme metadata point-lookup, memangkas scan baris dari **38,7 juta menjadi 0 baris**.

### 3.2 Percobaan Penempatan Bot di Forum Topic 30 & Revert
* **Kebutuhan Awal**:
  * Bot hanya aktif dan merespons pada Topic `30` grup `It tok`.
  * Hanya `@Ibeibe69` (ID: `8838704666`) yang boleh memberikan perintah.
  * User lain yang me-mention bot menerima pesan penolakan: *"Mohon maaf, saya hanya bisa disuruh oleh @Ibeibe69"*.
  * Di topic grup, bot hanya mengembalikan hasil akhir (*no intermediate step/tool bubbles*), sedangkan di DM tetap menampilkan step lengkap.
* **Perubahan yang Sempat Diaplikasikan**:
  1. Penambahan `TELEGRAM_ALLOWED_TOPICS=30` pada service `hermes-pm` di `docker-compose.yml`.
  2. Patch pada `plugins/platforms/telegram/adapter.py`:
     * Logging audit update grup mentah.
     * Fungsi `_reply_non_owner_mention` untuk mendeteksi mention dari user non-owner pada Topic 30 dan membalas teks penolakan dengan cooldown 15 detik.
  3. Patch pada `gateway/run.py` & `pm/config.yaml`:
     * Penambahan resolver `display.platforms.telegram_group`.
     * Konfigurasi grup: `tool_progress: "off"`, `interim_assistant_messages: false`, `streaming: false`, `long_running_notifications: false`.
* **Keputusan Akhir (Revert)**:
  * User memutuskan membatalkan rencana integrasi di grup topic (*"saya cancel aja deh plan add bot di topic itu saya urungkan niat"*).
  * `docker-compose.yml` di-restore dari backup `docker-compose.yml.bak_topic30`.
  * `pm/config.yaml` di-restore dari `config.yaml.bak_group_display`.
  * Folder patch mount dilepas dan container di-recreate bersih.
  * Bot kembali murni melayani private DM operator secara aman.

### 3.3 Pemulihan Permanen Google Cloud SDK (`gcloud` & `kubectl`)
* **Akar Masalah**:
  Saat container `hermes-pm` dibuat ulang dari image base, file di `/usr/local/bin/gcloud` dan `/usr/local/bin/kubectl` terhapus karena image dasar `nousresearch/hermes-agent:latest` tidak menyertakan SDK Google Cloud secara bawaan.
* **Solusi Permanen**:
  1. Mengunduh arsip mandiri Google Cloud CLI x86_64 resmi (`google-cloud-cli-linux-x86_64.tar.gz`).
  2. Mengekstrak langsung ke volume persisten host: `/opt/data/gcloud-sdk/google-cloud-sdk/`.
  3. Menginstal komponen: `gcloud components install kubectl gke-gcloud-auth-plugin --quiet`.
  4. Membuat symlink ganda di `/opt/data/bin/` (persisten) dan `/usr/local/bin/` (runtime container).
  5. Konfigurasi kredensial dan service account (`hermes-monitor-sa@tokobuah-staging-499001.iam.gserviceaccount.com`) tetap aman dan terbaca di `/opt/data/.config/gcloud`.

---

## 4. CAVEATS, GOTCHAS, & POST-MORTEM INSIDEN

### 🚨 Gotcha 1: Ephemeral Filesystem pada Docker Container Hermes
* **Fenomena**: Tool yang diinstal manual dengan `apt-get` atau diekstrak ke `/usr/local/bin` di dalam container akan hilang saat container mengalami update, recreate, atau restart via compose.
* **Aturan Pencegahan**: Semua tool, binary, script, dan SDK **wajib diletakkan di dalam mount `/opt/data/`** (host: `/home/avocado/hermes-deploy/pm/`). Gunakan script bootstrap atau symlink dari `/opt/data/bin/` agar tahan terhadap re-deploy container.

### 🚨 Gotcha 2: Telegram Bot Privacy Mode pada Forum Supergroup
* **Fenomena**: Bot yang di-add ke grup forum tidak menerima update pesan sama sekali (`RAW update id` tidak muncul di log) meskipun bot di-mention secara eksplisit `@tokobuah_pm_bot`.
* **Penyebab**: Pengaturan *Group Privacy* bawaan Telegram di `@BotFather` memblokir pengiriman pesan grup jika bot berstatus anggota biasa non-admin.
* **Solusi Baku**:
  1. Matikan privacy mode melalui `@BotFather` (`/mybots` → pilih bot → *Bot Settings* → *Group Privacy* → *Turn off*).
  2. **PENTING**: Perubahan Group Privacy **tidak berlaku surut**. Bot wajib di-*kick* (keluarkan) dari grup lalu di-*invite* ulang agar izin baru aktif di server Telegram.
  3. Alternatif tercepat: Promosikan bot menjadi Admin grup dengan hak minimal (*Manage Topics*).

### 🚨 Gotcha 3: Telegram API HTTP/2 Stall & Exponential Backoff Reconnect
* **Fenomena**: Bot mendadak diam beberapa menit, tidak membalas chat DM, dan log menunjukkan `Telegram network error ... reconnecting in 60s`.
* **Penyebab**:
  * Koneksi HTTP/2 ke IP sticky Telegram `149.154.166.110` terkadang mengalami *TCP window freeze* atau *flood control rate-limit* dari sisi server Telegram.
  * Library Telegram Python masuk ke siklus penundaan eksponensial (5s → 10s → 20s → 40s → 60s).
* **Solusi**: Jangan restart container secara terburu-buru karena akan me-reset antrean pending updates. Tunggu hingga siklus polling mencatatkan `Telegram polling confirmed healthy: getUpdates progressing` secara alami, atau restart service gateway via s6-svc: `/command/s6-svc -r /run/service/gateway-default`.

### 🚨 Gotcha 4: Model Provider 503 ("response_format type is unavailable")
* **Fenomena**: Bot membalas `⚠️ The model provider failed after retries` saat instruksi baru diberikan.
* **Penyebab**: 9router merutekan permintaan ke model `deepseek-v4-flash` / `deepseek-v4-pro-max` yang sedang menolak parameter `response_format: {"type": "json_object"}`.
* **Mitigasi**: Pastikan parameter auxiliary approval pada konfigurasi agen menggunakan provider cadangan atau nonaktifkan enforce JSON schema jika model upstream mengalami fluktuasi stabilitas.

---

## 5. STANDARD OPERATING PROCEDURE (SOP) & RUNBOOK OPERASIONAL

### 5.1 Akses & Pemeriksaan Health-Check Gateway
Jalankan verifikasi dari terminal lokal melalui SSH tunnel terotorisasi:

```bash
# 1. Masuk ke VM Host
ssh -i /Users/avocado/.ssh/google_compute_engine avocado@34.87.88.43

# 2. Cek status seluruh container Hermes stack
cd /home/avocado/hermes-deploy
docker-compose ps

# 3. Verifikasi status koneksi Telegram pada bot hermes-pm
docker exec hermes-pm sh -c "grep -i 'telegram connected' /opt/data/logs/gateway.log | tail -5"

# 4. Cek error log terkini
docker exec hermes-pm sh -c "tail -25 /opt/data/logs/errors.log"

# 5. Uji kesehatan 9router upstream
docker logs --tail 20 9router
```

### 5.2 SOP Restart Gateway Tanpa Merusak Container
Jika bot mengalami network hang pada Telegram polling, restart hanya proses gateway-nya melalui s6 supervisor (tanpa recreate container):

```bash
# Restart proses gateway hermes-pm secara graceful
docker exec -u root hermes-pm /command/s6-svc -r /run/service/gateway-default

# Pantau inisialisasi ulang
docker exec hermes-pm sh -c "tail -f /opt/data/logs/gateway.log"
# Tunggu hingga muncul log: '✓ telegram connected'
```

### 5.3 SOP Validasi Tooling Cloud & Kubernetes di Dalam Container
Pastikan container selalu dapat beroperasi dengan infrastruktur GCP:

```bash
# Cek ketersediaan SDK
docker exec -u hermes hermes-pm sh -c "export HOME=/opt/data; gcloud --version; kubectl version --client"

# Cek akun aktif gcloud
docker exec -u hermes hermes-pm sh -c "export HOME=/opt/data; gcloud auth list"
# Akun aktif wajib: hermes-monitor-sa@tokobuah-staging-499001.iam.gserviceaccount.com
```

### 5.4 SOP Recreate Container yang Aman
Jika perlu mengubah `docker-compose.yml`:

```bash
cd /home/avocado/hermes-deploy

# Backup file konfigurasi
cp docker-compose.yml docker-compose.yml.bak_$(date +%Y%m%d_%H%M%S)

# Terapkan perubahan
docker-compose up -d --no-deps hermes-pm

# Pastikan symlink SDK di /usr/local/bin tetap terpasang
docker exec -u root hermes-pm sh -c "
G=/opt/data/gcloud-sdk/google-cloud-sdk/bin
for b in gcloud kubectl gke-gcloud-auth-plugin bq gsutil; do
    ln -sf \$G/\$b /usr/local/bin/\$b
done
"
```

---

## 6. GUARDRAILS & BATASAN KEAMANAN KHUSUS

Berdasarkan aturan global tata kelola AI agent (`RULE[user_global]`), agen yang beroperasi di mesin ini wajib tunduk pada batasan mutlak berikut:

1. **Strict Production Freeze (§1)**:
   * Dilarang menjalankan mutasi, redeployment, scaling, atau restart pod di level production tanpa izin eksplisit per aksi.
   * Dilarang menyentuh database production dengan query mutasi data tanpa klausul validasi.
2. **Zero Deletion Without Permission (§2)**:
   * Perintah seperti `docker rm -f`, `rm -rf`, `kubectl delete`, `DROP TABLE`, atau `TRUNCATE` dilarang keras dijalankan tanpa konfirmasi tertulis.
   * Tidak boleh menggunakan bypass flag (`-f`, `-y`, `--quiet`, `--force`) pada perintah yang berdampak destruktif.
3. **Database OLTP Protection Protocol**:
   * Dilarang menjalankan query reporting / agregasi periodik (`COUNT(*)`, `SUM()`, `GROUP BY`) langsung ke tabel transaksional production berkuran besar (`game_transactions`, `wallets`, `game_transaction_callbacks`) tanpa menyertakan filter index utama (`id` range / primary key seek).
   * Gunakan selalu streaming Kafka (`game-transaction-*`), replica analytics, atau BigQuery untuk kebutuhan pelaporan.
4. **Strict Secret Masking (§5)**:
   * Kredensial, database password, API token bot Telegram (`PM_TELEGRAM_TOKEN`), service account private key, dan JWT secret tidak boleh dicetak plaintext di chat, commit message, maupun file dokumentasi publik.
   * Selalu gunakan format masking: `postgresql://user:********@host:port/dbname` atau `token: <redacted>`.
5. **Channel & Scope Boundary**:
   * Bot operasional internal (`tokobuah-pm`) tidak boleh dibiarkan bergabung ke ruang publik atau forum bebas tanpa mekanisme gating otorisasi ID pengguna yang ketat.
   * Jika tidak ada kebutuhan kolaboratif multi-user yang mendesak, operasikan bot secara privat melalui direct message (DM) operator.

---
> **Dokumentasi ini disusun secara otomatis oleh AI Assistant Antigravity**  
> **Terakhir diverifikasi**: 2026-11-15 02:52 WIB  
> **Lokasi File**: `/Users/avocado/tokobuah/infra-stuff/HERMES_DEVOPS_AUTOMATION_RUNBOOK.md`
