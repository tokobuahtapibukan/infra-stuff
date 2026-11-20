#!/usr/bin/env python3
"""
Drift Engine — Fase 1 (Mac, manual)
Jalankan semua kartu claim aktif di `claims/` secara read-only, bandingkan
hasil vs expected, lalu tulis:
  - drift-results/latest.json  (data mentah per kartu)
  - status-brief.md            (laporan ringkas, generated)

Usage:
  python3 claims/check/drift_engine.py                 # semua kartu aktif
  python3 claims/check/drift_engine.py --card p0-secret-yaml-tracked
  python3 claims/check/drift_engine.py --env production --severity critical
  HUB_TEST_ACCOUNT_A="user:pass" HUB_TEST_ACCOUNT_B="user:pass" python3 ...

Prinsip:
  - Cek = deterministik, TANPA LLM.
  - STALE = cek tidak bisa dijalankan (error/credential hilang).
  - DRIFTED = cek berjalan tapi tidak match expected.
  - Tidak ada secret value yang disimpan/ditampilkan (AGENTS.md §5).
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CLAIMS_DIR = REPO / "claims"
RESULTS_DIR = REPO / "drift-results"
BRIEF_PATH = REPO / "status-brief.md"
RETRY_DELAY = int(os.environ.get("DRIFT_RETRY_DELAY", "20"))


# ───────────────────────── helpers ─────────────────────────

def sh(args, timeout=120):
    """run subprocess; return (rc, combined_output). raise TimeoutError-like via rc=-1."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # timeout, missing binary, ...
        return -1, str(e)


class CheckError(Exception):
    """cek gagal dijalankan → STALE (bukan DRIFTED)."""


_TOKEN_CACHE = {"tok": None, "exp": 0}


def get_gcp_token():
    """Token GCP portabel: (1) gcloud CLI → (2) SA key file → (3) GCE metadata."""
    if _TOKEN_CACHE["tok"] and time.time() < _TOKEN_CACHE["exp"]:
        return _TOKEN_CACHE["tok"]
    tok = None
    # 0. key drift khusus (path JSON dari env — pemisahan viewer-SA utk watchdog)
    drift_key = os.environ.get("DRIFT_GCP_KEY", "")
    if drift_key and os.path.isfile(os.path.expanduser(drift_key)):
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request as _Req
            c = service_account.Credentials.from_service_account_file(
                os.path.expanduser(drift_key),
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            c.refresh(_Req())
            tok = c.token
        except Exception:
            tok = None
    if not tok:
        rc, out = sh(["gcloud", "auth", "print-access-token", "--quiet"], timeout=40)
    if rc == 0 and out.strip().startswith(("1/", "ya29.")):
        tok = out.strip()
    if not tok:
        cands = [
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
            "/app/gcp_key.json",
            os.path.expanduser("~/.config/gcp_key.json"),
            "/home/avocado/gcp_key.json",
        ]
        for p in cands:
            if p and os.path.isfile(p):
                try:
                    from google.oauth2 import service_account
                    from google.auth.transport.requests import Request as _Req
                    creds = service_account.Credentials.from_service_account_file(
                        p, scopes=["https://www.googleapis.com/auth/cloud-platform"])
                    creds.refresh(_Req())
                    tok = creds.token
                    break
                except Exception:
                    continue
    if not tok:
        rc, out = sh(["curl", "-sS", "--max-time", "5",
                      "-H", "Metadata-Flavor: Google",
                      "http://metadata.google.internal/computeMetadata/v1/instance/"
                      "service-accounts/default/token"], timeout=15)
        if rc == 0:
            try:
                tok = json.loads(out).get("access_token")
            except Exception:
                tok = None
    if not tok:
        raise CheckError("token GCP tidak tersedia (gcloud CLI / SA key / metadata)")
    _TOKEN_CACHE.update(tok=tok, exp=time.time() + 240)
    return tok


def api_get(url, timeout=45, want_status=False):
    tok = get_gcp_token()
    cmd = ["curl", "-sS", "--max-time", str(timeout),
           "-H", f"Authorization: Bearer {tok}",
           "-H", "Accept: application/json", url]
    if want_status:
        cmd.insert(2, "-w")
        cmd.insert(3, "\n__HTTP__%{http_code}")
    rc, out = sh(cmd, timeout=timeout + 10)
    if rc != 0:
        raise CheckError(f"API call gagal: {out.strip()[:150]}")
    status = None
    if want_status:
        body, _, st = out.rpartition("__HTTP__")
        out, status = body, st.strip()
    out = out.strip()
    if not out:
        return {} if not want_status else (None, status)
    try:
        d = json.loads(out)
        return d if not want_status else (d, status)
    except json.JSONDecodeError:
        extra = f" (HTTP {status})" if status else ""
        raise CheckError(f"respons API bukan JSON{extra}: {out[:120]}")


def compute_list(path):
    """GET list resource compute v1 global dengan pagination."""
    items, token = [], None
    for _ in range(5):
        u = f"https://compute.googleapis.com/compute/v1/{path}"
        if token:
            u += f"&pageToken={token}"
        else:
            u += "?"
        d = api_get(u)
        items.extend(d.get("items", []))
        token = d.get("nextPageToken")
        if not token:
            break
    return items


def curl_status(url, host_header=None, timeout=30):
    cmd = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout)]
    if host_header:
        cmd += ["-H", f"Host: {host_header}"]
    cmd.append(url)
    rc, out = sh(cmd, timeout=timeout + 10)
    if rc != 0:
        raise CheckError(f"curl gagal: {out.strip()[:150]}")
    return int(out.strip() or 0)


