# Kafka Topology — Confluent Cloud (peta wajib-baca sebelum vonis "topik tidak ada")

> Lahir dari insiden vonis-salah 2026-11-28: agent menyimpulkan topik `fruit4d-staging-transaction`
> "tidak pernah dibuat" padahal ada — karena hanya mengecek cluster production. Dua cluster kita
> memakai **hostname bootstrap yang identik**; satu-satunya pembeda adalah kredensial.

## Environment → Cluster

| Env | Confluent env ID | Cluster ID | Nama cluster | Tipe | Bootstrap endpoint |
| :-- | :-- | :-- | :-- | :-- | :-- |
| production | `env-5d9zj2` | `lkc-38r9y82` | `tokobuah-production` | STANDARD (high avail) | `SASL_SSL://pkc-ldvr1.asia-southeast1.gcp.confluent.cloud:9092` |
| staging | `env-zw1k1z` | `lkc-2227jno` | `tokobuah-development` | BASIC (low) | `SASL_SSL://pkc-ldvr1.asia-southeast1.gcp.confluent.cloud:9092` |

⚠️ **Hostname bootstrap KEDUA cluster identik.** Jangan pernah pakai hostname untuk menentukan
"ini cluster mana" — lihat kredensial (API key) yang dipakai config/secret.

## API Key → Cluster (ID key bukan secret; nilai secret tidak pernah disimpan di repo — §5)

| Key ID | Nama | Cluster scope | Dipakai oleh |
| :-- | :-- | :-- | :-- |
| `Y2WSD2FDHB27UY7H` | staging-key | `lkc-2227jno` (staging) | secret.yaml pod staging (mis. `company-deployment-key/staging/core/fruit4d/secret.yaml`) |
| `TMWWPIMRPURQJCPE` | production-key | `lkc-38r9y82` (prod) | config prod |

## Topik per cluster (snapshot 2026-11-28 — cek live sebelum memakai)

### Staging (`lkc-2227jno`, 11 topik)
`audit.event`, `be.game.bet`, `be.prize.credited`, `dlq-lcc-k8g202g`, `dlq-lcc-pgkvzj5`,
**`fruit4d-staging-transaction`** (3 partisi, RF 3 — topik bet-event api-fruit-lottery),
`game-transaction`, `game-transaction-ikndev`, `game-transaction-outbox-kafka-ikndev`,
`spinwheel.prize.won`, `ticket.granted`

### Production (`lkc-38r9y82`, 22 topik)
`audit.event`, `be.game.bet`, `be.prize.credited`, `dlq-lcc-nvy9oqz`, `game-transaction`,
`game-transaction-{buah5758,ikn788,hambabet,rumushoki,pengenwd,terios88,cinabotak,cinasuper,omsipit,terbangwd,tapakhoki,dutaledak,padi808}`,
`game-transaction-outbox-kafka-buah5758`, `spinwheel.prize.won`, `ticket.granted`
— **tidak ada topik fruit4d** (lottery belum live di prod; topik prod dibuat saat go-live,
usulan penamaan: `fruit4d-prod-transaction`, konsisten pola `{service}-{env}-transaction`).

## BigQuery sink connector per env (apa yang benar-benar sampai ke BQ)

| Env | Connector | project.dataset | Topics di-map | Fruit4d? |
| :-- | :-- | :-- | :-- | :-- |
| prod | `lcc-nvy9oqz` (RUNNING) | `tokobuah-production.game_reports` | 14× `game-transaction-{company}` + `audit.event`, `ticket.granted`, `spinwheel.prize.won` | ❌ |
| staging | `lcc-k8g202g` (RUNNING) | `tokobuah-staging-499001.game_reports` | `be.game.bet`→bets_raw, `audit.event`, `spinwheel.prize.won`, `ticket.granted`, `game-transaction-ikndev` | ❌ |

Konsekuensi terverifikasi 2026-11-28: **data lottery (fruit4d) tidak ada di BigQuery mana pun**
(0 row gameCode fruit/SHIO/4D di `view_all_game_transactions_raw`). Data bet lottery hanya hidup
di MySQL lottery (`bet_events`, `bet_invoices`, `draws`). Catatan: `TCG_LOTTERY` (providerId=31,
brand 384) di BQ adalah game lottery provider eksternal TCG via game-engine — BUKAN fruit4d.

## Checklist anti-vonis-salah (baca sebelum menyimpulkan "topik/resource tidak ada")

1. **Tentukan env target dari kredensial**, bukan hostname (hostname identik antar cluster).
2. **Enumerate SEMUA environment** (`confluent environment list` → topic list per cluster)
   sebelum vonis negatif. Banyak service hanya ada di staging; beberapa ada di keduanya.
3. **Confluent Cloud tidak auto-create topik** — producer yang mengirim ke topik yang belum
   dibuat akan gagal senyap (buffer Redis → `*_lost`), bukan membuat topik baru.
4. Configmap K8s yang tidak memuat `KAFKA_BROKERS`/kredensial berarti kredensial datang dari
   Secret — cek file secret-nya (keberadaan key-ID saja, bukan nilainya) untuk tahu cluster mana.
5. Dokumen SOP (`PROVIDER_PROXY_AND_STREAMING_OPERATIONS.md` §5) hanya mencakup cluster prod —
   dokumen ini yang jadi peta lengkapnya.

## Recheck otomatis

Belum ada check tool Confluent di engine (daftar Fase 1). Peta ini diverifikasi manual via CLI
saat sesi menyentuh Kafka; kandidat check tool `confluent_topic_exists` / `connector_topic_map`
untuk Fase berikutnya.
