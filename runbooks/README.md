# Runbooks

One per alert, in the shape a person at 03:00 needs: what fired, what it usually
is, the first three steps, how to know it is fixed, and how to make the alert
fire on purpose so nobody has to trust that it works.

Rules for the set:

1. An alert fires on the absence of progress, not on the presence of an error.
   None of the incidents behind these produced an error.
2. Every check verifies identity, not liveness. A 200 on a port says that
   something answered, not what.
3. Pressure is read before the network is touched.
4. The ledger is the evidence, not the status page. A counter that resets on
   restart is not evidence of anything.
5. Every alert has a fault that proves it (`tools/fault.py`, `tools/prove.py`)
   and a unit test on synthetic series (`prometheus/tests`). An alert that has
   never fired is a hope.
6. An alert nobody reads is a log line. Every alert reaches a receiver that
   writes it down; the proof reads the receiver, not Prometheus.
