# ⚡ TOKOBUAH PLATFORM — AMP PAGE SERVICE, TENANT REGISTRY & AMP DOMAINS RUNBOOK
> **File Name**: `AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md`  
> **Document Version**: 1.0.0  
> **Created Date**: 2026-11-21  
> **Workspace Path**: `/Users/avocado/tokobuah/infra-stuff/`  
> **Primary Maintainers**: DevOps, SRE, and AI Autonomous Agents  
> **Precedence & Governance**: Strictly governed by Global Safety Rules in `~/AGENTS.md` and `MASTER_INFRA_KNOWLEDGE_BASE.md`. Stricter rule wins.  
> **Claim cards**: `claims/**/amp-*.yaml`, `claims/**/tenant-registry-*.yaml`, `claims/inventory/tenant-internal-lb-*.yaml`, `claims/security/cloudarmor-staging-eight.yaml`

---

## 📑 TABLE OF CONTENTS
1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Topologi & Komponen](#2-topologi--komponen)
   - [2.1 AMP Page Service (repo `AMP`)](#21-amp-page-service-repo-amp)
   - [2.2 Edge: Cloudflare, Cloud Armor, Ingress](#22-edge-cloudflare-cloud-armor-ingress)
   - [2.3 tenant-registry (repo `tenant-registry-go`)](#23-tenant-registry-repo-tenant-registry-go)
   - [2.4 Backend internal tenant: `new-backend-internal`](#24-backend-internal-tenant-new-backend-internal)
   - [2.5 Domain AMP: STANDALONE vs SUBDOMAIN (D50)](#25-domain-amp-standalone-vs-subdomain-d50)
3. [Kronologi Perubahan](#3-kronologi-perubahan)
4. [Caveat, Insiden & Pelajaran](#4-caveat-insiden--pelajaran)
5. [Prosedur Operasional](#5-prosedur-operasional)
6. [Open Items](#6-open-items)
7. [Dokumen Terkait & Handoff](#7-dokumen-terkait--handoff)

---

## 1. Ringkasan Eksekutif

**AMP Page Service** membangun dan menyajikan satu halaman AMP statis per company (tenant). Admin panel company
mengirim 4 setting (`enabled`, `ampDomain`, `redirectTo`, `canonical`) dengan JWT admin; AMP mengambil konten dari API
internal (CMS, gamelist, backend promo milik tenant), memvalidasi (AMP validator + SEO gate), menyimpan HTML di GCS, dan
menyajikannya berdasarkan header `Host` (custom domain agen, mis. `merek.com`).

**tenant-registry** adalah service internal read-only yang menjawab *"backend internal company X ada di IP berapa?"*,
dibaca langsung dari Service Kubernetes berlabel. AMP memakainya supaya promo tiap company diambil dari backend
company itu sendiri (sebelumnya semua company memakai satu backend tetap milik `buah5758`).

Status per 2026-11-21:

| Komponen | Staging | Production |
|---|---|---|
| AMP | image dari `main` (auto), terakhir `eec8508` (D50) | `v0.0.4` |
| tenant-registry | in-cluster, 1 replica | `v0.1.0`, 1 replica, membaca `prod-client-cluster` |
| Tenant berlabel + IP di-pin | 1 (`ikndev`) | 13 (termasuk `padi808`, otomatis via summon-tenant) |
| Domain AMP SUBDOMAIN (D50) | AMP siap; Domain Engine & admin panel sedang dikerjakan | belum |

---

## 2. Topologi & Komponen

### 2.1 AMP Page Service (repo `AMP`)
* **Repo**: `~/tokobuah/AMP` → `tokobuahorganization/AMP`. TypeScript strict di Node 24, satu image dua mode:
  `amp-build` (`MODE=build`: admin API, build, `/internal/*`) dan `amp-serve` (`MODE=serve`: halaman by `Host`).
  Desain & keputusan: `plan.md` (Decision log D1–D50), `docs/deploy.md`, `docs/domains.md`, `docs/tenant-registry.md`.
* **Cluster / namespace**: staging `staging-gke-standard` ns `amp`; production `prod-core-cluster` (Autopilot) ns `amp`.
* **Storage**: GCS `tokobuah-staging-amp-data` / `tokobuah-production-amp-data` (`hosts/<host>` = pemilik host,
  `tenants/<code>/{config.json,page.html,build.json,domain.json}`, `locks/domain-family/<root>`).
* **Identitas GCP**: Workload Identity `amp/amp-ksa` → `amp-sa@<project>` (`roles/storage.objectAdmin` di bucket).
  Staging: key JSON lama sudah dihapus (2026-11-15), node pool `GKE_METADATA`, `nodeSelector` WI di deployment.
* **Manifest**: `company-deployment-key/{staging,production}/core/amp/` (00–09). Image tag dikelola CI di staging
  (`kubectl set image <sha>`), di production lewat edit `07`/`08` + apply.
* **Rilis**:
  * Staging: push `main` → trigger `be-amp-page-main` (Cloud Build `tokobuah-staging-499001`) → `kubectl set image`.
  * Production: tag `vX.Y.Z` → **build manual** (tidak ada trigger di project production):
    `gcloud builds submit --project tokobuah-production --region asia-southeast1 --config cloudbuild.prod.yaml --substitutions TAG_NAME=vX.Y.Z`
    → image `asia-southeast1-docker.pkg.dev/tokobuah-production/tokobuah/amp-page:vX.Y.Z` → prosedur §5.1.
  * Artifact Registry staging ada di **asia-southeast2**, production di **asia-southeast1**.

### 2.2 Edge: Cloudflare, Cloud Armor, Ingress
| | Staging | Production |
|---|---|---|
| Ingress (GCE, HTTP :80 saja) | `136.82.0.162` (`amp-staging-ingress-ip`) | `35.227.207.207` |
| Host admin API | `amp-api.stagingtokobuah.xyz` | `amp-api.nkigaming.site` |
| Cloud Armor origin lock | `cf-origin-lock-staging` di 2 backend AMP ✅ | **TIDAK ADA** ⚠️ (lihat §4.8, kartu `amp-prod-origin-open`) |
| SSL Cloudflare `amp-api` | Configuration Rule `ssl: flexible` khusus host (zone `full` sejak 2026-11-14) | — |

* Origin hanya HTTP :80. Host apa pun yang lewat Cloudflare ke AMP harus **SSL Flexible** (zone atau Configuration
  Rule per host); Full/Strict → **525**.
* Domain agen (Domain Engine) wajib **proxied**: dengan origin lock, record DNS-only = pengunjung kena 403.
* Domain Engine & tenant-registry memanggil AMP lewat Service internal cluster, bukan lewat Ingress.

### 2.3 tenant-registry (repo `tenant-registry-go`)
* **Repo**: `~/tokobuah/tenant-registry-go` → `tokobuahorganization/tenant-registry-go` (Go, distroless, read-only).
  Desain & model keamanan: `docs/design.md`; operasional: `docs/operations.md`; integrasi AMP: `docs/amp-integration.md`.
* **Cara kerja**: tiap 30 detik `list services` (label `tokobuah.io/company-code`, nama `new-backend-internal`), validasi
  (internal LB, port 80/TCP, IP privat di CIDR, cocok `loadBalancerIP`, namespace tidak di deny-list), kode ganda
  **ditahan** (fail closed). API: `GET /v1/tenants/{code}` → `{ company_code, backend_url, observed_at, stale }`.
* **Keamanan**: ClusterIP saja; NetworkPolicy hanya dari `amp-build` (ditegakkan di production / Dataplane V2, **tidak**
  di staging / legacy datapath); auth Google ID token Workload Identity + allow-list email + scope + rate limit; tanpa
  endpoint tulis; RBAC hanya `list services`.
* **Deploy**:
  | | Staging | Production |
  |---|---|---|
  | Lokasi | `staging-gke-standard` ns `tenant-registry`, `source: in-cluster` | `prod-core-cluster` ns `tenant-registry`, `source: gke` → `prod-client-cluster` (private endpoint) |
  | Identitas | KSA in-cluster (ClusterRole `tenant-registry-reader`) | GSA `tenant-registry-sa@tokobuah-production` (WI) + `roles/container.clusterViewer` + RBAC `list services` di prod-client |
  | Caller | `amp-sa@tokobuah-staging-499001` (`tenants:get`) | `amp-sa@tokobuah-production` (`tenants:get`) |
  | CIDR backend | `10.10.16.0/20` | `10.20.16.0/20` |
  | Manifest | `company-deployment-key/staging/core/tenant-registry/` | `company-deployment-key/production/core/tenant-registry/` (+ `client-cluster/rbac.yaml`, `setup.sh`, `deploy.sh`) |
* **Rilis production**: tag di repo → `gcloud builds submit --project tokobuah-production --config cloudbuild.prod.yaml --substitutions TAG_NAME=vX.Y.Z` → edit tag di `03-deployment.yaml` → apply dengan `--context` eksplisit.
* Pod `prod-core-cluster` bisa menjangkau control plane private `prod-client-cluster` (pod range `10.240.0.0/17`
  dipakai bersama ketiga cluster production); master authorized networks **tidak perlu** diubah.

### 2.4 Backend internal tenant: `new-backend-internal`
* Setiap tenant punya `new-backend` di namespace = company code (kecuali `buah5758` → namespace `client`) di
  `prod-client-cluster`, dengan Service `new-backend-internal` (internal LB, global access) di `client-gke-subnet`.
  Dipakai PGA (`trx_upstream`) dan AMP (promo, lewat tenant-registry).
* **Wajib** (sejak 2026-11-17): label `tokobuah.io/company-code: "<kode persis>"` dan `spec.loadBalancerIP` = alamat
  statis `prod-<code>-backend-internal` (region `asia-southeast1`, subnet `client-gke-subnet`). **Alamat internal statis
  tidak berbayar.** Kode dengan `_` / huruf besar dinormalisasi untuk nama alamat (`IKN_01` → `prod-ikn-01-backend-internal`).
* **Otomatis untuk tenant baru**: `summon-tenant` step 3 (`templates/client/service-internal.yaml` + `pin_internal_ip()`
  di `modules/step3_gke.py`) → label + reserve + pin + verifikasi. Terbukti di onboarding `padi808` (2026-11-20):
  berlabel, IP `10.20.16.138` di-pin & di-reserve, langsung terbaca registry.
* Production (13 tenant):

  | Code | Namespace | IP | Code | Namespace | IP |
  |---|---|---|---|---|---|
  | buah5758 | client | 10.20.16.106 | omsipit | omsipit | 10.20.16.54 |
  | cinabotak | cinabotak | 10.20.16.56 | padi808 | padi808 | 10.20.16.138 |
  | cinasuper | cinasuper | 10.20.16.43 | pengenwd | pengenwd | 10.20.16.40 |
  | dutaledak | dutaledak | 10.20.16.128 | rumushoki | rumushoki | 10.20.16.11 |
  | hambabet | hambabet | 10.20.16.68 | tapakhoki | tapakhoki | 10.20.16.146 |
  | ikn788 | ikn788 | 10.20.16.78 | terbangwd | terbangwd | 10.20.16.108 |
  |  |  |  | terios88 | terios88 | 10.20.16.36 |

  Staging: `ikndev` (namespace `client`) → `10.10.16.26` (`staging-ikndev-backend-internal`).

### 2.5 Domain AMP: STANDALONE vs SUBDOMAIN (D50)
| Mode | Contoh | Status |
|---|---|---|
| `STANDALONE` | `merekamp.com`, root domain + zone Cloudflare sendiri | Production |
| `SUBDOMAIN` | `amp.merek.com`, satu tingkat di bawah money site (domain `STANDARD`) agen, memakai zone money site | AMP: staging (`eec8508`); Domain Engine: staging (`c5898f7`); admin panel: dikerjakan |

Aturan inti (kontrak lengkap: `docs/handoffs/2026-11-amp-subdomain/00-kontrak-bersama.md`):
* Satu tingkat saja; label `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`, bukan `www`, default `amp`.
* Parent = registrable domain menurut **public suffix list ICANN** (AMP: `tldts` 7.4.19). `merek.com.vn` = root,
  `co.id`/`com.vn` bukan domain. Jangan pakai daftar TLD manual.
* Parent wajib domain `STANDARD` aktif milik company yang sama; tetap 1 AMP per company.
* Default `redirectTo` = money site; default `canonical` = **host AMP sendiri** (supaya terindeks). AMP tidak mengisi
  canonical sendiri, Domain Engine yang mengirim default.
* DNS `A <label>` → IP ingress AMP, **proxied**; Configuration Rule `ssl: flexible` per host.
* **Menghapus AMP SUBDOMAIN tidak boleh menghapus zone money site.** Menghapus money site **ikut menghapus** AMP
  SUBDOMAIN-nya (deregister AMP dulu; `409` kalau AMP masih diproses, `502` kalau AMP engine gagal). Revisi kontrak no. 10
  (2026-11-20); sebelumnya money site ditolak dihapus.
* Redirect money site **tidak mengenai** host AMP SUBDOMAIN (rule redirect mengecualikan host itu; kontrak no. 11).
* Alur satu jalur: admin panel → Domain Engine → AMP `/internal/domains/{code}` (panel berhenti memanggil AMP langsung).
* AMP `/internal/domains`: `409 hostname_taken` (host persis milik company lain), `409 parent_domain_taken` (host lain di
  keluarga domain sedang **aktif** dipakai company lain), `422 domain_reserved` (keluarga `AMP_DOMAIN`), `503 busy`
  (pendaftaran lain di keluarga yang sama sedang jalan; aman di-retry). Pendaftaran per keluarga domain diserialkan
  dengan kunci `locks/domain-family/<root>`.

---

## 3. Kronologi Perubahan

| Tanggal | Perubahan | Bukti |
|---|---|---|
| 2026-11-15 | Staging: Cloud Armor `cf-origin-lock-staging` dipasang di backend AMP; GCS via Workload Identity, key JSON `amp-sa` + Secret `amp-gsa-key` dihapus; manifest AMP staging pertama kali di-commit | CDK `57106d6`, AMP D48 |
| 2026-11-15 | Cloudflare `stagingtokobuah.xyz`: Configuration Rule `ssl: flexible` untuk `amp-api` (zone sudah `full`) | §4.1 |
| 2026-11-17 | tenant-registry dibuat (repo baru), staging (`c47c01b`, 1 replica `b454611`); AMP D49 (promo per company, `48866d1`); staging configmap AMP → registry (`764c72f`) | repo `tenant-registry-go` |
| 2026-11-17 | Production: GSA + WI + `clusterViewer`, 12 IP backend di-reserve, label + pin 12 Service, registry `v0.1.0` (`c5b4790`); AMP `v0.0.3` + configmap registry (`a03fdcb`) | CDK |
| 2026-11-17 | summon-tenant: label + pin IP otomatis di step 3 | `summon-tenant/README.md` |
| 2026-11-19 | Production AMP `v0.0.4` (fix header tab), isi image dicocokkan hash `/app/src` dengan tag (53/53) | CDK `98ce5ae` |
| 2026-11-20 | Tenant baru `padi808` otomatis berlabel + IP di-pin (`10.20.16.138`) dan terbaca registry | §2.4 |
| 2026-11-21 | AMP D50 (domain AMP sebagai subdomain money site) + perbaikan code review, staging | AMP `eec8508` |

---

## 4. Caveat, Insiden & Pelajaran

### 4.1 Error 525 di `amp-api.stagingtokobuah.xyz`
* **Gejala**: admin panel staging gagal dengan `525 SSL handshake failed`.
* **Penyebab**: mode SSL zone `stagingtokobuah.xyz` diubah ke `full` pada 2026-11-14 16:23Z (untuk host lain), padahal
  origin AMP hanya HTTP :80. Bukan dari Cloud Armor (Armor bekerja di :80; log LB tidak mencatat DENY untuk IP Cloudflare).
* **Perbaikan**: Configuration Rule `(http.host eq "amp-api.stagingtokobuah.xyz")` → `ssl: flexible`.
  **Jangan** kembalikan seluruh zone ke Flexible (host lain butuh Full).

### 4.2 kubectl context berpindah diam-diam ke production
* 2026-11-17: current-context berpindah dari staging ke `game-cluster` production di tengah sesi; `kubectl apply` tanpa
  `--context` sempat membuat namespace/ClusterRole `tenant-registry` di production `game-cluster` (pod `ErrImagePull`,
  tidak ada yang berjalan). Terdeteksi dari output `created`, langsung dihapus.
* **Aturan**: selalu `--context` dan `--project` eksplisit. `kubectl diff` dulu; kalau objek yang seharusnya ada
  tercatat `created`, berhenti.

### 4.3 Akses control plane production butuh VPN
* Master authorized networks production berisi `34.2.153.31/32` (egress VPN). Di luar VPN (mis. `114.124.x.x`),
  kubectl ke production → `TLS handshake timeout`, dan `kubectl diff` yang gagal bisa terlihat seperti "0 drift".
  Selalu baca **exit code** `kubectl diff` (0 = sama, 1 = beda, >1 = error). Jangan tambah IP pribadi ke allow-list.

### 4.4 Domain Engine: `deleteDomain()` selalu `deleteZone`
* Untuk AMP SUBDOMAIN (memakai zone money site), alur hapus lama akan **menghapus zone money site** → situs utama mati.
  Wajib bercabang (hapus DNS record + rule saja). **Selesai** di Domain Engine PR #1, dengan test regresi
  ("Delete SUBDOMAIN tidak memanggil deleteZone"). Detail: `DOMAIN_ENGINE_RUNBOOK.md` §2.2.

### 4.5 Admin panel memegang `AMP_INTERNAL_KEY`
* Panel memanggil AMP `/internal/domains` langsung dengan `X-Internal-Key` dan company code dari JWT yang hanya di-decode.
  Kunci itu bisa mendaftarkan domain untuk company mana pun. Rencana: panel berhenti memanggil `/internal`, lalu
  `INTERNAL_KEY` dirotasi (AMP `amp-secrets` + Domain Engine `AMP_INTERNAL_KEY`) dan dihapus dari env panel.

### 4.6 Halaman AMP statis
* Perubahan template / sumber promo baru terlihat setelah company **publish ulang** dari panel. Re-render memakai
  snapshot upstream tersimpan (D30), tidak memanggil upstream/registry.

### 4.7 Image production di-push di luar Cloud Build
* `amp-page:v0.0.4` di-push tanpa catatan build (juga menimpa `latest`). Sebelum dipakai: cocokkan hash semua file
  `/app/src` di pod dengan `git show <tag>:src/...`. Rilis berikutnya sebaiknya lewat `cloudbuild.prod.yaml`.

### 4.8 ⚠️ Origin AMP production tidak dikunci Cloud Armor
* 2026-11-21: `http://35.227.207.207/healthz` dan `/docs` (Host `amp-api.nkigaming.site`) menjawab **200** dari IP
  non-Cloudflare. Backend `amp-build`/`amp-serve` production tidak punya `securityPolicy`, padahal
  `cf-origin-lock-production` ada. Admin API dan `/internal` bisa dijangkau langsung lewat HTTP (tetap butuh JWT /
  `X-Internal-Key`). Dilacak kartu `amp-prod-origin-open`. Perbaikan (butuh izin, Guardrail 1): `securityPolicy` di
  `04-backendconfig.yaml` production, setelah memastikan semua host AMP production proxied lewat Cloudflare.

### 4.9 Dependency `tldts`
* Dikunci persis `tldts@7.4.19` + `overrides.tldts-core = 7.4.19` (rentang `^` sempat menarik `tldts-core` 7.5.5 yang
  baru dirilis sehari). Upgrade hanya ke versi berumur ≥ 2 minggu.

---

## 5. Prosedur Operasional

### 5.1 Rilis AMP production (zero drift)
```bash
CTX=gke_tokobuah-production_asia-southeast1_prod-core-cluster
cd ~/tokobuah/company-deployment-key/production/core/amp
kubectl --context $CTX diff -f 02-configmap.yaml -f 07-deployment-serve.yaml -f 08-deployment-build.yaml; echo $?   # harus 0
sed -i '' 's#amp-page:vOLD#amp-page:vNEW#' 08-deployment-build.yaml
kubectl --context $CTX apply -f 08-deployment-build.yaml && kubectl --context $CTX rollout status deploy/amp-build -n amp
# verifikasi image = tag: bandingkan sha256 tiap file /app/src di pod dengan git show vNEW:src/...
sed -i '' 's#amp-page:vOLD#amp-page:vNEW#' 07-deployment-serve.yaml
kubectl --context $CTX apply -f 07-deployment-serve.yaml && kubectl --context $CTX rollout status deploy/amp-serve -n amp
git add 07-deployment-serve.yaml 08-deployment-build.yaml && git commit && git push
kubectl --context $CTX diff -f 02-configmap.yaml -f 07-deployment-serve.yaml -f 08-deployment-build.yaml; echo $?   # harus 0
```
Rollback: kembalikan tag di `07`/`08`, apply. Configmap hanya diubah bila rilis menambah env.

### 5.2 Rollback AMP ke backend promo tetap
Di `02-configmap.yaml`: set `UPSTREAM_PROMOS_URL`, hapus `TENANT_REGISTRY_URL`, `TENANT_REGISTRY_AUDIENCE`,
`PROMOS_BACKEND_CIDRS` (tepat satu sumber), apply, `kubectl rollout restart deployment/amp-build -n amp`.

### 5.3 Cek tenant terbaca registry
```bash
PCL=gke_tokobuah-production_asia-southeast1-c_prod-client-cluster
kubectl --context $PCL get svc -A -l tokobuah.io/company-code \
  -o jsonpath='{range .items[*]}{.metadata.labels.tokobuah\.io/company-code}={.status.loadBalancer.ingress[0].ip}(pin {.spec.loadBalancerIP}){"\n"}{end}'
gcloud compute addresses list --project tokobuah-production --filter='name~backend-internal$'
# lookup dari pod amp-build (identitas amp-sa, ID token audience tenant-registry):
#   GET http://tenant-registry.tenant-registry.svc.cluster.local/v1/tenants/<code>  → 200 backend_url
```
Log registry yang patut di-alert: `company code withheld`, `cluster poll failed`, `service rejected`.

### 5.4 Error build AMP terkait backend promo
| Kode | Arti | Tindakan |
|---|---|---|
| `502 tenant_backend_unknown` | company belum punya `new-backend-internal` berlabel | pasang label (manifest CDK) / cek summon-tenant |
| `502 tenant_registry_unavailable` | registry mati > 15 menit / token WI gagal | cek pod `tenant-registry` |
| `502 tenant_registry_invalid` | jawaban registry tidak valid / IP di luar CIDR / ditolak 401/403 | cek `CALLERS` & log registry |

---

## 6. Open Items
* [ ] Production: pasang `cf-origin-lock-production` di backend AMP (§4.8) — butuh izin.
* [x] D50 Domain Engine: staging (`c5898f7`), uji ujung-ke-ujung lolos 2026-11-20 (`DOMAIN_ENGINE_RUNBOOK.md`).
* [ ] D50 admin panel (prompt di §7), lalu rilis production: AMP engine → Domain Engine → panel.
* [ ] Panel berhenti memanggil `/internal`; rotasi `INTERNAL_KEY` (§4.5).
* [ ] `summon-tenant` belum di git (perubahan step 3 hanya lokal).
* [ ] Trigger PR untuk AMP (`cloudbuild.pr.yaml`) belum ada; trigger tag production belum ada.
* [ ] Staging: `amp-serve` 1 replica tanpa PDB, `preStop`/connection draining 0, log `/healthz` ±30k/hari, bucket
      versioning tanpa lifecycle rule (lihat `AMP/docs/deploy.md` §10).

---

## 7. Dokumen Terkait & Handoff
* Repo AMP: `plan.md` (D33–D50), `docs/deploy.md`, `docs/domains.md`, `docs/tenant-registry.md` (diagram).
* Repo tenant-registry-go: `docs/design.md`, `docs/operations.md`, `docs/amp-integration.md`.
* Handoff fitur AMP SUBDOMAIN (2026-11-20), satu file per tim:
  * `docs/handoffs/2026-11-amp-subdomain/00-kontrak-bersama.md`
  * `docs/handoffs/2026-11-amp-subdomain/admin-panel.md`
  * `docs/handoffs/2026-11-amp-subdomain/domain-management.md`
  * `docs/handoffs/2026-11-amp-subdomain/amp-engine.md` (sudah diimplementasikan, `eec8508`)
* Domain Engine (implementasi D50, subdomain usersite, model redirect, rilis): `DOMAIN_ENGINE_RUNBOOK.md`;
  handoff lanjutan `docs/handoffs/2026-11-subdomain-redirect/`.
