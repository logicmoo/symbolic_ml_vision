# Observed portal association versus ordinary occlusion

Learn a source/arrival association from witnessed remote reappearances, not from line colors or hidden portal wiring.

**Execution status: not run.**

## Local memory and new measured evidence

Remember the independently observed asymmetric actor, its previous full mask/color,
position, input response and acquisition-time velocity; retain visibility uncertainty
through partial/missing intervals. Record visible line-gate geometry independently.
Read only earlier validated observations/STM before processing a new frame.

Main clips first walk behind an ordinary opaque panel: exactly four fully hidden
samples plus partial entry/exit, with emergence fitting remembered speed. Later,
actual RIGHT/LEFT inputs bring the actor into a distinctive line gate. Immediate
trials show entrance/contact followed by remote appearance in the next image;
there is no sampled fully-missing portal frame in that variant. Delayed trials
have four consecutive entirely missing portal frames, followed by remote arrival.
The actor is never drawn walking through the intervening pixels during transit.
Input-free delay samples are sensor ticks, not teleport/arrival commands.

The visible contrast is deliberate: the normal occluder is a solid plain panel;
portal devices are **special-looking striped DOUBLE LINE GATES**, not blank
occluders or generic rings. Each has two colored two-pixel rails, twenty pixels
high with left edges eight pixels apart, and three contrasting diagonal stripe strokes
between the rails. The source and remote gates have independently visible colors.
The decorative-line control uses the SAME double-line/stripe cues but no working
link: the appearance is evidence for a mechanism hypothesis, never proof of wiring.

## Prediction before the next observation

`PortalAssociationMemory` in `omega_vision.evaluation.action_mechanism_recordings`
is a constrained pixel-only fixture baseline, **not a semantic teleporter detector**.
It receives observed PNG bytes and acquisition times, never generator gate links,
destinations, teacher identity or hidden state. Its explicit conventions are a
majority-color uniform background, uniquely colored striped paired 2x20 line rails,
one full 6x8 colored asymmetric actor and a fixed camera/layout. Partial actor
observations remain unavailable to this simple reader. The geometric conventions
are authored baseline limits, not general learned visual concepts.
Legacy 6x16 outline observations remain readable for historical replay, but all
current test-card recordings use the versioned striped double-line devices.

After a witnessed departure near one gate and remote reappearance near another,
the baseline retains source/destination **observation signatures**, arrival offset
and source-image evidence. It does not assume that two visible lines are linked.
The first transit has no learned destination prediction. Before later entry,
`prediction = memory.predict(previous_png, actual_input)` freezes a destination
hypothesis from earlier observed associations, not constant-velocity extrapolation.
It predicts where an eventual transit would emerge, conditional on entry; it does
not assert that the very next sample already contains the destination actor.
Only afterward does `memory.observe(current_png, at_seconds, learn=False)` inspect
the new image to grade a held-out probe without learning its result first.
Main clips include a return trip and third transit, so that prediction can be
tested against a genuinely later occurrence. Missing frames are not observations
of the predicted destination. Keep evidence/decision time and source cutoffs distinct.

## Controls, induction requirements and inference limits

Near-miss trials pass below the apertures with continuous visible travel. Identical
decorative-line controls have no functioning link: visible glyphs alone do not
prove a mechanism. Validation reverses motion and appearance; the final trial
changes layout. New or ambiguous glyphs require their own earlier observations,
not silent cross-recording rule deployment. Mapping proposals need independently
observed support/counterexamples, scoped mechanisms and frozen held-out evaluation.

A remote/too-fast reappearance conflicts with the remembered constant-speed
prediction, but unseen acceleration/fast travel, identity ambiguity and other
hidden causes remain alternatives. Teleportation is a hypothesis, **not a newly
registered or implemented semantic event predicate**. The evaluator retains one
actor identity for scoring; the student cannot copy it or call predicted hidden
positions observed facts. No tracker lifetime/access checks are weakened.

