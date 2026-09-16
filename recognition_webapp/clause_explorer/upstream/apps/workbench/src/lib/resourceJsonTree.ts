import { EditorState } from "@codemirror/state";
import { ensureSyntaxTree, foldEffect, foldedRanges, foldState, unfoldEffect } from "@codemirror/language";
import { json } from "@codemirror/lang-json";
import type { SyntaxNode } from "@lezer/common";

export type JsonTreeNode = { path: string; from: number; to: number; fold?: { from: number; to: number } };
export function jsonChildPath(path: string, key: string | number): string {
  return typeof key === "number" ? `${path}[${key}]`
    : /^[A-Za-z_$][\w$]*$/.test(key) ? `${path}.${key}` : `${path}[${JSON.stringify(key)}]`;
}
export function jsonPathTokens(path: string): (string | number)[] {
  if (!path.startsWith("$")) throw new Error("Invalid JSON tree path");
  const tokens: (string | number)[] = [];
  const pattern = /\.([A-Za-z_$][\w$]*)|\[((?:0|[1-9]\d*)|"(?:[^"\\]|\\.)*")\]/gy;
  pattern.lastIndex = 1;
  while (pattern.lastIndex < path.length) {
    const match = pattern.exec(path);
    if (!match) throw new Error("Invalid JSON tree path");
    tokens.push(match[1] ?? JSON.parse(match[2]));
  }
  return tokens;
}
export function jsonTreeNodes(state: EditorState): JsonTreeNode[] | null {
  const tree = ensureSyntaxTree(state, state.doc.length, 100);
  if (!tree) return null;
  let valid = true;
  tree.iterate({ enter(node) { if (node.type.isError) valid = false; } });
  if (!valid) return null;
  try { JSON.parse(state.doc.toString()); } catch { return null; }
  const nodes: JsonTreeNode[] = [];
  const visit = (node: SyntaxNode, path: string) => {
    const container = node.name === "Object" || node.name === "Array";
    const from = node.from + 1, to = node.to - 1;
    nodes.push({ path, from: node.from, to: node.to,
      ...(container ? { fold: from < to ? { from, to } : { from: node.from, to: node.to } } : {}) });
    if (node.name === "Object") {
      for (let child = node.firstChild; child; child = child.nextSibling) {
        if (child.name !== "Property") continue;
        const name = child.getChild("PropertyName"), value = child.lastChild;
        if (name && value) visit(value, jsonChildPath(path, JSON.parse(state.sliceDoc(name.from, name.to))));
      }
    } else if (node.name === "Array") {
      let index = 0;
      for (let child = node.firstChild; child; child = child.nextSibling) {
        if (!["[", "]", ","].includes(child.name)) visit(child, jsonChildPath(path, index++));
      }
    }
  };
  const root = tree.topNode.firstChild;
  if (root) visit(root, "$");
  return nodes;
}
export function expandedJsonPaths(state: EditorState): Set<string> {
  const closed = new Set<string>();
  foldedRanges(state).between(0, state.doc.length, (from, to) => { closed.add(`${from}:${to}`); });
  return new Set((jsonTreeNodes(state) ?? []).filter(node => node.fold && !closed.has(`${node.fold.from}:${node.fold.to}`)).map(node => node.path));
}
export function changeJsonFolds(state: EditorState, path: string, expand: boolean, descendants = true, childrenOnly = false): EditorState {
  const nodes = jsonTreeNodes(state) ?? [];
  const branch = nodes.find(node => node.path === path);
  if (!branch?.fold) return state;
  const effects = nodes.filter(node => node.fold && (childrenOnly ? node.path !== path : true)
    && (descendants ? node.from >= branch.from && node.to <= branch.to : node.path === path))
    .map(node => (expand ? unfoldEffect : foldEffect).of(node.fold!));
  return state.update({ effects }).state;
}
export function createJsonTreeState(doc: string): EditorState {
  return EditorState.create({ doc, extensions: [json(), foldState] });
}
export function updateJsonTreeDocument(state: EditorState, doc: string): EditorState {
  if (state.doc.toString() === doc) return state;
  const expanded = expandedJsonPaths(state), previous = jsonTreeNodes(state) ?? [];
  const next = createJsonTreeState(doc);
  const closed = new Set(previous.filter(node => node.fold && !expanded.has(node.path)).map(node => node.path));
  return next.update({ effects: (jsonTreeNodes(next) ?? [])
    .filter(node => node.fold && closed.has(node.path)).map(node => foldEffect.of(node.fold!)) }).state;
}
export function restoreJsonFolds(target: EditorState, source: EditorState) {
  const effects: ReturnType<typeof foldEffect.of>[] = [];
  foldedRanges(target).between(0, target.doc.length, (from, to) => { effects.push(unfoldEffect.of({ from, to })); });
  if (target.doc.toString() === source.doc.toString()) {
    const ranges: Array<{ from: number; to: number }> = [];
    foldedRanges(source).between(0, source.doc.length, (from, to) => { ranges.push({ from, to }); });
    effects.push(...ranges.sort((a, b) => a.from - b.from || a.to - b.to).map(range => foldEffect.of(range)));
    return effects;
  }
  const expanded = expandedJsonPaths(source);
  const closed = new Set((jsonTreeNodes(source) ?? []).filter(node => node.fold && !expanded.has(node.path)).map(node => node.path));
  for (const node of jsonTreeNodes(target) ?? []) {
    if (node.fold && closed.has(node.path)) effects.push(foldEffect.of(node.fold));
  }
  return effects;
}
export function jsonBranchAt(state: EditorState, position: number): string {
  return (jsonTreeNodes(state) ?? []).filter(node => node.fold && node.from <= position && position <= node.to)
    .sort((a, b) => (a.to - a.from) - (b.to - b.from))[0]?.path ?? "$";
}
