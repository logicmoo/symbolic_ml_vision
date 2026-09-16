import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { ResourceSourceEditor } from "@app/components/ResourceSourceEditor";
import {
  aggregateClauseArguments,
  clauseRowsKey,
  filterPredicateGroups,
  formatClause,
  formatTerm,
  groupingArgument,
  groupClausesByPredicate,
  orderPredicateGroups,
  parsePrologData,
  parseSources,
  partitionKey,
  partitionClausesByArgument,
  partitionRowsKey,
  planExpandMost,
  shouldExposeTermTree,
  sourceTextForSyntax,
  type ArgumentGroupingMode,
  type Clause,
  type ExplorerSyntax,
  type PredicateGroup,
  type PredicateOrder,
  type PrologTerm,
  type SourceFile,
} from "./PrologClauseExplorerModel";

export * from "./PrologClauseExplorerModel";

export interface PortrayContext {
  clause: Clause;
  syntax: ExplorerSyntax;
  proposedHtml: ReactNode;
}

export interface PrologClauseExplorerProps {
  sources: SourceFile[];
  initialSource?: string;
  initialSyntax?: ExplorerSyntax;
  pageSize?: number;
  rootLimit?: number;
  portray?: (context: PortrayContext) => ReactNode;
  workspaceId?: string;
  onReloadSource?: (source: SourceFile) => Promise<void> | void;
  onSourcesChange?: (sources: SourceFile[]) => Promise<void> | void;
  onClose?: () => void;
  className?: string;
}

const CONTROL_SOURCE_PATH = "frontend/packages/omega_vision_ui/src/components/PrologClauseExplorer.tsx";
const CONTROL_STYLE_PATH = "frontend/packages/omega_vision_ui/src/styles/video_import.css";

function basename(path: string): string {
  return path.split(/[\\/]/).map((part) => part.trim()).filter(Boolean).at(-1) || path.trim();
}

function sourceDisplayName(source?: SourceFile): string {
  return basename(source?.label || source?.name || "");
}

function clauseIdentity(clause: Clause): string {
  return `${clause.sourcePath}\u0000${clause.index}\u0000${clause.line}\u0000${clause.predicate}/${clause.arity}`;
}

function displayClause(clause: Clause, syntax: ExplorerSyntax): string {
  return formatClause(clause, syntax).replace(/\s+/g, " ").trim();
}

function compactStructuredClause(
  clause: Clause,
  syntax: ExplorerSyntax,
  hiddenArguments: Set<number>,
): string {
  const arguments_ = clause.argTerms.map((term, index) =>
    hiddenArguments.has(index) ? "." : formatTerm(term, syntax)
  );
  if (syntax === "metta") {
    return clause.arity ? `(${clause.predicate} ${arguments_.join(" ")})` : `(${clause.predicate})`;
  }
  if (syntax === "json") {
    return JSON.stringify({
      predicate: clause.predicate,
      arity: clause.arity,
      arguments: arguments_,
    });
  }
  return clause.arity ? `${clause.predicate}(${arguments_.join(", ")})` : clause.predicate;
}

function shortValue(value: string, limit = 15): string {
  const compact = value.replace(/\s+/g, " ").trim();
  return compact.length > limit ? `${compact.slice(0, limit - 1)}…` : compact;
}

function groupShape(
  group: PredicateGroup,
  syntax: ExplorerSyntax,
): string {
  if (syntax === "json") return `${group.predicate}/${group.arity}`;
  if (!group.arity) return syntax === "metta" ? `(${group.predicate})` : `${group.predicate}`;
  const args = aggregateClauseArguments(group.clauses).map((value) => shortValue(value || "_"));
  return syntax === "metta"
    ? `(${group.predicate} ${args.join(" ")})`
    : `${group.predicate}(${args.join(", ")})`;
}

function partitionShape(
  group: PredicateGroup,
  argumentIndex: number,
  value: string,
  syntax: ExplorerSyntax,
): string {
  if (syntax === "json") {
    return JSON.stringify({
      predicate: group.predicate,
      arity: group.arity,
      partitionArgument: argumentIndex + 1,
      value,
    });
  }
  const arguments_ = aggregateClauseArguments(
    group.clauses.filter((clause) => (clause.args[argumentIndex] || "") === value),
  ).map((argument, index) =>
    index === argumentIndex ? shortValue(value, 34) : shortValue(argument || "_", 20)
  );
  return syntax === "metta"
    ? `(${group.predicate} ${arguments_.join(" ")})`
    : `${group.predicate}(${arguments_.join(", ")})`;
}

function selectionShape(
  group: PredicateGroup,
  syntax: ExplorerSyntax,
  argument?: { index: number; value: string },
): string {
  const arguments_ = Array.from({ length: group.arity }, (_, index) =>
    argument?.index === index ? argument.value : "_"
  );
  if (syntax === "json") {
    return JSON.stringify({
      predicate: group.predicate,
      arity: group.arity,
      arguments: arguments_,
    });
  }
  return syntax === "metta"
    ? `(${group.predicate}${arguments_.length ? ` ${arguments_.join(" ")}` : ""})`
    : group.arity
      ? `${group.predicate}(${arguments_.join(", ")})`
      : group.predicate;
}

function groupPartsMetadata(
  group: PredicateGroup,
  threshold: number,
  mode: ArgumentGroupingMode,
  pageSize: number,
): string {
  if (group.clauses.length <= threshold || group.arity === 0) return "direct";
  const argumentIndex = groupingArgument(group, mode, pageSize);
  if (argumentIndex < 0) return "paged";
  const parts = new Set(group.clauses.map((clause) => clause.args[argumentIndex] || "")).size;
  return `arg ${argumentIndex + 1} · ${parts} parts`;
}

function uniqueArguments(clauses: Clause[]): number {
  return new Set(clauses.flatMap((clause) => clause.args)).size;
}

function sourceLines(source: SourceFile | undefined): number {
  if (!source?.text) return 0;
  return source.text.split(/\r?\n/).length;
}

function sourceCodeHref(path: string): string {
  return `/workbench/repository/file?path=${encodeURIComponent(path)}`;
}

function isStructuredTerm(term: PrologTerm): boolean {
  return term.kind === "list" || term.kind === "compound";
}

function structuredSummary(terms: PrologTerm[]): string {
  const compounds = terms.filter((term) => term.kind === "compound").length;
  const lists = terms.filter((term) => term.kind === "list").length;
  if (compounds && !lists) return `${compounds} compound${compounds === 1 ? "" : "s"}`;
  if (lists && !compounds) return `${lists} list${lists === 1 ? "" : "s"}`;
  return `${terms.length} structured`;
}

