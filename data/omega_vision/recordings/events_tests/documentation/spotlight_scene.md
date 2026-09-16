# Reconstruct a static scene through a moving spotlight

Retain previously observed pixels while a circular sensor aperture moves across a fixed camera.

## Task and newly measured evidence

The underlying 48x32 scene and camera are static. A circular spotlight samples
different regions through actual MOVE_POINTER x/y receipts. Each PNG is RGBA:
alpha 255 marks observed pixels inside the aperture, **including observed black**;
alpha 0 marks unknown pixels outside it. Outside RGB channels are also zero, so
hidden scene colors are not smuggled beneath transparency. Only the evaluator
contains the full scene; there is no extra root preview or hidden-scene PNG.

## Executable observation-only memory

`omega_vision.evaluation.visual_memory_baselines.SpotlightMemory` accepts only
individual current RGBA PNG bytes. `memory.observe(current_png)` unions visible
pixels with earlier known pixels; `memory.image()` returns a copy of accumulated
RGBA memory. Black with alpha 255 is known; black with alpha 0 remains unknown.
Previously seen pixels persist after the spotlight moves, repeat observations
are idempotent, and no lookahead or hidden-scene read is possible through this API.
The accumulator checks the entire observation for contradictory known pixels
before accepting any new pixels. Different dimensions, nonbinary visibility or
conflicting static-scene evidence require an error, not a silent memory rewrite.

## Completion, controls and held-out scene

Complete scans use at most 35 frames and eventually reveal every pixel. Compare
the accumulated RGB image to evaluator ground truth only when the union-known
mask has full coverage. Earlier and partial scans must preserve unknown cells.
Partial/revisit controls never complete the scene; repeated visits cannot create
knowledge of unseen pixels. Validation changes both scene and scan ordering;
the final test changes the scene again. Start a fresh accumulator per scene.

Reconstruction is exact registered-pixel accumulation, not object completion,
SLAM, camera-motion compensation or general temporal recognition. Moving the
aperture does not mean objects appeared, disappeared, were created or destroyed.
The Workbench's stronger object/event-memory interpretation remains untested;
this fixture-unit accumulator does not claim that pipeline is implemented.


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

- **train_a**: Complete circular-aperture scan of a static scene; accumulated observed pixels eventually cover the entire fixed camera.
- **train_b**: Complete circular-aperture scan of a static scene; accumulated observed pixels eventually cover the entire fixed camera.
- **validation_a**: Complete circular-aperture scan of a static scene; accumulated observed pixels eventually cover the entire fixed camera.
- **test_a**: Complete circular-aperture scan of a static scene; accumulated observed pixels eventually cover the entire fixed camera.
- **control_partial**: Partial scan with repeated visits: previously seen pixels persist, but unobserved scene cells must remain unknown.
- **control_revisit**: Partial scan with repeated visits: previously seen pixels persist, but unobserved scene cells must remain unknown.

## Loadable recordings

Choose events_tests in the ordinary recording selector. Numbered frame `0`
is the baseline; no extra root `image` preview is part of the sequence.
Workspace switches expose the same shared recordings and stable identities.

| Logical Visual Sequence ID | Partition | Frames |
|---|---|---|
| `recordings/events_tests/spotlight_scene_train_a` | training | 35 |
| `recordings/events_tests/spotlight_scene_train_b` | training | 35 |
| `recordings/events_tests/spotlight_scene_validation_a` | validation | 35 |
| `recordings/events_tests/spotlight_scene_test_a` | test | 35 |
| `recordings/events_tests/spotlight_scene_control_partial` | training_control | 7 |
| `recordings/events_tests/spotlight_scene_control_revisit` | test_control | 7 |

## Reproduction and preservation

`python -m omega_vision.evaluation.visual_memory_recordings` is create-only,
idempotent and refuses differing existing files. It publishes this independent
four-test index as `visual_memory_tests.json`, not by editing `tests.json`.
All prior recordings and saved documentation are preserved. No GET generates
fixtures or changes Save To, Look In, memory, preferences or execution status.
