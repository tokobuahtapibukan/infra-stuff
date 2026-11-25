# Prompt — Superadmin (repo `tokobuah/superadmin-companyend`, Next.js): saklar No_Index per money site agen

Kamu bekerja di panel superadmin (Next.js; API route di `src/app/api/**` memanggil Domain Engine lewat
`DOMAIN_ENGINE_URL`, default `http://10.10.16.39`). Ikuti konvensi repo.

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
1. Di halaman domain per agen (`src/app/(dashboard)/domains/`), tambah saklar **No_Index** pada baris **money site**
   (`type: "STANDARD"` dari `GET /domains`; jangan pakai label tebakan "Main/Landing/Alternative" untuk menentukan ini).
2. Status per money site dari `GET /domains/:name/no-index`; ubah lewat `PUT /domains/:name/no-index { enabled }`
   (token superadmin; Domain Engine mengizinkan SUPERADMIN untuk semua company).
3. Dialog konfirmasi dampak sama seperti admin panel; notifikasi sukses hanya setelah API sukses; error tampil apa adanya.
4. Test: saklar hanya di money site, payload benar, error tampil.

## Catatan terkait (dari audit 2026-11-23, bisa dikerjakan bersamaan)
- Label tipe domain di `src/app/api/domains/route.ts` ditebak dari redirect/urutan; pakai `type` dari engine.
- Edit redirect dan hapus domain melakukan "hapus redirect dulu"; dengan validasi baru, kegagalan langkah berikutnya
  membuat redirect hilang. Lihat `DOMAIN_ENGINE_RUNBOOK.md` (open items).

## Definition of done
- Superadmin bisa menyalakan/mematikan No_Index per money site agen; status sesuai Cloudflare.
