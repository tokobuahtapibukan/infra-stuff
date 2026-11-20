# Prompt — AMP engine (repo `tokobuah/AMP`): domain AMP sebagai subdomain money site

> **Status 2026-11-21:** sudah diimplementasikan dan berjalan di staging (AMP commit `eec8508`), termasuk perbaikan hasil
> code review: public suffix list (`tldts`), kunci per keluarga domain, pengecekan host aktif, `AMP_DOMAIN` dicadangkan.
> Production menunggu Domain Engine & admin panel. Konteks lengkap: `AMP_PAGE_SERVICE_AND_TENANT_REGISTRY_RUNBOOK.md` §2.5.

Kamu bekerja di repo AMP engine (TypeScript strict di Node ≥24, Express, Zod, `node:test`). **Baca `CLAUDE.md` dan `plan.md`
dulu** dan patuhi aturan repo: catat keputusan di Decision log `plan.md` sebelum implementasi, **tanpa komentar di kode**
(`npm run lint:comments`), semua input di-parse Zod, `npm run ci` wajib hijau sebelum selesai.

## Latar belakang
Sekarang custom domain AMP yang didaftarkan Domain Engine lewat `PUT /internal/domains/:code` **wajib root domain**
(`src/schema/common.ts` → `rootDomain` / `isRootDomain`; D34). Request lapangan: AMP juga bisa ditempatkan sebagai
**subdomain dari money site agent**, misalnya `amp.merek.com`. Mode lama (root/STANDALONE) tetap harus berjalan.

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

## Yang harus kamu kerjakan (AMP engine)

### 1. `plan.md` — Decision **D50** (tulis dulu)
Isi: AMP custom domain boleh root domain (STANDALONE) atau subdomain satu tingkat dari registrable domain (SUBDOMAIN);
`www` dan subdomain bertingkat ditolak; pengaman lintas tenant `parent_domain_taken`; default canonical untuk SUBDOMAIN =
host itu sendiri bila Domain Engine tidak mengirim `canonical`; serve/build/redirect tidak berubah. Refines D34 dan D39.

### 2. Validasi hostname — `src/schema/common.ts`
- Tambah `ampHostname` (Zod, trim + lowercase) yang menerima:
  - root domain (aturan `isRootDomain` yang sekarang), **atau**
  - tepat satu label + root domain, dengan label sesuai regex kontrak dan **bukan `www`**.
- Tolak: `www.*`, `a.b.merek.com`, wildcard `*`, IP, port, path, skema. Punycode (`xn--`) tetap diterima.
- Helper murni yang bisa dites, misalnya `splitAmpHost(host) → { kind: "root" | "subdomain", parentDomain: string | null }`.
- `rootDomain` lama boleh tetap ada kalau masih dipakai di tempat lain.

### 3. `src/routes/internal.ts` — `PUT /domains/:code`
- `RegisterDomainBody.domain` memakai `ampHostname`. Pesan 422 diperbarui ("root domain atau satu tingkat subdomain").
- **Pengaman lintas tenant** sebelum `claimHostname`:
  - Untuk SUBDOMAIN: bila `hosts/<parentDomain>` ada dan pemiliknya company lain → `409 parent_domain_taken`.
  - Untuk root: bila ada `hosts/<label>.<root>` milik company lain → `409 parent_domain_taken`
    (pakai `storage.list("hosts/")` lalu filter sufiks `.<root>`; jumlah host kecil).
- Simpan di `tenants/<code>/domain.json` field baru `kind` (`"root"` | `"subdomain"`) dan `parentDomain` (string | null).
  Perbarui interface `DomainDoc` di `src/lib/build.ts` (field opsional, supaya `domain.json` lama tetap terbaca).
- **Canonical**: AMP tidak mengarang default; nilai `canonical` dari body disimpan apa adanya (Domain Engine mengirim host AMP
  sebagai default untuk SUBDOMAIN). Urutan prioritas D39 tidak berubah.
- Respons 200 menambahkan `kind` dan `parentDomain`. Re-render otomatis setelah simpan (D39) tetap jalan.

### 4. Yang **tidak** boleh berubah
- `src/routes/serve.ts` (lookup berdasarkan `Host`, 301 dari host lama ke host baru, redirect subpath ke `redirectTo`).
- Build/render, payload admin `{ enabled, ampDomain, redirectTo, canonical }`, aturan `ampDomain` = `<label>.{AMP_DOMAIN}` (D38),
  tenant-registry (D49), storage layout selain dua field baru di `domain.json`.
- Domain root yang sudah terdaftar harus tetap bekerja tanpa migrasi.

### 5. Test (`node:test`)
- `ampHostname` / `splitAmpHost`: diterima `merek.com`, `merek.co.id`, `amp.merek.com`, `m.merek.co.id`, `xn--fiqs8s.com`,
  `amp.xn--fiqs8s.com`; ditolak `www.merek.com`, `a.b.merek.com`, `*.merek.com`, `amp.merek.com:8080`, `https://amp.merek.com`,
  `-amp.merek.com`, `amp-.merek.com`, label 64 karakter, `localhost`.
- `PUT /internal/domains/:code`: SUBDOMAIN sukses → `domain.json` berisi `kind: "subdomain"`, `parentDomain`, canonical default;
  canonical eksplisit tetap dipakai; `409 parent_domain_taken` dua arah (anak milik company lain / parent milik company lain);
  `409 hostname_taken` tetap; root lama tidak berubah; `domain.json` lama tanpa `kind` tetap terbaca.
- Serve: host `amp.merek.com` terdaftar → 200; host lama company → 301 ke host baru (regresi).

### 6. Dokumentasi
- `docs/domains.md`: tambah mode SUBDOMAIN, contoh request/response, error `parent_domain_taken`, catatan DNS proxied + SSL rule.
- `docs/architecture.md` bagian internal routes, `docs/tenant-registry.md` tidak perlu diubah.

### 7. Rilis
- PR → `main` (otomatis ke staging). Uji di staging: `PUT` subdomain dengan `X-Internal-Key` dari dalam cluster, lalu
  `curl -H "Host: amp.<domain-staging>"` ke `amp-serve`.
- Production lewat tag baru (`vX.Y.Z`) seperti biasa; tidak ada env/config baru.

### 8. Setelah Admin panel berhenti memanggil `/internal` langsung
Minta ops **merotasi `INTERNAL_KEY`** (AMP `amp-secrets` + `AMP_INTERNAL_KEY` di `domain-management-secrets`) dan
menghapus `AMP_INTERNAL_KEY` dari env admin panel. Sampai saat itu, kunci ini dipegang panel (risiko: siapa pun yang
memegangnya bisa mendaftarkan domain untuk company mana pun).

## Definition of done
- `npm run ci` hijau, D50 tercatat, docs diperbarui.
- Root domain lama dan subdomain baru sama-sama bisa didaftarkan, disajikan, dan dihapus di staging.
