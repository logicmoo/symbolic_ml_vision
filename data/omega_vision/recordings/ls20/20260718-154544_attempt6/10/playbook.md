# Working model

- **Checked through level 4:** Avatar is a 5x5 block (color 12 top two rows, color 9 bottom three), moving one 5-pixel lattice tile per action. Controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right. Lattice centers are `x=11+5c, y=7+5r`; ordinary floor is color 3, walls have color-4 centers, and special/goal centers are enterable. Vacated cells restore their contents unless a one-use pickup was consumed.
- **Checked:** Lower-left HUD is a 3x3 binary code at 2x scale; the chamber shows the required 3x3 pattern at 1x scale. Enter its center only after both pattern and color match.
- **Checked:** The black/white plus glyph persistently rotates the HUD pattern 90 degrees clockwise on every entry.
- **Checked:** Hollow color-11 rings are one-use budget refills; after departure they become ordinary floor. Levels 2–3 drained 2 of 42 columns/action (21 actions/refill), while level 4 drained 1/action (42 actions/refill), so rate is level-dependent and must be checked each level.
- **Checked:** The multicolor ring persistently cycles HUD color clockwise while preserving pattern. Live transitions are 14→8→12→9; displayed 9→14 closes the cycle but is not yet live-tested.
- **Checked:** A white 5-cell bar marks a conveyor source. Entering the adjacent floor tile away from the bar launches across contiguous floor in one charged action, settling on the final ordinary floor tile before a wall/non-floor special. Entering a goal afterward is separate.
- **Checked for one input at level-4 step 167:** The all-black four-cell glyph transformed pattern `010/110/011` to `111/001/101`, preserving color. Its general rule is unknown; do not generalize beyond observed transitions.
- **Checked:** Level 4 completed at step 182. Its shortest executed solution used Q1 only, three color-ring entries, one black-glyph entry, and left two of 42 timer actions; Q2 was unnecessary.

# Working memory

- Level 5 began at step 182. Avatar starts `(c8,r7)` center `(51,42)`. HUD is color 12, pattern A=`010/110/011`. Goal `(c9,r0)` is color 8, pattern G=`101/110/011`.
- Specials: recharges Q1=`(c7,r0)`, Q2=`(c0,r1)`, Q3=`(c1,r8)`; color C=`(c4,r4)`; black glyph B=`(c2,r1)`; clockwise rotator R=`(c1,r6)`.
- Pattern hypothesis (**strong but untested**): level 4 established B(A)=T=`111/001/101`; level-5 goal G is consistent with the next iterate B(T)=G under a life-like/local pattern rule, suggesting exactly two B entries and no rotation. No route beyond the second B probe should rely on this until live-tested.
- Static conveyor inference: `(c5,r0)→(c5,r4)` down, `(c5,r3)→(c7,r3)` right, `(c2,r4)→(c0,r4)` left, `(c8,r5)→(c8,r7)` down, `(c6,r4)→(c6,r0)` up, `(c9,r5)→(c7,r5)` left, `(c7,r7)→(c9,r7)` right, `(c9,r9)→(c9,r1)` up. None are yet live-tested on level 5, though the general rule is checked.
- BFS assuming 2-column drain, three C entries, and two B entries finds a 38-action optimum using Q2 only: `ULUULLLRUULLLLULLLRRDRRRUULRLRUDDDDDDU`; events C1@7, B1@16, Q2@18 refill, B2@20 probe, C2@27, C3@29, goal@38. If drain is 1/action, a different 34-action no-refill route is shorter.
- The first four moves `ULUU` are common to both timer-rate optima and end at `(c7,r4)`. Execute that common prefix now, then inspect actual level-5 drain before choosing the divergent fifth move.
