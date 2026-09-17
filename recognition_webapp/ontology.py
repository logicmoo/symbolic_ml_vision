"""OmegaVisionMt: CycL-style vocabulary microtheory for the Omega Vision pipeline.

Every predicate the recognizer/deducer/inducer emits is declared with CycL's
meta-vocabulary: `isa`, `arity`, `argNIsa`, `resultIsa` (for denotational
functions), and `comment`. Rendered as KRF (in-microtheory blocks) and MeTTa.

The registry is the source of truth for the ontology; a regression test checks
it covers every event kind `two_frame._detect_events` actually emits.
"""
from __future__ import annotations

import re
from pathlib import Path

MT = "OmegaVisionMt"

# Collections used in argument constraints.
COLLECTIONS = {
    "VisualEntity": "A tracked foreground object with a stable e# identity, persisted across "
                    "frames by the clip tracker; reappearing objects re-bind to their remembered entity.",
    "VisualEntityGroup": "A tracked group (g#/w#) of visual entities that the grouping rules "
                         "accepted; identity persists across frames like entities.",
    "ARC3Command": "An ARC3-style user command token recorded in a frame's reserved state.json "
                   "incoming_action: ACTION1..ACTION4 arrows, ACTION5/6, RESET. FRAME is a "
                   "passive sampled advance and is NEVER a command.",
    "FrameDesignator": "A frame(N) term naming a numbered frame of the recording being analysed.",
    "TruthValue": "A NARS/PLN-style tv(strength, confidence) from counted evidence: strength = "
                  "positive share, confidence = n/(n+1).",
    "Vector2D": "A dxy(dx, dy) pixel displacement per one-second frame step.",
    "VisualEvent": "An event/relation/state/action term asserted for one frame transition.",
    "EventTypeDesignator": "The type key of a visual event as used by induction (e.g. moved, "
                           "user_input(ACTION4), start(contact)).",
}

E, G, CMD = "VisualEntity", "VisualEntityGroup", "ARC3Command"

