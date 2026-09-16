# LS20 - moving figure occludes the background

A single dark-red figure moves across a static yellow scene that also contains a
green object. Across the 14 recorded frames the figure changes position; parts of
the background disappear behind it and reappear once it moves on.

## Memory required

Track the figure as one persistent entity from the initial frame onward. Remember
where background and the green object were before the figure covered them, so that
reappearing pixels are recognized as previously-seen background rather than new
material.

## Measured new evidence

Each frame contributes the figure's new position and which background pixels are
currently visible. New evidence is the *currently* visible scene only; it does not
overwrite what earlier frames established about the static background.

## Required caution

Occlusion is a cross-frame inference and carries uncertainty. Do not treat newly
revealed background as created, missing pixels as destroyed, or a partly hidden
green object as two objects. A single frame does not certify a pass, and this
recording was not graded by the workbench.
