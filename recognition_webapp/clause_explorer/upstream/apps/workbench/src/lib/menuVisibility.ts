export type MenuFamily = "omega" | "workbench" | "common";

export type MenuVisibilityPreferences = {
  showOmegaVision: boolean;
  showWorkbench: boolean;
  menuItemVisibility: Record<string, boolean>;
};

export type VisibilityMenuItem = {
  id: string;
  label: string;
  group: string;
  family: MenuFamily;
  view: string;
  subview?: string;
  action?: string;
  pluginId?: string;
  pluginPageId?: string;
};

type NavigationSection = {
  group: string;
  items: ReadonlyArray<{ view: string; subview?: string; action?: string; label: string }>;
};
type WorkflowEntry = { id: string; routeView: string; label: string; menuGroup?: string; renderer: string };
type PluginEntry = { pluginId: string; id: string; label: string; group: string };

export const DEFAULT_MENU_VISIBILITY: MenuVisibilityPreferences = {
  showOmegaVision: true,
  showWorkbench: true,
  menuItemVisibility: {},
};

export function normalizeMenuSubview(subview?: string): string | undefined {
  return subview === "frames" || subview === "finish" || subview === "advanced" ? "sources" : subview;
}

export function pageMenuId(view: string, subview?: string, action?: string): string {
  const normalized = normalizeMenuSubview(subview);
  return `page:${encodeURIComponent(view)}${normalized ? `:${encodeURIComponent(normalized)}` : ""}${action ? `:${encodeURIComponent(action)}` : ""}`;
}

export const workflowMenuId = (id: string) => `workflow:${encodeURIComponent(id)}`;
export const pluginMenuId = (pluginId: string, id: string) => `plugin:${encodeURIComponent(pluginId)}:${encodeURIComponent(id)}`;
export const menuFamilyForGroup = (group: string): MenuFamily => group === "OMEGA VISION" ? "omega" : "workbench";

export function buildVisibilityMenu(
  sections: ReadonlyArray<NavigationSection>,
  workflows: ReadonlyArray<WorkflowEntry>,
  plugins: ReadonlyArray<PluginEntry>,
): VisibilityMenuItem[] {
  return [
    ...sections.flatMap(section => section.items.map(item => ({
      ...item,
      id: pageMenuId(item.view, item.subview, item.action),
      group: section.group,
      family: item.view === "setup" ? "common" as const : menuFamilyForGroup(section.group),
    }))),
    ...workflows.map(item => {
      const group = item.menuGroup || (item.renderer.startsWith("arc3_") ? "OMEGA VISION" : "WORKFLOWS");
      return { id: workflowMenuId(item.id), label: item.label, view: item.routeView, group, family: menuFamilyForGroup(group) };
    }),
    ...plugins.map(item => ({
      id: pluginMenuId(item.pluginId, item.id), label: item.label, view: "pluginPage",
      pluginId: item.pluginId, pluginPageId: item.id, group: item.group, family: menuFamilyForGroup(item.group),
    })),
  ];
}

export function isMenuFamilyVisible(family: MenuFamily, preferences: MenuVisibilityPreferences): boolean {
  return family === "common" || (family === "omega" ? preferences.showOmegaVision : preferences.showWorkbench);
}

export function isMenuItemVisible(item: VisibilityMenuItem, preferences: MenuVisibilityPreferences): boolean {
  return isMenuFamilyVisible(item.family, preferences) && preferences.menuItemVisibility[item.id] !== false;
}

export type MenuRoute = { view: string; subview?: string; pluginId?: string; pluginPageId?: string };
const RELATED_ROUTES: Record<string, string> = {
  workflows: "canvas", editor: "canvas", workflowRuns: "canvas", prompts: "sourceCode",
  runtimeContexts: "states", artifacts: "knowledgeArtifacts", evidence: "events", checks: "canvas",
};

export function menuItemForRoute(items: ReadonlyArray<VisibilityMenuItem>, route: MenuRoute): VisibilityMenuItem {
  const view = items.some(item => item.view === route.view) ? route.view : RELATED_ROUTES[route.view] || route.view;
  const subview = view === "videoImport" ? normalizeMenuSubview(route.subview || "sources") : route.subview;
  const matches = items.filter(candidate => !candidate.action && candidate.view === view && (
    view === "pluginPage"
      ? candidate.pluginId === route.pluginId && candidate.pluginPageId === route.pluginPageId
      : !candidate.subview || candidate.subview === subview
  ));
  const item = matches.find(candidate => candidate.subview === subview) || matches[0];
  return item || {
    id: view === "pluginPage" ? pluginMenuId(route.pluginId || "", route.pluginPageId || "") : pageMenuId(view, subview),
    view, subview, label: view,
    family: view === "setup" || view === "changeWorkspace" ? "common" : view === "videoImport" || view === "visualSequences" ? "omega" : "workbench",
    group: "",
  };
}

export function isMenuRouteVisible(items: ReadonlyArray<VisibilityMenuItem>, route: MenuRoute, preferences: MenuVisibilityPreferences): boolean {
  // Recovery is not hideable, even when its ordinary navigation entry is.
  if (route.view === "setup" || route.view === "changeWorkspace") return true;
  if (!isMenuItemVisible(menuItemForRoute(items, route), preferences)) return false;
  // Both routes host the same rich Recognition surface; the new name is not a visibility bypass.
  return route.view !== "visualSequences"
    || isMenuItemVisible(menuItemForRoute(items, { view: "videoImport", subview: "recognition" }), preferences);
}

export function parseMenuVisibility(candidate: unknown): MenuVisibilityPreferences {
  if (!candidate || typeof candidate !== "object") return DEFAULT_MENU_VISIBILITY;
  const fields = candidate as Record<string, unknown>;
  const choices = fields.menuItemVisibility;
  return {
    showOmegaVision: fields.showOmegaVision !== false,
    showWorkbench: fields.showWorkbench !== false,
    menuItemVisibility: choices && typeof choices === "object" && !Array.isArray(choices)
      ? Object.fromEntries(Object.entries(choices).filter((entry): entry is [string, boolean] => typeof entry[1] === "boolean"))
      : {},
  };
}