# name -> (category, [argIsa...], comment)
PREDICATES = {
    # --- movement events (1 arg: the entity) ---
    "moved": ("event", [E], "The entity translated between the previous and the current frame."),
    "moved_right": ("event", [E], "Direction-qualified movement: dominant displacement points right (+x). Definitional under moved."),
    "moved_left": ("event", [E], "Direction-qualified movement: dominant displacement points left (-x). Definitional under moved."),
    "moved_up": ("event", [E], "Direction-qualified movement: dominant displacement points up (-y). Definitional under moved."),
    "moved_down": ("event", [E], "Direction-qualified movement: dominant displacement points down (+y). Definitional under moved."),
    "turned": ("event", [E], "The entity's path heading changed between two consecutive displacement vectors (a path turn, not sprite rotation)."),
    "accelerated": ("event", [E], "The entity's speed increased between consecutive one-second samples."),
    "decelerated": ("event", [E], "The entity's speed decreased between consecutive one-second samples."),
    "bounce": ("event", [E], "Post-contact velocity reversal: the entity contacted something and reversed away."),
    "start": ("event", [E], "Motion episode begins: the entity was at rest and starts moving."),
    "continue": ("event", [E], "Motion episode continues: the entity keeps moving."),
    "end": ("event", [E], "Motion episode ends: the entity stops moving."),
    # --- appearance / identity events ---
    "appeared": ("event", [E], "The entity became visible in the interior with no border-crossing prehistory."),
    "reappeared": ("event", [E], "A previously known entity is re-observed and re-bound to its remembered identity."),
    "entered": ("event", [E], "The entity crossed a viewport boundary into view (border-crossing history required)."),
    "exited": ("event", [E], "The moving entity left through a viewport boundary, matching prior velocity."),
    "missing": ("event", [E], "A previously visible interior entity cannot be found; NOT evidence of destruction, exit or occlusion."),
    # --- shape / appearance change events ---
    "rotated": ("event", [E], "The entity's mask rotated in place with the same pixel area and colour."),
    "color_changed": ("event", [E], "Only the entity's colour changed; shape and position unchanged."),
    "area_changed": ("event", [E], "The entity's occupied pixel area changed without uniform scaling."),
    "scaled": ("event", [E], "The entity grew or shrank uniformly about its centre. Definitional under area_changed."),
    "shape_changed": ("event", [E], "The entity's mask changed to a different shape of comparable area; not a rigid rotation."),
    "deformed": ("event", [E], "Nonuniform deformation: the mask stretched/compressed while conserving area."),
    "hole_opened": ("event", [E], "An enclosed interior hole opened inside the entity; exterior bounding box unchanged."),
    "hole_closed": ("event", [E], "The entity's enclosed interior hole was filled; exterior bounding box unchanged."),
    # --- lineage events ---
    "split": ("event", [E, E, E], "One connected body separated: split(source, childA, childB) with conserved total area."),
    "merged": ("event", [E, E, E], "Two bodies fused into one connected result: merged(result, sourceA, sourceB)."),
    # --- group events ---
    "group_formed": ("event", [G], "Independent pieces joined into a coherent tracked assembly."),
    "group_dissolved": ("event", [G], "An existing assembly separated into independent pieces."),
    "member_added": ("event", [G, E], "member_added(group, member): a piece joined an existing assembly."),
    "member_removed": ("event", [G, E], "member_removed(group, member): a member left while the assembly survives."),
    # --- two-entity events ---
    "collision": ("event", [E, E], "Two approaching entities contacted and showed a motion response (recoil)."),
    # --- relations (episodic: start/continue/end phases apply) ---
    "contact": ("relation", [E, E], "The two entities share a boundary (touching), without overlapping pixels."),
    "attached": ("relation", [E, E], "Sealed attachment: a persisting long shared edge and rigid co-movement, stronger than contact."),
    "blocked": ("relation", [E, E], "blocked(entity, obstacle): the entity's attempted movement is prevented by the obstacle it presses against. Causal: requires attempt evidence (a recorded or abduced command), not stationary contact alone."),
    "carry": ("relation", [E, E], "carry(carrier, load): a supported carrier/load relation with joint motion, not co-motion alone."),
    "co_move": ("relation", [E, E], "The two entities share the same displacement; co-motion does not imply attachment or shared identity."),
    "follow": ("relation", [E, E], "follow(follower, leader): the follower visits the leader's previous positions with a lag."),
    "occlude": ("relation", [E, E], "occlude(occluder, hidden): the occluder hides the entity; darkness/occlusion hides but never erases."),
    # --- states ---
    "stationary": ("state", [E], "The entity did not move across the transition."),
    "visible": ("state", [E], "The entity is currently observed."),
    "absent": ("state", [E], "The entity is currently not observed (occluded or missing); absence of evidence stays unknown, not false."),
    # --- actions ---
    "user_input": ("action", [CMD], "An exogenous user command recorded in the frame's reserved state.json (or abduced when hidden). FRAME advances never assert user_input."),
}

# Function-denotational terms -> (arity, resultIsa, comment)
FUNCTIONS = {
    "tv": (2, "TruthValue", "tv(strength, confidence): counted-evidence truth value; contradictions lower strength instead of discarding the belief."),
    "dxy": (2, "Vector2D", "dxy(dx, dy): pixel displacement per one-second frame step."),
    "frame": (1, "FrameDesignator", "frame(N): the numbered frame a fact is asserted for."),
}

PREDICATE_ARITY_ISA = {1: "UnaryPredicate", 2: "BinaryPredicate",
                       3: "TernaryPredicate", 4: "QuaternaryPredicate", 5: "QuintaryPredicate"}
FUNCTION_ARITY_ISA = {1: "UnaryFunction", 2: "BinaryFunction",
                      3: "TernaryFunction", 4: "QuaternaryFunction"}


