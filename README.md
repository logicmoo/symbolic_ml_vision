# Symbolic ML Vision (Omega Vision)

Symbolic recognition, cross-frame deduction, and **inductive** reasoning over pixel/action
frame sequences. Each frame is turned into symbolic facts, consecutive frames are compared to
deduce movement / grouping / events, and whole sequences are generalised into inductive guesses —
all emitted as **Prolog (`.pl`)**, **MeTTa (`.metta`)**, and **JSON (`.json`)** files that you can
browse in the built-in **AtomSpace Explorer**.

Everything symbolic is produced by **Python + SWI-Prolog only** — no JavaScript is involved in
recognition, deduction, induction, or the `.pl`⇄`.metta`⇄`.json` conversion. The browser UI is an
optional viewer.

## Architecture

- **SWI-Prolog is the top-level host.** It embeds Python in-process via **Janus**, serves the app
  with `library(http)`, and runs the Prolog rule pack with full RAM.
- **Shared core.** `recognition_webapp/frame_pipeline.py` (recognition → deduction → per-frame
  `.pl`/`.metta`/`.json` → `.metta` sidecar for every `.pl` → inductive guesses) is used identically
  by the web server and the standalone crawler.
- **One request handler.** `recognition_webapp/web_api.py` (`dispatch`) is shared by the swipl host
  and a thin Python `http.server` fallback (`app.py`), so behaviour never forks.
- **Installable SWI pack** at `prolog/omega_vision/` (`pack_install/1`) that **self-provisions** a
  dedicated Python venv on first run.

### Paths

| Surface | Path |
|---|---|
| Web UI | `/omega_vision/ui/` (`/` and `/shapes` redirect here) |
| JSON API | `/omega_vision/api/v1/…` |

Both are served from a single port per host.

## Install

Two installers, both pointing at the same dedicated `.venv`:

```prolog
% SWI-Prolog pack (rules + swipl entry points)
?- pack_install('prolog/omega_vision').
```

```bash
# Python core (recognition / deduction / induction)
pip install .
```

SWI-Prolog 9.2+ (with `library(janus)`) and Python 3.11+ are required. On first launch the pack
creates `./.venv` and installs `numpy scipy Pillow opencv-contrib-python-headless scikit-image`
itself — no manual venv or `PYTHONPATH` needed.

## Run

**swipl-hosted web service** (production target):

```bash
swipl -g "use_module(library(omega_vision)), run_main(omega_vision/web_service, ['--port','8765'])"
```

**Standalone Python host** (test / fallback):

```bash
python -B recognition_webapp/app.py --port 8765
```

Open <http://127.0.0.1:8765/> → redirects to the UI.

**Crawler** — walk every recording, writing `.pl`/`.metta`/`.json` next to each frame and inducing
guesses per sequence. It self-relaunches when source changes and idles until it does:

```bash
# swipl entry
swipl -g "use_module(library(omega_vision)), run_main(omega_vision/learn_movie, [])"
# or the Python host
python -B recognition_webapp/crawler.py
```

## Dataset helpers

```powershell
python .\dataset.py verify
python .\dataset.py list | ConvertFrom-Json
python .\dataset.py stream --sequence recordings/events_tests/accelerated | python .\examples\consume_frames.py
```

The runtime data root (`data/omega_vision/…`: recordings + generated output + crawler control
files) lives outside the code repo and is git-ignored.

## Layout

```
prolog/omega_vision/          SWI pack (pack.pl + prolog/omega_vision/*.pl)
  web_service.pl              swipl HTTP server (library(http) + Janus)
  learn_movie.pl              swipl crawler entry
  venv_boot.pl                self-provisioning venv
  pipeline_bridge.pl + rules  shape_finder / group_regions / turtle_programs / group_acceptance
recognition_webapp/           Python core (pip-installable)
  frame_pipeline.py           shared recognition→deduction→induction engine
  web_api.py                  shared HTTP dispatch
  app.py                      thin http.server host
  crawler.py                  standalone crawler
  source_syntax.py            Prolog⇄MeTTa⇄JSON conversion (Python only)
  static/ + clause_explorer/  AtomSpace Explorer UI
docs/                         design + usage docs
```

## License

MIT — see [LICENSE](LICENSE).
