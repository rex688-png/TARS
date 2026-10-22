import type { ModelProviderDefinition } from "./plugin-settings";
import { TarsProviderRegistry } from "./tars-provider-registry";
import { Injectable } from "@angular/core";
import { combineLatest, filter, map, merge, Observable, of, startWith, shareReplay } from "rxjs";

import { ChatMessage, ChatService } from "./chat.service";
import { Config, ConfigService } from "./config.service";
import { LoggingService } from "./logging.service";
import { PngTuberService } from "./pngtuber.service";
import { ProjectionsService } from "./projections.service";
import { TarsApplicationCoordinator } from "./tars-application-coordinator.service";
import { BaseMessage, TauriService } from "./tauri.service";
import {
    TarsComponentHealth,
    TarsConversationEntry,
    TarsConversationRole,
    TarsEliteContext,
    TarsExternalIntegrationState,
    TarsInteractionState,
    TarsProviderInstallationState,
    TarsProviderSelection,
    TarsRuntimeConfigurationSummary,
    TarsRuntimeState,
} from "./tars-runtime-facade.models";

type UnknownRecord = Record<string, unknown>;
interface RuntimeComponentsMessage extends BaseMessage {
    type: "runtime_components";
    models: boolean;
    stt: boolean;
    tts: boolean;
    memory: boolean;
}

@Injectable({ providedIn: "root" })
export class TarsRuntimeFacade {
    readonly applicationState$ = this.applicationCoordinator.state$;

    readonly initializedComponents$: Observable<RuntimeComponentsMessage | null> = merge(
        this.applicationState$.pipe(
            filter((state) => state !== "running"),
            map(() => null),
        ),
        this.tauriService.output$.pipe(
            filter((message): message is RuntimeComponentsMessage => message.type === "runtime_components"),
        ),
    ).pipe(startWith(null), shareReplay(1));

    readonly interactionState$: Observable<TarsInteractionState> = this.pngTuberService.action$.pipe(
        map((phase) => ({ phase, derived: phase === "thinking" })),
    );

    readonly runtimeState$: Observable<TarsRuntimeState> = combineLatest([
        this.applicationState$,
        this.interactionState$,
    ]).pipe(map(([application, interaction]) => ({ application, interaction })));

    readonly conversation$: Observable<readonly TarsConversationEntry[]> = this.chatService.chatHistory$.pipe(
        map((messages) => messages.map((message) => this.toConversationEntry(message))),
    );

    readonly configuration$: Observable<TarsRuntimeConfigurationSummary | null> = this.configService.config$.pipe(
        map((config) => config ? this.toConfigurationSummary(config) : null),
    );

    readonly eliteContext$: Observable<TarsEliteContext> = combineLatest([
        this.projectionsService.commander$,
        this.projectionsService.location$,
        this.projectionsService.shipInfo$,
        this.projectionsService.target$,
    ]).pipe(
        map(([commander, location, ship, target]) => this.toEliteContext(commander, location, ship, target)),
    );

    readonly providerInstallation$: Observable<TarsProviderInstallationState | null> =
        this.configService.provider_install_status$.pipe(
            map((status) => status ? ({
                providerKey: status.provider_key,
                label: status.label,
                phase: status.state,
                downloadedBytes: status.downloaded_bytes,
                totalBytes: status.total_bytes,
                percent: status.percent,
                restartRequired: status.restart_required,
                ...(status.error ? { error: status.error } : {}),
            }) : null),
        );

    readonly alerts$ = this.loggingService.logs$.pipe(
        map((logs) => logs
            .filter((entry) => entry.prefix === "warn" || entry.prefix === "error")
            .map((entry) => ({
                severity: entry.prefix as "warn" | "error",
                timestamp: entry.timestamp,
                message: entry.message,
            }))),
    );

    readonly health$: Observable<readonly TarsComponentHealth[]> = combineLatest([
        this.applicationState$,
        this.configService.config$,
        this.configService.provider_install_status$,
        this.projectionsService.currentStatus$,
        this.initializedComponents$,
        this.configService.plugin_model_providers$ ?? of([]),
    ]).pipe(
        map(([application, config, installation, currentStatus, components, providers]) =>
            this.buildHealth(application, config, installation?.state, currentStatus, components, providers)),
    );

