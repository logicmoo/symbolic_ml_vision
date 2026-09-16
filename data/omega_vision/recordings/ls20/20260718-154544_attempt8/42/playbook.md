# Working model

- **Checked:** The avatar is a 5x5 block (color 12 top two rows, color 9 bottom three) moving one 5-pixel lattice tile per action without rotating. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Vacated tiles restore original contents unless a special was consumed.
- **Checked:** Traversable routes are color-3 platform tiles plus special/goal centers; color-4 gaps are impassable. Movement validity follows destination centers.
- **Checked:** The lower-left HUD is a 3x3 binary code at 2x scale; the chamber shows the target code at 1x scale. Entering its center with a matching code completes the level.
- **Checked by steps 6 and 46:** The black/white cross is a persistent **90-degree clockwise rotator**, not a mirror. Level 1's input happened to make one clockwise rotation look like a horizontal reflection. In level 2, `111/001/101` rotated to `101/001/111`, proving the rotation rule. Each entry applies one quarter-turn; leave and re-enter to apply additional turns.
- **Checked:** The bottom color-11 strip is a 42-column move budget. Level 1 drains 1 column/action; level 2 drains 2, giving 21 actions between refills. Rotator entry drained normally in level 2 (step 46), so do not assume special moves are free.
- **Checked:** A hollow color-11 ring is a one-use recharge pickup. Entry leaves the avatar there, leaves the code unchanged, refills all 42 columns, and consumes the ring; after departure it becomes plain color-3 floor. Rings do not teleport or respawn.

# Working memory

- Level 2 failed exploration state at step 46: avatar is on rotator `(c8,r8)`, code has one clockwise turn, both recharges are consumed, and only 18 actions remain. Python graph search proves at least 24 actions are required from this state to add the two remaining turns and reach the goal, so this attempt is unsalvageable without an undo (none available). Issue exactly one RESET now; do not reset again on the fresh board.
- Correct requirement: initial code needs three clockwise rotations to equal the goal. A bounded BFS over `(tile, rotation mod 4, consumed-recharge mask, remaining moves)` found a shortest feasible fresh solution of 45 actions:
  `URUUUUURRDRDDDDDDDLLRURUDUUUUUUULLLLLLDLDDDDD`
- Indexed checkpoints in that solution: action 17 enters rotator (turn 1, 4 moves remain); action 20 enters lower recharge `(c6,r9)` and refills; action 23 enters rotator (turn 2); action 25 re-enters rotator (turn 3); action 40 enters upper recharge `(c1,r2)` and refills; action 45 enters goal `(c1,r7)`.
- After RESET, batch the verified sequence in 6–8 action chunks with center-cell expectations. Do not consume the upper recharge early. First chunk from fresh start `(c4,r7)` is `U,R,U,U,U,U,U,R`, ending `(c6,r1)`.
- Ruled out: cross is not a reflector; one rotation is insufficient. The previous route was impossible because it consumed the upper recharge before discovering that three rotator contacts were required.
