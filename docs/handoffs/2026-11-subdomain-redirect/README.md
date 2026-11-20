# Handoff: subdomain usersite & redirect fleksibel antar host tenant (2026-11-20)

Prompt kerja per tim untuk fitur subdomain usersite (`type: "SUBDOMAIN"`, mis. `abc.x.com`) dan redirect bebas antar
host milik tenant (root ↔ subdomain, lintas money site, dengan opsi *standalone*). Setiap file berdiri sendiri dan
memuat kontrak bersama yang sama (`00-kontrak-bersama.md`). AMP engine tidak berubah.

| File | Tim | Status 2026-11-21 |
|---|---|---|
| `domain-management.md` | Domain Engine | ✅ selesai, staging (`main` @ `c5898f7`, PR #2) |
| `admin-panel.md` | Admin panel | ⏳ dikerjakan dev panel |

Catatan implementasi vs prompt (implementasi yang berlaku):
* `www` **boleh** dibuat sebagai subdomain usersite (mengadopsi `CNAME www` milik money site; hapus = hanya hapus
  pengaturannya). Untuk AMP, `www` tetap ditolak.
* Hapus subdomain usersite yang masih diproses → `409 subdomain_provisioning` (kode terpisah dari
  `amp_subdomain_provisioning`).
* Partial unique index "1 AMP per company" **tidak** ikut rilis ini (production: 0 duplikat per 2026-11-21, aman
  dibuat di PR terpisah).

Konteks, keputusan, prosedur rilis, dan pelajaran: `../../../DOMAIN_ENGINE_RUNBOOK.md`.
Ringkasan untuk dev panel (endpoint, payload, kode error, data uji): artifact "Handoff Subdomain & Redirect"
(https://claude.ai/artifact/J4LcwhF1uG3Bm925RZLRDy, privat; dibagikan manual).
Kontrak berubah → ubah ketiga file sekaligus (kontrak di-embed di tiap prompt).
