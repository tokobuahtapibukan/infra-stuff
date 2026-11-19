# 🏛️ TOKOBUAH PLATFORM — MASTER INFRASTRUCTURE KNOWLEDGE BASE & OPERATIONS RUNBOOK
> **Document Version**: 2.4.0  
> **Last Synchronized**: 2026-11-17 (see [Changelog](#changelog))  
> **Precedence**: Global rules in `~/AGENTS.md` apply on top of this document. If they differ, the **stricter rule wins**.  
> **Scope**: Architecture, Kubernetes (GKE), Networking, Databases (Cloud SQL & HAProxy), Messaging (Kafka), In-Memory Caching (Redis), CI/CD (CloudBuild), Financial Cost Optimization, and Operational Guardrails.  
> **Target Audience**: SREs, DevOps Engineers, and Autonomous AI Agents taking over this workspace.

---

## 📑 TABLE OF CONTENTS
1. [Platform Identity & Multi-Tenant Overview](#1-platform-identity--multi-tenant-overview)
2. [Google Cloud Platform (GCP) Project & Region Topology](#2-google-cloud-platform-gcp-project--region-topology)
3. [Networking & Ingress Architecture](#3-networking--ingress-architecture)
4. [Kubernetes (GKE) Cluster Ecosystem](#4-kubernetes-gke-cluster-ecosystem)
5. [Database Layer: Cloud SQL PostgreSQL, HAProxy, & MongoDB](#5-database-layer-cloud-sql-postgresql-haproxy--mongodb)
6. [Caching & In-Memory Layer (Redis Memorystore)](#6-caching--in-memory-layer-redis-memorystore)
7. [Event Streaming & Ledger Ingestion (Confluent Cloud Kafka & BigQuery)](#7-event-streaming--ledger-ingestion-confluent-cloud-kafka--bigquery)
8. [Serverless Compute: Cloud Run Inventory & Scaling](#8-serverless-compute-cloud-run-inventory--scaling)
9. [CI/CD Automation (CloudBuild) & Git Repositories](#9-cicd-automation-cloudbuild--git-repositories)
10. [Cost Reduction Matrix & Financial Projections](#10-cost-reduction-matrix--financial-projections)
11. [Vendor Evaluation Reference: Aerospike vs Kafka vs Redis vs Postgres](#11-vendor-evaluation-reference-aerospike-vs-kafka-vs-redis-vs-postgres)
12. [Agent Safety & Governance Guardrails: Permission & Approval Protocol](#12-agent-safety--governance-guardrails-permission--approval-protocol)
13. [Technical Operational Caveats & Golden Rules](#13-technical-operational-caveats--golden-rules)
14. [Security Audit Protocols & Network Exposure Verification](#14-security-audit-protocols--network-exposure-verification)
15. [Changelog](#changelog)

---

## 1. PLATFORM IDENTITY & MULTI-TENANT OVERVIEW

Tokobuah operates a high-availability, multi-tenant iGaming, FinTech, Payment, and White-Label platform.
* **Core Business Engines**:
  * `game-engine`: Real-time bet, win, refund, and rollback ingestion from external game providers (Pragmatic Play, PG Soft, SV388, etc.).
  * `transactional-engine`: Double-entry accounting ledger processing player balances atomically.
  * `auth-engine`: Player registration, authentication, JWT token issuance, and blacklisting.
  * `tripay-sc`: Payment gateway aggregation, callbacks, cron settlements, and merchant APIs.
  * `domain-management` & `user-site`: Dynamic multi-tenant frontend tenant routing and white-label sites.
* **Active Production Tenants (11+ Tenants)**:
  * Key tenants include `hambabet`, `ikn788`, `rumushoki`, `buah5758`, `dutaledak`, among others.
  * Multi-tenancy isolation model:
    * Compute: Tenant-isolated pods and namespaces (`hambabet`, `game`, `core`).
    * Database: Dedicated Cloud SQL databases per tenant accessed through an internal HAProxy routing layer.
    * Messaging: Partitioned and per-tenant topics in Kafka (`game-transaction-{tenant}`).

---

## 2. GOOGLE CLOUD PLATFORM (GCP) PROJECT & REGION TOPOLOGY

### Project Accounts & Active IDs:
* **Production GCP Project**: `tokobuah-production`
* **Staging GCP Project**: `tokobuah-staging-499001`
* **Primary Region**: `asia-southeast1` (Singapore)
* **Secondary / Specialized Regions**:
  * `asia-southeast2` (Jakarta) — Specialized tenant and DB endpoints.
  * `asia-east1` (Taiwan) — Cloud Run admin instances and regional subnets.
* **Primary IAM / Service Accounts**:
  * Active Developer / SRE gcloud Account: `admin@tokobuah.xyz`
  * Staging Workload Identity Account: `tripay-sa@tokobuah-staging-499001.iam.gserviceaccount.com`

---

## 3. NETWORKING & INGRESS ARCHITECTURE

### Virtual Private Clouds (VPCs):
* **`production-platform-vpc`** (Production network)
* **`staging-platform-vpc`** (Staging network)

### Subnet Layout (`staging-platform-vpc`):
* `core-subnet` (`10.10.1.0/24` in `asia-southeast1`): Primary subnet for standard staging workloads.
* `client-gke-subnet` (`10.10.16.0/20` in `asia-southeast1`): Client tenant pods.
* `tripay-gke-subnet` (`10.10.48.0/20` in `asia-southeast1`):
  * Secondary ranges: `tripay-pods` (`10.244.0.0/17`), `tripay-services` (`10.244.128.0/20`).
  * *Status*: **Idle** (0 resources bound) after Tripay cluster consolidation. Safe to delete.
* `taiwan-subnet` (`10.10.40.0/24` in `asia-east1`)
* `jakarta-subnet` (`10.10.8.0/24` in `asia-southeast2`)

### Cloud NAT & Egress Flow:
* GKE nodes and pods reside exclusively on **Private Subnets** without public IPv4 addresses.
* Outbound traffic to the public internet (including Confluent Cloud Kafka brokers) traverses **Cloud NAT** performing Source NAT (SNAT).
* **Cloud NAT inventory (live-verified 2026-11-17)** — all NATs cover `ALL_SUBNETWORKS_ALL_IP_RANGES`:

| Project | Router / NAT | Region | Network | IP Allocation | Current Egress IP |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tokobuah-production` | `prod-router-sg` / `prod-nat-sg` | asia-southeast1 | `production-platform-vpc` | **AUTO_ONLY** | `34.126.148.104` |
| `tokobuah-production` | `prod-router-tw` / `prod-nat-tw` | asia-east1 | `production-platform-vpc` | **AUTO_ONLY** | `35.201.237.149` |
| `tokobuah-staging-499001` | `staging-router` / `staging-nat` | asia-southeast1 | `staging-platform-vpc` | **AUTO_ONLY** | `34.21.205.254` |

* ⚠️ **AUTO_ONLY = ephemeral egress IPs.** GCP may add, replace, or release auto-allocated NAT IPs (e.g. on port-demand changes or NAT reconfiguration). **Never use these IPs in an allowlist** (vendor whitelist, firewall source range) until the NAT is converted to **MANUAL_ONLY with reserved static IPs** — converting is a production change (Guardrail 1).

### Vendor Egress Proxy VMs — ⚠️ PRODUCTION-CRITICAL (despite `stg` naming)
> [!CAUTION]
> `proxy-stg-jkt` and `proxy-stg-sg` live in the **staging project** and carry `stg` in their names, but **all production game-vendor API traffic depends on `proxy-stg-jkt`**. Both VMs are classified **PRODUCTION** for every guardrail in §12 and in `~/AGENTS.md` (§1 Production Freeze applies; the staging-only `rollout restart` exception does **not** apply). Any config edit, route add/remove, `supervisorctl restart proxy_root`, firewall change, SSH key change, VM stop/resize, or static IP change requires the full Guardrail 1 protocol and explicit user approval.

* **Purpose**: Static egress IPs whitelisted by game vendors. A Go reverse proxy (`proxy_root`, managed by supervisor) maps path prefixes to vendor base URLs (e.g. `/pp-prod` → Pragmatic Play). Config: `/home/adminbuah/config-new.json`.
* **Inventory (live-verified 2026-11-17)**:

| VM | Project | Zone | Network | Internal IP | Static External IP | Machine | Deletion Protection | Snapshots |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `proxy-stg-jkt` | `tokobuah-staging-499001` | asia-southeast2-a | `default` | `10.184.0.3` | `34.101.110.121` (`proxy-stg-jkt-ip`) | e2-micro | ✅ on (2026-11-17) | ✅ `proxy-stg-jkt-daily` |
| `proxy-stg-sg` | `tokobuah-staging-499001` | asia-southeast1-c | `default` | `10.148.0.4` | `34.21.136.141` (`proxy-stg-sg-ip`) | e2-micro | ✅ on (2026-11-17) | ✅ `proxy-stg-sg-daily` |

* **Resilience controls (applied 2026-11-17, user-approved, C4 — no restart, no downtime)**:
  * Deletion protection enabled on both VMs (`gcloud compute instances update <vm> --deletion-protection`). To delete a VM it must first be disabled — which itself requires Guardrail 2 approval.
  * Snapshot schedules (resource policies): `proxy-stg-jkt-daily` (asia-southeast2, storage asia-southeast2) and `proxy-stg-sg-daily` (asia-southeast1, storage asia-southeast1) — daily at 19:00 UTC (02:00 WIB), retention 7 days, `keep-auto-snapshots` on disk delete. Attached to boot disks `proxy-stg-jkt` / `proxy-stg-sg` (10 GB pd-standard).
  * Uptime checks (project `tokobuah-staging-499001`): `proxy-stg-jkt tcp80` and `proxy-stg-sg tcp80` — TCP connect to port 80 every 60 s from multiple Google regions (no HTTP request, so no vendor call). First results: all passed.
  * **Alerting (2026-11-17, user-approved)**: notification channel `Tokobuah Admin Email` (type email → the admin account; `projects/tokobuah-staging-499001/notificationChannels/3186120846916708900`). Alert policies `proxy-stg-jkt DOWN (vendor proxy, production-critical)` and `proxy-stg-sg DOWN (...)`: fire when **more than 1 checker region** reports failure for **2 minutes**; auto-close after 30 min of recovery; documentation in the alert points back to this section. Emails come from Google Cloud Alerting (`alerting-noreply@google.com`).
  * Note: created via the Monitoring REST API (gcloud `alpha` component is not installed on the workstation). Policy JSON kept only as a temp file; the live policy in Cloud Monitoring is the source of truth.

* **Single point of failure**: production uses **only `proxy-stg-jkt`**. `proxy-stg-sg` is not referenced by any live config (only a TCG rationale doc). If JKT is down, deleted, or misconfigured, **all production vendor integrations stop**.
* **Known callers (from live configs + code, 2026-11-17)**:

| Caller | Runs in | Reference | Egress source IP seen by proxy |
| :--- | :--- | :--- | :--- |
| `game-engine` **production** | `game-cluster` ns `game` (configmaps `game-engine-config`, `-launcher-config`, `-transactions-config`; 34 refs each, `http://34.101.110.121/<vendor>-prod`) | JKT | `34.126.148.104` (`prod-nat-sg`, AUTO_ONLY) |
| `game-engine` staging | `staging-gke-standard` ns `core` | JKT | `34.21.205.254` (`staging-nat`, AUTO_ONLY) |
| `gamelist-engine` staging | `staging-gke-standard` ns `core` | JKT | `34.21.205.254` (`staging-nat`, AUTO_ONLY) |
| Hermes agents (`proxy-route-manager`, `proxy_route_probe.py`, crawler) | VM `hermes-agent-host` | JKT + SG (HTTP + SSH as `adminbuah`) | `34.87.88.43` (VM external IP) |

  * Scanned with no matches: live configmaps in `prod-core-cluster` and `prod-client-cluster`; Kubernetes Secrets in all 4 clusters; Cloud Run env vars in both projects.
  * **Traffic verification (read-only SSH, 2026-11-17)**: the proxy app (Goinx) **does not log client source IPs** — `/var/log/proxy.out.log` only contains `Proxied URL: <full upstream URL incl. query string>` (6 × ~50 MB rotations, world-readable). Proxy logs are not shipped to Cloud Logging; firewall-rule logging and VPC Flow Logs are disabled. A 60-second `ss` sample of established/TIME_WAIT connections on :80/:443 showed only `34.126.148.104` (prod NAT) on JKT and nothing on SG. Low-frequency callers (staging, Hermes) cannot be ruled out without longer capture (e.g. temporarily enabling firewall-rule logging — requires approval).
  * **SSH sources (journald, last 30 days)**: successful logins only from `34.2.153.31` (= external IP of `sg-vpn-gateway-dev-1`, which is also the admin workstation's internet egress; users `adminbuah`, `avocado`) and IAP range `35.235.240.0/20` (`avocado`). ~39k (JKT) / ~33k (SG) failed or invalid attempts from the internet in 30 days. Hermes host `34.87.88.43` had no SSH logins in that window.
* **Network exposure (live-verified 2026-11-17)**:
  * Ingress: `proxy-stg-*-allow-http` (tcp:80) and `-allow-https` (tcp:443) from `0.0.0.0/0`; `default-allow-ssh` (tcp:22) and `default-allow-rdp` (tcp:3389) from `0.0.0.0/0` with no target tags (apply to every VM in `default`).
  * **SSH/RDP lockdown (applied 2026-11-17, user-approved, C3)** — two rules scoped to the proxy tags `proxy-stg-jkt-http`, `proxy-stg-sg-http` only (other VMs in `default`, e.g. `partner-analytics-vm`, unaffected; existing rules untouched):

| Rule | Priority | Action | Ports | Sources |
| :--- | :--- | :--- | :--- | :--- |
| `proxy-ssh-allow-trusted` | 900 | ALLOW | tcp:22 | `35.235.240.0/20` (IAP), `34.2.153.31/32` (`sg-vpn-gateway-dev-1-ip`, admin workstation egress), `34.87.88.43/32` (`hermes-agent-host`, static `hermes-agent-host-ip`) |
| `proxy-ssh-deny-internet` | 950 | DENY | tcp:22, tcp:3389 | `0.0.0.0/0` |

    * Verified after apply: SSH OK from workstation path, via IAP tunnel (`gcloud compute start-iap-tunnel <vm> 22 ...`), and from Hermes host; SSH from a non-allowlisted source (proxy-stg-sg egress `34.21.136.141` → JKT) **blocked**; port 80 and live production vendor traffic unaffected.
    * Rollback (non-destructive): `gcloud compute firewall-rules update proxy-ssh-deny-internet --disabled --project=tokobuah-staging-499001`.
    * `hermes-agent-host` external IP `34.87.88.43` was promoted from ephemeral to **static** (`hermes-agent-host-ip`, asia-southeast1, PREMIUM) on 2026-11-17 (user-approved; same IP, no downtime). It now survives VM stop/start. If the address is ever released or changed, update this rule's source list in the same change.
    * Recommended access path for humans: `gcloud compute ssh <vm> --tunnel-through-iap` (or `start-iap-tunnel` + existing key).
  * Production → proxy traffic is **plain HTTP to a public IP** (crosses Cloud NAT and the public internet path; vendor credentials in requests are visible to the proxy host).
  * Network `default` is peered with `staging-platform-vpc` (`default-to-staging-platform`, created 2026-11-10; imports e.g. `10.10.16.0/20`, `10.10.1.0/24`). A proxy route pointing at an RFC1918 target (e.g. `/fruit4d-dev` → `10.10.31.221`, an internal LB with global access) therefore bridges the internet into staging.
  * Service account: default compute SA `258862287268-compute@developer.gserviceaccount.com` with scope `cloud-platform`.
  * ~~Open DNS resolver on :53~~ — **false positive** (no firewall rule allows 53; the auditing workstation's network transparently intercepts DNS — see §14).
* **Hardening backlog** (proposed 2026-11-17, none executed): see the Proxy Machine Security Audit discussion — restrict 80/443 sources (prerequisite: NAT → MANUAL static IPs + caller verification), remove RFC1918 routes, ~~IAP-only SSH~~ (done 2026-11-17, see firewall lockdown), ~~deletion protection + snapshots + uptime check~~ (done 2026-11-17, incl. email alerting), least-privilege SA, fix Hermes `add_proxy_route.py` (input escaping, config validation, rolling restart, host key checking), longer-term move vendor egress into the production project.

### Ingress & Global HTTP(S) Load Balancer (GCLB):
* Managed by GKE `loadbalancer-controller` using Ingress class `gce`.
* **Public Static IP Inventory**:
  * `35.244.234.26` (`staging-tripay-ingress-ip`): Global external static IPv4 bound to `tripay-ingress` on `staging-gke-standard`.
  * `136.82.0.162`: `amp-ingress`
  * `136.68.233.79`: `game-engine-ingress` (`buah.iknstaging.com`)
* **Cloudflare Proxy Integration**:
  * Public domains (`tripay-be.iknstaging.com`, `tripay-cb.iknstaging.com`, `tripay-open.iknstaging.com`) resolve to Cloudflare edge IPs (`172.67.158.13`, `104.21.49.25`).
  * Cloudflare proxies SSL traffic to the GCP Global Static IP origin port 80/443.
  * **Critical Caveat**: When rebinding a GCP Global Static IP to a new Ingress/Forwarding Rule, Google Front End (GFE) edge proxies take **2 to 5 minutes** to propagate the new URL map globally. During this window, `curl` or Cloudflare may return HTTP 520 or TCP resets until propagation completes.

---

## 4. KUBERNETES (GKE) CLUSTER ECOSYSTEM

### Cluster Inventory:
```text
┌───────────────────────────────────┬───────────────────┬───────────────────────┬────────────────────────────┐
│ Cluster Name                      │ Environment       │ Zone / Region         │ Key Namespaces             │
├───────────────────────────────────┼───────────────────┼───────────────────────┼────────────────────────────┤
│ prod-core-cluster                 │ Production        │ asia-southeast1       │ core                       │
│ prod-client-cluster               │ Production        │ asia-southeast1-c     │ hambabet, tenant spaces    │
│ game-cluster                      │ Production        │ asia-southeast1-c     │ game                       │
│ staging-gke-standard              │ Staging           │ asia-southeast1-a     │ tripay, amp, core, fruit4d │
│ staging-tripay-cluster (DELETED)  │ Staging           │ asia-southeast1-a     │ [PURGED & CONSOLIDATED]    │
└───────────────────────────────────┴───────────────────┴───────────────────────┴────────────────────────────┘
```

### Staging Tripay Cluster Consolidation Details:
On November 11, 2026, `staging-tripay-cluster` was permanently deleted to eliminate the $73/mo GKE Management Fee and dedicated VM costs.
All workloads were consolidated into `staging-gke-standard` under the `tripay` namespace:
1. **Cluster Addon Enabled**: `GcsFuseCsiDriver=ENABLED` activated on `staging-gke-standard`.
2. **Node Pool Metadata Enabled**: `workload-metadata=GKE_METADATA` activated on `core-pool`.
3. **Workload Identity**:
   * Kubernetes ServiceAccount `tripay-ksa` in namespace `tripay`.
   * Annotated with: `iam.gke.io/gcp-service-account: tripay-sa@tokobuah-staging-499001.iam.gserviceaccount.com`.
   * IAM Role binding: `roles/iam.workloadIdentityUser` bound to `tokobuah-staging-499001.svc.id.goog[tripay/tripay-ksa]`.
4. **Volume Mount (GCS Fuse)**:
   * Storage bucket: `tokobuah-staging-tripay-storage`.
   * Mounted subpaths: `/app/docs`, `/app/file`, `/app/images`.
   * Pod resource requests: `gke-gcsfuse/cpu-request: "50m"`, `gke-gcsfuse/memory-limit: "256Mi"`.
5. **Active Pods in `staging-gke-standard` (`tripay` namespace)**:
   * `tripay-be`: 2/2 Running (Ready) — NestJS HTTP backend.
   * `tripay-callback`: 1/1 Running (Ready) — Payment webhook consumer.
   * `tripay-cron`: 2/2 Running (Ready) — Scheduled settlement worker.
   * `tripay-open`: 1/1 Running (Ready) — Open API / Scalar Documentation service.
6. **BackendConfig Custom Resources**:
   * `tripay-be-backendconfig`: Session affinity `GENERATED_COOKIE` (TTL 3600s), timeout 3600s.
   * `tripay-callback-backendconfig`: Timeout 60s.
   * `tripay-open-backendconfig`: Timeout 60s.

---

## 5. DATABASE LAYER: CLOUD SQL POSTGRESQL, HAPROXY, & MONGODB

### Multi-Tenant PostgreSQL Architecture:
* Financial ledgers require **strict ACID guarantees, row-level locking (`SELECT ... FOR UPDATE`), and double-entry bookkeeping**.
* Each tenant possesses an isolated database instance to prevent noisy-neighbor issues and guarantee audit compliance.

### HAProxy Database Proxy (`prod-db-proxy`):
* **VM Instance Name**: `prod-db-proxy`
* **Internal IP**: `10.20.16.5`
* **Zone / Project**: `asia-southeast1-b` / `tokobuah-production`
* **Port Mapping Allocation**:
  * Ports `5432` through `5450`: Dedicated tenant databases (e.g., port `5450` for `dutaledak`).
  * Port `5451`: `prod-connector-postgresql` (`connector_summary` database on private IP `10.60.128.61:5432`).
* **Operational Procedure for HAProxy Updates**:
  1. Edit `/etc/haproxy/haproxy.cfg`.
  2. Validate syntax: `sudo haproxy -c -f /etc/haproxy/haproxy.cfg`.
  3. Reload gracefully without dropping active connections: `sudo systemctl reload haproxy`.
  4. Sync GCE instance metadata `haproxy-cfg`.

### MongoDB Atlas Setup:
* Used primarily in `tripay-sc` for unstructured document schemas and logs.
* Private network endpoint: `atlas-tripay-stg` accessible via Private Service Connect (PSC) at `10.10.1.3`.

---

## 6. CACHING & IN-MEMORY LAYER (REDIS MEMORYSTORE)

### Current Production Inventory (verified live 2026-11-14):
10 separate GCP Memorystore Redis instances — all **Basic Tier, 1 GB, Redis 7.2**, zone `asia-southeast1-b`, network `production-platform-vpc`, created 2026-08-07 to 2026-08-09.

| Instance | Used Memory (max, 1h) |
| :--- | ---: |
| `prod-game-redis` | 35.1 MB |
| `prod-game-queue-redis` | 9.9 MB |
| `prod-pga-redis` | 7.9 MB |
| `prod-gamelist-redis` | 7.2 MB |
| `prod-domain-redis` | 5.1 MB |
| `prod-auth-redis` | 5.1 MB |
| `prod-shared-redis` | 4.9 MB |
| `prod-cms-redis` | 4.5 MB |
| `prod-ipwhitelist-redis` | 4.3 MB |
| `prod-spinwheel-redis` | 4.1 MB |
| **Total** | **~88 MB** |

*Source*: `gcloud redis instances list --project tokobuah-production --region=-` + Cloud Monitoring metric `redis.googleapis.com/stats/memory/usage` (ALIGN_MAX over 1h).

### Staging Inventory:
* `game-redis` ("redis for staging game engine") — Basic, 1 GB, Redis 7.2.
* `staging-redis` — Basic, 1 GB, Redis 7.2.

### Critical Findings & Planned Quick-Win:
* **The Problem**: 10 instances running 24/7 cost ~$35.77 each = **~$358 / month**.
* **Real Utilization**: **Total combined data across ALL 10 instances is only ~88 MB** (< 9% of a single 1 GB instance).
* **Watch Item**: `prod-game-redis` grew from 24.4 MB (earlier snapshot) to 35.1 MB. Monitor its growth trend before deciding between 1 or 2 target instances.
* **Recommended Action**: Consolidate into 1 or 2 Redis instances (e.g. 1 Core Cache + 1 Queue/Game instance).
* **Projected Savings**: **~$280 – $320 / month (~Rp 4.5 – 5.1 juta/bln)** with zero code changes required (only updating connection strings in ConfigMaps/Secrets).

---

## 7. EVENT STREAMING & LEDGER INGESTION (CONFLUENT CLOUD KAFKA & BIGQUERY)

### Broker Topology:
* **Broker Endpoint**: `pkc-ldvr1.asia-southeast1.gcp.confluent.cloud:9092`
* **Public IP**: `35.240.228.123` (accessed via Cloud NAT)
* **Authentication**: `SASL_SSL` (PLAIN protocol with API Key / Secret)
* **Wire Protocol**: Kafka Protocol v2/v3 compatible

### Topic & Partition Layout:
* **Multi-Tenant Financial Topics**: `game-transaction-{tenant}` (e.g. `game-transaction-buah5758`).
  * Partitions: **3 partitions per tenant**.
  * Partition Key: `data.transactionId` (UUID) or `userId`.
  * Retention: **7 days** with `cleanup.policy=delete` + Confluent Tiered Storage.
  * Message Payload: JSON, average **1.2 KB – 2.5 KB** per event (`GameTransactionMessage`).
* **Auxiliary Topics**: `{tenant}.user.registered`, `ticket.granted`, `spinwheel.prize.won`, `audit.event`.

### Producers:
* **`game-engine` (Node.js / NestJS)** using `kafkajs`:
  * Configured with `idempotent: true` and `acks=all` (`-1`).
  * Monitored P99 publish latency: **30 – 50 ms**.
  * Provider callback timeout SLA: **3,000 to 8,000 ms**.

### Consumers:
* **`transactional-engine` (Golang)** using `segmentio/kafka-go`:
  * Consumer Group ID: `{tenant}-backend` (1 pod per tenant).
  * Commit Strategy: **Manual Offset Commit strictly post-DB transaction**.
  * Idempotency Strategy: Unique constraint on `transactionId` in PostgreSQL with `ON CONFLICT DO NOTHING`.
  * Dead Letter Queue (DLQ): Fail-closed to PostgreSQL table `kafka_dlq`.

### Transactional Outbox Pattern:
* Used in Golang engines (`auth-engine`, `transactional-engine`):
  * Application writes business mutations AND pending events into local PostgreSQL table `kafka_outbox` in **one single ACID transaction**.
  * Background daemon (`kafkax.Writer`) reads `kafka_outbox` asynchronously and publishes to Kafka.
  * Guarantees at-least-once delivery even if Kafka brokers undergo transient downtime.

### Analytics Data Pipeline (Google BigQuery):
* **Confluent Managed Connector**: `BigQueryStorageSinkConnector` (Connector ID: `lcc-nvy9oqz`).
* **Transformation**: SMT (Single Message Transform) `ReplaceField$Value` strips heavy debug fields.
* **Target**: Google BigQuery dataset `tokobuah-production.game_reports`.
  * Ingests into partitioned tables `game_transaction_{tenant}_raw`.
  * Unified analytical view: `game_transaction_*` (160M+ historical transaction rows).

---

## 8. SERVERLESS COMPUTE: CLOUD RUN INVENTORY & SCALING

* **Inventory**: 27 Cloud Run services across production (Admin panels, Usersites, landing pages).
* **Scaling Hygiene Optimization**:
  * 26 services already configured with `min-scale: 0` (costing $0 when idle).
  * **`production-admin-ikn788`** (region `asia-east1`) previously had `min-scale: 1`. It has been reconfigured to **`min-scale: 0`**, saving **~$35 / month** in idle compute billing.

---

## 9. CI/CD AUTOMATION (CLOUDBUILD) & GIT REPOSITORIES

### Key Repositories (`/Users/avocado/tokobuah/`):
* `game-engine`: Core provider webhook ingestion engine.
* `transactional-engine-go`: Go ledger consumer.
* `auth-engine-go`: Player authentication and session management.
* `tripay-sc`: Payment gateway microservices (`wl-be`, `wl-callback`, `wl-cron`, `wl-open`).
* `admin-panel` & `user-site`: Next.js / React management and customer frontends.
* `summon-tenant`: Tenant provisioning and HAProxy registration scripts.

### CloudBuild Configuration Update (`tripay-sc`):
* CloudBuild deploy trigger files located in `deploy/cloudbuild/`:
  * `wl-be.staging.yaml`
  * `wl-callback.staging.yaml`
  * `wl-cron.staging.yaml`
  * `wl-open.staging.yaml`
* **Critical Update**: Line 41 updated to target the consolidated cluster:
  ```yaml
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        set -euo pipefail
        gcloud container clusters get-credentials staging-gke-standard --zone=asia-southeast1-a --project=${PROJECT_ID}
        kubectl -n tripay set image deployment/...
  ```
* Committed (`446f627`) and pushed to branch `main` at `git@github.com:tokobuahorganization/tripay-sc.git`.

---

## 10. COST REDUCTION MATRIX & FINANCIAL PROJECTIONS

### Implemented & Realized Savings (November 2026):
| Action Taken | Resource / Component Affected | Monthly Savings (USD) | Monthly Savings (IDR @ 16k) | 2-Month Projection |
| :--- | :--- | :--- | :--- | :--- |
| **Cluster Consolidation** | Deleted `staging-tripay-cluster` (GKE Mgmt Fee + VM node) | ~$121.50 – $170.00 | ~Rp 1.950.000 – 2.720.000 | ~Rp 3.900.000 – 5.440.000 |
| **Cloud Run Min-Scale** | `production-admin-ikn788` scaled from min 1 to 0 | ~$35.00 | ~Rp 560.000 | ~Rp 1.120.000 |
| **TOTAL REALIZED** | | **~$156.50 – $205.00 / mo** | **~Rp 2.510.000 – 3.280.000 / mo** | **~Rp 5.020.000 – 6.560.000** |

### Next-in-Line Optimization Pipeline (Low Traffic Window):
1. **Memorystore Redis Consolidation**:
   * Merge 10 Basic 1GB instances (~88MB total data) into 1-2 instances.
   * Potential Savings: **~$280 – $320 / month (~Rp 4.5 – 5.1 jt/bln)**.
2. **Cloud SQL Tenant Rightsizing**:
   * Downscale tenants `hambabet`, `ikn788`, and `rumushoki` from `db-custom-2-7680` to `db-custom-1-4096`.
   * Potential Savings: **~$160 – $300 / month (~Rp 2.5 – 4.8 jt/bln)**.
3. **GKE `prod-client-cluster` Node Modernization**:
   * Migrate legacy N1 machine types to modern E2 instances (`e2-standard-2`).
   * Potential Savings: **~$135 / month (~Rp 2.1 jt/bln)**.
* **Cumulative Maximum Potential**: **~$780 – $960 / month (~Rp 12.5 – 15.3 juta / bulan)**.

---

## 11. VENDOR EVALUATION REFERENCE: AEROSPIKE VS KAFKA VS REDIS VS POSTGRES

During vendor architecture explorations (e.g. Aerospike meeting, November 2026), maintain the following technical boundaries:
1. **Aerospike vs Kafka**:
   * Aerospike is a High-Performance NoSQL Key-Value / Record Store (Hybrid Memory Architecture: Index in RAM, raw data on NVMe SSD).
   * It is **NOT** a native append-only log and does **NOT** speak Kafka Wire Protocol. Adopting Aerospike requires rewriting client producers/consumers across all Go and NestJS services.
   * Aerospike does not offer a native Zero-ETL BigQuery Storage Sink Connector with SMT; eliminating Kafka would break the direct BigQuery ingestion pipeline.
2. **Aerospike vs Redis**:
   * Aerospike's true competitive advantage is replacing multi-gigabyte or terabyte Redis deployments to save RAM costs.
   * For Tokobuah's current ~88 MB Redis footprint, deploying an Aerospike 3-node NVMe cluster would **increase infrastructure costs**, not decrease them.
3. **Aerospike vs PostgreSQL (CRITICAL RULE)**:
   * **NEVER replace PostgreSQL with Aerospike at the tenant level.**
   * PostgreSQL maintains double-entry accounting ledgers, affiliate downline hierarchies, and complex admin portal reporting via SQL joins and ACID row-locks. Aerospike lacks relational joins and foreign key constraints.
   * If ever evaluated in the future, Aerospike should only act as a high-speed player session/balance cache **in front of** PostgreSQL, never as the System of Record.

---

## 12. AGENT SAFETY & GOVERNANCE GUARDRAILS: PERMISSION & APPROVAL PROTOCOL

> [!IMPORTANT]
> **MANDATORY POLICY FOR ALL AI AGENTS & AUTOMATIONS**  
> Any AI agent operating in this workspace, or in any child/peer conversation room, must adhere strictly to the permission boundaries outlined below. Failure to do so risks catastrophic service disruption, data loss, or unintended financial liabilities.

### Guardrail 1: Production Freeze & Mandatory Approval for Production Changes
* **Scope**: GCP Project `tokobuah-production`, production clusters (`prod-core-cluster`, `prod-client-cluster`, `game-cluster`), production Cloud SQL databases, production HAProxy (`prod-db-proxy`), production Redis, production Cloud Run services, and also:
  * Confluent Cloud Kafka (topics, ACLs, API keys, and the BigQuery sink connector `lcc-nvy9oqz`).
  * BigQuery datasets (e.g. `tokobuah-production.game_reports`).
  * IAM policies, role bindings, and service accounts.
  * Secret Manager secrets.
  * Cloudflare DNS records and proxy settings for production domains.
  * **Production-critical resources hosted in the staging project** — classified by *impact*, not by project or name: `proxy-stg-jkt` and `proxy-stg-sg` (vendor egress proxies, incl. `/home/adminbuah/config-new.json`, `proxy_root` service, their firewall rules, SSH keys, static IPs `proxy-stg-jkt-ip`/`proxy-stg-sg-ip`, and the `default` ↔ `staging-platform-vpc` peering). See §3 *Vendor Egress Proxy VMs*.
* **The Rule**: **NEVER execute ANY mutation, update, restart, deployment, scaling, or configuration change in PRODUCTION autonomously.**
* **Protocol Required Before Action**:
  1. Clearly explain to the user: What change is being planned.
  2. Specify the exact command(s) to be executed.
  3. Identify the blast radius (which tenants/services are affected).
  4. Provide a rollback plan.
  5. **Explicitly ask for user permission** and WAIT for confirmation (e.g., *"lanjutkan"*, *"gas"*, *"eksekusi"*, *"yes"*) before typing or triggering the mutation command.

### Guardrail 2: Strict Ban on Unapproved Deletions (Destructive Commands)
* **Applies to**: **Production AND Staging** (and local workstation for file/git deletions).
* **Scope**: 
  * Kubernetes: `kubectl delete pod/deployment/service/ingress/pvc/secret/configmap/namespace`
  * GCP Resources: `gcloud container clusters delete`, `gcloud compute instances delete`, `gcloud sql instances delete`, `gcloud compute networks subnets delete`, `gcloud compute addresses delete`, `gcloud compute forwarding-rules delete`, `gcloud run services delete`, `gcloud redis instances delete`
  * IaC / Helm: `terraform destroy`, `terraform apply` plans containing destroys, `helm uninstall`
  * Databases: `DROP DATABASE`, `DROP TABLE`, `TRUNCATE`, `DELETE FROM`, `ALTER TABLE ... DROP COLUMN`, `UPDATE ...` **without a `WHERE` clause**
  * Git: `git push --force` / `--force-with-lease`, `git reset --hard`, `git clean -fd`, remote branch deletion
  * Storage: `gsutil rm`, `gcloud storage rm`, bucket deletion
  * Filesystem: `rm -rf`, file deletions outside temporary scratch directories
* **The Rule**: **ZERO DESTRUCTION WITHOUT EXPLICIT PRIOR APPROVAL.**
* **No Confirmation-Bypass Flags**: Never use `--quiet`, `-q`, `-y`, `--yes`, `--force`, or `--auto-approve` on destructive commands. Example commands in this document must not include them either.
* **Context**: Even if an instance, cluster, or subnet is confirmed to be 100% idle, orphaned, or deprecated (e.g. `tripay-gke-subnet`), the agent **MUST NOT** delete it on its own initiative. The agent must present the finding, state that it is safe to delete, and ask: *"Apakah Anda ingin saya menghapus resource ini sekarang?"*. Only proceed when the user gives direct permission.

### Guardrail 3: Permission Required for Modifying / Updating Existing Resources
* **Applies to**: **Production AND Staging**.
* **Scope**:
  * Node pool resizing or scaling limits (`gcloud container clusters/node-pools update/resize`)
  * Cloud SQL instance tier patching / resizing (`gcloud sql instances patch`)
  * Cloud Run configuration updates (`gcloud run services update`)
  * HAProxy configuration edits (`/etc/haproxy/haproxy.cfg`)
  * Memorystore Redis scaling or failovers
  * Kubernetes: `kubectl apply`, `kubectl patch`, `kubectl scale`, `kubectl edit`, `kubectl set image/env`, `helm install/upgrade`
  * IAM / role binding / service account permission changes
  * Creating or changing secrets (Secret Manager, Kubernetes Secrets)
  * Firewall rules and DNS records (GCP and Cloudflare)
  * Confluent Kafka topics/ACLs/connectors and BigQuery dataset/table schema changes
* **Exception (Staging only)**: `kubectl rollout restart` in **staging** may be run without prior approval (inform the user). In **production**, restarts remain under Guardrail 1.
* **The Rule**: Modifying existing active resources can trigger container restarts, connection resets, or failover blips.
* **Protocol**: Always display the proposed configuration diff (YAML or CLI flags) and ask for permission before applying.

### Guardrail 4: Read-Only / Audit Default Principle
* **Trigger Keywords**: When the user asks:
  * *"coba kamu cek"*
  * *"hanya cek aja jangan action apa-apa"*
  * *"kira-kira menurut kamu apa"*
  * *"cuma mau tanya"*
* **The Rule**: The agent's mode is strictly **READ-ONLY AUDIT**.
* **Forbidden**: Do NOT execute any command that mutates state, restarts pods, writes to databases, or modifies files. Only run non-invasive discovery commands (`list`, `describe`, `get`, `cat`, read-only queries, cost calculations).

### Guardrail 5: Sensitive Data, Secret, & Password Protection
* **The Rule**:
  * **NEVER output raw database passwords, private encryption keys, API secrets, or JWT secret keys into chat text or commit messages.**
  * When showing connection strings, always mask credentials (e.g., `postgresql://postgres:********@10.20.16.5:5451/db`).
  * When handling Kubernetes Secrets, do not echo sensitive Base64-decoded payloads unless explicitly asked for troubleshooting a specific variable.

### Guardrail 6: Git & CI/CD Push Protection
* **The Rule**:
  * Before executing `git commit` and `git push` to branches that trigger automated CloudBuild pipelines (especially branch `main`):
  * The agent must run `git diff` first to review all changes.
  * Inform the user of the exact changes and commit message before pushing, unless the user explicitly gave an end-to-end task (e.g. *"ubah code cicd arahin ke tempat baru commit dan push"*).

### Guardrail 7: Blast Radius Containment in Multi-Tenant Environments
* **The Rule**:
  * Tokobuah hosts 11+ independent business tenants. An issue in one tenant must never cascade into another.
  * When debugging or restarting services, isolate changes to that specific tenant namespace or database.
  * Never run unbounded database maintenance scripts across all tenant databases simultaneously without testing on a single staging tenant first.

---

## 13. TECHNICAL OPERATIONAL CAVEATS & GOLDEN RULES

### Caveat 1: Zero-Drift Deployment Protocol
* Before applying any Kubernetes manifest to a new cluster or namespace, inspect and verify:
  1. Secret keys and Base64 contents.
  2. ConfigMap environment variables.
  3. Service ports and backend selectors.
  4. Workload Identity annotations and GCS Fuse CSI volume attributes.

### Caveat 2: Financial Idempotency & Message Safety
* Financial consumers (`transactional-engine`) must **NEVER** use auto-commit (`enable.auto.commit=false`).
* Offsets must only be committed to Kafka **after** the PostgreSQL database transaction completes (`COMMIT`).
* All transactional messages must carry a `transactionId` enforced with a database `UNIQUE` constraint and `ON CONFLICT DO NOTHING`.

### Caveat 3: GCP Load Balancer Rebinding Warmup
* When releasing a GCP Global External Reserved IP (`35.244.234.26`) from an old Ingress and attaching it to a new Ingress:
  * Deleting the old ingress takes ~60-90s to release backend services and forwarding rules.
  * Re-creating the Ingress and forwarding rule takes ~2 minutes.
  * GFE (Google Front End) edge nodes require **2 to 5 minutes** to propagate routes globally. Expect initial HTTP 520 or TCP resets from Cloudflare during this warmup period; do not panic or rollback prematurely.

### Caveat 4: Active Kubeconfig Context
* The current active staging context on the workstation is:
  `gke_tokobuah-staging-499001_asia-southeast1-a_staging-gke-standard`
* `staging-tripay-cluster` context has been permanently removed. Never invoke commands targeting the old cluster.

### Caveat 5: Idle VPC Subnet Policy
* GCP VPC Subnets (such as `tripay-gke-subnet`) cost **$0 / month** when idle.
* However, when decommissioning clusters, prune idle subnets to prevent CIDR block locking (`10.10.48.0/20`) and maintain clean network topologies.
* > ⚠️ **REQUIRES EXPLICIT USER APPROVAL (Guardrail 2).** Present the finding and ask first. Never add `--quiet`; keep the interactive confirmation prompt.
  ```bash
  gcloud compute networks subnets delete tripay-gke-subnet --region=asia-southeast1 --project=tokobuah-staging-499001
  ```

### Caveat 6: Dual-Write Outbox Pattern
* Services mutating PostgreSQL state that also produce events to Kafka must write to the `kafka_outbox` table in the same DB transaction.
* An outbox publisher relay then pushes to Kafka, ensuring zero message loss and complete atomic consistency between the SQL ledger and Kafka.

### Caveat 7: HAProxy Configuration Safe Reload Protocol
* Before reloading HAProxy on `prod-db-proxy` (`10.20.16.5`), always run a syntax verification check:
  ```bash
  sudo haproxy -c -f /etc/haproxy/haproxy.cfg
  ```
* Only reload via `sudo systemctl reload haproxy` if the check returns exit code 0 ("Configuration file is valid").

---

## 14. SECURITY AUDIT PROTOCOLS & NETWORK EXPOSURE VERIFICATION

### The 4-Layer Network Exposure Cross-Check Rule (Anti-Hallucination)
Never declare a Kubernetes or GCP service "publicly exposed" based on a single CLI output. Always cross-check 4 authoritative layers:
1. **Kubectl Output Semantics**: On GKE, `EXTERNAL-IP` in `kubectl get svc` often displays the internal VPC-native ClusterIP when an internal load balancer (ILB) is used. The actual LB IP is in `status.loadBalancer.ingress` (e.g. `10.10.x.x`). Always check annotations `cloud.google.com/load-balancer-type` (`Internal` = L4 ILB) and `networking.gke.io/internal-load-balancer-allow-global-access`.
2. **GKE Node External IPs**: Check `kubectl get nodes -o wide` or `status.addresses[?(@.type=="ExternalIP")]`. If all nodes lack external IPs, NodePort bypass is impossible. If external IPs exist, NodePort (30000-32767) is an actual attack surface.
3. **ESPv2 Public Ingress Endpoints (`*.cloud.goog`)**: For services with ESPv2 sidecars, check if Google Service Management endpoints are active:
   * `gcloud services list --project <PROJECT_ID>`
   * DNS/HTTPS probe to `<service-name>.<project-number>.cloud.goog`
   * Metadata Service Management API (`/v1/services/<name>`) — empty endpoints/visibility means inactive.
4. **Public DNS (`dig`)**: Check the host service name via public DNS (`dig <hostname> +short`). If it returns NXDOMAIN from the public internet, there is no public route.
*Only when all 4 layers confirm isolation can a service be safely classified as strictly internal VPC.*

### Cloud Armor Attachment Verification (Per-Backend, NOT Target-Proxy)
Di project ini, Cloud Armor ter-attach di level **BackendService**, **bukan** di target proxy GCLB maupun via annotation Ingress. Jangan pernah vonis policy "orphan/tidak aktif" hanya dari pemeriksaan target proxy + annotation Ingress (lihat `~/AGENTS.md` §8 — klaim negatif mewajibkan enumerasi semua titik attachment).
* **Attachment chain**: Annotation Service `cloud.google.com/backend-config` → CRD `BackendConfig` GKE (`spec.securityPolicy.name`) → loadbalancer-controller → field `securityPolicy` di `BackendService` (`k8s1-*`).
* **Active policies (live-verified 2026-11-15)**:
  * `cf-origin-lock-production` (`tokobuah-production`): 5 backend game-engine di namespace `game` (cluster `game-cluster`) — `game-engine-all-service`, `game-engine-launcher-service`, `game-engine-pg-service`, `game-engine-pp-service`, `game-engine-transactions-service`.
  * `cf-origin-lock-staging` (`tokobuah-staging-499001`): 10 backend — 5 game-engine (namespace `core`) **+ 3 tripay** (`tripay-be`, `tripay-callback`, `tripay-open`) **+ 2 amp** (`amp-build-service`, `amp-serve-service`, terkonfirmasi drift sweep 2026-11-19).
  * Bentuk rule identik: prio `1000`/`1010` allow Cloudflare IPv4, prio `1020` allow Cloudflare IPv6, prio `2147483647` default `deny(403)`; semua `preview: false` (enforcing, bukan preview).
* **Efek operasional**: Hanya IP proxy Cloudflare yang bisa mencapai backend-backend tersebut via GCLB. Probe langsung dari source IP non-Cloudflare (office, script, kubernetes exec dari VM lain) akan mengembalikan **403 dari Cloud Armor** — gejala yang bisa dikira service down padahal source-lock bekerja sesuai desain. Untuk testing, akses via domain yang di-proxy Cloudflare.
* **Perintah verifikasi**:
  ```bash
  gcloud compute backend-services list --project=<PROJECT_ID> --format="value(name, securityPolicy)"
  kubectl get backendconfig -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name} -> {.spec.securityPolicy.name}{"\n"}{end}'
  ```

### DNS Probe Caveat: Workstation DNS Interception (False "Open Resolver")
The admin workstation's network transparently intercepts outbound DNS (UDP **and** TCP 53): `dig @192.0.2.1 example.com` (TEST-NET, no server exists) still returns an answer. Any "open recursive resolver" finding produced from this workstation is therefore unreliable. Before reporting one:
1. Confirm a firewall rule actually allows tcp/udp 53 to the target.
2. Run the control test `dig @192.0.2.1 example.com +time=2 +tries=1` — if it answers, the result is local interception, not the target.
3. Identify the answering resolver: `dig @<target> o-o.myaddr.l.google.com TXT +short` (an IP that is not the target's = interception).
4. Re-test from a clean vantage point (e.g. Cloud Shell) if needed.

### Minimum Codebase Audit Pattern
1. `git pull --rebase` + check local branch status before auditing.
2. Read all sources (controllers, guards, services, utils, DTOs) — never rely on sampling.
3. Run dependency audits (`npm audit` / `go vet`) and compare local commit against deployed live image to identify version drift.
4. Live read-only checks: probe health endpoints, test auth rejection (unauthenticated, forged token, wrong API key). Never invoke stateful scheduler/mutation endpoints with real credentials.
5. Report findings grouped by severity (Critical, High, Medium, Low, Informational) and always document working security controls (negative findings proving protection).

---

## CHANGELOG

| Version | Date | Changes |
| :--- | :--- | :--- |
| 2.4.0 | 2026-11-17 | **Change applied (user-approved, C4)**: deletion protection on `proxy-stg-jkt` & `proxy-stg-sg`; daily snapshot schedules `proxy-stg-jkt-daily` / `proxy-stg-sg-daily` (7-day retention) attached to their boot disks; TCP:80 uptime checks for both proxies. No restart/downtime. Added email notification channel (admin) and two uptime alert policies (>1 region failing for 2 min). |
| 2.3.0 | 2026-11-17 | **Change applied (user-approved)**: firewall rules `proxy-ssh-allow-trusted` (prio 900) and `proxy-ssh-deny-internet` (prio 950) restrict SSH/RDP on the vendor proxies to IAP, admin workstation egress, and Hermes host. Documented verification results and rollback. Promoted `hermes-agent-host` IP `34.87.88.43` to static address `hermes-agent-host-ip` (same IP, no downtime). |
| 2.2.0 | 2026-11-17 | Classified `proxy-stg-jkt` & `proxy-stg-sg` as **PRODUCTION-CRITICAL** (new §3 *Vendor Egress Proxy VMs*; added to Guardrail 1 scope). Documented proxy inventory, known callers and their egress IPs, network exposure, SPOF on JKT, and hardening backlog. Replaced Cloud NAT paragraph with live NAT inventory and the AUTO_ONLY (ephemeral IP) warning. Added §14 DNS interception caveat (false "open resolver" findings from the workstation). Preserved §14 Cloud Armor section added on 2026-11-15. Added read-only SSH verification results (proxy does not log client IPs; observed caller = prod NAT; SSH login sources). |
| 2.1.0 | 2026-11-14 | Added §12 Agent Safety & Governance Guardrails; renamed former guardrails to §13 Caveats; added Caveat 6–7 and §14 Security Audit Protocols. Corrected Redis inventory from live data (10 instances incl. `prod-pga-redis`, ~88 MB total, staging instances listed). Fixed `asia-southeast1` = Singapore. Guardrail 1 scope extended (Kafka, BigQuery, IAM, Secret Manager, Cloudflare DNS). Guardrails 2 & 3 now explicitly apply to staging; added IaC/git/`UPDATE` without `WHERE`, kubectl apply/patch/scale, no-`--quiet` rule, staging-only `rollout restart` exception. Caveat 5 delete command now requires approval and has `--quiet` removed. Added precedence note pointing to `~/AGENTS.md`. |
| 2.0.0 | 2026-11 | Initial master knowledge base. |

---
*End of Master Infrastructure Knowledge Base.*  
*Maintained by Antigravity Autonomous Coding Agent.*
