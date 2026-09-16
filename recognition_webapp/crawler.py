"""Standalone recordings crawler (Python host; the swipl omega_vision/learn_movie entry can wrap this).

Walks every recording under <data-root>/recordings, runs the shared frame_pipeline.process_recording
on each (writing .pl/.metta/.json next to every frame, ensuring a .metta for every .pl, and inducing
guesses per sequence), and maintains two control files under <data-root>/.crawler:

* source.stamp   - the latest source-update timestamp the crawler launched with. Outputs older than
                   this are regenerated. When the on-disk source becomes newer, the crawler
                   re-execs a fresher copy of itself.
* produced.jsonl - one JSON line per produced .pl/.metta/.json file, so a browser can see which
                   recordings are freshly interesting.

When a full pass finds nothing stale, it sleeps, polling every 10s, and wakes/re-execs when the
source stamp advances.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from frame_pipeline import find_recordings, process_recording, source_epoch

POLL_SECONDS = 10


def control_dir(data_root: Path) -> Path:
    path = data_root / ".crawler"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_stamp(data_root, epoch: float) -> None:
    data_root = Path(data_root)
    (control_dir(data_root) / "source.stamp").write_bytes(
        (json.dumps({"epoch": epoch, "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(epoch))}) + "\n").encode("utf-8"))


def log_produced(data_root, records: list[dict]) -> None:
    if not records:
        return
    data_root = Path(data_root)
    with (control_dir(data_root) / "produced.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps({"ts": time.time(), **record}, ensure_ascii=True) + "\n")


def reexec() -> None:
    print("[crawler] source changed; re-launching a fresher crawler.", flush=True)
    os.execv(sys.executable, [sys.executable, "-B", os.path.abspath(__file__), *sys.argv[1:]])


def crawl_once(data_root, pipeline: str, launched: float) -> bool:
    """One pure pass over all recordings (no re-exec). Returns True if anything was (re)generated.

    Host-agnostic: called by this Python crawler and by the swipl omega_vision/learn_movie entry via
    Janus. Relaunch-on-source-change is the host loop's responsibility, not this function's.
    """
    data_root = Path(data_root)
    did_work = False
    for recording in find_recordings(data_root / "recordings"):
        result = process_recording(recording, pipeline=pipeline, stamp_epoch=launched)
        produced = result.get("produced", [])
        if produced:
            did_work = True
            log_produced(data_root, produced)
            guesses = len(result.get("induction", {}).get("guesses", []))
            print(f"[crawler] {result['recording']}: {len(produced)} files, "
                  f"{guesses} guesses, {len(result.get('errors', []))} errors", flush=True)
    return did_work


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "omega_vision")
    parser.add_argument("--pipeline", choices=("prolog", "opencv"), default="prolog")
    parser.add_argument("--once", action="store_true", help="Single pass, then exit (no sleep/relaunch).")
    args = parser.parse_args(argv)

    data_root = args.data_root.resolve()
    launched = source_epoch()
    write_stamp(data_root, launched)
    print(f"[crawler] data-root {data_root}; pipeline {args.pipeline}; source stamp {launched:.0f}", flush=True)

    while True:
        if source_epoch() > launched:
            reexec()
        did_work = crawl_once(data_root, args.pipeline, launched)
        if args.once:
            return 0
        if not did_work:
            # Nothing stale: sleep until the source stamp advances, then re-exec fresher code.
            print("[crawler] idle; watching source stamp every 10s.", flush=True)
            while source_epoch() <= launched:
                time.sleep(POLL_SECONDS)
            reexec()


if __name__ == "__main__":
    raise SystemExit(main())
