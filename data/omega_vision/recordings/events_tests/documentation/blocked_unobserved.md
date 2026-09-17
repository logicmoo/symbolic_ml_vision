# Blocked (unobserved inputs)

Blocked with no observed inputs: the actor sits at the wall an extra frame, so a
failed attempt must be abduced before movement resumes in another direction.

**Execution status: not run.**

## Local memory required for this test

Prior approach/contact, wall geometry, an unexplained stationary dwell at the
wall, and the later redirected movement.

## Measured new evidence and decision / episode timing

Intended start/continue/end at `2`, `3`, `4`; no `user_input` is authored in any
frame. The evidence for an attempt is the dwell itself: an actor that arrived
under its own motion, stops against the wall, and stays an extra frame with no
visible cause, then moves off in a different direction. The wall persists in
every frame.

## Required caution and fixture insufficiency

The abduced attempt is a hypothesis, never an observation. Without input traces
the recognizer may only propose `blocked` abductively with reduced confidence;
stationary contact alone must not auto-promote to a causal claim. Preserve
unknown and insufficient-evidence outcomes.

## Induction support and counterexamples

This is one authored example, not an independent train/validation split or
proof of a learned rule. Do not count adjacent frames as independent trials,
auto-promote a detector, or claim held-out accuracy.

## Oracle separation and inference limits

These are **input tests, not automatically passed tests**. Case/recording
names, `tests.json`, `suite.json`, this documentation, `expected_events.json`,
authored masks and entity IDs are evaluator information, never recognizer
facts. Predictions and abductive assumptions are not observations.

## Loadable recordings

Select **events_tests** in the ordinary Visual Sequence/recording selector.
Frame `0` is the real baseline; all frames are ordinary numbered image/state contexts.

| Recording (logical Visual Sequence ID) | Partition | Frames |
|---|---|---|
| `recordings/events_tests/blocked_unobserved` | event_baseline | 5 |
