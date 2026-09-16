# Four fully hidden frames behind a large opaque object

Separate observed approach/emergence from predicted hidden motion through a larger occluder's footprint.

## Geometry and actual visible evidence

An asymmetric 6x8 L-shaped actor moves six pixels per WAIT behind a substantially
larger 30x30 opaque object in a fixed 96x64 scene. Forward actor left edges are
12,18,...,78; the occluder covers x=33 through 62. Frame **3** (left edge 30) is
partial entry; frames **4,5,6,7** (36,42,48,54) are exactly four completely hidden
samples; frame **8** (left edge 60) is partial exit. All fully hidden frames have
zero actor-colored pixels. Several earlier full observations establish approach
velocity; later full views provide reappearance evidence.

## Earlier memory and new observations

Remember the last independently observed asymmetric shape/color and identity
alternatives, velocity with acquisition-time references, occluder geometry and
the active visibility hypothesis. Advance only a predicted hidden position
through frames 4-7; do not present it as a measured position or learned fact.
Emerging partial/full pixels must independently confirm correspondence before
retaining a specific identity. Event evidence time can precede decision time;
later confirmation cannot rewrite the earlier state as if the future were known.

## Controls, held-out variation and limits

Training changes appearance and vertical location; validation reverses motion.
The no-occluder absence control has the same four zero-visible samples without
an object covering the predicted path: disappearance alone cannot prove occlusion.
The evaluator's stable actor identity and hidden poses are never recognizer input.

This documents intended memory behavior, not an implemented general tracker or
successful Workbench semantic recognition. Lifetime, depth, amodal shape and
reidentification support may be unavailable. Keep ambiguities/unknown outcomes;
do not relax tracker/access checks or automatically create/promote rules. Large
opaque coverage is not a reason to claim physical destruction and recreation.


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

- **train_a**: Observed approach, partial entry, exactly four consecutive fully hidden samples, partial exit and reappearance.
- **train_b**: Observed approach, partial entry, exactly four consecutive fully hidden samples, partial exit and reappearance.
- **validation_a**: Observed approach, partial entry, exactly four consecutive fully hidden samples, partial exit and reappearance while traveling in the reversed direction with changed appearance.
- **control_absence**: The asymmetric actor vanishes for four samples without an intervening visible occluder, then returns; disappearance alone does not prove occlusion.

## Loadable recordings

Choose events_tests in the ordinary recording selector. Numbered frame `0`
is the baseline; no extra root `image` preview is part of the sequence.
Workspace switches expose the same shared recordings and stable identities.

| Logical Visual Sequence ID | Partition | Frames |
|---|---|---|
| `recordings/events_tests/occlusion_large_object_train_a` | training | 12 |
| `recordings/events_tests/occlusion_large_object_train_b` | training | 12 |
| `recordings/events_tests/occlusion_large_object_validation_a` | validation | 12 |
| `recordings/events_tests/occlusion_large_object_control_absence` | test_control | 12 |

## Reproduction and preservation

`python -m omega_vision.evaluation.visual_memory_recordings` is create-only,
idempotent and refuses differing existing files. It publishes this independent
four-test index as `visual_memory_tests.json`, not by editing `tests.json`.
All prior recordings and saved documentation are preserved. No GET generates
fixtures or changes Save To, Look In, memory, preferences or execution status.
