# Handoff — Block `/metrics` sebagai invariant provisioning money site (Domain Engine)

**Tanggal:** 2026-11-26 · **Sejajar dengan:** P0-1 security (WAF block `/metrics` production)

## Ringkasan
Fix darurat `tbk_block_metrics` (WAF Custom Rule, block `/beapi/metrics` + `/authapi/metrics`) sudah dipasang manual ke
**91 zone money-site (STANDARD) aktif** pada 2026-11-26. Tapi fix itu hanya mencakup zona yang **ada saat ini** — zona
**baru** (tenant baru, domain STANDARD baru) belum otomatis kena.

Deliverable ini = instruksi/perintah untuk **Domain Engine** supaya menjadikan `tbk_block_metrics` **invariant provisioning**:
setiap zona STANDARD baru auto-kena, dan rekonsiliasi berkala memastikan zona eksisting yang belum punya ikut tertutup.

## File
- `domain-management.md` — prompt lengkap untuk Domain Engine (implementasi `ensureMetricsBlockRule`, pemanggilan di
  provisioning, rekonsiliasi, test, rilis, definition of done).

## Status
- [x] Fix manual zona eksisting (91 zone, 2026-11-26) — live 403.
- [ ] Domain Engine implementasi `ensureMetricsBlockRule` (lihat `domain-management.md`) — **belum**, open item.

## Referensi
- Runbook: `DOMAIN_ENGINE_RUNBOOK.md` §6 Open Items.
- Claim regression: `claims/security/demobuah-beapi-metrics-public.yaml`, `demobuah-authapi-metrics-public.yaml`
  (memonitor regresi WAF block).