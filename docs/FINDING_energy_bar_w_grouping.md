# Finding: energy/status bar missing from the W layer

Reported at `…/omega_vision/ui/?test=ls20_occlusion&recording=recordings/ls20/saved_136&frame=3`
("seems to miss the energy bar").

## Root cause — it is detected, but not W-grouped

Recognition (opencv pipeline, 256×256) **does** find the bar's pixels as regions:

| region | color | bounds `[x,y,w,h]` | role |
|---|---|---|---|
| `r16` | `#aaaaa8` grey | `[48,240,208,16]` | bar container |
| `r18` | `#5b5b5b` dark | `[64,244,156,8]` | inner track |
| `r19/r20/r21` | `#80dafd` cyan | `[224/236/248,244,8,8]` | energy segments |

So it is **not a detection miss**. The "W GROUPS" companion renders the **W layer**
(`part_groups` in `prolog/omega_vision/prolog/omega_vision/group_regions.pl`), and none of
these regions form a W group, so nothing is drawn there.

Why no W group:

- W grouping is `partition_part_groups/3` = union-find over `attached/2`, where
  `attached(A,B) :- strong_adj(A,B), crack_gate(A,B)`.
- `crack_gate` (mode `crack`) requires ~180° **crack continuity** across a strong shared edge.
  Its own comment states: *"A chain of tiles that merely touch fails this and stays apart."*
- The cyan segments have ~4px **gaps** (not adjacent to each other); they only touch the grey
  container, and small-tile-on-large-region contacts fail `crack_gate`.
- The bar is not a squarish **cutout** enclosure, so the `glyphy_member` / `solo_cutout` paths
  (which group glyphs *inside a box*) don't apply either.

The engine is deliberately pixel-adjacency based (`% No bounding boxes are ever used`), so it has
no notion of "a horizontal run of aligned tiles = a bar".

## Resolution — implemented (readout/HUD enclosure)

The user chose to treat the bar as a **glyphed box / HUD readout**. Implemented in
`group_regions.pl` as a variant of option 2, wired through the existing glyphy machinery:

- **Pocket enclosure** (`pocket_member/2`, `held_inside/2`): a connected cluster reachable
  from an inner region without crossing the container is *held inside* it when the cluster
  touches the container, contains no background, touches the image border only if the
  container itself is border-clipped, and is smaller than the container. This certifies
  chained fillers (green + track) and the border-clipped last segment, which the extractor's
  single-region `encloses/2` ("only neighbour, not on border") can never certify.
- **Readout enclosure** (new `glyphy_enclosure/1` clause): an elongated (non-`outer_squarish`)
  foreground container holding ≥2 inners whose combined area fills ≥ half the container's
  area. The fill-ratio gate keeps sparse pockets (a playfield holding a few pieces, 17%
  fill) out while the energy bar (86% fill) passes.
- Both feed the existing `glyphy_member`/`child_of` machinery, so the container + track +
  segments become **one W group** and the contents are also emitted as a **child group** —
  differences (segments appearing/disappearing) remain trackable frame to frame.

Validation: saved_136 frame 3 now yields `[r16,r17,r18,r19,r20,r21]` as one W group with a
`[r17..r21]` child group; 12 random recordings re-ran with **zero** W-group diffs; regression
tests added in `recognition_webapp/tests/test_recognition.py`
(`HudReadoutAndInputEvidenceTests`).

## Original fix options (for the record)

1. **Bar-pattern heuristic.** Horizontal run of aligned tiles — rejected (needs bbox geometry,
   departs from the no-bbox design).
2. **Container-hub grouping.** Small regions on a larger elongated container — implemented as
   the pocket/readout enclosure above, with topological (not bbox) evidence.
3. **Relax `crack_gate`.** Rejected — highest regression risk.
