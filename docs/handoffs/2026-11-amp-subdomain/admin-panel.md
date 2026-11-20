# Prompt — Admin panel (repo `tokobuah/admin-panel`, Next.js): pilih domain AMP sebagai subdomain money site

Kamu bekerja di admin panel (Next.js App Router, API route di `src/app/api/**` yang mem-proxy ke Domain Engine lewat
`fetchEngine`, i18n di `src/lib/i18n.ts`, test vitest). Ikuti konvensi repo.

## Latar belakang
Sekarang domain AMP di panel **wajib root domain baru** (stand-alone):
- `src/app/(dashboard)/domains/domains-client.tsx`: saat type `AMP`, `isRootDomain()` menolak subdomain; Redirect To **dan**
  Canonical diisi otomatis dengan usersite aktif pertama.
- `src/app/(dashboard)/amp/amp-client.tsx` → `validateForm()`: menolak "subdomain dari domain yang ada di Domain Management"
  dan domain yang sudah terdaftar di Domain Management.
- `src/app/api/amp/domain/route.ts`: menolak non-root, `ampCanonical` default = `ampRedirectTo`.
Request lapangan: dari **daftar domain aktif (usersite/money site) milik agent**, admin bisa memilih salah satu untuk dijadikan
AMP **sebagai subdomain** (contoh `amp.merek.com`). Opsi domain AMP baru stand-alone tetap ada.

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

## Yang harus kamu kerjakan

### 1. UI pembuatan domain AMP (Domain Management, type AMP)
- Pilihan mode (radio/segmented):
  - **"Domain baru (stand-alone)"** — form sekarang, tidak berubah.
  - **"Subdomain dari money site"** — baru:
    - Dropdown **Money site**: hanya domain `STANDARD` milik company yang `provisioning completed` + `status active` (dari `GET /domains`).
      Kosong → tampilkan info "Belum ada money site aktif" dan nonaktifkan mode ini.
    - Input **Subdomain** (label), default `amp`, validasi live sesuai kontrak (regex, bukan `www`, tanpa titik).
    - **Preview** hostname final: `amp.merek.com`.
    - Teks bantuan (ID/EN): "Subdomain dibuat di zone Cloudflare money site, aktif dalam ±1 menit tanpa ganti nameserver.
      Bila money site dihapus, AMP subdomain ini ikut terhapus. Redirect money site tidak mempengaruhi AMP."
- Default saat mode Subdomain:
  - **Redirect To** = money site yang dipilih (bisa diubah).
  - **Canonical** = **hostname AMP itu sendiri** (`amp.merek.com`), bukan money site — supaya halaman AMP terindeks Google.
- Batas 1 AMP per company tetap (pesan sekarang dipakai untuk kedua mode).

### 2. Halaman AMP — `amp-client.tsx` → `validateForm()`
- Hapus/ubah aturan "Tidak dapat menggunakan subdomain dari domain yang ada di Domain Management" dan "domain yang sudah
  terdaftar di Domain Management" **untuk domain AMP milik company sendiri** (mode SUBDOMAIN memang subdomain dari usersite
  dan memang terdaftar di Domain Management sebagai type AMP).
- Tetap tolak: AMP == Redirect To, `www.`.
- Tampilkan keterangan mode, misalnya badge "Subdomain dari merek.com".

### 3. API route — `src/app/api/amp/domain/route.ts` (dan `/api/domains` bila membuat AMP dari sana)
- Terima `ampMode`, `parentDomain`, `subdomainLabel`. Untuk SUBDOMAIN: lewati `isRootDomain()`, kirim ke Domain Engine
  sesuai kontrak (`POST /domains` dengan `type: "AMP", ampMode: "SUBDOMAIN", parentDomain, subdomainLabel, ampRedirectTo?, ampCanonical?`).
