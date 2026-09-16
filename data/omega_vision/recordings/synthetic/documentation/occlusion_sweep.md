# Synthetic gradual occlusion (occlusion_sweep)

A hand-built demo, not a recording of live play. A red bar sweeps leftward across a
stationary green box (with a stationary blue marker nearby), covering the green box a
little more each frame, holding it fully hidden, then sliding away to reveal it again.

Frames: visible -> partly occluded -> mostly occluded -> fully occluded (2 frames)
-> partly revealed -> fully revealed.

## Required caution

The green box is only ever *hidden* and *shown again*. Missing pixels are not proof it
was destroyed, and its reappearance is not proof it was created. Match its identity
across the gap rather than treating the covered frames as a new object.
