# Fog of war: movement and clicking over the same frames

These two 35-frame recordings contain **byte-identical PNG observations in the
same order**. Their input receipts differ: one replays a directional movement
script; the other clicks the next aperture position. No existing recording is changed.

## Scripted controls, not free play

Frame 0 is an observation with no input. Each subsequent movement frame records
one actual RIGHT, DOWN or LEFT push along the serpentine waypoint grid. Interior
waypoints are eight pixels apart; the last viewport-edge spacing is clipped to
seven pixels. The click variant records CLICK with explicit image x/y coordinates
for the same resulting aperture position. These are declared fixture control
conventions, not hidden answers exposed to the recognizer.

Step advances one recorded input and then reveals its resulting observation.
An explicitly requested full run follows that same script. Opening the view or
adding controls does not start either. Previous/next-frame inspection must be
distinguished from issuing a free directional action: going backward in recorded
history is not a simulated LEFT press. Show the actual recorded input beside the frame.

## Local memory and the current observation

Read the prior recording-local native checkpoint before processing each current
RGBA image. Alpha 255 is observed, including genuinely observed black; alpha 0
is unknown. Retain earlier revealed pixels when the fog moves away. Never fill
unobserved pixels from the evaluator's full scene or future frames. Causal source
hashes, frame order and native frame/STM references accompany the result.

The same pixels cannot establish whether movement or a click caused them.
That distinction comes from the explicit recorded input, not image-only deduction.
Image-only reconstruction should agree between variants at every prefix; an
action-aware learner may distinguish the input interfaces but cannot claim two
independent visual confirmations from these duplicate image traces. Both evaluator
files retain the same visual fingerprint and mark `independentVisualTrial: false`.

## Scoring and limits

Compare reconstructed known pixels with evaluator truth only after inference has
been frozen. Knowledge must never exceed the union of visibility observed so far.
Completion requires all 48x32 pixels known; missing visibility is not no-change.
This contrast is not held-out evidence of generalization, a learned game, or a
new environment control API. Native Run/Step remains a separate explicit action;
fixture publication itself has execution status **not run**.

No data is copied into workspace-owned stores. STM-to-LTM promotion requires a
separate explicit call. Nowhere remains browser RAM only.

## Recorded input schedule

| Result frame | Movement variant input | Clicking variant input |
|---|---|---|
| 0 | baseline | baseline |
| 1 | RIGHT | CLICK (8, 0) |
| 2 | RIGHT | CLICK (16, 0) |
| 3 | RIGHT | CLICK (24, 0) |
| 4 | RIGHT | CLICK (32, 0) |
| 5 | RIGHT | CLICK (40, 0) |
| 6 | RIGHT | CLICK (47, 0) |
| 7 | DOWN | CLICK (47, 8) |
| 8 | LEFT | CLICK (40, 8) |
| 9 | LEFT | CLICK (32, 8) |
| 10 | LEFT | CLICK (24, 8) |
| 11 | LEFT | CLICK (16, 8) |
| 12 | LEFT | CLICK (8, 8) |
| 13 | LEFT | CLICK (0, 8) |
| 14 | DOWN | CLICK (0, 16) |
| 15 | RIGHT | CLICK (8, 16) |
| 16 | RIGHT | CLICK (16, 16) |
| 17 | RIGHT | CLICK (24, 16) |
| 18 | RIGHT | CLICK (32, 16) |
| 19 | RIGHT | CLICK (40, 16) |
| 20 | RIGHT | CLICK (47, 16) |
| 21 | DOWN | CLICK (47, 24) |
| 22 | LEFT | CLICK (40, 24) |
| 23 | LEFT | CLICK (32, 24) |
| 24 | LEFT | CLICK (24, 24) |
| 25 | LEFT | CLICK (16, 24) |
| 26 | LEFT | CLICK (8, 24) |
| 27 | LEFT | CLICK (0, 24) |
| 28 | DOWN | CLICK (0, 31) |
| 29 | RIGHT | CLICK (8, 31) |
| 30 | RIGHT | CLICK (16, 31) |
| 31 | RIGHT | CLICK (24, 31) |
| 32 | RIGHT | CLICK (32, 31) |
| 33 | RIGHT | CLICK (40, 31) |
| 34 | RIGHT | CLICK (47, 31) |

## Loadable recordings

- `recordings/events_tests/spotlight_action_modes_move`: arrow movement, 35 frames.
- `recordings/events_tests/spotlight_action_modes_click`: position clicking, 35 frames.

Both derive their visible frames from `spotlight_scene_train_a`. The original
movement-pointer recording and its history remain untouched. Recreate additively
with `python -m omega_vision.evaluation.fog_action_recordings`.
