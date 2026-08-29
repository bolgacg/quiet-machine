**Proof run, 2026-08-29 16:10 CEST (bare binaries on a 4-core WSL2 host).**

Prometheus 3.14.0. Six faults injected on collector-a in turn; every figure below is measured by tools/prove.py.

| fault | alert | fired after | other alerts while it fired | resolved after clear | reached the receiver |
|---|---|---|---|---|---|
| mute | QuietMachine | 87s | none | 11s | firing and resolved |
| silent-writer | SilentWriter | 99s | none | 10s | firing and resolved |
| hung-poller | HungPoller | 60s | none | 17s | firing and resolved |
| refusals | SilentRefusals | 91s | none | 6s | firing and resolved |
| identity | IdentityMismatch | 31s | none | 56s | firing and resolved |
| pressure | PressureStall (informational) | 35s | none | 31s | firing and resolved |

Ledger lines at the end of the run: 13. Verdict: PASS.
