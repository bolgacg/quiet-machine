**Proof run, 2026-08-29 14:12 UTC (GitHub Actions).**

Prometheus 3.14.0. Six faults injected on collector-a in turn; every figure below is measured by tools/prove.py.

| fault | alert | fired after | other alerts while it fired | resolved after clear | reached the receiver |
|---|---|---|---|---|---|
| mute | QuietMachine | 84s | none | 16s | firing and resolved |
| silent-writer | SilentWriter | 94s | none | 14s | firing and resolved |
| hung-poller | HungPoller | 56s | none | 14s | firing and resolved |
| refusals | SilentRefusals | 96s | none | 14s | firing and resolved |
| identity | IdentityMismatch | 30s | none | 66s | firing and resolved |
| pressure | PressureStall (informational) | 40s | none | 30s | firing only |

Ledger lines at the end of the run: 12. Verdict: PASS.
