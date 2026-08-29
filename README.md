# quiet-machine

The machine that stops reporting looks like a quiet machine. This is an
observability kit built around that sentence: every alert in it fires on the
absence of progress, not on the presence of an error, because none of the five
production incidents behind it produced one. Telemetry travels as
OpenTelemetry over NATS JetStream into an OpenTelemetry Collector, Prometheus
evaluates alert rules that live in git and carry unit tests, Alertmanager
delivers to a receiver that writes a ledger, and Grafana shows a front page
ordered the way the runbooks are: pressure first, identity second, progress
third, the alert board last. A fault injector makes each alert fire on
purpose, and `tools/prove.py` measures that it did.

Built in August 2026 as the follow-up to a Site Reliability Engineer
application, on the incidents described in the note that went with it.

## What is in it

| piece | where | what it does |
|---|---|---|
| collectors | `services/probe.py` | two stand-ins for a machine at a customer site: they poll three sensor legs, write frames into hour files, pass requests through an admission gate, read the host's pressure stall figures, and report every five seconds. Each carries six switchable faults. |
| bus | NATS JetStream, stream `QM_TELEMETRY` | telemetry is published as OTLP/JSON on `qm.telemetry.<service>`; the stream keeps an hour, so a bridge restart replays instead of losing. Faults are injected on `qm.control.<service>`. |
| bridge | `services/bridge.py` | pulls from the stream, verifies that the `service.name` inside each message matches the subject it arrived on, drops and counts the ones that lie, forwards the rest to the collector's OTLP receiver. Reports its own forward age and the stream backlog. |
| collector | `collector/otelcol.yaml` | OpenTelemetry Collector, OTLP in, Prometheus exposition out, resource attributes as labels. |
| rules | `prometheus/rules/quiet-machine.yml` | three recording rules and eight alerts, each naming its incident and its runbook. |
| rule tests | `prometheus/tests/quiet-machine.test.yml` | promtool unit tests: every alert silent on a healthy board, firing on its incident's series shape. |
| delivery | `alertmanager/`, `services/sink.py` | one route to a webhook receiver that appends every notification to a ledger file. |
| dashboard | `grafana/build_dashboard.py` | generates the provisioned front page. |
| runbooks | `runbooks/` | one per alert: what fired, what it usually is, first three steps, how to know it is fixed, how to make it fire on purpose. |
| proof | `tools/fault.py`, `tools/prove.py`, `proof/RESULTS.md` | inject, watch, clear, read the ledger; the table below is its output. |

## The alerts

| alert | fires on | incident it came from | runbook |
|---|---|---|---|
| QuietMachine | a collector's last report older than 60 s | the shape all five share | `runbooks/quiet-machine.md` |
| CollectorMissing | an expected collector has no series at all | a fleet that does not know its own membership | `runbooks/collector-missing.md` |
| SilentWriter | files keep appearing, frames stop | twenty hours of empty hour files that passed every presence check | `runbooks/silent-writer.md` |
| PressureStall | host CPU pressure (some, avg10) above 20 percent | a host diagnosed as a network fault that was CPU starvation | `runbooks/pressure-stall.md` |
| IdentityMismatch | telemetry claims a name that is not the subject's | a port collision that reported itself healthy for 71 restarts | `runbooks/identity-mismatch.md` |
| HungPoller | one leg stale while the process keeps reporting | a fetch that never returned on a busy process | `runbooks/hung-poller.md` |
| SilentRefusals | every request refused, none admitted, for a minute | 48,752 refusals from a process that was online | `runbooks/silent-refusals.md` |
| BusSilent | the bridge forwarded nothing for 60 s | so one page names the bus instead of one page per collector | `runbooks/bus-silent.md` |

Timings are demo timings: 5 second scrape and evaluation, one minute windows,
20 to 30 second holds, so a proof run takes minutes. In production the
windows widen with the scrape interval; the shapes do not change.

## Run it

With Docker:

    docker compose up -d --build
    open http://localhost:3000            # Grafana, anonymous viewer
    python tools/fault.py silent-writer   # needs: pip install nats-py
    python tools/fault.py clear

Without Docker, on bare binaries (this is how the proof below was run):

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    ./run-local.sh fetch                  # nats-server, otelcol-contrib, prometheus, alertmanager, grafana into .bin/
    ./run-local.sh up
    .venv/bin/python tools/prove.py       # about 25 minutes
    ./run-local.sh down

Tests that need no running stack:

    .bin/promtool check rules prometheus/rules/quiet-machine.yml
    .bin/promtool test rules prometheus/tests/quiet-machine.test.yml
    .venv/bin/python -m pytest -q tests

`tests/test_runbooks.py` fails the build if an alert has no runbook, a
runbook has no alert, or an alert is neither fault-proven nor unit-tested.

## Proof

<!-- proof-table -->

## The rules this kit is built on

1. **Progress, not presence.** A file that exists is not a file that grew. A
   process that is up is not a process that worked. Every check asserts a
   counter that must advance.
2. **Identity, not liveness.** A 200 on a port says something answered, not
   what. Every service publishes its own name and pid on `/status`; the
   bridge refuses telemetry whose claimed name does not match its subject.
3. **Pressure before the network.** `/proc/pressure` sits at the top of the
   front page. A host that vanishes from the LAN is usually starved.
4. **The ledger, not the status page.** Counters that reset on restart are
   not evidence. The proof reads the receiver's ledger, not Prometheus's
   alert list.
5. **Every alert has a fault that fires it and a test that pins it.** An
   alert that has never fired is a hope. `tests/test_runbooks.py` refuses an
   alert without both.
6. **An alert nobody reads is a log line.** Everything routes to a receiver
   that writes it down.

## Limits, stated

- The collectors are stand-ins written for this kit. The faults are real
  mechanisms (a frozen counter, a hung leg, a flipped mode, a wrong name, a
  CPU burn, silence), not simulated metric values, but the sensors are not.
- PressureStall depends on the host it runs on. On a shared host every
  collector reports the same pressure, which is correct; on a host with
  spare cores the burn may not reach 20 percent. The proof reports it as
  informational for that reason.
- QuietMachine resolves on its own once the silent series expires from the
  collector (5 minutes) and CollectorMissing takes over; the handover is
  deliberate and documented in both runbooks. CollectorMissing does not
  cover the bridge.
- Alertmanager has one route and one receiver. Silences, inhibition and
  on-call routing are not shown.
- No authentication on NATS, Prometheus or the collector. This is a kit,
  not a deployment.
- The compose file and the bare-binary runner share every config file, so
  they cannot drift; the compose path is exercised by CI, the bare-binary
  path by the proof run recorded above.
- Terraform is not part of this kit.
