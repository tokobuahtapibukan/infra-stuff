# Handoff: domain AMP sebagai subdomain money site (2026-11-20)

Prompt kerja per tim untuk fitur D50 (AMP `STANDALONE` + `SUBDOMAIN`). Setiap file berdiri sendiri dan memuat
kontrak bersama yang sama (`00-kontrak-bersama.md`), supaya ketiga tim menafsirkan aturan yang identik.

| File | Tim | Status 2026-11-21 |
|---|---|---|
| `amp-engine.md` | AMP | ✅ selesai, staging (`eec8508`) |
| `domain-management.md` | Domain Engine | ✅ selesai, staging (`main` @ `c5898f7`, PR #1) |
| `admin-panel.md` | Admin panel | ⏳ dikerjakan dev panel |

Konteks, keputusan, dan pelajaran: `../../../AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md` §2.5 dan §4;
sisi Domain Engine (implementasi, rilis, insiden): `../../../DOMAIN_ENGINE_RUNBOOK.md`.
Fitur lanjutan (subdomain usersite & redirect fleksibel): `../2026-11-subdomain-redirect/`.
Kontrak berubah → ubah keempat file sekaligus (kontrak di-embed di tiap prompt).
