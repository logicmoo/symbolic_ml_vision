# Working model

- **Checked through level 2 and current level 3:** Avatar is a 5x5 block (color 12 top two rows, color 9 bottom three), moving one 5-pixel lattice tile per action. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Route centers are color 3 or special/goal centers; color-4 gaps are impassable. Vacated cells restore original contents unless a one-use pickup was consumed.
- **Checked:** Lower-left HUD is a 3x3 binary code at 2x scale; chamber shows the required 3x3 pattern at 1x scale. Enter its center only after both pattern and color match.
- **Checked:** Black/white cross is a persistent 90-degree clockwise spatial rotator. Every entry turns the HUD pattern one quarter-turn; leaving restores the cross.
- **Checked:** Hollow color-11 rings are one-use recharge pickups. Entry refills the 42-column budget and consumes the ring; it becomes floor after departure. Rings do not teleport or respawn.
- **Checked:** Levels 2 and 3 drain exactly 2 budget columns/action (21 actions/refill).
- **Checked at level-3 step 111:** Multicolor ring around a black center is a persistent clockwise color-cycle operator. Entry recolored all set HUD bits 12→9 while preserving the pattern. Its side-color cycle is visually 14→8→12→9→14; only 12→9 has been live-tested.
- **Checked at step 100:** A white 5-cell bar bordering a corridor is an automatic conveyor/launcher. Entering level-3 top-left tile `(c0,r0)` caused a 17-frame slide right across the contiguous row to `(c5,r0)` in one action and charged one timer step.
- **Strong static hypothesis, not yet live-tested:** The analogous white bar above `(c9,r0)` launches down the contiguous right corridor to goal `(c9,r9)` in one action. The shortest route relies on this only for the final move, so `expect_levels` will test it cheaply.

# Working memory

- Level 3, after step 111. Avatar is on the color operator `(c4,r8)`, center `(31,47)`. HUD is now color 9 and still pattern `111/001/101`, confirming the planned one-step recolor. Goal `(c9,r9)` is color 9, pattern `101/100/111`, requiring exactly two clockwise spatial turns.
- Lattice centers are `x=11+5c`, `y=7+5r`. First recharge `(c5,r2)` is consumed; second recharge `(c2,r5)` is fresh. Current budget safely reaches it in 5 actions; after refill the goal is 16 actions away (within 21).
- Computed remaining shortest candidate: `UUULLURRRRRRRUUULUDUR` (21 actions). It reaches second recharge on action 5, enters the cross `(c8,r1)` on actions 17 and 19 (clockwise turns 1/2), exits north to `(c8,r0)`, then enters `(c9,r0)` for the predicted downward launch and completion on action 21.
- Ruled out/current correction: the cross is at `(c8,r1)`, not `(c8,r0)`; the two turns occur on `L` and later `D` in the suffix `LUDUR`.
- Level 2 is complete. Key global lessons: solve one-use recharge order before moving; distinguish fixed spatial rotation from color cycling; model conveyors as one-action forced transitions.
