export type TarsShellView = "tars" | "exploration" | "storage" | "settings";

/** Legacy runtime UI commands must never reintroduce the old tab hierarchy. */
export function viewForUiCommand(current: TarsShellView, show?: string): TarsShellView {
    if (!show || show === "search") return current;
    const target: Record<string, TarsShellView> = {
        chat: "tars", status: "tars", station: "tars", tasks: "tars",
        navigation: "exploration", storage: "storage", logbook: "settings",
        actions: "settings",
    };
    return target[show] ?? current;
}
