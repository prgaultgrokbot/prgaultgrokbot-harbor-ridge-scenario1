#!/usr/bin/env python3
"""Harbor Ridge reference demo. Stdlib only; n8n remains the workflow owner."""
import csv
import http.client
import json
import mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SOURCE = Path("/workspace/capstones/scenario1_solution/files")
RESULTS = SOURCE / "results/test_results_20261102_145509.json"
SAMPLES = SOURCE / "testset/test_emails.csv"
PREFIXES = ("/form", "/webhook", "/webhook-waiting", "/form-waiting")
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}

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
                data = json.loads(RESULTS.read_text())
                data["summary"] = {
                    "title": "Reference Gemini run · 32 of 32 routed correctly",
                    "description": "25 auto-routed; 6 complaints and 1 other item held for human review. No complaints missed. Manual misroute baseline: 30%.",
                    "source": RESULTS.name,
                    "scope": "Historical reference run; live demo submissions do not change these metrics.",
                    "correctly_routed": round(data["routing_accuracy"] * data["labelled"]),
                    "baseline_improvement_percentage_points": round((data["baseline_misroute_rate"] - data["misroute_rate"]) * 100, 1),
                }
                return self.json(data)
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