function portrayClause(context: PortrayContext, custom?: (context: PortrayContext) => ReactNode) {
  if (custom) return custom(context);
  if (context.syntax !== "prolog" || typeof context.proposedHtml !== "string") {
    return context.proposedHtml;
  }
  const parts = context.proposedHtml.split(/(#[0-9a-fA-F]{3,8}\b)/g);
  if (parts.length === 1) return context.proposedHtml;
  return parts.map((part, index) =>
    /^#[0-9a-fA-F]{3,4}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(part)
      ? (
          <span className="pce-color-chip" key={`${part}:${index}`}>
            <span className="pce-color-bar" style={{ backgroundColor: part }} />
            {part}
          </span>
        )
      : part
  );
}

function useOverflowingText(text: string, enabled = true) {
  const ref = useRef<HTMLElement | null>(null);
  const [overflowing, setOverflowing] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || !enabled) {
      setOverflowing(false);
      return;
    }

    const measure = () => setOverflowing(element.scrollWidth > element.clientWidth + 1);
    const frame = window.requestAnimationFrame(measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    if (element.parentElement) observer?.observe(element.parentElement);
    void document.fonts?.ready.then(measure);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [enabled, text]);
  return { ref, overflowing };
}

function useCompactClause(clause: Clause, syntax: ExplorerSyntax) {
  const rendered = displayClause(clause, syntax);
  const ref = useRef<HTMLElement | null>(null);
  const [hiddenArguments, setHiddenArguments] = useState<Set<number>>(new Set());
  const structured = clause.argTerms
    .map((term, index) => ({ term, index, length: formatTerm(term, syntax).length }))
    .filter(({ term }) => isStructuredTerm(term))
    .sort((left, right) => right.length - left.length || left.index - right.index);

  useEffect(() => {
    const element = ref.current;
    if (!element || !structured.length) {
      setHiddenArguments(new Set());
      return;
    }
    const measure = () => {
      const fullWidth = element.scrollWidth;
      const availableWidth = element.clientWidth;
      if (fullWidth <= availableWidth + 1) {
        setHiddenArguments(new Set());
        return;
      }
      const next = new Set<number>();
      for (const candidate of structured) {
        next.add(candidate.index);
        const compact = compactStructuredClause(clause, syntax, next);
        const approximateWidth = fullWidth * (compact.length / Math.max(1, rendered.length));
        if (approximateWidth <= availableWidth) break;
      }
      setHiddenArguments((previous) => {
        if (
          previous.size === next.size
          && [...previous].every((index) => next.has(index))
        ) return previous;
        return next;
      });
    };
    const frame = window.requestAnimationFrame(measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    if (element.parentElement) observer?.observe(element.parentElement);
    void document.fonts?.ready.then(measure);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [clause, rendered, structured.length, syntax]);

  return {
    compact: compactStructuredClause(clause, syntax, hiddenArguments),
    hiddenArguments,
    ref,
  };
}

type TermTreeNodeProps = {
  term: PrologTerm;
  label: string;
  nodeId: string;
  syntax: ExplorerSyntax;
  pageSize: number;
  limits: Map<string, number>;
  expandedTerms: Set<string>;
  onToggle: (nodeId: string) => void;
  onMore: (nodeId: string) => void;
  onSelect: () => void;
};

function TermTreeNode({
  term,
  label,
  nodeId,
  syntax,
  pageSize,
  limits,
  expandedTerms,
  onToggle,
  onMore,
  onSelect,
}: TermTreeNodeProps) {
  const rendered = formatTerm(term, syntax).replace(/\s+/g, " ").trim();
  const structured = isStructuredTerm(term);
  const { ref, overflowing } = useOverflowingText(rendered, structured);
  const canExpand = shouldExposeTermTree(term, overflowing);
  const expanded = canExpand && expandedTerms.has(nodeId);
  const children = term.kind === "list"
    ? [
        ...term.items.map((item, index) => ({
          term: item,
          label: `[${index}]`,
          id: `${nodeId}.item:${index}`,
        })),
        ...(term.tail ? [{ term: term.tail, label: "tail", id: `${nodeId}.tail` }] : []),
      ]
    : term.kind === "compound"
      ? term.args.map((argument, index) => ({
          term: argument,
          label: `arg ${index + 1}`,
          id: `${nodeId}.arg:${index}`,
        }))
      : [];
  const childLimitKey = `${nodeId}\u0000items`;
  const visibleChildren = term.kind === "list"
    ? children.slice(0, limits.get(childLimitKey) ?? pageSize)
    : children;

  return (
    <div className={`pce-term-node is-${term.kind}`} role="treeitem" aria-expanded={canExpand ? expanded : undefined}>
      <div className="pce-term-row">
        {canExpand ? (
          <button
            type="button"
            tabIndex={-1}
            className="pce-term-chevron"
            aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`}
            aria-expanded={expanded}
            onClick={() => onToggle(nodeId)}
          >
            {expanded ? "▼" : "▶"}
          </button>
        ) : <span className="pce-term-chevron-spacer" aria-hidden="true" />}
        <button type="button" className="pce-term-value pce-tree-select" title={rendered} onClick={onSelect}>
          <span>{label}</span>
          <code ref={ref}>{rendered}</code>
          <em>{term.kind}</em>
        </button>
      </div>
      {expanded && (
        <div className="pce-term-children" role="group">
          {visibleChildren.map((child) => (
            <TermTreeNode
              key={child.id}
              term={child.term}
              label={child.label}
              nodeId={child.id}
              syntax={syntax}
              pageSize={pageSize}
              limits={limits}
              expandedTerms={expandedTerms}
              onToggle={onToggle}
              onMore={onMore}
              onSelect={onSelect}
            />
          ))}
          {visibleChildren.length < children.length && (
            <button type="button" className="pce-more" onClick={() => onMore(childLimitKey)}>
              <span aria-hidden="true">…</span>
              <b>{Math.min(pageSize, children.length - visibleChildren.length)}</b> more list items
              <em>{visibleChildren.length} of {children.length}</em>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

type ClauseTreeRowProps = {
  clause: Clause;
  syntax: ExplorerSyntax;
  selected: boolean;
  pageSize: number;
  limits: Map<string, number>;
  expandedTerms: Set<string>;
  portrayObjects: boolean;
  portray?: (context: PortrayContext) => ReactNode;
  onToggleTerm: (nodeId: string) => void;
  onMore: (nodeId: string) => void;
  onSelect: () => void;
};

function ClauseTreeRow({
  clause,
  syntax,
  selected,
  pageSize,
  limits,
  expandedTerms,
  portrayObjects,
  portray,
  onToggleTerm,
  onMore,
  onSelect,
}: ClauseTreeRowProps) {
  const rendered = displayClause(clause, syntax);
  const clauseId = clauseIdentity(clause);
  const nodeId = `${clauseId}\u0000arguments`;
  const { compact, hiddenArguments, ref } = useCompactClause(clause, syntax);
  const structuredTerms = clause.argTerms.filter((_, index) => hiddenArguments.has(index));
  const canExpand = hiddenArguments.size > 0;
  const expanded = canExpand && expandedTerms.has(nodeId);

  return (
    <div className={`pce-clause-node${selected ? " selected" : ""}`} role="treeitem" aria-expanded={canExpand ? expanded : undefined}>
      <div className="pce-clause-row">
        {canExpand ? (
          <button
            type="button"
            tabIndex={-1}
            className="pce-term-chevron"
            aria-label={`${expanded ? "Collapse" : "Expand"} clause arguments`}
            aria-expanded={expanded}
            onClick={() => onToggleTerm(nodeId)}
          >
            {expanded ? "▼" : "▶"}
          </button>
        ) : <span className="pce-term-chevron-spacer" aria-hidden="true" />}
        <button
          type="button"
          className="pce-clause-value pce-tree-select"
          title={`${clause.sourcePath}:L${clause.line}\n${rendered}`}
          onClick={onSelect}
        >
          <span aria-hidden="true">·</span>
          <span className="pce-clause-code">
            <code className="pce-clause-measure" ref={ref} aria-hidden="true">{rendered}</code>
            <code>{canExpand
              ? compact
              : portrayObjects
                ? portrayClause({ clause, syntax, proposedHtml: rendered }, portray)
                : rendered}</code>
          </span>
          <em>{canExpand ? structuredSummary(structuredTerms) : "fact"}</em>
        </button>
      </div>
      {expanded && (
        <div className="pce-term-children pce-clause-arguments" role="group">
          {clause.argTerms.flatMap((term, index) => hiddenArguments.has(index)
            ? [(
                <TermTreeNode
                  key={`${nodeId}.arg:${index}`}
                  term={term}
                  label={`arg ${index + 1}:`}
                  nodeId={`${nodeId}.arg:${index}`}
                  syntax={syntax}
                  pageSize={pageSize}
                  limits={limits}
                  expandedTerms={expandedTerms}
                  onToggle={onToggleTerm}
                  onMore={onMore}
                  onSelect={onSelect}
                />
              )]
            : [])}
        </div>
      )}
    </div>
  );
}

export function PrologClauseExplorer({
  sources,
  initialSource,
  initialSyntax = "prolog",
  pageSize: initialPageSize = 20,
  rootLimit: initialRootLimit = 30,
  portray,
  workspaceId,
  onReloadSource,
  onSourcesChange,
  onClose,
  className = "",
}: PrologClauseExplorerProps) {
  const sourceSignature = sources.map((source) => source.name).join("\u0000");
  const sourceContentSignature = sources
    .map((source) => [
      source.name,
      source.label || "",
      source.dialect || "prolog",
      source.readOnly === true ? "readonly" : "editable",
      source.text,
    ].join("\u0000"))
    .join("\u0001");
  const initialTextMap = () => new Map(sources.map((source) => [source.name, source.text]));
  const filterRef = useRef<HTMLInputElement | null>(null);
  const [syntax, setSyntax] = useState<ExplorerSyntax>(initialSyntax);
  const [currentFile, setCurrentFile] = useState(
    sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "",
  );
  const [fileFocus, setFileFocus] = useState(
    sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "",
  );
  const [onlyCurrent, setOnlyCurrent] = useState(false);
  const [matching, setMatching] = useState(false);
  const [selectedPredicate, setSelectedPredicate] = useState<string | null>(null);
  const [selectedArgument, setSelectedArgument] = useState<{
    groupKey: string;
    argumentIndex: number;
    value: string;
  } | null>(null);
  const [selectedClauseId, setSelectedClauseId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedTerms, setExpandedTerms] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [predicateOrder, setPredicateOrder] = useState<PredicateOrder>("file");
  const [argumentChoice, setArgumentChoice] = useState<ArgumentGroupingMode>("auto");
  const [treeThreshold, setTreeThreshold] = useState(10);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [rootLimit, setRootLimit] = useState(initialRootLimit);
  const [portrayObjects, setPortrayObjects] = useState(false);
  const [linkToFile, setLinkToFile] = useState(true);
  const [limits, setLimits] = useState<Map<string, number>>(new Map());
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorSourceName, setEditorSourceName] = useState(
    sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "",
  );
  const [sourceTreeVisibility, setSourceTreeVisibility] = useState<Map<string, boolean>>(
    () => new Map(sources.map((source) => [source.name, true])),
  );
  const [drafts, setDrafts] = useState<Map<string, string>>(initialTextMap);
  const [indexedTexts, setIndexedTexts] = useState<Map<string, string>>(initialTextMap);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState("");
  const [pendingRevealClause, setPendingRevealClause] = useState<number | null>(null);

  useEffect(() => {
    setCurrentFile((previous) => {
      if (sources.some((source) => source.name === previous)) return previous;
      return sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "";
    });
    setFileFocus((previous) => {
      if (sources.some((source) => source.name === previous)) return previous;
      return sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "";
    });
    setEditorSourceName((previous) => {
      if (sources.some((source) => source.name === previous)) return previous;
      return sources.find((source) => source.name === initialSource)?.name || sources[0]?.name || "";
    });
    setSourceTreeVisibility((previous) => new Map(
      sources.map((source) => [source.name, previous.get(source.name) ?? true]),
    ));
  }, [initialSource, sourceSignature, sources]);

  useEffect(() => {
    const next = new Map(sources.map((source) => [source.name, source.text]));
    setDrafts(next);
    setIndexedTexts(next);
    setEditorOpen(false);
  }, [sourceContentSignature]);

  useEffect(() => {
    const focusFilter = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        filterRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusFilter);
    return () => window.removeEventListener("keydown", focusFilter);
  }, []);

  const indexedSources = useMemo(() => sources.map((source) => ({
    ...source,
    text: indexedTexts.get(source.name) ?? source.text,
  })), [indexedTexts, sourceContentSignature]);
  const clauses = useMemo(() => parseSources(indexedSources), [indexedSources]);
  const parseDiagnostics = useMemo(
    () => indexedSources.flatMap((source) =>
      parsePrologData(source.text, source.name, sourceDisplayName(source)).diagnostics
        .map((diagnostic) => ({ ...diagnostic, source: source.name }))
    ),
    [indexedSources],
  );
  const visibleSources = useMemo(
    () => indexedSources.filter((source) => sourceTreeVisibility.get(source.name) !== false),
    [indexedSources, sourceTreeVisibility],
  );
  const visibleSourceNames = useMemo(
    () => new Set(visibleSources.map((source) => source.name)),
    [visibleSources],
  );
  useEffect(() => {
    if (!visibleSources.length || visibleSourceNames.has(currentFile)) return;
    setCurrentFile(visibleSources[0].name);
    setFileFocus(visibleSources[0].name);
  }, [currentFile, visibleSourceNames, visibleSources]);
  const scopeClauses = useMemo(() => clauses.filter((clause) =>
    visibleSourceNames.has(clause.sourcePath)
    && (!onlyCurrent || !fileFocus || clause.sourcePath === fileFocus)
  ), [clauses, fileFocus, onlyCurrent, visibleSourceNames]);
  const fileOrderedGroups = useMemo(
    () => groupClausesByPredicate(scopeClauses),
    [scopeClauses],
  );
  const orderedGroups = useMemo(
    () => orderPredicateGroups(fileOrderedGroups, predicateOrder),
    [fileOrderedGroups, predicateOrder],
  );
  const groups = useMemo(
    () => orderPredicateGroups(filterPredicateGroups(fileOrderedGroups, query), predicateOrder),
    [fileOrderedGroups, predicateOrder, query],
  );
  const selectedGroup = selectedPredicate
    ? fileOrderedGroups.find((group) => group.key === selectedPredicate)
    : undefined;
  const selectedClause = clauses.find((clause) => clauseIdentity(clause) === selectedClauseId) || null;
  const matchingClauses = selectedGroup
    ? selectedArgument?.groupKey === selectedGroup.key
      ? selectedGroup.clauses.filter((clause) =>
          (clause.args[selectedArgument.argumentIndex] || "") === selectedArgument.value
        )
      : selectedGroup.clauses
    : [];
  const selectedClauses = selectedClause ? [selectedClause] : matchingClauses;
  const currentSource = visibleSources.find((source) => source.name === currentFile) || visibleSources[0];
  const currentClauses = clauses.filter((clause) => clause.sourcePath === currentSource?.name);
  const matchingRows = matchingClauses;
  const currentText = currentSource
    ? sourceTextForSyntax(currentSource, currentClauses, syntax)
    : "";
  const editorLanguage = syntax === "prolog" ? "prolog" : syntax === "metta" ? "clojure" : "json";
  const editorExtension = syntax === "prolog" ? "pl" : syntax === "metta" ? "metta" : "json";
  const locationLine = selectedClause?.sourcePath === currentSource?.name
    ? selectedClause.line
    : undefined;
  const canEditSource = Boolean(
    currentSource
    && currentSource.readOnly !== true
    && syntax === "prolog"
    && onSourcesChange,
  );
  const canEditAnySource = Boolean(
    indexedSources.some((source) => source.readOnly !== true)
    && onSourcesChange,
  );
  const editorSource = indexedSources.find((source) => source.name === editorSourceName)
    || indexedSources.find((source) => source.readOnly !== true)
    || indexedSources[0];
  const editorClauses = clauses.filter((clause) => clause.sourcePath === editorSource?.name);
  const editorDraft = editorSource
    ? drafts.get(editorSource.name) ?? editorSource.text
    : "";
  const dirtySourceNames = new Set(indexedSources
    .filter((source) => (
      source.readOnly !== true
      && (drafts.get(source.name) ?? source.text) !== source.text
    ))
    .map((source) => source.name));
  const editorDiagnostics = editorSource
    ? parsePrologData(editorDraft, editorSource.name, basename(editorSource.name)).diagnostics
    : [];
  const hasDirtyErrors = indexedSources.some((source) =>
    dirtySourceNames.has(source.name)
    && parsePrologData(drafts.get(source.name) ?? source.text, source.name).diagnostics
      .some((diagnostic) => diagnostic.severity === "error")
  );

  useEffect(() => {
    if (selectedPredicate || !fileOrderedGroups.length) return;
    setSelectedPredicate(fileOrderedGroups[0].key);
  }, [fileOrderedGroups, selectedPredicate]);

  useEffect(() => {
    if (pendingRevealClause === null) return;
    const frame = window.requestAnimationFrame(() => {
      const row = document.querySelector<HTMLElement>(
        `.pce [data-clause-index="${pendingRevealClause}"]`,
      );
      row?.scrollIntoView({ block: "center", behavior: "smooth" });
      setPendingRevealClause(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [expanded, limits, pendingRevealClause, query]);

  useEffect(() => {
    const handleExplorerKeys = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target?.isContentEditable) {
        if (event.key === "Escape" && editorOpen) setEditorOpen(false);
        return;
      }
      if (event.key.toLowerCase() === "l" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        setLinkToFile((previous) => !previous);
      } else if (
        event.key.toLowerCase() === "e"
        && !event.ctrlKey
        && !event.metaKey
        && !event.altKey
        && canEditSource
        && currentSource
      ) {
        event.preventDefault();
        setEditorSourceName(currentSource.name);
        setEditorOpen(true);
      } else if (event.key === "Escape" && editorOpen) {
        event.preventDefault();
        setEditorOpen(false);
      }
    };
    window.addEventListener("keydown", handleExplorerKeys);
    return () => window.removeEventListener("keydown", handleExplorerKeys);
  }, [canEditSource, currentSource, editorOpen]);

  const toggleExpanded = (key: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const toggleTerm = (nodeId: string) => {
    setExpandedTerms((previous) => {
      const next = new Set(previous);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };
  const collapseAll = () => {
    setExpanded(new Set());
    setExpandedTerms(new Set());
  };
  const selectPredicate = (key: string) => {
    setSelectedPredicate(key);
    setSelectedArgument(null);
    setSelectedClauseId(null);
    setExpanded((previous) => new Set(previous).add(key));
    if (linkToFile) {
      const source = fileOrderedGroups.find((group) => group.key === key)?.clauses[0]?.sourcePath;
      if (source) {
        setCurrentFile(source);
        setFileFocus(source);
        setMatching(false);
      }
    }
  };
  const selectArgument = (group: PredicateGroup, argumentIndex: number, value: string) => {
    const key = partitionKey(group.key, argumentIndex, value);
    setSelectedPredicate(group.key);
    setSelectedArgument({ groupKey: group.key, argumentIndex, value });
    setSelectedClauseId(null);
    setExpanded((previous) => new Set(previous).add(group.key).add(key));
    if (linkToFile) {
      const source = group.clauses.find((clause) => clause.args[argumentIndex] === value)?.sourcePath;
      if (source) {
        setCurrentFile(source);
        setFileFocus(source);
        setMatching(false);
      }
    }
  };
  const selectSource = (source: string) => {
    setCurrentFile(source);
    setFileFocus(source);
    setMatching(false);
    setExpanded(new Set());
    setExpandedTerms(new Set());
    setLimits(new Map());
  };
  const selectClause = (clause: Clause) => {
    setSelectedPredicate(`${clause.predicate}/${clause.arity}`);
    setSelectedArgument(null);
    setSelectedClauseId(clauseIdentity(clause));
    if (linkToFile) {
      setCurrentFile(clause.sourcePath);
      setFileFocus(clause.sourcePath);
      setMatching(false);
    }
  };
  const selectMatchingClause = (clause: Clause) => {
    setSelectedPredicate(`${clause.predicate}/${clause.arity}`);
    setSelectedClauseId(clauseIdentity(clause));
    if (linkToFile) {
      setCurrentFile(clause.sourcePath);
      setFileFocus(clause.sourcePath);
      setMatching(false);
    }
  };
  const expandMost = (maximum = rootLimit) => {
    const plan = planExpandMost(
      orderedGroups,
      argumentChoice,
      treeThreshold,
      pageSize,
      maximum,
    );
    setExpanded(plan.expanded);
    setExpandedTerms(new Set());
    setLimits(plan.limits);
  };
  const showMore = (key: string) => {
    setLimits((previous) => {
      const next = new Map(previous);
      next.set(key, (previous.get(key) ?? pageSize) + pageSize);
      return next;
    });
  };
  const updateDraft = (sourceName: string, value: string) => {
    setDrafts((previous) => new Map(previous).set(sourceName, value));
  };
  const openEditor = () => {
    if (!currentSource || currentSource.readOnly === true || !onSourcesChange) return;
    setEditorSourceName(currentSource.name);
    setEditorOpen(true);
  };
  const applyEditorSources = async () => {
    if (!onSourcesChange) return;
    setSyncing(true);
    setSyncStatus("");
    try {
      const nextSources = indexedSources.map((source) => {
        if (source.readOnly === true || !dirtySourceNames.has(source.name)) return source;
        return { ...source, text: drafts.get(source.name) ?? source.text };
      });
      for (const source of nextSources.filter((candidate) => dirtySourceNames.has(candidate.name))) {
        const diagnostic = parsePrologData(source.text, source.name).diagnostics
          .find((candidate) => candidate.severity === "error");
        if (diagnostic) {
          throw new Error(
            `${basename(source.name)} L${diagnostic.line}: ${diagnostic.message}`,
          );
        }
      }
      const nextClauses = parseSources(nextSources);
      const target = nextClauses.find((clause) => clause.sourcePath === editorSource?.name)
        || nextClauses[0]
        || null;
      setIndexedTexts(new Map(nextSources.map((source) => [source.name, source.text])));
      await onSourcesChange(nextSources);
      setExpanded(target ? new Set([`${target.predicate}/${target.arity}`]) : new Set());
      setExpandedTerms(new Set());
      setLimits(new Map());
      setSelectedPredicate(target ? `${target.predicate}/${target.arity}` : null);
      setSelectedArgument(null);
      setSelectedClauseId(target ? clauseIdentity(target) : null);
      if (target) {
        setCurrentFile(target.sourcePath);
        setFileFocus(target.sourcePath);
        setPendingRevealClause(target.index);
      }
      setEditorOpen(false);
      setSyncStatus(`Applied and reindexed ${dirtySourceNames.size} source file${
        dirtySourceNames.size === 1 ? "" : "s"
      }.`);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setSyncStatus(`Apply failed: ${message}`);
      throw reason;
    } finally {
      setSyncing(false);
    }
  };
  const focusTreeClause = (clause: Clause) => {
    const group = fileOrderedGroups.find((candidate) =>
      candidate.key === `${clause.predicate}/${clause.arity}`
    );
    if (!group) return;
    const argumentIndex = group.clauses.length > treeThreshold
      ? groupingArgument(group, argumentChoice, pageSize)
      : -1;
    setQuery("");
    setSelectedPredicate(group.key);
    setSelectedArgument(null);
    setSelectedClauseId(clauseIdentity(clause));
    setCurrentFile(clause.sourcePath);
    setFileFocus(clause.sourcePath);
    setExpanded((previous) => {
      const next = new Set(previous).add(group.key);
      if (argumentIndex >= 0) {
        next.add(partitionKey(group.key, argumentIndex, clause.args[argumentIndex] || ""));
      }
      return next;
    });
    setLimits((previous) => {
      const next = new Map(previous);
      if (argumentIndex < 0) {
        const index = group.clauses.findIndex((candidate) =>
          clauseIdentity(candidate) === clauseIdentity(clause)
        );
        next.set(clauseRowsKey(group.key), Math.max(next.get(clauseRowsKey(group.key)) ?? pageSize, index + 1));
        return next;
      }
      const partitions = partitionClausesByArgument(group.clauses, argumentIndex);
      const value = clause.args[argumentIndex] || "";
      const partIndex = partitions.findIndex((partition) => partition.value === value);
      const part = partitions[partIndex];
      const factIndex = part?.clauses.findIndex((candidate) =>
        clauseIdentity(candidate) === clauseIdentity(clause)
      ) ?? -1;
      const rowsKey = partitionRowsKey(group.key, argumentIndex);
      const partKey = partitionKey(group.key, argumentIndex, value);
      next.set(rowsKey, Math.max(next.get(rowsKey) ?? pageSize, partIndex + 1));
      next.set(partKey, Math.max(next.get(partKey) ?? pageSize, factIndex + 1));
      return next;
    });
    setPendingRevealClause(clause.index);
  };
  const syncTree = async () => {
    if (!currentSource) throw new Error("No source file is active.");
    setSyncing(true);
    setSyncStatus("");
    try {
      const target = selectedClause || selectedClauses[0] || currentClauses[0] || null;
      if (currentSource.readOnly === true) {
        if (!onReloadSource) throw new Error("This generated source does not expose a backing-file reload.");
        await onReloadSource(currentSource);
      } else {
        const nextText = drafts.get(currentSource.name) ?? currentSource.text;
        const diagnostic = parsePrologData(nextText, currentSource.name).diagnostics
          .find((candidate) => candidate.severity === "error");
        if (diagnostic) {
          throw new Error(
            `${basename(currentSource.name)} L${diagnostic.line}: ${diagnostic.message}`,
          );
        }
        const nextSources = sources.map((source) =>
          source.name === currentSource.name ? { ...source, text: nextText } : source
        );
        setIndexedTexts((previous) => new Map(previous).set(currentSource.name, nextText));
        if (onSourcesChange) await onSourcesChange(nextSources);
      }
      if (target) focusTreeClause(target);
      const currentDiagnostics = parsePrologData(currentSource.text, currentSource.name).diagnostics;
      setSyncStatus(`${currentSource.readOnly ? "Reloaded" : "Indexed"} ${basename(
        currentSource.name
      )} and synchronized the predicate tree.${
        currentDiagnostics.length
          ? ` ${currentDiagnostics.length} unsupported statement${currentDiagnostics.length === 1 ? "" : "s"} not indexed.`
          : ""
      }`);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setSyncStatus(`Sync failed: ${message}`);
      throw reason;
    } finally {
      setSyncing(false);
    }
  };
  const setSyntaxAndStopEditing = (next: ExplorerSyntax) => setSyntax(next);
  const editTitle = canEditSource
    ? "Edit this source with the shared CodeMirror editor; Apply files reparses the tree."
    : currentSource?.readOnly
      ? "Completed transform result.pl files are generated read-only artifacts."
      : "Switch to Prolog syntax and provide a source-change handler to edit facts.";
  const conciseSource = sourceDisplayName(currentSource);
  const selectedArgumentGroup = selectedArgument
    ? fileOrderedGroups.find((group) => group.key === selectedArgument.groupKey)
    : undefined;
  const selectionTerm = selectedClause
    ? displayClause(selectedClause, syntax)
    : selectedArgument && selectedArgumentGroup
      ? selectionShape(
         selectedArgumentGroup,
         syntax,
         { index: selectedArgument.argumentIndex, value: selectedArgument.value },
       )
      : selectedGroup
       ? selectionShape(selectedGroup, syntax)
       : "No selection";
  const selectionHint = selectedClause
    ? `Exact source clause · L${selectedClause.line}`
    : selectedArgument
      ? `Argument ${selectedArgument.argumentIndex + 1} = ${shortValue(selectedArgument.value, 48)}`
      : selectedGroup
       ? `All clauses for ${selectedGroup.key}`
       : "Choose a predicate, argument partition, or clause";
  const selectionTitle = selectedClause
    ? `${selectedClause.sourcePath}:L${selectedClause.line}\n${displayClause(selectedClause, syntax)}`
    : selectedArgumentGroup?.clauses[0]?.sourcePath || "";
  const renderClauseRows = (nodeKey: string, rows: Clause[]) => {
    const visibleCount = Math.min(limits.get(nodeKey) ?? pageSize, rows.length);
    return (
      <>
        {rows.slice(0, visibleCount).map((clause) => (
          <div key={clauseIdentity(clause)} data-clause-index={clause.index}>
            <ClauseTreeRow
              clause={clause}
              syntax={syntax}
              pageSize={pageSize}
              limits={limits}
              selected={Boolean(
                selectedClause
                && clauseIdentity(selectedClause) === clauseIdentity(clause)
              )}
              expandedTerms={expandedTerms}
              portrayObjects={portrayObjects}
              portray={portray}
              onToggleTerm={toggleTerm}
              onMore={showMore}
              onSelect={() => selectClause(clause)}
            />
          </div>
        ))}
        {visibleCount < rows.length && (
          <button
            type="button"
            className="pce-more"
            onClick={() => showMore(nodeKey)}
          >
            <span aria-hidden="true">…</span>
            <b>{Math.min(pageSize, rows.length - visibleCount)}</b> more clauses
            <em>{visibleCount} of {rows.length}</em>
          </button>
        )}
      </>
    );
  };
  const renderGroupChildren = (group: PredicateGroup) => {
    const fullGroup = fileOrderedGroups.find((candidate) => candidate.key === group.key) || group;
    const argumentIndex = group.clauses.length > treeThreshold
      ? groupingArgument(group, argumentChoice, pageSize)
      : -1;
    if (argumentIndex < 0) return renderClauseRows(clauseRowsKey(group.key), group.clauses);

    const partitions = partitionClausesByArgument(group.clauses, argumentIndex);
    const partsKey = partitionRowsKey(group.key, argumentIndex);
    const visibleParts = Math.min(limits.get(partsKey) ?? pageSize, partitions.length);
    return (
      <>
        {partitions.slice(0, visibleParts).map((partition) => {
          const partKey = partitionKey(group.key, argumentIndex, partition.value);
          const isExpanded = expanded.has(partKey);
          const firstClause = partition.clauses[0];
          return (
            <div className="pce-partition" key={partKey}>
              <div className={`pce-partition-row${
              selectedArgument?.groupKey === group.key
              && selectedArgument.argumentIndex === argumentIndex
              && selectedArgument.value === partition.value ? " selected" : ""
              }`}>
              <button
                type="button"
                tabIndex={-1}
                className="pce-chevron"
                aria-label={`${isExpanded ? "Collapse" : "Expand"} argument partition`}
                aria-expanded={isExpanded}
                onClick={() => toggleExpanded(partKey)}
              >
                {isExpanded ? "▼" : "▶"}
              </button>
              <button
                type="button"
                className="pce-partition-select pce-tree-select"
                title={`${firstClause.sourcePath}:L${firstClause.line}`}
                onClick={() => selectArgument(fullGroup, argumentIndex, partition.value)}
              >
                <code>{partitionShape(group, argumentIndex, partition.value, syntax)}</code>
                <span><b>{partition.clauses.length}</b> arg {argumentIndex + 1}</span>
              </button>
              </div>
              {isExpanded && (
              <div className="pce-partition-children">
                {renderClauseRows(partKey, partition.clauses)}
              </div>
              )}
            </div>
          );
        })}
        {visibleParts < partitions.length && (
          <button type="button" className="pce-more" onClick={() => showMore(partsKey)}>
            <span aria-hidden="true">…</span>
            <b>{Math.min(pageSize, partitions.length - visibleParts)}</b> more argument parts
            <em>{visibleParts} of {partitions.length}</em>
          </button>
        )}
      </>
    );
  };
  const handleTreeKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>(".pce-tree-select");
    if (!target) return;
    event.preventDefault();
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>(".pce-tree-select:not(:disabled)"),
    );
    const index = buttons.indexOf(target);
    if (event.key === "ArrowUp") {
      buttons[Math.max(0, index - 1)]?.focus();
      return;
    }
    if (event.key === "ArrowDown") {
      buttons[Math.min(buttons.length - 1, index + 1)]?.focus();
      return;
    }
    const row = target.closest<HTMLElement>(
      ".pce-predicate-row,.pce-partition-row,.pce-clause-row,.pce-term-row",
    );
    const twisty = row?.querySelector<HTMLButtonElement>(
      ":scope > .pce-chevron,:scope > .pce-term-chevron",
    );
    if (event.key === "ArrowRight") {
      if (twisty && twisty.getAttribute("aria-expanded") === "false") twisty.click();
      else buttons[Math.min(buttons.length - 1, index + 1)]?.focus();
      return;
    }
    if (twisty && twisty.getAttribute("aria-expanded") === "true") {
      twisty.click();
      return;
    }
    const rowDepth = (candidate: HTMLElement | null) => {
      let depth = 0;
      let ancestor = candidate?.parentElement || null;
      while (ancestor && ancestor !== event.currentTarget) {
        if (
          ancestor.classList.contains("pce-children")
          || ancestor.classList.contains("pce-partition-children")
          || ancestor.classList.contains("pce-term-children")
        ) depth += 1;
        ancestor = ancestor.parentElement;
      }
      return depth;
    };
    const currentDepth = rowDepth(row);
    for (let previous = index - 1; previous >= 0; previous -= 1) {
      const previousRow = buttons[previous].closest<HTMLElement>(
        ".pce-predicate-row,.pce-partition-row,.pce-clause-row,.pce-term-row",
      );
      if (
        previousRow
        && rowDepth(previousRow) < currentDepth
      ) {
        buttons[previous].focus();
        return;
      }
    }
  };

  return (
    <section className={`pce ${className}`.trim()}>
      <header className="pce-titlebar">
        <span className="pce-terminal-icon" aria-hidden="true">?-</span>
        <b>Clause Explorer</b>
        <span className="pce-title-divider" />
        <span title={currentSource?.name}>{conciseSource || "no source"} <i>/</i> filesystem</span>
        <nav className="pce-code-links" aria-label="Clause Explorer implementation">
          <a href={sourceCodeHref(CONTROL_SOURCE_PATH)} target="_blank" rel="noreferrer">TSX control</a>
          <a href={sourceCodeHref(CONTROL_STYLE_PATH)} target="_blank" rel="noreferrer">CSS</a>
        </nav>
        <label className="pce-portray" title="Render hexadecimal color values with a visual color chip">
          <input
            type="checkbox"
            checked={portrayObjects}
            onChange={(event) => setPortrayObjects(event.target.checked)}
          />
          Portray objects
        </label>
        <select
          value={syntax}
          aria-label="Clause representation"
          onChange={(event) => setSyntaxAndStopEditing(event.target.value as ExplorerSyntax)}
        >
          <option value="prolog">Prolog syntax</option>
          <option value="metta">MeTTa syntax</option>
          <option value="json">JSON syntax</option>
        </select>
        <button type="button" onClick={collapseAll}>Collapse all</button>
        <button type="button" onClick={() => expandMost()} title="Expand each predicate without exceeding its row budget">
          Expand most
        </button>
        <button
          type="button"
          className="pce-primary-action"
          disabled={!canEditSource}
          title={editTitle}
          onClick={openEditor}
        >
          Edit facts
        </button>
        {onClose && (
          <button type="button" className="pce-close" aria-label="Close Clause Explorer" onClick={onClose}>x</button>
        )}
      </header>

      <div className="pce-filterbar">
        <label className="pce-filter">
          <span aria-hidden="true">⌕</span>
          <input
            ref={filterRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter predicates, atoms, or clause text..."
            aria-label="Filter predicates, atoms, or clause text"
          />
          <kbd>Ctrl K</kbd>
        </label>
        <select
          value={predicateOrder}
          aria-label="Predicate tree order"
          title="File appearance keeps source order; Alphabetical sorts predicate/arity keys; Most clauses first sorts matching clause counts descending, with alphabetical ties."
          onChange={(event) => {
            setPredicateOrder(event.target.value as PredicateOrder);
            setExpanded(new Set());
            setExpandedTerms(new Set());
            setLimits(new Map());
          }}
        >
          <option value="file">File appearance</option>
          <option value="alphabetical">Alphabetical</option>
          <option value="count">Most clauses first</option>
        </select>
        <select
          value={argumentChoice}
          aria-label="Predicate argument grouping"
          title="Choose the argument used to partition large predicate groups."
          onChange={(event) => setArgumentChoice(event.target.value as ArgumentGroupingMode)}
        >
          <option value="auto">Auto: best argument</option>
          <option value="first">Always argument 1</option>
          <option value="second">Always argument 2</option>
          <option value="none">Never group by argument</option>
        </select>
        <label className="pce-number-control" title="Predicates above this count are partitioned by the selected argument strategy.">
          <span>Tree when over</span>
          <input
            type="number"
            min={1}
            max={999}
            value={treeThreshold}
            aria-label="Tree when over"
            onChange={(event) => setTreeThreshold(Math.max(1, Number(event.target.value) || 1))}
          />
        </label>
        <label className="pce-number-control">
          <span>Max parts / page</span>
          <input
            type="number"
            min={1}
            max={500}
            value={pageSize}
            aria-label="Max parts per page"
            onChange={(event) => {
              setPageSize(Math.max(1, Number(event.target.value) || 1));
              setLimits(new Map());
            }}
          />
        </label>
        <label className="pce-number-control">
          <span>Root max</span>
          <input
            type="number"
            min={1}
            max={999}
            value={rootLimit}
            aria-label="Root max"
            onChange={(event) => {
              const next = Math.max(1, Number(event.target.value) || 1);
              setRootLimit(next);
              expandMost(next);
            }}
          />
        </label>
        <span className="pce-summary">
          {scopeClauses.length} clauses · {fileOrderedGroups.length} predicates · {
            onlyCurrent && fileFocus
              ? basename(fileFocus)
              : "all files"
          }
        </span>
      </div>

      <div className="pce-workspace">
        <section className="pce-tree-pane">
          <header className="pce-tree-toolbar">
            <b>Predicate tree</b>
            <button
              type="button"
              aria-pressed={onlyCurrent}
              title="Restrict the tree to the selected source file"
              onClick={() => {
                setOnlyCurrent((previous) => !previous);
                setExpanded(new Set());
                setExpandedTerms(new Set());
                setLimits(new Map());
              }}
            >
              ▤ Only current file
            </button>
            <button
              type="button"
              className={linkToFile ? "active" : ""}
              aria-pressed={linkToFile}
              title="Link tree selections to their backing source file (L)"
              onClick={() => setLinkToFile((previous) => !previous)}
            >
              →▤ Link to file
            </button>
            <span>predicate / arity</span>
          </header>
          <nav className="pce-tree" aria-label="Predicate and arity tree" onKeyDown={handleTreeKeyDown}>
            {groups.map((group) => {
              const fullGroup = fileOrderedGroups.find((candidate) => candidate.key === group.key) || group;
              const isExpanded = expanded.has(group.key);
              const rootExpandable = group.clauses.length > 1
                || Boolean(group.clauses[0]?.argTerms.some(isStructuredTerm));
              const selected = selectedPredicate === group.key
                && !selectedArgument
                && !selectedClause;
              return (
                <div className="pce-group" key={group.key}>
                  <div className={`pce-predicate-row${selected ? " selected" : ""}`}>
                    {rootExpandable ? (
                      <button
                        type="button"
                        tabIndex={-1}
                        className="pce-chevron"
                        aria-label={`${isExpanded ? "Collapse" : "Expand"} ${group.key}`}
                        aria-expanded={isExpanded}
                        onClick={() => toggleExpanded(group.key)}
                      >
                        {isExpanded ? "▼" : "▶"}
                      </button>
                    ) : <span className="pce-chevron leaf" aria-hidden="true">·</span>}
                    <button
                      type="button"
                      className="pce-predicate pce-tree-select"
                      aria-pressed={selected}
                      title={fullGroup.clauses[0]?.sourcePath}
                      onClick={() => selectPredicate(group.key)}
                    >
                      <code>{groupShape(group, syntax)}</code>
                      <span className="pce-predicate-metadata">
                        <b>{group.clauses.length}</b>
                        <em>{groupPartsMetadata(group, treeThreshold, argumentChoice, pageSize)}</em>
                      </span>
                    </button>
                  </div>
                  {rootExpandable && isExpanded && (
                    <div className="pce-children">
                      {renderGroupChildren(group)}
                    </div>
                  )}
                </div>
              );
            })}
            {groups.length === 0 && <div className="pce-empty">No predicate heads match the current filter.</div>}
          </nav>
        </section>

        <div className="pce-divider" aria-hidden="true" />

        <section className="pce-source-pane">
          <header className="pce-source-toolbar">
            <div className="pce-tabs" role="tablist" aria-label="Loaded symbolic source files">
              <button
                type="button"
                role="tab"
                aria-selected={matching}
                className={matching ? "active" : ""}
                onClick={() => {
                  setFileFocus("");
                  setMatching(true);
                }}
              >
                Matching clauses
              </button>
              {visibleSources.map((source) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={!matching && currentFile === source.name}
                  className={[
                    !matching && currentFile === source.name ? "active" : "",
                    dirtySourceNames.has(source.name) ? "dirty" : "",
                  ].filter(Boolean).join(" ")}
                  key={source.name}
                  title={source.name}
                  onClick={() => selectSource(source.name)}
                >
                  {sourceDisplayName(source)}
                </button>
              ))}
            </div>
            {!matching && (
              <>
                <button type="button" disabled={!canEditSource} title={editTitle} onClick={openEditor}>
                  Edit source
                </button>
                <button
                  type="button"
                  disabled={!currentSource || syncing}
                  title={currentSource?.name}
                  onClick={() => void syncTree().catch(() => undefined)}
                >
                  {syncing ? "Syncing..." : "Sync tree"}
                </button>
              </>
            )}
            <span>{matching ? `${matchingRows.length} shown` : `${sourceLines(currentSource)} lines`}</span>
          </header>

          <div className="pce-source-main">
            <div className="pce-source-heading" title={currentSource?.name}>
              <b>{matching ? "Matching clauses" : conciseSource}</b>
              <span>
                {matching
                  ? `${matchingRows.length} matching`
                  : `${syntax === "prolog" ? "Prolog" : syntax === "metta" ? "MeTTa" : "JSON"} view · ${sourceLines(currentSource)} lines`}
              </span>
            </div>
            {matching ? (
              <>
                <div className="pce-matches" role="list" aria-label="Matching clauses across sources">
                  {matchingRows.map((clause) => {
                    const rendered = displayClause(clause, syntax);
                    return (
                      <button
                        type="button"
                        role="listitem"
                        key={clauseIdentity(clause)}
                        title={`${clause.sourcePath}:L${clause.line}\n${rendered}`}
                        onClick={() => selectMatchingClause(clause)}
                      >
                        <code>{portrayObjects
                          ? portrayClause({ clause, syntax, proposedHtml: rendered }, portray)
                          : rendered}</code>
                        <em>L{clause.line}</em>
                      </button>
                    );
                  })}
                  {!selectedPredicate && (
                    <div className="pce-empty">Select a predicate to show its clauses across source files.</div>
                  )}
                  {selectedPredicate && matchingRows.length === 0 && (
                    <div className="pce-empty">No clauses remain under the current file scope.</div>
                  )}
                </div>
              </>
            ) : (
              <div className="pce-source-editor">
                <ResourceSourceEditor
                  key={`${currentSource?.name || "__empty__"}:${syntax}`}
                  value={currentText}
                  onChange={() => undefined}
                  label={`${syntax === "prolog" ? "Prolog" : syntax === "metta" ? "MeTTa" : "JSON"} clause source`}
                  sourcePath={syntax === "prolog"
                    ? currentSource?.name || "source.pl"
                    : `${currentSource?.name || "source"}.${editorExtension}`}
                  showEnablement={false}
                  contentReadOnly
                  defaultFormat="text"
                  defaultTextLang={editorLanguage}
                  revealLine={syntax === "prolog" ? locationLine : undefined}
                  fileControlsContent={currentSource?.text || ""}
                  fileControls={currentSource && workspaceId && !matching && syntax === "prolog" ? {
                    currentWorkspaceId: workspaceId,
                    workspaceId,
                    originWorkspaceId: workspaceId,
                    relativePath: currentSource.name,
                    variant: "compact",
                    openHref: currentSource.sourceUrl,
                    allowLoadDifferent: false,
                    dirty: false,
                    readOnly: currentSource.readOnly === true,
                    onSave: async () => {
                      if (currentSource.readOnly === true) {
                        throw new Error("Completed transform sources are generated read-only artifacts.");
                      }
                      await syncTree();
                    },
                    onLoad: () => syncTree(),
                  } : undefined}
                />
              </div>
            )}
          </div>

          <section className="pce-selection">
            <div className="pce-selection-detail">
              <span>Selection</span>
              <b title={selectionTitle}>{selectionTerm}</b>
              <small title={selectionTitle}>{selectionHint}</small>
            </div>
            <div className="pce-selection-stat"><b>{selectedClauses.length}</b><span>clauses</span></div>
            <div className="pce-selection-stat"><b>{fileOrderedGroups.length}</b><span>predicates</span></div>
            <div className="pce-selection-stat"><b>{selectedClauses.length ? uniqueArguments(selectedClauses) : "—"}</b><span>unique atoms</span></div>
          </section>
        </section>
      </div>

      <footer className="pce-footer">
        <span>
          <b>● indexed</b>{" "}
          <em
            className={syncStatus.startsWith("Sync failed")
              ? "error"
              : parseDiagnostics.length ? "warning" : ""}
            title={parseDiagnostics[0]
              ? `${parseDiagnostics[0].source}:L${parseDiagnostics[0].line} ${parseDiagnostics[0].message}`
              : undefined}
          >
            {syncStatus || `Parsed ${clauses.length} clauses from ${indexedSources.length} real file${
              indexedSources.length === 1 ? "" : "s"
            }${parseDiagnostics.length
              ? ` · ${parseDiagnostics.length} unsupported statement${parseDiagnostics.length === 1 ? "" : "s"} not indexed`
              : ""}`}
          </em>
        </span>
        <span>↑↓ navigate · ←→ collapse/expand · Enter select</span>
      </footer>

      {editorOpen && editorSource && (
        <dialog
          className="pce-editor-dialog"
          open
          aria-labelledby="pce-editor-title"
          onKeyDownCapture={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
              event.preventDefault();
              void applyEditorSources().catch(() => undefined);
            }
          }}
        >
          <header>
            <b id="pce-editor-title">Edit Prolog source</b>
            <button
              type="button"
              className={sourceTreeVisibility.get(editorSource.name) !== false ? "active" : ""}
              aria-pressed={sourceTreeVisibility.get(editorSource.name) !== false}
              title={`${editorSource.name}\nKeep this file linked into the predicate tree`}
              onClick={() => setSourceTreeVisibility((previous) => {
                const next = new Map(previous);
                next.set(editorSource.name, previous.get(editorSource.name) === false);
                return next;
              })}
            >
              ▤→ Link to tree
            </button>
          </header>
          <nav role="tablist" aria-label="Editable source files">
            {indexedSources.map((source) => (
              <button
                type="button"
                role="tab"
                aria-selected={source.name === editorSource.name}
                className={source.name === editorSource.name ? "active" : ""}
                key={source.name}
                title={source.name}
                onClick={() => setEditorSourceName(source.name)}
              >
                {sourceDisplayName(source)}
                {dirtySourceNames.has(source.name) ? " *" : ""}
              </button>
            ))}
          </nav>
          <div className="pce-editor-dialog-body">
            <ResourceSourceEditor
              key={`edit:${editorSource.name}`}
              value={editorDraft}
              onChange={(value) => updateDraft(editorSource.name, value)}
              label={`Edit ${sourceDisplayName(editorSource)}`}
              sourcePath={editorSource.name}
              showEnablement={false}
              contentReadOnly={editorSource.readOnly === true || !onSourcesChange}
              defaultFormat="text"
              defaultTextLang="prolog"
              revealLine={selectedClause?.sourcePath === editorSource.name ? selectedClause.line : undefined}
            />
          </div>
          <div className="pce-editor-dialog-status">
            <span className={editorDiagnostics.some((diagnostic) => diagnostic.severity === "error")
              ? "error"
              : editorDiagnostics.length ? "warning" : "ok"}>
              {editorSource.readOnly === true
                ? "Generated read-only source"
                : editorDiagnostics.length
                  ? `L${editorDiagnostics[0].line}: ${editorDiagnostics[0].message}`
                  : `${editorClauses.length} parsed clauses · syntax looks good`}
            </span>
            <span>Ctrl+S applies files</span>
          </div>
          <footer>
            <button type="button" onClick={() => setEditorOpen(false)}>Cancel</button>
            <button
              type="button"
              className="pce-primary-action"
              disabled={!canEditAnySource || dirtySourceNames.size === 0 || hasDirtyErrors || syncing}
              onClick={() => void applyEditorSources().catch(() => undefined)}
            >
              {syncing ? "Applying..." : "Apply files"}
            </button>
          </footer>
        </dialog>
      )}
    </section>
  );
}

export default PrologClauseExplorer;
