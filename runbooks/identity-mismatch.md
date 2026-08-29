# IdentityMismatch (incident 3)

**Fires when** the bridge drops a telemetry message because the
`service.name` inside it does not match the subject it arrived on.

**Usually is** two processes on one identity: a crash-looping service whose
port was taken by another service ten seconds earlier, a copied config with
the old name still in it, a deploy that started the wrong binary under the
right subject. In the original incident the wrong process answered with a
200 for seventy-one restarts and the check read another process's JSON as
its own.

**First three steps**

1. The alert's labels say which subject and which claimed name. `curl` the
   `/status` of the service that owns the subject; it reports its own name,
   pid and port.
2. Compare with what is listening on that port (`ss -ltnp`). If a different
   pid owns it, that is the collision.
3. Stop the impostor, restart the owner, confirm `/status` reports the
   expected name before closing.

**Fixed when** `increase(qm_bridge_identity_mismatch_total[5m])` is zero and
the owner's `/status` names itself.

**Prove it** `python tools/fault.py identity --service collector-a` makes
collector-a report under collector-b's name. The bridge drops every message;
nothing is mislabelled downstream; the alert fires within about 20 seconds.

**The rule this left behind** every service publishes its name and pid on
`/status`, and every check verifies identity rather than a status code. Ports
are claimed in a registry before deploy.
