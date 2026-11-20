# Prompt — Domain Management Engine (repo `tokobuah/domain-management`): subdomain usersite & redirect fleksibel

Kamu bekerja di Domain Management Engine (NestJS + TypeORM + BullMQ, Cloudflare API per company memakai kredensial di
`company_configs`). Ikuti konvensi repo: migration TypeORM, DTO class-validator, test `*.spec.ts` (Jest, fake Cloudflare di
`test/fake-cloudflare.ts`). Baca dulu fitur AMP SUBDOMAIN yang sudah ada (PR #1), karena fitur ini memakai pola yang sama:
`src/domain/domain.service.ts` (create SUBDOMAIN, hapus berantai dengan row lock), `src/provisioning/domain-provisioning.processor.ts`
(langkah resumable), `src/redirect/redirect-rule-sync.service.ts` (pengecualian host dari redirect parent), dan
`src/cloudflare/cloudflare.service.ts` (`upsertPhaseRule`, `deletePhaseRule`, `buildRedirectRule`, `resolveRedirectRuleId`).

## Latar belakang
- Tombol "+ Subdomain" di admin panel saat ini **hanya tampilan**: data subdomain disimpan di state React, tidak ada API,
  tidak ada record di Cloudflare, dan hilang saat halaman di-refresh.
- Redirect sekarang hanya bisa dibuat untuk root domain, `targetDomain` bebas diisi apa saja, dan `addRedirect`
  **tidak memeriksa** bahwa `sourceDomain` milik `companyCode` yang dikirim. Ini celah lintas tenant yang ikut ditutup di sini.

## Kontrak bersama — Subdomain usersite & redirect fleksibel (identik di semua prompt — jangan diubah sepihak)

**Fitur:** tenant bisa membuat **subdomain** di bawah money site (domain `STANDARD`) miliknya, lalu mengatur redirect
antar host miliknya secara bebas (root ↔ subdomain, lintas money site). Fitur ini melengkapi AMP SUBDOMAIN
(`prompts/amp-subdomain/`) dan tidak mengubah kontraknya.

**Istilah**
- *Money site / usersite* = domain `STANDARD` (root domain dengan zone Cloudflare sendiri).
- *Subdomain usersite* = `<label>.<money site>`, misalnya `abc.x.com`. Di Domain Engine disimpan sebagai row `domains`
  dengan `type = 'SUBDOMAIN'`.
- *Host tenant* = semua host aktif milik satu company: root `STANDARD`, subdomain usersite, dan host AMP (mode apa pun).
- *Redirect induk* = redirect milik money site (`x.com → …`). Rule ini berlaku untuk seluruh zone, kecuali host yang dikecualikan.

**Aturan subdomain usersite**
1. Tepat **satu tingkat**: `label.parent`. Parent = registrable domain menurut PSL resmi (`tldts` 7.4.19, sama dengan AMP).
   Alasannya: Universal SSL Cloudflare hanya menanggung `*.x.com`.
2. Label memakai regex `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`. Bukan label yang sedang dipakai host AMP, dan belum
   ada record A/AAAA/CNAME dengan nama itu di zone parent, **kecuali** CNAME ke parent: record itu diadopsi.
   **`www` boleh.** Setiap money site sudah punya `CNAME www → apex` sejak provisioning, jadi subdomain `www` mengadopsi
   record itu dan menambahkan pengaturan (ikut induk / standalone / redirect sendiri). Untuk AMP, `www` tetap ditolak.
3. Parent wajib `STANDARD` milik **company yang sama**, provisioning `completed`, status `active`.
4. DNS: `CNAME <label> → <parent>`, dengan nilai proxied sama dengan record apex parent. IP otomatis sama dengan money site,
   dan ikut berubah saat IP company diganti (`dns-ip`). Tidak ada record `A` terpisah yang perlu disinkronkan.
5. Setiap subdomain punya setelan **`followParentRedirect`** (default `true`):
   - `true` → saat parent di-redirect, subdomain ini ikut ter-redirect (perilaku sekarang).
   - `false` → **standalone**: subdomain ini tidak ikut redirect parent dan tetap tersaji.
   - Bila subdomain punya redirect sendiri, redirect sendiri itulah yang berlaku. `followParentRedirect` diabaikan.
6. Menghapus subdomain hanya menghapus record CNAME dan rule redirect miliknya. Zone parent tidak pernah dihapus.
   Pengecualian: menghapus subdomain `www` hanya menghapus pengaturannya. Record `CNAME www` milik money site tetap ada.
7. Menghapus money site ikut menghapus semua subdomain usersite-nya (sama seperti AMP SUBDOMAIN), dalam satu transaksi
   dengan row lock.
8. Host AMP **tidak bisa** dibuat, diubah, atau dihapus lewat fitur subdomain, dan tidak bisa menjadi sumber redirect.
   Host AMP **boleh** menjadi target redirect.

**Aturan redirect**
9. Sumber redirect: root `STANDARD` atau subdomain usersite milik company itu.
   Target redirect: **host tenant yang aktif** (root, subdomain, atau AMP) milik company yang sama, dan bukan dirinya sendiri.
   **Tidak ada isian bebas**: target di luar daftar → `400`.
10. Redirect root (`x.com`) = satu rule untuk seluruh zone, dengan expression
    `not (http.host in {<host yang dikecualikan>})`. Host yang dikecualikan adalah semua host di zone itu yang
    **tidak boleh** ikut redirect parent:
    host AMP + subdomain dengan `followParentRedirect = false` + subdomain yang punya redirect sendiri.
    Daftar ini dihitung ulang dan disinkronkan setiap kali salah satu unsurnya berubah.
11. Redirect subdomain (`abc.x.com`) = satu rule per host dengan expression `(http.host eq "abc.x.com")`, di zone parent.
12. Semua redirect: 301 ke `https://<target>` + path, dengan query string dipertahankan.
    Rule selalu ditambah, diubah, atau dihapus **per rule**, tidak pernah dengan `PUT` entrypoint.
13. **Tidak boleh ada loop** pada graf redirect *efektif*. Target efektif sebuah host:
    redirect sendiri → targetnya; kalau tidak ada, dan `followParentRedirect` true serta parent di-redirect → target parent;
    selain itu, tidak ada. Pengecekan dijalankan setiap kali redirect dibuat atau diubah, dan setiap kali
    `followParentRedirect` diubah. Rantai (`a → b → c`) diperbolehkan; loop ditolak dengan `400`.
14. **Menghapus host yang sedang menjadi target redirect ditolak** dengan `409 domain_is_redirect_target`, beserta daftar sumbernya.
    Tenant harus melepas redirect tersebut dulu. Ini berlaku untuk subdomain, root, maupun AMP.
    Untuk hapus berantai money site, yang diperiksa adalah seluruh host yang ikut terhapus. Redirect yang target dan
    sumbernya sama-sama berada di dalam set yang terhapus tidak memblokir.

**Kontrak API Domain Engine**
- `POST /domains` untuk subdomain usersite:
  `{ "type": "SUBDOMAIN", "companyCode": "...", "parentDomain": "x.com", "subdomainLabel": "abc", "followParentRedirect"?: true }`
  → `201`, `domainName` = `abc.x.com`. Validasi gagal → `400` dengan pesan jelas.
- `PATCH /domains/:name/subdomain-settings` `{ "followParentRedirect": boolean }` → `200`. Hanya untuk `type = 'SUBDOMAIN'`.
  Rule redirect parent disinkronkan, dan loop dicek ulang.
- `GET /domains` / `GET /domains/:name`: row subdomain berisi `type: "SUBDOMAIN"`, `parentDomain`, dan `followParentRedirect`.
- `DELETE /domains/:name`:
  - `409 domain_is_redirect_target`: `{ code, message, redirectSources: ["abc.x.com", ...] }`.
  - Money site: subdomain usersite dan AMP-nya ikut terhapus. Redirect yang sumbernya ada di set terhapus juga ikut dihapus.
- `GET /domains/:name/redirect-sources` → `{ redirectSources: [...] }` (read-only), supaya panel bisa memberi peringatan
  sebelum tombol hapus ditekan.
- `POST /redirects` `{ sourceDomain, targetDomain, companyCode }`: sumber dan target harus host aktif milik `companyCode`,
  target bukan sumber, dan tidak membentuk loop. `sourceDomain` boleh subdomain usersite. Host AMP sebagai sumber → `400`.
- `GET /redirect-targets?companyCode=` → daftar host aktif tenant (root, subdomain, AMP), dipakai untuk dropdown target.
- `DELETE /redirects/:sourceDomain` (sudah ada): menghapus rule milik sumber itu, lalu menyinkronkan pengecualian di parent.

**Urutan rilis:** Domain Engine (endpoint baru + `openapi.yaml`, termasuk deploy Cloud Endpoints) → Admin panel.
AMP engine tidak berubah. **Staging dulu**, production setelah lolos uji ujung-ke-ujung.

## Yang harus kamu kerjakan

### 1. Data
- Tipe domain bertambah: `type: 'STANDARD' | 'AMP' | 'SUBDOMAIN'` (entity, DTO enum, Swagger).
- Subdomain usersite memakai kolom yang sudah ada: `parentDomainId` (FK RESTRICT), `parentDomain`, `parentZoneId`, `dnsRecordId`.
  `cloudflareZoneId` dan `nameServers` tetap null, dan `ampMode` null.
- Migration: tambah kolom `followParentRedirect boolean NOT NULL DEFAULT true`. Kolom ini hanya bermakna untuk `SUBDOMAIN`.
  Default `true` aman untuk row lama.
- Pertimbangkan sekalian partial unique index `UNIQUE("companyCode") WHERE type='AMP'`. Aturan 1 AMP per company saat ini
  masih cek-lalu-insert. **Cek data duplikat dulu** sebelum index dibuat.

### 2. Audit tempat yang berasumsi "`type !== 'AMP'` berarti STANDARD"
Saat ini ada di `domain.service.ts` (`deleteDomain`, `updateAmpConfig`), `company.service.ts` (`updateCompanyDnsIp`),
`provisioning.processor.ts` (`isAmp`). Semua harus membedakan `SUBDOMAIN` secara eksplisit:
- `deleteDomain`: `SUBDOMAIN` punya jalurnya sendiri (no. 5). **Jangan** masuk ke `deleteMoneySite`.
- `updateCompanyDnsIp`: lewati `SUBDOMAIN` (record-nya CNAME ke parent, jadi ikut otomatis).
- `syncDomainStatus` / `syncPendingDomains`: status mengikuti zone parent (pola AMP SUBDOMAIN).
- `setProtection`: tolak `400` (setelan zone parent). `purgeCache`: purge per URL host itu saja.
- Processor: cabang tersendiri (no. 4). Jalur `provisionOwnZone` harus menolak `SUBDOMAIN` (defence in depth).

### 3. Create — `POST /domains` `type: 'SUBDOMAIN'`
- Validasi sesuai kontrak no. 1–3. Parent dicari berdasarkan nama, lalu dicek company, tipe, status, dan PSL.
  Domain milik company lain diberi pesan yang sama dengan domain yang tidak dikenal.
- Pre-check di zone parent: kalau sudah ada record A/AAAA/CNAME bernama itu → `400`.
  Nama yang sudah dipakai host AMP otomatis ditolak oleh UNIQUE `domainName`; beri pesan yang jelas.
- Insert dilakukan di bawah row lock parent (sama seperti AMP SUBDOMAIN), lalu enqueue provisioning.

### 4. Provisioning `SUBDOMAIN` (resumable, simpan `provisioningStep`)
Urutan `redirect-sync` → `dns`:
1. `redirect-sync`: kalau `followParentRedirect = false` dan parent punya redirect, sinkronkan pengecualian di rule parent
   **sebelum** record dibuat, supaya host baru tidak sempat ter-redirect.
2. `dns`: `ensureDNSRecord(parentZoneId, parent, 'CNAME', label, parent, proxied)`. Nilai `proxied` = `!isPrivateIp(company.dnsIp)`,
   sama dengan apex. Simpan `dnsRecordId`.
3. Tidak ada `createZone`, `setSslMode`, `setPseudoIpv4`, maupun registrasi AMP. Status = status zone parent.

### 5. Delete
- **Subdomain:** cek target redirect (no. 7) → hapus rule redirect miliknya (kalau ada) dan row `redirects`-nya →
  hapus `dnsRecordId` (404 = sukses) → sinkronkan pengecualian parent (keluarkan host ini) → hapus row.
  Tidak pernah `deleteZone`. Ditolak `409` kalau masih `queued`/`processing`.
- **Money site (`deleteMoneySite`):** anak sekarang bisa AMP **atau** SUBDOMAIN.
  - Deregister AMP hanya dilakukan untuk anak AMP.
  - Cek target redirect atas **seluruh set** (root + semua anak) sebelum menghapus apa pun.
  - Hapus row `redirects` yang sumbernya ada di set itu. Zone ikut terhapus, jadi rule-nya ikut hilang.
- **AMP dan root lain:** tambahkan cek target redirect (no. 7) sebelum hapus.

### 6. Redirect — `redirect.service.ts`, `redirect-rule-sync.service.ts`, `cloudflare.service.ts`
- `addRedirect`:
  - Sumber dan target dicari di tabel `domains`, dan **keduanya wajib milik `dto.companyCode`** (tutup celah lintas tenant).
  - Target wajib aktif (`provisioningStatus = 'completed'`, status `active`) dan bukan sumber itu sendiri.
  - Sumber root → rule untuk seluruh zone (pola sekarang). Sumber subdomain → rule per host `(http.host eq "<host>")` di
    `parentZoneId`, dengan `ref` deterministik. Tambahkan `buildHostRedirectRule` di samping `buildRedirectRule`.
  - Setelah redirect subdomain dibuat atau dihapus → sinkronkan pengecualian di rule parent.
- Ganti `excludedHostsFor(parent)` menjadi: host AMP + subdomain dengan `followParentRedirect = false` + subdomain yang
  punya row `redirects` sebagai sumber.
- `PATCH /domains/:name/subdomain-settings`: simpan nilai baru → cek loop (no. 8) → sinkronkan pengecualian parent.
  Kalau sinkronisasi ke Cloudflare gagal, kembalikan nilai lama (jangan biarkan DB dan Cloudflare berbeda).
- Batas jumlah rule per zone (tergantung plan Cloudflare): error Cloudflare karena batas rule harus diterjemahkan menjadi
  `409` dengan pesan yang jelas, bukan `502` generik.

### 7. Cek target redirect (`409 domain_is_redirect_target`)
- `redirectSourcesOf(hosts[])` = row `redirects` dengan `targetDomain` ∈ `hosts` dan `sourceDomain` ∉ set yang sedang dihapus.
  Ada isinya → `409 { code: 'domain_is_redirect_target', message, redirectSources }`.
- Endpoint read-only `GET /domains/:name/redirect-sources` memakai fungsi yang sama.

### 8. Cek loop (ganti `introducesLoop`)
- Bangun graf target efektif (kontrak no. 13) dari seluruh host company, lalu simulasikan perubahan yang diminta.
  Kalau ada siklus → `400` dengan jalur loop-nya (`a → b → a`).
- Jalankan di: `addRedirect`, `PATCH subdomain-settings`, dan saat redirect root dibuat (karena subdomain dengan
  `followParentRedirect = true` ikut ter-redirect).

### 9. API & dokumentasi
- Endpoint baru: `PATCH /domains/{domainName}/subdomain-settings`, `GET /domains/{domainName}/redirect-sources`,
  `GET /redirect-targets`. Tambahkan ke **`openapi.yaml` dan `openapi-prod.yaml`**. ESP akan menjawab 404 untuk route yang
  tidak ada di spec, jadi rilis wajib menyertakan `gcloud endpoints services deploy`.
- Response `GET /domains` sudah otomatis membawa `followParentRedirect` karena entity dikembalikan langsung.

### 10. Test (`*.spec.ts`)
- **Create:** sukses dengan CNAME ke parent (proxied mengikuti apex); `www` diterima dengan mengadopsi record yang ada
  (dan dihapus tanpa menghapus record-nya); ditolak untuk label AMP, label bertingkat,
  record yang sudah ada, parent milik company lain, dan parent yang belum aktif.
- **Provisioning:** tidak memanggil `createZone`, `setSslMode`, maupun `PUT`; dengan `followParentRedirect = false`,
  pengecualian dipasang sebelum record dibuat; resume per langkah.
- **Redirect:**
  - `abc.x.com → xyz.y.com` lintas zone membuat rule per host di zone `x.com`, dan `abc.x.com` masuk pengecualian rule `x.com`.
  - Target milik company lain atau target bebas → `400`. Sumber milik company lain → `400`/`403`.
  - Loop `a → b → a`, termasuk lewat parent (`abc.x.com → y.com` sementara `y.com → x.com` dan abc ikut parent) → `400`.
- **Standalone:** `x.com → y.com` dengan `aaa.x.com` `followParentRedirect = false` menghasilkan rule `x.com` dengan
  `not (http.host in {"aaa.x.com"})`; toggle kembali ke `true` mengeluarkan host itu dari pengecualian.
- **Delete:**
  - Subdomain yang menjadi target → `409` dengan `redirectSources`.
  - Subdomain biasa → hapus CNAME dan rule-nya, sinkronkan parent, dan **tidak** memanggil `deleteZone`.
  - Money site dengan anak AMP + SUBDOMAIN: deregister hanya untuk AMP, row `redirects` sumber ikut terhapus, `deleteZone` sekali.
  - Money site yang salah satu anaknya menjadi target dari luar set → `409` dan tidak ada yang terhapus.
- `updateCompanyDnsIp` tidak menyentuh `SUBDOMAIN`. Semua test AMP SUBDOMAIN yang lama tetap hijau.

### 11. Rilis
- Staging dulu: build image, retag `latest`, rollout, deploy Cloud Endpoints (`openapi.yaml`), lalu restart pod.
  Migration berjalan otomatis saat boot.
- **Cek origin usersite sebelum uji:** record CNAME membuat `abc.x.com` diteruskan ke origin money site dengan
  `Host: abc.x.com`. Pastikan origin usersite (ingress/aplikasi di `dnsIp` company) mau melayani Host itu.
  Kalau origin hanya menerima host tertentu, subdomain akan 404 atau 421 walaupun DNS dan redirect-nya benar.
  Ini perlu diverifikasi, bukan diasumsikan.
- Uji ujung-ke-ujung:
  1. Buat `abc.x.com` (ikut parent) dan `aaa.x.com` (standalone).
  2. Redirect `x.com → y.com`. Hasil yang diharapkan: `abc.x.com` ter-redirect, `aaa.x.com` tetap tersaji.
  3. Buat `xyz.y.com`, lalu redirect `abc.x.com → xyz.y.com`. Hasil: `abc.x.com` 301 ke `xyz.y.com` dengan path dan query.
  4. Hapus `xyz.y.com` → `409`. Lepas redirect-nya, lalu hapus lagi → sukses.
  5. Cek di Cloudflare bahwa rule redirect milik tenant (yang tidak dibuat engine) tetap utuh.

## Definition of done
- Migration + kode + test hijau; perilaku AMP SUBDOMAIN dan STANDALONE tidak berubah.
- Tidak ada jalur kode yang memanggil `deleteZone`, `setSslMode`, `purge_everything`, security level, atau `PUT` entrypoint
  pada zone money site karena operasi subdomain atau redirect host.
- Redirect hanya bisa dibuat antar host aktif milik company yang sama.
