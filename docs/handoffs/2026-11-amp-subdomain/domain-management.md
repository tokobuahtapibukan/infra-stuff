# Prompt — Domain Management Engine (repo `tokobuah/domain-management`): AMP sebagai subdomain money site

Kamu bekerja di Domain Management Engine (NestJS + TypeORM + BullMQ, Cloudflare API per company memakai kredensial di
`company_configs`). Ikuti konvensi repo yang ada (migration TypeORM, DTO class-validator, test `*.spec.ts`).

## Latar belakang
Sekarang domain `type: 'AMP'` selalu **root domain dengan zone Cloudflare sendiri**
(`domain.service.ts` → `registerDomain` menolak non-root; `domain-provisioning.processor.ts` → `createZone` → `ssl` → `dns` A `@` → `amp`).
Request lapangan: AMP juga bisa dibuat sebagai **subdomain dari money site (domain `STANDARD`) milik agent yang sama**,
contoh `amp.merek.com` di bawah `merek.com`, memakai **zone Cloudflare money site yang sudah ada**. Mode lama tetap jalan.

## Kontrak bersama (identik di ketiga prompt — jangan diubah sepihak)

**Fitur:** domain AMP sekarang bisa dibuat dengan dua mode.

| Mode | Contoh | Status |
|---|---|---|
| `STANDALONE` | `merekamp.com` (root domain sendiri, zone Cloudflare sendiri) | **Sudah ada**, tetap berjalan seperti sekarang |
| `SUBDOMAIN` | `amp.merek.com`, di bawah money site / usersite aktif agent `merek.com` | **Baru** |

**Istilah**
- *Money site / usersite* = domain bertipe `STANDARD` di Domain Engine (situs utama agent).
- *Label* = bagian depan subdomain yang diketik admin. Di `amp.merek.com`, label = `amp`, parent = `merek.com`.

**Aturan mode SUBDOMAIN**
1. Tepat **satu tingkat**: `label.parent`. `a.b.merek.com` ditolak. *Parent* = registrable domain menurut **public suffix list resmi (ICANN)**,
   sama di ketiga komponen (AMP memakai `tldts` versi `7.4.19`; Domain Engine dan panel pakai library PSL yang sama atau setara):
   `merek.com.vn` dan `merek.co.th` = root, `amp.merek.com.vn` = subdomain, `co.id` / `com.vn` / TLD tidak resmi (`.test`) **bukan domain**.
   Jangan pakai daftar TLD manual (daftar lama tidak lengkap).
2. Label: huruf kecil/angka/`-`, regex `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`, **bukan `www`**. Default yang diisi otomatis di UI: `amp`. Hostname total ≤ 253 karakter.
3. Parent wajib domain `STANDARD` milik **company yang sama**, provisioning `completed`, status zone `active`.
4. Tetap **1 domain AMP per company** (STANDALONE atau SUBDOMAIN, bukan keduanya).
5. Default `redirectTo` (tujuan tombol Login/Daftar/Game/Promo) = parent (money site), contoh `merek.com`.
6. Default `canonical` = **host AMP itu sendiri**, contoh `amp.merek.com` → `<link rel="canonical" href="https://amp.merek.com/">`, supaya halaman AMP diindeks Google. (Mode STANDALONE tidak berubah.)
7. DNS: record `A <label>` → IP ingress AMP (`AMP_INGRESS_IP`), **proxied = true** (origin AMP dikunci Cloud Armor: hanya IP Cloudflare; record DNS-only = pengunjung kena 403).
8. SSL: origin AMP hanya HTTP :80. Untuk host AMP dibuat **Configuration Rule Cloudflare `ssl: flexible` khusus host itu**, supaya tetap jalan walau mode SSL zone money site diubah ke Full/Strict (kalau tidak: error 525).
9. **Menghapus AMP SUBDOMAIN hanya menghapus DNS record + configuration rule miliknya. Zone money site TIDAK BOLEH dihapus.**
10. Menghapus domain `STANDARD` yang jadi parent AMP SUBDOMAIN **ikut menghapus AMP tersebut** secara otomatis
    (deregister dari AMP engine → hapus row AMP → hapus zone money site → hapus row money site). Ditolak `409` hanya bila
    AMP anak masih `queued`/`processing`; bila deregister AMP engine gagal → `502` dan **tidak ada** yang terhapus.
