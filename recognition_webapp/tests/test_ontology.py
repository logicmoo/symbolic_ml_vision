"""OmegaVisionMt ontology coverage: the CycL vocabulary must match what the code emits."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ontology import (BELIEF_PREDICATES, COLLECTIONS, FUNCTIONS, PREDICATES,
                      emitted_event_kinds, render_krf, render_metta)


class OmegaVisionMtTests(unittest.TestCase):
    def test_every_emitted_kind_is_declared(self):
        emitted = emitted_event_kinds()
        self.assertTrue(emitted, "two_frame.py must emit event kinds")
        missing = emitted - set(PREDICATES)
        self.assertFalse(missing, f"Emitted kinds missing from OmegaVisionMt: {sorted(missing)}")

    def test_every_predicate_is_fully_declared(self):
        for name, (category, args, comment) in PREDICATES.items():
            self.assertIn(category, ("event", "relation", "state", "action"), name)
            self.assertTrue(args, f"{name} needs at least arg1Isa")
            for arg in args:
                self.assertIn(arg, COLLECTIONS, f"{name} argIsa {arg} must be a declared Collection")
            self.assertGreater(len(comment), 20, f"{name} needs a real comment")
        for name, (result, comment) in FUNCTIONS.items():
            self.assertIn(result, COLLECTIONS, f"{name} resultIsa {result} must be a declared Collection")
            self.assertGreater(len(comment), 20, name)
        for name, (args, comment) in BELIEF_PREDICATES.items():
            for arg in args:
                self.assertIn(arg, COLLECTIONS, f"{name} argIsa {arg} must be a declared Collection")
            self.assertGreater(len(comment), 20, name)

    def test_renders_are_balanced_and_complete(self):
        krf, metta = render_krf(), render_metta()
        for text, label in ((krf, "krf"), (metta, "metta")):
            meaningful = "\n".join(line for line in text.splitlines()
                                   if not line.lstrip().startswith((";", ";;")))
            self.assertEqual(meaningful.count("("), meaningful.count(")"), f"{label} parens balanced")
        for name in list(PREDICATES) + list(FUNCTIONS) + list(BELIEF_PREDICATES) + list(COLLECTIONS):
            self.assertIn(f"comment {name} ", krf, f"{name} comment in krf")
            self.assertIn(f"comment {name} ", metta, f"{name} comment in metta")
        self.assertIn("(in-microtheory OmegaVisionMt)", krf)
        self.assertIn("(resultIsa tv TruthValue)", krf)
        self.assertIn("(arg1Isa blocked VisualEntity)", krf)
        self.assertIn("(arg2Isa blocked VisualEntity)", krf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
