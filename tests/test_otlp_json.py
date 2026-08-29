import os
import sys

from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))
from otlp_json import encode, service_name  # noqa: E402


def collect():
    reader = InMemoryMetricReader()
    provider = MeterProvider(resource=Resource.create({"service.name": "collector-x", "qm.mode": "live"}),
                             metric_readers=[reader])
    meter = provider.get_meter("test")
    c = meter.create_counter("qm_frames_written")
    c.add(50)
    c.add(25, {"leg": "sensor-a"})
    meter.create_observable_gauge("qm_heartbeat_timestamp_seconds", callbacks=[lambda _: [Observation(1234.5)]])
    return encode(reader.get_metrics_data())


def test_resource_and_service_name():
    payload = collect()
    assert service_name(payload) == "collector-x"
    keys = {a["key"] for a in payload["resourceMetrics"][0]["resource"]["attributes"]}
    assert {"service.name", "qm.mode"} <= keys


def test_sum_is_cumulative_monotonic_with_points():
    payload = collect()
    metrics = {m["name"]: m for m in payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]}
    s = metrics["qm_frames_written"]["sum"]
    assert s["isMonotonic"] is True and s["aggregationTemporality"] == 2
    values = sorted(int(p["asInt"]) for p in s["dataPoints"])
    assert values == [25, 50]
    labelled = [p for p in s["dataPoints"] if p["attributes"]]
    assert labelled[0]["attributes"] == [{"key": "leg", "value": {"stringValue": "sensor-a"}}]


def test_gauge_point_is_double():
    payload = collect()
    metrics = {m["name"]: m for m in payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]}
    g = metrics["qm_heartbeat_timestamp_seconds"]["gauge"]["dataPoints"][0]
    assert g["asDouble"] == 1234.5 and g["timeUnixNano"].isdigit()
