# Right-arrow stair descent with gravity and blocked-right evidence

Traverse two/three-cell stair treads using RIGHT only; distinguish commanded horizontal motion, falling and final obstruction.

**Execution status: not run.**

## Actual input and physics contract

Main clips issue only **RIGHT** arrows. A right attempt moves up to one four-pixel
cell horizontally, checking solid geometry at every pixel. Gravity is a separate
update: lack of support increases downward velocity by one pixel per sensor tick,
capped at four; each vertical pixel step checks collisions and landing resets
velocity. No DOWN command, diagonal command or fixed click-count y-trajectory exists.
Frames with `incoming_action: null` after baseline are sensor-only ticks: no extra
command was issued. They reveal intermediate fall/landing observations.

Visible stairs drop after treads of two or three cells. Training varies tread
patterns; held-out clips vary patterns and one/two-cell drops. Support, risers and
the final right-hand barrier are visible in the PNG, but the full floor map and
simulator velocity live only in evaluator JSON. Main traversals end at the visible
barrier, settle, and receive at least three further RIGHT attempts with no movement.
That evidence must not be confused with a no-input pause.

## Earlier local memory, new evidence and decision timing

Retain the independently tracked actor, earlier positions/times, previous observed
support/contact and recorded input direction. Compare each current image with that
frozen history. Measure horizontal displacement after RIGHT separately from
vertical displacement while unsupported. Successive acquired samples, including
sensor-only ticks, are needed to assess fall speed/acceleration. A smaller final
displacement may be a landing/collision, not a new downward input or changed gravity.
Keep predicted support/trajectory separate from actual pixels.

For blocked-right, compare earlier successful RIGHT response, current visible
barrier/clearance and repeated current RIGHT receipts with failed displacement.
An unchanged image with no command does not supply the same causal evidence.
Signed observed support/free destination matters: offscreen or unobserved regions
remain unknown, not an invented floor or proven empty space. The fixtures keep
their actual floor inside the observed viewport; they do not demonstrate reasoning
about unseen ground. Use `at_seconds`, not the fixed fixture timestamp.

## Controls and induction limits

The flat-floor control issues RIGHT but never falls. The pause/fall control first
issues one RIGHT off a ledge, then no further commands: x stays fixed while gravity
continues the fall and landing. These counterexamples distinguish horizontal
command effects from command-driven downward movement. Different tread/drop
patterns rule out an absolute click-count or prescribed-y explanation.

Potential action/support/fall/landing and blocked-right rules need measured
producer contracts, causal cutoffs, independent supporting sequences, explicit
counterexamples and frozen held-out tests. The simulator is executable; no general
gravity detector, learned force/mass model, semantic induction stage or automatic
stable-identity pass is implemented here. Do not create new registered predicates,
relax tracker/access checks or promote fixture oracles into accepted rules.


## Exact terminal blocked-right evidence

The table names actual numbered frames, not oracle event labels. The stop/support
baseline and all three later failed-attempt PNGs are byte-identical; each of the
three later states nevertheless records a real RIGHT receipt. Actor displacement
is zero in BOTH x and y. These are not missing-input samples.

| Recording | Last successful RIGHT interval | Visible stop/support baseline | Further RIGHT attempts, zero displacement | Three-attempt decision boundary |
|---|---|---|---|---|
| `stairs_gravity_train_a` | 36 -> 37 | 37 | 38, 39, 40 | 40 (10.00 s) |
| `stairs_gravity_train_b` | 36 -> 37 | 39 | 40, 41, 42 | 42 (10.50 s) |
| `stairs_gravity_validation_pattern` | 39 -> 40 | 40 | 41, 42, 43 | 43 (10.75 s) |
| `stairs_gravity_test_drops` | 38 -> 39 | 39 | 40, 41, 42 | 42 (10.50 s) |
| `stairs_gravity_control_flat` | 20 -> 21 | 21 | 22, 23, 24 | 24 (6.00 s) |

### Frame-by-frame local-memory reasoning

1. Before the first failed-attempt frame, freeze the validated history through
   the stop/support baseline. Retain independently observed actor identity/pose,
   the latest earlier successful RIGHT response, and its measured
   horizontal displacement. Do not initialize a movement affordance from a label.
   In train_b, RIGHT succeeds at frame 37; frames 38 and 39 are sensor-only
   settling observations before failed RIGHT attempts 40, 41 and 42.
