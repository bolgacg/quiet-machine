# HungPoller (incident 4)

**Fires when** one polling leg has not succeeded for 30 seconds while the
process itself keeps reporting (heartbeat under 30 seconds old).

**Usually is** a fetch that never returns and never rejects: a request
timeout defeated by event loop starvation on an overloaded host, a socket
half-open across a NAT, a lock held by a leg that died. Everything else about
the process looks busy: the log grows, timestamps move, other legs flow.

**First three steps**

1. The alert names the leg. Check whether the host is also under pressure
   (PressureStall); starvation was the cause in the original incident.
2. Read the per-leg ages on the dashboard: one stale leg is a hung fetch, all
   legs stale is QuietMachine's territory.
3. Restart the process. A hung leg does not recover on its own; the guard
   that came out of this incident exits the process when a leg goes stale
   while it is meant to be polling, with the per-leg ages written to the log
   first, so the diagnosis is there before anyone looks.

**Fixed when** every `qm:leg_age_seconds` for the service is under 10.

**Prove it** `python tools/fault.py hung-poller --service collector-a`
freezes leg sensor-c; the other two keep flowing; the alert fires in about
50 seconds.

**The rule this left behind** pauses that are idle by design refresh the
timestamp so the guard does not fire on them, and that exception was verified
in production rather than assumed.
