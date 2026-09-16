# Recognition Studio

A standalone local webapp using the **OpenCV and Prolog recognition pipelines**
from Omega Vision. No Workbench, workspaces, accounts, databases, event engine,
graders, or LLM. This folder can be moved and run on its own; it does not import
anything from the parent project.

## Run

Use Python 3.12+, a modern browser, and SWI-Prolog (`swipl` on PATH). Install the
Python image-processing dependencies if they are not already available:

```powershell
python -m pip install -r .\requirements.txt
swipl --version
python -B .\app.py
```

Open **http://127.0.0.1:8765** for recorded demos.
**http://127.0.0.1:8765/shapes** is the separate image-upload and drawing page.
Use `--port 8766` if that port is occupied.
The script also works by full path from another directory. Ctrl+C stops it.

On the demos page, choose a test-based demo and frame; its pipeline starts
automatically as soon as the frame loads. **Run again** manually retries it.
Rapid navigation runs only the latest ready frame after an in-flight request;
superseded results never replace the current frame's analysis. On Shapes,
upload a PNG/JPEG/WebP, draw, or choose a quick
example and click **Recognize shapes**. Choose the pipeline:

| Pipeline | Actual execution |
| --- | --- |
| OpenCV + Prolog (default) | Original OpenCV contours, holes, medials, fill points, and grouping evidence; then SWI-Prolog grouping and turtle programs |
| Prolog shapes + groups | Original pure-Prolog shape finder; then Prolog grouping and turtle programs |
| Geometry only | The earlier lightweight connected-grid recognizer; explicitly selected, never a fallback |

The result shows which engines and versions executed. If OpenCV or SWI-Prolog
fails or is unavailable, the error is displayed; a grid-only result is not
silently substituted. Contours view shows outer edges, holes, medials, and fill
points. **Edit grid** switches back to drawing; painting then uses the edited
grid rather than the original upload for the next run.

The demo frame's **analysis images** show the pipeline's region masks, Prolog
groups, rendered turtle programs, and original Pillow debug overlay. Click a
thumbnail to enlarge it; **Input** returns to the original recorded image.
Outer-edge, inner-edge, and medial toggles control the turtle image. That image
executes the generated Prolog `start`/`turn`/`forward` drawing instructions; it
is not a copy of the contour image. These panels use pipeline output only, never
the authored expected masks.
The original image is kept compact so these panels are easier to see. Loading
and errors appear in the panels rather than hiding them. An empty original or
grouping image, such as Appeared's baseline frame, is identified explicitly.

Task and pipeline selectors sit in compact rows above the frame; there is no
right-hand results pane on Demos. **Parts grouping** shows the actual Prolog W
groups, their areas, and their member regions. Group checkboxes select all their
members; individual part checkboxes allow finer selection. Turtle output draws
only selected parts. With no selected parts, it draws all parts (subject to the
outer/inner/medial layer switches). Selection resets for a new frame.

The **MeTTa / Prolog output editor** beneath the analysis has tabs for this
frame's `.metta`, region, group, turtle, and geometry files. MeTTa records each
measurement and deduction under `(Frame "sequence-id" "frame-id")`; it includes
no other frame or authored expected answers. This is serialization of actual
process output, not an additional MeTTa inference engine. With no recording
context, an image digest identifies the input.

MeTTa/Prolog output and expected interpretation have independent expand/collapse
controls. Draft edits remain in browser memory, bound to the same frame and
generated source; they are never executed or sent to recognition. Download saves
the selected draft, while **Restore generated** restores the process output.
The pipeline's result JSON remains unmodified. Selecting parts filters drawing,
not the complete current-frame process output.

The demos page contains no upload, drawing, or quick-shape controls.
Its single **Task** dropdown lists the recordings from
`data\omega_vision\dataset.json`, grouped by their catalogue categories. Each
option uses the test's name, adding its variant only when multiple recordings
exist. The image caption uses that same name. Previous, Next, and the frame
slider follow numeric manifest order and load the original
PNG, with its hash checked before serving it. The Input view shows those original
pixels, not the grid editor's quantized image. Regions and Contours show the
pipeline's processed coordinates. The URL retains the selected test, recording,
and frame across reloads.

