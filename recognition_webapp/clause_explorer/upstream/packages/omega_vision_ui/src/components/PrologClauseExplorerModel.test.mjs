import assert from "node:assert/strict";
import test from "node:test";
import {
  aggregateClauseArguments,
  autoGroupingArgument,
  clauseRowsKey,
  filterPredicateGroups,
  groupingArgument,
  groupClausesByPredicate,
  orderPredicateGroups,
  parsePrologData,
  parsePrologTerm,
  parseSources,
  partitionKey,
  partitionClausesByArgument,
  partitionRowsKey,
  planExpandMost,
  shouldExposeTermTree,
  sourceTextForSyntax,
  termContainsList,
  termPartCount,
} from "./PrologClauseExplorerModel.ts";

test("parser preserves multiline clauses, nesting, comments, and source lines", () => {
  const parsed = parsePrologData(
    `% heading
shape(
  [a, b(c, d)],
  "x.y"). % inline
/* block
comment */ color(1.5, foo(bar)).
:- dynamic ignored/1.
rule(X) :- helper(X, [a,b]).
`,
    "fixture.pl",
    "Fixture",
  );

  assert.deepEqual(
    parsed.clauses.map((clause) => `${clause.predicate}/${clause.arity}@${clause.line}-${clause.endLine}`),
    ["shape/2@2-4", "color/2@6-6", "rule/1@8-8"],
  );
  assert.equal(parsed.clauses[0].args[0], "[a, b(c, d)]");
  assert.deepEqual(parsed.diagnostics, []);
});

test("parser reports unsupported or incomplete source instead of dropping it silently", () => {
  const invalidHead = parsePrologData("valid(a).\nBadHead(a).\n", "invalid.pl");
  assert.equal(invalidHead.clauses.length, 1);
  assert.equal(invalidHead.diagnostics[0].line, 2);
  assert.equal(invalidHead.diagnostics[0].severity, "warning");
  assert.equal(invalidHead.diagnostics[0].message, "Unsupported or invalid predicate head");

  const unterminated = parsePrologData("value(\"100% complete\")", "unterminated.pl");
  assert.equal(unterminated.diagnostics[0].message, "Unterminated Prolog statement");
  assert.equal(unterminated.diagnostics[0].severity, "error");
  assert.deepEqual(
    parsePrologData("value(\"100% complete\"). % trailing comment\n", "percent.pl").diagnostics,
    [],
  );
  assert.equal(
    parsePrologData("nested([a, b).\n", "unbalanced.pl").diagnostics[0].message,
    "Unbalanced Prolog delimiters",
  );
  const incompleteArguments = parsePrologData("bad(a,).\n", "arguments.pl");
  assert.equal(incompleteArguments.clauses.length, 0);
  assert.equal(incompleteArguments.diagnostics[0].message, "Incomplete predicate argument list");
  assert.equal(incompleteArguments.diagnostics[0].severity, "error");
  for (const source of [
    "bad(,a).",
    "bad(a,,b).",
    "bad(nested(a,)).",
    "bad([a,]).",
    "bad([Head|]).",
    "bad([Head|,Tail]).",
    "bad((a,)).",
    "bad({a,}).",
  ]) {
    const parsed = parsePrologData(source, "nested-arguments.pl");
    assert.equal(parsed.clauses.length, 0, source);
    assert.equal(parsed.diagnostics[0].message, "Incomplete predicate argument list", source);
  }
});

test("predicate order switches without changing clause order or filter stability", () => {
  const clauses = parseSources([
    {
      name: "non-alphabetical.pl",
      text: "zeta(match).\nalpha(other).\nzeta(other).\nbeta(match).\n",
    },
  ]);
  const sourceOrder = groupClausesByPredicate(clauses);

  assert.deepEqual(sourceOrder.map((group) => group.key), ["zeta/1", "alpha/1", "beta/1"]);
  assert.deepEqual(
    orderPredicateGroups(sourceOrder, "alphabetical").map((group) => group.key),
    ["alpha/1", "beta/1", "zeta/1"],
  );
  assert.deepEqual(sourceOrder[0].clauses.map((clause) => clause.args[0]), ["match", "other"]);

  const filtered = filterPredicateGroups(sourceOrder, "match");
  assert.deepEqual(filtered.map((group) => group.key), ["zeta/1", "beta/1"]);
  assert.deepEqual(
    orderPredicateGroups(filtered, "alphabetical").map((group) => group.key),
    ["beta/1", "zeta/1"],
  );
});

