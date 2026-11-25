# Prompt — Domain Engine: pasang WAF block `/metrics` untuk SEMUA money site (baru & eksisting)

Kamu bekerja di Domain Management Engine (NestJS + TypeORM + BullMQ, Cloudflare API per company memakai kredensial
`company_configs`). Ikuti konvensi repo: migration TypeORM, DTO class-validator, test `*.spec.ts` (Jest, fake Cloudflare
di `test/fake-cloudflare.ts`). Baca dulu pola rule yang sudah ada di `src/cloudflare/cloudflare.service.ts`
(`upsertPhaseRule`, `deletePhaseRule`, `buildRedirectRule`, `buildHostRedirectRule`) dan alur provisioning
`src/provisioning/domain-provisioning.processor.ts`, karena fitur ini memakai pola yang sama.

## Latar belakang (kenapa ini wajib)

Pada 2026-11-26, pentest menemukan **`/beapi/metrics` dan `/authapi/metrics` terbuka tanpa auth di PRODUCTION** untuk
**semua tenant**, membocorkan label route `route=` termasuk `/admin/*` (121+ rute admin dari prod) dan metrik internal
(`balance_drift_open`, `kafka_dlq_depth`). Ini severity **critical** (exposure kontrol prod).

Fix darurat sudah diterapkan manual ke **91 zone money-site (STANDARD) yang aktif saat itu**: WAF Custom Rule
`tbk_block_metrics` pada phase `http_request_firewall_custom`, `action: block`. **Tapi itu hanya menutup zone yang sudah
ada.** Zona money site baru (tenant baru, atau domain `STANDARD` baru ditambahkan) **belum punya rule ini secara otomatis.**

Tugas kamu: jadikan `tbk_block_metrics` **invariant bertingkat provisioning** — setiap zona `STANDARD` yang dibuat engine
wajib membawa rule ini sejak hari pertama, plus rekonsiliasi zona eksisting yang belum punya.

## Invariant yang harus dijaga (jangan diubah sepihak)

1. **Setiap zona money-site (`type = 'STANDARD'`, `provisionOwnZone`) WAJIB punya WAF Custom Rule** `tbk_block_metrics`
   (phase `http_request_firewall_custom`, `action: block`).
2. **Ekspresi rule (persis):**
   ```
   (ends_with(http.request.uri.path, "/beapi/metrics") or ends_with(http.request.uri.path, "/authapi/metrics"))
   ```
3. **Idempotent & deterministik:** pakai `ref = "tbk_block_metrics"` sehingga sumber ulang memakai ulang rule yang sama,
   tidak menduplikat. Sama seperti pola `upsertPhaseRule` untuk redirect/SSL.
4. **Jangan menimpa rule lain:** tambah/ubah/hapus **per rule**, `POST/PATCH …/rules/{id}` — **tidak pernah `PUT`
   entrypoint** (invariant `domain-engine-no-entrypoint-put`). Rule tenant lain (mis. `Black_mamba` js_challenge) harus utuh.
5. **Hanya dua path itu yang diblokir** (403). Path & endpoint lain tidak boleh terpengaruh (verifikasi homepage tetap 200).

## Yang harus kamu kerjakan

### 1. `src/cloudflare/cloudflare.service.ts`
Tambah method `ensureMetricsBlockRule(zoneId, creds): Promise<string>` yang:
- `GET /zones/{zoneId}/rulesets/phases/http_request_firewall_custom/entrypoint`;
- kalau sudah ada rule dengan `ref == 'tbk_block_metrics'` → kembalikan id-nya (no-op, idempotent);
- kalau belum → `POST /zones/{zoneId}/rulesets/{ruleset}/rules` dengan rule `{ ref, description, expression, action: 'block' }`.
- Error Cloudflare karena batas jumlah rule (plan zone) → lemparkan error yang jelas (`409`), JANGAN lanjut diam-diam tanpa rule.

Letakkan di samping `createRedirectRule`/`ensureHostSslFlexibleRule` (semua memakai `upsertPhaseRule`/`deletePhaseRule`).

### 2. Panggil saat provisioning zona STANDARD
Di `domain-provisioning.processor.ts`, pada jalur `provisionOwnZone` (money site), **setelah zone dibuat / DNS siap**,
tambahkan langkah provisioning baru — mis. step `metrics-rule` di antara `dns` dan `completed`:
- panggil `ensureMetricsBlockRule(zoneId, creds)` per company;
- simpan/mark selesai di DB (bisa lewat `provisioningStep` yang sudah ada, atau kolom/flag non-teknis — pilih yang paling
  konsisten dengan state machine provisioning saat ini);
- kalau zona gagal mendapat rule → provisioning **tidak boleh** dianggap `completed`: gagal terlihat (re-try via cron
  `sync-pending`), bukan sinkron diam.

### 3. Rekonsiliasi zona eksisting (belum punya rule)
Pastikan proses sinkronisasi berkala (`sync-pending` CronJob `POST …/internal/domains/sync-pending`) atau prosesor
konvergensi juga **memastikan** `ensureMetricsBlockRule` untuk **semua** zona `STANDARD` yang `provisioningStatus='completed'`
dan `status='active'` — sehingga kalau ada zona lama atau gagal sekali, akan tertutup otomatis pada siklus berikutnya
(idempotent, aman diulang).

### 4. Test (`*.spec.ts`, fake Cloudflare)
- Provisioning zona `STANDARD` baru → memanggil `ensureMetricsBlockRule` dan rule `tbk_block_metrics` ada di respons.
- Sumber ulang / zona yang rule-nya sudah ada → **tidak** menambah rule duplikat (opsi `ref` idempotent).
- Zona yang plan-nya tidak mendukung custom rule → provisioning gagal / estatus jelas, bukan `completed` tanpa rule.
- Rule tenant lain di phase yang sama tetap utuh setelah operasi (pola no-PUT).
- Defensive: `SUBDOMAIN` dan `AMP` tidak boleh memanggil `ensureMetricsBlockRule` pada zona parent-nya sendiri
  (block cukup di money-site / zone yang melayani `/beapi`, `/authapi` dari origin tenant).

### 5. Rilis
- Staging dulu: build image, retag `latest`, rollout, deploy Cloud Endpoints (`openapi.yaml`/`openapi-prod.yaml`) jika ada
  endpoint baru. Migration berjalan saat boot.
- Uji ujung-ke-ujung: tambahkan satu money-site `STANDARD` baru di staging → verifikasi `curl https://<domain>/beapi/metrics`
  = **403** dan `/authapi/metrics` = **403**, sedangkan `https://<domain>/` tetap **200**.

## Definition of done
- `ensureMetricsBlockRule` ada, dipanggil untuk setiap zona `STANDARD` baru, dan dipastikan ulang lewat rekonsiliasi berkala.
- Tidak ada `PUT` entrypoint; rule tenant lain tidak hilang.
- Tidak ada secret yang diprint/dilog (kredensial Cloudflare hanya dipakai di proses, dirujuk via env/DB).
- Ekspresi rule tetap persis seperti no. 2; hanya `/beapi/metrics` & `/authapi/metrics` yang diblokir.

## Verifikasi akhir (read-only)
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://<money-site>/beapi/metrics   # 403
curl -sS -o /dev/null -w "%{http_code}\n" https://<money-site>/authapi/metrics  # 403
curl -sS -o /dev/null -w "%{http_code}\n" https://<money-site>/                  # 200
```