Tests and recordings are linked many-to-many through each test's `recordings`
list. A shared recording appears under every linked test without copying its
images. Each dropdown choice keeps both IDs, so changing frames preserves the
chosen test context. The catalogue exposes all linked `testIds`, rather than
treating the recording's legacy `testId` as exclusive ownership.

The nearby existing `data\omega_vision` export is used automatically. To use
another existing export, launch with
`python -B .\app.py --data-root "C:\path\to\data\omega_vision"`.
Missing demo data produces an explanatory message; the independent Shapes page
remains usable. No data directory is created.

### Expected interpretation

Under the left/input frame, the demos page displays its authored caption,
objects, dimensions, occupied pixel areas, changes from the preceding frame,
and recorded event targets. Test memory, timing, uncertainty, and fixture
insufficiency notes are retained. For example, Deformed preserves 36 occupied
pixels while changing a 6 x 6 square into a 12 x 3 rectangle; this is area, not
a physical-mass measurement.

This is explicitly **human-only evaluator reference**, fetched separately from
the PNG. It never enters an OpenCV or Prolog request. The app does not claim a
test passed merely because an authored expected event is displayed; many tests
require temporal reasoning beyond recognition. A shared recording without an
oracle authored for the selected test link is marked accordingly.

Keyboard drawing: enter the grid editor, focus it, use arrow keys to move, and
Space/Enter to paint.

## Recognition scope

- Four-connected same-color regions, boundaries, enclosed holes, and actual
  cell-to-cell adjacency.
- Classic polyomino names and descriptive identities for unfamiliar geometry.
- Shape matching independent of color, translation, rotation, reflection, and
  exact integer scaling.

This is geometric recognition for flat-color images and pixel art, **not a
semantic photo classifier**. A region is not necessarily a real-world object.
Matching shape IDs do not mean two occurrences are the same persistent entity;
`object-N` identifiers apply only to the current image. No tracking or learning
memory is included.

Uploads retain their original bytes in browser memory and send those bytes to
the native pipeline, not just a browser-quantized grid. OpenCV processes at most
256 pixels on the longest side using the original filtering and area-threshold
policy. Edited grids are rendered at 8 pixels per cell before that pipeline.
Pure Prolog uses at most 32 x 32 cells and 16 colors for bounded runtime; its
original shape finder omits regions smaller than four cells. Prolog infers
background from borders and topology, so the grid background selector is disabled
for the native pipelines. These preprocessing choices and dropped-region counts
are reported, not hidden.

The grid editor is a separate 64 x 64 / 32-color view. In Geometry-only mode,
reconstruction is exact relative to this **analysis grid**. Native contours
are approximate and make no exact-reconstruction claim. Uploaded alpha is not
used to establish physical occlusion. Limits: 10 MB / 4 megapixels per image,
512 kept OpenCV regions, and a 30-second Prolog timeout.

## Files and API

### Original Clause Explorer

The output area now embeds the exact working Workbench `?- Clause Explorer`,
including **Most clauses first**, argument grouping, nested disclosures,
Link to file, Sync tree, and the original CodeMirror source editor.
The source component, `.ts` model and editor dependencies are unchanged copies,
not a JavaScript rewrite. Only standalone mounting, local draft handling and
stylesheet/CSP integration are new. See
[clause_explorer/README.md](clause_explorer/README.md) for the source hashes and
reproducible browser build.

The original tree indexes Prolog output. Native MeTTa/JSON remain available in
the existing output editor; unsupported native-MeTTa conversions are identified
instead of silently reparsing them with the discarded implementation. Explorer
edits are browser-only drafts, never executed or saved to the dataset.

