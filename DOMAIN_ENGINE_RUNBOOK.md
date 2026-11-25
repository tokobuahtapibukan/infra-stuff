# 🌐 TOKOBUAH PLATFORM — DOMAIN ENGINE (DOMAIN MANAGEMENT) RUNBOOK
> **File Name**: `DOMAIN_ENGINE_RUNBOOK.md`  
> **Document Version**: 1.0.0  
> **Created Date**: 2026-11-21  
> **Workspace Path**: `/Users/avocado/tokobuah/infra-stuff/`  
> **Primary Maintainers**: DevOps, SRE, and AI Autonomous Agents  
> **Precedence & Governance**: Strictly governed by Global Safety Rules in `~/AGENTS.md` and `MASTER_INFRA_KNOWLEDGE_BASE.md`. Stricter rule wins.  
> **Claim cards**: `claims/meta/domain-engine-owner-runbook.yaml`, `claims/security/domain-engine-no-entrypoint-put.yaml`; juga tercakup `claims/inventory/core-cluster-services-alive.yaml`, `claims/fix-tracking/core-repos-no-secret-tracked.yaml`, `claims/fix-tracking/node20-eol-dockerfiles.yaml`, `claims/fix-tracking/no-latest-in-cdk.yaml`

---

## 📑 TABLE OF CONTENTS
1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Topologi & Komponen](#2-topologi--komponen)
   - [2.1 Service & environment](#21-service--environment)
   - [2.2 Jenis domain](#22-jenis-domain)
   - [2.3 Model redirect](#23-model-redirect)
   - [2.4 Origin usersite (target CNAME subdomain)](#24-origin-usersite-target-cname-subdomain)
3. [Kronologi Perubahan](#3-kronologi-perubahan)
4. [Caveat, Insiden & Pelajaran](#4-caveat-insiden--pelajaran)
5. [Prosedur Operasional](#5-prosedur-operasional)
6. [Open Items](#6-open-items)
7. [Dokumen Terkait & Handoff](#7-dokumen-terkait--handoff)

---

## 1. Ringkasan Eksekutif

**Domain Engine** (repo `domain-management`, NestJS + TypeORM + BullMQ) adalah sumber kebenaran domain tenant dan
satu-satunya komponen yang menulis ke Cloudflare akun tenant (kredensial per company di tabel `company_configs`).
Ia membuat zone, record DNS, setelan SSL, rule redirect, dan mendaftarkan host AMP ke AMP engine.

Per 2026-11-21:
* **Staging** menjalankan `main` @ `c5898f7`: AMP SUBDOMAIN (PR #1) + subdomain usersite & redirect fleksibel (PR #2).
  Diuji ujung-ke-ujung pada tenant `ikndev`, dan data tenant dikembalikan identik.
* **Production** masih `0.0.10` (= `a0f0b3e`). Rilis fitur di atas belum dilakukan (§5.2, §6).

Prinsip yang dijaga kode:
* **Zone money site tidak pernah dihapus karena operasi subdomain.** Subdomain (AMP maupun usersite) hanya memiliki
  record dan rule miliknya sendiri di zone parent.
* **Rule Cloudflare diubah per rule, tidak pernah dengan `PUT` entrypoint**, supaya rule milik tenant tidak tertimpa
  (kartu `domain-engine-no-entrypoint-put`).
* **Redirect hanya antar host aktif milik company yang sama.**

---

## 2. Topologi & Komponen

### 2.1 Service & environment

| | Staging | Production |
|---|---|---|
| Cluster / ns | `staging-gke-standard` / `core` (1 replica) | `prod-core-cluster` / `core` (2 replica) |
| Image | `…/tokobuah-staging-499001/tokobuah/domain-management:latest` (`imagePullPolicy: Always`) | `…/tokobuah-production/tokobuah/domain-management:0.0.10` (tag tetap) |
| Manifest | `company-deployment-key/staging/core/domain-management/` | `company-deployment-key/production/core/domain-management/` |
| ESP (Cloud Endpoints) | service `domain-management.stagingtokobuah.xyz`, config `2026-11-20r0`, spec `openapi.yaml` | service `domain.tokobuahapi.store`, config `2026-08-09r0`, spec `openapi-prod.yaml` |
| Akses | internal LB `10.10.16.39:80` → sidecar ESP `:8082` → app `:8080` | internal (VPN untuk control plane) |
| Pemanggil | admin panel staging `BE_DOMAINS=http://10.10.16.39` | admin panel production |
| AMP engine | `http://amp-build-service.amp.svc.cluster.local:8080/internal`, `AMP_INGRESS_IP=136.82.0.162` | sama, `AMP_INGRESS_IP=35.227.207.207` |
| API docs (Scalar) | `GET /docs` (tanpa token, `security: []` di ESP), dari VPC atau `kubectl port-forward` | sama |

* Migration TypeORM dijalankan **saat boot** di bawah `pg_advisory_lock`, jadi aman walau beberapa replica start
  bersamaan.
* ESP menolak (404) route yang tidak ada di spec. Route baru = deploy Cloud Endpoints dulu, baru image.
* Staging tidak punya trigger Cloud Build. Image dibangun manual (§5.1).

### 2.2 Jenis domain

| `type` / `ampMode` | Contoh | Zone | Record | Hapus |
|---|---|---|---|---|
| `STANDARD` (money site) | `x.com` | zone sendiri | `A @` → IP company, `CNAME www` | zone dihapus; **anak AMP + subdomain ikut terhapus** (row lock; `409` kalau anak masih diproses; `502` kalau AMP engine gagal) |
| `AMP` / `STANDALONE` | `merekamp.com` | zone sendiri | `A @` → `AMP_INGRESS_IP` | zone dihapus, AMP dideregister |
| `AMP` / `SUBDOMAIN` | `amp.x.com` | zone parent (`parentZoneId`) | `A amp` → `AMP_INGRESS_IP` (proxied) + Configuration Rule `ssl: flexible` per host | record + rule saja |
| `SUBDOMAIN` (usersite) | `abc.x.com`, `www.x.com` | zone parent | `CNAME abc → x.com` (proxied seperti apex; ikut berubah otomatis kalau IP company diganti) | rule redirect miliknya + record saja; `www` hanya pengaturannya |

* Subdomain: satu tingkat di bawah **registrable domain menurut PSL ICANN** (`tldts` 7.4.19, sama dengan AMP engine).
  Universal SSL hanya menanggung `*.x.com`.
* Tetap **1 AMP per company** (STANDALONE atau SUBDOMAIN). Dicek di aplikasi (cek-lalu-insert); unique index belum ada.
* Host yang sedang menjadi **target redirect tidak bisa dihapus** (`409 domain_is_redirect_target` + `redirectSources`).
* Kolom tambahan `domains`: `ampMode`, `parentDomainId` (FK `ON DELETE RESTRICT`), `parentDomain`, `parentZoneId`,
  `dnsRecordId`, `sslRuleId`, `followParentRedirect` (default `true`).

### 2.3 Model redirect

* **Sumber money site** → satu rule untuk seluruh zone: `not (http.host in {…})`. Yang dikecualikan otomatis: host
  AMP, subdomain standalone (`followParentRedirect=false`), dan subdomain yang punya redirect sendiri. Daftar ini
  dihitung ulang dari DB setiap kali salah satu unsurnya berubah (`RedirectRuleSyncService.syncForParent`).
* **Sumber subdomain usersite** → rule per host `(http.host eq "abc.x.com")` di zone parent.
* **Target**: host aktif milik company yang sama (`GET /redirect-targets`), termasuk host AMP. Teks bebas ditolak `400`.
  Host AMP tidak bisa jadi sumber.
* **Loop** dicek pada graf *efektif*: subdomain yang ikut induk dihitung ikut ter-redirect. Rantai boleh, siklus
  ditolak `400` (`Redirect loop: y.com -> abc.x.com -> y.com`).
* Semua rule punya `ref` deterministik (hash host), sehingga retry memakai ulang rule yang sama. Fase dynamic redirect
  diubah per rule (`POST/PATCH/DELETE …/rules/{id}`).
* **ID rule yang tidak sinkron** (§4.1): kalau ID yang tersimpan tidak ada di ruleset, rule yang diadopsi adalah
  *satu-satunya* rule dengan target dan cakupan yang sama (zone-wide vs per-host). Nol atau lebih dari satu kandidat →
  gagal dengan pesan jelas, tidak menebak.
* Error batas jumlah rule per zone dari Cloudflare → `409` dengan pesan jelas.

### 2.4 Origin usersite (target CNAME subdomain)

Diverifikasi live 2026-11-20 (staging, tenant `ikndev`):
* `35.219.44.141` = static IP `fe-usersite-static-ip` → LB regional `fe-usersite-lb` (asia-southeast2). URL map
  **tanpa host rule**: semua Host diteruskan ke `fe-usersite-backend` (NEG serverless → Cloud Run `fe-usersite`).
* Tenant ditentukan oleh env `COMPANY_CODE` (satu deployment = satu company), **bukan** dari Host. Kode usersite tidak
  punya allowlist host.
* Bukti nyata: `www.dfsdfssss.site` (CNAME ke apex) → 200, halaman identik dengan apex. Jadi subdomain usersite langsung
  tersaji tanpa perubahan origin.
* Canonical semua host = `NEXT_PUBLIC_SITE_URL` (tetap), sehingga subdomain tidak diindeks sebagai halaman terpisah.
* Tenant production lain belum diverifikasi; cek ulang saat rilis.

---

## 3. Kronologi Perubahan

| Tanggal | Perubahan |
|---|---|
| 2026-11-06 | Redirect pindah ke dynamic ruleset (`a0f0b3e`, masih `PUT` entrypoint). Rilis production `0.0.10` |
| 2026-11-16 | Fix DNS idempotent `ensureDNSRecord` (`e1f88c8`), staging |
| 2026-11-20 | PR #1: AMP SUBDOMAIN (`e1bd870`), redirect per rule + adopsi ID rule yang tidak sinkron (`1d74ab7`). Staging; AMP engine D50 (`eec8508`) live di staging |
| 2026-11-20 | PR #2: subdomain usersite, standalone, redirect fleksibel, cek loop, 409 target redirect, `www` (`015a5e8`, `5699dd7`), dokumentasi skema API (`ec9c096`). ESP staging `2026-11-20r0`; staging = `main` @ `c5898f7` |
| 2026-11-20 | Uji ujung-ke-ujung staging; snapshot DB + Cloudflare sesudah uji identik dengan sebelumnya |

---

## 4. Caveat, Insiden & Pelajaran

### 4.1 ID rule redirect tidak sinkron dengan Cloudflare
* Staging `kwlaisncaliscn.store`: DB menyimpan rule `c698…`, padahal rule yang aktif `712d…` (target dan format sama,
  dibuat 2026-11-06). Bukan Page Rule dan bukan ID ruleset.
* Akibat kalau tidak ditangani: menambah pengecualian AMP gagal, dan hapus redirect meninggalkan rule aktif.
* Sekarang ditangani adopsi otomatis (§2.3). Production per 2026-11-21: 1 redirect, ID-nya sinkron.

### 4.2 `PUT` entrypoint menimpa rule tenant
* Kode lama `createRedirectRule`/`deleteRedirectRule` melakukan `PUT` ke seluruh entrypoint
  `http_request_dynamic_redirect`, sehingga **semua rule redirect lain di zone hilang**.
* Sudah diganti operasi per rule. Kartu `domain-engine-no-entrypoint-put` menjaga agar tidak kembali.
* Production `0.0.10` **masih memakai kode lama** sampai rilis berikutnya.

### 4.3 Record DNS yang dihapus masih resolve 6–7 menit
* Setelah `DELETE /dns_records/:id`, API langsung menunjukkan record sudah hilang, tetapi NS otoritatif Cloudflare
  masih menjawab sekitar 6–7 menit. Nama yang tidak pernah dibuat langsung `NXDOMAIN`, jadi ini jeda propagasi, bukan
  wildcard.
* Selama jeda itu, rule zone-wide (mis. redirect money site) masih berlaku untuk host tersebut.
* Saat memverifikasi pembersihan: percayai API/rule sebagai sumber kebenaran, lalu cek DNS lagi setelah beberapa menit.

### 4.4 Retag gagal tersembunyi, restart memakai image lama
* `gcloud artifacts docker tags add $R:src $R:latest` di **zsh**: `$R:latest`/`$R:amp…` dibaca sebagai modifier zsh
  (`:l`, `:a`). Error-nya tersembunyi oleh `| tail`, rollout restart "sukses", tetapi menarik image lama.
* Pelajaran: tulis `"${R}:tag"`, jangan sembunyikan exit code perintah mutasi, dan **selalu verifikasi digest
  `imageID` pod** setelah rollout.
* Jangan pakai nama variabel `path` di zsh (terhubung ke `$PATH`, sehingga semua perintah jadi "command not found").

### 4.5 Fitur "+ Subdomain" di admin panel hanya tampilan
* `domains-client.tsx` menyimpan subdomain di state React (`subdomainsMap`), tanpa API, dengan notifikasi sukses
  palsu. Contoh: `ikntestingit.kwlaisncaliscn.store` tidak pernah ada di Cloudflare maupun DB.
* Penggantinya ada di handoff `docs/handoffs/2026-11-subdomain-redirect/admin-panel.md`.

### 4.6 Celah lintas tenant di `addRedirect` (sudah ditutup di `main`)
* Sebelumnya `sourceDomain` tidak dicek kepemilikannya dan `targetDomain` bebas diisi. Sekarang keduanya wajib host
  aktif milik `companyCode` yang sama.
* Production `0.0.10` masih memakai perilaku lama.

### 4.7 Staging memakai `:latest`
* Termasuk temuan `no-latest-in-cdk`. Rollback staging = pindahkan tag `latest` ke tag sebelumnya.
* Production tetap memakai tag tetap; jangan pernah pakai `latest` atau edit langsung di cluster.

### 4.8 Key internal plaintext di repo admin-panel
* `cloudbuild.yaml` dan `cloudbuild-dev.yaml` di repo `admin-panel` memuat `AUDIT_INGEST_KEY` sebagai teks biasa
  (nilai tidak dicatat di sini). Sebaiknya dipindah ke Secret Manager lalu dirotasi.

---

## 5. Prosedur Operasional

> Semua langkah mutasi tunduk pada `~/AGENTS.md`: staging §3 (minta izin dengan diff/spec), production §1 (rencana,
> perintah, blast radius, rollback, lalu tunggu izin eksplisit). Shell di Mac = zsh (§4.4).

### 5.1 Rilis staging
```bash
R=asia-southeast2-docker.pkg.dev/tokobuah-staging-499001/tokobuah/domain-management
# 0. (hanya jika openapi.yaml berubah) deploy ESP dulu
gcloud endpoints services deploy openapi.yaml --project tokobuah-staging-499001
# 1. build dari tree bersih (worktree / checkout tanpa file untracked)
gcloud builds submit . --project tokobuah-staging-499001 --tag "${R}:<label>-<sha>"
# 2. pindahkan latest, lalu VERIFIKASI tag
gcloud artifacts docker tags add "${R}:<label>-<sha>" "${R}:latest"
gcloud artifacts docker images list $R --include-tags --sort-by=~UPDATE_TIME --limit 2
# 3. rollout + verifikasi digest pod dan log migration
kubectl -n core rollout restart deployment/domain-management
kubectl -n core rollout status deployment/domain-management --timeout=5m
kubectl -n core get pods -l app=domain-management \
  -o 'custom-columns=NAME:.metadata.name,DIGEST:.status.containerStatuses[?(@.name=="domain-management")].imageID'
```
Rollback: `tags add "${R}:<tag-sebelumnya>" "${R}:latest"`, lalu rollout restart. Migration aditif tidak perlu dibalik.

### 5.2 Rilis production (zero drift)
Urutan: **AMP engine → Domain Engine → admin panel** (kontrak di handoff).
1. Persiapan: CI hijau di repo terkait; backup on-demand DB production sebelum migration.
2. AMP engine: tag `vX.Y.Z` → build (`cloudbuild.prod.yaml`) → ubah image di manifest
   `production/core/amp/07-deployment-serve.yaml` + `08-deployment-build.yaml` → commit → `kubectl apply`. Verifikasi
   halaman AMP production yang ada tetap tampil. Lihat juga `AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md` §5.1.
3. Domain Engine:
   * deploy ESP production lebih dulu kalau ada route baru: `gcloud endpoints services deploy openapi-prod.yaml --project tokobuah-production`;
   * tag `0.0.N` → build (`cloudbuild.yaml`, push ke registry production);
   * ubah image di `production/core/domain-management/deployment.yaml` → commit → `kubectl apply`;
   * verifikasi: 2 pod ready dengan digest baru, log `Applied N migration(s)`, endpoint baru 200 lewat ESP (read-only).
4. Rollback: kembalikan image di manifest ke tag sebelumnya, lalu apply. Kolom migration aditif dibiarkan. ESP: deploy
   ulang spec sebelumnya.
5. Setelah rilis: perbarui §2.1, §3 dan kartu terkait.

Status data production 2026-11-21 (read-only) untuk rilis PR #1 + #2:
* 2 migration baru, keduanya aditif.
* 94 domain (92 STANDARD, 2 AMP STANDALONE), 0 company dengan lebih dari satu AMP.
* 1 redirect, sudah memenuhi aturan baru dan ID-nya sinkron.

### 5.3 Pemeriksaan read-only dari dalam pod
Kredensial DB dan Cloudflare dibaca dari env pod dan `company_configs`, tidak pernah dicetak. Pola:
```bash
kubectl -n core exec -i deploy/domain-management -c domain-management -- node - < snapshot.js
```
`snapshot.js` (node + `pg` + `axios` yang sudah ada di image) mencetak JSON: row `domains`/`redirects` satu company,
record DNS, rule `http_request_dynamic_redirect`, dan `http_config_settings` per zone money site. Dipakai untuk:
* cek ID rule redirect sinkron (§4.1);
* cek migration yang sudah jalan (`SELECT name FROM migrations`);
* snapshot sebelum/sesudah uji (§5.4).

### 5.4 Uji ujung-ke-ujung staging & mengembalikan data tenant
1. Snapshot (§5.3) → `before.json`.
2. Panggil API lewat ESP: `kubectl -n core port-forward svc/domain-management 18082:80`. JWT admin staging diminta
   lewat `se secret request` (jangan ditempel di chat) dan hanya dibaca di perintah yang memakainya.
3. Uji, lalu bersihkan lewat API yang sama (lepas redirect dulu, baru hapus host).
4. Snapshot → `after.json` → `diff`. Harus identik, termasuk ID rule. Cek DNS lagi setelah ±7 menit (§4.3).

---

## 6. Open Items
* [x] **Invariant WAF block `/metrics` (P0-1)** — 2026-11-26: rule `tbk_block_metrics` (block `/beapi/metrics` + `/authapi/metrics`)
      dipasang manual ke **91 zone STANDARD aktif**. **OTW: jadikan invariant provisioning** agar zona STANDARD baru auto-kena
      (`ensureMetricsBlockRule` di provisioning + rekonsiliasi berkala). Lihat `docs/handoffs/2026-11-block-metrics-on-new-domains/`.
      Kartu regression: `claims/security/demobuah-beapi-metrics-public.yaml`, `demobuah-authapi-metrics-public.yaml`.
* [ ] Rilis production PR #1 + #2 (§5.2), setelah AMP engine production menerima subdomain (D50).
* [ ] Admin panel: UI AMP SUBDOMAIN, subdomain usersite, dropdown target redirect, dialog hapus dengan
      `redirect-sources` (handoff §7).
* [ ] Partial unique index `UNIQUE("companyCode") WHERE type='AMP'` (PR terpisah; production 0 duplikat per 2026-11-21).
* [ ] Rotasi `AMP_INTERNAL_KEY` setelah panel tidak memegangnya lagi (`AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md` §4.5).
* [ ] Pindahkan `AUDIT_INGEST_KEY` admin-panel dari `cloudbuild*.yaml` ke Secret Manager, lalu rotasi (§4.8).
* [ ] Verifikasi origin usersite production menerima Host subdomain (§2.4) saat rilis.
* [ ] Base image `node:20` (EOL) di Dockerfile Domain Engine (kartu `node20-eol-dockerfiles`).

---

## 7. Dokumen Terkait & Handoff
* Repo `domain-management`: PR #1 (AMP SUBDOMAIN) dan PR #2 (subdomain usersite & redirect); Scalar `GET /docs`.
* Handoff:
  * `docs/handoffs/2026-11-amp-subdomain/` (AMP SUBDOMAIN, kontrak tiga tim)
  * `docs/handoffs/2026-11-subdomain-redirect/` (subdomain usersite & redirect fleksibel)
  * Ringkasan untuk dev panel: artifact "Handoff Subdomain & Redirect" (https://claude.ai/artifact/J4LcwhF1uG3Bm925RZLRDy, privat)
* `AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md` (AMP engine, D50, `/internal/domains`).
* `MASTER_INFRA_KNOWLEDGE_BASE.md` §9 (repositori).
