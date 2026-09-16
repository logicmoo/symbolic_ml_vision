/** Browser-side indexing and display only. Python supplies every converted source and term. */
import {
  aggregateClauseArguments as originalAggregate, groupClausesByPredicate,
  type Clause, type ParsedProlog, type PrologTerm, type SourceFile, type ExplorerSyntax,
} from "./upstream/packages/omega_vision_ui/src/components/PrologClauseExplorerModel.ts";
export {
  autoGroupingArgument, clauseRowsKey, filterPredicateGroups, groupingArgument, groupClausesByPredicate,
  orderPredicateGroups, partitionKey, partitionClausesByArgument, partitionRowsKey, planExpandMost,
  shouldExposeTermTree, termContainsList, termPartCount,
} from "./upstream/packages/omega_vision_ui/src/components/PrologClauseExplorerModel.ts";
export type {
  SourceFile, ExplorerSyntax, ArgumentGroupingMode, Clause, PredicateGroup, PredicateOrder, PrologTerm,
} from "./upstream/packages/omega_vision_ui/src/components/PrologClauseExplorerModel.ts";

type Formats = Record<ExplorerSyntax, string>;
type FormattedClause = Clause & { formats: Formats; predicateFormats: { prolog: string; metta: string } };
type Analysis = {
  name: string; text: string; dialect: string; clauses: FormattedClause[];
  diagnostics: ParsedProlog["diagnostics"]; formats: Formats;
  viewNodes: Record<ExplorerSyntax, { key: string; text: string; start: number; end: number }[]>;
};
const prepared = new Map<string, Analysis>();
const pending = new Map<string, Promise<void>>();
const predicates = new Map<string, { prolog: string; metta: string }>();
const key = (name: string, text: string) => JSON.stringify([name, text]);

export function hasSources(sources: SourceFile[]): boolean {
  return sources.every(source => prepared.has(key(source.name, source.text)));
}

export function analysisFor(source: Pick<SourceFile, "name" | "text">): Analysis {
  const value = prepared.get(key(source.name, source.text));
  if (!value) throw new Error(`Python source analysis is not ready: ${source.name}`);
  return value;
}

export function prepareSources(sources: SourceFile[]): Promise<void> {
  const missing = sources.filter(source => !prepared.has(key(source.name, source.text)));
  if (!missing.length) return Promise.resolve();
  const requestKey = JSON.stringify(missing.map(source => [source.name, source.text]));
  const existing = pending.get(requestKey);
  if (existing) return existing;
  const request = (async () => {
    const response = await fetch("/omega_vision/api/v1/source-syntax", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources: missing }), cache: "no-store",
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `Source conversion failed (${response.status})`);
    if (value.schemaVersion !== 1 || !Array.isArray(value.sources) || value.sources.length !== missing.length) {
      throw new Error("Invalid Python source response");
    }
    value.sources.forEach((item: Analysis, index: number) => {
      if (item.name !== missing[index].name || item.text !== missing[index].text
          || !Array.isArray(item.clauses) || !Array.isArray(item.diagnostics)
          || !item.formats || !item.viewNodes) throw new Error("Source response identity is inconsistent");
      prepared.set(key(item.name, item.text), item);
      item.clauses.forEach(clause => predicates.set(clause.predicate, clause.predicateFormats));
    });
  })().finally(() => pending.delete(requestKey));
  pending.set(requestKey, request);
  return request;
}

export function parsePrologData(text: string, name = "", _label = name): ParsedProlog {
  const result = prepared.get(key(name, text));
  if (!result) return { source: text, clauses: [], predicates: [], diagnostics: [{
    line: 1, severity: "error", message: "Waiting for Python source validation.", statement: "",
  }] };
  return { source: text, clauses: result.clauses,
    predicates: groupClausesByPredicate(result.clauses), diagnostics: result.diagnostics };
}

export function parseSources(sources: SourceFile[]): Clause[] {
  let index = 0;
  return sources.flatMap(source => analysisFor(source).clauses.map(clause => ({ ...clause, index: index++ })));
}

function formatsOf(value: PrologTerm | Clause): Formats {
  if (!("formats" in value) || !value.formats || typeof value.formats !== "object") {
    throw new Error("Missing Python-produced term representations");
  }
  const formats = value.formats;
  if (!("prolog" in formats) || !("metta" in formats) || !("json" in formats)
      || typeof formats.prolog !== "string" || typeof formats.metta !== "string" || typeof formats.json !== "string") {
    throw new Error("Invalid Python-produced term representations");
  }
  return { prolog: formats.prolog, metta: formats.metta, json: formats.json };
}

export function formatTerm(term: PrologTerm, syntax: ExplorerSyntax): string {
  return formatsOf(term)[syntax];
}
export function formatClause(clause: Clause, syntax: ExplorerSyntax): string {
  return formatsOf(clause)[syntax];
}
export function sourceTextForSyntax(source: SourceFile, _clauses: Clause[], syntax: ExplorerSyntax): string {
  return analysisFor(source).formats[syntax];
}
export function aggregateClauseArguments(clauses: Clause[], syntax?: ExplorerSyntax): string[] {
  return originalAggregate(clauses).map((value, index) => !syntax || value === "_" || value === "â€¦" ? value
    : formatTerm(clauses[0].argTerms[index], syntax));
}
export function formatPredicate(value: string, syntax: ExplorerSyntax): string {
  const formats = predicates.get(value);
  if (!formats) throw new Error("Predicate has no Python representation");
  return syntax === "metta" ? formats.metta : formats.prolog;
}
export function formatBoundArgument(
  group: { clauses: Clause[] }, argument: { index: number; value: string }, syntax: ExplorerSyntax,
): string {
  const clause = group.clauses.find(item => item.args[argument.index] === argument.value);
  if (!clause) throw new Error("Argument partition is no longer present");
  return formatTerm(clause.argTerms[argument.index], syntax);
}