Current clips have `_lines_v2` identities. The previously published outline-v1
clips remain untouched and loadable as history; they were not renamed, migrated
or overwritten. The version change alters visible gate cues, not input schedules,
actor motion, ordinary occlusion timing or portal latency.

## One sequential two-phase recording: first reject the motion model

Load `recordings/events_tests/teleporter_train_delayed_lines_v2`. This existing
44-frame recording follows the SAME observed actor and pre-motion through both
phases; it is not a montage of different examples.

1. **Phase 1, frames 0-13:** frames 0-4 establish +8 px/s from actual PNG positions
   and acquisition times. Partial entry is visible at 5-6, exactly four completely
   hidden samples occur at 7-10, and partial exit at 11-12 precedes full reappearance
   at 13. The full-view displacement from 4 to 13 is +18 px over 2.25 s, exactly
   matching the remembered constant-speed prediction. Ordinary occlusion is
   consistent with this evidence; predicted hidden positions are not observations.
2. **Phase 2, frames 14-23:** continue observing the same appearance and +8 px/s
   motion toward the special striped double-line gate. Freeze that earlier
   velocity and the full observation at 18. Frame 19 records an actual RIGHT;
   frames 19-22 contain no visible actor, and 20-23 are sensor-only observations.
   At frame 23, the full actor reappears remotely: +43 px over 1.25 s, versus
   +10 px predicted. **The FIRST conclusion is constant-speed model mismatch.**
   Before frame 23, absence alone does not establish that mismatch or its cause.
3. **Keep competing explanations:** the object either sped up/moved rapidly
   while unseen, or teleported; **unseen acceleration/fast motion AND teleportation
   remain alternative hypotheses**, not observed causes. Identity uncertainty and
   other hidden causes are additional limits. A jump or decorative lines alone
   MUST NOT be graded as definitive teleportation. Nor is acceleration established
   merely by rejecting constant speed.
4. **Later discrimination, frames 24-43:** a return trip reappears at 33, and a
   third entry at 37 reappears at 41. Earlier witnessed gate associations can now
   support a frozen conditional destination prediction for the later trial.
   Compare no-entry and decorative-line controls and independent changed-layout
   trials; repeated position-specific effects support a portal hypothesis more
   than a generic fast-motion account. They are not permission to backdate that
   knowledge to frame 23 or copy the simulator's wiring as proof.

The separate `teleporter_train_delayed_lines_v2/observer_assessment.json` is a
saved **evaluator-only assessment contract**, not an added runtime event schema or
an executed grader. It names both phase boundaries, the earliest model-mismatch
decision, unresolved alternatives and conclusions that must not be graded as
established. Its teacher cause may be teleporter; that oracle cause, the recording
name, this document and the sidecar are never student inputs. The existing
`evaluation.json`, every PNG/state and the manifest remain unchanged. Workbench
execution status stays `not_run`; no semantic predicate or stage is registered.


## Matched motion-envelope evidence from rendered pixels

The values below use the observed actor mask in the actual PNGs and the
recorded 0.25-second sampling interval, not teacher positions or hidden wiring.
Velocity is established before occlusion. The full-view endpoints include
the elapsed time spent in partial views as well as the four fully hidden
samples. A normal reappearance fits that earlier velocity; the portal
reappearance lies outside its constant-speed displacement envelope.

| Recording | Pre-occlusion horizontal velocity | Normal full-view interval: measured / expected displacement | First portal full-view interval: displacement versus envelope |
|---|---|---|---|
| `teleporter_train_a_lines_v2` | +8 px/s | 4 -> 13: +18 px / 2.25 s = +18 px expected | 18 -> 19: 43 px / 0.25 s > 2 px envelope |
| `teleporter_train_delayed_lines_v2` | +8 px/s | 4 -> 13: +18 px / 2.25 s = +18 px expected | 18 -> 23: 43 px / 1.25 s > 10 px envelope |
| `teleporter_validation_reverse_lines_v2` | -8 px/s | 4 -> 13: -18 px / 2.25 s = -18 px expected | 18 -> 23: 43 px / 1.25 s > 10 px envelope |
| `teleporter_test_layout_lines_v2` | +8 px/s | 4 -> 13: +18 px / 2.25 s = +18 px expected | 20 -> 21: 41 px / 0.25 s > 2 px envelope |

