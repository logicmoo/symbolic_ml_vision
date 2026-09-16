# Working model

- **Checked through level 2 step 25:** The avatar is a 5x5 block (color 12 in its top two rows, color 9 in its bottom three). It moves exactly one 5-pixel lattice tile per action and keeps this orientation. Controls are ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Vacated tiles restore their original contents.
- **Checked:** Traversable routes are color-3 platform tiles plus special/goal centers; color-4 gaps are impassable. Model movement by the destination center, not by requiring the whole 5x5 footprint to be color 3.
- **Checked:** The lower-left HUD is a 3x3 binary key/code at 2x scale. A target chamber displays the required 3x3 code at 1x scale. Entering its center while the HUD matches completes the level (level 1 completed at step 13).
- **Checked:** A tiny black/white cross is a persistent horizontal-reflection operator. Entering its tile mirrors the HUD code left/right; leaving restores the operator pixels while the changed code persists. Re-entering likely applies another reflection, so avoid accidental extra contact.
- **Checked:** The bottom color-11 strip is a 42-column move budget. Drain rate varies: level 1 used 1 column per ordinary move; level 2 uses 2. Special-entry moves seen so far do not drain it.
- **Checked (level 2 step 25):** A hollow color-11 ring is a recharge station, not a portal. Entering the upper-left ring left the avatar on that tile, left the HUD unchanged, and restored all 42 budget columns (22 missing columns refilled). A second identical ring is another recharge. The ring should be treated as a persistent refill point; verify restoration after leaving, but do not expect teleportation.

# Working memory

- Level 2, step 25. Avatar center `(16,17)` = tile `(c1,r2)` on centers `x=11+5c`, `y=7+5r`; it is standing on the upper-left recharge. HUD is `111/001/101`; goal at `(16,42)` is `111/100/101`, so one horizontal reflection is required. Reflector is `(51,47)`=`(c8,r8)`; second recharge is `(41,52)`=`(c6,r9)`. Budget has just reset to all 42 columns (21 ordinary moves).
- Shortest current route to reflector is 15 actions: R,U,R,R,R,R,R,R,D,D,D,D,D,D,D. The last D enters the reflector and should be free, so this leg costs 14 ordinary moves/28 columns. Next batch takes the first 8 actions to `(c8,r1)`.
- After reflecting, go D,L,L to enter recharge 2 (the first two moves cost 4 columns, ring refills). To return without re-entering the reflector: from recharge 2 `(c6,r9)`, use R,U,U,R,U,U,U,U,U,U,L,L,L,L,L,L,D,L to re-enter recharge 1 `(c1,r2)` (17 ordinary moves then refill), then D five times to the goal (four ordinary moves and free goal entry). Recompute/verify this route in Python before issuing it.
- Ruled out: rings do not teleport or alter the HUD; ACTION2 uncertainty is resolved (it moves down). Established code/reflection rules remain valid.
