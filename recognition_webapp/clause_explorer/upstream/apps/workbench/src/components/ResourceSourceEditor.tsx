import { useEffect, useMemo, useRef, useState } from "react";
import { useContextReset } from "../lib/useContextReset";
import type { CSSProperties, ReactNode } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { RangeSet, type Extension } from "@codemirror/state";
import { foldedRanges } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { json } from "@codemirror/lang-json";
import { createJsonTreeState, updateJsonTreeDocument, jsonTreeNodes, expandedJsonPaths, changeJsonFolds, restoreJsonFolds, jsonChildPath, jsonPathTokens, jsonBranchAt } from "../lib/resourceJsonTree";
import { markdown } from "@codemirror/lang-markdown";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { StreamLanguage } from "@codemirror/language";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { yaml } from "@codemirror/legacy-modes/mode/yaml";
import { toml } from "@codemirror/legacy-modes/mode/toml";
import { xml } from "@codemirror/legacy-modes/mode/xml";
import { c, cpp, java, csharp, scala, kotlin, dart, objectiveC } from "@codemirror/legacy-modes/mode/clike";
import { rust } from "@codemirror/legacy-modes/mode/rust";
import { go } from "@codemirror/legacy-modes/mode/go";
import { ruby } from "@codemirror/legacy-modes/mode/ruby";
import { perl } from "@codemirror/legacy-modes/mode/perl";
import { powerShell } from "@codemirror/legacy-modes/mode/powershell";
import { swift } from "@codemirror/legacy-modes/mode/swift";
import { r } from "@codemirror/legacy-modes/mode/r";
import { lua } from "@codemirror/legacy-modes/mode/lua";
import { haskell } from "@codemirror/legacy-modes/mode/haskell";
import { groovy } from "@codemirror/legacy-modes/mode/groovy";
import { julia } from "@codemirror/legacy-modes/mode/julia";
import { clojure } from "@codemirror/legacy-modes/mode/clojure";
import { scheme } from "@codemirror/legacy-modes/mode/scheme";
import { erlang } from "@codemirror/legacy-modes/mode/erlang";
import { elm } from "@codemirror/legacy-modes/mode/elm";
import { coffeeScript } from "@codemirror/legacy-modes/mode/coffeescript";
import { sass } from "@codemirror/legacy-modes/mode/sass";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import { cmake } from "@codemirror/legacy-modes/mode/cmake";
import { nginx } from "@codemirror/legacy-modes/mode/nginx";
import { properties } from "@codemirror/legacy-modes/mode/properties";
import { diff } from "@codemirror/legacy-modes/mode/diff";
import { verilog } from "@codemirror/legacy-modes/mode/verilog";
import { vhdl } from "@codemirror/legacy-modes/mode/vhdl";
import { standardSQL } from "@codemirror/legacy-modes/mode/sql";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { prolog } from "../lib/prologMode";
import { prologClauseFolding } from "../lib/prologFolding";
import { jsonDocumentToMetta, mettaDocumentToJson, mettaToJsonValue } from "../lib/mettaResourceCodec";
import { useUserUiPreferences } from "../lib/uiPreferences";
import { WorkspaceResourceFileControls, type WorkspaceResourceFileControlsProps } from "./WorkspaceResourceFileControls";
import { MarkdownDocument } from "./MarkdownDocument";
import "../styles/operation_editor.css";

