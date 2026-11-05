#!/usr/bin/env python3
"""Harbor Ridge reference demo. Stdlib only; n8n remains the workflow owner."""
import csv
import http.client
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SOURCE = Path("/workspace/capstones/scenario1_solution/files")
AUDIT_LOG = SOURCE / "logs/triage_log.jsonl"
SAMPLES = SOURCE / "testset/test_emails.csv"
PREFIXES = ("/form", "/webhook", "/webhook-waiting", "/form-waiting")
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}

def live_scoreboard(audit_log=None):
    """Recompute from every complete audit record, including unlabelled form demos.

    A malformed/in-flight JSONL line is skipped and reported, never replaced by
    stale reference results. Repeated batch runs count as separate activity.
    """
    path = audit_log if audit_log is not None else AUDIT_LOG
    rows, skipped = [], 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("Not an audit object")
                rows.append(row)
            except ValueError:
                skipped += 1
    labelled = [r for r in rows if str(r.get("expected_team") or "").strip()]
    correct = sum(r.get("proposed_team") == r["expected_team"] for r in labelled)
    statuses = {"AUTO_ROUTED": 0, "COMPLAINT": 0, "NEEDS_REVIEW": 0}
    for row in rows:
        status = row.get("status") or "UNKNOWN"
        statuses[status] = statuses.get(status, 0) + 1
    def yes(value):
        return value is True or str(value).strip().lower() in ("yes", "true", "1")
    complaints = [r for r in labelled if yes(r.get("expected_complaint"))]
    missed = [r.get("item_id") for r in complaints if not yes(r.get("complaint_flag"))]
    timestamps = []
    for row in rows:
        stamp = row.get("processed_at")
        try:
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                timestamps.append((dt, stamp))
        except (AttributeError, TypeError, ValueError):
            pass
    accuracy = correct / len(labelled) if labelled else None
    misroute = 1 - accuracy if accuracy is not None else None
    return {
        "items": len(rows), "labelled": len(labelled),
        "routing_accuracy": accuracy, "misroute_rate": misroute,
        "baseline_misroute_rate": 0.30,
        "auto_routed_share": statuses["AUTO_ROUTED"] / len(rows) if rows else None,
        "by_status": statuses,
        "complaint_recall": (len(complaints) - len(missed)) / len(complaints) if complaints else None,
        "complaints_missed": missed,
        "run_at": max(timestamps, key=lambda t: t[0])[1] if timestamps else None,
        "errors": [{"item_id": r.get("item_id"), "expected": r["expected_team"],
                    "got": r.get("proposed_team"), "status": r.get("status")}
                   for r in labelled if r.get("proposed_team") != r["expected_team"]],
        "skipped_audit_lines": skipped,
        "summary": {
            "title": f"Live triage activity · {len(rows)} processed emails",
            "description": f"{correct} of {len(labelled)} labelled emails routed correctly; accuracy excludes unlabelled demos.",
            "source": path.name,
            "scope": "Live audit-log totals: live triage demos and manual Load labelled test set both update these numbers. Accuracy and complaint recall use labelled rows only; repeated runs count as new activity.",
            "correctly_routed": correct,
            "baseline_improvement_percentage_points": round((0.30 - misroute) * 100, 1) if misroute is not None else None,
        },
    }

class Handler(BaseHTTPRequestHandler):
    server_version = "HarborRidgeDemo/1.0"

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, status=200):
        self.reply(status, json.dumps(obj, ensure_ascii=False))

    def request_body(self):
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            parts = []
            while True:
                size = int(self.rfile.readline().split(b";", 1)[0], 16)
                if not size:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    break
                parts.append(self.rfile.read(size))
                self.rfile.read(2)
            return b"".join(parts)
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def proxy(self, target=None):
        conn = http.client.HTTPConnection("127.0.0.1", 5678, timeout=180)
        try:
            body = self.request_body()
            connection_headers = {x.strip().lower() for x in self.headers.get("Connection", "").split(",")}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | connection_headers | {"content-length"}}
            if body or self.headers.get("Content-Length") is not None:
                headers["Content-Length"] = str(len(body))
            headers.setdefault("X-Forwarded-Host", self.headers.get("Host", "localhost:8787"))
            headers.setdefault("X-Forwarded-Proto", "http")
            conn.request(self.command, target or self.path, body=body or None, headers=headers)
            response = conn.getresponse()
            data = response.read()
            self.send_response(response.status, response.reason)
            response_hop = HOP | {x.strip().lower() for x in response.getheader("Connection", "").split(",")}
            for key, value in response.getheaders():
                if key.lower() in response_hop | {"content-length"}:
                    continue
                if key.lower() == "location":
                    parsed = urlsplit(value)
                    if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0") and parsed.port == 5678:
                        value = parsed.path + ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (OSError, http.client.HTTPException) as exc:
            self.json({"error": "The live n8n service could not be reached.", "detail": str(exc)}, 502)
        finally:
            conn.close()

    def handle_request(self):
        path = urlsplit(self.path).path
        if any(path == prefix or path.startswith(prefix + "/") for prefix in PREFIXES):
            return self.proxy()
        if path == "/api/review-queue":
            return self.proxy("/webhook/review-queue")
        if self.command not in ("GET", "HEAD"):
            return self.json({"error": "Method not allowed"}, 405)
        try:
            if path == "/api/scoreboard":
                return self.json(live_scoreboard())
            if path == "/api/samples":
                with SAMPLES.open(newline="", encoding="utf-8-sig") as f:
                    return self.json(list(csv.DictReader(f)))
            name = "index.html" if path == "/" else unquote(path).lstrip("/")
            if name.startswith("static/"):
                name = name[7:]
            file = (STATIC / name).resolve()
            if not file.is_relative_to(STATIC.resolve()) or not file.is_file():
                return self.json({"error": "Not found"}, 404)
            return self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        except (OSError, ValueError) as exc:
            self.json({"error": "Reference data unavailable", "detail": str(exc)}, 500)

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = handle_request

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8787), Handler)
    print("Listening on http://0.0.0.0:8787", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
