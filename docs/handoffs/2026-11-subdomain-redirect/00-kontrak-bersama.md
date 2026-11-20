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
