import assert from "node:assert/strict";
import test from "node:test";
import {
  prepareSources, hasSources, parseSources, parsePrologData, formatTerm,
  formatClause, sourceTextForSyntax,
} from "../server-model.ts";

test("the browser displays server representations without converting or excluding file types", async () => {
  const sources = [
    { name: "frame-2.metta", text: "native frame" },
    { name: "deductions-2.pl", text: "native deductions" },
    { name: "geometry.json", text: '{"source":"native"}' },
  ];
  const previous = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) });
    return Response.json({
      schemaVersion: 1,
      sources: sources.map((source, i) => ({
        ...source, dialect: "prolog", diagnostics: [], viewNodes: { prolog: [], metta: [], json: [] },
        formats: { prolog: `python-prolog-${i}`, metta: `python-metta-${i}`, json: `python-json-${i}` },
        clauses: [{
          index: 0, predicate: "prepared", arity: 1, args: ["value"],
          argTerms: [{ kind: "atom", source: "value", formats: { prolog: "python-atom", metta: "python-symbol", json: "python-json-value" } }],
          source: "native", original: "native", metta: "not used",
          sourcePath: source.name, sourceLabel: source.name, line: 1, endLine: 1,
          predicateFormats: { prolog: "prepared", metta: "prepared" },
          formats: { prolog: "python-clause", metta: "python-expression", json: "python-node" },
        }],
      })),
    });
  };
  try {
    assert.equal(hasSources(sources), false);
    assert.match(parsePrologData(sources[0].text, sources[0].name).diagnostics[0].message, /Python/);
    await prepareSources(sources);
    const clauses = parseSources(sources);
    assert.equal(clauses.length, 3);
    assert.deepEqual(clauses.map(c => c.sourcePath), sources.map(s => s.name));
    assert.equal(formatTerm(clauses[0].argTerms[0], "metta"), "python-symbol");
    assert.equal(formatClause(clauses[0], "metta"), "python-expression");
    assert.equal(sourceTextForSyntax(sources[2], [], "prolog"), "python-prolog-2");
    await prepareSources(sources);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/omega_vision/api/v1/source-syntax");
    assert.deepEqual(calls[0].body.sources, sources);
    assert.throws(() => formatTerm({ kind: "atom", source: "r2" }, "metta"), /Python-produced/);
  } finally {
    globalThis.fetch = previous;
  }
});

test("failed source analysis remains an explicit failure, not an empty converted source", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ error: "source service failed" }, { status: 422 });
  const source = { name: "unavailable.metta", text: "(data r2)" };
  try {
    await assert.rejects(prepareSources([source]), /source service failed/);
    assert.equal(hasSources([source]), false);
    assert.throws(() => sourceTextForSyntax(source, [], "prolog"), /not ready/);
  } finally {
    globalThis.fetch = previous;
  }
});
