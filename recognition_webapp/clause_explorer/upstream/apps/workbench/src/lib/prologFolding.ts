import { foldService } from "@codemirror/language";

export type PrologFoldRange = {
  from: number;
  to: number;
};

export function prologClauseFoldRange(
  source: string,
  lineStart: number,
  lineEnd: number,
): PrologFoldRange | null {
  let statementStart: number | null = null;
  let parens = 0;
  let brackets = 0;
  let braces = 0;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";

    if (lineComment) {
      if (char === "\n") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "%") {
      lineComment = true;
      continue;
    }
    if (char === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (statementStart === null && !/\s/.test(char)) statementStart = index;
    if (char === "'" || char === '"' || char === "`") {
      quote = char;
      continue;
    }
    if (char === "(") parens += 1;
    else if (char === ")") parens -= 1;
    else if (char === "[") brackets += 1;
    else if (char === "]") brackets -= 1;
    else if (char === "{") braces += 1;
    else if (char === "}") braces -= 1;

    const terminatesStatement = char === "."
      && parens === 0
      && brackets === 0
      && braces === 0
      && (!next || /\s/.test(next) || next === "%" || (next === "/" && source[index + 2] === "*"));
    if (!terminatesStatement) continue;

    if (
      statementStart !== null
      && statementStart >= lineStart
      && statementStart <= lineEnd
      && index > lineEnd
    ) {
      return { from: lineEnd, to: index };
    }
    statementStart = null;
    if (index > lineEnd) return null;
  }
  return null;
}

export const prologClauseFolding = foldService.of((state, lineStart, lineEnd) =>
  prologClauseFoldRange(state.doc.toString(), lineStart, lineEnd)
);
