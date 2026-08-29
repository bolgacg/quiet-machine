"""Generates grafana/dashboards/quiet-machine.json. The front page is ordered
the way the runbooks are: pressure first, identity second, progress third,
and the alert board last. Run: python grafana/build_dashboard.py"""
import json
import os

DS = {"type": "prometheus", "uid": "prometheus"}
panels = []
_id = [0]


def panel(kind, title, targets, x, y, w, h, **opts):
    _id[0] += 1
    p = {"id": _id[0], "type": kind, "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"datasource": DS, "expr": e, "legendFormat": lf, "refId": chr(65 + i), **extra}
                     for i, (e, lf, extra) in enumerate(targets)]}
    p.update(opts)
    panels.append(p)


def fc(unit=None, thresholds=None, overrides=None, extra=None):
    d = {"color": {"mode": "palette-classic"}, "custom": {"lineWidth": 2, "fillOpacity": 8, "showPoints": "never"}}
    if unit:
        d["unit"] = unit
    if thresholds:
        d["thresholds"] = {"mode": "absolute", "steps": [{"color": "green", "value": None}] + [{"color": c, "value": v} for v, c in thresholds]}
        d["custom"]["thresholdsStyle"] = {"mode": "line"}
    if extra:
        d.update(extra)
    return {"defaults": d, "overrides": overrides or []}


def row(title, y):
    _id[0] += 1
    panels.append({"id": _id[0], "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})


row("Pressure first. A host that vanishes from the network is usually starved, not disconnected.", 0)
panel("timeseries", "CPU pressure, some avg10 (percent); the alert line is 20",
      [('qm_pressure_some_avg10{resource="cpu"}', "{{service_name}}", {})], 0, 1, 12, 8,
      fieldConfig=fc("percent", [(20, "red")]))
panel("timeseries", "Memory and IO pressure, some avg10 (percent)",
      [('qm_pressure_some_avg10{resource=~"memory|io"}', "{{service_name}} {{resource}}", {})], 12, 1, 12, 8,
      fieldConfig=fc("percent"))

row("Identity, not liveness. A 200 on a port says something answered, not what.", 9)
panel("table", "Who is reporting, and who they say they are",
      [('qm_identity_info', "", {"instant": True, "format": "table"})], 0, 10, 14, 7,
      transformations=[{"id": "labelsToFields", "options": {}},
                       {"id": "organize", "options": {"excludeByName": {"Time": True, "Value": True, "__name__": True, "job": True, "instance": True, "qm_mode": True, "pid": True, "otel_scope_name": True, "otel_scope_version": True, "otel_scope_schema_url": True},
                                                      "renameByName": {"service_name": "service", "service_instance_id": "host:pid"},
                                                      "indexByName": {"service_name": 0, "service_instance_id": 1, "pid": 2, "port": 3, "mode": 4, "fault": 5}}}])
panel("stat", "Dropped for a false name, last 5 minutes",
      [('round(sum(increase(qm_bridge_identity_mismatch_total[5m])) or vector(0))', "last 5m", {})], 14, 10, 5, 7,
      fieldConfig=fc(thresholds=[(1, "red")]), options={"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"]}})
panel("stat", "Stream backlog behind the bridge",
      [('qm_bridge_stream_pending', "pending", {})], 19, 10, 5, 7,
      fieldConfig=fc(thresholds=[(100, "orange"), (1000, "red")]), options={"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"]}})

row("Progress, not presence. A file that exists is not a file that grew; a process that is up is not a process that worked.", 17)
panel("timeseries", "Frames written per second (progress) against files created per minute (presence)",
      [('rate(qm_frames_written_total[1m])', "{{service_name}} frames/s", {}),
       ('increase(qm_files_written_total[1m])', "{{service_name}} files/min", {})], 0, 18, 12, 8, fieldConfig=fc())
panel("timeseries", "Seconds since each leg last succeeded; the alert line is 30",
      [('qm:leg_age_seconds', "{{service_name}} {{leg}}", {})], 12, 18, 12, 8,
      fieldConfig=fc("s", [(30, "red")]))
panel("timeseries", "Admissions per second by outcome; refused with nothing admitted is incident 5",
      [('sum by (service_name, outcome) (rate(qm_admissions_total[1m]))', "{{service_name}} {{outcome}}", {})], 0, 26, 12, 8,
      fieldConfig=fc(overrides=[{"matcher": {"id": "byRegexp", "options": ".*refused"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}]))
panel("timeseries", "Seconds since each collector last reported; the alert line is 60",
      [('qm:heartbeat_age_seconds', "{{service_name}}", {})], 12, 26, 12, 8,
      fieldConfig=fc("s", [(60, "red")]))

row("The board. Every alert here fires on absence, and every one has a runbook and a fault that proves it.", 34)
panel("state-timeline", "Firing alerts (ALERTS series from Prometheus)",
      [('ALERTS{alertstate="firing"}', "{{alertname}} {{service_name}}{{subject_service}}{{leg}}", {})], 0, 35, 24, 9,
      fieldConfig=fc(extra={"color": {"mode": "fixed", "fixedColor": "red"}}), options={"showValue": "never", "mergeValues": True, "rowHeight": 0.8})

dash = {"uid": "quiet-machine", "title": "Quiet machine: front page", "tags": ["quiet-machine"], "timezone": "browser",
        "schemaVersion": 39, "version": 1, "refresh": "10s", "time": {"from": "now-30m", "to": "now"},
        "editable": False, "panels": panels, "templating": {"list": []}, "annotations": {"list": []}}
out = os.path.join(os.path.dirname(__file__), "dashboards", "quiet-machine.json")
with open(out, "w") as f:
    json.dump(dash, f, indent=1)
print(f"wrote {out}: {len([p for p in panels if p['type'] != 'row'])} panels")
