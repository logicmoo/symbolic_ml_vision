// Small, explicit call-site patches: retain the original renderer, use Python-produced formats.
export function wireServerSyntax(source) {
  const patches = [
    ["  aggregateClauseArguments,", "  aggregateClauseArguments,\n  formatPredicate,\n  formatBoundArgument,"],
    ['} from "./PrologClauseExplorerModel";', '} from "server-clause-model";'],
    ["aggregateClauseArguments(group.clauses)", "aggregateClauseArguments(group.clauses, syntax)"],
    ['    group.clauses.filter((clause) => (clause.args[argumentIndex] || "") === value),\n  )',
     '    group.clauses.filter((clause) => (clause.args[argumentIndex] || "") === value),\n    syntax,\n  )'],
    ["index === argumentIndex ? shortValue(value, 34) : shortValue(argument || \"_\", 20)",
     "index === argumentIndex ? shortValue(argument, 34) : shortValue(argument || \"_\", 20)"],
    ["argument?.index === index ? argument.value : \"_\"",
     "argument?.index === index ? formatBoundArgument(group, argument, syntax) : \"_\""],
    ['          <option value="json">JSON syntax</option>\n', ""],
    ["        <b>Clause Explorer</b>", "        <b>AtomSpace Explorer</b>"],
    [
      '        <nav className="pce-code-links" aria-label="Clause Explorer implementation">\n' +
        "          <a href={sourceCodeHref(CONTROL_SOURCE_PATH)} target=\"_blank\" rel=\"noreferrer\">TSX control</a>\n" +
        "          <a href={sourceCodeHref(CONTROL_STYLE_PATH)} target=\"_blank\" rel=\"noreferrer\">CSS</a>\n" +
        "        </nav>\n",
      "",
    ],
    ['aria-label="Close Clause Explorer"', 'aria-label="Close AtomSpace Explorer"'],
  ];
  let output = source.replaceAll("\r\n", "\n");
  for (const [before, after] of patches) {
    if (output.split(before).length !== 2) throw new Error(`Original syntax call site changed: ${before}`);
    output = output.replace(before, after);
  }
  const start = output.indexOf("function compactStructuredClause(");
  const end = output.indexOf("function groupPartsMetadata(");
  if (start < 0 || end <= start) throw new Error("Original display-format helpers changed");
  output = output.slice(0, start) + output.slice(start, end)
    .replaceAll("${group.predicate}", "${formatPredicate(group.predicate, syntax)}")
    .replaceAll("${clause.predicate}", "${formatPredicate(clause.predicate, syntax)}") + output.slice(end);
  return output;
}
