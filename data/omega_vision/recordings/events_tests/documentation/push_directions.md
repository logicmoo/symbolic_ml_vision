# Push directions

Repeat from left, right, above and below

**Execution status: not run.**

## Controlled trial

Repeat from left, right, above and below

## Earlier local memory for this family

Remember actor/crate identities and shapes, previous positions, contact side,
input direction, displacement vectors, obstacle geometry, empty destination
evidence, and whether motion continued after contact ended. Keep learned
affordances attached to evidence and mechanism scope, not hard-coded sprite IDs.

The principal candidate is:

> Directional action into a contacted movable object predicts displacement of
> that object in the action direction when the destination is observably free.

That is a hypothesis to learn and test. Absence of a detected wall is not proof
of a free destination when that area was occluded or not inspected.

## Measured evidence and candidate to test

Generalize direction relative to contact geometry rather than fixed screen coordinates

This is the evaluator's learning target, not an initial accepted rule.

## Family controls, counterexamples and held-out variation

Held-out direction/orientation, different start positions; not every directional command moves every crate.

- **train_a**: Training example. Approach and push from this clip's physical contact orientation, then retreat; compare input direction with crate displacement. Trace: plate occupancy=not applicable; crate movement=present; door changes=not applicable; wall removal=not applicable.
- **train_b**: Training example. Approach and push from this clip's physical contact orientation, then retreat; compare input direction with crate displacement. Trace: plate occupancy=not applicable; crate movement=present; door changes=not applicable; wall removal=not applicable.
- **control_a**: Training control. Issue directional movements without crate contact; directional input alone does not move the crate. Trace: plate occupancy=not applicable; crate movement=absent; door changes=not applicable; wall removal=not applicable.
- **validation_a**: Held-out validation example. Approach and push from this clip's physical contact orientation, then retreat; compare input direction with crate displacement. Trace: plate occupancy=not applicable; crate movement=present; door changes=not applicable; wall removal=not applicable.
- **test_a**: Frozen final example. Approach and push from this clip's physical contact orientation, then retreat; compare input direction with crate displacement. Trace: plate occupancy=not applicable; crate movement=present; door changes=not applicable; wall removal=not applicable.
- **test_control_a**: Frozen final control. Issue directional movements without crate contact; directional input alone does not move the crate. Trace: plate occupancy=not applicable; crate movement=absent; door changes=not applicable; wall removal=not applicable.
- **train_c**: Training example. Approach and push from this clip's physical contact orientation, then retreat; compare input direction with crate displacement. Trace: plate occupancy=not applicable; crate movement=present; door changes=not applicable; wall removal=not applicable.

## Decision / episode timing and actual simulation

Each world starts with a baseline and WAIT interval. Directional inputs attempt
one 8-pixel cell step; blocked attempts remain in the trace without movement.
CLICK receipts contain screen coordinates; only clicking an existing removable
barrier removes it. No `PUSH_SUCCESS` or inferred outcome is recorded as input.
Plates visibly retain an exposed occupancy border beneath an occupant; door
filled/hollow appearance is observable. Cell-equality occupancy and these
appearances are fixture conventions, not recognizer-supplied semantic facts.
Pause, release and post-release windows remain separate observations.

Training includes right, left and up pushes; validation and final positive clips push down. All four physical contact orientations are represented with changed appearances and waits. No-contact controls still issue directional inputs without moving the crate.

## Per-clip evidence checkpoints

These are evaluator checkpoints to compare against independently measured images,
not accepted events or input facts. Read the predecessor before each listed frame;
confirm a causal candidate only after its full response/hold/release horizon.
Numbers are actual numbered source frames; `none` is not a runtime negative label.

| Clip | Visible occupancy changes | Visible door changes | Crate displacement |
|---|---|---|---|
| train_a | none | none | 3, 5 |
| train_b | none | none | 4, 6 |
| control_a | none | none | none |
| validation_a | none | none | 3, 5 |
| test_a | none | none | 4, 6 |
| test_control_a | none | none | none |
| train_c | none | none | 3, 5 |

## Training, counterexamples and held-out evaluation

`train_a` and `train_b` vary physical orientation/location, appearance, dwell and
input timing. `control_a` is an independent training control, not an adjacent
frame counted as another experiment. Only training clips may influence candidate
generation or thresholds. Freeze candidates before `validation_a`; reserve
`test_a` and `test_control_a` as final held-out inputs, never tuning examples.
Control names describe evaluator intent, not a universal empty-events outcome.
For example a no-press timer control still contains an observed door change.

Retain each candidate's source sequences/pairs, positive support, explicit
counterexamples, measured delay window, uncertainty and mechanism scope. A failed
release prediction must not erase support for an earlier press prediction.
Incomplete response horizons are pending/inconclusive, not negatives. Candidate
gates (two independent positive pairs in two sequences, a held-out pair,
confidence >= 0.8 and zero permitted counterexamples) are minimum requirements,
not demonstrated results of fixture generation or substitutes for controls.

