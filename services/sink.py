"""The alert receiver. Alertmanager posts here and every notification is
appended to a ledger file, one JSON line each. The proof reads this ledger, not
Prometheus's alert page, because an alert that fired and reached nobody is a
log line (incident 1), and a status page is not evidence of delivery
(incident 5).
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("QM_SINK_PORT", "9095"))
LEDGER = os.environ.get("QM_LEDGER", os.path.join(os.path.dirname(__file__), "..", "data", "alerts.ledger.jsonl"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/alerts":
            return self._send(404, b"{}")
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n))
        except ValueError:
            return self._send(400, b"{}")
        os.makedirs(os.path.dirname(os.path.abspath(LEDGER)), exist_ok=True)
        with open(LEDGER, "a") as f:
            for a in payload.get("alerts", []):
                f.write(json.dumps({"received_at": time.time(), "status": a.get("status"),
                                    "labels": a.get("labels", {}), "startsAt": a.get("startsAt"),
                                    "endsAt": a.get("endsAt")}) + "\n")
        self._send(200, b"{}")

    def do_GET(self):
        if self.path == "/ledger":
            try:
                with open(LEDGER, "rb") as f:
                    return self._send(200, f.read(), "application/x-ndjson")
            except OSError:
                return self._send(200, b"")
        self._send(200, json.dumps({"service": "sink", "pid": os.getpid(), "port": PORT, "ledger": LEDGER}).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"sink on :{PORT}, ledger {LEDGER}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