11. Redirect domain parent (mis. `merek.com` → `baru.com`) **tidak boleh** mengenai host AMP SUBDOMAIN: `amp.merek.com`
    tetap menyajikan AMP. Domain Engine menyusun expression redirect dengan pengecualian host AMP
    (`not (http.host in {"amp.merek.com"})`) dan menyinkronkannya setiap AMP SUBDOMAIN dibuat/dihapus atau redirect dibuat.

**Alur & kepemilikan (satu jalur saja)**
```
Admin panel ──► Domain Engine ──► AMP engine (PUT/DELETE /internal/domains/{companyCode}, X-Internal-Key)
               (sumber kebenaran     (simpan mapping host → company, sajikan halaman)
                domain + Cloudflare)
```
Panel **tidak lagi** memanggil `/internal/domains` AMP secara langsung; semua lewat Domain Engine
(yang memang sudah mendaftarkan, meng-update, dan menghapus domain di AMP).

**Kontrak API Domain Engine (baru)**
- `POST /domains` untuk SUBDOMAIN:
  `{ "type": "AMP", "ampMode": "SUBDOMAIN", "companyCode": "...", "parentDomain": "merek.com", "subdomainLabel": "amp", "ampRedirectTo"?: "...", "ampCanonical"?: "..." }`
  → `domainName` dihitung Domain Engine = `amp.merek.com`. Default no. 5 & 6 diterapkan bila kosong.
- STANDALONE tetap: `{ "type": "AMP", "domainName": "merekamp.com", ... }` (boleh tambah `"ampMode": "STANDALONE"`, default bila tidak dikirim).
- `GET /domains` / `GET /domains/:name` mengembalikan field tambahan `ampMode` (`STANDALONE`|`SUBDOMAIN`|null) dan `parentDomain` (string|null).
- `DELETE /domains/:name` untuk STANDARD yang punya anak AMP SUBDOMAIN → `204`, AMP anak **ikut terhapus** (aturan no. 10).
  `409` kode `amp_subdomain_provisioning` bila AMP anak masih diproses; `502` kode `amp_deregister_failed` bila AMP engine
  gagal (tidak ada yang terhapus, aman diulang).
- `POST /redirects` dengan `sourceDomain` = money site yang punya AMP SUBDOMAIN → sukses, host AMP otomatis dikecualikan
  (aturan no. 11). `sourceDomain` = host AMP SUBDOMAIN itu sendiri → `400`.
- Validasi gagal → `400` dengan pesan jelas (label tidak valid, `www`, parent bukan milik company / belum aktif, sudah ada AMP, record DNS dengan nama itu sudah ada).

**Kontrak AMP `/internal/domains/{companyCode}` (baru)**
- `PUT` body tetap `{ domain, zoneId?, redirectTo?, canonical? }`; `domain` sekarang boleh root **atau** subdomain satu tingkat.
- `409 parent_domain_taken` bila parent/anak domain itu sedang **aktif** dipakai company lain di AMP; `409 hostname_taken` bila host persisnya milik company lain.
- `422 domain_reserved` bila domain berada di keluarga `AMP_DOMAIN` milik layanan; `503 busy` (aman di-retry) bila pendaftaran lain di keluarga domain yang sama sedang berjalan.
- AMP **tidak** mengisi canonical sendiri: Domain Engine wajib mengirim `canonical` = host AMP sebagai default untuk SUBDOMAIN.
- `DELETE` idempotent: company yang tidak punya domain terdaftar → `2xx` atau `404`; Domain Engine menganggap keduanya sukses.

**Urutan rilis:** AMP engine (kompatibel ke belakang) → Domain Engine → Admin panel. **Staging dulu**, production setelah lolos uji ujung-ke-ujung.

## ⚠️ Bahaya yang wajib dicegah
`deleteDomain()` sekarang **selalu** memanggil `cloudflareService.deleteZone(domain.cloudflareZoneId)`. Untuk AMP SUBDOMAIN,
zone yang dipakai adalah **zone money site**. Kalau zone id itu disimpan di `cloudflareZoneId` dan alur hapus tidak diubah,
menghapus/mengganti AMP akan **menghapus zone money site dan mematikan situs utama agent**. Semua fungsi yang menyentuh
zone harus membedakan mode (lihat no. 5).

