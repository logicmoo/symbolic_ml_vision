import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { PrologClauseExplorer } from "./upstream/packages/omega_vision_ui/src/components/PrologClauseExplorer";
import {
  groupClausesByPredicate, parseSources, sourceTextForSyntax, prepareSources, hasSources, analysisFor,
  type SourceFile, type ExplorerSyntax,
} from "./server-model";
import "./explorer.css";
import "./host.css";

type OutputSource = Omit<SourceFile, "dialect"> & { dialect?: "prolog" | "metta" | "json" };
type HostOptions = {
  getSources: () => OutputSource[];
  onSourcesChange?: (sources: SourceFile[]) => void;
};

function supportedSource(source: OutputSource) {
  return /\.(pl|prolog|metta|json)$/i.test(source.name);
}
function modelSources(sources: OutputSource[]): SourceFile[] {
  return sources.filter(supportedSource).map(source => ({
    ...source, dialect: source.dialect === "json" ? undefined : source.dialect,
  }));
}

function canRenderSource(source: OutputSource, syntax: string) {
  return ["prolog", "metta", "json"].includes(syntax) && supportedSource(source);
}

function renderSource(source: OutputSource, syntax: ExplorerSyntax) {
  const [value] = modelSources([source]);
  if (!value) throw new Error("Unsupported source file");
  return sourceTextForSyntax(value, [], syntax);
}

function mount(container: HTMLElement, options: HostOptions) {
  const root = createRoot(container);
  let destroyed = false;
  let request = 0;
  const render = () => {
    if (destroyed) return;
    const generation = ++request;
    const sources = modelSources(options.getSources());
    void prepareSources(sources).then(() => {
      if (destroyed || generation !== request) return;
      root.render(createElement("div", { className: "standalone-clause-explorer" },
        createElement(PrologClauseExplorer, {
          sources,
          initialSyntax: "metta",
          onSourcesChange: options.onSourcesChange,
          onReloadSource: () => render(),
        }),
      ));
    }).catch(error => {
      if (!destroyed && generation === request) root.render(createElement("p", { role: "alert" },
        error instanceof Error ? error.message : String(error)));
    });
  };
  render();
  return {
    render,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      root.unmount();
    },
  };
}

declare global {
  interface Window {
    ClauseExplorer: {
      mount: typeof mount;
      canRenderSource: typeof canRenderSource;
      renderSource: typeof renderSource;
      parseSources: typeof parseSources;
      groupClausesByPredicate: typeof groupClausesByPredicate;
      implementation: string;
      prepareSources: (sources: OutputSource[]) => Promise<void>;
      hasSources: (sources: OutputSource[]) => boolean;
      sourceNodes: (source: OutputSource, syntax: ExplorerSyntax) => ReturnType<typeof analysisFor>["viewNodes"][ExplorerSyntax];
    };
  }
}
window.ClauseExplorer = {
  mount, canRenderSource, renderSource, parseSources, groupClausesByPredicate,
  prepareSources: sources => prepareSources(modelSources(sources)),
  hasSources: sources => hasSources(modelSources(sources)),
  sourceNodes: (source, syntax) => analysisFor(source).viewNodes[syntax],
  implementation: "original-workbench-python-syntax",
};
