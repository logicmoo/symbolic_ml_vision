# Learn a control-to-actor association before testing its response

Each 96x64 recording has separate earlier calibration intervals followed by a
frozen association and a later action-response test. The observer receives no
supplied actor ID, color role, pose, or expected response. Such values belong
only to the evaluator. The source protocol supplies control semantics and the
experiment boundary, not the actor association.

## Calibration and held-out confirmation

Frame 0 is the baseline. Training intervals end at frames 1-4 and contain RIGHT,
WAIT, LEFT and UP. The proposed responder must be selected before the held-out
calibration intervals ending at frames 5-6 (DOWN and WAIT). The autonomous
distractor moves on no-input samples and does not follow opposite directions.
These observations may discriminate a conditional responder; a unique group
or a matching color alone is not evidence of control ownership.

Freeze the association at frame 6. Test responses from frame 7 onward must never
train, select or retroactively validate their own actor. Later source-frame
visual correspondence may carry the already-bound identity forward; ambiguity
or loss of the source G must withhold the binding rather than reassign it.
No cross-recording temporal order or same-instance identity is assumed.

## Test phase and controls

The positive case has four successful RIGHT inputs at frames 7-10, followed by
three RIGHT attempts at frames 11-13 without displacement against a visible
barrier. Expected qualified blocked onset is frame 13, not first contact.
The six- or seven-pixel contact does not lower the existing eight-pixel
composition threshold or force manually accepted G singletons.

The validation case changes colors and actor/distractor dimensions, so a fixed
color/size rule cannot stand in for calibration. The ambiguous case has two
calibration responders and must remain unresolved. The no-input control uses
WAIT for the final three samples and must not count them as failed actuators.
The missing-actor control must not assign the calibrated control to a remaining
visible group after the source actor is lost.

## Evidence and safety boundary

`control_protocol.json` records the given cardinal control vectors and fixed
train/validation/test boundary. Its control-scope ID is a channel, not a visual
actor. `state.json` records actual inputs and acquisition coordinates only.
`evaluation.json` contains authored actor identities/geometry and expectations,
strictly for grading after native inference has been frozen.

Use verified source pixels, actual FIRST_PASS final-G acceptance, earlier
calibration receipts and causal checkpoint ancestry. Typed action receipts must
name the current source G and the actual input interval; a later displacement
cannot supply the direction or choose the actor. No-input, missing observation
and ambiguous correspondence remain distinct.

This is bounded, conditional calibration under the recorded control protocol,
not proof of universal physical causality or automatic general rule approval.
Native recording-memory writes require explicit execution. No LTM publication
or global preference change is implied; Nowhere remains browser RAM.

## Load and preserve

These are ordinary recordings under `recordings/events_tests`, indexed by
`control_actor_calibration_tests.json`. Definition status is `not_run`; runtime
history is separate. Generate additively with
`python -m omega_vision.evaluation.control_actor_calibration_recordings`.
Existing files, histories and recordings are never replaced or migrated.