- Jangan lagi menurunkan `ampCanonical` dari `ampRedirectTo` untuk SUBDOMAIN (biarkan kosong → Domain Engine memakai host AMP, atau kirim host AMP).
- Tampilkan error 400/409/502 Domain Engine apa adanya (pesan sudah jelas), termasuk `amp_subdomain_provisioning`
  ("AMP sedang diproses, coba lagi sebentar") dan `amp_deregister_failed` ("gagal melepas AMP, tidak ada yang terhapus, coba lagi").

### 4. **Hapus pemanggilan langsung ke AMP `/internal`** (wajib)
- `src/lib/amp-proxy.ts` → `registerAmpInternalDomain` / `deleteAmpInternalDomain` dipanggil dari
  `api/amp/domain/route.ts`, `api/amp/domain/[domainName]/route.ts`, `api/amp/domain/[domainName]/amp-config/route.ts`.
- Domain Engine **sudah** melakukan semua ini sendiri (provisioning langkah `amp`, `updateAmpConfig`, `deleteDomain`). Panggilan
  dari panel membuat dua jalur yang bisa saling menimpa, dan memakai company code dari JWT yang hanya di-decode (tidak
  diverifikasi) + `X-Internal-Key` yang bisa mendaftarkan domain untuk company **mana pun**.
- Hapus ketiga pemanggilan itu dan fungsi/env terkait (`AMP_INTERNAL_KEY`, `ampInternalKey()`). Setelah rilis, ops akan
  merotasi kunci ini. Pemanggilan AMP lain (build, `/api/v1/...` dengan JWT admin) **tetap**.

### 5. Daftar domain (Domain Management)
- Baris domain AMP SUBDOMAIN: tampilkan "Subdomain dari merek.com"; aksi yang tidak berlaku untuk subdomain disembunyikan
  (nameserver, protection/security level, purge seluruh zone).
- Baris money site yang dipakai AMP: badge "Dipakai AMP: amp.merek.com". Tombol hapus **tetap aktif**, tapi dialog konfirmasi
  wajib menyebut: "AMP `amp.merek.com` akan ikut terhapus dan halaman AMP tidak lagi tersaji." (Domain Engine menghapus
  berantai, kontrak no. 10.)
- Form redirect untuk money site yang dipakai AMP: info "`amp.merek.com` tidak ikut di-redirect, tetap menyajikan AMP".
  Pertimbangkan menyarankan admin mengganti Redirect To AMP ke domain tujuan redirect, supaya tombol Login/Daftar tidak
  lewat 2 kali redirect. Host AMP SUBDOMAIN tidak boleh dipilih sebagai sumber redirect.
- Fitur kelola subdomain/record DNS generik untuk money site: record milik AMP (nama = label AMP) tampil terkunci / tidak bisa
  diedit atau dihapus dari sana, dan nama label AMP tidak boleh dipakai record baru.

### 6. i18n & test
- String baru di `src/lib/i18n.ts` (ID + EN).
- Vitest: validasi label (default `amp`, `www` ditolak, titik ditolak), default Redirect To = money site & Canonical = host AMP,
  payload ke Domain Engine untuk dua mode, route tidak lagi memanggil `/internal` AMP, dialog hapus money site yang dipakai AMP
  menyebut AMP yang ikut terhapus, pesan error 409/502 hapus tampil.

### 7. Rilis
Setelah AMP engine dan Domain Engine versi baru sudah di staging. Uji di staging: buat AMP subdomain dari usersite staging →
publish dari halaman AMP → `https://amp.<usersite>/` tampil, canonical = host AMP, tombol Login/Daftar ke money site →
hapus AMP → usersite tetap jalan. Pasang redirect usersite → AMP tetap tampil. Hapus usersite yang dipakai AMP → dialog
menyebut AMP, keduanya terhapus. Lalu production.

## Definition of done
- Dua mode bisa dibuat dari panel; mode stand-alone tidak berubah.
- Panel tidak lagi memegang/memakai `AMP_INTERNAL_KEY`.
