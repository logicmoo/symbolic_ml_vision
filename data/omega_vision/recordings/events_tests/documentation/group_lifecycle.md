# Group formation, joint motion and dissolution

This additive family uses eight source-only observations on an opaque 96x64
canvas. Four rectangles have widths 4, 6, 5 and 7 pixels and normally height 10.
Two colors repeat, but same-colored members have distinct geometry. Their colors
and names are not physical-role labels supplied to the recognizer.

## Expected causal sequence

Frames 0-2 show separated members approaching independently. Frame 3 introduces
long shared boundaries, but joined geometry is not yet common observed motion.
Frames 4 and 5 show a common four-pixel translation. The positive case expects
`group_formed` at frame 4. At frame 6 every member is again visible and separated;
the same assembly's `group_dissolved` is expected then, not retroactively.

The current authored grouping rules can merge a simple adjacent two-part shape
into one final G. This four-member layout exercises the existing color-regrouping
and final-G acceptance behavior without substituting manually authored singleton
groups. The actual producer must verify that behavior from the pixels and
registered first-pass dependencies; the intended layout is not an acceptance
certificate. It does not solve arbitrary changing G membership or lineage.

## Controls

- `group_lifecycle_stationary`: joined frames repeat without common nonzero
  motion. Formation and dissolution must not be invented.
- `group_lifecycle_weak_edge`: height 6 yields six shared boundary pixels.
  Keep the existing eight-pixel rule; do not lower it to make this control pass.
- `group_lifecycle_missing_member`: formation is supported before one member
  becomes unobserved. Later composition is unknown, not proved dissolved.

## Evidence and native memory

Only current source pixels, independently verified first-pass measurements and
eligible earlier recording memory may support the result. Criterion acceptance,
complete extraction, final-G evidence and checkpoint ancestry need actual
source-bound provenance. A supplied `independent: true` or a recomputed content
hash is not an independent acceptance producer.

Initial observation supplies no previous assembly or measured motion. Each
`FRAME` receipt advances a recorded observation, not an actuator or force.
`state.json.at_seconds` is the fixture's one-second sampling coordinate, not
the constant publication timestamp. No calibrated physical clock, camera
attestation or absence of entities outside the viewport is implied.

Native frame/STM writes require explicit execution confirmation. Publication of
these input files runs no perception, changes no memory preference, creates no
learned rule and performs no STM-to-LTM transfer. Nowhere remains browser RAM.

## Scoring and limitations

The separate `expected_events.json` is evaluator-only: it contains authored
member masks/positions, expected decisions and the unknown-frame expectations.
It must never become an observer input or a source of accepted G/O identities.
Scoring follows frozen inference and must align actual source hashes, exact
decision frames and measured membership, preserving one assembly identity.
Incidental non-group events may exist; extra group transitions are not allowed.

Missing correspondence, partial extraction, stale artifacts or unsupported
criterion provenance must remain unavailable/unknown. A qualified assembly
event is not proof of a hidden physical bond or its mechanism. These are related
positive/control observations, not independent evidence of generalization.

## Load and preserve

Choose this test under Sanity Tests or load its ordinary Visual Sequences under
`recordings/events_tests`. Its source files are new, never replacements for the
older `group_formed`, `group_dissolved` or causal-history recordings. The saved
definition remains `not_run`; actual execution history is reported separately.

Recreate only missing equal files with
`python -m omega_vision.evaluation.group_lifecycle_recordings`. Generation rejects
conflicting existing content; it does not migrate, merge, rename or delete history.
