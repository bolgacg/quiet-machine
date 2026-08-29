"""Every alert has a runbook and every runbook belongs to an alert. A rule
without a runbook is a page with no first step; a runbook without a rule is
a document nobody will be sent to."""
import os
import re

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


def alerts():
    with open(os.path.join(ROOT, "prometheus", "rules", "quiet-machine.yml")) as f:
        doc = yaml.safe_load(f)
    return [r for g in doc["groups"] for r in g["rules"] if "alert" in r]


def test_every_alert_names_an_existing_runbook():
    for r in alerts():
        rb = r["annotations"].get("runbook")
        assert rb, f"{r['alert']} has no runbook annotation"
        assert os.path.exists(os.path.join(ROOT, rb)), f"{r['alert']} points at a missing runbook {rb}"


def test_every_runbook_belongs_to_an_alert():
    named = {r["annotations"]["runbook"] for r in alerts()}
    for fn in os.listdir(os.path.join(ROOT, "runbooks")):
        if fn.endswith(".md") and fn != "README.md":
            assert f"runbooks/{fn}" in named, f"runbooks/{fn} is not referenced by any alert"


def test_every_alert_is_proven_by_a_fault_or_a_unit_test():
    with open(os.path.join(ROOT, "tools", "prove.py")) as f:
        proven = set(re.findall(r'\("[a-z-]+", "([A-Za-z]+)"\)', f.read()))
    with open(os.path.join(ROOT, "prometheus", "tests", "quiet-machine.test.yml")) as f:
        unit = set(re.findall(r"alertname:\s*([A-Za-z]+)", f.read()))
    for r in alerts():
        assert r["alert"] in proven or r["alert"] in unit, f"{r['alert']} is neither fault-proven nor unit-tested"
