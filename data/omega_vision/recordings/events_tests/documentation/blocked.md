# Blocked

A wall halts rightward movement; repeated attempts fail until the actor moves another way with the wall still standing.

**Execution status: not run.**

## Local memory required for this test

Prior approach/contact, repeated actual attempted inputs, wall geometry and failed displacement

## Measured new evidence and decision / episode timing

Intended start/continue/end at `2`, `3`, `4`; blocked ends when the attempts change direction and motion resumes while the wall persists in every frame

## Required caution and fixture insufficiency

The recording's state.json now carries the real ARC3 arrow commands (right, right, right, down as ACTION4/ACTION2), so a genuine attempted-input trace exists. The oracle user_input annotations remain separate evaluator vocabulary.

Frame advances now record the gameplay arrow commands in `state.json`
(`incoming_action`), though measured force is still absent. Oracle `user_input`
annotations remain evaluator metadata, never recognizer facts. Warm-up, causal-input and timing limitations above are intentionally
preserved rather than repaired by rewriting the fixture. Group membership,
lineage and appearance/state producer contracts are not supplied by names.

## Induction support and counterexamples

This is one original evaluation example, not an independent train/validation
split or proof of a learned rule. Do not count adjacent frames as independent
trials, auto-promote a detector, or claim held-out accuracy. Preserve unknown
and insufficient-evidence outcomes. Additional versioned warm-ups, controls
and held-out examples are required before making those claims.


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
| `recordings/events_tests/blocked` | event_baseline | 5 |

## Source and preservation

This test's saved documentation incorporates its exact row from the approved
`EVENT_TEST_RECORDINGS_LOCAL_MEMORY_PLAN.md` (2026-09-12). Serving this page
reads this file, not that standalone plan. The original 38 recordings,
their images/states/manifests/oracles and `suite.json` are unchanged.
Changed fixtures or documentation require an explicit versioned publication;
the create-only generator refuses to overwrite differing files.
