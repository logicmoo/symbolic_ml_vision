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
    [
      // Portray objects: the #rrggbb literal itself becomes a swatch — background of that
      // color, text inverted to contrast — in EVERY syntax, not only Prolog.
      '  if (context.syntax !== "prolog" || typeof context.proposedHtml !== "string") {\n' +
      "    return context.proposedHtml;\n" +
      "  }\n" +
      "  const parts = context.proposedHtml.split(/(#[0-9a-fA-F]{3,8}\\b)/g);\n" +
      "  if (parts.length === 1) return context.proposedHtml;\n" +
      "  return parts.map((part, index) =>\n" +
      "    /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(part)\n" +
      "      ? (\n" +
      "          <span className=\"pce-color-chip\" key={`${part}:${index}`}>\n" +
      '            <span className="pce-color-bar" style={{ backgroundColor: part }} />\n' +
      "            {part}\n" +
      "          </span>\n" +
      "        )\n" +
      "      : part\n" +
      "  );",
      '  if (typeof context.proposedHtml !== "string") {\n' +
      "    return context.proposedHtml;\n" +
      "  }\n" +
      "  const parts = context.proposedHtml.split(/(#[0-9a-fA-F]{3,8}\\b)/g);\n" +
      "  if (parts.length === 1) return context.proposedHtml;\n" +
      "  const contrastInk = (hex: string) => {\n" +
      "    let value = hex.slice(1);\n" +
      "    if (value.length < 6) value = value.split(\"\").map((ch) => ch + ch).join(\"\").slice(0, 6);\n" +
      "    const r = parseInt(value.slice(0, 2), 16) || 0;\n" +
      "    const g = parseInt(value.slice(2, 4), 16) || 0;\n" +
      "    const b = parseInt(value.slice(4, 6), 16) || 0;\n" +
      "    return 0.299 * r + 0.587 * g + 0.114 * b > 140 ? \"#000000\" : \"#ffffff\";\n" +
      "  };\n" +
      "  return parts.map((part, index) =>\n" +
      "    /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(part)\n" +
      "      ? (\n" +
      "          <span className=\"pce-color-chip\" key={`${part}:${index}`}\n" +
      "            style={{ backgroundColor: part, color: contrastInk(part) }}>\n" +
      "            {part}\n" +
      "          </span>\n" +
      "        )\n" +
      "      : part\n" +
      "  );",
    ],
    [
      "  const scopeClauses = useMemo(() => clauses.filter((clause) =>\n" +
      "    visibleSourceNames.has(clause.sourcePath)\n" +
      "    && (!onlyCurrent || !fileFocus || clause.sourcePath === fileFocus)\n" +
      "  ), [clauses, fileFocus, onlyCurrent, visibleSourceNames]);",
      "  const scopeClauses = useMemo(() => {\n" +
      "    // Identical clauses repeated across sibling files (regions.pl / regions.metta /\n" +
      "    // frame-N.metta hold the same facts) appear ONCE in the tree: first file wins.\n" +
      "    const seen = new Set();\n" +
      "    return clauses.filter((clause) => {\n" +
      "      if (!visibleSourceNames.has(clause.sourcePath)) return false;\n" +
      "      if (onlyCurrent && fileFocus && clause.sourcePath !== fileFocus) return false;\n" +
      "      const identity = `${clause.predicate}/${clause.arity}|${clause.args.join(\"\\u0001\")}`;\n" +
      "      if (seen.has(identity)) return false;\n" +
      "      seen.add(identity);\n" +
      "      return true;\n" +
      "    });\n" +
      "  }, [clauses, fileFocus, onlyCurrent, visibleSourceNames]);",
    ],
    [
      // Portray objects applies to compact clause rows too, not only fully-shown facts.
      "            <code>{canExpand\n" +
      "              ? compact\n" +
      "              : portrayObjects\n" +
      "                ? portrayClause({ clause, syntax, proposedHtml: rendered }, portray)\n" +
      "                : rendered}</code>",
      "            <code>{portrayObjects\n" +
      "              ? portrayClause({ clause, syntax, proposedHtml: canExpand ? compact : rendered }, portray)\n" +
      "              : canExpand ? compact : rendered}</code>",
    ],
    [
      // Portray objects applies to argument-partition rows in the predicate tree.
      "                <code>{partitionShape(group, argumentIndex, partition.value, syntax)}</code>",
      "                <code>{portrayObjects\n" +
      "                  ? portrayClause({ clause: firstClause, syntax, proposedHtml: partitionShape(group, argumentIndex, partition.value, syntax) }, portray)\n" +
      "                  : partitionShape(group, argumentIndex, partition.value, syntax)}</code>",
    ],
    [
      // Portray objects applies to predicate-group headers in the tree.
      "                      <code>{groupShape(group, syntax)}</code>",
      "                      <code>{portrayObjects\n" +
      "                        ? portrayClause({ clause: fullGroup.clauses[0], syntax, proposedHtml: groupShape(group, syntax) }, portray)\n" +
      "                        : groupShape(group, syntax)}</code>",
    ],
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
