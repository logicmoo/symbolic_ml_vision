# Original Workbench Clause Explorer

This is the working `?- Clause Explorer` confirmed in the Workbench on port 5173,
including **Most clauses first**. It is reused, not reimplemented.

`upstream/` contains the original component, `.ts` model, CodeMirror source
editor and their local dependencies, copied byte-for-byte. `upstream.json`
records every source hash and the exact original CSS section. The build rejects
changed upstream files. No JSX-to-manual-DOM port or alternative tree renderer
is used.

The standalone boundary is explicit:

- `host.ts` supplies actual Prolog output files, reloads the local view, and
  applies source edits to the app's browser-only drafts. It supplies no workspace
  ID, so the original workspace file controls are not mounted.
- `preferences-host.ts` supplies fixed editor-control placement without reading
  or writing Workbench preferences.
- `codemirror-host.ts` passes the server's per-document style nonce to the
  original CodeMirror component. Inline scripts and unrestricted inline styles
  are not enabled.
- `host.css` adapts container sizing only. The original explorer CSS remains
  hash-bound; editor dependency CSS is scoped to `#clause-explorer` at build time.

The original tree parser indexes **Prolog**, not native MeTTa or JSON. Those
outputs remain in the app's existing output editor. Prolog can be displayed as
Prolog, MeTTa or JSON using the original formatter. A requested unsupported
native-MeTTa conversion stays explicitly labeled as native, rather than invoking
the discarded port or inventing a parser.

## Build

The browser assets are already included. Running the Python app needs no Node
server, Workbench server, CDN or parent checkout.

To rebuild the included bundle with Node 22+:

```powershell
npm ci
npm run typecheck
npm test
npm run build
```

`static/clause_explorer.js` and `static/clause_explorer.css` are generated
assets, not manually maintained replacements. All package versions are locked.
`THIRD_PARTY_LICENSES.txt` contains dependency attribution; original project
code retains the root LGPL license.

The **TSX control** and **CSS** links show the actual included source. Changing
source drafts, sorting, filtering, expanding or synchronizing the tree never
runs recognition or writes saved data.