2. At each listed attempt, read the actual RIGHT receipt and independently
   measure zero displacement against the remembered actor observation. Verify
   signed visible barrier pixels immediately to the actor's right and ground
   support directly below its footprint. Missing/offscreen evidence is unknown;
   neither a hidden floor map nor an evaluator support flag is detector input.
3. The first failed attempt supplies a blocked-right candidate, not evidence
   that the command was absent. Keep the same actor, direction and obstruction
   context through the second and third failed attempts. Under this test's
   three-attempt criterion, the final listed frame is the earliest fully
   supported decision boundary. Cite the earlier attempt frames; do not backdate
   knowledge or manufacture a runtime-confirmed predicate from this plan.
4. The obstruction remains at clip end. No release or end-of-blocking episode
   is observed; the end of a recording is not an episode-end event.

### Stationary no-input control is different evidence

`stairs_gravity_control_pause_fall`: frame 0 -> 1 contains the only RIGHT.
Sensor-only frames 2, 3 and 4 continue the fall and land; frames 5, 6, 7, 8
and 9 are stationary with null incoming actions. Their identical pixels do
**not** support blocked-right: there are no repeated RIGHT attempts and no
observed adjacent right-hand barrier at that actor location. Stationary alone
is not blocked, and a pause must not be relabeled as a failed command.

These are exact fixture/evidence requirements, not an integrated general
Workbench blocked detector. Execution status stays `not_run`; states/actions
contain no `blocked=true` answer.


## Recording-local memory and oracle boundary

Earlier Shape/Object observations, temporal/event prefixes and eligible level-1
STM must be frozen before reading this frame. Unknown is not false; current
writes and future frames cannot confirm themselves. Predictions/abductions
remain hypotheses until independent evidence arrives, and later confirmation
cannot backdate knowledge. No memory files, learned rules or approvals are
created by publication. Nowhere remains current-browser RAM only.

Names, catalog entries, this document and `evaluation.json` are evaluator
information, never student facts. The PNG and actual input/acquisition metadata
are the student's observations. Fixture-unit checks are not Workbench detector
or learner passes; UI status remains `not_run`.

## Individual trials and controls

- **train_a**: Only RIGHT inputs traverse varied two/three-cell treads; gravity and collision determine descent during input and sensor-only frames. Three final RIGHT attempts remain blocked by the visible right-hand barrier.
- **train_b**: Only RIGHT inputs traverse varied two/three-cell treads; gravity and collision determine descent during input and sensor-only frames. Three final RIGHT attempts remain blocked by the visible right-hand barrier.
- **validation_pattern**: Only RIGHT inputs traverse varied two/three-cell treads; gravity and collision determine descent during input and sensor-only frames. Three final RIGHT attempts remain blocked by the visible right-hand barrier.
- **test_drops**: Only RIGHT inputs traverse varied two/three-cell treads; gravity and collision determine descent during input and sensor-only frames. Three final RIGHT attempts remain blocked by the visible right-hand barrier.
- **control_flat**: Only RIGHT attempts move along a flat supported floor; no vertical motion occurs. Three final RIGHT attempts meet the visible barrier.
- **control_pause_fall**: One RIGHT leaves a ledge, then no commands are issued: sensor-only frames show continued accelerating fall and landing at unchanged x.

## Loadable recordings

All recordings use ordinary numbered frames starting at `0`, with no root
preview duplicate. Workspace changes expose the same shared assets/identities.

| Logical Visual Sequence ID | Partition | Frames |
|---|---|---|
| `recordings/events_tests/stairs_gravity_train_a` | training | 41 |
| `recordings/events_tests/stairs_gravity_train_b` | training | 43 |
| `recordings/events_tests/stairs_gravity_validation_pattern` | validation | 44 |
| `recordings/events_tests/stairs_gravity_test_drops` | test | 43 |
| `recordings/events_tests/stairs_gravity_control_flat` | training_control | 25 |
| `recordings/events_tests/stairs_gravity_control_pause_fall` | test_control | 10 |

## Reproduction and preservation

`python -m omega_vision.evaluation.action_mechanism_recordings` publishes
create-only inputs and this separate `action_mechanism_tests.json` supplement.
It never edits `tests.json`, `visual_memory_tests.json`, earlier documentation
or existing recordings. Differing files are preserved as conflicts. No GET
generates data or changes Save To, Look In, preferences or execution status.
