# Kartu Claim — Skema

Setiap file `.yaml` di `claims/**` adalah SATU kartu dengan field berikut:

| Field | Wajib | Keterangan |
|---|---|---|
| `id` | ✅ | Unik, kebab-case. Nama stabil — jangan diganti (sejarahnya hidup di sini) |
| `service` | ✅ | Tag ownership: `game-engine`, `user-site`, `tripay`, `meta`, `all-go`, dsb. Room pemilik service yang menjaga kartu ini |
| `env` | ✅ | `production` \| `staging` \| `both` |
| `claim` | ✅ | Kalimat natural-language tentang fakta ini (apa yang kita PERCAYA) |
| `belief_source` | ✅ | Dari mana kepercayaannya: doc+section, report, sesi obrolan, dsb. |
| `check.tool` | ✅ | Nama fungsi cek di engine (deterministik, read-only) |
| `check.args` | ✅ | Argumen tool (project, path, URL, dst.) |
| `expect` | ✅ | Nilai yang harus terpenuhi (count / equals / absent / status / hash / diff_empty) |
| `severity` | ✅ | `critical` (amankan sekarang) \| `warn` \| `info` |
| `recheck` | ✅ | `12h` \| `24h` \| `7d` |
| `retry` | ⬜ | Ulangi cek jika gagal pertama (anti-flaky, default 2, jeda 90s) |
| `flip_note` | ⬜ | Instruksi saat kondisi INTI berubah (mis. P0 selesai: flip `count: 22` → `0`) |
| `credentials` | ⬜ | Nama env-var kredensial di hub (untuk kartu perilaku). NILAI TIDAK PERNAH di sini |
| `note` | ⬜ | Konteks bebas |
| `created` | ✅ | Tanggal kartu dibuat (ISO) |
| `last_verified` | ⬜ | Terakhir kali engine memverifikasi lolos (engine yang menulis) |
| `status` | ✅ | `active` \| `retired` |

## Prinsip

- **Cek = deterministik.** Tidak ada LLM di jalur pass/fail.
- **Expect = properti, bukan nilai volatil.** Jangan card "image tag = v1.4.2" (berubah tiap
  deploy → false alarm selamanya). Card "image tag != `:latest`".
- **Kartu fix-tracking** boleh mem-`expect` kondisi SAKIT saat ini (mis. `count: 22` secret),
  dengan `flip_note` yang menyatakan kapan dan bagaimana flip ke kondisi sehat.
- **Kartu invariant (perilaku)** menjalankan mini-pentest terjadwal (login test-account,
  probe 403, dst.) — semua read-only setelah auth, hanya test account.

## Fungsi cek yang tersedia (Fase 1 — engine Mac; ditambah bertahap)

```
gcp_backend_services_policy            # hitung backend dgn securityPolicy tertentu
gcp_target_proxies_no_policy           # pastikan tidak ada target proxy dgn securityPolicy
k8s_ingress_status_ip                  # IP dari status ingress
http_probe_status                      # GET URL (+host header) → expect status
cross_tenant_probe                     # login 2 test account → swap token → expect 403
gcp_gke_cluster_absent / _exists
gcp_target_http_proxies_prefix_count   # hitung LB dengan prefix nama
git_ls_files_count                     # hitung file ter-track via pola (HANYA count)
gomod_version_below                    # berapa go.mod yang modul-nya < versi X
domain_sibling_app_match               # dig + compare fingerprint asset
js_bundle_contains_url                 # homepage → chunk → grep string
gcs_level_image_public                 # ambil image_url /beapi/public/levels → GET 200
compare_lb_inventory_vs_hub_scan_targets # meta: semua public LB masuk scan hub
```
