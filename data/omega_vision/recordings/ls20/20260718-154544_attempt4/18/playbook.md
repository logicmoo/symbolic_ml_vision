# Working model

- **Checked through level 2:** Avatar is a 5x5 block (color 12 top two rows, color 9 bottom three), moving one 5-pixel lattice tile per action. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Route centers are color 3 or special/goal centers; color-4 gaps are impassable. Vacated cells restore original contents unless a special was consumed.
- **Checked:** Lower-left HUD is a 3x3 binary code at 2x scale; chamber shows target at 1x scale. Enter its center only after both pattern and color match.
- **Checked:** Black/white cross is a persistent 90-degree clockwise spatial rotator. Every entry turns the HUD pattern one quarter-turn; leaving restores the cross.
- **Checked:** Hollow color-11 rings are one-use recharge pickups. Entry refills the 42-column budget and consumes the ring; it becomes floor after departure. Rings do not teleport or respawn.
- **Checked:** Level 3, like level 2, drains exactly 2 budget columns/action (21 actions/refill); first-move bar expectation and steps 93–100 confirm this.
- **Strong static hypothesis, untested:** Multicolor ring around a black center is a clockwise color-cycle operator. Side colors clockwise are 14→8→12→9→14; current HUD color 12 and target 9 are consecutive, so one entry should recolor the code 12→9. Stop and inspect first contact.
- **Checked (step 100):** A white 5-cell bar bordering a corridor is an automatic conveyor/launcher. Entering top-left tile `(c0,r0)` caused a 17-frame animation sliding the avatar right across the contiguous row to `(c5,r0)` in the same action; only one action/budget charge was used. The analogous white bar above `(c9,r0)` strongly predicts a downward slide to `(c9,r9)`; this remains untested until the planned final goal entry.

# Working memory

- Level 3, step 100. Lattice centers `x=11+5c`, `y=7+5r`. Avatar is at `(c5,r0)` center `(36,7)` after the first conveyor; HUD is pattern `111/001/101`, color 12. Goal `(c9,r9)` is `101/100/111`, color 9: requires two clockwise spatial turns plus likely one color-cycle step. Budget has 26 columns (13 actions).
- Specials: spatial rotator `(c8,r1)`; candidate color operator `(c4,r8)`; unused recharges `(c5,r2)` and `(c2,r5)`. All special states are fresh.
- Search updated with observed forced transition `enter (c0,r0) -> (c5,r0)` and predicted `enter (c9,r0) -> (c9,r9)`. Shortest feasible remaining candidate route is 32 actions:
  `LDDRDDDLDDDUUULLURRRRRRRUUULUDUR`
  Events: remaining action 4 first recharge `(c5,r2)`; 11 color operator; 16 second recharge `(c2,r5)`; 28/30 rotator turns 1/2; 32 predicted conveyor goal entry.
- Next execute `L,D,D,R` to first recharge. Then `D,D,D,L,D,D` stops above color operator, followed by one separate `D` contact probe.
- Level 2 is complete. Key global lessons: solve one-use recharge order before moving; distinguish fixed spatial rotation from color cycling; model conveyor transitions as one action.
