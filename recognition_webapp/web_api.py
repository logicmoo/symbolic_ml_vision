"""Host-agnostic HTTP request handling for Recognition Studio.

The whole request lifecycle (routing, origin check, CSP/nonce, static serving, JSON API) lives here
as one pure function, `dispatch`, so the exact same logic runs under two hosts:

* the standalone Python `http.server` in app.py (used by pytest and plain-`python` runs), and
* the swipl-hosted `library(http)` server in server.pl (production; Python embedded via Janus).

`dispatch` returns a plain dict (status, headers, base64 body) that either host writes verbatim, so
no HTTP behaviour is duplicated or forked between them.
"""

import base64
import json
import secrets
from pathlib import Path

from recognition import examples, recognize
from pipelines import PipelineError, capabilities, run_pipeline
from demos import DemoCatalog, catalog_for, cached_listing, processed_marker as demo_processed_marker
from expectations import frame_expectations
from frame_pipeline import (deduce2_from_payload, process_recording, find_recordings,
                            source_epoch, stabilize_result, clean_generated)
from scene_memory import cached_frame_result, learned_scene
from tracker import track_frame
from diff_frames import diff_frames
from source_syntax import analyze_sources

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = ROOT.parent / "data" / "omega_vision"
MAX_BODY = 14 * 1024 * 1024
WEB_PREFIX = "/omega_vision/ui"
STATIC = {
    f"{WEB_PREFIX}/": ("index.html", "text/html; charset=utf-8"),
    f"{WEB_PREFIX}/shapes": ("index.html", "text/html; charset=utf-8"),
    f"{WEB_PREFIX}/app.js": ("app.js", "text/javascript; charset=utf-8"),
    f"{WEB_PREFIX}/clause_explorer.js": ("clause_explorer.js", "text/javascript; charset=utf-8"),
    f"{WEB_PREFIX}/clause_explorer.css": ("clause_explorer.css", "text/css; charset=utf-8"),
    f"{WEB_PREFIX}/style.css": ("style.css", "text/css; charset=utf-8"),
}
POST_ROUTES = ("/omega_vision/api/v1/recognize", "/omega_vision/api/v1/deduce2", "/omega_vision/api/v1/track", "/omega_vision/api/v1/diff",
               "/omega_vision/api/v1/source-syntax", "/omega_vision/api/v1/process", "/omega_vision/api/v1/clear",
               "/omega_vision/api/v1/powder-load")


def _response(status: int, body: bytes, content_type: str) -> dict:
    """Build the full response (headers + CSP + per-document style nonce) both hosts emit."""
    style_nonce = secrets.token_urlsafe(24) if content_type.startswith("text/html") else None
    if style_nonce:
        body = body.replace(b"</head>", (
            f'<meta name="clause-explorer-style-nonce" content="{style_nonce}"></head>'
        ).encode())
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; "
            + (f"style-src 'self' 'nonce-{style_nonce}'; " if style_nonce else "style-src 'self'; ")
            + "img-src 'self' blob: data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        ),
    }
    return {"status": status, "headers": headers, "body_b64": base64.b64encode(body).decode("ascii")}


def _json(status: int, value: object) -> dict:
    return _response(status, json.dumps(value, allow_nan=False).encode("utf-8"), "application/json")


def _redirect(location: str) -> dict:
    return {"status": 302, "headers": {"Location": location, "Content-Length": "0",
                                       "Cache-Control": "no-store"}, "body_b64": ""}


def _authorized(host: str | None, origin: str | None, port: int) -> bool:
    """Any Host is welcome (local, LAN, tunnel); only cross-SITE browser calls are refused.

    A request is rejected only when it carries an Origin header naming a DIFFERENT site
    than the one addressed - i.e. some other web page scripting this app. Direct visits,
    tunnels (e.g. *.trycloudflare.com) and same-origin app requests always work.
    """
    if not host:
        return False
    if origin is None:
        return True
    local = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origin_host = origin.split("://", 1)[-1]
    if origin_host in local and host in local:
        return True
    return origin_host.lower() == host.lower()


def _query_params(query: str) -> dict:
    from urllib.parse import parse_qs
    return parse_qs(query or "")


# --- POWDER (openworld_dr KB browser) integration -------------------------------------------
# "Load into POWDER" exports the current frame's MeTTa output into POWDER's KBs tree and
# queues it into the live store, so the frame's facts can be browsed there immediately.

def _powder_base() -> str:
    import os
    return os.environ.get("POWDER_URL", "http://127.0.0.1:3050/swish/openworld_dr").rstrip("/")