const streamLang = (mode: Parameters<typeof StreamLanguage.define>[0]): Extension[] => [StreamLanguage.define(mode)];
const TEXT_LANGUAGES: { id: string; label: string; extension: () => Extension[] }[] = [
  { id: "plain", label: "Plain Text", extension: () => [] },
  { id: "markdown", label: "Markdown", extension: () => [markdown()] },
  { id: "json", label: "JSON", extension: () => [json()] },
  { id: "javascript", label: "JavaScript / TS", extension: () => [javascript({ jsx: true, typescript: true })] },
  { id: "python", label: "Python", extension: () => [python()] },
  { id: "css", label: "CSS", extension: () => [css()] },
  { id: "html", label: "HTML", extension: () => [html()] },
  { id: "xml", label: "XML", extension: () => streamLang(xml) },
  { id: "yaml", label: "YAML", extension: () => streamLang(yaml) },
  { id: "toml", label: "TOML", extension: () => streamLang(toml) },
  { id: "ini", label: "INI / Properties", extension: () => streamLang(properties) },
  { id: "shell", label: "Shell", extension: () => streamLang(shell) },
  { id: "powershell", label: "PowerShell", extension: () => streamLang(powerShell) },
  { id: "dockerfile", label: "Dockerfile", extension: () => streamLang(dockerFile) },
  { id: "sql", label: "SQL", extension: () => streamLang(standardSQL) },
  { id: "diff", label: "Diff / Patch", extension: () => streamLang(diff) },
  { id: "c", label: "C", extension: () => streamLang(c) },
  { id: "cpp", label: "C++", extension: () => streamLang(cpp) },
  { id: "java", label: "Java", extension: () => streamLang(java) },
  { id: "csharp", label: "C#", extension: () => streamLang(csharp) },
  { id: "kotlin", label: "Kotlin", extension: () => streamLang(kotlin) },
  { id: "scala", label: "Scala", extension: () => streamLang(scala) },
  { id: "dart", label: "Dart", extension: () => streamLang(dart) },
  { id: "objectivec", label: "Objective-C", extension: () => streamLang(objectiveC) },
  { id: "go", label: "Go", extension: () => streamLang(go) },
  { id: "rust", label: "Rust", extension: () => streamLang(rust) },
  { id: "ruby", label: "Ruby", extension: () => streamLang(ruby) },
  { id: "perl", label: "Perl", extension: () => streamLang(perl) },
  { id: "swift", label: "Swift", extension: () => streamLang(swift) },
  { id: "r", label: "R", extension: () => streamLang(r) },
  { id: "lua", label: "Lua", extension: () => streamLang(lua) },
  { id: "haskell", label: "Haskell", extension: () => streamLang(haskell) },
  { id: "groovy", label: "Groovy", extension: () => streamLang(groovy) },
  { id: "julia", label: "Julia", extension: () => streamLang(julia) },
  { id: "clojure", label: "Clojure", extension: () => streamLang(clojure) },
  { id: "scheme", label: "Scheme / Lisp", extension: () => streamLang(scheme) },
  { id: "erlang", label: "Erlang", extension: () => streamLang(erlang) },
  { id: "elm", label: "Elm", extension: () => streamLang(elm) },
  { id: "coffeescript", label: "CoffeeScript", extension: () => streamLang(coffeeScript) },
  { id: "sass", label: "Sass", extension: () => streamLang(sass) },
  { id: "cmake", label: "CMake", extension: () => streamLang(cmake) },
  { id: "nginx", label: "Nginx", extension: () => streamLang(nginx) },
  { id: "verilog", label: "Verilog", extension: () => streamLang(verilog) },
  { id: "vhdl", label: "VHDL", extension: () => streamLang(vhdl) },
  { id: "latex", label: "LaTeX", extension: () => streamLang(stex) },
  { id: "prolog", label: "Prolog", extension: () => [
    ...streamLang(prolog),
    prologClauseFolding,
  ] },
];
function textLanguageExtension(id: string): Extension[] {
  return (TEXT_LANGUAGES.find((entry) => entry.id === id) || TEXT_LANGUAGES[0]).extension();
}
const EXTENSION_TEXT_LANGUAGE: Record<string, string> = {
  md: "markdown", markdown: "markdown", mdx: "markdown", txt: "plain", text: "plain", log: "plain",
  json: "json", jsonl: "json", geojson: "json", ipynb: "json", webmanifest: "json",
  js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript", ts: "javascript", tsx: "javascript", mts: "javascript", cts: "javascript",
  py: "python", pyi: "python", pyw: "python",
  css: "css", less: "css", scss: "sass", sass: "sass",
  html: "html", htm: "html", xhtml: "html", vue: "html", svelte: "html",
  xml: "xml", svg: "xml", xsd: "xml", xsl: "xml", plist: "xml", rss: "xml",
  yaml: "yaml", yml: "yaml",
  toml: "toml",
  ini: "ini", cfg: "ini", conf: "ini", properties: "ini", env: "ini",
  sh: "shell", bash: "shell", zsh: "shell", ksh: "shell",
  ps1: "powershell", psm1: "powershell", psd1: "powershell",
  sql: "sql",
  diff: "diff", patch: "diff",
  c: "c", h: "c",
  cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp", hh: "cpp", hxx: "cpp",
  java: "java",
  cs: "csharp",
  kt: "kotlin", kts: "kotlin",
  scala: "scala", sc: "scala",
  dart: "dart",
  mm: "objectivec",
  go: "go",
  rs: "rust",
  rb: "ruby", gemspec: "ruby",
  pl: "prolog", pro: "prolog", prolog: "prolog",
  pm: "perl",
  swift: "swift",
  r: "r",
  lua: "lua",
  hs: "haskell",
  groovy: "groovy", gradle: "groovy",
  jl: "julia",
  clj: "clojure", cljs: "clojure", cljc: "clojure", edn: "clojure",
  scm: "scheme", ss: "scheme", lisp: "scheme", el: "scheme", metta: "clojure",
  erl: "erlang", hrl: "erlang",
  elm: "elm",
  coffee: "coffeescript",
  tex: "latex", sty: "latex",
  v: "verilog", sv: "verilog", svh: "verilog",
  vhd: "vhdl", vhdl: "vhdl",
};
export function textLanguageForFilename(name: string): string {
  const base = (name.split(/[\\/]/).at(-1) || "").toLowerCase();
  if (base === "dockerfile" || base.startsWith("dockerfile.")) return "dockerfile";
  if (base === "makefile" || base === "cmakelists.txt") return "cmake";
  if (base === ".gitignore" || base === ".dockerignore" || base === ".npmrc" || base === ".editorconfig") return "ini";
  const ext = base.includes(".") ? base.split(".").at(-1)! : "";
  return EXTENSION_TEXT_LANGUAGE[ext] || "plain";
}

type SourceFormat = "metta" | "json" | "tree" | "text" | "markdown";
type Props = {
  value: string;
  onChange: (json: string) => void;
  onValidityChange?: (valid: boolean) => void;
  className?: string;
  style?: CSSProperties;
  label?: string;
  sourcePath?: string;
  resourceMetadata?: Record<string, unknown>;
  showEnablement?: boolean;
  disabled?: boolean;
  contentReadOnly?: boolean;
  stacked?: boolean;
  defaultFormat?: SourceFormat;
  defaultTextLang?: string;
  revealLine?: number;
  fileControlsContent?: string;
  fileControls?: Omit<WorkspaceResourceFileControlsProps, "disabled" | "content" | "onClientContent">;
};

type SourceMode = { format: SourceFormat; textLanguage: string };

const LANGUAGE_ALIASES: Record<string, string> = {
  md: "markdown",
  markdown: "markdown",
  mdx: "markdown",
  js: "javascript",
  jsx: "javascript",
  ts: "javascript",
  tsx: "javascript",
  node: "javascript",
  py: "python",
  python3: "python",
  pwsh: "powershell",
  ps: "powershell",
  yml: "yaml",
  cxx: "cpp",
  cc: "cpp",
  cs: "csharp",
  golang: "go",
  rb: "ruby",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  metta: "clojure",
  lisp: "clojure",
};

