export type SourceDialect = "prolog" | "metta";
export type ExplorerSyntax = "prolog" | "metta" | "json";
export type PredicateOrder = "file" | "alphabetical" | "count";
export type ArgumentGroupingMode = "auto" | "first" | "second" | "none";

export interface SourceFile {
  name: string;
  text: string;
  label?: string;
  sourceUrl?: string;
  dialect?: SourceDialect;
  readOnly?: boolean;
}

export type PrologTerm =
  | {
      kind: "list";
      source: string;
      items: PrologTerm[];
      tail?: PrologTerm;
    }
  | {
      kind: "compound";
      source: string;
      functor: string;
      args: PrologTerm[];
    }
  | {
      kind: "atom" | "number" | "variable" | "string";
      source: string;
    };

export interface Clause {
  index: number;
  predicate: string;
  arity: number;
  args: string[];
  argTerms: PrologTerm[];
  source: string;
  original: string;
  metta: string;
  sourcePath: string;
  sourceLabel: string;
  line: number;
  endLine: number;
}

export interface PredicateGroup {
  key: string;
  predicate: string;
  arity: number;
  clauses: Clause[];
}

export interface ClausePartition {
  value: string;
  clauses: Clause[];
}

export interface ExpansionPlan {
  expanded: Set<string>;
  limits: Map<string, number>;
}

export interface ParsedProlog {
  source: string;
  clauses: Clause[];
  predicates: PredicateGroup[];
  diagnostics: PrologParseDiagnostic[];
}

export interface PrologParseDiagnostic {
  line: number;
  severity: "warning" | "error";
  message: string;
  statement: string;
}

type PrologStatement = {
  text: string;
  line: number;
  endLine: number;
};

function sourceBasename(path: string): string {
  return path.split(/[\\/]/).map((part) => part.trim()).filter(Boolean).at(-1) || path.trim();
}

function splitTopLevel(text: string, delimiter = ","): string[] {
  const parts: string[] = [];
  let start = 0;
  let parens = 0;
  let brackets = 0;
  let braces = 0;
  let quote = "";
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    else if (char === delimiter && parens === 0 && brackets === 0 && braces === 0) {
      parts.push(text.slice(start, index).trim());
      start = index + 1;
    }
  }
  const tail = text.slice(start).trim();
  parts.push(tail);
  return parts;
}

function findTopLevelCharacter(text: string, delimiter: string): number {
  let parens = 0;
  let brackets = 0;
  let braces = 0;
  let quote = "";
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    else if (char === delimiter && parens === 0 && brackets === 0 && braces === 0) return index;
  }
  return -1;
}

function hasIncompleteTermParts(source: string): boolean {
  const value = source.trim();
  if (value.startsWith("[") && value.endsWith("]")) {
    const body = value.slice(1, -1).trim();
    if (!body) return false;
    const tailAt = findTopLevelCharacter(body, "|");
    const itemSource = tailAt >= 0 ? body.slice(0, tailAt) : body;
    const tailSource = tailAt >= 0 ? body.slice(tailAt + 1).trim() : "";
    if (tailAt >= 0 && (!itemSource.trim() || !tailSource)) return true;
    const items = itemSource.trim() ? splitTopLevel(itemSource) : [];
    return items.some((item) => !item || hasIncompleteTermParts(item))
      || Boolean(tailSource && hasIncompleteTermParts(tailSource));
  }

  if (
    (value.startsWith("(") && value.endsWith(")"))
    || (value.startsWith("{") && value.endsWith("}"))
  ) {
    const body = value.slice(1, -1).trim();
    if (!body) return value.startsWith("(");
    return splitTopLevel(body).some((part) => !part || hasIncompleteTermParts(part));
  }

  const compound = /^([a-z][A-Za-z0-9_]*|'(?:\\.|[^'])*')\s*\(([\s\S]*)\)$/.exec(value);
  if (compound) {
    if (!compound[2].trim()) return false;
    return splitTopLevel(compound[2]).some((argument) =>
      !argument || hasIncompleteTermParts(argument)
    );
  }

  const separated = splitTopLevel(value);
  return separated.length > 1 || separated.some((part) => !part);
}

