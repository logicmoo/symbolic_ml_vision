# Working model

- **Checked through level 3:** Avatar is a 5x5 block (color 12 top two rows, color 9 bottom three), moving one 5-pixel lattice tile per action. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Lattice route centers are ordinary floor color 3 or special/goal centers; color-4 centers are walls. Vacated cells restore original contents unless a one-use pickup was consumed.
- **Checked:** Lower-left HUD is a 3x3 binary code at 2x scale; the chamber shows the required 3x3 pattern at 1x scale. Enter its center only after both pattern and color match.
- **Checked:** The black/white plus glyph is a persistent 90-degree-clockwise spatial rotator. Every entry turns the HUD pattern one quarter-turn; leaving restores the glyph.
- **Checked:** Hollow color-11 rings are one-use recharge pickups. Entry refills the 42-column budget and consumes the ring; the tile becomes ordinary floor after departure. Levels 2–3 drained 2 columns/action, i.e. 21 actions/refill; level 4 is assumed identical until its first move confirms it.
- **Checked:** The multicolor ring is a persistent clockwise color-cycle operator. Level 3 live-tested 12→9 while preserving pattern; its displayed cycle is 14→8→12→9→14.
- **Checked:** A white 5-cell bar is a conveyor source marker. Entering its adjacent floor tile on the side away from the bar launches the avatar away from the bar across contiguous floor in one charged action. It settles on the final ordinary floor tile before a wall/non-floor special; entering a goal afterward costs another action. Level-3 horizontal and vertical instances both animated for 17 frames.
- **Checked:** Level 3 completed at step 133 only after manually moving from the vertical conveyor endpoint `(c9,r8)` down into the matching goal `(c9,r9)`.

# Working memory

- Level 4 began at step 133. Lattice centers remain `x=11+5c`, `y=7+5r`; avatar starts `(c9,r0)` center `(56,7)`. HUD is color 14, pattern `010/110/011`. Goal `(c0,r0)` is color 9, pattern `111/001/101`.
- Specials: recharges Q1=`(c2,r2)`, Q2=`(c5,r9)`; color-cycle C=`(c5,r5)`; a new all-black four-cell glyph B=`(c3,r5)`. There is no known black/white rotator. B is an **untested pattern-changing operator**: current and target have 5 vs. 6 set bits, so ordinary spatial rotation/reflection cannot suffice.
- Static conveyor inference (not yet live-tested on level 4): source→settled endpoint: `(c7,r3)→(c7,r8)` down, `(c5,r3)→(c9,r3)` right, `(c7,r4)→(c5,r4)` left, `(c6,r4)→(c6,r0)` up, `(c2,r6)→(c2,r8)` down, `(c0,r6)→(c3,r6)` right, `(c3,r7)→(c0,r7)` left, `(c7,r7)→(c5,r7)` left.
- A tile-state BFS with those conveyor transitions gives an exact-budget candidate if B needs one entry and color needs three: start→Q1 9 actions; Q1→third C entry 14; C→Q2 7 (Q2 reached exactly on action 21); Q2→B 6; B→goal 15 (exactly 21). This tight fit strongly suggests the intended order, but B's effect remains assumed and must be probed once before committing past it.
- Current next segment is the fully ordinary route `LLLDDLLLL` to Q1, with no conveyor or new mechanic: from `(c9,r0)` to `(c2,r2)` in 9 actions. After confirmation, candidate continuation to first C entry is `RRRDDDLLUD`; use two `UD` loops for color entries 2/3, then `UULLUDD` to Q2.
