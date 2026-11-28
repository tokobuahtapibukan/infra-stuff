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

### Staging (`lkc-2227jno`, 12 topik)
`audit.event`, `be.game.bet`, `be.prize.credited`, `dlq-lcc-k8g202g`, `dlq-lcc-pgkvzj5`,
**`fruit4d-staging-transaction`** (3 partisi, RF 3 — topik bet-event api-fruit-lottery),
`game-transaction`, `game-transaction-ikndev`, **`game-transaction-ikndemo`** (1 partisi, RF 3 —
dibuat 2026-11-28, tenant staging kedua; sebelumnya TIDAK ADA sehingga game-flow ikndemo tidak
mengalir ke BQ `game_transactions_raw`, tidak seperti ikndev), `game-transaction-outbox-kafka-ikndev`,
`spinwheel.prize.won`, `ticket.granted`

> **Resolusi topik game-tenant (diverifikasi 2026-11-28 di `transactional-engine-go/pkg/config/config.go`
> `GameTopic()`):** `KAFKA_GAME_TOPIC + "-" + COMPANY_CODE`, kecuali `KAFKA_GAME_TOPIC_FULL` di-set
> (verbatim). Tenant `client` (ikndev): `game-transaction` + `ikndev` → `game-transaction-ikndev`
> (group `new-backend-staging-group`). Tenant `ikndemo`: `game-transaction` + `ikndemo` →
> `game-transaction-ikndemo` (group `new-backend-staging-group-ikndemo`, agentCode filter `ikndemo`).
> Topik dasar `game-transaction` (tanpa suffix) ada di daftar tapi TIDAK di-tuju resolusi mana pun —
> kemungkinan sisa setup lama; belum dihapus (butuh izin §2).

### Production (`lkc-38r9y82`, 22 topik)
`audit.event`, `be.game.bet`, `be.prize.credited`, `dlq-lcc-nvy9oqz`, `game-transaction`,
`game-transaction-{buah5758,ikn788,hambabet,rumushoki,pengenwd,terios88,cinabotak,cinasuper,omsipit,terbangwd,tapakhoki,dutaledak,padi808}`,
`game-transaction-outbox-kafka-buah5758`, `spinwheel.prize.won`, `ticket.granted`
— **tidak ada topik fruit4d** (lottery belum live di prod; topik prod dibuat saat go-live,
usulan penamaan: `fruit4d-prod-transaction`, konsisten pola `{service}-{env}-transaction`).

## BigQuery sink connector per env (apa yang benar-benar sampai ke BQ)

| Env | Connector | project.dataset | Topics di-map | Fruit4d? |
| :-- | :-- | :-- | :-- | :-- |
| prod | `lcc-nvy9oqz` (RUNNING) | `tokobuah-production.game_reports` | 14× `game-transaction-{company}` + `audit.event`, `ticket.granted`, `spinwheel.prize.won` | ❌ (topik fruit4d prod belum ada — lottery belum live di prod) |
| staging | `lcc-k8g202g` (RUNNING) | `tokobuah-staging-499001.game_reports` | `be.game.bet`→bets_raw, `audit.event`, `spinwheel.prize.won`, `ticket.granted`, `game-transaction-ikndev`→game_transactions_raw | ✅ **SUDAH MENGALIR** |

**Koreksi 2026-11-28 (vonis salah versi-1):** transaksi lottery fruit4d **SUDAH masuk BigQuery
staging** — via jalur standar game-engine: pod lottery game-engine publish `game-transaction` →
topik `game-transaction-ikndev` → `game_reports.game_transactions_raw`. GameCode di BQ:
`FRUIT4D_LOTTERY` & `FRUIT4D_LOTTERY_CUSTOM` (providerId=40); siklus lengkap `bet`/`cashin`/
`refund`/`rollback_bet` terverifikasi (61+ row, latest live hari ini). Kesalahan versi-1: query
hanya dijalankan di project **production** — data memang belum ada di sana karena lottery belum
live di prod (ingat §8: enumerasi lintas-environment wajib).

**Yang TIDAK masuk BQ (by design, bukan bug):** topik `fruit4d-staging-transaction` (bet-event
stream api-fruit-lottery) adalah jalur **payout-processing + audit internal** — tidak di-map ke
connector, dan tidak perlu untuk dashboard superadmin karena angka bet/settle sudah tertutup
oleh game-transaction path. Jika suatu hari Finance butuh audit `payout.failed/gave_up` di BQ,
baru tambahkan mapping itu (SOP 5.2).

**Checklist go-live lottery prod:** deploy lottery pod di prod dengan `KAFKA_PRODUCER_TOPIC:
game-transaction` (runtime: `game-transaction-{company}`) — topik company sudah ter-cover di
connector prod (14 company). Company baru → ikut SOP 5.2. Tidak ada wiring tambahan untuk
dashboard, selama flow lottery tetap lewat seamless game-engine pod.

Catatan: `TCG_LOTTERY` (providerId=31, brand 384) di BQ adalah game lottery provider eksternal
TCG via game-engine — BUKAN fruit4d. Flow-nya berhenti 2026-11-11; masih terbuka apakah sengaja
(game di-pause) atau anomali — cek terpisah.

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
