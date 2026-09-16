import { useSyncExternalStore } from "react";
import { DEFAULT_MENU_VISIBILITY, parseMenuVisibility, type MenuVisibilityPreferences } from "./menuVisibility";

export type ResourceSourceFileControlsPlacement = "above" | "below";

export type GenerationsView = "fullest" | "full" | "compact";

export type UserUiPreferences = MenuVisibilityPreferences & {
  redirectDefaultWorkspaceToArc3: boolean;
  resourceSourceFileControlsPlacement: ResourceSourceFileControlsPlacement;
  /** Whether the per-page "UI Config" strip (PageUiTools) is shown at all. */
  pageUiToolsVisible: boolean;
  /** Whether page-generation strips (version steppers) are shown at all. */
  generationsVisible: boolean;
  /** The one shared view of the generations notice when visible. */
  generationsView: GenerationsView;
};

export const USER_UI_PREFERENCES_STORAGE_KEY = "metta-workbench.user-ui-preferences.v1";
export const USER_UI_PREFERENCES_CHANGED_EVENT = "workbench:user-ui-preferences-changed";

export const DEFAULT_USER_UI_PREFERENCES: UserUiPreferences = {
  ...DEFAULT_MENU_VISIBILITY,
  redirectDefaultWorkspaceToArc3: true,
  resourceSourceFileControlsPlacement: "above",
  pageUiToolsVisible: true,
  generationsVisible: true,
  generationsView: "fullest",
};

let cachedSource: string | null | undefined;
let cachedPreferences = DEFAULT_USER_UI_PREFERENCES;

function parseUserUiPreferences(source: string | null): UserUiPreferences {
  if (!source) return DEFAULT_USER_UI_PREFERENCES;
  try {
    const candidate = JSON.parse(source) as Partial<UserUiPreferences>;
    return {
      ...parseMenuVisibility(candidate),
      redirectDefaultWorkspaceToArc3: candidate.redirectDefaultWorkspaceToArc3 !== false,
      resourceSourceFileControlsPlacement:
        candidate.resourceSourceFileControlsPlacement === "below" ? "below" : "above",
      pageUiToolsVisible: candidate.pageUiToolsVisible !== false,
      generationsVisible: candidate.generationsVisible !== false,
      generationsView:
        candidate.generationsView === "full" || candidate.generationsView === "compact"
          ? candidate.generationsView
          : "fullest",
    };
  } catch {
    return DEFAULT_USER_UI_PREFERENCES;
  }
}

export function readUserUiPreferences(): UserUiPreferences {
  if (typeof window === "undefined") return DEFAULT_USER_UI_PREFERENCES;
  const source = window.localStorage.getItem(USER_UI_PREFERENCES_STORAGE_KEY);
  if (source !== cachedSource) {
    cachedSource = source;
    cachedPreferences = parseUserUiPreferences(source);
  }
  return cachedPreferences;
}

export function writeUserUiPreferences(preferences: UserUiPreferences): void {
  if (typeof window === "undefined") return;
  const source = JSON.stringify(preferences);
  window.localStorage.setItem(USER_UI_PREFERENCES_STORAGE_KEY, source);
  cachedSource = source;
  cachedPreferences = preferences;
  window.dispatchEvent(new CustomEvent(USER_UI_PREFERENCES_CHANGED_EVENT));
}

export function updateUserUiPreferences(patch: Partial<UserUiPreferences>): void {
  const current = readUserUiPreferences();
  writeUserUiPreferences({
    ...current,
    ...patch,
    menuItemVisibility: { ...current.menuItemVisibility, ...patch.menuItemVisibility },
  });
}

function subscribeUserUiPreferences(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const onStorage = (event: StorageEvent) => {
    if (!event.key || event.key === USER_UI_PREFERENCES_STORAGE_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(USER_UI_PREFERENCES_CHANGED_EVENT, listener);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(USER_UI_PREFERENCES_CHANGED_EVENT, listener);
  };
}

export function useUserUiPreferences(): UserUiPreferences {
  return useSyncExternalStore(subscribeUserUiPreferences, readUserUiPreferences, () => DEFAULT_USER_UI_PREFERENCES);
}