test("clause-count order is descending with natural alphabetical ties and preserves source order", () => {
  const sourceOrder = groupClausesByPredicate(parseSources([{
    name: "counts.pl",
    text: [
      "region10(a).",
      "single(a).",
      "region2(first).",
      "largest(first).",
      "region10(b).",
      "largest(second).",
      "region2(second).",
      "largest(third).",
    ].join("\n"),
  }]));
  const before = structuredClone(sourceOrder);
  const sorted = orderPredicateGroups(sourceOrder, "count");
  assert.deepEqual(sorted.map((group) => group.key), ["largest/1", "region2/1", "region10/1", "single/1"]);
  assert.deepEqual(sorted.map((group) => group.clauses.length), [3, 2, 2, 1]);
  assert.deepEqual(sorted[0].clauses.map((clause) => clause.args[0]), ["first", "second", "third"]);
  assert.deepEqual(sourceOrder, before);
  assert.equal(orderPredicateGroups(sourceOrder, "file"), sourceOrder);
  assert.deepEqual(orderPredicateGroups([], "count"), []);
});

test("count sorting uses the currently filtered clauses and selected source scope", () => {
  const sources = [
    { name: "first.pl", text: "many(match).\nmany(other).\nmany(other).\nfew(match).\nfew(match).\n" },
    { name: "second.pl", text: "few(match).\nfew(match).\n" },
  ];
  const all = parseSources(sources);
  const scope = all.filter((clause) => clause.sourcePath === "first.pl");
  const groups = groupClausesByPredicate(scope);
  assert.deepEqual(orderPredicateGroups(groups, "count").map((group) => group.key), ["many/1", "few/1"]);
  const filtered = orderPredicateGroups(filterPredicateGroups(groups, "match"), "count");
  assert.deepEqual(filtered.map((group) => [group.key, group.clauses.length]), [["few/1", 2], ["many/1", 1]]);
  const bothFiles = orderPredicateGroups(groupClausesByPredicate(all), "count");
  assert.deepEqual(bothFiles.map((group) => [group.key, group.clauses.length]), [["few/1", 4], ["many/1", 3]]);
  assert.deepEqual(groups.map((group) => [group.key, group.clauses.length]), [["many/1", 3], ["few/1", 2]]);
});

test("generic Prolog terms preserve lists at every argument and nesting depth", () => {
  const parsed = parsePrologData(
    "mixed([a,b], wrap(before, [x,[y,z]], after), [], [Head|Tail], atom).\n",
    "nested-lists.pl",
    "Nested lists",
  );
  const [first, wrapped, empty, improper, scalar] = parsed.clauses[0].argTerms;

  assert.equal(first.kind, "list");
  assert.deepEqual(first.items.map((term) => term.source), ["a", "b"]);
  assert.equal(wrapped.kind, "compound");
  assert.equal(wrapped.args[1].kind, "list");
  assert.equal(wrapped.args[1].items[1].kind, "list");
  assert.deepEqual(wrapped.args[1].items[1].items.map((term) => term.source), ["y", "z"]);
  assert.deepEqual(empty, { kind: "list", source: "[]", items: [] });
  assert.equal(improper.kind, "list");
  assert.equal(improper.items[0].source, "Head");
  assert.equal(improper.tail.source, "Tail");
  assert.equal(scalar.kind, "atom");
  assert.equal(termContainsList(wrapped), true);
  assert.equal(termPartCount(improper), 2);

  const json = JSON.parse(sourceTextForSyntax(
    { name: "nested-lists.pl", text: parsed.source, label: "parts_debug_0 / python_pil" },
    parsed.clauses,
    "json",
  ));
  assert.equal(json.source.label, "python_pil");
  assert.equal(json.clauses[0].argumentTerms[1].arguments[1].items[1].kind, "list");
  assert.equal(json.clauses[0].argumentTerms[3].tail.source, "Tail");
});

