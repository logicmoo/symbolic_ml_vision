// The standalone app has no Workbench preferences store.
export function useUserUiPreferences() {
  return { resourceSourceFileControlsPlacement: "above" as const };
}
