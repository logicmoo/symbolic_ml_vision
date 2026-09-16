# Working model

- **Checked through level 2:** Avatar is a 5x5 block (color 12 top two rows, color 9 bottom three), moving one 5-pixel lattice tile per action without rotating. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Traversable route centers are color 3 or specials/goals; color-4 gaps are impassable. Vacated cells restore original contents unless a special was consumed.
- **Checked:** Lower-left HUD is a 3x3 binary code at 2x scale; a gray chamber shows the target at 1x scale. Entering the chamber center with matching pattern **and color** is the apparent objective (pattern matching confirmed; level 3 makes color relevance explicit).
- **Checked:** Black/white cross is a persistent 90-degree clockwise spatial rotator. Every entry turns the HUD pattern one quarter-turn; leaving restores the cross. Level 2 required three entries and completed successfully.
- **Checked:** Hollow color-11 rings are one-use recharge pickups. Entry refills the 42-column budget and consumes the ring; it becomes plain floor after departure. Rings neither teleport nor respawn.
- **Checked:** Budget drain may vary by level: level 1 drained 1 column/action, level 2 drained 2. Rotator entries drain normally in level 2. Always test a new level's rate using a bar-cell expectation on the first useful move.
- **Strong static hypothesis, untested:** A multicolor 3x3 ring around a black center is a color-cycle operator. Its side colors in clockwise order are 14→8→12→9→14; current HUD color 12 and target color 9 are consecutive, so one entry likely cycles 12→9. Stop and inspect on first contact.
- **Static observation, no plan relies on it:** Level 3 has white 5-cell boundary bars beside `(c0,r0)` and above `(c9,r0)`, possibly a paired boundary link. Adding a direct link between those tiles did not shorten the computed required-special route, so do not waste a probe unless later evidence requires it.

# Working memory

- Level 3, fresh at step 92. Lattice centers are `x=11+5c`, `y=7+5r`. Start `(c0,r8)` center `(11,47)`. HUD pattern `111/001/101` in color 12. Goal `(c9,r9)` center `(56,52)` is pattern `101/100/111` in color 9: this is exactly two clockwise spatial turns plus likely one color-cycle step.
- Specials: spatial rotator `(c8,r1)` center `(51,12)`; candidate color-cycle operator `(c4,r8)` center `(31,47)`; recharges `(c5,r2)` center `(36,17)` and `(c2,r5)` center `(21,32)`. Full bar 42. Platform graph has one connected component.
- Assuming level-2 drain (2 columns = 21 actions/refill) and one color-cycle contact, bounded BFS found a 52-action feasible route:
  `UUUUUUUURRRRDDDDDLLRRDDDUUUUUURDDRRRRUUULUDDRDDDDDDD`
  Events: action 19 recharge `(c2,r5)`; 24 color operator; 31 recharge `(c5,r2)`; 41/43 rotator turns 1/2; 52 goal with budget exactly exhausted.
- Next: execute first eight ups to `(c0,r0)`. First action expects two-column drain; mismatch stops immediately if level 3 uses another rate. No new special is touched in this chunk.
- Level 2 is complete. Key correction carried forward: spatial operator rotates clockwise; it is not a mirror. One-use recharge ordering must be solved globally before movement.