test("structured term disclosure follows measured visibility", () => {
  const shortList = parsePrologTerm("[a,b]");
  const longList = parsePrologTerm("[start(40,0,90), forward(519), turn(-90), close]");
  const shortCompound = parsePrologTerm("next(none)");
  const nestedCompound = parsePrologTerm("wrapper([a,b], child(deep([x,y,z])))");

  assert.equal(shouldExposeTermTree(shortList, false), false);
  assert.equal(shouldExposeTermTree(longList, false), false);
  assert.equal(shouldExposeTermTree(longList, true), true);
  assert.equal(shouldExposeTermTree(shortCompound, false), false);
  assert.equal(shouldExposeTermTree(shortCompound, true), true);
  assert.equal(termContainsList(nestedCompound), true);
});

test("argument partitions preserve source order and prefer eligible structured values", () => {
  const clauses = parseSources([{
    name: "partitions.pl",
    text: [
      "item(a, same, [x,y]).",
      "item(b, same, [x,y]).",
      "item(c, same, [z]).",
      "item(d, same, [z]).",
    ].join("\n"),
  }]);
  const group = groupClausesByPredicate(clauses)[0];
  const argumentIndex = autoGroupingArgument(group, 20);
  const partitions = partitionClausesByArgument(group.clauses, argumentIndex);

  assert.equal(argumentIndex, 2);
  assert.deepEqual(partitions.map((partition) => partition.value), ["[x,y]", "[z]"]);
  assert.deepEqual(partitions[0].clauses.map((clause) => clause.args[0]), ["a", "b"]);
  assert.equal(autoGroupingArgument(group, 1), -1);
});

test("canonical aggregate heads and forced grouping modes are preserved", () => {
  const groups = groupClausesByPredicate(parseSources([{
    name: "aggregate.pl",
    text: [
      "route(main, north, [a,b]).",
      "route(main, south, [c,d]).",
      "route(main, south, [e,f]).",
    ].join("\n"),
  }]));
  const group = groups[0];

  assert.deepEqual(aggregateClauseArguments(group.clauses), ["main", "…", "…"]);
  assert.equal(groupingArgument(group, "auto", 20), 1);
  assert.equal(groupingArgument(group, "first", 20), 0);
  assert.equal(groupingArgument(group, "second", 20), 1);
  assert.equal(groupingArgument(group, "none", 20), -1);
});

test("Expand most shares the canonical root budget across argument partitions", () => {
  const group = groupClausesByPredicate(parseSources([{
    name: "budget.pl",
    text: [
      "part(a, red).",
      "part(b, red).",
      "part(c, blue).",
      "part(d, blue).",
      "part(e, green).",
      "part(f, green).",
    ].join("\n"),
  }]))[0];
  const plan = planExpandMost([group], "second", 2, 20, 5);
  const partitions = partitionClausesByArgument(group.clauses, 1);

  assert.equal(plan.expanded.has(group.key), true);
  assert.equal(plan.limits.get(partitionRowsKey(group.key, 1)), 3);
  assert.equal(plan.expanded.has(partitionKey(group.key, 1, partitions[0].value)), true);
  assert.equal(plan.limits.get(partitionKey(group.key, 1, "red")), 1);
  assert.equal(plan.limits.get(partitionKey(group.key, 1, "blue")), 1);
  assert.equal(plan.expanded.has(partitionKey(group.key, 1, "green")), false);

  const ungrouped = planExpandMost([group], "none", 2, 20, 4);
  assert.equal(ungrouped.limits.get(clauseRowsKey(group.key)), 4);
});
