# BusSilent

**Fires when** the bridge has forwarded nothing to the collector for 60
seconds. Every collector will look quiet at once; this alert exists so that
one page names the real patient instead of one page per collector.

**Usually is** the bridge lost the stream (consumer deleted, NATS restarted
without JetStream storage), the collector's OTLP receiver is refusing, or the
bridge itself is down (in which case its own metrics stop too and this alert
resolves when they expire; CollectorMissing does not cover the bridge, and
that is a known limit).

**First three steps**

1. `qm_bridge_forward_failed_total` climbing means the collector refused;
   check the collector's log. `qm_bridge_stream_pending` climbing means the
   bridge is alive and stuck; a flat zero with silence means the stream is
   empty or the consumer is gone.
2. `nats stream info QM_TELEMETRY` and `nats consumer info QM_TELEMETRY
   bridge` on the bus.
3. Restart the bridge. The stream replays whatever it missed; nothing is
   lost while the stream's retention window holds.

**Fixed when** `qm:bridge_forward_age_seconds` is under 10 and QuietMachine
is not firing for any collector.

**Prove it** the unit test "the bridge stops forwarding" in
`prometheus/tests/quiet-machine.test.yml`; on the live stack, stop the bridge
process for two minutes and watch the pending count climb, then restart it
and watch the count drain.
