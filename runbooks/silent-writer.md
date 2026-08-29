# SilentWriter (incident 1)

**Fires when** a collector keeps creating files but has written no data
frames for a minute. Presence is green; progress is zero.

**Usually is** a reconnect storm: the writer keeps opening hour files that
contain only reconnect markers. Every file-exists check passes. The original
incident ran twenty hours this way and raised forty-two escalating alerts into
a log nobody was reading.

**First three steps**

1. `curl http://<collector>:9101/status`: `files` climbing while `frames` is
   frozen confirms the shape.
2. Look at the newest file's size and content, not its existence. A few
   hundred bytes of markers is this incident.
3. Restart the collector's upstream connection, then watch `frames`, not the
   file listing.

**Fixed when** `rate(qm_frames_written_total[1m])` is back above zero for two
minutes.

**Prove it** `python tools/fault.py silent-writer --service collector-a`.
Files keep appearing every five seconds; frames stop; the alert fires in
about 100 seconds (a one-minute window plus 30 seconds hold).

**The rule this left behind** a health check asserts a counter that must
advance, never a file that must exist.