    /** No external integration is claimed until a real adapter reports it. */
    readonly externalIntegrations$: Observable<readonly TarsExternalIntegrationState[]> =
        of([]);

    constructor(
        private readonly applicationCoordinator: TarsApplicationCoordinator,
        private readonly pngTuberService: PngTuberService,
        private readonly chatService: ChatService,
        private readonly configService: ConfigService,
        private readonly projectionsService: ProjectionsService,
        private readonly loggingService: LoggingService,
        private readonly tauriService: TauriService,
    ) {}

    initializeApplication(): Promise<void> {
        return this.applicationCoordinator.initialize();
    }

    attachToExistingApplication(): Promise<void> {
        return this.applicationCoordinator.attachToExistingRuntime();
    }

    startAssistant(): Promise<void> {
        return this.applicationCoordinator.startAssistant();
    }

    returnToConfiguration(): Promise<void> {
        return this.applicationCoordinator.returnToConfiguration();
    }

    private toConversationEntry(message: ChatMessage): TarsConversationEntry {
        return {
            id: `${message.index}:${message.timestamp}`,
            timestamp: message.timestamp,
            role: this.toConversationRole(message.role),
            text: message.message,
            ...(message.processingText ? { activityDetail: message.processingText } : {}),
        };
    }

    private toConversationRole(role: string): TarsConversationRole {
        switch (role) {
            case "cmdr": return "commander";
            case "covas": return "tars";
            case "action":
            case "plugin": return "activity";
            case "warning": return "warning";
            case "error": return "error";
            default: return "system";
        }
    }

    private toConfigurationSummary(config: Config): TarsRuntimeConfigurationSummary {
        return {
            llm: this.providerSelection(
                config.llm_provider,
                config.llm_model_name,
                config.llm_api_key || config.api_key,
            ),
            agent: this.providerSelection(
                config.agent_llm_provider,
                config.agent_llm_model_name,
                config.agent_llm_api_key || config.api_key,
            ),
            vision: {
                ...this.providerSelection(
                    config.vision_provider,
                    config.vision_model_name,
                    config.vision_api_key || config.api_key,
                ),
                enabled: config.vision_var && config.vision_provider !== "none",
            },
            stt: this.providerSelection(
                config.stt_provider,
                config.stt_model_name,
                config.stt_api_key || config.api_key,
            ),
            tts: this.providerSelection(
                config.tts_provider,
                config.tts_model_name,
                config.tts_api_key || config.api_key,
            ),
            memory: {
                ...this.providerSelection(
                    config.embedding_provider,
                    config.embedding_model_name,
                    config.embedding_api_key || config.api_key,
                ),
                enabled: config.embedding_provider !== "none",
            },
            pttMode: config.ptt_var,
        };
    }

    private providerSelection(provider: string, model: string, credential: string): TarsProviderSelection {
        const requiresCredential = !provider.startsWith("plugin:")
            && provider !== "local-ai-server"
            && provider !== "none";
        return {
            provider,
            label: TarsProviderRegistry.label(provider),
            model,
            configured: provider !== "none" && (!requiresCredential || Boolean(credential)),
        };
    }

    private toEliteContext(
        commanderValue: unknown,
        locationValue: unknown,
        shipValue: unknown,
        targetValue: unknown,
    ): TarsEliteContext {
        const commander = this.asRecord(commanderValue);
        const location = this.asRecord(locationValue);
        const ship = this.asRecord(shipValue);
        const target = this.asRecord(targetValue);
        const values = [commander, location, ship, target];
        return {
            available: values.some((value) => Object.keys(value).length > 0),
            ...this.optionalString("commanderName", commander["Commander"] ?? commander["Name"]),
            ...this.optionalString("systemName", location["StarSystem"] ?? location["SystemName"]),
            ...this.optionalString("bodyName", location["Body"] ?? location["BodyName"]),
            ...this.optionalString("shipType", ship["Model"] ?? ship["Type"] ?? ship["Ship"] ?? ship["ShipType"]),
            ...this.optionalString("shipIdent", ship["ShipIdent"]),
            ...this.optionalString("targetName", target["Name"] ?? target["Ship"]),
        };
    }

