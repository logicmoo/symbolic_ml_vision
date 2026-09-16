# Using your own system

## Choose the input

For vision, pipe `dataset.py stream --sequence ID` into your program. Decode each
PNG with your own image library, retain the supplied action and timestamp, and
update your model after each observation. Frame IDs are evidence references,
not object identities. Assign your own stable entity IDs and maintain identity
across frames; track competing matches when observations are ambiguous.

For symbolic work, read `dataset.py symbolic --id ID`. Use the example's
structured facts, observations, or demonstrations for its declared task.
Start with `contact_full_lifecycle` (successive touching/not-touching
observations) or `motion_stationary_start_continue_end` (observed positions).
These are inputs for event reasoning, not tests of a particular rule parser.
Deduction and induction are distinct: consequences of supplied premises are
not automatically newly learned universal rules. The transport is ordinary
JSON and JSONL; there is no required reasoning language or native database.
You can translate these examples into your system's own representation.
The set also includes reasoning counterexamples: unknown observations, repeated
evidence that is not independent, circular confirmation, and rules challenged by
new observations. Interpret intended results within each example's assumptions,
not as universal physical or learning laws.

The supplied consumer demonstrates reading real images and actions. Its PNG
hash comparison is neither object tracking nor a reasoner, and never consults
evaluation results.

## Report evidence, not just labels

A useful output convention is a typed event or relation with
`{predicate, args}`, your own stable entity IDs in `args`, and these additional
fields:

| Field | Suggested meaning |
| --- | --- |
| `kind` | `event`, `relation`, `hypothesis`, or `prediction` |
| `frames` | Supporting sequence/frame IDs; include both sides of a change |
| `evidence` | Referenced observations, source hashes, and the reasoning used |
| `status` | `observed`, `inferred`, `unknown`, `unsupported`, or `conditional` |
| `uncertainty` | Confidence or competing interpretations, with assumptions |

This is a suggested output shape, not a supplied answer or a mandatory API.
Keep observations, inferred relations, predictions, and hypotheses distinct.
Preserve unknown/unsupported/conditional results rather than forcing a binary
answer. A proposed rule can be well formed without having evidence that it is
true or that a predicted event occurred.

Movement, contact, attachment/group behavior, occlusion/fog, controls,
pressure plates/pushing, and calibration/counterexamples provide different
reasoning challenges. Missing from view is not proof of creation or destruction.
Visual overlap is not alone proof of attachment. A protocol's supplied
directions and trial boundaries are not a supplied controlled-actor identity.
Correlations do not establish universal physical causes; explicitly consider
alternative explanations and counterexamples.

## Keep evaluation separate

Use earlier observations or designated training examples to learn. Freeze the
learned rules, parameters, and entity-handling policy before producing a judged
held-out response. Declare your split and any catalogue/protocol information
you supplied. Do not treat a catalogue partition label alone as proof that a
training/held-out freeze has been enforced.

Feed the reasoner public inputs only. Do not concatenate an entire future
sequence before asking for an earlier-frame prediction, pass catalogue test
summaries as hidden hints, or use expected files to generate the response.
After saving or otherwise fixing the response, an evaluator can explicitly
inspect `data\omega_vision\evaluation` or run `symbolic --id ID --expected`.
That separate step is comparison, not reasoning input.
The expected JSON conveys the example's intent; it does not mandate the source
system's output syntax, parser, or implementation.

This is a public local dataset, not an OS sandbox. Developers can inspect gold;
honest evaluation depends on not feeding it to the reasoner. Some source cases
have insufficient evidence, conditional expectations, or unimplemented grading.
Report those limitations directly. This export contains no native execution
history and does not certify that earlier source-system runs passed.

## Keep extensions small and local

The supplied readers do not save results. If you add persistence for this
project, all Omega Vision state must stay below `data\omega_vision`, with one
shared resolver and regression coverage for containment and stable identity
across workspace switches. New visual sequences belong only in `recordings`
or `curated`. Never overwrite the exported originals, move legacy data
automatically, or persist Nowhere payloads. Follow the complete shared-storage
contract in `DATA_FORMAT.md`.
