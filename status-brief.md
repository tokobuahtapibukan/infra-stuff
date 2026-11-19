# STATUS BRIEF

> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.
> Last sweep: **2026-11-19 16:42 UTC** · engine: `drift_engine v1`

**Sweep ini: 12 kartu dicek · ✅ 10 verified · ❌ 0 drift · ⚠️ 2 stale · ⏭️ 2 carry-forward (dalam jendela recheck)**

**Carry-forward 2 kartu** (terakhir dicek ?): 0 terakhir VERIFIED

## Per environment (sweep ini)

| Env | Verified | Drift | Stale |
|---|---|---|---|
| production | 8 | 0 | 1 |
| staging | 1 | 0 | 1 |
| both | 1 | 0 | 0 |

## ❌ Drift

- (tidak ada — semua klaim sesuai ekspektasi)

## ⚠️ Stale (cek tidak bisa dijalankan)

- **`gameengine-gclb-ip`**: kubectl gagal/kosong: [Errno 2] No such file or directory: 'kubectl'
- **`staging-tripay-cluster-dead`**: GKE REST tidak tersedia DAN gcloud CLI gagal: [Errno 2] No such file or directory: 'gcloud'

## 📋 Fix-tracking (open items yang sedang di-follow)

- ✅ `staging-url-in-prod-bundle` — Open finding: JS bundle produksi dutaledak.online masih hardcode 'https://stagingtokobuah.xyz' (fallback canon
- ⏭️ `gonet-x-lag` (carry: ?) — P1 (masih OPEN): golang.org/x/net versi deklarasinya masih < 0.62.0 di 7 dari 8 repo Go (audit, auth, connecto
- ⏭️ `p0-secret-yaml-tracked` (carry: ?) — P0 (masih OPEN): 26 file 'secret.yaml*' masih ter-track di git repo company-deployment-key (12 production + 14
