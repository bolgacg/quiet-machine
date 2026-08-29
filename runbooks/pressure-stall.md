# PressureStall (incident 2)

**Fires when** the host's CPU pressure (`/proc/pressure/cpu`, some, 10 second
average) is above 20 percent for 20 seconds.

**Usually is** too many processes for the cores. The original incident looked
like a network fault for a week: pings flapping, SSH dropping, zero interface
errors. It was a four-core host running sixty-eight supervised processes; the
kernel could not service the network stack in time. A later trigger was a
recursive filesystem walk driving IO wait to 46 percent.

**First three steps**

1. Read pressure before touching the network: `cat /proc/pressure/cpu
   /proc/pressure/io /proc/pressure/memory` on the host.
2. `top` by CPU, then shed the least important workers first. Do not reboot;
   a reboot hides the cause and comes back.
3. If IO pressure is the high one, find the process walking the disk.

**Fixed when** `qm_pressure_some_avg10{resource="cpu"}` is under 5 for five
minutes with the shed workers still stopped.

**Prove it** `python tools/fault.py pressure --service collector-a --seconds
90` burns every core from inside the collector for 90 seconds. On a shared
host every collector on it will show the same pressure, which is correct: the
pressure is the host's. This is the one alert that depends on the machine it
runs on, so the proof reports it as informational.
