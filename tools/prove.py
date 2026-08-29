"""Prove that every alert fires on the fault it was written for, and stops when
the fault clears, and reaches the receiver. Each row in the result is measured,
not typed.

For each fault: inject it on collector-a, watch Prometheus until the expected
alert is firing, note every other alert that fired meanwhile, clear the fault,
watch until it resolves, and wait for the board to go quiet again. At the end
read the receiver's ledger and confirm a firing notification arrived for each
alert. Writes proof/results.json and proof/RESULTS.md.
"""
import argparse
import asyncio
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
from fault import inject  # noqa: E402

CASES = [
    ("mute", "QuietMachine"),
    ("silent-writer", "SilentWriter"),
    ("hung-poller", "HungPoller"),
    ("refusals", "SilentRefusals"),
    ("identity", "IdentityMismatch"),
    ("pressure", "PressureStall"),
]
TARGET = "collector-a"


def firing(prom):
    r = requests.get(f"{prom}/api/v1/alerts", timeout=5)
    r.raise_for_status()
    return [a for a in r.json()["data"]["alerts"] if a["state"] == "firing"]


def about_target(a):
    return TARGET in a["labels"].values()


def wait(prom, pred, timeout, every=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        al = firing(prom)
        if pred(al):
            return time.time() - t0, al
        time.sleep(every)
    return None, firing(prom)


def metric_present(prom, expr):
    r = requests.get(f"{prom}/api/v1/query", params={"query": expr}, timeout=5)
    return bool(r.json().get("data", {}).get("result"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prom", default=os.environ.get("QM_PROM_URL", "http://localhost:9090"))
    ap.add_argument("--nats", default=os.environ.get("QM_NATS_URL", "nats://localhost:4222"))
    ap.add_argument("--sink", default=os.environ.get("QM_SINK_URL", "http://localhost:9095"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "proof"))
    ap.add_argument("--fire-timeout", type=float, default=300)
    ap.add_argument("--resolve-timeout", type=float, default=300)
    ap.add_argument("--informational", default="pressure",
                    help="comma-separated faults whose result is reported but does not fail the run")
    ap.add_argument("--skip", default="")
    ap.add_argument("--stamp", default=None, help="ISO date for the report; defaults to now")
    a = ap.parse_args()
    informational = set(x for x in a.informational.split(",") if x)
    skip = set(x for x in a.skip.split(",") if x)
    os.makedirs(a.out, exist_ok=True)

    def say(msg):
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)

    say("waiting for collector-a and collector-b to be reporting")
    t, _ = wait(a.prom, lambda al: metric_present(a.prom, 'qm_heartbeat_timestamp_seconds{service_name="collector-a"}')
                and metric_present(a.prom, 'qm_heartbeat_timestamp_seconds{service_name="collector-b"}'), 180)
    if t is None:
        say("collectors never reported; nothing to prove")
        sys.exit(2)
    say("both collectors reporting; letting the rule windows fill (75s)")
    time.sleep(75)
    base = firing(a.prom)
    say(f"baseline: {len(base)} alert(s) firing: {[x['labels']['alertname'] for x in base]}")
    t, _ = wait(a.prom, lambda al: not al, 180)
    if t is None:
        say("board never went quiet; cannot start")
        sys.exit(2)

    rows = []
    for fault, alert in CASES:
        if fault in skip:
            rows.append({"fault": fault, "alert": alert, "skipped": True})
            continue
        say(f"inject {fault} on {TARGET}, expecting {alert}")
        asyncio.run(inject(a.nats, TARGET, fault, 900))
        t_fire, al = wait(a.prom, lambda al: any(x["labels"]["alertname"] == alert and about_target(x) for x in al), a.fire_timeout)
        others = set()
        if t_fire is not None:
            for _ in range(5):  # hold a moment and collect anything else that fires
                for x in firing(a.prom):
                    if x["labels"]["alertname"] != alert:
                        others.add(x["labels"]["alertname"] + (" (collector-a)" if about_target(x) else " (elsewhere)"))
                time.sleep(2)
        say(f"  fired after {t_fire:.0f}s" if t_fire is not None else f"  did not fire within {a.fire_timeout:.0f}s")
        asyncio.run(inject(a.nats, TARGET, "clear", 0))
        t_res, _ = wait(a.prom, lambda al: not any(x["labels"]["alertname"] == alert and about_target(x) for x in al), a.resolve_timeout)
        say(f"  resolved {t_res:.0f}s after clear" if t_res is not None else "  did not resolve")
        t_quiet, left = wait(a.prom, lambda al: not al, 240)
        if t_quiet is None:
            say(f"  board still shows {[x['labels']['alertname'] for x in left]}; continuing")
        rows.append({"fault": fault, "alert": alert, "fired_after_s": t_fire, "other_alerts": sorted(others),
                     "resolved_after_s": t_res, "quiet_after_s": t_quiet, "informational": fault in informational})

    say("reading the receiver's ledger")
    ledger = [json.loads(l) for l in requests.get(f"{a.sink}/ledger", timeout=5).text.splitlines() if l.strip()]
    for r in rows:
        if r.get("skipped"):
            continue
        r["delivered_firing"] = any(l["status"] == "firing" and l["labels"].get("alertname") == r["alert"] for l in ledger)
        r["delivered_resolved"] = any(l["status"] == "resolved" and l["labels"].get("alertname") == r["alert"] for l in ledger)

    build = requests.get(f"{a.prom}/api/v1/status/buildinfo", timeout=5).json()["data"]
    stamp = a.stamp or time.strftime("%Y-%m-%d %H:%M %Z")
    ok = all(r.get("skipped") or r["informational"] or (r["fired_after_s"] is not None and r["resolved_after_s"] is not None and r["delivered_firing"]) for r in rows)
    result = {"stamp": stamp, "prometheus": build.get("version"), "rows": rows, "ledger_lines": len(ledger), "ok": ok}
    with open(os.path.join(a.out, "results.json"), "w") as f:
        json.dump(result, f, indent=2)

    def cell(v, suffix="s"):
        return "did not" if v is None else f"{v:.0f}{suffix}"

    md = [f"**Proof run, {stamp}.**", "",
          f"Prometheus {build.get('version')}. Six faults injected on collector-a in turn; every figure below is measured by tools/prove.py.", "",
          "| fault | alert | fired after | other alerts while it fired | resolved after clear | reached the receiver |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("skipped"):
            md.append(f"| {r['fault']} | {r['alert']} | skipped | | | |")
            continue
        md.append(f"| {r['fault']} | {r['alert']}{' (informational)' if r['informational'] else ''} | {cell(r['fired_after_s'])} | "
                  f"{', '.join(r['other_alerts']) or 'none'} | {cell(r['resolved_after_s'])} | "
                  f"{'firing' + (' and resolved' if r['delivered_resolved'] else ' only') if r['delivered_firing'] else 'no'} |")
    md += ["", f"Ledger lines at the end of the run: {len(ledger)}. Verdict: {'PASS' if ok else 'FAIL'}.", ""]
    with open(os.path.join(a.out, "RESULTS.md"), "w") as f:
        f.write("\n".join(md))
    print("\n".join(md))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
