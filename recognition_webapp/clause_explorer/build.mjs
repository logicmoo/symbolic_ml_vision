import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { wireServerSyntax } from "./syntax-wiring.mjs";

const root = dirname(fileURLToPath(import.meta.url));
const require = createRequire(process.env.CLAUSE_EXPLORER_TOOLCHAIN || resolve(root, "package.json"));
const { build } = await import(pathToFileURL(require.resolve("vite")));
const provenance = JSON.parse(readFileSync(resolve(root, "upstream.json"), "utf8"));
for (const [file, expected] of Object.entries(provenance.files)) {
  const actual = createHash("sha256").update(readFileSync(resolve(root, "upstream", file))).digest("hex");
  if (actual !== expected) throw new Error(`Upstream source changed: ${file}`);
}
if (createHash("sha256").update(readFileSync(resolve(root, "explorer.css"))).digest("hex") !== provenance.css.extractedHash) {
  throw new Error("The original explorer style section changed");
}
const packageNames = Object.keys(JSON.parse(readFileSync(resolve(root, "package.json"), "utf8")).dependencies);
function packageRoot(name) {
  try { return dirname(require.resolve(`${name}/package.json`)); }
  catch (error) { if (error.code !== "ERR_PACKAGE_PATH_NOT_EXPORTED") throw error; }
  let directory = dirname(require.resolve(name));
  while (directory !== dirname(directory)) {
    try {
      const metadata = JSON.parse(readFileSync(resolve(directory, "package.json"), "utf8"));
      if (metadata.name === name) return directory;
    } catch (error) { if (error.code !== "ENOENT") throw error; }
    directory = dirname(directory);
  }
  throw new Error(`Cannot locate installed package ${name}`);
}
const aliases = packageNames.sort((a, b) => b.length - a.length).map(name => ({
  find: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?=/|$)`),
  replacement: packageRoot(name),
}));
const app = resolve(root, "upstream/apps/workbench/src");
const codeMirrorRoot = packageRoot("@uiw/react-codemirror");
const codeMirrorPackage = JSON.parse(readFileSync(resolve(codeMirrorRoot, "package.json"), "utf8"));
const licenses = new Map();
const result = await build({
  configFile: false, root, logLevel: "warn",
  resolve: { alias: [
    { find: "@app/components/ResourceSourceEditor", replacement: resolve(root, "source-editor-host.ts") },
    { find: "server-clause-model", replacement: resolve(root, "server-model.ts") },
    { find: "@app", replacement: app },
    { find: "@uiw/react-codemirror", replacement: resolve(root, "codemirror-host.ts") },
    { find: "codemirror-upstream", replacement: resolve(codeMirrorRoot, codeMirrorPackage.module) },
    { find: "../lib/uiPreferences", replacement: resolve(root, "preferences-host.ts") },
    ...aliases,
  ] },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  plugins: [{
    name: "unchanged-explorer-source-and-style",
    enforce: "pre",
    transform(source, id) {
      if (id.replaceAll("\\", "/").endsWith("/upstream/packages/omega_vision_ui/src/components/PrologClauseExplorer.tsx")) {
        return { code: wireServerSyntax(source), map: null };
      }
    },
    generateBundle() {
      for (const id of this.getModuleIds()) {
        if (!id.includes("node_modules") || id.includes("\0")) continue;
        let directory = dirname(id.split("?")[0]);
        while (directory !== dirname(directory)) {
          let metadata;
          try { metadata = JSON.parse(readFileSync(resolve(directory, "package.json"), "utf8")); }
          catch (error) { if (error.code !== "ENOENT") throw error; }
          if (metadata) {
            const key = `${metadata.name}@${metadata.version}`;
            if (!licenses.has(key)) {
              let text = "";
              for (const name of ["LICENSE", "LICENSE.md", "LICENSE.txt", "license", "license.md"]) {
                try { text = readFileSync(resolve(directory, name), "utf8"); break; }
                catch (error) { if (error.code !== "ENOENT") throw error; }
              }
              licenses.set(key, `${key}\nLicense: ${metadata.license || "See upstream package"}\n${text}`);
            }
            break;
          }
          directory = dirname(directory);
        }
      }
    },
  }],
  css: { postcss: { plugins: [{
    postcssPlugin: "scope-editor-styles",
    Rule(rule) {
      if (rule.parent?.type === "atrule" && /keyframes$/i.test(rule.parent.name)) return;
      rule.selectors = rule.selectors.map(selector => `#clause-explorer ${selector}`);
    },
  }] } },
  build: {
    write: false, sourcemap: false, minify: true,
    lib: { entry: resolve(root, "host.ts"), formats: ["iife"], name: "WorkbenchClauseExplorer" },
    rolldownOptions: { output: { codeSplitting: false } },
  },
});
const outputs = (Array.isArray(result) ? result : [result]).flatMap(item => item.output);
const javascript = outputs.filter(item => item.type === "chunk");
if (javascript.length !== 1) throw new Error("Expected one self-contained browser script");
const styles = outputs.filter(item => item.type === "asset" && item.fileName.endsWith(".css"));
const destination = resolve(root, "../static");
mkdirSync(destination, { recursive: true });
writeFileSync(resolve(destination, "clause_explorer.js"),
  `/* Generated from unchanged Workbench sources. See ../clause_explorer/upstream.json and THIRD_PARTY_LICENSES.txt. */\n${javascript[0].code}`);
writeFileSync(resolve(destination, "clause_explorer.css"),
  styles.map(item => String(item.source)).join("\n"));
writeFileSync(resolve(root, "THIRD_PARTY_LICENSES.txt"), [...licenses.values()].sort().join("\n\n----------\n\n"));
console.log(`Bundled original Clause Explorer (${javascript[0].code.length} JS characters); ${Object.keys(provenance.files).length} upstream hashes unchanged.`);
