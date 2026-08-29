"""Bus to collector. Telemetry rides the same NATS the platform already runs on,
as OTLP/JSON messages in a JetStream stream, so a bridge restart replays what it
missed instead of losing it. The bridge forwards each message to the
OpenTelemetry Collector's OTLP receiver.

It also checks identity: a message whose service.name does not match the subject
it arrived on is counted and dropped, never forwarded. A process answering under
a name that is not its own is incident 3, and telemetry that trusts the claim
would mislabel another service's metrics.
"""
import asyncio
import json
import os
import socket
import sys
import time

import nats
import requests
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (MetricExporter, MetricExportResult,
                                              PeriodicExportingMetricReader)
from opentelemetry.sdk.resources import Resource

sys.path.insert(0, os.path.dirname(__file__))
from otlp_json import encode, service_name  # noqa: E402

NATS_URL = os.environ.get("QM_NATS_URL", "nats://localhost:4222")
OTLP_URL = os.environ.get("QM_OTLP_URL", "http://localhost:4318")
STREAM = "QM_TELEMETRY"
DURABLE = "bridge"


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} bridge {msg}", flush=True)


class Counters:
    forwarded = 0
    dropped_identity = {}
    failed = 0
    last_forward = 0.0
    pending = 0


def post(payload):
    r = requests.post(f"{OTLP_URL}/v1/metrics", json=payload, timeout=5)
    r.raise_for_status()


class HttpExporter(MetricExporter):
    """The bridge's own metrics go straight to the collector; it must not depend on itself."""

    def export(self, metrics_data, timeout_millis=10_000, **kwargs):
        try:
            post(encode(metrics_data))
            return MetricExportResult.SUCCESS
        except Exception as e:  # noqa: BLE001
            log(f"own export failed: {e!r}")
            return MetricExportResult.FAILURE

    def force_flush(self, timeout_millis=10_000):
        return True

    def shutdown(self, timeout_millis=30_000, **kwargs):
        return None


def build_meter():
    resource = Resource.create({"service.name": "bridge", "service.instance.id": f"{socket.gethostname()}:{os.getpid()}"})
    provider = MeterProvider(resource=resource,
                             metric_readers=[PeriodicExportingMetricReader(HttpExporter(), export_interval_millis=5000)])
    meter = provider.get_meter("quiet-machine.bridge")

    def forwarded(_):
        yield Observation(Counters.forwarded)

    def dropped(_):
        for (subj, claimed), n in Counters.dropped_identity.items():
            yield Observation(n, {"subject_service": subj, "claimed": claimed})

    def failed(_):
        yield Observation(Counters.failed)

    def last_forward(_):
        yield Observation(Counters.last_forward)

    def pending(_):
        yield Observation(Counters.pending)

    meter.create_observable_counter("qm_bridge_forwarded", callbacks=[forwarded], description="messages forwarded to the collector")
    meter.create_observable_counter("qm_bridge_identity_mismatch", callbacks=[dropped],
                                    description="messages dropped because service.name did not match the subject")
    meter.create_observable_counter("qm_bridge_forward_failed", callbacks=[failed], description="collector refused or timed out")
    meter.create_observable_gauge("qm_bridge_last_forward_timestamp_seconds", callbacks=[last_forward],
                                  description="wall clock of the last successful forward")
    meter.create_observable_gauge("qm_bridge_stream_pending", callbacks=[pending],
                                  description="messages waiting in the stream for this bridge")


async def main():
    build_meter()
    nc = await nats.connect(NATS_URL, reconnect_time_wait=1, max_reconnect_attempts=-1)
    js = nc.jetstream()
    try:
        await js.stream_info(STREAM)
    except Exception:  # noqa: BLE001
        await js.add_stream(name=STREAM, subjects=["qm.telemetry.>"], max_age=3600)
    sub = await js.pull_subscribe("qm.telemetry.>", durable=DURABLE, stream=STREAM)
    log(f"consuming {STREAM} as {DURABLE}, forwarding to {OTLP_URL}")
    last_info = 0.0
    while True:
        try:
            msgs = await sub.fetch(50, timeout=2)
        except (asyncio.TimeoutError, nats.errors.TimeoutError):
            msgs = []
        for msg in msgs:
            subject_service = msg.subject.rsplit(".", 1)[-1]
            try:
                payload = json.loads(msg.data)
            except ValueError:
                await msg.ack()
                continue
            claimed = service_name(payload)
            if claimed != subject_service:
                key = (subject_service, claimed or "none")
                Counters.dropped_identity[key] = Counters.dropped_identity.get(key, 0) + 1
                await msg.ack()
                continue
            try:
                post(payload)
                Counters.forwarded += 1
                Counters.last_forward = time.time()
                await msg.ack()
            except Exception as e:  # noqa: BLE001
                Counters.failed += 1
                log(f"forward failed, will retry: {e!r}")
                await msg.nak(delay=5)
        if time.time() - last_info > 5:
            try:
                info = await js.consumer_info(STREAM, DURABLE)
                Counters.pending = int(info.num_pending)
            except Exception:  # noqa: BLE001
                pass
            last_info = time.time()


if __name__ == "__main__":
    asyncio.run(main())