def predicate_isa(arity: int) -> str:
    """CycL arity-typed specialisation of Predicate (UnaryPredicate, BinaryPredicate, ...)."""
    return PREDICATE_ARITY_ISA.get(arity, "Predicate")


def function_isa(arity: int) -> str:
    """CycL arity-typed specialisation of Function-Denotational (UnaryFunction, ...)."""
    return FUNCTION_ARITY_ISA.get(arity, "Function-Denotational")

# Belief/derivation wrapper predicates (induction/deduction layer).
BELIEF_PREDICATES = {
    "event": (["VisualEvent", "FrameDesignator"], "event(Term, frame(N)): a detected instantaneous event at frame N."),
    "relation": (["VisualEvent", "FrameDesignator"], "relation(Term, frame(N)): a detected episodic relation observation at frame N."),
    "state": (["VisualEvent", "FrameDesignator"], "state(Term, frame(N)): a detected state observation at frame N."),
    "action": (["VisualEvent", "FrameDesignator"], "action(user_input(Cmd), frame(N)): the recorded exogenous input at frame N."),
    "guess": (["VisualEvent", "TruthValue"], "guess(Belief, tv(S,C), support(N)): an inductive hypothesis with counted evidence; never a fact."),
    "prediction": (["VisualEvent", "FrameDesignator"], "prediction(Term, ...): a next-frame expectation issued from prior beliefs, later scored confirmed/refuted."),
    "abducible": (["EventTypeDesignator", "EventTypeDesignator"], "abducible(Hypothesis, explains(Observed), when(W)): a hidden antecedent hypothesised because a believed implication's consequent was observed without it; an explanation, never an observation."),
    "implies": (["EventTypeDesignator", "EventTypeDesignator"], "implies(A, B, When): induced implication between event types with counted evidence; misses fully explained by an UNLESS precondition are excused and named."),
    "user_action": ([CMD, "FrameDesignator"], "user_action(Command, from_frame(P), to_frame(N)): the recorded command that led into frame N."),
    "frame_context": (["EventTypeDesignator", "EventTypeDesignator"], "frame_context(Key, Value): scalar input evidence from the frame's reserved state.json."),
}


def emitted_event_kinds() -> set:
    """Every event/relation/state/action kind two_frame._detect_events actually emits."""
    text = (Path(__file__).parent / "two_frame.py").read_text(encoding="utf-8")
    kinds = set()
    for match in re.finditer(r'add\("(?:event|relation|state|action)",\s*"([a-z_]+)"', text):
        kinds.add(match.group(1))
    for match in re.finditer(r'if [^\n]+ else "([a-z_]+)", e\)', text):
        kinds.add(match.group(1))
    return kinds


