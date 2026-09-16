"""Standalone Python HTTP host for Recognition Studio (pytest / plain-`python` fallback).

The production entry point is server.pl (swipl-hosted `library(http)` with Python embedded via
Janus). This module keeps a thin `http.server` host so the test-suite and a bare `python app.py`
still work. Both hosts route through the single shared `web_api.dispatch`, so no request behaviour
is duplicated between them.
"""

import sys

sys.dont_write_bytecode = True

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from web_api import dispatch, DEFAULT_DATA_ROOT, MAX_BODY

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    server_version = "Recognition/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def _emit(self, response: dict) -> None:
        body = base64.b64decode(response["body_b64"])
        self.send_response(response["status"])
        for name, value in response["headers"].items():
            if name.lower() != "content-length":
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _call(self, method: str, body: bytes = b"") -> dict:
        split = urlsplit(self.path)
        return dispatch(
            method, split.path, split.query, body,
            host=self.headers.get("Host"), origin=self.headers.get("Origin"),
            port=self.server.server_address[1],
            content_type=self.headers.get_content_type() if method == "POST" else "",
            transfer_encoding=self.headers.get("Transfer-Encoding"),
            data_root=str(self.server.data_root),
        )

    def do_GET(self) -> None:
        self._emit(self._call("GET"))

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._emit(self._call("POST", b""))  # oversized/invalid; dispatch returns 413
            return
        body = self.rfile.read(length) if length else b""
        self._emit(self._call("POST", body))


def make_server(port: int, data_root: Path = DEFAULT_DATA_ROOT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.data_root = data_root
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT, help="Existing visual-demo export directory (read-only)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        server = make_server(args.port, args.data_root)
    except OSError as error:
        parser.exit(1, f"Could not start recognition webapp: {error}\n")
    print(f"Recognition webapp: http://127.0.0.1:{args.port}", flush=True)
    print(f"Project: {ROOT}\nImages and results are not saved. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
