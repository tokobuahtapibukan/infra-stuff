# Infra Fact Registry — `claims/`

Daftar **fakta infra yang teruji** + cara membuktikannya lagi. Satu kartu = satu fakta.
Ini adalah "peta yang membuktikan dirinya sendiri" — engine checker menjalankan semua kartu
secara terjadwal dan menghasilkan `../status-brief.md`.

## Aturan main (wajib)

1. **Satu kartu = satu fakta**, dengan `id` stabil (kebab-case). Fakta berubah → **edit kartu
   yang sudah ada**, jangan buat kartu duplikat.
2. **`expect` harus deterministik** (count, equals, subset, absen, status HTTP, hash).
   LLM tidak boleh jadi hakim pass/fail — hanya engine yang membandingkan.
3. **Tidak ada secret value di kartu mana pun** (AGENTS.md §5): hanya count, existence,
   source, atau one-way hash. Kredensial perilaku (test account dll.) hidup di env hub,
   dirujuk lewat nama (field `credentials`), tidak pernah di-commit.
4. **Ownership via `service:`** — fisik file semua ada di sini, tapi room pemilik
   service-lah yang menjaga kartu bertag service itu tetap benar.
5. **Fakta per-environment berbeda → kartu berbeda** (tag `env:` sama fakta, nilai beda = 2 kartu).
6. **Kartu lahir dari verifikasi live** di sesi kerja mana pun (lihat `~/AGENTS.md` §9),
   dan **retire** saat tidak relevan lagi (hapus file + note di commit message; git history = arsip).

## File ownership (mencegah git conflict antara room-Mac dan hub)

| Path | Pemilik | Keterangan |
|---|---|---|
| `claims/**` | manusia + room-Mac | kartu & skema; hub TIDAK menulis di sini |
| `docs/**`, `*.md` (KB/runbook) | manusia + room-Mac | narasi |
| `status-brief.md` | **GENERATED (hub/engine)** | jangan edit manual |
| `drift-results/**` | **GENERATED (hub/engine)** | jangan edit manual |

Hub hanya `git add status-brief.md drift-results/` saat push hasil sweep.

## Bootstrap checklist — service/repo BARU masuk ekosistem

Saat chat room baru mengerjakan service/repo baru, ia wajib menambah minimal kartu-kartu ini:

- [ ] `service-alive` — deployment/pod/service hidup & healthy (env: prod &/atau staging)
- [ ] `no-secret-tracked` — `git ls-files` repo tersebut bebas `.env` non-example / `secret.yaml`
- [ ] `base-image-policy` — base image Dockerfile bukan stream EOL (node:20, golang:1.22, dst.)
- [ ] `owner` — siapa owner SRE + di mana runbook-nya (kartu `info`, cek = file exists)
- [ ] `surface` — domain/LB/endpoint publiknya apa (input radar sentinel; kartu `surface/`)

## Wave 2 — service di luar GCP (rencana, belum di-seed)

Sistem ini provider-agnostic: cukup tambah fungsi cek + **1 kredensial read-only di env hub
(tidak pernah masuk git)**. Kandidat kartu per service:

| Service | State card | Invariant card (mini-pentest terjadwal) |
|---|---|---|
| MongoDB | primary & replication lag OK; DB tenant ada | akses **tanpa** auth harus ditolak |
| Kafka (Confluent Cloud) | topic `game-transaction-{tenant}` ada untuk semua tenant | consumer group tak dikenal = 0 |
| Cloudflare | jumlah account/zone sesuai (hub sudah punya Domain Engine) | origin-lock probe tetap 403 |
| Firebase RTDB | rules hash tidak berubah | config source maintenance = `rtdb` |

## Status hidup kartu

```
active → (engine lolos) last_verified ter-stamp tiap sweep
       → (engine gagal) DRIFTED → alert → patch → active lagi
       → (cek error/credential hilang) STALE  → alert meta "engine tidak sehat"
       → (tidak relevan) RETIRED → hapus file
```
