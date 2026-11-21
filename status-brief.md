# STATUS BRIEF

> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.
> Last sweep: **2026-11-21 04:56 UTC** · engine: `drift_engine v1`

**Sweep ini: 16 kartu dicek · ✅ 16 verified · ❌ 0 drift · ⚠️ 0 stale · ⏭️ 34 carry-forward (dalam jendela recheck)**

**Carry-forward 34 kartu** (terakhir dicek ?): 5 terakhir VERIFIED, ⚠️ 4 masih belum sehat: `cost-scheduler-not-deployed` (STALE), `sentinel-scan-targets-complete` (DRIFTED), `dutaledak-sibling-live` (STALE), `gcs-level-images-public` (STALE)

## Per environment (sweep ini)

| Env | Verified | Drift | Stale |
|---|---|---|---|
| production | 10 | 0 | 0 |
| staging | 5 | 0 | 0 |
| both | 1 | 0 | 0 |

## ❌ Drift

- (tidak ada — semua klaim sesuai ekspektasi)

## ⚠️ Stale (cek tidak bisa dijalankan)

- (tidak ada)

## 📋 Fix-tracking (open items yang sedang di-follow)

- ✅ `amp-prod-origin-open` — Closed: probe HTTP langsung dari source non-Cloudflare ke Ingress AMP production (35.227.207.207) ditolak 403 
- ⏭️ `amp-base-image-policy` (carry: ?) — Dockerfile AMP (node:24.x) dan tenant-registry-go (golang:1.26 + distroless) tidak memakai stream base image E
- ⏭️ `amp-repos-no-secret-tracked` (carry: ?) — Repo AMP dan tenant-registry-go TIDAK mem-track berkas secret (0 file)
- ⏭️ `core-repos-no-secret-tracked` (carry: ?) — Repo inti (auth/transactional/backend-pg/game-engine/user-site/dataset/content/domain) TIDAK mem-track berkas 
- ⏭️ `cost-scheduler-not-deployed` (carry: STALE) — Open: staging cost-scheduler (company-deployment-key/cost-scheduler) BELUM dideploy — 0 job Cloud Scheduler 's
- ⏭️ `gocrypto-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/crypto masih < 0.58.1 di 7 dari 8 repo Go (devops-engine jauh di v0.25.0; whitel
- ⏭️ `gonet-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/net versi deklarasinya masih < 0.62.0 di 7 dari 8 repo Go (audit, auth, connecto
- ⏭️ `no-latest-in-cdk` (carry: ?) — Open (P2): 52 baris manifest di working tree company-deployment-key masih memakai tag image :latest (prod+stag
- ⏭️ `node20-eol-dockerfiles` (carry: ?) — Open (P2): base image node:20 (EOL April 2026) masih dipakai di 8 baris Dockerfile lintas 4 repo (backend-pg, 
- ⏭️ `p0-secret-yaml-tracked` (carry: ?) — P0 (masih OPEN): 26 file 'secret.yaml*' masih ter-track di git repo company-deployment-key (12 production + 14
- ⏭️ `staging-url-in-prod-bundle` (carry: VERIFIED) — Open finding: JS bundle produksi dutaledak.online masih hardcode 'https://stagingtokobuah.xyz' (fallback canon
- ⏭️ `tripay-sc-secrets-tracked` (carry: ?) — Open finding (P0-related): 4 berkas secret ter-track di git repo tripay-sc (secret.ts wl-be, wl-callback, wl-c
