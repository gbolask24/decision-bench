"""python -m dbench watch: a local page that follows a run as it happens. Reads logs/runs/*/summary.json,
which the runner rewrites every few seconds; serves only on this machine (127.0.0.1)."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .live import list_runs

PAGE = Path(__file__).with_name("watch.html")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def make_server(root: Path, port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    root = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/runs":
                return self._send(200, json.dumps(list_runs(root)).encode(), "application/json")
            if u.path == "/api/summary":
                name = (parse_qs(u.query).get("run") or [""])[0]
                f = root / name / "summary.json"
                if NAME.match(name) and f.resolve().parent.parent == root and f.exists():
                    return self._send(200, f.read_bytes(), "application/json")
            self._send(404, b'{"error": "not found"}', "application/json")

        def log_message(self, *args):  # keep the terminal quiet; the page is the view
            pass

    return ThreadingHTTPServer((host, port), Handler)
