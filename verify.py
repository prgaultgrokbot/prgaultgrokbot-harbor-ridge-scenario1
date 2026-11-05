#!/usr/bin/env python3
"""Isolated smoke/integration test; no pip, no API key, no original-server changes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO

ROOT = Path(__file__).resolve().parent

def main():
    with tempfile.TemporaryDirectory(prefix="harbor-ridge-check-") as tmp:
        app = Path(tmp) / "app"
        shutil.copytree(ROOT, app, ignore=shutil.ignore_patterns("__pycache__"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, PORT=str(port))
        env.pop("GEMINI_API_KEY", None)
        base = f"http://127.0.0.1:{port}"
        with (Path(tmp) / "server.log").open("w+") as log:
            process = subprocess.Popen([sys.executable, "server.py"], cwd=app, env=env, stdout=log, stderr=log)
            def request(path, fields=None, expected=200, headers=None):
                body = urllib.parse.urlencode(fields).encode() if fields is not None else None
                req = urllib.request.Request(base + path, data=body, headers=headers or {})
                try:
                    with urllib.request.urlopen(req, timeout=5) as r:
                        status, content = r.status, r.read()
                except urllib.error.HTTPError as e:
                    status, content = e.code, e.read()
                assert status == expected, (path, status, content[:200])
                return content
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        request("/healthz")
                        break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("Server did not start")
                for path in ("/", "/static/logo.svg", "/static/logo.png", "/teaching", "/teach",
                             "/teaching_source", "/teach/README.txt", "/teaching_source/cloud_server.py",
                             "/form", "/form/0ff96437-e049-5d4f-b2c4-77d3d8d222ee",
                             "/form/6f68e732-8331-5c86-9168-04cee57bae2a",
                             "/form/161badb9-3351-5e53-bda4-917244a79638", "/webhook/review-queue"):
                    request(path)
                with zipfile.ZipFile(BytesIO(request("/harbor_ridge_teaching_source.zip"))) as z:
                    assert z.testzip() is None
                    assert "teaching_source/cloud_server.py" in z.namelist()
                initial = json.loads(request("/api/scoreboard"))
                sample_rows = json.loads(request("/api/samples"))
                assert len(sample_rows) == 32
                notice = request("/form", {"mode": "ai", "sender": "Test", "subject": "Test", "body": "Fictional"}, expected=400)
                assert b"GEMINI_API_KEY" in notice
                assert json.loads(request("/api/scoreboard"))["items"] == initial["items"]
                request("/form", {"mode": "replay", "sample_id": "T01"})
                assert json.loads(request("/api/scoreboard"))["items"] == initial["items"] + 1
                request("/form", {"mode": "replay", "sample_id": "T06"})
                pending = json.loads(request("/api/review-queue"))
                assert any(r["item_id"] == "T06" for r in pending)
                request("/webhook/review-decision", {"item_id": "T06", "decision": "Accept", "reason": "Training check"})
                assert not any(r["item_id"] == "T06" for r in json.loads(request("/api/review-queue")))
                before_batch = json.loads(request("/api/scoreboard"))["items"]
                request("/webhook/batch-test", {})
                after_batch = json.loads(request("/api/scoreboard"))["items"]
                assert after_batch == before_batch + 32
                request("/form", {"mode": "replay", "sample_id": "T01"}, expected=403, headers={"Origin": "https://other.example"})
                request("/form", {"body": "x" * 20001}, expected=413)
                request("/teaching_source/%2e%2e/server.py", expected=404)
                request("/%2e%2e/server.py", expected=404)
                request("/not-a-file", expected=404)
                print(f"PASS: python3 server.py returned HTTP 200 for / on isolated port {port}.")
                print(f"PASS: hub/assets, 32 samples, source ZIP, 4 panels, no-key notice, replay, review, batch (+32), limits and traversal checks. Initial audit rows: {initial['items']}.")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        # Exercise optional Gemini parsing with a fake network response: never make an API call.
        spec = importlib.util.spec_from_file_location("cloud_demo", app / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from unittest.mock import patch
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, *args):
                answer = json.dumps({"team": "Claims", "complaint_flag": False, "confidence": 0.95, "reason": "Fictional test"})
                return json.dumps({"candidates": [{"content": {"parts": [{"text": answer}]}}]}).encode()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "stub-test-value", "MAX_AI_CALLS_PER_HOUR": "20"}), patch.object(module, "urlopen", return_value=Response()):
            row = module.gemini_triage({"sender": "Test", "subject": "Test", "body": "Fictional"})
            assert row["status"] == "AUTO_ROUTED"
        print("PASS: optional Gemini parsing/audit append with a stub only (no external request).")
        print("Original port 8787 service and bundled data were not modified.")

if __name__ == "__main__":
    main()
