# Handoff: saklar No_Index per money site (2026-11-25)

Rule WAF `No_Index` (blok crawler termasuk Googlebot/Bingbot, HTTP/1.x, negara US) yang selama ini dipasang manual oleh tim,
sekarang bisa dinyalakan/dimatikan per money site dari admin panel dan superadmin lewat Domain Engine.

| File | Tim | Status 2026-11-25 |
|---|---|---|
| (Domain Engine) | Domain Engine | ✅ staging (`noindex-7139163`, ESP `2026-11-25r0`), uji ujung-ke-ujung lolos; PR #3 |
| `admin-panel.md` | Admin panel | ⏳ siap dikerjakan (endpoint live di staging) |
| `superadmin.md` | Superadmin | ⏳ siap dikerjakan (endpoint live di staging) |

Fakta production saat desain (read-only, 2026-11-25): 94 zone money site, semuanya plan Free; 92 zone punya rule
`Black_mamba` (JS challenge), 2 zone (`tapakhoki.life`, `tapakhoki.me`) sudah punya `No_Index` manual → akan diambil alih.

Konteks Domain Engine: `../../../DOMAIN_ENGINE_RUNBOOK.md`. Kontrak berubah → ubah semua file sekaligus.

Hasil uji staging 2026-11-25 (dari SG, non-US): browser HTTP/2 → 200; HTTP/1.1 → 403; UA `AhrefsBot`/`GoogleBot` → 403;
host AMP → 200 (dikecualikan); domain yang di-redirect → 301 (redirect dievaluasi sebelum WAF). Kondisi zone dikembalikan identik.

⚠️ Temuan isi rule (belum diubah, perlu keputusan pemilik rule): `contains` peka huruf besar-kecil, sehingga entri
`GoogleBot`, `BingBot`, `PythonRequests`, dan `" Mozilla/5.0 (compatible; Googlebot…"` (diawali spasi) tidak cocok dengan UA
aslinya. Terbukti di staging: UA Googlebot/bingbot/python-requests asli lewat HTTP/2 dari non-US → 200. Googlebot sebagian
besar tetap terblokir lewat syarat US dan HTTP/1.1. Perbaikan = ubah konstanta `NO_INDEX_BASE_EXPRESSION`
(mis. `lower(http.user_agent) contains "googlebot"`).