Bahaya lain:
- Untuk SUBDOMAIN `cloudflareZoneId` = null, padahal `if (!domain.cloudflareZoneId)` adalah pemicu `createZone` di processor.
  Tentukan cabang mode **di awal** `process()`, dan beri guard eksplisit di jalur lama: `ampMode === 'SUBDOMAIN'` tidak pernah
  boleh mencapai `createZone`/`setSslMode`/`setPseudoIpv4`.
- `createRedirectRule`/`deleteRedirectRule` sekarang `PUT` entrypoint `http_request_dynamic_redirect` dengan
  `expression: 'true'`: semua host di zone ikut ter-redirect (termasuk `amp.merek.com`), dan `PUT` menimpa semua redirect rule
  lain di zone. Lihat no. 5a.

## Yang harus kamu kerjakan

### 1. Data — migration baru
Kolom baru di `domains`:
- `ampMode` varchar null (`'STANDALONE' | 'SUBDOMAIN'`; backfill `'STANDALONE'` untuk `type = 'AMP'` yang sudah ada).
- `parentDomainId` int null, FK ke `domains.id` (`ON DELETE RESTRICT`).
- `parentZoneId` varchar null (zone money site yang dipakai; **jangan** ditaruh di `cloudflareZoneId`).
- `dnsRecordId` varchar null (id record `A <label>` yang dibuat), `sslRuleId` varchar null (id rule SSL per host).
Untuk SUBDOMAIN, `cloudflareZoneId` dan `nameServers` tetap **null**.

### 2. DTO & validasi — `CreateDomainDto`, `registerDomain()`
- Field baru: `ampMode?: 'STANDALONE' | 'SUBDOMAIN'`, `parentDomain?: string`, `subdomainLabel?: string`.
- SUBDOMAIN:
  - parent dicari by `domainName`; wajib `companyCode` sama, `type = 'STANDARD'`, `provisioningStatus = 'completed'`, `status = 'active'`, punya `cloudflareZoneId`.
  - label sesuai regex kontrak, bukan `www`; `domainName = ${label}.${parent}` (lowercase), ≤ 253.
  - aturan 1 AMP per company tetap (cek `type: 'AMP'` apa pun modenya).
  - `assertDomainAllowed` (blocklist) untuk host penuh.
  - default `ampRedirectTo = parent`, default `ampCanonical = domainName` (host AMP itu sendiri) bila kosong; `ampRedirectTo` tidak boleh sama dengan `domainName`.
  - Cek dulu di zone parent: kalau sudah ada record A/AAAA/CNAME dengan nama itu yang **bukan** milik AMP → 400 (jangan menimpa record usersite).
- STANDALONE: alur & validasi sekarang tidak berubah (default `ampMode = 'STANDALONE'`).

### 3. Provisioning — `domain-provisioning.processor.ts`
Cabang baru untuk `ampMode === 'SUBDOMAIN'` (resumable seperti sekarang, simpan langkah di `provisioningStep`):
1. **Lewati** `createZone`, `setSslMode`, `setPseudoIpv4` (itu setelan zone money site, jangan diubah).
2. `redirect-exclude`: bila parent punya redirect (tabel `redirects`, `sourceDomain = parent`), sinkronkan rule redirect-nya
   supaya mengecualikan host AMP (no. 5a). Langkah ini **sebelum** `dns`, supaya host AMP tidak sempat ter-redirect.
3. `ssl-rule`: buat Configuration Rule `http_config_settings` dengan expression `(http.host eq "<domainName>")` → `set_config { ssl: "flexible" }`.
   **Tambahkan rule** ke entrypoint ruleset yang sudah ada (`POST /zones/{zone}/rulesets/{rulesetId}/rules`; buat entrypoint hanya bila belum ada).
   **Jangan `PUT` entrypoint** — itu menimpa semua rule yang sudah dipasang agent. Beri `ref` deterministik
   (mis. `amp-ssl-<domainName>`), cari dulu rule dengan `ref` itu sebelum POST (idempotent saat retry). Simpan `sslRuleId`.
   Langkah ini **sebelum** `dns`, supaya tidak ada jeda 525 bila zone money site memakai Full/Strict.