function normalizedLanguage(value: string): string {
  const token = value.trim().toLowerCase().replace(/^text\//, "").replace(/^application\//, "");
  const normalized = LANGUAGE_ALIASES[token] || token;
  return TEXT_LANGUAGES.some(language => language.id === normalized) ? normalized : "plain";
}

function isJsonContent(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

function looksLikeMarkdown(value: string): boolean {
  return /^(?: {0,3}#{1,6}\s+\S| {0,3}(?:[-*+]|\d+\.)\s+\S| {0,3}>\s+\S|```|~~~)/m.test(value)
    || /\[[^\]]+\]\([^)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__/.test(value);
}

function shebangLanguage(value: string): string {
  const firstLine = value.split(/\r?\n/, 1)[0]?.trim().toLowerCase() || "";
  if (!firstLine.startsWith("#!")) return "";
  if (/\bpython/.test(firstLine)) return "python";
  if (/\b(?:node|deno|bun)\b/.test(firstLine)) return "javascript";
  if (/\b(?:pwsh|powershell)\b/.test(firstLine)) return "powershell";
  if (/\bruby\b/.test(firstLine)) return "ruby";
  if (/\bperl\b/.test(firstLine)) return "perl";
  if (/\b(?:bash|zsh|ksh|sh)\b/.test(firstLine)) return "shell";
  return "";
}

function contentLanguage(value: string): string {
  const trimmed = value.replace(/^\s*(```|~~~)[\s\S]*?^\s*\1\s*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*(?:%|\/\/|#(?!\!)).*$/gm, "").trim();
  if (/^<!doctype\s+html|^<html[\s>]/i.test(trimmed)) return "html";
  if (/^<\?xml\b/i.test(trimmed)) return "xml";
  if (/^(?:select|insert|update|delete|create|alter)\b[\s\S]*\b(?:from|into|table)\b/im.test(trimmed)) return "sql";
  if (/^(?:from\s+[\w.]+\s+import|import\s+[\w.]+(?:\s+as\s+\w+)?\s*$|(?:async\s+)?def\s+\w+\s*\(|class\s+\w+[^;\n]*:)/m.test(trimmed)) return "python";
  if (/^(?:const|let|var|function|export|import)\s+[\w{*]|=>/m.test(trimmed)) return "javascript";
  if (/^(?:\s*:-\s*\w|\s*[a-z]\w*(?:\([^;\n]*\))?\s*:-|\s*[a-z]\w*\([^;\n]*\)\.\s*$)/m.test(trimmed)) return "prolog";
  if (/^\s*\((?:=|!|:|defn|define|import!|let|match|bind!)(?:\s|\()/m.test(trimmed)) return "clojure";
  if (/^(?:package\s+main|func\s+\w+\s*\()/m.test(trimmed)) return "go";
  if (/^(?:fn\s+\w+|use\s+\w+::|impl(?:<[^>]+>)?\s+\w+)/m.test(trimmed)) return "rust";
  if (/^---\s*$[\s\S]*^\w[\w.-]*:\s+/m.test(trimmed) && !looksLikeMarkdown(value.replace(/^---[\s\S]*?^---\s*$/m, ""))) return "yaml";
  return "";
}

function metadataLanguage(metadata?: Record<string, unknown>): string {
  if (!metadata) return "";
  for (const key of ["language", "syntax", "lexer", "format", "mimeType", "mime_type", "contentType", "type", "kind"]) {
    const value = metadata[key];
    if (typeof value !== "string") continue;
    const detected = normalizedLanguage(value);
    if (detected !== "plain") return detected;
  }
  return "";
}

export function detectResourceSourceMode(
  value: string,
  sourcePath = "",
  metadata?: Record<string, unknown>,
  defaultFormat?: SourceFormat,
  defaultTextLanguage?: string,
): SourceMode {
  if (isJsonContent(value)) {
    if (defaultFormat === "text") return { format: "text", textLanguage: "json" };
    return { format: "metta", textLanguage: "clojure" };
  }
  const pathLanguage = textLanguageForFilename(sourcePath);
  // Executable markers outrank Markdown-looking comments; real Markdown
  // content still outranks a misleading filename or resource annotation.
  const detectedLanguage = shebangLanguage(value)
    || contentLanguage(value)
    || (looksLikeMarkdown(value) ? "markdown" : "")
    || metadataLanguage(metadata)
    || normalizedLanguage(defaultTextLanguage || "").replace(/^plain$/, "")
    || (pathLanguage !== "plain" ? pathLanguage : "")
    || "plain";
  if (detectedLanguage === "markdown") return { format: "text", textLanguage: "markdown" };
  if (defaultFormat === "text") return { format: "text", textLanguage: detectedLanguage };
  if (/\.metta$/i.test(sourcePath) && detectedLanguage === "clojure") return { format: "metta", textLanguage: "clojure" };
  return {
    format: defaultFormat || "text",
    textLanguage: detectedLanguage || "plain",
  };
}

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };
type JsonPathToken = string | number;

function jsonTypeLabel(value: JsonValue): string {
  if (Array.isArray(value)) return `array(len:${value.length})`;
  if (value === null) return "null";
  switch (typeof value) {
    case "string":
      return `string(${value.length})`;
    case "number":
      return Number.isInteger(value) ? "integer" : "number";
    case "boolean":
      return "boolean";
    default:
      return `object(${Object.keys(value).length})`;
  }
}

function jsonObjectField(value: JsonValue, field: string): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const map = value as JsonObject;
  const direct = map[field];
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  if (typeof direct === "number" && Number.isFinite(direct)) return String(direct);
  const target = field.toLowerCase();
  for (const [key, raw] of Object.entries(map)) {
    if (key.toLowerCase() === target && typeof raw === "string" && raw.trim()) return raw.trim();
  }
  return null;
}

function keysMatchingSuffix(value: JsonValue, suffixPattern: RegExp): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.keys(value as JsonObject).filter((key) => suffixPattern.test(key));
}

function firstStringFromKeys(value: JsonValue, keys: string[]): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const map = value as JsonObject;
  for (const key of keys) {
    const raw = map[key];
    if (typeof raw === "string" && raw.trim()) return raw.trim();
  }
  return null;
}

function jsonObjectIdentifier(value: JsonValue): string | null {
  const direct = jsonObjectField(value, "id") || jsonObjectField(value, "key");
  if (direct) return direct;
  return firstStringFromKeys(value, keysMatchingSuffix(value, /(^|[_-])(id|key)$/i));
}

function jsonObjectKinds(value: JsonValue): string[] {
  const kinds: string[] = [];
  const pushUnique = (key: string) => {
    const item = jsonObjectField(value, key);
    if (item && !kinds.includes(item)) kinds.push(item);
  };
  pushUnique("subkind");
  pushUnique("kind");
  pushUnique("type");
  pushUnique("role");
  for (const item of keysMatchingSuffix(value, /(kind|role)$/i)) {
    const text = jsonObjectField(value, item);
    if (text && !kinds.includes(text)) kinds.push(text);
  }
  return kinds;
}

function jsonObjectKindValue(value: JsonValue): string | null {
  return jsonObjectField(value, "kind")
    || jsonObjectField(value, "type")
    || firstStringFromKeys(value, keysMatchingSuffix(value, /(^|[_-])(kind|type)$/i));
}

function jsonObjectSubkindValue(value: JsonValue): string | null {
  return jsonObjectField(value, "subkind") || firstStringFromKeys(value, keysMatchingSuffix(value, /(^|[_-])subkind$/i));
}

function jsonObjectRoleValue(value: JsonValue): string | null {
  return jsonObjectField(value, "role") || firstStringFromKeys(value, keysMatchingSuffix(value, /(^|[_-])role$/i));
}

function normalizedKindLabels(kind: string | null, subkind: string | null): { kind: string | null; subkind: string | null } {
  if (kind && subkind && /_defined_by_json$/i.test(kind) && !/_defined_by_json$/i.test(subkind)) {
    return { kind: subkind, subkind: kind };
  }
  return { kind, subkind };
}

function jsonObjectNameLike(value: JsonValue): string | null {
  const direct = jsonObjectField(value, "name") || jsonObjectField(value, "label");
  if (direct) return direct;
  return firstStringFromKeys(value, keysMatchingSuffix(value, /(^|[_-])(name|label)$/i));
}

function jsonObjectParentName(value: JsonValue): string | null {
  return jsonObjectField(value, "parentName") || jsonObjectField(value, "parent_name");
}

function longestStringInDict(value: JsonValue): { text: string; keyed: boolean } | null {
  let longest = "";
  let longestKeyed = false;
  const visit = (node: JsonValue, depth: number, keyed: boolean) => {
    if (depth > 4) return;
    if (typeof node === "string") {
      if (node.length > longest.length) {
        longest = node;
        longestKeyed = keyed;
      }
      return;
    }
    if (Array.isArray(node)) {
      node.forEach((entry) => visit(entry, depth + 1, false));
      return;
    }
    if (node && typeof node === "object") {
      Object.values(node).forEach((entry) => visit(entry, depth + 1, true));
    }
  };
  visit(value, 0, false);
  return longest.trim() ? { text: longest.trim(), keyed: longestKeyed } : null;
}

function jsonNodeSummary(value: JsonValue): string {
  const tags = jsonNodePromotedTokens(value).map(token => token.text);
  return tags.length ? `${tags.join(" · ")} · ${jsonTypeLabel(value)}` : jsonTypeLabel(value);
}

function jsonNodeSummaryParts(value: JsonValue): { id: string | null; kind: string | null; name: string | null; type: string } {
  const normalizedKinds = normalizedKindLabels(jsonObjectKindValue(value), jsonObjectSubkindValue(value));
  return {
    id: jsonObjectIdentifier(value),
    kind: normalizedKinds.kind,
    name: jsonObjectNameLike(value),
    type: jsonTypeLabel(value),
  };
}

function jsonObjectTokenGroup(value: JsonValue, exactKeys: string[], suffixPattern: RegExp): Array<{ label: string; value: string }> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const map = value as JsonObject;
  const exact = new Set(exactKeys.map((key) => key.toLowerCase()));
  const seen = new Set<string>();
  const tokens: Array<{ label: string; value: string }> = [];
  for (const [rawKey, rawValue] of Object.entries(map)) {
    const trimmed = typeof rawValue === "string" ? rawValue.trim()
      : typeof rawValue === "number" && Number.isFinite(rawValue) ? String(rawValue) : "";
    if (!trimmed) continue;
    const key = rawKey.toLowerCase();
    if (!exact.has(key) && !suffixPattern.test(rawKey)) continue;
    const identity = `${key}:${trimmed}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    tokens.push({ label: key, value: trimmed });
  }
  return tokens;
}

function jsonNodePromotedTokens(value: JsonValue): Array<{ className: string; text: string }> {
  const idTokens = jsonObjectTokenGroup(value, ["id", "key"], /(^|[_-])(id|key)$/i)
    .map((item) => ({ className: "json-tree-token-id", text: `${item.label}:${item.value}` }));
  const kindTokens = jsonObjectTokenGroup(value, ["kind", "type", "subkind", "role"], /(^|[_-])(kind|type|subkind|role)$/i)
    .map((item) => ({ className: "json-tree-token-kind", text: `${item.label}:${item.value}` }));
  const nameTokens = jsonObjectTokenGroup(value, ["name", "label"], /(^|[_-])(name|label)$/i)
    .map((item) => ({ className: "json-tree-token-name", text: `${item.label}:${item.value}` }));
  return [...idTokens, ...kindTokens, ...nameTokens];
}

function jsonNodeTooltip(value: JsonValue): { text: string; source: "length" | "description" | "longest"; keyed: boolean } | null {
  if (Array.isArray(value)) {
    return { text: `length: ${value.length}`, source: "length", keyed: false };
  }
  const explicit = jsonObjectField(value, "description");
  if (explicit) return { text: explicit, source: "description", keyed: true };
  const longest = longestStringInDict(value);
  if (!longest) return null;
  return { text: longest.text, source: "longest", keyed: longest.keyed };
}

function formatPrimitivePreview(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "string") return `"${value}"`;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return `${value}`;
  return "…";
}

function simpleValueDisplay(value: JsonValue): string | null {
  if (Array.isArray(value)) return null;
  if (value && typeof value === "object") return null;
  return formatPrimitivePreview(value);
}

function arrayPreviewInfo(value: JsonValue, suppressValue: string | null = null): { mode: "horizontal" | "vertical"; values: string[]; truncated: boolean } | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const previewValues = value.slice(0, 8).filter((entry) => !(typeof entry === "string" && suppressValue && entry.trim() === suppressValue.trim()));
  if (previewValues.length === 0) return null;
  const allStrings = previewValues.every((entry) => typeof entry === "string");
  const hasNonAlphaNumericString = allStrings && previewValues.some((entry) => /[^A-Za-z0-9]/.test(entry as string));
  return {
    mode: hasNonAlphaNumericString ? "vertical" : "horizontal",
    values: previewValues.map((entry) => formatPrimitivePreview(entry)),
    truncated: value.length > previewValues.length,
  };
}

function collectExpandablePaths(value: JsonValue, path: string, out: Set<string>) {
  if (Array.isArray(value)) {
    out.add(path);
    value.forEach((entry, index) => collectExpandablePaths(entry, jsonChildPath(path, index), out));
    return;
  }
  if (value && typeof value === "object") {
    out.add(path);
    Object.entries(value).forEach(([key, entry]) => collectExpandablePaths(entry, jsonChildPath(path, key), out));
  }
}

function parseJsonPath(path: string): JsonPathToken[] {
  return jsonPathTokens(path);
}

function getNodeAtPath(root: JsonValue, path: string): JsonValue | null {
  const tokens = parseJsonPath(path);
  let current: JsonValue = root;
  for (const token of tokens) {
    if (typeof token === "number") {
      if (!Array.isArray(current) || token < 0 || token >= current.length) return null;
      current = current[token];
      continue;
    }
    if (!current || typeof current !== "object" || Array.isArray(current) || !Object.prototype.hasOwnProperty.call(current, token)) return null;
    current = (current as JsonObject)[token];
  }
  return current;
}

function updateJsonAtPath(root: JsonValue, path: string, updater: (target: JsonValue, parent: JsonValue | null, key: JsonPathToken | null) => JsonValue | null): JsonValue | null {
  const tokens = parseJsonPath(path);
  const cloned = JSON.parse(JSON.stringify(root)) as JsonValue;
  if (tokens.length === 0) return updater(cloned, null, null);
  let parent: JsonValue | null = null;
  let current: JsonValue = cloned;
  let currentKey: JsonPathToken | null = null;
  for (const token of tokens) {
    parent = current;
    currentKey = token;
    if (typeof token === "number") {
      if (!Array.isArray(current) || token < 0 || token >= current.length) return null;
      current = current[token];
    } else {
      if (!current || typeof current !== "object" || Array.isArray(current) || !Object.prototype.hasOwnProperty.call(current, token)) return null;
      current = (current as JsonObject)[token];
    }
  }
  const next = updater(current, parent, currentKey);
  if (next === null) {
    if (parent === null || currentKey === null) return null;
    if (typeof currentKey === "number") {
      if (!Array.isArray(parent)) return null;
      parent.splice(currentKey, 1);
    } else {
      if (!parent || typeof parent !== "object" || Array.isArray(parent)) return null;
      delete (parent as JsonObject)[currentKey];
    }
    return cloned;
  }
  if (parent === null || currentKey === null) return cloned;
  if (typeof currentKey === "number") {
    if (!Array.isArray(parent) || currentKey < 0 || currentKey >= parent.length) return null;
    parent[currentKey] = next;
  } else {
    if (!parent || typeof parent !== "object" || Array.isArray(parent)) return null;
    (parent as JsonObject)[currentKey] = next;
  }
  return cloned;
}

export function ResourceSourceEditor({
  value,
  onChange,
  onValidityChange,
  className = "",
  style,
  label = "Edit this resource directly",
  sourcePath = "",
  resourceMetadata,
  showEnablement = true,
  disabled = false,
  contentReadOnly = false,
  stacked = false,
  defaultFormat,
  defaultTextLang,
  revealLine,
  fileControlsContent,
  fileControls,
}: Props) {
  const { resourceSourceFileControlsPlacement } = useUserUiPreferences();
  const editingLocked = disabled || contentReadOnly;
  const initialMode = detectResourceSourceMode(value, sourcePath || label, resourceMetadata, defaultFormat, defaultTextLang);
  const [format, setFormat] = useState<SourceFormat>(initialMode.format);
  const formatChosen = useRef(false);
  const chooseFormat = (next: SourceFormat) => { formatChosen.current = true; setFormat(next); };
  const [textLang, setTextLang] = useState<string>(initialMode.textLanguage);
  const [metta, setMetta] = useState("");
  const [jsonDraft, setJsonDraft] = useState(value);
  const [error, setError] = useState("");
  const [jsonState] = useState(() => ({ current: createJsonTreeState(value) }));
  const [, refreshTree] = useState(0);
  const [selectedTreePath, setSelectedTreePath] = useState("$");
  const [treeRenderNormal, setTreeRenderNormal] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string } | null>(null);
  const emittedJson = useRef<string | null>(null);
  const sourceModel = useRef<"json" | "raw">(isJsonContent(value) ? "json" : "raw");
  const rawMettaProjection = useRef(false);
  const codeMirrorView = useRef<EditorView | null>(null);
  const invalidDraft = useRef(false);
  const sourceContext = sourcePath || label;
  const previousSourceContext = useRef(sourceContext);
  const [externalConflict, setExternalConflict] = useState(false);
  const sourceMettaToJson = (source: string) => sourceModel.current === "raw"
    ? mettaDocumentToJson(source) : JSON.stringify(mettaToJsonValue(source), null, 2);
  const validDraft = (valid: boolean) => {
    invalidDraft.current = !valid;
    onValidityChange?.(valid);
  };

  const revealRequestedLine = (view: EditorView) => {
    if (!revealLine || revealLine < 1 || view.state.doc.lines === 0) return;
    const line = view.state.doc.line(Math.min(revealLine, view.state.doc.lines));
    view.dispatch({
      selection: { anchor: line.from },
      effects: EditorView.scrollIntoView(line.from, { y: "center" }),
    });
  };

  useContextReset(JSON.stringify([sourceContext, value]), () => {
    const changedDocument = previousSourceContext.current !== sourceContext;
    previousSourceContext.current = sourceContext;
    if (changedDocument) {
      invalidDraft.current = false;
      setExternalConflict(false);
      setFormat(initialMode.format);
      setTextLang(initialMode.textLanguage);
      formatChosen.current = false;
      jsonState.current = createJsonTreeState(value);
      setSelectedTreePath("$");
    } else if (invalidDraft.current && value !== emittedJson.current) {
      setExternalConflict(true);
      return;
    }
    const currentFormat = changedDocument || !formatChosen.current ? initialMode.format : format;
    if (value === emittedJson.current) {
      emittedJson.current = null;
      if (sourceModel.current === "raw" && (currentFormat === "metta" || rawMettaProjection.current)) {
        setMetta(value);
        try { setJsonDraft(sourceMettaToJson(value)); } catch { setJsonDraft(value); }
      } else {
        setJsonDraft(value);
      }
      return;
    }
    rawMettaProjection.current = false;
    if (!formatChosen.current) {
      setFormat(initialMode.format);
      setTextLang(initialMode.textLanguage);
    }
    setJsonDraft(value);
    if (!value) { setMetta(""); setError(""); validDraft(true); return; }
    try {
      setMetta(jsonDocumentToMetta(value));
      sourceModel.current = "json";
      setError("");
      validDraft(true);
    }
    catch (reason) {
      setMetta(value);
      sourceModel.current = "raw";
      if (currentFormat === "metta" || currentFormat === "json" || currentFormat === "tree") {
        try {
          const converted = sourceMettaToJson(value);
          setMetta(value);
          setJsonDraft(converted);
          sourceModel.current = "raw";
          rawMettaProjection.current = true;
          setError("");
          validDraft(true);
          return;
        } catch {
          // The source remains editable below with the original parse error.
        }
      }
      if (initialMode.textLanguage !== "json") {
        sourceModel.current = "raw";
        setError("");
        validDraft(true);
      } else {
        sourceModel.current = "json";
        setError(reason instanceof Error ? reason.message : String(reason));
        validDraft(false);
      }
    }
  });

  useEffect(() => {
    if (!revealLine) return;
    let cancelled = false;
    const reveal = () => {
      const view = codeMirrorView.current;
      if (!cancelled && view) revealRequestedLine(view);
    };
    const frame = window.requestAnimationFrame(reveal);
    const timer = window.setTimeout(reveal, 50);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [format, revealLine, textLang, value]);

  const editMetta = (next: string) => {
    if (editingLocked) return;
    setMetta(next);
    try {
      const json = sourceMettaToJson(next);
      rawMettaProjection.current = sourceModel.current === "raw";
      setJsonDraft(json);
      const emitted = sourceModel.current === "raw" ? next : json;
      emittedJson.current = emitted;
      onChange(emitted);
      setError("");
      setExternalConflict(false);
      validDraft(true);
    }
    catch (reason) {
      if (sourceModel.current === "raw") {
        rawMettaProjection.current = false;
        setJsonDraft(next);
        emittedJson.current = next;
        onChange(next);
        setError("");
        validDraft(true);
      } else {
        setError(reason instanceof Error ? reason.message : String(reason));
        validDraft(false);
      }
    }
  };
  const editJson = (next: string) => {
    if (editingLocked) return;
    setJsonDraft(next);
    try {
      JSON.parse(next);
      const nextMetta = jsonDocumentToMetta(next);
      setMetta(nextMetta);
      const emitted = rawMettaProjection.current ? nextMetta : next;
      if (!rawMettaProjection.current) sourceModel.current = "json";
      emittedJson.current = emitted;
      onChange(emitted);
      setError("");
      setExternalConflict(false);
      validDraft(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); validDraft(false); }
  };
  const editText = (next: string) => {
    if (editingLocked) return;
    if (sourceModel.current === "json" || rawMettaProjection.current) { editJson(next); return; }
    setJsonDraft(next);
    emittedJson.current = next;
    onChange(next);
    setError("");
    validDraft(true);
    try { setMetta(jsonDocumentToMetta(next)); } catch { setMetta(next); }
  };
  const loadClientContent = (content: string) => {
    if (editingLocked) return;
    if (sourceModel.current === "raw") { onChange(content); return; }
    try {
      const parsed = JSON.parse(content);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("A resource document must be a JSON object");
      onChange(`${JSON.stringify(parsed, null, 2)}\n`);
    } catch {
      onChange(mettaDocumentToJson(content));
    }
  };
  let resource: Record<string, unknown> | null = null;
  try { const parsed = JSON.parse(value); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) resource = parsed; } catch { /* Invalid source remains editable. */ }
  const resourceEnabled = resource?.enabled !== false;
  const setEnabled = (enabled: boolean) => { if (!editingLocked && resource) onChange(JSON.stringify({ ...resource, enabled }, null, 2)); };
  jsonState.current = updateJsonTreeDocument(jsonState.current, jsonDraft);
  const codeMirrorJsonTree = jsonTreeNodes(jsonState.current);
  const treeExpandedPaths = expandedJsonPaths(jsonState.current);
  const parsedTreeRoot = useMemo(() => {
    if (!codeMirrorJsonTree) return null;
    try {
      const parsed = JSON.parse(jsonDraft);
      return parsed as JsonValue;
    } catch {
      return null;
    }
  }, [codeMirrorJsonTree, jsonDraft]);
  const allExpandablePaths = new Set((codeMirrorJsonTree ?? []).filter(node => node.fold).map(node => node.path));
  const treeSelectionType = useMemo(() => {
    if (!codeMirrorJsonTree) return "";
    const selected = getNodeAtPath(parsedTreeRoot, selectedTreePath);
    return !codeMirrorJsonTree.some(node => node.path === selectedTreePath) ? "missing" : treeRenderNormal ? jsonTypeLabel(selected) : jsonNodeSummary(selected);
  }, [parsedTreeRoot, selectedTreePath, treeRenderNormal]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [contextMenu]);

  const changeTreeFolds = (path: string, expand: boolean, descendants = true, childrenOnly = false) => {
    jsonState.current = changeJsonFolds(jsonState.current, path, expand, descendants, childrenOnly);
    const view = codeMirrorView.current;
    if (format === "json" && view) view.dispatch({ effects: restoreJsonFolds(view.state, jsonState.current) });
    refreshTree(value => value + 1);
  };
  const togglePath = (path: string) => changeTreeFolds(path, !treeExpandedPaths.has(path), false);
  const expandSelectedBranch = () => {
    changeTreeFolds(selectedTreePath, true);
  };
  const collapseSelectedBranch = () => {
    changeTreeFolds(selectedTreePath, false);
  };
  const collapseSelectedChildren = () => {
    changeTreeFolds(selectedTreePath, false, true, true);
    changeTreeFolds(selectedTreePath, true, false);
  };

  const expandWholeTree = () => {
    changeTreeFolds("$", true);
  };

  const collapseWholeTree = () => {
    changeTreeFolds("$", false);
  };

  const writeTreeDocument = (nextRoot: JsonValue) => {
    const nextText = `${JSON.stringify(nextRoot, null, 2)}\n`;
    editJson(nextText);
  };

  const addKeyAtPath = (path: string) => {
    if (editingLocked || !parsedTreeRoot) return;
    const node = getNodeAtPath(parsedTreeRoot, path);
    if (!node || typeof node !== "object" || Array.isArray(node)) return;
    const key = window.prompt("New key name");
    if (!key || !key.trim()) return;
    const valueInput = window.prompt("New value (JSON literal or plain text)", "\"\"");
    if (valueInput === null) return;
    let nextValue: JsonValue;
    try {
      nextValue = JSON.parse(valueInput) as JsonValue;
    } catch {
      nextValue = valueInput;
    }
    const updated = updateJsonAtPath(parsedTreeRoot, path, (target) => {
      if (!target || typeof target !== "object" || Array.isArray(target)) return target;
      return { ...(target as JsonObject), [key.trim()]: nextValue };
    });
    if (updated) writeTreeDocument(updated);
  };

  const deleteAtPath = (path: string) => {
    if (editingLocked || !parsedTreeRoot || path === "$") return;
    if (!window.confirm(`Delete ${path}?`)) return;
    const updated = updateJsonAtPath(parsedTreeRoot, path, () => null);
    if (updated) writeTreeDocument(updated);
  };

  const renderTreeNode = (node: JsonValue, path: string, labelText: string): ReactNode => {
    const isArray = Array.isArray(node);
    const isObject = Boolean(node && typeof node === "object" && !isArray);
    const children: Array<[string, JsonValue, string]> = isArray
      ? (node as JsonValue[]).map((entry, index) => {
        const entryId = jsonObjectIdentifier(entry);
        const entryKind = jsonObjectKinds(entry)[0] || null;
        const entryName = jsonObjectNameLike(entry);
        const preferredLabel = treeRenderNormal ? `[${index}]` : (entryName || entryId || entryKind || `[${index}]`);
        return [jsonChildPath(path, index), entry, preferredLabel];
      })
      : isObject
        ? (() => {
          const mapNode = node as JsonObject;
          const suppressMetadataKeys = new Set<string>();
          if (!treeRenderNormal && jsonObjectIdentifier(node)) {
            suppressMetadataKeys.add("id");
            Object.keys(mapNode).forEach((key) => { if (/_id$/i.test(key)) suppressMetadataKeys.add(key); });
          }
          if (!treeRenderNormal && jsonObjectKinds(node).length > 0) {
            suppressMetadataKeys.add("subkind");
            suppressMetadataKeys.add("kind");
            suppressMetadataKeys.add("role");
            Object.keys(mapNode).forEach((key) => { if (/(kind|role)$/i.test(key)) suppressMetadataKeys.add(key); });
          }
          if (!treeRenderNormal && jsonObjectNameLike(node)) {
            suppressMetadataKeys.add("label");
            suppressMetadataKeys.add("name");
            suppressMetadataKeys.add("parentName");
            suppressMetadataKeys.add("parent_name");
            Object.keys(mapNode).forEach((key) => { if (/(name|label)$/i.test(key)) suppressMetadataKeys.add(key); });
          }
          if (!treeRenderNormal && jsonObjectField(node, "description")) {
            suppressMetadataKeys.add("description");
          }
          return Object.entries(mapNode)
            .filter(([key]) => !suppressMetadataKeys.has(key))
            .map(([key, entry]) => [jsonChildPath(path, key), entry, key]);
        })()
        : [];
    const hasChildren = isArray || isObject;
    const expanded = treeExpandedPaths.has(path);
    const selected = selectedTreePath === path;

    const tooltip = jsonNodeTooltip(node);
    const preview = arrayPreviewInfo(
      node,
      tooltip && tooltip.source === "longest" && !tooltip.keyed ? tooltip.text : null,
    );
    const inlineValue = simpleValueDisplay(node);
    const promotedTokens = jsonNodePromotedTokens(node);
    const detailText = inlineValue ?? (treeRenderNormal ? jsonTypeLabel(node) : jsonNodeSummary(node));
    return <div key={path} className="json-tree-node">
      <div className={`json-tree-row ${selected ? "selected" : ""}`} onContextMenu={(event) => {
        if (disabled) return;
        event.preventDefault();
        setSelectedTreePath(path);
        setContextMenu({ x: event.clientX, y: event.clientY, path });
      }}>
        <button type="button" className="json-tree-toggle" aria-label={`${expanded ? "Collapse" : "Expand"} ${path}`} aria-expanded={hasChildren ? expanded : undefined} disabled={disabled || !hasChildren} onClick={() => togglePath(path)}>{hasChildren ? (expanded ? "▾" : "▸") : "·"}</button>
        <button type="button" className="json-tree-label" title={tooltip?.text || undefined} disabled={disabled} onClick={() => setSelectedTreePath(path)}>
          <span className="json-tree-main">
            <code>{labelText}</code>
            {inlineValue || treeRenderNormal
              ? <span>{detailText}</span>
              : <span className="json-tree-metadata">
                {promotedTokens.length
                  ? promotedTokens.map((token, index) => <span key={`${path}-token-${index}`} className={`json-tree-token ${token.className}`}>{index > 0 ? <span className="json-tree-token-sep"> · </span> : null}{token.text}</span>)
                  : <span>{detailText}</span>}
              </span>}
          </span>
          {preview
            ? <span className={`json-tree-array-preview ${preview.mode}`}>
              {preview.values.map((entry, index) => <span key={`${path}-preview-${index}`}>{entry}</span>)}
              {preview.truncated ? <span>…</span> : null}
            </span>
            : null}
        </button>
      </div>
      {hasChildren && expanded ? <div className="json-tree-children">{children.map(([childPath, childNode, childLabel]) => renderTreeNode(childNode, childPath, childLabel))}</div> : null}
    </div>;
  };

  const renderedFileControls = fileControls
    ? <WorkspaceResourceFileControls
        {...fileControls}
        content={fileControlsContent ?? (format === "metta" ? metta : jsonDraft)}
        onClientContent={loadClientContent}
        disabled={disabled}
        readOnly={contentReadOnly || fileControls.readOnly}
      />
    : null;
  const codeMirrorLanguage = format === "metta"
    ? "clojure"
    : format === "json"
      ? "json"
      : format === "markdown"
        ? "markdown"
        : textLang;
  const selectCodeMirrorLanguage = (language: string) => {
    formatChosen.current = true;
    if (format === "text") {
      setTextLang(language);
      return;
    }
    if (language === codeMirrorLanguage) return;
    setTextLang(language);
    setFormat("text");
  };
  const reloadCurrentSource = () => {
    sourceModel.current = isJsonContent(value) ? "json" : "raw";
    rawMettaProjection.current = false;
    let nextJson = value;
    if (sourceModel.current === "raw" && initialMode.format === "metta") {
      try {
        nextJson = mettaDocumentToJson(value);
        rawMettaProjection.current = true;
      } catch { /* Native programs remain editable in their original language. */ }
    }
    setJsonDraft(nextJson);
    try { setMetta(jsonDocumentToMetta(value)); } catch { setMetta(value); }
    emittedJson.current = null;
    jsonState.current = createJsonTreeState(nextJson);
    setFormat(initialMode.format);
    setTextLang(initialMode.textLanguage);
    setError("");
    setExternalConflict(false);
    validDraft(true);
  };

  return <div className="operation-json-block resource-source-editor">
    <div className="llm-subhead"><div><span>RESOURCE SOURCE</span><b>{label}</b></div><div className="source-format-tabs">
      {showEnablement && resource && <button disabled={editingLocked} className={`resource-enable-action ${resourceEnabled ? "disable-resource" : "enable-resource"}`} onClick={() => setEnabled(!resourceEnabled)}>{resourceEnabled ? "Disable Resource" : "Enable Resource"}</button>}
      <button disabled={disabled} className={format === "metta" ? "active" : ""} onClick={() => chooseFormat("metta")}>MeTTa</button>
      <button disabled={disabled} className={format === "json" ? "active" : ""} onClick={() => chooseFormat("json")}>JSON</button>
      <button disabled={disabled} className={format === "tree" ? "active" : ""} onClick={() => chooseFormat("tree")}>Tree</button>
      <button disabled={disabled} className={format === "text" ? "active" : ""} onClick={() => chooseFormat("text")}>Text</button>
      <button disabled={disabled} className={format === "markdown" ? "active" : ""} onClick={() => chooseFormat("markdown")}>Markdown</button>
      {format !== "tree" ? <select className="rse-text-lang" aria-label="CodeMirror language" disabled={disabled} value={codeMirrorLanguage} onChange={event => selectCodeMirrorLanguage(event.target.value)} title="CodeMirror syntax highlighting; choosing another lexer opens Text view">{TEXT_LANGUAGES.map(entry => <option key={entry.id} value={entry.id}>{entry.label}</option>)}</select> : null}
    </div></div>
    {contentReadOnly && <div className="resource-source-readonly" role="status">Read-only source</div>}
    {resourceSourceFileControlsPlacement === "above" ? renderedFileControls : null}
    {format === "markdown"
      ? <div className="markdown-render operation-visible-editor" style={style}>
          <MarkdownDocument content={jsonDraft} onChange={editText} editable={!editingLocked} />
        </div>
      : format === "tree"
      ? <div
          className={`json-tree-browser operation-visible-editor ${className}`.trim()}
          style={style}
          data-codemirror-json-tree={codeMirrorJsonTree ? "ready" : "invalid"}
        >
        <div className="json-tree-toolbar">
          <span>Path <code>{selectedTreePath}</code>{treeSelectionType ? <> · <b>{treeSelectionType}</b></> : null}</span>
          <div>
            <button type="button" className={treeRenderNormal ? "active" : ""} disabled={disabled || !codeMirrorJsonTree} onClick={() => setTreeRenderNormal((previous) => !previous)}>
              {treeRenderNormal ? "Enhanced labels" : "Normal labels"}
            </button>
            <button type="button" disabled={disabled || !allExpandablePaths.has(selectedTreePath)} onClick={() => collapseSelectedChildren()}>Collapse children</button>
          </div>
        </div>
        <div className="json-tree-root">
        <div className="json-tree-fold-overlay" aria-label="JSON tree fold controls">
          <button type="button" disabled={disabled || !allExpandablePaths.has("$")} onClick={expandWholeTree}>Expand All</button>
          <button type="button" disabled={disabled || !allExpandablePaths.has("$")} onClick={collapseWholeTree}>Collapse All</button>
          <button type="button" disabled={disabled || !allExpandablePaths.has(selectedTreePath)} onClick={expandSelectedBranch}>Expand branch</button>
          <button type="button" disabled={disabled || !allExpandablePaths.has(selectedTreePath)} onClick={collapseSelectedBranch}>Collapse branch</button>
        </div>
        {codeMirrorJsonTree ? renderTreeNode(parsedTreeRoot, "$", "$") : <div className="validation bad">Tree is unavailable until valid JSON has been parsed by CodeMirror. Fix syntax in JSON or MeTTa mode first.</div>}
        </div>
        {contextMenu && parsedTreeRoot ? <div className="json-tree-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
          <button type="button" disabled={editingLocked} onClick={() => { addKeyAtPath(contextMenu.path); setContextMenu(null); }}>Add key</button>
          <button type="button" disabled={editingLocked || contextMenu.path === "$"} onClick={() => { deleteAtPath(contextMenu.path); setContextMenu(null); }}>Delete element</button>
          <button type="button" onClick={() => setContextMenu(null)}>Cancel</button>
        </div> : null}
      </div>
      : <div className={`raw-json-editor operation-visible-editor ${className}`.trim()} style={style} aria-invalid={Boolean(error)}>
         {format === "json" && <div className="codemirror-fold-overlay" aria-label="JSON fold controls">
           <button type="button" onMouseDown={event => event.preventDefault()} disabled={disabled} onClick={expandSelectedBranch}>Expand branch</button>
           <button type="button" onMouseDown={event => event.preventDefault()} disabled={disabled} onClick={collapseSelectedBranch}>Collapse branch</button>
           <button type="button" onMouseDown={event => event.preventDefault()} onClick={expandWholeTree}>Expand all</button>
           <button type="button" onMouseDown={event => event.preventDefault()} onClick={collapseWholeTree}>Collapse all</button>
         </div>}
         <CodeMirror
            key={`${format}:${codeMirrorLanguage}`}
           value={format === "metta" ? metta : jsonDraft}
           height="100%"
            theme="dark"
            editable={!editingLocked}
            readOnly={editingLocked}
            basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: Boolean(revealLine) || !editingLocked }}
            extensions={format === "metta" ? streamLang(clojure) : format === "json" ? [json()] : format === "text" ? textLanguageExtension(textLang) : []}
            onCreateEditor={view => {
              codeMirrorView.current = view;
              if (format === "json") {
                const selected = jsonTreeNodes(view.state)?.find(node => node.path === selectedTreePath);
                view.dispatch({ effects: restoreJsonFolds(view.state, jsonState.current),
                  ...(selected && selected.path !== "$" ? { selection: { anchor: selected.from, head: selected.to } } : {}) });
                jsonState.current = view.state;
              }
              revealRequestedLine(view);
            }}
            onUpdate={update => {
              if (format !== "json" || !(update.docChanged || update.selectionSet
                || !RangeSet.eq([foldedRanges(update.state)], [foldedRanges(update.startState)]))) return;
              jsonState.current = update.state;
              if (update.selectionSet) setSelectedTreePath(jsonBranchAt(update.state, update.state.selection.main.head));
              refreshTree(value => value + 1);
            }}
            onChange={value => format === "metta" ? editMetta(value) : format === "text" ? editText(value) : editJson(value)}
          />
        </div>}
    {stacked && format !== "markdown" ? <div className="markdown-render operation-visible-editor" style={style}>
      <MarkdownDocument content={jsonDraft} onChange={editText} editable={!editingLocked} />
    </div> : null}
    {error && <div className="validation bad" role="alert">Invalid source syntax: {error}. Draft preserved; synchronization and saving are paused until this is fixed.</div>}
    {!error && format === "json" && !codeMirrorJsonTree && <div className="validation bad" role="status">No valid JSON representation is available for this source. Edit its original language or correct the JSON draft.</div>}
    {externalConflict && <div className="validation bad" role="alert">Source changed in another view. Your invalid draft is retained.
      <button type="button" onClick={reloadCurrentSource}>Use latest source (discard this draft)</button>
    </div>}
    {resourceSourceFileControlsPlacement === "below" ? renderedFileControls : null}
  </div>;
}
