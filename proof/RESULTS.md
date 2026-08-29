**Proof run, 2026-08-29 16:37 CEST (bare binaries on a 4-core WSL2 host).**

Prometheus 3.14.0. Six faults injected on collector-a in turn; every figure below is measured by tools/prove.py.

| fault | alert | fired after | other alerts while it fired | resolved after clear | reached the receiver |
|---|---|---|---|---|---|
| mute | QuietMachine | 93s | none | 19s | firing and resolved |
| silent-writer | SilentWriter | 97s | none | 16s | firing and resolved |
| hung-poller | HungPoller | 62s | none | 21s | firing and resolved |
| refusals | SilentRefusals | 97s | none | 14s | firing and resolved |
| identity | IdentityMismatch | 38s | none | 66s | firing and resolved |
| pressure | PressureStall (informational) | 32s | none | 29s | firing only |

Ledger lines at the end of the run: 12. Verdict: PASS.