4. `dns`: `ensureDNSRecord(parentZoneId, parentDomain, 'A', label, AMP_INGRESS_IP, proxied=true)` (selalu `true`, jangan
   diturunkan dari `isPrivateIp`); simpan `dnsRecordId`.
5. `amp`: `ampService.registerDomain(companyCode, domainName, parentZoneId, { redirectTo, canonical })` (sama seperti sekarang).
   `409 parent_domain_taken` dari AMP engine → `UnrecoverableError` (jangan di-retry), seperti `DnsRecordConflictError`.
6. `status` mengikuti status zone parent (`active`), `provisioningStatus = 'completed'`. Tidak ada langkah nameserver.

### 4. Update — `updateAmpConfig()`
Saat ini sinkron ke AMP hanya `if (domain.cloudflareZoneId)` → untuk SUBDOMAIN pakai zone efektif (`parentZoneId`), supaya
perubahan redirect/canonical tetap terkirim ke AMP.

### 5. Hapus & fungsi zone lain — `deleteDomain()` dan kawan-kawan
- **AMP SUBDOMAIN:** `ampService.deregister` → hapus `dnsRecordId` (record saja) → hapus `sslRuleId` (rule saja) → sinkronkan
  ulang redirect parent (keluarkan host AMP dari pengecualian, no. 5a) → hapus row. **Tidak pernah `deleteZone`.**
  Error Cloudflare `404` (sudah tidak ada) = sukses; error lain → batalkan, row tetap ada, aman diulang.
- **STANDARD yang punya anak AMP SUBDOMAIN → hapus berantai (kontrak no. 10)**, urutan wajib:
  1. Dalam transaksi, kunci row parent (`SELECT … FOR UPDATE`). `registerDomain` SUBDOMAIN juga mengunci row parent yang
     sama saat insert anak, supaya hapus parent dan buat anak tidak bisa balapan.
  2. Anak `queued`/`processing` → `409 amp_subdomain_provisioning`.
  3. Deregister anak dari AMP engine. **Wajib berhasil** (`2xx`/`404`); gagal → `502 amp_deregister_failed`, tidak ada yang
     dihapus. Untuk jalur ini `ampService.deleteDomain` harus melempar error, bukan mengembalikan `ok:false` seperti sekarang.
  4. Hapus row anak → `deleteZone(parent.cloudflareZoneId)` → hapus row parent. Record + rule AMP ikut hilang bersama zone,
     tidak perlu dihapus satu per satu.
  5. Audit log `DOMAIN_DELETED` untuk anak, `detail: { reason: 'parent_deleted', parentDomain }`.
  Semua pengecekan dan deregister terjadi **sebelum** `deleteZone`. FK `ON DELETE RESTRICT` tetap dipasang sebagai jaring
  pengaman (parent tidak bisa terhapus tanpa anak dibereskan dulu).
- `syncDomainStatus` / `syncPendingDomains`: SUBDOMAIN ikut status parent (jangan query zone null).
- `purgeCache`: SUBDOMAIN → purge per URL host itu saja (`https://<host>/`, `/robots.txt`, `/sitemap.xml`), **bukan** `purge_everything` zone money site.
- `setProtection` (security level = setelan zone): untuk SUBDOMAIN tolak `400` ("ikut setelan domain induk") supaya tidak mengubah money site.
- `retryProvisioning`: harus mengikuti cabang SUBDOMAIN.
- Endpoint/fitur subdomain record generik (kalau ada) **tidak boleh** mengubah/menghapus record milik AMP (`dnsRecordId`).

### 5a. Redirect — `redirect.service.ts` + `cloudflare.service.ts`
Tujuan: tenant redirect `merek.com` → `baru.com`, **`amp.merek.com` tidak ikut ter-redirect** (kontrak no. 11).
- Expression redirect dihitung dari anak AMP SUBDOMAIN milik `sourceDomain`:
  - tidak ada anak → `true` (perilaku sekarang, tidak berubah);
  - ada anak → `not (http.host in {"amp.merek.com"})`.
- Satu fungsi `syncRedirectExpression(parentDomain)` dipanggil dari: `addRedirect`, provisioning langkah `redirect-exclude`,
  dan hapus AMP SUBDOMAIN.
