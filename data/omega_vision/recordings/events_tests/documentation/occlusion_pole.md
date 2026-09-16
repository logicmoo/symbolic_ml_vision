# Four fully hidden frames behind a slender pole

Retain an asymmetric actor's identity and motion hypothesis across exactly four completely hidden samples.

## Geometry and actual visible evidence

An asymmetric 6x8 L-shaped actor moves two pixels per sampled WAIT behind a
12-pixel-wide opaque vertical pole, all in a fixed 96x64 view. Forward actor
left edges are 18,20,...,48; the pole covers x=30 through 41. Full hiding occurs
only at left edges 30,32,34,36: frames **6,7,8,9**, four consecutive samples with
exactly zero actor-colored pixels. Frames 4,5 and 10,11 are partial entry/exit,
not part of the four fully hidden frames. Earlier fully visible observations
establish velocity from real acquisition times; later full views show emergence.

## Memory, prediction and decision timing

Freeze the previous visible mask, color/asymmetry, stable track alternatives,
measured approach velocity and pole silhouette before each new frame. During
frames 6-9 retain the last observation and a projected-position hypothesis.
Projected hidden masks/positions are **not observed facts**. Partial emergence
supplies new evidence; independently match it using appearance and the motion
window rather than creating a new identity by default or copying the teacher ID.
Occlusion is a supported explanation only with compatible visible occluder
geometry and later evidence; preserve the distinction between event evidence
time and later decision time. Do not close an episode because visibility is unknown.

## Controls, held-out variation and limits

Training changes color, vertical position and asymmetric appearance; validation
reverses travel and changes appearance. The absence control removes the actor
for the same four samples with **no visible occluder**. That control is unexplained
missing/reappearance evidence, not automatically pole occlusion or destruction.
Teacher identity remains one entity across the gap for scoring only.

No tracker or occlusion detector is implemented by this fixture. Existing tracker
lifetime and typed identity/depth capabilities may not support the full gap;
report unsupported/unknown behavior honestly. Do not weaken lifetime/access
checks, copy oracle poses into memory, or advertise an automatic identity pass.


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
| `recordings/events_tests/occlusion_pole_train_a` | training | 16 |
| `recordings/events_tests/occlusion_pole_train_b` | training | 16 |
| `recordings/events_tests/occlusion_pole_validation_a` | validation | 16 |
| `recordings/events_tests/occlusion_pole_control_absence` | test_control | 16 |

## Reproduction and preservation

`python -m omega_vision.evaluation.visual_memory_recordings` is create-only,
idempotent and refuses differing existing files. It publishes this independent
four-test index as `visual_memory_tests.json`, not by editing `tests.json`.
All prior recordings and saved documentation are preserved. No GET generates
fixtures or changes Save To, Look In, memory, preferences or execution status.
