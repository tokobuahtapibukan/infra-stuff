#!/usr/bin/env python3
"""Sinkronkan rule allow Cloudflare di policy Cloud Armor origin-lock dengan daftar resmi Cloudflare.

  python3 scripts/cloudarmor_cf_sync.py --env production          # DRY-RUN (default): tampilkan diff + perintah
  python3 scripts/cloudarmor_cf_sync.py --env staging --apply     # minta konfirmasi interaktif, lalu eksekusi

Aturan (lihat ~/AGENTS.md §3): mengubah Cloud Armor = perubahan firewall → WAJIB izin eksplisit user per
environment. Tidak ada flag --yes; konfirmasi harus diketik. Rule yang tidak lagi dibutuhkan TIDAK dihapus
otomatis (§2) — skrip hanya mencetak perintah hapusnya.

Desain rule (mengikuti yang sudah live):
  - Cloud Armor membatasi 10 range per rule → IPv4 dipecah per 10 (prio 1000, 1010, lalu 1001, 1002, …),
    IPv6 di prio 1020 (lanjut 1021, …). Default rule (deny 403) tidak disentuh.
  - Daftar diambil dari https://api.cloudflare.com/client/v4/ips dan divalidasi (success=true, jumlah wajar,
    tiap entri CIDR valid) sebelum dipakai.
"""
import argparse
import ipaddress
import json
import subprocess
import sys
import urllib.request

POLICIES = {
    "production": ("tokobuah-production", "cf-origin-lock-production"),
    "staging": ("tokobuah-staging-499001", "cf-origin-lock-staging"),
}
V4_PRIOS = [1000, 1010, 1001, 1002, 1003]
V6_PRIOS = [1020, 1021, 1022]
CHUNK = 10


def cloudflare_ranges():
    with urllib.request.urlopen("https://api.cloudflare.com/client/v4/ips", timeout=30) as r:
        d = json.load(r)
    if not d.get("success"):
        sys.exit("Cloudflare API: success=false — batal.")
    v4 = sorted({str(ipaddress.ip_network(c)) for c in d["result"]["ipv4_cidrs"]}, key=lambda c: ipaddress.ip_network(c))
    v6 = sorted({str(ipaddress.ip_network(c)) for c in d["result"]["ipv6_cidrs"]}, key=lambda c: ipaddress.ip_network(c))
    if len(v4) < 5 or len(v6) < 3:
        sys.exit(f"Daftar Cloudflare mencurigakan (v4={len(v4)}, v6={len(v6)}) — batal.")
    return v4, v6, d["result"].get("etag", "")


def current_rules(project, policy):
    out = subprocess.run(["gcloud", "compute", "security-policies", "describe", policy,
                          f"--project={project}", "--format=json"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"Gagal membaca policy: {out.stderr.strip()[:200]}")
    pol = json.loads(out.stdout)
    pol = pol[0] if isinstance(pol, list) else pol
    rules = {}
    for r in pol.get("rules", []):
        src = ((r.get("match") or {}).get("config") or {}).get("srcIpRanges") or []
        rules[r["priority"]] = {"action": r.get("action"), "src": sorted(src), "desc": r.get("description", "")}
    return rules


def plan(desired, prios, label, have):
    """Perubahan MINIMAL: range yang sudah ada tidak pernah dipindah antar rule (memindah = jeda 403 di
    antara dua update). Hanya range usang yang dibuang dari rule-nya, dan range baru diisi ke slot kosong.
    Return {prio: (src_list, desc, is_new_rule, only_adds)} untuk rule yang berubah, plus rule yang jadi kosong."""
    want = set(desired)
    cur = {p: set(have[p]["src"]) for p in prios if p in have and have[p]["action"] == "allow"}
    existing = set().union(*cur.values()) if cur else set()
    to_add = sorted(want - existing, key=ipaddress.ip_network)
    new = {p: s & want for p, s in cur.items()}                     # buang yang usang, sisanya tetap di tempatnya
    for p in prios:                                                 # isi range baru ke slot yang masih muat
        while to_add and len(new.setdefault(p, set())) < CHUNK:
            new[p].add(to_add.pop(0))
    if to_add:
        sys.exit(f"Slot prioritas {label} tidak cukup untuk {len(to_add)} range baru — perlu desain ulang.")
    changes, emptied = {}, []
    for i, p in enumerate(prios):
        before, after = cur.get(p, set()), new.get(p, set())
        if after == before:
            continue
        if not after:
            emptied.append(p)
            continue
        changes[p] = (sorted(after, key=ipaddress.ip_network), f"Cloudflare {label} bagian {i + 1}",
                      p not in cur, before <= after)
    return changes, emptied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=POLICIES, required=True)
    ap.add_argument("--apply", action="store_true", help="eksekusi setelah konfirmasi interaktif")
    a = ap.parse_args()
    project, policy = POLICIES[a.env]

    v4, v6, etag = cloudflare_ranges()
    have = current_rules(project, policy)
    ch4, empty4 = plan(v4, V4_PRIOS, "IPv4", have)
    ch6, empty6 = plan(v6, V6_PRIOS, "IPv6", have)
    changes = {**ch4, **ch6}
    stale = sorted(empty4 + empty6)

    cmds, notes = [], []
    # Urutan aman: rule yang hanya MENAMBAH dijalankan dulu, baru rule yang membuang range usang.
    for prio, (src, desc, is_new, only_adds) in sorted(changes.items(), key=lambda kv: (not kv[1][3], kv[0])):
        before = set(have.get(prio, {}).get("src", []))
        notes.append(f"prio {prio}: +{sorted(set(src) - before) or '-'}  -{sorted(before - set(src)) or '-'}")
        verb = ["create", str(prio), "--action=allow", f"--description={desc}"] if is_new else ["update", str(prio)]
        cmds.append(["gcloud", "compute", "security-policies", "rules", *verb,
                     f"--security-policy={policy}", f"--project={project}", f"--src-ip-ranges={','.join(src)}"])

    print(f"Policy {project}/{policy}  —  Cloudflare etag {etag}: IPv4 {len(v4)}, IPv6 {len(v6)}")
    for n in notes:
        print("  CHANGE", n)
    for p in stale:
        print(f"  ⚠️ rule prio {p} tidak dibutuhkan lagi. Hapus MANUAL setelah izin (tidak dijalankan skrip):")
        print(f"     gcloud compute security-policies rules delete {p} --security-policy={policy} --project={project}")
    if not cmds:
        print("✅ Sudah sinkron — tidak ada perubahan.")
        return
    print("\nPerintah yang akan dijalankan:")
    for c in cmds:
        print("  " + " ".join(c))
    if not a.apply:
        print("\nDRY-RUN — tidak ada yang diubah. Jalankan ulang dengan --apply setelah mendapat izin.")
        return
    if input(f"\nKetik nama policy '{policy}' untuk melanjutkan: ").strip() != policy:
        sys.exit("Dibatalkan.")
    # Tambah/perluas dulu sebelum mempersempit tidak relevan di sini: tiap update mengganti 1 rule secara atomik.
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        print(("OK   " if r.returncode == 0 else "FAIL ") + " ".join(c[:6]), (r.stderr.strip()[-200:] if r.returncode else ""))
        if r.returncode != 0:
            sys.exit("Berhenti di kegagalan pertama. Policy mungkin sebagian terupdate — cek & jalankan ulang dry-run.")
    print("Selesai. Verifikasi: jalankan ulang dry-run (harus 'Sudah sinkron') + kartu cloudarmor-cf-ranges-*.")


if __name__ == "__main__":
    main()
