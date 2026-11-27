# STATUS BRIEF

> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.
> Last sweep: **2026-11-27 05:27 UTC** · engine: `drift_engine v1`

**Sweep ini: 34 kartu dicek · ✅ 32 verified · ❌ 1 drift · ⚠️ 1 stale · ⏭️ 34 carry-forward (dalam jendela recheck)**

**Carry-forward 34 kartu** (terakhir dicek ?): 4 terakhir VERIFIED, ⚠️ 1 masih belum sehat: `gmp-no-app-metrics-scrape` (STALE)

## Per environment (sweep ini)

| Env | Verified | Drift | Stale |
|---|---|---|---|
| production | 18 | 0 | 0 |
| staging | 13 | 1 | 1 |
| both | 1 | 0 | 0 |

## ❌ Drift

- **`staging-openapi-and-docs-public`** (all-go, staging): status: expect 200 got 404
  - claim: Dokumentasi OpenAPI backend staging terbuka tanpa auth di https://dev.stagingtokobuah.xyz: /beapi/openapi.yaml (1,4 MB, 200), /authapi/openapi.yaml (150 KB, 200), /beapi/docs (200). Berisi route internal/admin, schema seluruh tabel DB live, model role (SUPERADMIN/ADMIN), skema HMAC, arsitektur (Kafka/Redis/backend-pg), kontak dev. Prod demobuah.online TIDAK terekspos (404 untuk /beapi/openapi.yaml, /authapi/openapi.yaml, /beapi/docs).
  - kartu: `claims/security/staging-openapi-and-docs-public.yaml`

## ⚠️ Stale (cek tidak bisa dijalankan)

- **`staging-payment-mockup-public`**: curl gagal: 000curl: (35) TLS connect error: error:0A000126:SSL routines::unexpected eof while reading

## 📋 Fix-tracking (open items yang sedang di-follow)

- ✅ `amp-prod-origin-open` — Closed: probe HTTP langsung dari source non-Cloudflare ke Ingress AMP production (35.227.207.207) ditolak 403 
- ✅ `cost-scheduler-not-deployed` — Open: staging cost-scheduler (company-deployment-key/cost-scheduler) BELUM dideploy — 0 job Cloud Scheduler 's
- ✅ `staging-url-in-prod-bundle` — Open finding: JS bundle produksi dutaledak.online masih hardcode 'https://stagingtokobuah.xyz' (fallback canon
- ⏭️ `amp-base-image-policy` (carry: ?) — Dockerfile AMP (node:24.x) dan tenant-registry-go (golang:1.26 + distroless) tidak memakai stream base image E
- ⏭️ `amp-repos-no-secret-tracked` (carry: ?) — Repo AMP dan tenant-registry-go TIDAK mem-track berkas secret (0 file)
- ⏭️ `core-repos-no-secret-tracked` (carry: ?) — Repo inti (auth/transactional/backend-pg/game-engine/user-site/dataset/content/domain) TIDAK mem-track berkas 
- ⏭️ `gocrypto-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/crypto masih < 0.58.1 di 7 dari 8 repo Go (devops-engine jauh di v0.25.0; whitel
- ⏭️ `gonet-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/net versi deklarasinya masih < 0.62.0 di 7 dari 8 repo Go (audit, auth, connecto
- ⏭️ `no-latest-in-cdk` (carry: ?) — Open (P2): 52 baris manifest di working tree company-deployment-key masih memakai tag image :latest (prod+stag
- ⏭️ `node20-eol-dockerfiles` (carry: ?) — Open (P2): base image node:20 (EOL April 2026) masih dipakai di 8 baris Dockerfile lintas 4 repo (backend-pg, 
- ⏭️ `p0-secret-yaml-tracked` (carry: ?) — P0 (masih OPEN): 26 file 'secret.yaml*' masih ter-track di git repo company-deployment-key (12 production + 14
- ⏭️ `tripay-sc-secrets-tracked` (carry: ?) — Open finding (P0-related): 4 berkas secret ter-track di git repo tripay-sc (secret.ts wl-be, wl-callback, wl-c