def _powder_kb_root() -> Path:
    import os
    configured = os.environ.get("POWDER_KB_DIR")
    if configured:
        return Path(configured)
    return ROOT.parent.parent / "openworld_dr" / "KBs"


def _powder_api(method: str, path: str, payload: dict | None = None) -> dict:
    import urllib.request
    url = f"{_powder_base()}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def powder_load_frame(data_root: Path, sequence: str, frame: str) -> dict:
    """Copy the frame's .metta output into POWDER's KBs tree, queue-load it into the live
    store, and return the POWDER browser URL that displays the loaded source."""
    import time
    root = data_root.resolve()
    if sequence.split("/", 1)[0] not in ("recordings", "curated"):
        raise ValueError("Sequences live under recordings/ or curated/.")
    frame_dir = (root / sequence / frame).resolve()
    if not frame_dir.is_relative_to(root) or not frame_dir.is_dir():
        raise ValueError("Unknown frame.")
    sources = sorted(frame_dir.glob("*.metta"))
    if not sources:
        raise ValueError("This frame has no .metta output yet; let the crawler process it first.")
    kb_root = _powder_kb_root()
    if not kb_root.is_dir():
        raise ValueError(f"POWDER KBs directory not found at {kb_root}; set POWDER_KB_DIR.")
    case = sequence.rsplit("/", 1)[-1]
    export_dir = kb_root / "omega_vision" / "frames" / case / frame
    export_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for source in sources:
        target = export_dir / source.name
        data = source.read_bytes().replace(b"\r\n", b"\n")
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)
        exported.append(f"KBs/omega_vision/frames/{case}/{frame}/{source.name}")
    try:
        generation = _powder_api("GET", "/api/status")["generation"]
        job = _powder_api("POST", "/api/kb/queue", {"files": exported, "generation": generation})
        job_id = job.get("id")
        outcome = job
        for _ in range(60):
            if not job_id:
                break
            outcome = _powder_api("GET", f"/api/tasks/result?id={job_id}")
            if "result" in outcome or "error" in outcome:
                break
            time.sleep(0.5)
    except OSError as error:
        raise ValueError(f"POWDER is not reachable at {_powder_base()}: {error}")
    if isinstance(outcome, dict) and outcome.get("error"):
        raise ValueError(f"POWDER refused the load: {json.dumps(outcome['error'])[:400]}")
    primary = next((p for p in exported if p.endswith("induction.metta")), exported[0])
    return {"sequenceId": sequence, "frame": frame, "loaded": exported,
            "job": job_id, "result": outcome.get("result") if isinstance(outcome, dict) else None,
            "powderUrl": f"{_powder_base()}/#/source?path={primary}"}


def _static(path: str) -> dict:
    filename, content_type = STATIC[path]
    content = (ROOT / "static" / filename).read_bytes()
    if filename == "index.html":
        if path == f"{WEB_PREFIX}/shapes":
            content = content.replace(b'data-page="demos"', b'data-page="shapes"').replace(
                b"<title>Vision demos</title>", b"<title>Shape explorer</title>")
        for asset in ("app.js", "clause_explorer.js", "clause_explorer.css", "style.css"):
            version = int((ROOT / "static" / asset).stat().st_mtime)
            content = content.replace(f'{WEB_PREFIX}/{asset}"'.encode(), f'{WEB_PREFIX}/{asset}?v={version}"'.encode())
    return _response(200, content, content_type)


