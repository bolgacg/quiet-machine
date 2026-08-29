"""Inject a fault into a collector, or clear it.

  python tools/fault.py silent-writer --service collector-a --seconds 300
  python tools/fault.py clear --service collector-a
"""
import argparse
import asyncio
import json
import os

import nats

FAULTS = ["silent-writer", "pressure", "identity", "hung-poller", "refusals", "mute", "clear"]


async def inject(url, service, fault, seconds):
    nc = await nats.connect(url)
    await nc.publish(f"qm.control.{service}", json.dumps({"fault": fault, "seconds": seconds}).encode())
    await nc.flush()
    await nc.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fault", choices=FAULTS)
    ap.add_argument("--service", default="collector-a")
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--nats", default=os.environ.get("QM_NATS_URL", "nats://localhost:4222"))
    a = ap.parse_args()
    asyncio.run(inject(a.nats, a.service, a.fault, a.seconds))
    print(f"{a.fault} on {a.service}" + ("" if a.fault == "clear" else f" for {a.seconds:.0f}s"))


if __name__ == "__main__":
    main()
