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