def curl_get(url, host_header=None, timeout=30):
    cmd = ["curl", "-sS", "--max-time", str(timeout)]
    if host_header:
        cmd += ["-H", f"Host: {host_header}"]
    cmd.append(url)
    rc, out = sh(cmd, timeout=timeout + 10)
    if rc != 0:
        raise CheckError(f"curl gagal: {out.strip()[:150]}")
    return out


def semver_key(v):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def find_go_mod(repo_path, max_depth=3):
    p = Path(repo_path)
    if not p.exists():
        raise CheckError(f"repo tidak ditemukan: {p}")
    cands = [f for f in p.rglob("go.mod") if len(f.relative_to(p).parts) <= max_depth]
    if not cands:
        raise CheckError(f"go.mod tidak ditemukan di {p}")
    return sorted(cands)[0]


# ───────────────────────── check tools ─────────────────────────

def chk_gcp_backend_services_policy(args):
    data = compute_list(f"projects/{args['project']}/global/backendServices")
    hits = [b["name"] for b in data if (b.get("securityPolicy") or "").endswith(args["policy_suffix"])]
    return {"count": len(hits), "names": sorted(hits)}


def chk_gcp_target_proxies_no_policy(args):
    total = 0
    details = []
    kinds = ["targetHttpProxies", "targetHttpsProxies", "targetSslProxies", "targetTcpProxies"]
    for proj in args["projects"]:
        for kind in kinds:
            try:
                data = compute_list(f"projects/{proj}/global/{kind}")
            except CheckError:
                continue
            for p in data:
                if p.get("securityPolicy"):
                    total += 1
                    details.append(f"{proj}/{kind}/{p['name']}")
    return {"with_policy": total, "details": details[:10]}


def chk_k8s_ingress_status_ip(args):
    cmd = ["kubectl", "--context", args["context"], "-n", args["namespace"],
           "get", "ingress", args["ingress"],
           "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}"]
    rc, out = sh(cmd, timeout=60)
    if rc != 0 or not out.strip():
        raise CheckError(f"kubectl gagal/kosong: {out.strip()[:150]}")
    return {"ip": out.strip()}


def chk_http_probe_status(args):
    status = curl_status(args["url"], host_header=args.get("host_header"))
    return {"status": status}


def _login(domain, account):
    user, _, pwd = account.partition(":")
    body = json.dumps({"username": user, "password": pwd})
    rc, out = sh(["curl", "-sS", "-X", "POST", "--max-time", "30",
                  "-H", "Content-Type: application/json", "-H", "Accept: application/json",
                  "-d", body, f"https://{domain}/authapi/auth/login"], timeout=45)
    if rc != 0:
        raise CheckError(f"login {domain} gagal: {out[:120]}")
    d = json.loads(out)
    tok = (d.get("data") or {}).get("access_token")
    if not tok:
        raise CheckError(f"login {domain} tidak menghasilkan token: {out[:120]}")
    return tok


def _bearer_get(url, token, timeout=30):
    marker = "\n__STATUS__%{http_code}"
    rc, out = sh(["curl", "-sS", "--max-time", str(timeout),
                  "-H", f"Authorization: Bearer {token}",
                  "-H", "Accept: application/json",
                  "-w", marker, url], timeout=timeout + 10)
    if rc != 0:
        raise CheckError(f"GET gagal: {out[:120]}")
    body, _, status = out.rpartition("__STATUS__")
    st = int(status.strip() or 0)
    try:
        return st, json.loads(body)
    except Exception:
        return st, {"raw": body[:200]}


def chk_cross_tenant_probe(args):
    acct_a = os.environ.get("HUB_TEST_ACCOUNT_A", "")
    acct_b = os.environ.get("HUB_TEST_ACCOUNT_B", "")
    if not acct_a or not acct_b:
        raise CheckError("credential test account belum di-set (env HUB_TEST_ACCOUNT_A/B) — "
                         "ini STALE, bukan drift")
    da, db, path = args["domain_a"], args["domain_b"], args["path"]
    tok_a = _login(da, acct_a)
    tok_b = _login(db, acct_b)
    # token B di domain A (harus ditolak)
    st1, j1 = _bearer_get(f"https://{da}{path}", tok_b)
    code1 = ((j1.get("error") or {}).get("code")) if isinstance(j1, dict) else None
    # token A di domain B (harus ditolak)
    st2, j2 = _bearer_get(f"https://{db}{path}", tok_a)
    code2 = ((j2.get("error") or {}).get("code")) if isinstance(j2, dict) else None
    return {
        "status": st1,
        "error_code": code1,
        "_other_direction": {"status": st2, "error_code": code2},
    }