Record actual input attempts independently of their observed outcomes.
Action-effect induction may use zero delay; the current event-transition inducer
starts at one transition. Same-pair plate/door changes need an explicit justified
event-rule contract, not shifted timestamps. Freeze predictions before observing
their effects and score complete observed positive and negative horizons exactly.

The existing-vocabulary baseline is generic measured movement/contact/appearance
or shape change. Typed plate occupancy, open/closed door state, pushing affordance,
signed clearance and mechanism-specific predicates are **planned domain-semantic
tests**, not new registered runtime predicates. This fixture's cell occupancy,
`doorOpen`, named roles and momentum are evaluator conventions only.

Induction proposes, never auto-approves. Explicitly authorized cross-recording
experiments do not merge STM. Unapproved proposals belong to their originating
frame's authorized `memory/induced_rules.metta`; explicit later approval may publish
to that recording's real `memory_level_1_stm`, never automatically to shared LTM.
Publication at order p cannot affect p or earlier frames. Held-out evaluation does
not silently install candidates into another recording. Later local reuse needs
an explicit probe. Abduction, hidden-cause probes and cold-memory replay are still
separate work, not claims made by this dataset. Nowhere remains browser RAM only;
no server payload, persistent abduction or cache is authorized for it.


## Historical read and decision protocol

Local memory means this recording's earlier frame history and level-1 STM in the
one shared Omega store, never a workspace partition or an automatic union with
other recordings. At frame `0`, establish measured baselines only; a still image
does not establish zero velocity or a false prior episode.

For each later frame, freeze the exact predecessor's `shapes_db.metta` and
`objects_db.metta`, validated temporal/event checkpoints and canonical log prefix,
and eligible `memory_level_1_stm` entries published strictly before this frame.
Keep actual G-track and O identity types distinct. Apply sequence, level, source
hash, order and publication cutoffs; reject stale prefixes, gaps and forks.
Only then extract this image and compare independently matched observations.
Current writes, future frames and future approvals cannot confirm themselves.
Missing evidence is **unknown**, not false. Current-frame observations/proposals
are written only after the historical read context is frozen.

Record evidence time separately from decision time. If later motion supplies
confirmation, decide at that later frame and cite the earlier evidence; do not
backdate knowledge. Relation episodes use true/false/unknown: `start` requires
established false-to-true evidence; `continue`/`end` require the same active episode
or an explicitly supported initial-boundary anchor. Unknown cannot end an episode.
Retain ordered directional roles and canonically ordered symmetric subjects.
Use `state.json.at_seconds` / manifest sampling times, not the fixed synthetic
`recorded_at`, for velocity, delay and horizon measurements.

## Oracle separation and inference limits

These are **input tests, not automatically passed tests**. No recognizer or
learner was run to publish them. Case/recording names, `tests.json`, `suite.json`,
this documentation, `expected_events.json`, `evaluation.json`, authored masks,
entity IDs, hidden roles/wiring and expected results are evaluator information,
never recognizer facts. Runtime identities are independently produced and aligned
only for scoring. Predictions and abductive assumptions are not observations.
No empty memory files, detector implementations, rules or approvals are created.

Evidence references must retain source frames and versions. Do not treat shape
similarity as proof of identity, missing detections as signed negative evidence,
or a predicted response as an observed intermediate fact. Do not infer general
force, mass, hidden-state, arbitrary Boolean or recursive-chain reasoning from
these demonstrations. Unsupported representations/detectors remain unavailable.


## Loadable recordings

Select **events_tests** in the ordinary Visual Sequence/recording selector.
Frame `0` is the real baseline; all frames are ordinary numbered image/state contexts.
Workspace switches expose the same stable recording identities.

| Recording (logical Visual Sequence ID) | Partition | Frames |
|---|---|---|
| `recordings/events_tests/push_directions_train_a` | training | 11 |
| `recordings/events_tests/push_directions_train_b` | training | 13 |
| `recordings/events_tests/push_directions_control_a` | training_control | 14 |
| `recordings/events_tests/push_directions_validation_a` | validation | 11 |
| `recordings/events_tests/push_directions_test_a` | test | 13 |
| `recordings/events_tests/push_directions_test_control_a` | test_control | 14 |
| `recordings/events_tests/push_directions_train_c` | training | 11 |

## Source and preservation

This test's saved documentation incorporates its exact row from the approved
`EVENT_TEST_RECORDINGS_LOCAL_MEMORY_PLAN.md` (2026-09-12). Serving this page
reads this file, not that standalone plan. The original 38 recordings,
their images/states/manifests/oracles and `suite.json` are unchanged.
Changed fixtures or documentation require an explicit versioned publication;
the create-only generator refuses to overwrite differing files.
