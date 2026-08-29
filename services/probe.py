"""A collector stand-in: the machine at a customer site that gathers sensor
frames and reports over the bus. It carries the failure modes from the
incident note as switchable faults, so every alert in this kit can be made to
fire on purpose, and made to stop.

Faults (qm.control.<service>, JSON {"fault": name, "seconds": n}):
  silent-writer  files keep appearing, frames stop (incident 1)
  pressure       burn every core so /proc/pressure/cpu climbs (incident 2)
  identity       report under another service's name (incident 3)
  hung-poller    one leg stops succeeding while the process stays busy (incident 4)
  refusals       the global mode flips and every request is refused, quietly (incident 5)
  mute           stop reporting altogether, without dying (the quiet machine)
  clear          back to normal
"""
import asyncio
import json
import multiprocessing
import os
import random
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nats
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (MetricExporter, MetricExportResult,
                                              PeriodicExportingMetricReader)
from opentelemetry.sdk.resources import Resource

sys.path.insert(0, os.path.dirname(__file__))
from otlp_json import encode  # noqa: E402

SERVICE = os.environ.get("QM_SERVICE", "collector-a")
NATS_URL = os.environ.get("QM_NATS_URL", "nats://localhost:4222")
STATUS_PORT = int(os.environ.get("QM_STATUS_PORT", "9101"))
MODE = os.environ.get("QM_MODE", "live")
EXPORT_MS = int(os.environ.get("QM_EXPORT_MS", "5000"))
STREAM = "QM_TELEMETRY"
SUBJECT = f"qm.telemetry.{SERVICE}"
CONTROL = f"qm.control.{SERVICE}"
IDENTITY_CLAIM = os.environ.get("QM_IDENTITY_CLAIM", "collector-b" if SERVICE != "collector-b" else "collector-a")
LEGS = ["sensor-a", "sensor-b", "sensor-c"]
FAULTS = {"silent-writer", "pressure", "identity", "hung-poller", "refusals", "mute"}


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {SERVICE} {msg}", flush=True)


def _burn(until):
    x = 1.0
    while time.time() < until:
        x = (x * 1.000001) % 7.0


class State:
    def __init__(self):
        self.fault = None
        self.fault_until = 0.0
        self.global_mode = MODE
        self.leg_last_ok = {leg: time.time() for leg in LEGS}
        self.files = 0
        self.frames = 0
        self.admitted = 0
        self.refused = 0
        self.burners = []

    def active(self, name):
        if self.fault == name and time.time() < self.fault_until:
            return True
        if self.fault == name:
            self.clear("expired")
        return False

    def set(self, name, seconds):
        self.clear("replaced")
        self.fault, self.fault_until = name, time.time() + seconds
        if name == "refusals":
            self.global_mode = "paper"  # the mode flipped globally; this process did not
        if name == "pressure":
            n = (os.cpu_count() or 2) * 2
            self.burners = [multiprocessing.Process(target=_burn, args=(self.fault_until,), daemon=True) for _ in range(n)]
            for p in self.burners:
                p.start()
        log(f"fault {name} for {seconds}s")

    def clear(self, why="cleared"):
        if self.fault is None:
            return
        log(f"fault {self.fault} {why}")
        self.fault, self.fault_until = None, 0.0
        self.global_mode = MODE
        for p in self.burners:
            if p.is_alive():
                p.terminate()
        self.burners = []


state = State()


def pressure():
    out = {}
    for res in ("cpu", "memory", "io"):
        try:
            with open(f"/proc/pressure/{res}") as f:
                first = f.readline().split()
                out[res] = float(dict(kv.split("=") for kv in first[1:])["avg10"])
        except (OSError, KeyError, ValueError):
            pass
    return out


class NatsExporter(MetricExporter):
    """Publishes each export as one OTLP/JSON message on the telemetry stream."""

    def __init__(self):
        super().__init__()
        self.loop = None
        self.js = None
        self.published = 0
        self.failed = 0

    def export(self, metrics_data, timeout_millis=10_000, **kwargs):
        if state.active("mute"):
            return MetricExportResult.SUCCESS  # the machine goes quiet without an error
        if self.loop is None or self.js is None:
            return MetricExportResult.FAILURE
        payload = encode(metrics_data)
        if state.active("identity"):
            for rm in payload["resourceMetrics"]:
                for a in rm["resource"]["attributes"]:
                    if a["key"] == "service.name":
                        a["value"] = {"stringValue": IDENTITY_CLAIM}
        fut = asyncio.run_coroutine_threadsafe(self.js.publish(SUBJECT, json.dumps(payload).encode()), self.loop)
        try:
            fut.result(timeout=timeout_millis / 1000)
            self.published += 1
            return MetricExportResult.SUCCESS
        except Exception as e:  # noqa: BLE001
            self.failed += 1
            log(f"publish failed: {e!r}")
            return MetricExportResult.FAILURE

    def force_flush(self, timeout_millis=10_000):
        return True

    def shutdown(self, timeout_millis=30_000, **kwargs):
        return None