def render_krf() -> str:
    lines = [
        ";; OmegaVisionMt - vocabulary of the Omega Vision symbolic recognition pipeline.",
        ";; Generated by recognition_webapp/ontology.py (symbolic_ml_vision); regenerate there.",
        ";; Detected facts are observations of one recording; guesses carry tv(strength,",
        ";; confidence) counted evidence and are hypotheses, never ground truth.",
        "",
        "(in-microtheory BaseKB)",
        f"(isa {MT} Microtheory)",
        f"(genlMt {MT} BaseKB)",
        f'(comment {MT} "Vocabulary of the Omega Vision symbolic recognition pipeline: '
        'per-transition visual events, episodic relations, states and exogenous user '
        'commands detected from recorded frames, plus the induction/abduction belief '
        'layer built over them. Frame-to-frame law: beliefs only ever accumulate from '
        'the transitions already seen; nothing is revealed before its frame.")',
        "",
        f"(in-microtheory {MT})",
        "",
        ";; --- Collections ---",
    ]
    for name, comment in COLLECTIONS.items():
        lines.append(f"(isa {name} Collection)")
        lines.append(f'(comment {name} "{comment}")')
    lines.append("")
    for category, title in (("event", "Instantaneous visual events"),
                            ("relation", "Episodic relations (start/continue/end phases apply)"),
                            ("state", "States"),
                            ("action", "Exogenous actions")):
        lines.append(f";; --- {title} ---")
        for name, (cat, args, comment) in PREDICATES.items():
            if cat != category:
                continue
            lines.append(f"(isa {name} {predicate_isa(len(args))})")
            lines.append(f"(arity {name} {len(args)})")
            for index, arg in enumerate(args, 1):
                lines.append(f"(arg{index}Isa {name} {arg})")
            lines.append(f'(comment {name} "{comment}")')
        lines.append("")
    lines.append(";; --- Denotational functions ---")
    for name, (arity, result, comment) in FUNCTIONS.items():
        lines.append(f"(isa {name} Function-Denotational)")
        lines.append(f"(isa {name} {function_isa(arity)})")
        lines.append(f"(arity {name} {arity})")
        lines.append(f"(resultIsa {name} {result})")
        lines.append(f'(comment {name} "{comment}")')
    lines.append("")
    lines.append(";; --- Belief / derivation layer ---")
    for name, (args, comment) in BELIEF_PREDICATES.items():
        lines.append(f"(isa {name} {predicate_isa(len(args))})")
        lines.append(f"(arity {name} {len(args)})")
        for index, arg in enumerate(args, 1):
            lines.append(f"(arg{index}Isa {name} {arg})")
        lines.append(f'(comment {name} "{comment}")')
    lines.append("")
    return "\n".join(lines)


def render_metta() -> str:
    lines = [
        "; OmegaVisionMt - vocabulary of the Omega Vision symbolic recognition pipeline.",
        "; Generated by recognition_webapp/ontology.py (symbolic_ml_vision); regenerate there.",
        f"(isa {MT} Microtheory)",
        f"(genlMt {MT} BaseKB)",
    ]
    for name, comment in COLLECTIONS.items():
        lines.append(f"(ist {MT} (isa {name} Collection))")
        lines.append(f'(ist {MT} (comment {name} "{comment}"))')
    for name, (cat, args, comment) in PREDICATES.items():
        lines.append(f"(ist {MT} (isa {name} {predicate_isa(len(args))}))")
        lines.append(f"(ist {MT} (arity {name} {len(args)}))")
        for index, arg in enumerate(args, 1):
            lines.append(f"(ist {MT} (arg{index}Isa {name} {arg}))")
        lines.append(f'(ist {MT} (comment {name} "{comment}"))')
    for name, (arity, result, comment) in FUNCTIONS.items():
        lines.append(f"(ist {MT} (isa {name} Function-Denotational))")
        lines.append(f"(ist {MT} (isa {name} {function_isa(arity)}))")
        lines.append(f"(ist {MT} (arity {name} {arity}))")
        lines.append(f"(ist {MT} (resultIsa {name} {result}))")
        lines.append(f'(ist {MT} (comment {name} "{comment}"))')
    for name, (args, comment) in BELIEF_PREDICATES.items():
        lines.append(f"(ist {MT} (isa {name} {predicate_isa(len(args))}))")
        lines.append(f"(ist {MT} (arity {name} {len(args)}))")
        for index, arg in enumerate(args, 1):
            lines.append(f"(ist {MT} (arg{index}Isa {name} {arg}))")
        lines.append(f'(ist {MT} (comment {name} "{comment}"))')
    return "\n".join(lines) + "\n"


def write_ontology(target: Path) -> list:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (("OmegaVisionMt.krf", render_krf()), ("OmegaVisionMt.metta", render_metta())):
        path = target / name
        data = text.replace("\r\n", "\n").encode("utf-8")
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        written.append(path)
    return written


if __name__ == "__main__":
    import sys
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data" / "omega_vision" / "knowledge"
    for path in write_ontology(destination):
        print(path)
