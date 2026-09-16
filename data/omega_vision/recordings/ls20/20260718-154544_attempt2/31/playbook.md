# Working model

- **Checked through level 2 step 33:** The avatar is a 5x5 block (color 12 in its top two rows, color 9 in its bottom three). It moves one 5-pixel lattice tile per action without rotating. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Vacated tiles restore their original contents unless a special was consumed.
- **Checked:** Traversable routes are color-3 platform tiles plus special/goal centers; color-4 gaps are impassable. Movement validity follows the destination center rather than the whole 5x5 footprint.
- **Checked:** The lower-left HUD is a 3x3 binary key/code at 2x scale. A target chamber displays the required 3x3 code at 1x scale. Entering its center while the HUD matches completes the level.
- **Checked:** A tiny black/white cross is a persistent horizontal reflector. Entering it mirrors the HUD code left/right; leaving restores the cross while the changed code persists. Avoid extra entries because another reflection would undo the first.
- **Checked:** The bottom color-11 strip is a 42-column move budget. Level 1 drains 1 column per ordinary move; level 2 drains 2. Reflector/goal contact did not drain it.
- **Checked (steps 25–26):** A hollow color-11 ring is a one-use recharge pickup, not a portal or persistent station. Entry leaves the avatar on that tile, leaves the code unchanged, restores all 42 budget columns, and consumes the ring: after departure its tile restores entirely to color-3 floor. Plan routes so each recharge is used only once.

# Working memory

- Level 2, step 33. Avatar center `(51,12)`=`(c8,r1)` on centers `x=11+5c`, `y=7+5r`. HUD `111/001/101`; goal `(16,42)` is `111/100/101`, so one reflection is still required. Upper-left recharge has been consumed. Reflector `(51,47)`=`(c8,r8)` is below; unused recharge 2 is `(41,52)`=`(c6,r9)`. Budget has 26 columns = 13 ordinary moves.
- Do **not** enter the reflector yet. Revised feasible route, computed on the tile graph: from current go `D,D,D,D,D,D,L,D,D,L` to unused recharge 2 while avoiding reflector (first 9 moves consume 18 columns; final ring entry refills). Then `R,R,U` enters reflector (2 ordinary moves, leaving 38 columns after reflection). Finally exact-budget shortest route to goal is `U,U,U,U,U,U,U,L,L,L,L,L,L,D,D,L,D,D,D,D`; its first 19 moves consume all 38 columns and its last move enters the goal for free.
- Next batch: six downs to `(c8,r7)`, immediately above the reflector. Then turn left rather than down and take `L,D,D,L` to recharge 2.
- Ruled out: rings neither teleport nor persist; the consumed upper ring cannot be reused. The earlier route reflector→recharge2→recharge1→goal was invalid because it assumed recharge1 would respawn.