export function parsePrologTerm(source: string): PrologTerm {
  const value = source.trim();
  if (value.startsWith("[") && value.endsWith("]")) {
    const body = value.slice(1, -1).trim();
    if (!body) return { kind: "list", source: value, items: [] };
    const tailAt = findTopLevelCharacter(body, "|");
    const itemSource = tailAt >= 0 ? body.slice(0, tailAt) : body;
    const tailSource = tailAt >= 0 ? body.slice(tailAt + 1).trim() : "";
    return {
      kind: "list",
      source: value,
      items: itemSource.trim() ? splitTopLevel(itemSource).map(parsePrologTerm) : [],
      ...(tailSource ? { tail: parsePrologTerm(tailSource) } : {}),
    };
  }

  const compound = /^([a-z][A-Za-z0-9_]*|'(?:\\.|[^'])*')\s*\(([\s\S]*)\)$/.exec(value);
  if (compound) {
    return {
      kind: "compound",
      source: value,
      functor: compound[1],
      args: compound[2].trim() ? splitTopLevel(compound[2]).map(parsePrologTerm) : [],
    };
  }
  if (/^-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) {
    return { kind: "number", source: value };
  }
  if (/^[A-Z_][A-Za-z0-9_]*$/.test(value)) return { kind: "variable", source: value };
  if (
    (value.startsWith("'") && value.endsWith("'"))
    || (value.startsWith('"') && value.endsWith('"'))
  ) return { kind: "string", source: value };
  return { kind: "atom", source: value };
}

export function termContainsList(term: PrologTerm): boolean {
  if (term.kind === "list") return true;
  return term.kind === "compound" && term.args.some(termContainsList);
}

export function termPartCount(term: PrologTerm): number {
  if (term.kind === "list") return term.items.length + (term.tail ? 1 : 0);
  if (term.kind === "compound") return term.args.length;
  return 0;
}

export function shouldExposeTermTree(term: PrologTerm, isOverflowing: boolean): boolean {
  return (term.kind === "list" || term.kind === "compound")
    && isOverflowing
    && termPartCount(term) > 0;
}

export function splitPrologStatements(source: string): PrologStatement[] {
  const statements: PrologStatement[] = [];
  let current = "";
  let currentLine: number | null = null;
  let line = 1;
  let parens = 0;
  let brackets = 0;
  let braces = 0;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  const appendCommentGap = () => {
    if (current && !/\s$/.test(current)) current += " ";
  };

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";

    if (lineComment) {
      if (char === "\n") {
        lineComment = false;
        if (current) current += "\n";
        line += 1;
      }
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      } else if (char === "\n") {
        if (current) current += "\n";
        line += 1;
      }
      continue;
    }
    if (quote) {
      current += char;
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      if (char === "\n") line += 1;
      continue;
    }
    if (char === "%") {
      appendCommentGap();
      lineComment = true;
      continue;
    }
    if (char === "/" && next === "*") {
      appendCommentGap();
      blockComment = true;
      index += 1;
      continue;
    }
    if (currentLine === null && !/\s/.test(char)) currentLine = line;
    if (char === "'" || char === '"') {
      quote = char;
      current += char;
      continue;
    }
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    current += char;

    const terminatesStatement = char === "."
      && parens === 0
      && brackets === 0
      && braces === 0
      && (!next || /\s/.test(next) || next === "%" || (next === "/" && source[index + 2] === "*"));
    if (terminatesStatement) {
      const text = current.trim();
      if (text && currentLine !== null) statements.push({ text, line: currentLine, endLine: line });
      current = "";
      currentLine = null;
    }
    if (char === "\n") line += 1;
  }

  return statements;
}

