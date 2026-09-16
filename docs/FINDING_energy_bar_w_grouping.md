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

## Fix options (need review — each changes the shared W engine for ALL recordings)

1. **Bar-pattern heuristic (recommended, additive).** Add a narrowly-gated rule that groups a
   horizontal run of ≥3 small foreground regions of similar height sharing a baseline (optionally
   near a frame edge) into one W group. Additive (adds W groups, leaves existing ones), but needs
   bounding-box/alignment geometry, which departs from the current no-bbox design.
2. **Container-hub grouping.** Treat small foreground regions sitting **on** a larger elongated
   foreground region as attached to it (a non-cutout analogue of `glyphy_member`). Groups the bar
   via the grey container as hub; broader blast radius than option 1.
3. **Relax `crack_gate` for small tiles.** Simplest code change, **highest** regression risk —
   would group many unrelated touching tiles across every recording.

## Why not applied autonomously

There is no golden-output test for W-group *contents* (tests assert source metadata only), and the
change affects grouping across all 793 recordings, which cannot be visually validated without the
reviewer. Recommend option 1, gated tightly, with before/after spot-checks on a sample of
recordings once approved.