- Ubah cara kerja rule redirect: **tambah** rule ke entrypoint (`POST …/rulesets/{id}/rules`, buat entrypoint bila belum ada),
  **update** lewat `PATCH …/rulesets/{id}/rules/{ruleId}`, **hapus** lewat `DELETE …/rules/{ruleId}`. Tidak ada lagi `PUT`
  entrypoint (sekarang menimpa redirect rule lain milik tenant).
- Redirect lama yang masih berupa Page Rule (fallback di `deleteRedirectRule`): bila parent-nya mendapat AMP SUBDOMAIN, migrasikan
  ke dynamic rule lewat jalur di atas, atau tolak pembuatan AMP dengan `400` berisi pesan jelas.
- `addRedirect` dengan `sourceDomain` = host AMP SUBDOMAIN → `400` (zone-nya milik money site; redirect di sana akan mengenai
  seluruh money site).

### 6. Respons API
`GET /domains`, `GET /domains/:name`, `POST /domains` menambahkan `ampMode` dan `parentDomain` (nama domain parent).
Perbarui `openapi.yaml` / `openapi-prod.yaml`.

### 7. Test (`*.spec.ts`)
- Create SUBDOMAIN: sukses (default redirect = parent, canonical = host), label `www`/invalid/bertingkat ditolak, parent milik company lain ditolak, parent belum aktif ditolak, sudah punya AMP ditolak, record dengan nama sama sudah ada ditolak.
- Provisioning SUBDOMAIN: **tidak** memanggil `createZone`/`setSslMode`/`setPseudoIpv4`; memanggil `ensureDNSRecord` di zone parent dengan `proxied=true`; rule SSL ditambahkan tanpa `PUT` entrypoint; `ampService.registerDomain` dipanggil dengan host penuh; resume setelah gagal di tiap langkah.
- **Delete SUBDOMAIN tidak memanggil `deleteZone`** (test regresi wajib); hanya record + rule + AMP deregister.
- Delete STANDARD dengan anak AMP: deregister AMP dipanggil, kedua row terhapus, `deleteZone` dipanggil **sekali** untuk zone
  parent; urutan deregister sebelum `deleteZone`. Anak `processing` → 409. Deregister gagal → 502 dan **tidak ada** yang
  terhapus (`deleteZone` tidak dipanggil, kedua row masih ada).
- Redirect: `merek.com` → `baru.com` saat `amp.merek.com` ada → expression mengecualikan host AMP; AMP dibuat setelah redirect
  ada → rule di-PATCH sebelum `ensureDNSRecord`; AMP dihapus → expression kembali `true`; tidak ada pemanggilan `PUT`
  entrypoint; `sourceDomain` = host AMP → 400.
- purge/protection/sync untuk SUBDOMAIN seperti no. 5. STANDALONE: semua test lama tetap hijau.

### 8. Rilis
Staging dulu, setelah AMP engine versi yang menerima subdomain sudah jalan (kalau belum, langkah `amp` gagal 422 dan job
bisa di-retry). Jalankan migration, uji ujung-ke-ujung: buat AMP `amp.<usersite-staging>`, cek record proxied + rule SSL di
Cloudflare, `https://amp.<usersite-staging>/` tersaji setelah publish, hapus AMP → **zone usersite masih ada dan situs utama tetap jalan**.
Lalu: pasang redirect usersite → domain lain → usersite ter-redirect, `https://amp.<usersite-staging>/` **tetap** tersaji AMP.
Terakhir: hapus usersite yang punya AMP → AMP ikut terhapus (AMP engine tidak lagi menyajikan host itu), zone usersite terhapus.

## Definition of done
- Migration + kode + test hijau; STANDALONE tidak berubah perilakunya.
- Tidak ada jalur kode yang bisa memanggil `deleteZone` / `setSslMode` / `purge_everything` / security level pada zone money site karena AMP SUBDOMAIN.
  Pengecualian satu-satunya: `deleteZone` saat tenant menghapus **money site itu sendiri** (hapus berantai, kontrak no. 10).
- Redirect money site tidak pernah mengenai host AMP SUBDOMAIN; tidak ada lagi `PUT` entrypoint redirect.
