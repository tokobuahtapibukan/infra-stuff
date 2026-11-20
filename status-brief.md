# STATUS BRIEF

> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.
> Last sweep: **2026-11-20 04:43 UTC** · engine: `drift_engine v1`

**Sweep ini: 8 kartu dicek · ✅ 7 verified · ❌ 1 drift · ⚠️ 0 stale · ⏭️ 24 carry-forward (dalam jendela recheck)**

**Carry-forward 24 kartu** (terakhir dicek ?): 11 terakhir VERIFIED, ⚠️ 1 masih belum sehat: `gameengine-gclb-ip` (STALE)

## Per environment (sweep ini)

| Env | Verified | Drift | Stale |
|---|---|---|---|
| production | 6 | 0 | 0 |
| staging | 0 | 1 | 0 |
| both | 1 | 0 | 0 |

## ❌ Drift

- **`staging-ssh-firewall-scoped`** (meta, staging): ssh_sources_ok: expect True got False
  - claim: Firewall staging terkunci: 3 rule SSH hanya dari VPN gateway + IAP; TIDAK ADA rule RDP
  - kartu: `claims/meta/staging-ssh-firewall-scoped.yaml`

## ⚠️ Stale (cek tidak bisa dijalankan)

- (tidak ada)

## 📋 Fix-tracking (open items yang sedang di-follow)

- ⏭️ `core-repos-no-secret-tracked` (carry: ?) — Repo inti (auth/transactional/backend-pg/game-engine/user-site/dataset/content/domain) TIDAK mem-track berkas 
- ⏭️ `gocrypto-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/crypto masih < 0.58.1 di 7 dari 8 repo Go (devops-engine jauh di v0.25.0; whitel
- ⏭️ `gonet-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/net versi deklarasinya masih < 0.62.0 di 7 dari 8 repo Go (audit, auth, connecto
- ⏭️ `no-latest-in-cdk` (carry: ?) — Open (P2): 51 baris manifest di 26 file company-deployment-key masih memakai tag image :latest (prod+staging)
- ⏭️ `node20-eol-dockerfiles` (carry: ?) — Open (P2): base image node:20 (EOL April 2026) masih dipakai di 8 baris Dockerfile lintas 4 repo (backend-pg, 
- ⏭️ `p0-secret-yaml-tracked` (carry: ?) — P0 (masih OPEN): 26 file 'secret.yaml*' masih ter-track di git repo company-deployment-key (12 production + 14
- ⏭️ `staging-url-in-prod-bundle` (carry: VERIFIED) — Open finding: JS bundle produksi dutaledak.online masih hardcode 'https://stagingtokobuah.xyz' (fallback canon
- ⏭️ `tripay-sc-secrets-tracked` (carry: ?) — Open finding (P0-related): 4 berkas secret ter-track di git repo tripay-sc (secret.ts wl-be, wl-callback, wl-c
