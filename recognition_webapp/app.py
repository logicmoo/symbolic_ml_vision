"""Run the standalone recognition webapp on loopback, with no persistence."""

import sys

sys.dont_write_bytecode = True

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from recognition import examples, recognize
from pipelines import PipelineError, capabilities, run_pipeline
from demos import DemoCatalog
from expectations import frame_expectations
from two_frame import deduce_two_frames
from tracker import track_frame, mapping as tracker_mapping
from group_tracker import track_groups
from diff_frames import diff_frames
from source_syntax import analyze_sources


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = ROOT.parent / "data" / "omega_vision"
MAX_BODY = 14 * 1024 * 1024
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/shapes": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/clause_explorer.js": ("clause_explorer.js", "text/javascript; charset=utf-8"),
    "/clause_explorer.css": ("clause_explorer.css", "text/css; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
RECOGNITION_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "Recognition/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def reply(self, status: int, body: bytes, content_type: str) -> None:
        style_nonce = secrets.token_urlsafe(24) if content_type.startswith("text/html") else None
        if style_nonce:
            body = body.replace(b"</head>", (
                f'<meta name="clause-explorer-style-nonce" content="{style_nonce}"></head>'
            ).encode())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            + (f"style-src 'self' 'nonce-{style_nonce}'; " if style_nonce else "style-src 'self'; ")
            +
            "img-src 'self' blob: data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def json(self, status: int, value: object) -> None:
        self.reply(status, json.dumps(value, allow_nan=False).encode("utf-8"), "application/json")

    def authorized(self) -> bool:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in hosts or (
            origin is not None and origin not in {f"http://{host}" for host in hosts}
        ):
            self.json(403, {"error": "Use the local app URL; cross-origin requests are not allowed."})
            return False
        return True

    def do_GET(self) -> None:
        if not self.authorized():
            return
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.json(200, {"ok": True, "app": "recognition", "persistent_storage": False})
        elif path == "/api/capabilities":
            self.json(200, capabilities())
        elif path == "/api/examples":
            self.json(200, examples())
        elif path in ("/api/demos", "/api/demos/frame", "/api/demos/expectations"):
            try:
                demos = DemoCatalog(self.server.data_root)
                if path == "/api/demos":
                    self.json(200, demos.listing())
                else:
                    query = parse_qs(urlsplit(self.path).query)
                    if any(len(query.get(key, [])) != 1 for key in ("sequence", "frame")):
                        raise ValueError("Choose a demo recording and frame.")
                    if path == "/api/demos/expectations":
                        if len(query.get("test", [])) != 1:
                            raise ValueError("Choose a linked test for the frame expectations.")
                        self.json(200, frame_expectations(demos, query["test"][0], query["sequence"][0], query["frame"][0]))
                    else:
                        image = demos.image(query["sequence"][0], query["frame"][0])
                        self.reply(200, image, "image/png")
            except FileNotFoundError:
                self.json(404, {"error": "Demo data or frame is missing. Use --data-root with an existing data/omega_vision export."})
            except KeyError as error:
                self.json(404, {"error": str(error).strip("'")})
            except (OSError, ValueError) as error:
                self.json(422, {"error": str(error)})
        elif path == "/clause-explorer-source":
            key = parse_qs(urlsplit(self.path).query).get("file", [])
            sources = {
                "component": ROOT / "clause_explorer" / "upstream" / "packages" / "omega_vision_ui" / "src" / "components" / "PrologClauseExplorer.tsx",
                "css": ROOT / "clause_explorer" / "explorer.css",
            }
            if len(key) != 1 or key[0] not in sources:
                self.json(404, {"error": "Unknown Clause Explorer source."})
                return
            self.reply(200, sources[key[0]].read_bytes(), "text/plain; charset=utf-8")
        elif path in STATIC:
            filename, content_type = STATIC[path]
            content = (ROOT / "static" / filename).read_bytes()
            if filename == "index.html":
                if path == "/shapes":
                    content = content.replace(b'data-page="demos"', b'data-page="shapes"').replace(b"<title>Vision demos</title>", b"<title>Shape explorer</title>")
                for asset in ("app.js", "clause_explorer.js", "clause_explorer.css", "style.css"):
                    version = int((ROOT / "static" / asset).stat().st_mtime)
                    content = content.replace(f'/{asset}"'.encode(), f'/{asset}?v={version}"'.encode())
            self.reply(200, content, content_type)
        else:
            self.json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self.authorized():
            return
        if self.path not in ("/api/recognize", "/api/deduce2", "/api/track", "/api/diff", "/api/source-syntax"):
            self.json(404, {"error": "Not found."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Content-Type must be application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.json(400, {"error": "Invalid Content-Length."})
            return
        if self.headers.get("Transfer-Encoding") or not 0 < length <= MAX_BODY:
            self.json(413, {"error": "A fixed JSON body of at most 14 MiB is required."})
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self.json(400, {"error": "Incomplete request body."})
            return
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError):
            self.json(400, {"error": "Invalid JSON."})
            return
        if self.path == "/api/source-syntax":
            try:
                if not isinstance(payload, dict) or set(payload) != {"sources"}:
                    raise ValueError("A sources array is required.")
                self.json(200, analyze_sources(payload["sources"]))
            except (ValueError, TypeError, RecursionError) as error:
                self.json(422, {"error": str(error)})
            return
        if self.path == "/api/deduce2":
            try:
                if not isinstance(payload, dict):
                    raise ValueError("A JSON object with current and previous frames is required.")
                current = payload.get("current")
                previous = payload.get("previous")
                # Drop OpenCV's per-frame r# ids as early as possible: relabel both frames'
                # objects with the tracker's clip-stable e# identities before deducing, so
                # matches / occluders / reveals all reference stable ids (r# kept as nativeId).
                sequence_id = payload.get("sequenceId")
                current_order = payload.get("currentOrder")
                previous_order = payload.get("previousOrder")
                if (isinstance(sequence_id, str) and sequence_id and type(current_order) is int
                        and type(previous_order) is int and isinstance(current, dict) and isinstance(previous, dict)):
                    width, height = payload.get("width"), payload.get("height")
                    track_frame(sequence_id, previous_order, previous.get("objects") or [], width, height)
                    track_frame(sequence_id, current_order, current.get("objects") or [], width, height)
                    cmap = tracker_mapping(sequence_id, current_order)
                    pmap = tracker_mapping(sequence_id, previous_order)
                    relabel = lambda objs, m: [{**o, "id": m.get(o.get("id"), o.get("id")), "nativeId": o.get("id")} for o in objs]
                    current = {"objects": relabel(current.get("objects") or [], cmap)}
                    previous = {"objects": relabel(previous.get("objects") or [], pmap)}
                    map_groups = lambda gs, m: {layer: [sorted({m.get(r, r) for r in members})
                                                        for members in (gs or {}).get(layer, [])]
                                                for layer in ("G", "W")}
                    cur_groups = map_groups(payload.get("currentGroups"), cmap)
                    prev_groups = map_groups(payload.get("previousGroups"), pmap)
                    # Assign clip-stable numeric group ids (G1, W2, ...) via the group tracker.
                    prev_gids = track_groups(sequence_id, previous_order, prev_groups)
                    cur_gids = track_groups(sequence_id, current_order, cur_groups)
                    def _with_ids(groups, gids):
                        out = []
                        for layer in ("G", "W"):
                            for i, members in enumerate(groups.get(layer, [])):
                                gid = gids.get(layer, [])[i] if i < len(gids.get(layer, [])) else f"{layer.lower()}?"
                                out.append({"id": gid, "layer": layer, "members": members})
                        return out
                    cur_group_list = _with_ids(cur_groups, cur_gids)
                    prev_group_list = _with_ids(prev_groups, prev_gids)
                    result = deduce_two_frames(current, previous, width=width, height=height,
                                               current_order=current_order, previous_order=previous_order,
                                               current_groups=cur_group_list, previous_groups=prev_group_list)
                else:
                    result = deduce_two_frames(current, previous)
            except ValueError as error:
                self.json(422, {"error": str(error)})
            else:
                self.json(200, result)
            return
        if self.path == "/api/track":
            try:
                if not isinstance(payload, dict):
                    raise ValueError("A JSON object with sequenceId, order, and objects is required.")
                result = track_frame(payload.get("sequenceId"), payload.get("order"), payload.get("objects"),
                                     payload.get("width"), payload.get("height"),
                                     payload.get("channel", "frame"))
            except ValueError as error:
                self.json(422, {"error": str(error)})
            else:
                self.json(200, result)
            return
        if self.path == "/api/diff":
            try:
                if not isinstance(payload, dict):
                    raise ValueError("A JSON object with current and previous frame images is required.")
                result = diff_frames(payload.get("current"), payload.get("previous"),
                                     payload.get("tolerance", 40))
            except ValueError as error:
                self.json(422, {"error": str(error)})
            else:
                self.json(200, result)
            return
        if not RECOGNITION_LOCK.acquire(blocking=False):
            self.json(503, {"error": "Recognition is busy. Try again shortly."})
            return
        try:
            if isinstance(payload, dict) and payload.get("pipeline") in ("opencv", "prolog"):
                result = run_pipeline(payload)
            elif isinstance(payload, dict) and payload.get("pipeline", "geometry") == "geometry":
                result = recognize(payload)
            else:
                raise ValueError("Unknown recognition pipeline.")
        except ValueError as error:
            self.json(422, {"error": str(error)})
        except PipelineError as error:
            self.json(503, {"error": str(error)})
        else:
            self.json(200, result)
        finally:
            RECOGNITION_LOCK.release()


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