def _get(path: str, query: str, data_root: Path) -> dict:
    # Redirect the bare root (and the pre-move UI paths) to the namespaced UI.
    if path in ("/", "", WEB_PREFIX):
        return _redirect(f"{WEB_PREFIX}/")
    if path == "/shapes":
        return _redirect(f"{WEB_PREFIX}/shapes")
    if path == "/omega_vision/api/v1/health":
        return _json(200, {"ok": True, "app": "recognition", "persistent_storage": False})
    if path == "/omega_vision/api/v1/capabilities":
        return _json(200, capabilities())
    if path == "/omega_vision/api/v1/examples":
        return _json(200, examples())
    if path == "/omega_vision/api/v1/recordings":
        root = data_root / "recordings"
        listing = []
        for recording in find_recordings(root):
            frames = sum(1 for child in recording.iterdir()
                         if child.is_dir() and child.name.isdigit() and (child / "image.png").is_file())
            # Processed marker: induction lives under the LAST frame dir (legacy root honoured).
            marker = demo_processed_marker(recording)
            listing.append({"id": recording.relative_to(data_root).as_posix(),
                            "frames": frames, "processed": marker is not None,
                            "outputsUpdated": marker.stat().st_mtime if marker else 0})
        return _json(200, {"recordings": listing, "sourceEpoch": source_epoch()})
    if path == "/omega_vision/api/v1/scene":
        params = _query_params(query)
        if len(params.get("sequence", [])) != 1:
            return _json(422, {"error": "Choose a recording sequence for the learned scene."})
        upto = None
        if params.get("upto"):
            if len(params["upto"]) != 1 or not params["upto"][0].isdigit():
                return _json(422, {"error": "upto must be a frame number."})
            upto = int(params["upto"][0])
        static_only = params.get("static", ["0"])[0] in ("1", "true")
        try:
            return _json(200, learned_scene(data_root, params["sequence"][0], upto=upto,
                                            static_only=static_only))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/demos/frame-files":
        # Enumerate the frame's N/ directory verbatim: every text file (pl/metta/json)
        # that exists on disk, reserved inputs included as read-only evidence.
        params = _query_params(query)
        if any(len(params.get(key, [])) != 1 for key in ("sequence", "frame")):
            return _json(422, {"error": "Choose a recording sequence and frame."})
        sequence, frame = params["sequence"][0], params["frame"][0]
        root = data_root.resolve()
        if sequence.split("/", 1)[0] not in ("recordings", "curated") or not frame.isdigit():
            return _json(422, {"error": "Frames live under recordings/ or curated/ with numeric ids."})
        frame_dir = (root / sequence / frame).resolve()
        if not frame_dir.is_relative_to(root) or not frame_dir.is_dir():
            return _json(404, {"error": "Unknown frame."})
        media = {".json": "application/json", ".pl": "text/x-prolog", ".metta": "text/plain"}
        listing = []
        for file_path in sorted(frame_dir.iterdir()):
            if not file_path.is_file() or file_path.suffix not in media:
                continue
            try:
                listing.append({"name": file_path.name, "content": file_path.read_text(encoding="utf-8"),
                                "media_type": media[file_path.suffix]})
            except (OSError, UnicodeDecodeError):
                continue
        return _json(200, {"sequenceId": sequence, "frame": frame, "files": listing})
    if path == "/omega_vision/api/v1/demos/state":
        # A frame's reserved state.json (read-only input evidence): the recorded command
        # that led INTO this frame, game/level scalars, timing. Never pipeline output.
        params = _query_params(query)
        if any(len(params.get(key, [])) != 1 for key in ("sequence", "frame")):
            return _json(422, {"error": "Choose a recording sequence and frame."})
        sequence, frame = params["sequence"][0], params["frame"][0]
        root = data_root.resolve()
        if sequence.split("/", 1)[0] not in ("recordings", "curated") or not frame.isdigit():
            return _json(422, {"error": "Frames live under recordings/ or curated/ with numeric ids."})
        state_path = (root / sequence / frame / "state.json").resolve()
        if not state_path.is_relative_to(root) or not state_path.is_file():
            return _json(404, {"error": "This frame has no recorded state.json."})
        try:
            return _json(200, json.loads(state_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return _json(422, {"error": "The frame's state.json is unreadable."})
    if path == "/omega_vision/api/v1/induction":
        params = _query_params(query)
        if len(params.get("sequence", [])) != 1:
            return _json(422, {"error": "Choose a recording sequence for the induction summary."})
        sequence = params["sequence"][0]
        root = data_root.resolve()
        if not isinstance(sequence, str) or sequence.split("/", 1)[0] not in ("recordings", "curated"):
            return _json(422, {"error": "Induction sequences live under recordings/ or curated/."})
        try:
            recording = (root / sequence).resolve()
        except OSError:
            return _json(422, {"error": "Invalid sequence path."})
        if (not recording.is_relative_to(root) or not recording.is_dir()
                or not ((recording / "recording.json").is_file()
                        or any(child.is_dir() and child.name.isdigit() and (child / "image.png").is_file()
                               for child in recording.iterdir()))):
            return _json(404, {"error": "Unknown recording."})
        # Induction always lives under a frame dir: beliefs AS OF that frame (only evidence
        # that has already happened). Without upto, serve the LAST frame's end state.
        upto = params.get("upto", [None])[0]
        frame_dirs_sorted = sorted((child for child in recording.iterdir()
                                    if child.is_dir() and child.name.isdigit()),
                                   key=lambda child: int(child.name))
        candidates = []
        if upto is not None and upto.isdigit():
            candidates += [recording / upto / "induction.json", recording / upto / "beliefs.json"]
            scope = "as_of_frame"
        else:
            candidates += [frame / name for frame in reversed(frame_dirs_sorted)
                           for name in ("induction.json", "beliefs.json")]
            scope = "final_frame"
        candidates.append(recording / "induction.json")  # legacy root layout
        for snapshot_path in candidates:
            if not snapshot_path.is_file():
                continue
            try:
                payload_out = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            return _json(200, {"sequenceId": sequence,
                               "upto": payload_out.get("upto"),
                               "induction": payload_out,
                               "scope": scope if snapshot_path.parent != recording else "legacy_root",
                               "updated": snapshot_path.stat().st_mtime})
        return _json(404, {"error": "The crawler has not induced this recording yet."})
    if path in ("/omega_vision/api/v1/demos", "/omega_vision/api/v1/demos/frame", "/omega_vision/api/v1/demos/expectations"):
        try:
            if path == "/omega_vision/api/v1/demos":
                return _json(200, cached_listing(data_root))
            demos = catalog_for(data_root)
            params = _query_params(query)
            if any(len(params.get(key, [])) != 1 for key in ("sequence", "frame")):
                raise ValueError("Choose a demo recording and frame.")
            if path == "/omega_vision/api/v1/demos/expectations":
                if len(params.get("test", [])) != 1:
                    raise ValueError("Choose a linked test for the frame expectations.")
                return _json(200, frame_expectations(demos, params["test"][0], params["sequence"][0], params["frame"][0]))
            image = demos.image(params["sequence"][0], params["frame"][0])
            return _response(200, image, "image/png")
        except FileNotFoundError:
            return _json(404, {"error": "Demo data or frame is missing. Use --data-root with an existing data/omega_vision export."})
        except KeyError as error:
            return _json(404, {"error": str(error).strip("'")})
        except (OSError, ValueError) as error:
            return _json(422, {"error": str(error)})
    if path == "/clause-explorer-source":
        key = _query_params(query).get("file", [])
        sources = {
            "component": ROOT / "clause_explorer" / "upstream" / "packages" / "omega_vision_ui" / "src" / "components" / "PrologClauseExplorer.tsx",
            "css": ROOT / "clause_explorer" / "explorer.css",
        }
        if len(key) != 1 or key[0] not in sources:
            return _json(404, {"error": "Unknown Clause Explorer source."})
        return _response(200, sources[key[0]].read_bytes(), "text/plain; charset=utf-8")
    if path in STATIC:
        return _static(path)
    return _json(404, {"error": "Not found."})


def _post(path: str, body: bytes, content_type: str, transfer_encoding: str | None, data_root: Path) -> dict:
    if path not in POST_ROUTES:
        return _json(404, {"error": "Not found."})
    if content_type != "application/json":
        return _json(415, {"error": "Content-Type must be application/json."})
    if transfer_encoding or not 0 < len(body) <= MAX_BODY:
        return _json(413, {"error": "A fixed JSON body of at most 14 MiB is required."})
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return _json(400, {"error": "Invalid JSON."})

    if path == "/omega_vision/api/v1/source-syntax":
        try:
            if not isinstance(payload, dict) or set(payload) != {"sources"}:
                raise ValueError("A sources array is required.")
            return _json(200, analyze_sources(payload["sources"]))
        except (ValueError, TypeError, RecursionError) as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/process":
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get("recording"), str):
                raise ValueError("A recording id (e.g. recordings/events_tests/bounce) is required.")
            relative = payload["recording"].replace("\\", "/").strip("/")
            root = data_root.resolve()
            recording = (root / relative).resolve()
            if not recording.is_relative_to(root / "recordings") or not (recording / "recording.json").is_file():
                raise ValueError("Unknown recording.")
            return _json(200, process_recording(recording, pipeline=payload.get("pipeline", "prolog"),
                                                force=bool(payload.get("force"))))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/powder-load":
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get("sequence"), str) \
                    or not isinstance(payload.get("frame"), str) or not payload["frame"].isdigit():
                raise ValueError("A recording sequence and numeric frame are required.")
            return _json(200, powder_load_frame(data_root, payload["sequence"], payload["frame"]))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/clear":
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get("recording"), str):
                raise ValueError("A recording id (e.g. recordings/events_tests/blocked) is required.")
            relative = payload["recording"].replace("\\", "/").strip("/")
            if relative.split("/", 1)[0] not in ("recordings", "curated"):
                raise ValueError("Recordings live under recordings/ or curated/.")
            root = data_root.resolve()
            recording = (root / relative).resolve()
            if (not recording.is_relative_to(root) or not recording.is_dir()
                    or not any(child.is_dir() and child.name.isdigit() and (child / "image.png").is_file()
                               for child in recording.iterdir())):
                raise ValueError("Unknown recording.")
            # Deletes ONLY files this pipeline generated (manifest-matched); the reserved
            # inputs (image.*, state.json) and anything else are untouchable by contract.
            removed = clean_generated(recording, dry_run=False)
            return _json(200, {"recording": relative,
                               "removed": len(removed),
                               "files": [p.relative_to(recording).as_posix() for p in removed[:200]]})
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/deduce2":
        try:
            return _json(200, deduce2_from_payload(payload))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/track":
        try:
            if not isinstance(payload, dict):
                raise ValueError("A JSON object with sequenceId, order, and objects is required.")
            return _json(200, track_frame(payload.get("sequenceId"), payload.get("order"),
                                          payload.get("objects"), payload.get("width"),
                                          payload.get("height"), payload.get("channel", "frame")))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    if path == "/omega_vision/api/v1/diff":
        try:
            if not isinstance(payload, dict):
                raise ValueError("A JSON object with current and previous frame images is required.")
            return _json(200, diff_frames(payload.get("current"), payload.get("previous"), payload.get("tolerance", 40)))
        except ValueError as error:
            return _json(422, {"error": str(error)})
    # Recognition is stateless and thread-safe; the threading host serves requests concurrently.
    try:
        if isinstance(payload, dict) and payload.get("pipeline") in ("opencv", "prolog"):
            # Prefer the crawler's cached symbolic artifacts; stale caches (older than the
            # source stamp or the reserved inputs) are invalid and fall through to a live run.
            result = cached_frame_result(payload, data_root) or run_pipeline(payload)
            frame = payload.get("frame") if isinstance(payload, dict) else None
            if (not result.get("cached") and "stable_ids" not in result
                    and isinstance(frame, dict) and isinstance(frame.get("frameId"), str)
                    and frame["frameId"].isdigit() and isinstance(frame.get("sequenceId"), str)
                    and frame["sequenceId"].split("/", 1)[0] in ("recordings", "curated")):
                try:
                    # Live recorded-frame runs also show clip-stable e# identities.
                    stabilize_result(result, frame["sequenceId"], int(frame["frameId"]))
                except ValueError:
                    pass
        elif isinstance(payload, dict) and payload.get("pipeline", "geometry") == "geometry":
            result = recognize(payload)
        else:
            raise ValueError("Unknown recognition pipeline.")
    except ValueError as error:
        return _json(422, {"error": str(error)})
    except PipelineError as error:
        return _json(503, {"error": str(error)})
    return _json(200, result)


