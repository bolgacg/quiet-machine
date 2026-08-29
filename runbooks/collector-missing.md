# CollectorMissing

**Fires when** an expected collector has no heartbeat series at all for 30
seconds. The expected set is written into the rule on purpose: a fleet that
does not know its own membership cannot notice a member gone.

**Usually is** a collector silent long enough that its series expired from
the collector-side exporter (5 minutes), a collector that never registered
after a deploy, or a renamed service that now reports under a different
`service.name` (check IdentityMismatch).

**First three steps**

1. Is the name in the rule still the name the service uses? Renames are the
   most common cause of a "missing" service that is running fine.
2. `docker compose ps` or `data/pids`: is the process there at all?
3. If it is running and reporting, follow QuietMachine; the two alerts share
   a cause more often than not.

**Fixed when** `qm_heartbeat_timestamp_seconds{service_name="<name>"}` exists
again and QuietMachine is not firing for it.

**Prove it** the unit test "a collector with no series at all" in
`prometheus/tests/quiet-machine.test.yml`. On the live stack, stop one
collector for six minutes and watch QuietMachine hand over to this alert.