function topLevelRuleSeparator(text: string): number {
  let parens = 0;
  let brackets = 0;
  let braces = 0;
  let quote = "";
  let escaped = false;
  for (let index = 0; index < text.length - 1; index += 1) {
    const char = text[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "'" || char === '"') quote = char;
    else if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    else if (
      char === ":"
      && text[index + 1] === "-"
      && parens === 0
      && brackets === 0
      && braces === 0
    ) return index;
  }
  return -1;
}

function sourceEndingDiagnostic(source: string): PrologParseDiagnostic | null {
  let line = 1;
  let lastCode = "";
  let lastCodeLine = 1;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  let blockCommentLine = 1;
  let parens = 0;
  let brackets = 0;
  let braces = 0;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";
    if (lineComment) {
      if (char === "\n") {
        lineComment = false;
        line += 1;
      }
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      } else if (char === "\n") {
        line += 1;
      }
      continue;
    }
    if (quote) {
      if (!/\s/.test(char)) {
        lastCode = char;
        lastCodeLine = line;
      }
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      if (char === "\n") line += 1;
      continue;
    }
    if (char === "%") {
      lineComment = true;
      continue;
    }
    if (char === "/" && next === "*") {
      blockComment = true;
      blockCommentLine = line;
      index += 1;
      continue;
    }
    if (!/\s/.test(char)) {
      lastCode = char;
      lastCodeLine = line;
    }
    if (char === "'" || char === '"') quote = char;
    else if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;
    if (char === "\n") line += 1;
  }

  if (blockComment) {
    return {
      line: blockCommentLine,
      severity: "error",
      message: "Unterminated block comment",
      statement: "",
    };
  }
  if (quote) {
    return {
      line: lastCodeLine,
      severity: "error",
      message: "Unterminated quoted value",
      statement: "",
    };
  }
  if (parens !== 0 || brackets !== 0 || braces !== 0) {
    return {
      line: lastCodeLine,
      severity: "error",
      message: "Unbalanced Prolog delimiters",
      statement: "",
    };
  }
  if (lastCode && lastCode !== ".") {
    return {
      line: lastCodeLine,
      severity: "error",
      message: "Unterminated Prolog statement",
      statement: "",
    };
  }
  return null;
}

