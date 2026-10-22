export type EliteDataStatus = "ELITE LIVE" | "LAST KNOWN" | "ELITE OFFLINE";
export type TarsActivityStatus = "OFFLINE" | "STARTING" | "READY" | "LISTENING" | "THINKING" | "SPEAKING" | "ACTING" | "ERROR";

export function tarsActivityStatus(application: string, interaction: string): TarsActivityStatus {
    if (application === "error") return "ERROR";
    if (application === "stopped" || application === "configuring") return "OFFLINE";
    if (application !== "running") return "STARTING";
    switch (interaction) {
        case "listening": return "LISTENING";
        case "thinking": return "THINKING";
        case "speaking": return "SPEAKING";
        case "acting": return "ACTING";
        default: return "READY";
    }
}

/** A recent, non-historic journal event proves live activity; cached state alone does not. */
export function eliteDataStatus(hasContext: boolean, lastLiveEventAt: number | null, now = Date.now()): EliteDataStatus {
    if (lastLiveEventAt !== null && now >= lastLiveEventAt && now - lastLiveEventAt < 90_000) return "ELITE LIVE";
    return hasContext ? "LAST KNOWN" : "ELITE OFFLINE";
}
