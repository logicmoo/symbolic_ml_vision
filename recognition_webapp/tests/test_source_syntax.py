import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frame_metta import _render
from source_syntax import Term, analyze_source, analyze_sources, metta, parse_prolog_term, prolog
from two_frame import _emit_files


class SourceSyntaxTests(unittest.TestCase):
    def convert(self, text, before="prolog", after="metta"):
        suffix = {"prolog": "pl", "metta": "metta", "json": "json"}[before]
        result = analyze_source({"name": "source." + suffix, "text": text})
        self.assertEqual(result["diagnostics"], [])
        return result["formats"][after]

    def test_recovered_proper_lists_and_bare_ids(self):
        samples = {
            "members(['e4']).": "(members ([] e4))",
            "empty([]).": "(empty ([]))",
            "nested([xy(74,8), [r2,'#0c1018']]).": "(nested ([] (xy 74 8) ([] r2 #0c1018)))",
            "members([e4|[e5]]).": "(members ([] e4 e5))",
        }
        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(self.convert(source), expected)
                self.assertNotIn("[|]", expected)
                self.assertNotIn("(list ", expected)

    def test_reverse_proper_list_and_nested_frame_scope(self):
        value = self.convert("(group g7 (layer g) (members ([] e4)) (frame 2))", "metta", "prolog")
        self.assertEqual(value, "group(g7, layer(g), members([e4]), frame(2)).")
        frame = "(part (Frame recordings/events_tests/demo 2) r2 #0c1018)"
        result = self.convert(frame, "metta", "prolog")
        self.assertEqual(result, "part('Frame'('recordings/events_tests/demo', 2), r2, '#0c1018').")
        self.assertEqual(self.convert(result), frame)

    def test_symbols_keep_escaping_and_roundtrip_content(self):
        for value in ("r2", "#0c1018", "recordings/x/y", "Red square", "a(b)c", "a[b]{c}",
                      "a;b", "with\ttab", "line\nbreak", "return\rhere", "back\\slash", 'say "hi"', "$literal"):
            with self.subTest(value=value):
                source = Term("compound", "value", (Term("atom", value),))
                rendered = metta(source)
                self.assertEqual(self.convert(rendered, "metta", "prolog"), prolog(source) + ".")
        self.assertEqual(metta(Term("atom", "")), '""')
        self.assertEqual(self.convert("value('Red square')."), r"(value Red\ square)")
        self.assertEqual(self.convert(r"value('line\nbreak')."), r"(value line\nbreak)")

    def test_variables_are_not_changed_into_layer_atoms(self):
        self.assertEqual(self.convert("p(X, _)."), "(p $X $_)")
        self.assertEqual(self.convert("(p $X $_)", "metta", "prolog"), "p(X, _).")

    def test_unresolved_list_tail_is_not_silently_made_proper(self):
        self.assertEqual(metta(parse_prolog_term("[Head|Tail]")), "(list* $Head $Tail)")
        self.assertEqual(self.convert("(members (list* $Head $Tail))", "metta", "prolog"),
                         "members([Head | Tail]).")

    def test_multiple_clauses_comments_and_multiline_input_are_not_lost(self):
        source = "% Heading\np(a). q([b,c]).\nlong(\n  r2,\n  '#0c1018')."
        result = analyze_source({"name": "both.pl", "text": source})
        self.assertEqual(len(result["clauses"]), 3)
        self.assertIn("(p a) (q ([] b c))", result["formats"]["metta"])
        self.assertIn("(long r2 #0c1018)", result["formats"]["metta"])
        self.assertEqual(result["formats"]["prolog"], source)
        self.assertEqual(self.convert("; note ignored\n(p a)", "metta", "prolog").splitlines()[-1], "p(a).")

    def test_native_comments_rules_and_directives_are_preserved_without_executing(self):
        source = ":- dynamic p/1.\np(X) :- q(X), call(X).\n"
        result = analyze_source({"name": "rules.pl", "text": source})
        self.assertEqual(result["formats"]["prolog"], source)
        self.assertIn("Prolog rule retained in native Prolog only", result["formats"]["metta"])
        self.assertIn(":- q(X), call(X)", result["formats"]["metta"])
        self.assertEqual(len(result["clauses"]), 1)

    def test_json_keeps_types_and_has_real_tree_terms(self):
        source = '{"value":"true","flag":true,"missing":null,"items":[1,"1",false],"empty":[]}'
        result = analyze_source({"name": "geometry.json", "text": source})
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["formats"]["json"], source)
        self.assertEqual(result["clauses"][0]["predicate"], "json_field")
        self.assertEqual(len(result["clauses"]), 5)
        for marker in ("json_string", "json_boolean", "json_null", "json_array", "json_number"):
            self.assertIn(marker, result["formats"]["metta"])
        self.assertIn("(json_string true)", result["formats"]["metta"])
        self.assertIn("(json_boolean true)", result["formats"]["metta"])
        self.assertIn("(json_array ([]))", result["formats"]["metta"])

    def test_all_generated_file_types_and_numbered_names_are_included(self):
        sources = [
            {"name": "frame-2.metta", "text": "(part r2 #0c1018)"},
            {"name": "deductions-2.metta", "text": "(group g7 (members ([] e4)))"},
            {"name": "deductions-2.pl", "text": "group(g7, members(['e4']))."},
            {"name": "geometry.json", "text": '{"parts":[{"id":"r2"}]}'},
            {"name": "recognition.json", "text": '{"object_count":1}'},
        ]
        with patch("builtins.open", side_effect=AssertionError("Conversion must not access files")):
            result = analyze_sources(sources)
        self.assertEqual([item["name"] for item in result["sources"]], [item["name"] for item in sources])
        self.assertTrue(all(item["clauses"] and not item["diagnostics"] for item in result["sources"]))

    def test_invalid_input_is_visible_not_a_fake_success(self):
        for name, text in (("bad.metta", "(missing"), ("bad.metta", r"(value incomplete\ "),
                           ("bad.pl", "p(a,)."), ("bad.json", '{"a":1,"a":2}'),
                           ("bad.json", '{"a":NaN}')):
            with self.subTest(name=name, text=text):
                self.assertTrue(analyze_source({"name": name, "text": text})["diagnostics"])
        with self.assertRaisesRegex(ValueError, "unique"):
            analyze_sources([{"name": "same.pl", "text": "a."}] * 2)

    def test_browser_selection_offsets_match_each_rendered_file(self):
        result = analyze_source({"name": "unicode.pl", "text": "% \U0001f50d\np('a\U0001f642'). q(b)."})
        for syntax in ("prolog", "metta"):
            wire = result["formats"][syntax].encode("utf-16-le")
            for node in result["viewNodes"][syntax]:
                self.assertEqual(wire[node["start"] * 2:node["end"] * 2].decode("utf-16-le"), node["text"])

    def test_native_layer_list_and_symbol_fixes_remain_in_python(self):
        files = _emit_files([], [], [], 2, 1, groups=[
            {"id": "g7", "layer": "G", "members": ["e4"], "gained": [], "lost": []},
        ])
        outputs = {file["name"]: file["content"] for file in files}
        self.assertIn("group(g7, layer(g), members([e4]), frame(2)).", outputs["deductions.pl"])
        self.assertIn("(group g7 (layer g) (members ([] e4)) (frame 2))", outputs["deductions.metta"])
        self.assertEqual(_render(("part", ("Frame", "recordings/x/y", "2"), "r2", "#0c1018", "Red square")),
                         r"(part (Frame recordings/x/y 2) r2 #0c1018 Red\ square)")

    def test_deduction_hypotheses_use_the_same_escape_rules(self):
        files = _emit_files([], [{"current": "e4", "hypotheses": [
            {"label": 'possible "hidden" (part)\nnext', "confidence": 0.5},
        ]}], [], 2, 1)
        for file in files:
            result = analyze_source({"name": file["name"], "text": file["content"]})
            self.assertEqual(result["diagnostics"], [])
        mt = next(file["content"] for file in files if file["name"].endswith(".metta"))
        self.assertIn(r'possible\ \"hidden\"\ \(part\)\nnext', mt)

    def test_headless_cli_has_no_javascript_dependency(self):
        script = Path(__file__).resolve().parents[1] / "source_syntax.py"
        result = subprocess.run([sys.executable, "-B", str(script), "--from", "prolog", "--to", "metta"],
                                input="members(['e4']).", text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, "(members ([] e4))")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
