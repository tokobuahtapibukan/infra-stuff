# Prompt — Admin panel (repo `tokobuah/admin-panel`, Next.js): saklar No_Index per money site

Kamu bekerja di admin panel (Next.js App Router, API route di `src/app/api/**` mem-proxy ke Domain Engine lewat
`fetchEngine`, i18n di `src/lib/i18n.ts`, test vitest). Ikuti konvensi repo.

## Kontrak bersama — No_Index per money site (identik di semua prompt — jangan diubah sepihak)

**Fitur:** tenant (admin panel) dan superadmin bisa menyalakan atau mematikan rule WAF **`No_Index`** untuk money site
miliknya, supaya domain tenant tidak terekspos (tidak dirayapi mesin pencari/crawler/scanner).

**Isi rule (tetap, tidak bisa diubah dari panel)**
- Nama `No_Index`, action **block**, fase Cloudflare `http_request_firewall_custom`.
- Expression = salinan persis rule yang sudah dipakai tim (sumber: `tapakhoki.life`, 2026-11-25), yaitu blok jika salah satu:
  User-Agent crawler/scanner (Googlebot, AhrefsBot, SemrushBot, BingBot, YandexBot, Nmap, CensysInspect, … ),
  `http.request.version in {"HTTP/1.0" "HTTP/1.1"}`, atau `ip.geoip.country eq "US"`.
- Disimpan sebagai satu konstanta di Domain Engine (`NO_INDEX_BASE_EXPRESSION`). Perubahan isi = perubahan kode.

**Aturan**
1. Hanya untuk **money site** (`type: "STANDARD"`) yang provisioning-nya `completed`. Domain AMP (STANDALONE maupun
   SUBDOMAIN) dan subdomain usersite ditolak `400`.
2. Rule berlaku untuk **seluruh zone money site** (apex, `www`, subdomain usersite), **kecuali host AMP** di zone itu.
   Pengecualian AMP disinkronkan otomatis saat AMP subdomain dibuat (sebelum DNS-nya aktif) atau dihapus.
3. **On** → tepat satu rule `No_Index`, enabled, di **urutan pertama** custom rules zone (menang atas rule lain seperti
   `Black_mamba` yang berupa JS challenge). Rule `No_Index` yang dulu dipasang manual **diambil alih** (tidak diduplikasi).
   Rule lain di zone **tidak pernah disentuh**.
4. **Off** → rule `No_Index` dihapus (termasuk yang dipasang manual).
5. Status on/off **dibaca langsung dari Cloudflare** (tidak disimpan di DB), jadi rule manual ikut terbaca sebagai on.
6. Setiap perubahan dicatat di audit log (`DOMAIN_NO_INDEX_ENABLED` / `DOMAIN_NO_INDEX_DISABLED`).

**Dampak yang harus dijelaskan ke user di UI (saat menyalakan)**
- Domain **hilang dari Google/Bing** dan mesin pencari lain; preview link (WhatsApp/Facebook) tidak muncul.
- **Semua pengunjung dari Amerika Serikat** diblokir.
- Klien yang memakai **HTTP/1.0/1.1** diblokir (sebagian alat monitoring, `curl` default, proxy lama).
- Berlaku juga untuk subdomain di bawah domain itu, **kecuali halaman AMP**.

**Kontrak API Domain Engine**
- `GET /domains/:name/no-index` → `200 { "domainName": "merek.com", "enabled": true }`.
- `PUT /domains/:name/no-index` body `{ "enabled": true | false }` → `200 { "domainName", "enabled" }`.
- Error: `400` bukan money site / belum aktif (pesan menjelaskan); `403` domain milik company lain; `404` domain tidak
  ada; `409` zone sudah mencapai batas jumlah custom rule plan Cloudflare; `502` Cloudflare gagal.
- Tidak ada field `No_Index` di `GET /domains`; panel memanggil `GET …/no-index` per money site (jumlah domain per tenant
  dibatasi, jadi aman).

**Urutan rilis:** Domain Engine (+ deploy Cloud Endpoints karena ada path baru) → admin panel & superadmin.
**Staging dulu**, production setelah lolos uji ujung-ke-ujung.

## Yang harus kamu kerjakan
1. **Kolom / aksi "No_Index" di daftar domain** (`src/app/(dashboard)/domains/domains-client.tsx`):
   - Hanya pada baris **money site** (`STANDARD`). Baris AMP dan subdomain tidak punya saklar ini.
   - Status dimuat per money site lewat `GET /domains/:name/no-index` (tampilkan placeholder saat memuat; error →
     tampilkan "tidak diketahui" + tombol muat ulang, jangan anggap off).
   - Saklar on/off → `PUT /domains/:name/no-index { enabled }`.
2. **Dialog konfirmasi saat menyalakan**, menjelaskan dampak (lihat kontrak: hilang dari mesin pencari, pengunjung US
   diblokir, klien HTTP/1.x diblokir, berlaku juga ke subdomain kecuali AMP). Mematikan cukup konfirmasi singkat.
3. **API route panel**: proxy dua endpoint di atas lewat `fetchEngine`; companyCode/tenant dari sesi, bukan dari form.
4. Notifikasi sukses hanya setelah API sukses; pesan error (`400`/`409`/`502`) ditampilkan apa adanya.
5. i18n ID + EN; vitest: saklar hanya muncul di money site, konfirmasi sebelum on, payload benar, error tampil.

## Definition of done
- Tenant bisa menyalakan/mematikan No_Index per money site, statusnya sama dengan Cloudflare (termasuk rule manual).
