"""Copies proof/RESULTS.md into the README between the proof markers, so the
table in the README is always the measured one. Run after tools/prove.py."""
import os
import re

root = os.path.join(os.path.dirname(__file__), "..")
with open(os.path.join(root, "proof", "RESULTS.md")) as f:
    table = f.read().strip()
with open(os.path.join(root, "README.md")) as f:
    readme = f.read()
block = "<!-- proof-table -->\n" + table + "\n<!-- /proof-table -->"
new, n = re.subn(r"<!-- proof-table -->.*?(<!-- /proof-table -->|$)", lambda m: block, readme, count=1, flags=re.S)
if n == 0:
    raise SystemExit("no proof-table marker in README")
with open(os.path.join(root, "README.md"), "w") as f:
    f.write(new if new.endswith("\n") else new + "\n")
print("README proof table updated")
