# SilentRefusals (incident 5)

**Fires when** a collector refused every request for a minute and admitted
none. The process is up, its restart counter is quiet, nothing is red.

**Usually is** an admission gate comparing the caller's mode with a global
mode, after the global mode changed and the process did not. In the original
incident three services were silently refused everything, one of them 48,752
times, and the status field that should have shown it reset on every restart.

**First three steps**

1. `curl http://<collector>:9101/status`: compare `mode` with `global_mode`.
   A mismatch is this incident.
2. Do not trust the status counters alone; read the admissions ledger (here,
   `qm_admissions_total` by outcome, which never resets while the process
   lives).
3. Fix the mode on the side that is wrong, then confirm `admitted` climbs.

**Fixed when** `rate(qm_admissions_total{outcome="admitted"}[1m])` is above
zero and the refused rate is back to its baseline.

**Prove it** `python tools/fault.py refusals --service collector-a` flips the
global mode to paper while the collector stays live; every request is refused
without an error line; the alert fires in about 100 seconds.

**The rule this left behind** the gate is tested in both directions, a
"guard that did not run" check asks for positive evidence that each admission
path executed, and the weekly review reads the ledger, not the status page.