    private buildHealth(
        application: TarsRuntimeState["application"],
        config: Config | null,
        installationState: string | undefined,
        currentStatus: unknown,
        components: RuntimeComponentsMessage | null,
        providers: readonly ModelProviderDefinition[],
    ): readonly TarsComponentHealth[] {
        const providerBusy = ["downloading", "verifying", "extracting"].includes(installationState ?? "");
        const backendStatus = application === "running"
            ? "ready"
            : application === "error" ? "error" : application === "stopped" || application === "configuring" ? "unavailable" : "busy";
        const configuredUnknown = (enabled: boolean): TarsComponentHealth["status"] =>
            enabled ? "available" : "unavailable";
        const observed = (key: keyof Omit<RuntimeComponentsMessage, "type">, enabled: boolean): TarsComponentHealth["status"] =>
            components && application === "running" ? (components[key] ? "ready" : "unavailable")
                : application === "starting" || application === "restarting" ? "busy" : configuredUnknown(enabled);
        const available = (provider: string | undefined): boolean => Boolean(provider && provider !== 'none' &&
            (!provider.startsWith('plugin:') || providers.some(item => provider === `plugin:${item.plugin_guid}:${item.id}`)));
        const evidence = components && application === "running" ? "observed" : "configured";
        const hasStatus = Object.keys(this.asRecord(currentStatus)).length > 0;

        return [
            this.health("backend", backendStatus, "observed", `Application is ${application}.`),
            this.health("models", observed("models", available(config?.llm_provider)), evidence,
                components ? "Model initialization reported by runtime." : "Waiting for model initialization report."),
            this.health("stt", observed("stt", available(config?.stt_provider)), evidence,
                components ? "Speech initialization reported by runtime." : "Waiting for speech initialization report."),
            this.health("tts", observed("tts", available(config?.tts_provider)), evidence,
                components ? "Voice initialization reported by runtime." : "Waiting for voice initialization report."),
            this.health("audio", config ? "unknown" : "unavailable", config ? "configured" : "not-exposed",
                "Audio-device health is not exposed."),
            this.health("provider-installation",
                installationState === "failed" ? "error" : providerBusy ? "busy" : installationState === "installed" ? "ready" : "unknown",
                installationState ? "observed" : "not-exposed",
                installationState ? `Provider installation is ${installationState}.` : "No provider installation state reported."),
            this.health("elite-journal", "unknown", "not-exposed", "Journal freshness and connection health are not exposed."),
            this.health("elite-status", hasStatus ? "ready" : "unknown", hasStatus ? "observed" : "not-exposed",
                hasStatus ? "Status state has been received; file freshness is not exposed." : "No Status state received."),
            this.health("plugins", "unknown", "not-exposed", "Per-plugin runtime health is not exposed."),
            this.health("memory", observed("memory", available(config?.embedding_provider)), evidence,
                components ? "Embedding initialization reported by runtime." : "Waiting for embedding initialization report."),
            this.health("vision", configuredUnknown(Boolean(config?.vision_var && config.vision_provider !== "none")),
                config ? "configured" : "not-exposed", "Vision configuration is known; capture health is not exposed."),
        ];
    }

    private health(
        component: TarsComponentHealth["component"],
        status: TarsComponentHealth["status"],
        evidence: TarsComponentHealth["evidence"],
        detail: string,
    ): TarsComponentHealth {
        return { component, status, evidence, detail };
    }

    private asRecord(value: unknown): UnknownRecord {
        return value !== null && typeof value === "object" && !Array.isArray(value)
            ? value as UnknownRecord
            : {};
    }

    private optionalString<Key extends keyof TarsEliteContext>(
        key: Key,
        value: unknown,
    ): Partial<Pick<TarsEliteContext, Key>> {
        return typeof value === "string" && value.trim() ? { [key]: value } as Pick<TarsEliteContext, Key> : {};
    }
}
