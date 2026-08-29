"""OTLP/JSON encoding of the OpenTelemetry SDK's MetricsData.

The collector's OTLP receiver accepts this shape at POST /v1/metrics. Only what
this kit produces is encoded (gauges and sums carrying number points); any other
metric type raises on purpose, so a new instrument cannot be dropped in silence.
"""
from opentelemetry.sdk.metrics.export import Gauge, MetricsData, Sum


def _value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _attrs(d):
    return [{"key": k, "value": _value(v)} for k, v in (d or {}).items()]


def _point(p):
    out = {"attributes": _attrs(p.attributes), "timeUnixNano": str(p.time_unix_nano)}
    if p.start_time_unix_nano:
        out["startTimeUnixNano"] = str(p.start_time_unix_nano)
    if isinstance(p.value, float):
        out["asDouble"] = p.value
    else:
        out["asInt"] = str(p.value)
    return out


def _metric(m):
    out = {"name": m.name, "description": m.description or "", "unit": m.unit or ""}
    if isinstance(m.data, Sum):
        out["sum"] = {
            "dataPoints": [_point(p) for p in m.data.data_points],
            "aggregationTemporality": int(m.data.aggregation_temporality),
            "isMonotonic": bool(m.data.is_monotonic),
        }
    elif isinstance(m.data, Gauge):
        out["gauge"] = {"dataPoints": [_point(p) for p in m.data.data_points]}
    else:
        raise TypeError(f"no OTLP/JSON encoding for {type(m.data).__name__} ({m.name})")
    return out


def encode(md: MetricsData) -> dict:
    return {
        "resourceMetrics": [
            {
                "resource": {"attributes": _attrs(rm.resource.attributes)},
                "scopeMetrics": [
                    {
                        "scope": {"name": sm.scope.name, "version": sm.scope.version or ""},
                        "metrics": [_metric(m) for m in sm.metrics],
                    }
                    for sm in rm.scope_metrics
                ],
            }
            for rm in md.resource_metrics
        ]
    }


def service_name(payload: dict):
    """The service.name a payload claims, or None."""
    for rm in payload.get("resourceMetrics", []):
        for a in rm.get("resource", {}).get("attributes", []):
            if a.get("key") == "service.name":
                return a.get("value", {}).get("stringValue")
    return None
