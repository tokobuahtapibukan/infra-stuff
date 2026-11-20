# STATUS BRIEF

> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.
> Last sweep: **2026-11-20 16:53 UTC** · engine: `drift_engine v1`

**Sweep ini: 18 kartu dicek · ✅ 11 verified · ❌ 1 drift · ⚠️ 6 stale · ⏭️ 18 carry-forward (dalam jendela recheck)**

**Carry-forward 18 kartu** (terakhir dicek ?): 3 terakhir VERIFIED, ⚠️ 1 masih belum sehat: `staging-ssh-firewall-scoped` (DRIFTED)

## Per environment (sweep ini)

| Env | Verified | Drift | Stale |
|---|---|---|---|
| production | 6 | 1 | 5 |
| staging | 4 | 0 | 1 |
| both | 1 | 0 | 0 |

## ❌ Drift

- **`sentinel-scan-targets-complete`** (meta, production): uncovered: expect [] got ['dataset-forwarding-rule', 'production-buah5758-http-forwarding-rule', 'production-cinabotak-http-forwarding-rule', 'production-cinasuper-http-forwarding-rule', 'production-dutaledak-http-forwarding-rule', 'production-hambabet-http-forwarding-rule', 'production-ikn788-http-forwarding-rule', 'production-omsipit-http-forwarding-rule', 'production-padi808-http-forwarding-rule', 'production-pengenwd-http-forwarding-rule', 'production-rumushoki-http-forwarding-rule', 'production-tapakhoki-http-forwarding-rule', 'production-terbangwd-http-forwarding-rule', 'production-terios88-http-forwarding-rule']
  - claim: Semua global HTTP LB production yang menerima traffic muncul di log http_load_balancer 7 hari terakhir (mekanisme scan 7-day sentinel hub)
  - kartu: `claims/meta/sentinel-scan-targets-complete.yaml`

## ⚠️ Stale (cek tidak bisa dijalankan)

- **`cost-scheduler-not-deployed`**: Cloud Scheduler API error: {'code': 403, 'message': 'The principal (user or service account) lacks IAM permission "cloudscheduler.jobs.list" for the resource "projects/tokobuah-
- **`dutaledak-sibling-live`**: curl gagal: Command '['curl', '-sS', '--max-time', '30', 'https://dutaledak.store/']' timed out after 40 seconds
- **`gcs-level-images-public`**: curl gagal: Command '['curl', '-sS', '--max-time', '30', 'https://dutaledak.online/beapi/public/levels']' timed out after 40 seconds
- **`maintenance-off-demobuah`**: curl gagal: Command '['curl', '-sS', '--max-time', '30', 'https://demobuah.online/api/maintenance']' timed out after 40 seconds
- **`maintenance-off-dutaledak`**: curl gagal: Command '['curl', '-sS', '--max-time', '30', 'https://dutaledak.online/api/maintenance']' timed out after 40 seconds
- **`partner-portal-domain-live`**: curl gagal: Command '['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '30', 'https://buahdatasemuammanis.net/']' timed out after 40 seconds

## 📋 Fix-tracking (open items yang sedang di-follow)

- ⚠️ `cost-scheduler-not-deployed` — Open: staging cost-scheduler (company-deployment-key/cost-scheduler) BELUM dideploy — 0 job Cloud Scheduler 's
- ✅ `staging-url-in-prod-bundle` — Open finding: JS bundle produksi dutaledak.online masih hardcode 'https://stagingtokobuah.xyz' (fallback canon
- ⏭️ `core-repos-no-secret-tracked` (carry: ?) — Repo inti (auth/transactional/backend-pg/game-engine/user-site/dataset/content/domain) TIDAK mem-track berkas 
- ⏭️ `gocrypto-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/crypto masih < 0.58.1 di 7 dari 8 repo Go (devops-engine jauh di v0.25.0; whitel
- ⏭️ `gonet-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/net versi deklarasinya masih < 0.62.0 di 7 dari 8 repo Go (audit, auth, connecto
- ⏭️ `no-latest-in-cdk` (carry: ?) — Open (P2): 52 baris manifest di working tree company-deployment-key masih memakai tag image :latest (prod+stag
- ⏭️ `node20-eol-dockerfiles` (carry: ?) — Open (P2): base image node:20 (EOL April 2026) masih dipakai di 8 baris Dockerfile lintas 4 repo (backend-pg, 
- ⏭️ `p0-secret-yaml-tracked` (carry: ?) — P0 (masih OPEN): 26 file 'secret.yaml*' masih ter-track di git repo company-deployment-key (12 production + 14
- ⏭️ `tripay-sc-secrets-tracked` (carry: ?) — Open finding (P0-related): 4 berkas secret ter-track di git repo tripay-sc (secret.ts wl-be, wl-callback, wl-c
