# Working model

- **Checked (step 0):** 64x64 board; only ACTION1–ACTION4 are available; run requires 7 levels. Gameplay area is a color-3 platform laid out on a 5-pixel lattice. A 5x5 two-color object (color 12 on its upper 2 rows, color 9 on its lower 3) starts at top-left (34,45), center (36,47).
- **Strongly supported geometry, controls still assumed:** The 5x5 object is the avatar and moves 5 cells per cardinal input; likely conventional mapping ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. This has not yet been live-tested.
- **Checked geometry:** Main platform is eight 5x5 tiles wide (x=14..53) and five high (y=25..49), with holes at tile positions (col 3, rows 1..3), (col 0,row 3), (col 2,row 3), and parts outside the platform. Start is (col 4,row 4). A tiny black/white object lies in tile (col 1,row 1). A narrow upper path is centered at x=36 and leads to a blue pattern around center (36,12).
- **Plausible but unconfirmed objective:** collect/activate the black-white object, then reach the upper blue marker. A blue glyph in the lower-left HUD is closely related but not identical to the upper marker, so there may be a code/pattern state mechanic. Do not assume mere key-and-exit completion until movement/collection evidence confirms it.
- **Checked HUD facts:** bottom bar is color 11 across x=13..54 at y=61..62, with three color-8 2x2 segments to its right. Treat it as budget/status, not terrain.

# Working memory

- Level 1, fresh attempt, step 0. Suspected avatar at (34,45), facing/colored with 12 above 9.
- Cheapest useful probe on a shortest candidate route to the black-white object: ACTION3, predicted conventional left move by 5 to top-left (29,45), restoring old footprint to color 3. If confirmed, continue left to x=24, then up three times and left once to overlap the object tile.
- Ruled out from static board only: nothing yet; action meanings and exact objective remain untested.