def chk_gcp_gke_cluster_absent(args):
    """Endpoint /global/clusters sudah DEPRECATED (404 per 2026); pakai locations/-."""
    names = []
    try:
        d = api_get(f"https://container.googleapis.com/v1/projects/{args['project']}/locations/-/clusters")
        names = [c.get("name") for c in d.get("clusters", [])]
    except CheckError:
        rc, out = sh(["gcloud", "container", "clusters", "list",
                      "--project", args["project"], "--format", "value(name)"], timeout=120)
        if rc != 0:
            raise CheckError(f"GKE REST (locations/-) gagal DAN gcloud CLI gagal: {out.strip()[:150]}")
        names = [l for l in out.split() if l]
    return {"exists": args["name"] in names, "live_clusters": names}


def chk_gcp_target_http_proxies_prefix_count(args):
    data = compute_list(f"projects/{args['project']}/global/targetHttpProxies")
    names = [p["name"] for p in data if p["name"].startswith(args["name_prefix"])]
    return {"count": len(names), "names": sorted(names)}


def chk_git_ls_files_count(args):
    repos = [args["repo"]] if args.get("repo") else list(args.get("repos") or [])
    pat = re.compile(args["pattern"])
    total, files, missing = 0, [], []
    for rp in repos:
        repo = Path(os.path.expanduser(rp))
        rc0, _ = sh(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"], timeout=30)
        if rc0 != 0:
            missing.append(str(repo))
            continue
        rc, out = sh(["git", "-C", str(repo), "ls-files"], timeout=60)
        if rc != 0:
            raise CheckError(f"git ls-files gagal di {repo}: {out[:120]}")
        for l in out.splitlines():
            if pat.search(l):
                total += 1
                if len(files) < 30:
                    files.append(f"{Path(rp).name}:{l}")
    if missing:
        raise CheckError(f"repo tidak ada di host ini: {', '.join(missing)}")
    return {"count": total, "files": files}


def chk_gomod_version_below(args):
    details = {}
    under = 0
    for r in args["repos"]:
        gmod = find_go_mod(os.path.expanduser(r))
        txt = gmod.read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^\s*{re.escape(args['module'])}\s+v[\w.+~-]+", txt, re.M)
        if not m:
            details[r] = "not-declared"
            continue
        ver = m.group(0).split()[-1]
        details[r] = ver
        if semver_key(ver) < semver_key(args["below"]):
            under += 1
    return {"count_below": under, "details": details}


def _home_fingerprint(domain):
    html = curl_get(f"https://{domain}/", timeout=30)
    fonts = sorted(set(re.findall(r"/_next/static/media/([0-9a-zA-Z._-]+?\.woff2)", html)))
    return ("200" if len(html) > 1000 else "000"), fonts[:5]


def chk_domain_sibling_app_match(args):
    live_p, fp_p = _home_fingerprint(args["primary"])
    live_s, fp_s = _home_fingerprint(args["sibling"])
    return {
        "sibling_live": live_s == "200",
        "same_app": bool(fp_s) and bool(fp_p) and any(f in fp_p for f in fp_s),
        "_fingerprint_s": fp_s,
        "_fingerprint_p": fp_p,
    }


def chk_gcs_level_image_public(args):
    dom = args["api_domain"]
    out = curl_get(f"https://{dom}/beapi/public/levels", timeout=30)
    d = json.loads(out)
    lvls = (d.get("data") or {}).get("levels") or []
    img = next((l.get("image_url") for l in lvls if l.get("image_url")), None)
    if not img:
        raise CheckError("tidak ada image_url di /beapi/public/levels")
    status = curl_status(img, timeout=30)
    return {"status": status}


def chk_js_bundle_contains_url(args):
    dom = args["domain"]
    needle = args["needle"]
    html = curl_get(f"https://{dom}/", timeout=30)
    chunks = sorted(set(re.findall(r"/_next/static/chunks/[0-9a-zA-Z._-]+?\.js", html)))
    for c in chunks:
        js = curl_get(f"https://{dom}{c}", timeout=30)
        if needle in js:
            return {"found": True, "_chunk": c, "_chunks_scanned": len(chunks)}
    return {"found": False, "_chunks_scanned": len(chunks)}


def chk_k8s_deployments_healthy(args):
    """Semua deployment di namespace harus ready (availableReplicas >= 1 atau spec 0)."""
    ctx = args.get("context")
    ns = args["namespaces"] if isinstance(args["namespaces"], list) else [args["namespaces"]]
    bad, total = [], 0
    for n in ns:
        cmd = ["kubectl"]
        if ctx:
            cmd += ["--context", ctx]
        cmd += ["-n", n, "get", "deployments", "-o", "json"]
        rc, out = sh(cmd, timeout=90)
        if rc != 0:
            raise CheckError(f"kubectl ns {n} gagal: {out.strip()[:150]}")
        items = json.loads(out).get("items", [])
        total += len(items)
        for dep in items:
            name = dep["metadata"]["name"]
            spec = dep.get("spec", {}).get("replicas", 1)
            avail = (dep.get("status") or {}).get("availableReplicas", 0)
            if spec > 0 and avail < spec:
                bad.append(f"{n}/{name} ({avail}/{spec} available)")
    return {"deployments_total": total, "unhealthy": len(bad), "unhealthy_list": bad[:10]}


def chk_repo_grep_count(args):
    """Hitung baris yang match regex di file-file repo (1 atau banyak repo, glob path opsional)."""
    repos = [args["repo"]] if args.get("repo") else list(args.get("repos") or [])
    pat = re.compile(args["pattern"])
    file_glob = args.get("files", "**")
    count, hits, missing = 0, [], []
    for rp in repos:
        repo = Path(os.path.expanduser(rp))
        if not repo.exists():
            missing.append(str(repo))
            continue
        for f in repo.glob(file_glob):
            if not f.is_file() or ".git" in f.parts:
                continue
            if f.stat().st_size > 2_000_000:
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if pat.search(line):
                        count += 1
                        if len(hits) < 10:
                            hits.append(f"{repo.name}/{f.name}:{i}: {line.strip()[:90]}")
            except OSError:
                continue
    if missing:
        raise CheckError(f"repo tidak ada di host ini: {', '.join(missing)}")
    return {"count": count, "hits": hits}


def chk_http_json_field(args):
    out = curl_get(args["url"], host_header=args.get("host_header"), timeout=30)
    d = json.loads(out)
    val = d
    for part in args["field_path"].split("."):
        val = val.get(part) if isinstance(val, dict) else None
    return {"value": val}


def chk_http_header_contains(args):
    rc, out = sh(["curl", "-sS", "-D", "-", "-o", "/dev/null", "--max-time", "30", args["url"]], timeout=40)
    if rc != 0:
        raise CheckError(f"curl gagal: {out[:120]}")
    headers = "\n".join(l for l in out.splitlines() if ":" in l).lower()
    present = args["header"].lower() in headers
    contains = (args.get("contains") or "").lower() in headers if args.get("contains") else present
    return {"header_present": present, "contains": contains}


import hashlib


def chk_iam_policy_hash(args):
    """Hash deterministik dari set role yang diikat ke sebuah member (SA) di project.
    Deteksi 'siapa pun mengubah izin SA' — self-monitoring. (gcloud CLI; REST IAM 404 di env ini)"""
    rc, out = sh(["gcloud", "projects", "get-iam-policy", args["project"],
                  "--format=json"], timeout=120)
    if rc != 0:
        raise CheckError(f"get-iam-policy gagal: {out.strip()[:150]}")
    d = json.loads(out)
    roles = sorted({b["role"] for b in d.get("bindings", [])
                    if any(args["member_contains"] in m for m in b.get("members", []))})
    h = hashlib.sha256("|".join(roles).encode()).hexdigest()[:16]
    return {"roles": roles, "hash": h}


def chk_gcp_firewall_sources(args):
    """Self-monitoring: sourceRanges rule firewall tetap terkunci + tidak ada rule RDP baru."""
    proj = args["project"]
    expected = set(args["expected_sources"])
    rules = compute_list(f"projects/{proj}/global/firewalls")
    ok, detail = True, []
    for name in args["rules"]:
        r = next((x for x in rules if x["name"] == name), None)
        if r is None:
            ok = False; detail.append(f"{name}: rule hilang")
            continue
        src = set(r.get("sourceRanges") or [])
        if src != expected:
            ok = False; detail.append(f"{name}: {sorted(src)} != {sorted(expected)}")
    rdp = [x["name"] for x in rules
           if any(a.get("IPProtocol") == "tcp" and "3389" in (a.get("ports") or [])
                  for a in (x.get("allowed") or []))]
    return {"ssh_sources_ok": ok, "rdp_rule_count": len(rdp), "_detail": detail, "_rdp": rdp}


def chk_git_commit_age(args):
    if args["repo"] == "DRIFT_REGISTRY":
        env = os.environ.get("DRIFT_REGISTRY_PATH", "")
        repo = Path(os.path.expanduser(env)) if env else None
        if repo is None or not repo.exists():
            repo = None
            for cand in ("/registry/infra-stuff",
                         os.path.expanduser("~/tokobuah/infra-stuff"),
                         "/home/avocado/tokobuah/infra-stuff"):
                if Path(cand).exists():
                    repo = Path(cand)
                    break
        if repo is None:
            raise CheckError("registry drift tidak ditemukan di host ini")
    else:
        repo = Path(os.path.expanduser(args["repo"]))
    rc, out = sh(["git", "-C", str(repo), "log", "-1", "--author=" + args["author_pattern"],
                  "--format=%ct"], timeout=60)
    if rc != 0 or not out.strip():
        return {"age_hours": None, "last_commit": None}
    age_h = (time.time() - int(out.strip())) / 3600
    return {"age_hours": round(age_h, 1), "last_commit": out.strip()}


def chk_lb_log_coverage(args):
    """Semua public global HTTP LB (forwarding rule) production HARUS muncul di
    log http_load_balancer 7 hari terakhir (mekanisme scan 7-day hub)."""
    proj = args["project"]
    frs = compute_list(f"projects/{proj}/global/forwardingRules")
    live = {f["name"] for f in frs
            if f.get("networkTier") == "PREMIUM"
            and (f.get("target") or "").endswith("targetHttpProxies")
            and f.get("ipAddresses")}
    # logging API
    tok = get_gcp_token()
    since = datetime.now(timezone.utc).timestamp() - 7 * 86400
    since_s = datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logged = set()
    token_page = None
    for _ in range(4):  # max 4 page x 1000
        payload = {
            "resourceNames": [f"projects/{proj}"],
            "filter": f'timestamp >= "{since_s}" AND resource.type="http_load_balancer"',
            "orderBy": "timestamp desc",
            "pageSize": 1000,
        }
        if token_page:
            payload["pageToken"] = token_page
        body = json.dumps(payload)
        rc2, out2 = sh(["curl", "-sS", "--max-time", "60",
                        "-X", "POST", "https://logging.googleapis.com/v2/entries:list",
                        "-H", f"Authorization: Bearer {tok.strip()}",
                        "-H", "Content-Type: application/json", "-d", body], timeout=90)
        if rc2 != 0:
            raise CheckError(f"logging API gagal: {out2[:150]}")
        d = json.loads(out2)
        for e in d.get("entries", []):
            fn = ((e.get("resource") or {}).get("labels") or {}).get("forwarding_rule_name")
            if fn:
                logged.add(fn)
        token_page = d.get("nextPageToken")
        if not token_page:
            break
    uncovered = sorted(live - logged)
    return {"uncovered": uncovered, "live_lb_count": len(live), "logged_lb_count": len(logged & live)}


def chk_gcp_gke_nodepool_autoscaling(args):
    """Bound autoscaling + shape sebuah node pool (GKE REST, read-only).
    Key output sengaja tidak berakhiran _min/_max/_in agar tidak bentrok dgn komparator verify()."""
    url = (f"https://container.googleapis.com/v1/projects/{args['project']}/locations/"
           f"{args['location']}/clusters/{args['cluster']}/nodePools/{args['pool']}")
    d = api_get(url)
    if not d.get("name"):
        raise CheckError(f"node pool {args['pool']} tidak ditemukan: {str(d)[:120]}")
    a = d.get("autoscaling") or {}
    cfg = d.get("config") or {}
    return {
        "autoscaling_enabled": bool(a.get("enabled")),
        "autoscale_lo": a.get("minNodeCount", a.get("totalMinNodeCount", 0)) if a.get("enabled") else None,
        "autoscale_hi": a.get("maxNodeCount", a.get("totalMaxNodeCount")) if a.get("enabled") else None,
        "machine_type": cfg.get("machineType"),
        "spot": bool(cfg.get("spot") or cfg.get("preemptible")),
    }


def chk_gcp_scheduler_jobs_prefix_count(args):
    """Hitung job Cloud Scheduler dengan prefix nama tertentu (+ berapa yang ENABLED)."""
    url = (f"https://cloudscheduler.googleapis.com/v1/projects/{args['project']}/locations/"
           f"{args['location']}/jobs?pageSize=500")
    d = api_get(url)
    if "error" in d:
        raise CheckError(f"Cloud Scheduler API error: {str(d['error'])[:150]}")
    jobs = [j for j in d.get("jobs", [])
            if j.get("name", "").rsplit("/", 1)[-1].startswith(args["name_prefix"])]
    return {
        "count": len(jobs),
        "enabled_count": sum(1 for j in jobs if j.get("state") == "ENABLED"),
        "names": sorted(j["name"].rsplit("/", 1)[-1] for j in jobs),
    }


def chk_k8s_namespace_labels(args):
    """Pastikan namespace membawa label tertentu (mis. label atribusi billing)."""
    ctx = args.get("context")
    missing = []
    for ns, want in args["labels"].items():
        cmd = ["kubectl"] + (["--context", ctx] if ctx else []) + ["get", "namespace", ns, "-o", "json"]
        rc, out = sh(cmd, timeout=60)
        if rc != 0:
            raise CheckError(f"kubectl ns {ns} gagal: {out.strip()[:150]}")
        have = (json.loads(out).get("metadata") or {}).get("labels") or {}
        for k, v in want.items():
            if have.get(k) != v:
                missing.append(f"{ns}: {k}={v} (live: {have.get(k)!r})")
    return {"missing": len(missing), "_detail": missing}


def chk_gcp_instance_shape(args):
    """Shape VM: machine type, vCPU, RAM (MB), status (Compute REST, read-only)."""
    base = f"https://compute.googleapis.com/compute/v1/projects/{args['project']}/zones/{args['zone']}"
    inst = api_get(f"{base}/instances/{args['instance']}")
    if not inst.get("machineType"):
        raise CheckError(f"instance {args['instance']} tidak ditemukan: {str(inst)[:120]}")
    mt_name = inst["machineType"].rsplit("/", 1)[-1]
    mt = api_get(f"{base}/machineTypes/{mt_name}")
    return {
        "status": inst.get("status"),
        "machine_type": mt_name,
        "vcpus": mt.get("guestCpus"),
        "memory_mb": mt.get("memoryMb"),
        "provisioning_model": (inst.get("scheduling") or {}).get("provisioningModel", "STANDARD"),
    }


CHECKS = {
    "gcp_backend_services_policy": chk_gcp_backend_services_policy,
    "gcp_target_proxies_no_policy": chk_gcp_target_proxies_no_policy,
    "k8s_ingress_status_ip": chk_k8s_ingress_status_ip,
    "http_probe_status": chk_http_probe_status,
    "cross_tenant_probe": chk_cross_tenant_probe,
    "gcp_gke_cluster_absent": chk_gcp_gke_cluster_absent,
    "gcp_target_http_proxies_prefix_count": chk_gcp_target_http_proxies_prefix_count,
    "git_ls_files_count": chk_git_ls_files_count,
    "gomod_version_below": chk_gomod_version_below,
    "domain_sibling_app_match": chk_domain_sibling_app_match,
    "gcs_level_image_public": chk_gcs_level_image_public,
    "js_bundle_contains_url": chk_js_bundle_contains_url,
    "k8s_deployments_healthy": chk_k8s_deployments_healthy,
    "repo_grep_count": chk_repo_grep_count,
    "http_json_field": chk_http_json_field,
    "http_header_contains": chk_http_header_contains,
    "iam_policy_hash": chk_iam_policy_hash,
    "gcp_firewall_sources": chk_gcp_firewall_sources,
    "git_commit_age": chk_git_commit_age,
    "compare_lb_inventory_vs_hub_scan_targets": chk_lb_log_coverage,
    "gcp_gke_nodepool_autoscaling": chk_gcp_gke_nodepool_autoscaling,
    "gcp_scheduler_jobs_prefix_count": chk_gcp_scheduler_jobs_prefix_count,
    "k8s_namespace_labels": chk_k8s_namespace_labels,
    "gcp_instance_shape": chk_gcp_instance_shape,
}


# ───────────────────────── verify & run ─────────────────────────

def verify(expect, actual):
    """bandingkan per-key; support: equality biasa, '<key>_in' (membership), '<key>_min' (>=)."""
    ok = True
    detail = []
    for k, v in expect.items():
        if k.endswith("_in"):
            key, allowed = k[:-3], v
            av = actual.get(key)
            if av not in allowed:
                ok = False
                detail.append(f"{key}: expect salah satu {allowed}, got {av!r}")
        elif k.endswith("_min"):
            key, floor = k[:-4], v
            av = actual.get(key)
            try:
                if av is None or av < floor:
                    ok = False
                    detail.append(f"{key}: expect >={floor}, got {av!r}")
            except TypeError:
                ok = False
                detail.append(f"{key}: tidak bisa dibandingkan ({av!r})")
        elif k.endswith("_max"):
            key, ceil = k[:-4], v
            av = actual.get(key)
            try:
                if av is None or av > ceil:
                    ok = False
                    detail.append(f"{key}: expect <={ceil}, got {av!r}")
            except TypeError:
                ok = False
                detail.append(f"{key}: tidak bisa dibandingkan ({av!r})")
        else:
            av = actual.get(k)
            if av != v:
                ok = False
                detail.append(f"{k}: expect {v!r} got {av!r}")
    return ok, "; ".join(detail) or "ok"


def load_cards():
    cards = []
    for f in sorted(CLAIMS_DIR.rglob("*.yaml")):
        c = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not c or c.get("status") != "active":
            continue
        c["_file"] = str(f.relative_to(REPO))
        cards.append(c)
    return cards


RECHECK_HOURS = {"12h": 12, "24h": 24, "7d": 168}


def _atomic_write(path: Path, text: str):
    """tulis ke tmp lalu rename (hindari file setengah-jadi bila proses terinterupsi)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_last_runs():
    """ambil run-at terakhir per kartu dari latest.json (untuk honour recheck interval)."""
    f = RESULTS_DIR / "latest.json"
    if not f.exists():
        return {}, {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        runs = {r["id"]: r.get("at") or d.get("run_at") for r in d.get("results", [])}
        prev_status = {r["id"]: {"status": r.get("status"), "at": r.get("at"), "detail": r.get("detail")}
                       for r in d.get("results", [])}
        return runs, prev_status
    except Exception:
        return {}, {}


def due_now(card, last_runs):
    """True jika kartu sudah masuk jadwal recheck (default engine menghormati interval)."""
    last = last_runs.get(card["id"])
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last)
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return True
    return age_h >= RECHECK_HOURS.get(card.get("recheck", "24h"), 24)


def run_card(card):
    # kartu lokal-only (cek repo di host ini): skip rapi kalau reponya tidak ada
    if card.get("local_only"):
        args = card["check"].get("args") or {}
        paths = [args.get("repo", "")] + list(args.get("repos") or [])
        if paths and not any(Path(os.path.expanduser(p)).exists() for p in paths if p):
            return {"status": "SKIPPED", "reason": "local_only: repo tidak ada di host ini (dijalankan di Mac)"}
    # kartu yang butuh binary tertentu (mis. kubectl): skip rapi kalau tidak tersedia
    for tool in (card.get("requires_tools") or []):
        rc, _ = sh(["which", tool], timeout=10)
        if rc != 0:
            return {"status": "SKIPPED", "reason": f"env: '{tool}' tidak tersedia di host ini"}
    tool = card["check"]["tool"]
    fn = CHECKS.get(tool)
    if fn is None:
        return {"status": "STALE", "reason": f"tool '{tool}' belum diimplementasi di engine"}
    attempts = int(card.get("retry", 1))
    last = None
    for i in range(attempts):
        try:
            actual = fn(card["check"]["args"])
            ok, detail = verify(card["expect"], actual)
            if ok:
                return {"status": "VERIFIED", "expect": card["expect"],
                        "actual": {k: v for k, v in actual.items() if not k.startswith("_")},
                        "_actual_full": actual, "detail": detail, "attempts": i + 1}
            last = {"status": "DRIFTED", "expect": card["expect"],
                    "actual": {k: v for k, v in actual.items() if not k.startswith("_")},
                    "_actual_full": actual, "detail": detail, "attempts": i + 1}
        except CheckError as e:
            last = {"status": "STALE", "reason": str(e), "attempts": i + 1}
        except Exception as e:  # noqa
            last = {"status": "STALE", "reason": f"error tak terduga: {e}", "attempts": i + 1}
        if i < attempts - 1:
            time.sleep(RETRY_DELAY)
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card")
    ap.add_argument("--env")
    ap.add_argument("--severity")
    ap.add_argument("--force-all", action="store_true",
                    help="abaikan interval recheck (jalan semua kartu sekarang)")
    args = ap.parse_args()

    cards = load_cards()
    if args.card:
        cards = [c for c in cards if c["id"] == args.card]
    if args.env:
        cards = [c for c in cards if c.get("env") in (args.env, "both")]
    if args.severity:
        cards = [c for c in cards if c.get("severity") == args.severity]
    if not cards:
        print("tidak ada kartu yang sesuai filter")
        sys.exit(1)

    last_runs, prev_status = ({}, {}) if args.force_all else load_last_runs()
    results = []
    for c in cards:
        if not args.force_all and not due_now(c, last_runs):
            prev = prev_status.get(c["id"]) or {}
            results.append({"id": c["id"], "service": c.get("service"), "env": c.get("env"),
                            "severity": c.get("severity"), "claim": c.get("claim"),
                            "card_file": c["_file"], "status": "SKIPPED",
                            "reason": f"masih dalam jendela recheck {c.get('recheck','24h')}",
                            "carried_status": prev.get("status"),
                            "carried_at": prev.get("at")})
            print(f"⏭️ [SKIPPED  ] {c['id']:36s} (recheck {c.get('recheck','24h')}, last: {prev.get('status','?')})")
            continue
        icon = {"critical": "‼", "warn": "△", "info": "·"}.get(c.get("severity"), " ")
        r = run_card(c)
        r["at"] = datetime.now(timezone.utc).isoformat()
        results.append({"id": c["id"], "service": c.get("service"), "env": c.get("env"),
                        "severity": c.get("severity"), "claim": c.get("claim"),
                        "card_file": c["_file"], **r})
        mark = {"VERIFIED": "✅", "DRIFTED": "❌", "STALE": "⚠️", "SKIPPED": "⏭️"}[r["status"]]
        extra = r.get("detail") or r.get("reason") or ""
        print(f"{mark} [{r['status']:9s}] {icon} {c['id']:36s} {extra}")

    # kartu SKIPPED: catat last_run dari run sebelumnya (bukti masih terawati)
    for r in results:
        if r["status"] == "SKIPPED":
            r["last_run"] = last_runs.get(r["id"])
    now = datetime.now(timezone.utc)
    checked = [r for r in results if r["status"] != "SKIPPED"]
    summ = {"verified": sum(r["status"] == "VERIFIED" for r in checked),
            "drifted": sum(r["status"] == "DRIFTED" for r in checked),
            "stale": sum(r["status"] == "STALE" for r in checked),
            "skipped": sum(r["status"] == "SKIPPED" for r in results)}

    RESULTS_DIR.mkdir(exist_ok=True)
    _atomic_write(RESULTS_DIR / "latest.json",
        json.dumps({"run_at": now.isoformat(), "engine": "drift_engine v1",
                    "cards_total": len(checked), "skipped_total": summ["skipped"],
                    "summary": summ, "results": checked,
                    "skipped": [r["id"] for r in results if r["status"] == "SKIPPED"]},
                   indent=1))
    write_brief(results, now, summ)
    print(f"\nTotal {len(checked)} kartu dicek: {summ['verified']} verified · "
          f"{summ['drifted']} drifted · {summ['stale']} stale "
          f"(+{summ['skipped']} skipped dalam jendela recheck)")
    print(f"Brief: {BRIEF_PATH}")


def write_brief(results, now, summ):
    lines = []
    a = lines.append
    checked = [r for r in results if r["status"] != "SKIPPED"]
    a("# STATUS BRIEF")
    a("")
    a("> ⚠️ FILE INI **GENERATED** oleh drift engine — jangan edit manual.")
    a(f"> Last sweep: **{now.strftime('%Y-%m-%d %H:%M UTC')}** · engine: `drift_engine v1`")
    a("")
    a(f"**Sweep ini: {len(checked)} kartu dicek · ✅ {summ['verified']} verified · "
      f"❌ {summ['drifted']} drift · ⚠️ {summ['stale']} stale · "
      f"⏭️ {summ.get('skipped', 0)} carry-forward (dalam jendela recheck)**")
    a("")
    carried = [r for r in results if r["status"] == "SKIPPED"]
    if carried:
        ok_c = sum(1 for r in carried if r.get("carried_status") == "VERIFIED")
        bad_c = [r for r in carried if r.get("carried_status") in ("DRIFTED", "STALE")]
        a(f"**Carry-forward {len(carried)} kartu** (terakhir dicek {(carried[0].get('carried_at') or '?')[:16].replace('T',' ')}): "
          f"{ok_c} terakhir VERIFIED" + (f", ⚠️ {len(bad_c)} masih belum sehat: " + ", ".join(f'`{r["id"]}` ({r.get("carried_status")})' for r in bad_c) if bad_c else ""))
        a("")
    a("## Per environment (sweep ini)")
    a("")
    a("| Env | Verified | Drift | Stale |")
    a("|---|---|---|---|")
    for env in ("production", "staging", "both"):
        rs = [r for r in checked if r.get("env") == env]
        if not rs:
            continue
        a(f"| {env} | {sum(r['status']=='VERIFIED' for r in rs)} | "
          f"{sum(r['status']=='DRIFTED' for r in rs)} | {sum(r['status']=='STALE' for r in rs)} |")
    a("")
    drifted = [r for r in results if r["status"] == "DRIFTED"]
    stale = [r for r in results if r["status"] == "STALE"]
    a("## ❌ Drift")
    a("")
    if drifted:
        for r in drifted:
            a(f"- **`{r['id']}`** ({r.get('service')}, {r.get('env')}): {r.get('detail')}")
            a(f"  - claim: {r.get('claim')}")
            a(f"  - kartu: `{r.get('card_file')}`")
    else:
        a("- (tidak ada — semua klaim sesuai ekspektasi)")
    a("")
    a("## ⚠️ Stale (cek tidak bisa dijalankan)")
    a("")
    if stale:
        for r in stale:
            a(f"- **`{r['id']}`**: {r.get('reason')}")
    else:
        a("- (tidak ada)")
    a("")
    a("## 📋 Fix-tracking (open items yang sedang di-follow)")
    a("")
    ft = [r for r in checked if r.get("card_file", "").startswith("claims/fix-tracking/")] + \
         [r for r in carried if r.get("card_file", "").startswith("claims/fix-tracking/")]
    if ft:
        for r in ft:
            st = {"VERIFIED": "✅", "DRIFTED": "❌", "STALE": "⚠️"}.get(r["status"], "⏭️")
            note = "" if r["status"] != "SKIPPED" else f" (carry: {r.get('carried_status','?')})"
            a(f"- {st} `{r['id']}`{note} — {r.get('claim','')[:110]}")
    else:
        a("- (belum ada)")
    a("")
    _atomic_write(BRIEF_PATH, "\n".join(lines))


if __name__ == "__main__":
    main()
