import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { wireServerSyntax } from "../syntax-wiring.mjs";

test("the original renderer only changes source-format call sites and the recovered syntax choices", () => {
  const original = readFileSync(new URL("../upstream/packages/omega_vision_ui/src/components/PrologClauseExplorer.tsx", import.meta.url), "utf8");
  const wired = wireServerSyntax(original);
  assert.match(wired, /from "server-clause-model"/);
  assert.match(wired, /aggregateClauseArguments\(group\.clauses, syntax\)/);
  assert.match(wired, /formatBoundArgument\(group, argument, syntax\)/);
  assert.match(wired, /option value="prolog"/);
  assert.match(wired, /option value="metta"/);
  assert.doesNotMatch(wired, /option value="json"/);
  assert.match(wired, /\$\{clause\.sourcePath\}\\u0000\$\{clause\.index\}\\u0000\$\{clause\.line\}\\u0000\$\{clause\.predicate\}/);
  assert.match(wired, /Most clauses first/);
  assert.throws(() => wireServerSyntax(original.replace("aggregateClauseArguments,", "renamedImport,")), /changed/);
});
