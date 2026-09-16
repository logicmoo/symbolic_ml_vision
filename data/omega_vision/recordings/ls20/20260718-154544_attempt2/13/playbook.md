# Working model

- **Checked through level 1:** The controllable avatar is a 5x5 block (color 12 in its top two rows, color 9 in its bottom three). It moves exactly one 5-pixel lattice tile per action and keeps this orientation. ACTION1=up, ACTION3=left, ACTION4=right. ACTION2 is strongly presumed down but has not yet been live-confirmed. A vacated tile restores its original board contents, not necessarily plain floor.
- **Checked:** Traversable routes are the color-3 platform tiles (plus special/goal tile centers); color-4 gaps are impassable. Model movement on tile centers rather than requiring the whole 5x5 destination footprint to be color 3.
- **Checked:** Lower-left HUD displays a 3x3 binary key/code at 2x scale. The target chamber contains the required 3x3 code at 1x scale. Entering the target center while the HUD code matches completes the level (level 1 completed this way at step 13).
- **Checked:** A tiny black/white cross centered on a route tile is a persistent horizontal-reflection operator. Entering it mirrors the HUD code left/right; leaving restores the operator pixels, while the changed HUD state persists. Avoid entering it an extra time, since it is likely reusable/toggling.
- **Checked:** Bottom color-11 strip starts with 42 columns and loses one leftmost column per ordinary move, so it is the move budget. Level-1 reflector contact did not reduce the bar. Three color-8 blocks at the right are HUD, not terrain.
- **Strongly supported, not live-tested:** Two identical hollow color-11 rings are paired teleporters. Their placement provides a shortcut between otherwise distant parts of the level; stepping into one should settle the avatar at the other. Test the first entry explicitly before relying on this.

# Working memory

- Level 2, step 13, fresh board. Avatar center `(31,42)` (tile `(c4,r7)` on centers `x=11+5c`, `y=7+5r`), top-left `(29,40)`. HUD code is `111/001/101`; goal at center `(16,42)` is `111/100/101`, so exactly one horizontal reflection is required.
- Specials: reflector center `(51,47)` = `(c8,r8)`; presumed paired portals at `(16,17)` = `(c1,r2)` and `(41,52)` = `(c6,r9)`. Full budget is 42.
- Plan to approach the upper-left portal efficiently: from `(c4,r7)`, U,R,U,U,U,L,U,U,L,L,D reaches `(c2,r2)`, immediately right of portal `(c1,r2)`. The final D is a useful safe test of presumed ACTION2=down. Then probe one left entry into the ring separately; predict teleport to `(c6,r9)` if the portal model is right.
- If teleport is confirmed: from destination `(c6,r9)`, go R,R,U to enter reflector `(c8,r8)`; then D,L,L to re-enter the lower portal and teleport back to `(c1,r2)`; finally D five times reaches the matching goal `(c1,r7)`. Each special-entry effect must be checked before committing beyond it.
- Ruled out from level 1: target is not activated before code matching; reflector is not consumed or a generic collectible; movement is not one pixel. Current uncertainty is portal behavior and ACTION2 mapping, not the established code/reflection rule.
