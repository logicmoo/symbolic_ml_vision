# Reconstruct a static scene through an arrow-commanded spotlight

The circular sensor aperture is moved by DISCRETE ARROW COMMANDS, not pointer
coordinates: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right, one 8 px step
per command. Each frame's `incoming_action` in state.json is the only movement
evidence; `action_data` is empty. Everything outside the aperture is occluded by
darkness (RGB and alpha zero) - darkness hides, it never erases.

## Task

Correlate the arrow command received between frames with the aperture's visible
motion, and accumulate previously observed pixels while the spotlight moves.
Observed black inside the aperture (alpha 255) is knowledge; black with alpha 0
remains unknown. Previously seen pixels persist after the spotlight moves on.

## Recordings

* `spotlight_arrows_train_a` - a serpentine scan (23 arrow commands) that
  eventually reveals every pixel of the static 48x32 scene.
* `spotlight_arrows_control_partial` - a short partial walk with a revisit;
  unobserved scene cells must remain unknown and repeats add no new knowledge.

Only the evaluator carries the full scene. Reconstruction is exact
registered-pixel accumulation through the moving hole; moving the aperture does
not mean objects appeared or disappeared.
