# Symbolic Vision Events

A small, local dataset starter for programs that infer events and connections.
It includes **raw PNG/action sequences** and **structured symbolic inputs**, not
the Omega Vision Workbench or a replacement grader. Use any language or reasoner;
Python 3.12+ is needed only for the supplied readers. No installation is needed.

For the separate recognition-only webapp, see
[`recognition_webapp\README.md`](recognition_webapp/README.md). Run
`python -B .\recognition_webapp\app.py` and open `http://127.0.0.1:8765`.
The app is independent of Workbench. Its Demos page reads this dataset; its
separate Shapes page supports independent uploads and drawing.

Use `list` for the current inventory of tests, sequences, frames, and symbolic
examples.

## Quickstart

Run these PowerShell commands from this repository. These are existing, small
examples; use `list` to discover the rest:

```powershell
python .\dataset.py verify
$catalog = python .\dataset.py list | ConvertFrom-Json
$catalog.inventory
$sequence = "recordings/events_tests/accelerated"
python .\dataset.py stream --sequence $sequence | python .\examples\consume_frames.py
$symbolic = "contact_full_lifecycle"
python .\dataset.py symbolic --id $symbolic
```

Replace the consumer with your program to receive one chronological JSON object
per frame. It includes PNG base64, the recorded action, time, and source hashes.
`consume_frames.py` reads the actual PNG header and compares PNG-byte hashes; it
does **not** decode pixels, recognize objects, infer events, or look up answers.
Your vision program needs its own RGB/RGBA PNG decoder.

To work from any directory, use the full path to the scripts. `dataset.py` always
locates data next to its own source, not under the current working directory.
All commands are read-only, write results to stdout, and report failures to
stderr with a nonzero exit status. Streaming failures can leave a valid prefix
on stdout; check the reader's exit status before treating a run as complete.

## What's where

| Location | Purpose |
| --- | --- |
| `data\omega_vision\dataset.json` | Inventory, sequence/example IDs, provenance, file hashes |
| `data\omega_vision\recordings` | Raw image/state sequences; `curated` is the other allowed sequence family |
| `data\omega_vision\symbolic\inputs` | Public structured examples |
| `data\omega_vision\evaluation` | Separate expected results/oracles, never default frame inputs |
| `docs\DATA_FORMAT.md` | Manifest, JSONL, integrity checks, shared-storage contract |
| `docs\USING_YOUR_SYSTEM.md` | Feeding your system, event outputs, and honest evaluation |

The catalogue spans movement, contact, attachment and groups; occlusion/fog;
controls; pressure plates/pushing; calibration and counterexamples. See each
test's linked documentation and the manifest for the actual inventory.

The contact example supplies two entities and four successive observations of
whether they touch: false, true, true, false. Your system can deduce when contact
begins, continues, and ends. `motion_stationary_start_continue_end` supplies
observed positions for a similar movement exercise. Neither requires a rule
parser, a particular output syntax, or a native engine/database.

The legacy demo catalogue, private live recordings, native source-code copies,
and old internal UI/memory behavior are not included. Malformed-rule and
parser-security fixtures remain excluded. A well-formed proposed rule is not
supporting evidence: that distinction belongs in the reasoning examples, without
requiring the source system's parser or promotion machinery.
The same applies to uncertainty, circular or duplicated evidence, counterexamples,
context-sensitive rules, and generalization to unseen observations. These are
reasoning cases; parser/security checks and product-specific output or approval
settings are not.
No private recordings, preferences, secrets, caches, or native execution history
are included. Some original cases have insufficient evidence or unimplemented
grading; this export does not claim those cases passed.

Evaluation is an explicit opt-in:

```powershell
python .\dataset.py symbolic --id $symbolic --expected
```

That command returns the expected result **instead of** the public input. Keep it
away from your reasoner's input. Expected JSON describes the example's intended
result; it does not require you to implement the original parser or engine.
This public local dataset is not an OS sandbox: developers can inspect the gold
files, but they must not feed them to a system whose results are being judged.
See `LICENSE` for the source data's licensing.
