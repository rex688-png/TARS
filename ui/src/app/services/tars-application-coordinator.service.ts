import { Injectable } from "@angular/core";
import { MatSnackBar } from "@angular/material/snack-bar";
import { BehaviorSubject, Subscription } from "rxjs";

import { ChatService } from "./chat.service";
import { Config, ConfigService } from "./config.service";
import { LoggingService } from "./logging.service";
import { TauriService } from "./tauri.service";

export type TarsApplicationState =
    | "stopped"
    | "starting"
    | "configuring"
    | "running"
    | "restarting"
    | "error";

/**
 * Owns renderer-side application lifecycle orchestration.
 *
 * Electron remains the process owner and TauriService remains the transport.
 * Keeping this coordination out of a visual component allows another shell to
 * attach without creating a second backend or changing the runtime protocol.
 */
@Injectable({ providedIn: "root" })
export class TarsApplicationCoordinator {
    private readonly stateSubject = new BehaviorSubject<TarsApplicationState>("stopped");
    readonly state$ = this.stateSubject.asObservable();

    private initialized = false;
    private ownsLifecycle = false;
    private hasAutoStarted = false;
    private restartInFlight = false;
    private currentConfig: Config | null = null;
    private readonly subscriptions = new Subscription();

    constructor(
        private readonly tauriService: TauriService,
        private readonly configService: ConfigService,
        private readonly loggingService: LoggingService,
        private readonly chatService: ChatService,
        private readonly snackBar: MatSnackBar,
    ) {
        this.subscriptions.add(
            this.tauriService.runMode$.subscribe((mode) => {
                if (!this.initialized) {
                    return;
                }
                if (this.restartInFlight && mode === "starting") {
                    return;
                }
                if (mode === "configuring") {
                    this.restartInFlight = false;
                }
                this.stateSubject.next(mode);
            }),
        );

        this.subscriptions.add(
            this.configService.config$.subscribe((config) => {
                this.currentConfig = config;
                this.maybeAutoStart();
            }),
        );
    }

    /** Start the backend process once for the current renderer application. */
    async initialize(): Promise<void> {
        if (this.initialized) {
            return;
        }
        this.initialized = true;
        this.ownsLifecycle = true;
        this.stateSubject.next("starting");
        try {
            await this.tauriService.runExe();
            // Remote transports may already have replayed their configuration
            // before this coordinator is initialized.
            this.maybeAutoStart();
        } catch (error) {
            this.stateSubject.next("error");
            console.error("Failed to initialize TARS backend:", error);
        }
    }

    /** Attach a secondary renderer without starting or restarting the backend. */
    async attachToExistingRuntime(): Promise<void> {
        if (this.initialized) {
            return;
        }
        this.initialized = true;
        this.stateSubject.next("starting");
        try {
            await this.tauriService.requestRuntimeState();
        } catch (error) {
            this.stateSubject.next("error");
            console.error("Failed to attach to the existing TARS backend:", error);
        }
    }

    /** Preserve the existing overlay -> session clear -> start command order. */
    async startAssistant(): Promise<void> {
        this.requireLifecycleOwnership("start TARS");
        try {
            this.stateSubject.next("starting");
            if (this.shouldCreateOverlay(this.currentConfig)) {
                await this.createOverlay(this.currentConfig!);
            }
            this.loggingService.clearLogs();
            this.chatService.clearChat();
            await this.tauriService.send_start_signal();
        } catch (error) {
            this.stateSubject.next("error");
            console.error("Failed to start:", error);
        }
    }

    /** Return to configuration by closing overlays and restarting the backend. */
    async returnToConfiguration(): Promise<void> {
        this.requireLifecycleOwnership("restart the TARS backend");
        try {
            this.restartInFlight = true;
            this.stateSubject.next("restarting");
            await this.destroyOverlay();
            await this.tauriService.restart_process();
        } catch (error) {
            this.restartInFlight = false;
            this.stateSubject.next("error");
            console.error("Failed to stop:", error);
        }
    }

    getCurrentState(): TarsApplicationState {
        return this.stateSubject.getValue();
    }

    private maybeAutoStart(): void {
        if (
            this.initialized
            && this.ownsLifecycle
            && this.currentConfig?.cn_autostart
            && this.stateSubject.getValue() !== "running"
            && !this.hasAutoStarted
        ) {
            this.hasAutoStarted = true;
            console.log("Started automatically.");
            void this.startAssistant();
        }
    }

    private requireLifecycleOwnership(action: string): void {
        if (!this.ownsLifecycle) {
            throw new Error(`This renderer is attached read-only and cannot ${action}.`);
        }
    }

    private shouldCreateOverlay(config: Config | null): config is Config {
        return Boolean(
            config
            && config.overlay_mode !== "disabled"
            && (config.overlay_show_avatar || config.overlay_show_chat || config.overlay_show_hud),
        );
    }

    private async createOverlay(config: Config): Promise<void> {
        try {
            await this.tauriService.createOverlay({
                alwaysOnTop: true,
                screenId: config.overlay_screen_id ?? -1,
                mode: config.overlay_mode ?? "desktop",
                standaloneTransparent: config.overlay_standalone_transparent ?? true,
                standaloneBackgroundColor: config.overlay_standalone_background_color ?? "#000000",
                vrSizeMeters: config.overlay_vr_size_meters ?? 0.9,
                vrAnchor: config.overlay_vr_anchor ?? "head",
                vrHorizontalOffset: config.overlay_vr_horizontal_offset ?? 0,
                vrVerticalOffset: config.overlay_vr_vertical_offset ?? 0,
                vrDistanceOffset: config.overlay_vr_distance_offset ?? 0,
                vrTiltDegrees: config.overlay_vr_tilt_degrees ?? 0,
                vrCurvature: config.overlay_vr_curvature ?? 0,
            });
        } catch (error) {
            console.error("Failed to create overlay:", error);
            this.snackBar.open(
                error instanceof Error ? error.message : "The overlay could not be created.",
                "OK",
                { duration: 7000 },
            );
        }
    }

    private async destroyOverlay(): Promise<void> {
        try {
            await this.tauriService.destroyOverlay();
        } catch (error) {
            // Preserve the existing behavior: an overlay cleanup failure must not
            // prevent the backend from returning to configuration mode.
            console.error("Failed to destroy overlay:", error);
        }
    }
}