function termToMetta(term: PrologTerm): string {
  if (term.kind === "list") {
    const members = term.items.map(termToMetta);
    if (term.tail) return `(list* ${[...members, termToMetta(term.tail)].join(" ")})`;
    return members.length ? `(list ${members.join(" ")})` : "(list)";
  }
  if (term.kind === "compound") {
    const args = term.args.map(termToMetta);
    return args.length ? `(${term.functor} ${args.join(" ")})` : `(${term.functor})`;
  }
  if (term.kind === "string") {
    return JSON.stringify(term.source.slice(1, -1).replace(/\\(['"\\])/g, "$1"));
  }
  return term.source;
}

function prologTermToMetta(term: string): string {
  return termToMetta(parsePrologTerm(term));
}

export function groupClausesByPredicate(clauses: Clause[]): PredicateGroup[] {
  const byPredicate = new Map<string, PredicateGroup>();
  for (const clause of clauses) {
    const key = `${clause.predicate}/${clause.arity}`;
    const group = byPredicate.get(key) || {
      key,
      predicate: clause.predicate,
      arity: clause.arity,
      clauses: [],
    };
    group.clauses.push(clause);
    byPredicate.set(key, group);
  }
  return [...byPredicate.values()];
}

export function orderPredicateGroups(
  groups: PredicateGroup[],
  order: PredicateOrder,
): PredicateGroup[] {
  if (order === "file") return groups;
  return [...groups].sort((left, right) =>
    (order === "count" ? right.clauses.length - left.clauses.length : 0)
    || left.key.localeCompare(right.key, undefined, { numeric: true, sensitivity: "base" })
  );
}

export function partitionClausesByArgument(
  clauses: Clause[],
  argumentIndex: number,
): ClausePartition[] {
  const partitions = new Map<string, Clause[]>();
  for (const clause of clauses) {
    const value = clause.args[argumentIndex] || "";
    const rows = partitions.get(value) || [];
    rows.push(clause);
    partitions.set(value, rows);
  }
  return [...partitions].map(([value, rows]) => ({ value, clauses: rows }));
}

export function autoGroupingArgument(group: PredicateGroup, pageSize: number): number {
  const candidates = Array.from({ length: group.arity }, (_, index) => {
    const values = new Set(group.clauses.map((clause) => clause.args[index] || ""));
    return { index, count: values.size };
  }).filter(({ count }) => count > 1 && count <= Math.max(1, pageSize));
  candidates.sort((left, right) =>
    left.count - right.count
    || left.index - right.index
  );
  return candidates[0]?.index ?? -1;
}

export function groupingArgument(
  group: PredicateGroup,
  mode: ArgumentGroupingMode,
  pageSize: number,
): number {
  if (mode === "none" || group.arity === 0) return -1;
  if (mode === "first") return 0;
  if (mode === "second") return group.arity > 1 ? 1 : 0;
  return autoGroupingArgument(group, pageSize);
}

export function aggregateClauseArguments(clauses: Clause[]): string[] {
  if (!clauses.length) return [];
  const arguments_ = clauses[0].args.map((value, index) =>
    clauses.every((clause) => clause.args[index] === value) ? value : "_"
  );
  const hasInvariant = arguments_.some((value) => value !== "_");
  return hasInvariant
    ? arguments_.map((value) => value === "_" ? "…" : value)
    : arguments_;
}

export function clauseRowsKey(groupKey: string): string {
  return `${groupKey}\u0000facts`;
}

export function partitionRowsKey(groupKey: string, argumentIndex: number): string {
  return `${groupKey}\u0000groups:${argumentIndex}`;
}

export function partitionKey(
  groupKey: string,
  argumentIndex: number,
  value: string,
): string {
  return `${groupKey}\u0000arg:${argumentIndex}\u0000${value}`;
}

export function planExpandMost(
  groups: PredicateGroup[],
  groupingMode: ArgumentGroupingMode,
  treeThreshold: number,
  pageSize: number,
  rootMax: number,
): ExpansionPlan {
  const expanded = new Set<string>();
  const limits = new Map<string, number>();
  const threshold = Math.max(1, treeThreshold);
  const page = Math.max(1, pageSize);
  const maximum = Math.max(1, rootMax);

  for (const group of groups) {
    expanded.add(group.key);
    const argumentIndex = group.clauses.length > threshold
      ? groupingArgument(group, groupingMode, page)
      : -1;
    if (argumentIndex < 0) {
      limits.set(clauseRowsKey(group.key), Math.min(maximum, group.clauses.length));
      continue;
    }

    const partitions = partitionClausesByArgument(group.clauses, argumentIndex);
    const shown = Math.min(partitions.length, page, maximum);
    limits.set(partitionRowsKey(group.key, argumentIndex), shown);
    if (!shown) continue;
    const remaining = Math.max(0, maximum - shown);
    for (const [index, partition] of partitions.slice(0, shown).entries()) {
      const allowance = Math.floor(remaining / shown) + (index < remaining % shown ? 1 : 0);
      if (allowance <= 0) continue;
      const key = partitionKey(group.key, argumentIndex, partition.value);
      expanded.add(key);
      limits.set(key, Math.min(partition.clauses.length, allowance));
    }
  }
  return { expanded, limits };
}

export function filterPredicateGroups(groups: PredicateGroup[], query: string): PredicateGroup[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return groups;
  return groups.flatMap((group) => {
    if (group.key.toLowerCase().includes(normalized)) return [group];
    const clauses = group.clauses.filter((clause) =>
      clause.source.toLowerCase().includes(normalized)
      || clause.args.some((argument) => argument.toLowerCase().includes(normalized))
    );
    return clauses.length ? [{ ...group, clauses }] : [];
  });
}

export function parsePrologData(
  source: string,
  sourcePath = "",
  sourceLabel = sourcePath || "Prolog source",
): ParsedProlog {
  const clauses: Clause[] = [];
  const diagnostics: PrologParseDiagnostic[] = [];
  for (const statement of splitPrologStatements(source)) {
    const body = statement.text.replace(/\.\s*$/, "").trim();
    if (!body || body.startsWith(":-") || body.startsWith("?-")) continue;
    const ruleAt = topLevelRuleSeparator(body);
    const head = (ruleAt >= 0 ? body.slice(0, ruleAt) : body).trim();
    const match = /^([a-z][A-Za-z0-9_]*)(?:\s*\(([\s\S]*)\))?$/.exec(head);
    if (!match) {
      diagnostics.push({
        line: statement.line,
        severity: "warning",
        message: "Unsupported or invalid predicate head",
        statement: statement.text,
      });
      continue;
    }
    const args = match[2] === undefined || !match[2].trim() ? [] : splitTopLevel(match[2]);
    if (args.some((argument) => !argument || hasIncompleteTermParts(argument))) {
      diagnostics.push({
        line: statement.line,
        severity: "error",
        message: "Incomplete predicate argument list",
        statement: statement.text,
      });
      continue;
    }
    const argTerms = args.map(parsePrologTerm);
    clauses.push({
      index: clauses.length,
      predicate: match[1],
      arity: args.length,
      args,
      argTerms,
      source: statement.text,
      original: statement.text,
      metta: ruleAt >= 0
        ? `; Prolog rule retained in PL view only: ${statement.text.replace(/\s+/g, " ")}`
        : prologTermToMetta(head),
      sourcePath,
      sourceLabel,
      line: statement.line,
      endLine: statement.endLine,
    });
  }

  const endingDiagnostic = sourceEndingDiagnostic(source);
  if (endingDiagnostic) diagnostics.push(endingDiagnostic);

  return {
    source,
    clauses,
    predicates: groupClausesByPredicate(clauses),
    diagnostics,
  };
}

export function parseSources(sources: SourceFile[]): Clause[] {
  let index = 0;
  return sources.flatMap((source) => parsePrologData(
    source.text,
    source.name,
    sourceBasename(source.name),
  ).clauses.map((clause) => ({ ...clause, index: index++ })));
}

function structuredClause(clause: Clause) {
  return {
    predicate: clause.predicate,
    arity: clause.arity,
    arguments: clause.args,
    argumentTerms: clause.argTerms.map(structuredTerm),
    source: {
      file: sourceBasename(clause.sourcePath),
      label: clause.sourceLabel,
      line: clause.line,
      endLine: clause.endLine,
    },
    prolog: clause.source,
    metta: clause.metta,
  };
}

function structuredTerm(term: PrologTerm): Record<string, unknown> {
  if (term.kind === "list") {
    return {
      kind: term.kind,
      source: term.source,
      items: term.items.map(structuredTerm),
      ...(term.tail ? { tail: structuredTerm(term.tail) } : {}),
    };
  }
  if (term.kind === "compound") {
    return {
      kind: term.kind,
      source: term.source,
      functor: term.functor,
      arguments: term.args.map(structuredTerm),
    };
  }
  return { kind: term.kind, source: term.source };
}

export function formatTerm(term: PrologTerm, syntax: ExplorerSyntax): string {
  if (syntax === "metta") return termToMetta(term);
  if (syntax === "json") return JSON.stringify(structuredTerm(term));
  return term.source;
}

export function formatClause(clause: Clause, syntax: ExplorerSyntax): string {
  if (syntax === "metta") return clause.metta;
  if (syntax === "json") return JSON.stringify(structuredClause(clause));
  return clause.source;
}

export function sourceTextForSyntax(
  source: SourceFile,
  clauses: Clause[],
  syntax: ExplorerSyntax,
): string {
  if (syntax === "prolog") return source.text;
  if (syntax === "metta") return clauses.map((clause) => clause.metta).join("\n");
  return JSON.stringify({
    source: {
      label: sourceBasename(source.label || source.name),
      file: sourceBasename(source.name),
      dialect: source.dialect || "prolog",
    },
    clauses: clauses.map(structuredClause),
  }, null, 2);
}
