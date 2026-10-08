import { TarsApplicationState } from "./tars-application-coordinator.service";

export type TarsInteractionPhase = "idle" | "listening" | "thinking" | "speaking" | "acting";

export interface TarsInteractionState {
    phase: TarsInteractionPhase;
    /** Thinking is currently inferred from conversation events, not model telemetry. */
    derived: boolean;
}

export type TarsConversationRole = "commander" | "tars" | "activity" | "system" | "warning" | "error";

export interface TarsConversationEntry {
    id: string;
    timestamp: string;
    role: TarsConversationRole;
    text: string;
    activityDetail?: string;
}

export interface TarsProviderSelection {
    provider: string;
    label: string;
    model: string;
    configured: boolean;
}

/** Secret-free configuration summary for general-purpose frontend use. */
export interface TarsRuntimeConfigurationSummary {
    llm: TarsProviderSelection;
    agent: TarsProviderSelection;
    vision: TarsProviderSelection & { enabled: boolean };
    stt: TarsProviderSelection;
    tts: TarsProviderSelection;
    memory: TarsProviderSelection & { enabled: boolean };
    pttMode: "voice_activation" | "push_to_talk" | "push_to_mute" | "toggle";
}

export interface TarsEliteContext {
    available: boolean;
    commanderName?: string;
    systemName?: string;
    bodyName?: string;
    shipType?: string;
    shipIdent?: string;
    targetName?: string;
}

export interface TarsProviderInstallationState {
    providerKey: string;
    label: string;
    phase: "downloading" | "verifying" | "extracting" | "installed" | "failed";
    downloadedBytes: number;
    totalBytes: number;
    percent: number;
    restartRequired: boolean;
    error?: string;
}

export type TarsHealthStatus = "ready" | "available" | "busy" | "unavailable" | "error" | "unknown";
export type TarsHealthEvidence = "observed" | "configured" | "not-exposed";

export type TarsComponentId =
    | "backend"
    | "models"
    | "stt"
    | "tts"
    | "audio"
    | "provider-installation"
    | "elite-journal"
    | "elite-status"
    | "plugins"
    | "memory"
    | "vision";

export interface TarsComponentHealth {
    component: TarsComponentId;
    status: TarsHealthStatus;
    evidence: TarsHealthEvidence;
    detail: string;
}

/**
 * Reserved source-neutral contract for recovered integrations. Task 6A does not
 * create Observatory data or assume an external integration's transport.
 */
export interface TarsExternalIntegrationState {
    id: string;
    label: string;
    status: TarsHealthStatus;
    lastEventAt?: string;
    detail?: string;
}

export interface TarsRuntimeState {
    application: TarsApplicationState;
    interaction: TarsInteractionState;
}
