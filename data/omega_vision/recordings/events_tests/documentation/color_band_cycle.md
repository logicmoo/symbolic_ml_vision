# Click-driven color cycle from a visible ordered band

Predict target color from the visible swatch order and observed click effects, including last-to-first wrap.

## Task and newly measured evidence

A single solid colored target sits to the left of a visible vertical color band.
The drawn arrow orders the band top to bottom. A CLICK anywhere on a target pixel,
including its edges/corners, advances one swatch; the last wraps to the first.
Background, band and one-pixel-outside clicks do nothing. The fixture teacher uses
a palette to render the world, but the baseline never receives it.

## Executable observation-only baseline

`omega_vision.evaluation.visual_memory_baselines.ColorBandMemory` extracts exact
RGB connected components from the PNG itself. Its declared layout conventions
are a majority-color uniform background, one large solid rectangular target,
and at least two smaller equal solid square swatches in one vertical column to
the right, with unique colors and one exact target-color match. It does not
hard-code RGB order, target coordinates, a palette length or an oracle index.
This is a constrained raster-layout baseline, not general object recognition.

Call `prediction = memory.predict(previous_png, "CLICK", {"x": x, "y": y})`
before acquiring/reading the next image, then
`assessment = memory.observe(prediction, current_png)`. The prediction is immutable.
The first on-target click is unknown until a real earlier before/click/after
transition establishes the modular step. Later predictions use that retained
observed step plus the currently visible band/current target color. Observed
successor evidence retains source image hashes and click coordinates; replaying
the same evidence does not multiply support. Conflicting observed steps remove
the single-step prediction rather than silently select a convenient answer.
No-op off-target prediction uses measured hit geometry, not an oracle hit flag.

## Controls, held-out trials and inference limits

Training changes palette order and target placement. Validation and final clips
use previously unseen colors/orderings. Boundary controls alternate true edge
hits with adjacent misses; no-target controls click swatches/background only.
Keep step evidence from training frozen for the held-out predictions: do not
learn the held-out outcome before scoring it. Use
`memory.observe(prediction, current_png, learn=False)` throughout held-out clips
to keep their outcomes out of training evidence. Last-to-first wrap is approved
fixture behavior, not an invented non-wrapping terminal state.

The baseline does not infer arbitrary UI semantics, antialiasing, multiple
targets, nonuniform backgrounds, hidden palettes or arbitrary band orientation.
Unknown first-click predictions are reported separately, not counted as passes.
No new registered event predicate or runtime induction stage is introduced.


## Local memory and evidence boundary

Read only the eligible earlier history of this recording before processing the
current image: prior Shape/Object observations, validated temporal/event prefix
and explicitly eligible recording-level STM. Frame `0` is the actual baseline,
not proof of prior stationary motion or nonexistence. Freeze earlier evidence and
predictions before observing the next image. Preserve stable observed identities,
alternative correspondences and the distinction between observed and projected
geometry. Use `state.json.at_seconds`, not the fixed synthetic fixture timestamp.

Predictions are not current observations; a later confirmation cannot backdate
knowledge. Unknown evidence is not false and does not close a relation episode.
Any memory entry or approved rule needs source-frame/version and publication
cutoffs. The standalone baselines here use explicit in-process memory only; they
do not read or write Workbench memory, create predicates, promote rules, merge
recording STM, or relax tracker lifetime/access checks. Nowhere stays browser RAM
only. Cross-recording baseline trials are explicitly selected unit experiments,
not automatic cross-recording memory inheritance or deployment.

## Oracle separation and execution status

**Execution status: not run.** These are input fixtures, not Workbench detector or
learner passes. Executable fixture-unit baselines are specifically identified
below; their checks do not set this UI status or demonstrate full semantic-stage
integration. Names, this documentation, catalog metadata and `evaluation.json`
are evaluator information, never recognizer facts. Palette indices, next colors,
hidden full scenes, masks, roles, intended identity and hidden object positions
stay in evaluator JSON. Frame states contain only ordinary acquisition metadata
and actual input receipts. Independent observations must confirm effects.


## Individual clip intent

- **train_a**: Varied target-interior/edge clicks advance the visible ordered band, including last-to-first wrap; outside/band clicks do nothing.
- **train_b**: Varied target-interior/edge clicks advance the visible ordered band, including last-to-first wrap; outside/band clicks do nothing.
- **validation_a**: Varied target-interior/edge clicks advance the visible ordered band, including last-to-first wrap; outside/band clicks do nothing.
- **test_a**: Varied target-interior/edge clicks advance the visible ordered band, including last-to-first wrap; outside/band clicks do nothing.
- **control_a**: Only off-target and swatch clicks: the target keeps its initial color through the full clip.
- **control_boundary**: Alternate one-pixel-outside misses with inclusive target-edge/corner hits, then complete a wrapping cycle.

## Loadable recordings

Choose events_tests in the ordinary recording selector. Numbered frame `0`
is the baseline; no extra root `image` preview is part of the sequence.
Workspace switches expose the same shared recordings and stable identities.

| Logical Visual Sequence ID | Partition | Frames |
|---|---|---|
| `recordings/events_tests/color_band_cycle_train_a` | training | 12 |
| `recordings/events_tests/color_band_cycle_train_b` | training | 12 |
| `recordings/events_tests/color_band_cycle_validation_a` | validation | 11 |
| `recordings/events_tests/color_band_cycle_test_a` | test | 10 |
| `recordings/events_tests/color_band_cycle_control_a` | training_control | 10 |
| `recordings/events_tests/color_band_cycle_control_boundary` | test_control | 15 |

## Reproduction and preservation

`python -m omega_vision.evaluation.visual_memory_recordings` is create-only,
idempotent and refuses differing existing files. It publishes this independent
four-test index as `visual_memory_tests.json`, not by editing `tests.json`.
All prior recordings and saved documentation are preserved. No GET generates
fixtures or changes Save To, Look In, memory, preferences or execution status.
