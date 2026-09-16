# Data format

All dataset paths are relative to `data\omega_vision`. The source export is
described by `dataset.json` (`schemaVersion: 1`). JSON paths use `/`, even on
Windows; command-line filesystem paths can use `\`.

## Manifest

| Field | Meaning |
| --- | --- |
| `name`, `source` | Dataset name; source repository, revision, and snapshot note |
| `inventory` | Counts of tests, sequences, frames, and symbolic examples |
| `tests` | `id`, `title`, `group`, `summary`, documentation path, sequence IDs in `recordings` |
| `sequences` | `id`, `testId`, `partition`, `label`, `frameCount`, `directory`, `frames`, optional-value protocol/assessment paths, evaluation path |
| `symbolicExamples` | `id`, `track`, `task`, `description`, public `input`, evaluation `expected`, `sourceTests` |
| `files` | Relative file path to SHA-256 digest; excludes the manifest itself |

Extra catalogue metadata is allowed. A frame entry has `frameId` (string),
`order` (nonnegative integer), and `image`/`state` paths. Numeric `order`, not
lexical filenames or directory enumeration, defines chronology. Sequence
directories must be descendants of `recordings` or `curated`.

Test-to-recording links are many-to-many: each test's `recordings` list names its
sequences, and a sequence can be listed by several tests. `testIds` in reader
and webapp catalogue responses is derived from those links. A sequence's legacy
`testId` records its original source test; it does not impose exclusive ownership.
Shared sequences and frames are counted once in the inventory.

`controlProtocol` and `observerAssessment` may be null. Protocols describe
supplied directions and trial boundaries; they do not identify the controlled
actor for the learner. A sequence's `evaluation` points into the separate
evaluation area. Test documentation, labels, protocols, and assessment metadata
are not automatically appended to frame streams.

The source PNG and state files are preserved byte-for-byte. A state's public
fields are `incoming_action`, `action_data`, and `at_seconds`; preserve their
values, including nulls, rather than inventing missing actions or timestamps.

## Frame JSONL

`python dataset.py stream --sequence ID` emits one object per observed frame:

| Field | Content |
| --- | --- |
| `sequence_id`, `frame_id`, `order` | Dataset evidence identity and numeric observation order |
| `image.mime_type`, `image.base64` | `image/png` and the original PNG bytes encoded as base64 |
| `incoming_action`, `action_data`, `at_seconds` | Only these fields from the current frame's recorded state |
| `source.image`, `source.state` | Paths of the two current source files |
| `source.sha256.image`, `source.sha256.state` | Hashes checked against those original files |

There is no oracle, gold annotation, teacher payload, expected object identity,
or array of future frames in a stream record. The reader does not load
evaluation files to stream images. It hashes each image/state before emitting
that frame. It forwards no additional state fields.

The example consumer only base64-decodes the PNG bytes, reads IHDR dimensions
and RGB/RGBA color mode, and compares the complete PNG hash with the previous
frame in the same sequence. A changed PNG encoding is not necessarily a changed
pixel, and neither establishes an event. The first frame reports
`png_bytes_changed: null` because no prior image was observed.

## Symbolic inputs and integrity

`symbolic --id ID` emits the parsed contents of the example's public input,
without wrapping in catalogue or evaluation metadata. `--expected` instead
reads the separately stored expected output. Tracks are `symbolic_deduction`
and `symbolic_induction`; task-specific JSON structure stays as exported.
Expected JSON describes intended results, not a mandatory parser/engine
contract. Use your own representation, entity IDs, and reasoning language.

Examples cover movement, relation histories, visibility, blocked actions, rules,
and learning from observations. The `task` field describes each example.
`sourceTests` identifies original source test functions, not entries in the
visual test catalogue. These are provenance citations, not required executable
tests or local paths. Source-file provenance is reference material, not
reasoner input.
`documentation/event-vocabulary.json` describes the predicate vocabulary.
The legacy demo catalogue, native source-code copies, and malformed-rule/parser
security fixtures are deliberately excluded. Reasoning distinctions, such as a
well-formed hypothesis not being supporting evidence, do not require implementing
the source system's parser or promotion machinery.

`verify` checks every listed file hash, catalogue references, test/sequence
links, frame IDs/orders and counts, and all four inventory
totals. Source-test citations remain provenance strings.
Hashes detect inconsistency with this local manifest, not independent
authenticity: someone who can edit the data can also edit the manifest.

The shared reader resolver rejects absolute, drive-qualified, backslash,
parent-traversal, and nonportable paths. Resolved references must stay inside
the data root, including through symlinks and Windows junctions. The root itself
cannot be redirected. Missing data and broken references are errors, not empty
successful results. The reader writes no files or bytecode caches.

## Shared-storage contract

Here, repository means this explicitly requested independent new project, not a
workspace partition of the source project. The contract below is retained
verbatim. This starter is read-only; it does not implement an Inspector, a data
writer, or workspace management. The corresponding downstream requirements are
not fulfilled merely by documenting them here.

```text
1. ONE shared physical Omega Vision data root: <repository>\data\omega_vision. All our data, memory, rules, events, executions, preferences, cache, logs and locks must be descendants. No sibling repo\data\recordings/runtime/knowledge/etc and no workspace-root Omega data writes.
2. ALL Visual Sequences are under ONLY omega_vision\recordings or omega_vision\curated. Retain curated spelling. importables is staging, not a sequence family. No new standalone video/arc_recordings/recognition_* sequence roots.
3. Workspaces DO NOT divide data physically OR logically. No omega_vision\workspaces\<id> namespace, workspace-specific catalogs/ownership filters or cache namespaces that divide the shared data. Workspace provenance/editor configuration is metadata only. Same assets and stable identities are visible across workspace switches. Game/level/run areas may organize the shared store.
4. Inspector gets real authorized areas from this shared root; area selection must not change Save To/Look In. Read-only saved-area browsing must not depend on unrelated sequence enumeration; sequence-specific actions still require valid context.
5. Nowhere stays current-browser-RAM-only; never persist/cache its payloads or relabel full payload copies as audit.
6. Preserve existing files/history. NO automatic migration, merge, rename or deletion of legacy data. Inventory incompatibilities and show unavailable historical settings honestly rather than silently substituting destinations.
7. Enforce these through shared resolver/writer helpers AND regression coverage: path containment for each writer/cache, two-workspace shared visibility/identity, only two canonical sequence families for new saves, no out-of-root/hidden-workspace fallback. Reject unsafe paths; do not weaken access checks. Do not declare compliant based only on changed labels.
```
