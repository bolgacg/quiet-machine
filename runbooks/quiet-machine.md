# QuietMachine

**Fires when** a collector's last report is more than 60 seconds old for 20
seconds. The series still exists; its value is stale.

**Usually is** the machine at the site lost its connection, the process is
alive but its exporter thread is wedged, or the bus is up and the bridge is
not (check BusSilent; if it is firing too, this is not the collector's fault).

**First three steps**

1. `curl http://<collector>:9101/status`. If it answers, read `published` and
   `publish_failed`: a climbing `publish_failed` is a bus problem, a frozen
   `published` with the process alive is a wedged exporter.
2. Check the bridge's `qm_bridge_stream_pending`. If messages are piling up
   in the stream, the collector is fine and the bridge is the patient.
3. Only then look at the site's network.

**Fixed when** `qm:heartbeat_age_seconds` for the service drops under 10 and
stays there for two scrapes.

**Prove it** `python tools/fault.py mute --service collector-a`; the alert
fires within about 90 seconds and resolves within 30 of `clear`. If the
silence lasts past the collector's metric expiration (5 minutes), this alert
resolves on its own because the series is gone; CollectorMissing takes over.
That handover is the reason both alerts exist.
