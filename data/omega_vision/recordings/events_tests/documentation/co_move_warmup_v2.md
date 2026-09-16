# co move warmup v2

Separated objects move together then their velocities diverge. Includes a measured stationary warm-up interval.

**Execution status: not run.** This is a versioned test input, not a passed detector result.

## Earlier local memory and measured evidence

Freeze the previous Shape/Object observations, temporal/event checkpoint and eligible recording-level STM before processing the next image. Keep source hashes and actual frame order. Initial observation is not measured stationary motion. Group identity and membership need independent evidence, not a remembered oracle label.

- Co-motion does not imply physical attachment or shared object identity.
- Frame 0 -> 1 establishes stationary motion; do not infer it from frame 0 alone.

## Decision-frame expectations

- Frame 2: `{'predicate': 'start', 'args': [{'predicate': 'co_move', 'args': ['actor', 'other']}]}` (decision uses only frames 0 through 2).
- Frame 3: `{'predicate': 'continue', 'args': [{'predicate': 'co_move', 'args': ['actor', 'other']}]}` (decision uses only frames 0 through 3).
- Frame 4: `{'predicate': 'end', 'args': [{'predicate': 'co_move', 'args': ['actor', 'other']}]}` (decision uses only frames 0 through 4).

Support at a later frame does not rewrite earlier knowledge. Current observations can support a deduction with references to prior contact/path/shape evidence. If correspondence or a required baseline is unresolved, retain unknown/inconclusive rather than manufacturing the expected event.

## Controls, scoring and induction

Compare the original shorter v1 recording as an insufficient-history control. Stationary comparisons do not seed positive recurrence; a confirmed event must be independently scored before it can support rule evaluation. Candidate-generated labels cannot confirm that same candidate. Held-out trials never tune thresholds; promotion remains explicit and later local reuse obeys publication cutoffs.

The separate expected_events.json is evaluator-only. Descriptions, case IDs, authored masks, entity names and membership annotations are not recognizer inputs. FRAME is observation advance, not an action or force. Actual action-bearing blocked examples are available in stairs_gravity; a no-input stationary frame is not a failed RIGHT.

## Loadable recording

`recordings/events_tests/co_move_warmup_v2` contains 5 numbered frames from 0.

All assets are shared across workspaces. Native memory belongs to the real frame and recording-level STM under data/omega_vision; Nowhere remains browser RAM only. No memory payloads or learned rules are published merely by generating this example.

## Preservation

This v2 recording does not replace, rename, reindex or overwrite the original v1 recording or its expected outcomes. Recreate additively with `python -m omega_vision.evaluation.causal_event_recordings`.