| File | Purpose |
| --- | --- |
| `app.py` | Loopback-only standard-library HTTP server |
| `recognition.py` | Stateless validation and recognition adapter |
| `grid_core.py` | Extracted component, boundary, and topology functions |
| `shape_core.py` | Extracted shape vocabulary, normalization, and naming |
| `static` | Browser UI and image-to-grid import |
| `pipelines.py` | Original-image processing and stdin/stdout Prolog handoff |
| `pixels_to_regions*.py` | Extracted OpenCV pipeline and shared image helpers |
| `shape_finder.pl`, `group_regions.pl`, `turtle_programs.pl` | Actual Prolog recognition rules |
| `pipeline_bridge.pl` | In-memory fact loading and JSON/artifact output |

`POST /omega_vision/api/v1/recognize` accepts a `pipeline` (`opencv`, `prolog`, or `geometry`)
and either `image: {"base64": "..."}` for a native pipeline or
`grid`, `palette`, and `background` as shown below:

```json
{"pipeline":"opencv","grid":[[0,1],[0,1]],"palette":["#000000","#ff0000"],"background":0,"tolerance":24}
```

Omitting `pipeline` retains the original Geometry-only API. Native results
include executed stages, geometry, Prolog groups, source-image hash, and generated
artifact contents. Invalid requests return JSON errors with non-success status.
The optional `frame: {"sequenceId":"...","frameId":"..."}` supplies the current
frame's provenance reference for its MeTTa output; original image bytes retain
their measured source hash.
`GET /omega_vision/api/v1/examples` supplies examples; `/omega_vision/api/v1/capabilities` reports dependencies.
`GET /omega_vision/api/v1/demos` supplies the recorded-test catalogue and frame IDs.
`GET /omega_vision/api/v1/demos/frame?sequence=ID&frame=ID` returns a hash-checked original PNG.
`GET /omega_vision/api/v1/demos/expectations?test=ID&sequence=ID&frame=ID` returns separate,
hash-bound human reference guidance, only for a declared test-recording link.

**No automatic directory or file creation.** Images, grids, and generated outputs
stay in memory; Prolog receives facts through stdin and returns them on stdout.
Generated `regions.pl`, `groups.pl`, `turtles.pl`, and `geometry.json` are available
through the download selector. Only an explicit download saves a file, using the
browser's chosen destination. There are no per-run folders or required output
directories. No user settings or images are written to browser storage.
The server binds only to `127.0.0.1`; it is not a production internet service.
No workspace selection or storage-root setup is required.

## Source and license

`grid_core.py` and `shape_core.py` retain selected functions from
`logicmoo/omega_vision`, respectively
`python/omega_vision/perception/grid_analysis.py` and `symbolic_arc.py`.
Their headers record the source-file SHA-256 hashes. Only the needed pure
recognition definitions were extracted; there is no runtime dependency on the
original checkout. The native recognition sources also have provenance headers.
Standalone adaptations replace Workbench imports, expose OpenCV geometry in
memory instead of debug/output paths, and resolve source fingerprints next to
the code. The Prolog adapter derives border/perimeter/enclosure facts from its
actual region cells and uses the original streaming emitters; file-writing
wrappers are never invoked. The original topology grid and polyomino vocabulary
supply the built-in demonstrations. LGPL-2.1-or-later; see `LICENSE`.

```powershell
python -B -m unittest discover -s tests -v
```

Pipeline integration tests use the existing visual-sequence PNGs, not generated
demo images. The default selection is every frame of `attached`, `occlude`,
`control_actor_calibration_train_a`, and `push_chain_train_a` (39 frames). Each
frame runs through both native pipelines in manifest order; its original hash,
output region consistency, real engine execution, and absence of file writes
are checked. The first sequence is also exercised through HTTP. Evaluation/gold
files are not read, and no event-deduction accuracy is implied.

The default data location is the parent project's `data\omega_vision`. If this
standalone app is moved elsewhere, point tests at an existing export:

```powershell
$env:RECOGNITION_DATA_ROOT = "C:\path\to\data\omega_vision"
python -B -m unittest discover -s tests -v
```

`RECOGNITION_SEQUENCE_IDS` can contain comma-separated manifest sequence IDs, or
`all` for the full export. Missing data is a test error, not a silent demo fallback.
Small geometry and invalid-input unit tests remain independent of the data.