Normal fully hidden frames are 7, 8, 9 and 10 in each main contrast.
The delayed portal trials separately have four fully missing portal samples;
the direct trials have no extra entirely missing portal sample. Line-gate
cues are measured independently from the remembered movement envelope.
Retain ordinary occlusion, unusually fast/unseen accelerated travel, identity
ambiguity and teleportation as distinct explanations. Earlier witnessed
gate-to-gate associations support a conditional destination hypothesis;
one unexplained fast jump or decorative lines alone cannot prove teleportation.


## Recording-local memory and oracle boundary

Earlier Shape/Object observations, temporal/event prefixes and eligible level-1
STM must be frozen before reading this frame. Unknown is not false; current
writes and future frames cannot confirm themselves. Predictions/abductions
remain hypotheses until independent evidence arrives, and later confirmation
cannot backdate knowledge. No memory files, learned rules or approvals are
created by publication. Nowhere remains current-browser RAM only.

Names, catalog entries, this document and `evaluation.json` are evaluator
information, never student facts. The PNG and actual input/acquisition metadata
are the student's observations. Fixture-unit checks are not Workbench detector
or learner passes; UI status remains `not_run`.

## Individual trials and controls

- **train_a**: First pass behind a normal opaque panel for four fully hidden frames at the observed speed; then enter a line gate and appear remotely. Portal transit is immediate between observations, without an extra fully missing sample. Return through the second gate and repeat the first pairing, allowing an earlier observed association to predict the third transit. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.
- **train_delayed**: First pass behind a normal opaque panel for four fully hidden frames at the observed speed; then enter a line gate and appear remotely. Portal transit itself adds four missing frames before each remote arrival. Return through the second gate and repeat the first pairing, allowing an earlier observed association to predict the third transit. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.
- **validation_reverse**: First pass behind a normal opaque panel for four fully hidden frames at the observed speed; then enter a line gate and appear remotely. Portal transit itself adds four missing frames before each remote arrival. Return through the second gate and repeat the first pairing, allowing an earlier observed association to predict the third transit. Travel is reversed and the actor's appearance changes. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.
- **test_layout**: First pass behind a normal opaque panel for four fully hidden frames at the observed speed; then enter a line gate and appear remotely. Portal transit is immediate between observations, without an extra fully missing sample. Return through the second gate and repeat the first pairing, allowing an earlier observed association to predict the third transit. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.
- **control_near_miss**: Move below both visible gate apertures without entering; the actor traverses intervening pixels normally. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.
- **control_decorative**: Cross visually identical but unlinked decorative gates: continuous ordinary travel, not a remote jump. The earlier panel still gives normal occlusion. Both devices have paired colored rails and three contrasting diagonal stripe strokes; decorative controls retain those same visible cues without a working link.

## Loadable recordings

All recordings use ordinary numbered frames starting at `0`, with no root
preview duplicate. Workspace changes expose the same shared assets/identities.

| Logical Visual Sequence ID | Partition | Frames |
|---|---|---|
| `recordings/events_tests/teleporter_train_a_lines_v2` | training | 32 |
| `recordings/events_tests/teleporter_train_delayed_lines_v2` | training | 44 |
| `recordings/events_tests/teleporter_validation_reverse_lines_v2` | validation | 44 |
| `recordings/events_tests/teleporter_test_layout_lines_v2` | test | 34 |
| `recordings/events_tests/teleporter_control_near_miss_lines_v2` | training_control | 41 |
| `recordings/events_tests/teleporter_control_decorative_lines_v2` | test_control | 41 |

## Reproduction and preservation

`python -m omega_vision.evaluation.action_mechanism_recordings` publishes
create-only inputs and this separate `action_mechanism_tests.json` supplement.
It never edits `tests.json`, `visual_memory_tests.json`, earlier documentation
or existing recordings. Differing files are preserved as conflicts. No GET
generates data or changes Save To, Look In, preferences or execution status.