def dispatch(method: str, path: str, query: str = "", body: object = b"", *,
             host: str | None = None, origin: str | None = None, port: int = 0,
             content_type: str = "", transfer_encoding: str | None = None,
             data_root: object = None) -> dict:
    """Route one HTTP request to a full response dict. Host-agnostic; safe for Janus (JSON-only)."""
    if data_root is None:
        data_root = DEFAULT_DATA_ROOT
    data_root = Path(data_root)
    if not _authorized(host, origin, port):
        return _json(403, {"error": "Use the local app URL; cross-origin requests are not allowed."})
    if isinstance(body, str):
        body = body.encode("utf-8")
    elif body is None:
        body = b""
    try:
        if method == "GET":
            return _get(path, query, data_root)
        if method == "POST":
            return _post(path, body, content_type, transfer_encoding, data_root)
        return _json(404, {"error": "Not found."})
    except Exception as error:  # never leak a stack trace to the socket
        return _json(500, {"error": f"Internal error: {error}"})


def dispatch_request(req: dict) -> dict:
    """Dict-in / dict-out wrapper for the swipl (Janus) host: marshals plain dicts only.

    `req` keys: method, path, query, body, host, origin, port, content_type, transfer_encoding,
    data_root. Returns {status, headers{...}, body_b64}.
    """
    req = req or {}
    return dispatch(
        str(req.get("method", "GET")).upper(),
        req.get("path", "/"),
        req.get("query", "") or "",
        req.get("body", b"") or b"",
        host=req.get("host"),
        origin=req.get("origin"),
        port=int(req.get("port", 0) or 0),
        content_type=req.get("content_type", "") or "",
        transfer_encoding=req.get("transfer_encoding") or None,
        data_root=req.get("data_root"),
    )