exporter = NatsExporter()


def build_meter():
    resource = Resource.create({
        "service.name": SERVICE,
        # the instance is the machine, not the process: a restart must continue the
        # same series, or the stale twin of the old process pages for five minutes
        "service.instance.id": os.environ.get("QM_INSTANCE", socket.gethostname()),
        "qm.mode": MODE,
    })
    provider = MeterProvider(resource=resource,
                             metric_readers=[PeriodicExportingMetricReader(exporter, export_interval_millis=EXPORT_MS)])
    meter = provider.get_meter("quiet-machine.probe")
    files = meter.create_counter("qm_files_written", description="hour files created (presence)")
    frames = meter.create_counter("qm_frames_written", description="data frames written (progress)")
    admissions = meter.create_counter("qm_admissions", description="requests through the admission gate, by outcome")
    files.add(0)
    frames.add(0)
    admissions.add(0, {"outcome": "admitted"})
    admissions.add(0, {"outcome": "refused"})

    def heartbeat(_):
        yield Observation(time.time())

    def legs(_):
        for leg, ts in state.leg_last_ok.items():
            yield Observation(ts, {"leg": leg})

    def psi(_):
        for res, v in pressure().items():
            yield Observation(v, {"resource": res})

    def identity(_):
        # the active fault is on /status, not here: a label that changes would churn the series
        yield Observation(1, {"pid": str(os.getpid()), "port": str(STATUS_PORT), "mode": MODE})

    meter.create_observable_gauge("qm_heartbeat_timestamp_seconds", callbacks=[heartbeat],
                                  description="wall clock at the moment of reporting")
    meter.create_observable_gauge("qm_leg_last_ok_timestamp_seconds", callbacks=[legs],
                                  description="last successful poll per leg")
    meter.create_observable_gauge("qm_pressure_some_avg10", callbacks=[psi],
                                  description="/proc/pressure some avg10 on the host, percent")
    meter.create_observable_gauge("qm_identity_info", callbacks=[identity],
                                  description="who this process says it is")
    return files, frames, admissions


def tick(files, frames, admissions, n):
    now = time.time()
    for leg in LEGS:
        if state.active("hung-poller") and leg == "sensor-c":
            continue  # the fetch never returns; the other legs keep flowing
        state.leg_last_ok[leg] = now
    if n % 5 == 0:
        files.add(1)  # a new hour file, in every mode; under silent-writer it holds only markers
        state.files += 1
    if not state.active("silent-writer"):
        k = random.randint(40, 60)
        frames.add(k)
        state.frames += k
    for _ in range(10):
        if state.global_mode == MODE:
            admissions.add(1, {"outcome": "admitted"})
            state.admitted += 1
        else:
            admissions.add(1, {"outcome": "refused"})  # refused, and not logged at error level
            state.refused += 1


class Status(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"service": SERVICE, "pid": os.getpid(), "port": STATUS_PORT, "mode": MODE,
                           "global_mode": state.global_mode, "fault": state.fault,
                           "files": state.files, "frames": state.frames,
                           "admitted": state.admitted, "refused": state.refused,
                           "published": exporter.published, "publish_failed": exporter.failed}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


async def bus():
    nc = await nats.connect(NATS_URL, reconnect_time_wait=1, max_reconnect_attempts=-1)
    js = nc.jetstream()
    try:
        await js.stream_info(STREAM)
    except Exception:  # noqa: BLE001
        await js.add_stream(name=STREAM, subjects=["qm.telemetry.>"], max_age=3600)
    exporter.loop, exporter.js = asyncio.get_running_loop(), js

    async def control(msg):
        try:
            cmd = json.loads(msg.data)
        except ValueError:
            return
        fault = cmd.get("fault")
        if fault == "clear":
            state.clear()
        elif fault in FAULTS:
            state.set(fault, float(cmd.get("seconds", 300)))
        else:
            log(f"unknown fault {fault!r}")

    await nc.subscribe(CONTROL, cb=control)
    log(f"on the bus at {NATS_URL}, publishing {SUBJECT}, listening {CONTROL}")
    while True:
        await asyncio.sleep(3600)


def main():
    threading.Thread(target=lambda: asyncio.run(bus()), daemon=True).start()
    threading.Thread(target=lambda: ThreadingHTTPServer(("0.0.0.0", STATUS_PORT), Status).serve_forever(), daemon=True).start()
    files, frames, admissions = build_meter()
    log(f"status on :{STATUS_PORT}, mode {MODE}")
    n = 0
    while True:
        tick(files, frames, admissions, n)
        n += 1
        time.sleep(1)


if __name__ == "__main__":
    main()
