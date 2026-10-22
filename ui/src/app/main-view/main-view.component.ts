import { ChatService } from '../services/chat.service';
import { filter, firstValueFrom, take, timeout } from 'rxjs';
import { TarsActionApprovalComponent } from '../components/tars-action-approval/tars-action-approval.component';
import { needsSetup } from '../services/tars-setup-state';
import { Component, OnDestroy, OnInit, ViewChild } from "@angular/core";
import { CommonModule } from "@angular/common";
import { MatButtonModule } from "@angular/material/button";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { Subscription } from "rxjs";

import { ChatContainerComponent } from "../components/chat-container/chat-container.component";
import { ActionsContainerComponent } from "../components/actions-container/actions-container.component";
import { InputContainerComponent } from "../components/input-container/input-container.component";
import { MemoriesContainerComponent } from "../components/memories-container/memories-container.component";
import { LogContainerComponent } from "../components/log-container/log-container.component";
import { SettingsMenuComponent } from "../components/settings-menu/settings-menu.component";
import { TarsExplorationComponent } from "../components/tars-exploration/tars-exploration.component";
import { TarsStorageComponent } from "../components/tars-storage/tars-storage.component";
import { ConfigService } from "../services/config.service";
import { PolicyService } from "../services/policy.service";
import { ProjectionsService } from "../services/projections.service";
import { TarsApplicationCoordinator, TarsApplicationState } from "../services/tars-application-coordinator.service";
import { TarsRuntimeFacade } from "../services/tars-runtime-facade.service";
import { UIService } from "../services/ui.service";
import { EventService } from "../services/event.service";
import { TauriService } from "../services/tauri.service";
import { eliteDataStatus, tarsActivityStatus } from "./tars-status";
import { interval } from "rxjs";
import { TarsShellView, viewForUiCommand } from "./tars-shell-navigation";


@Component({
    selector: "app-main-view",
    standalone: true,
    imports: [TarsActionApprovalComponent,CommonModule, MatButtonModule, MatIconModule, MatProgressBarModule,
        ChatContainerComponent, InputContainerComponent, SettingsMenuComponent,
        ActionsContainerComponent, MemoriesContainerComponent, LogContainerComponent,
        TarsExplorationComponent, TarsStorageComponent],
    templateUrl: "./main-view.component.html",
    styleUrl: "./main-view.component.css",
})
export class MainViewComponent implements OnInit, OnDestroy {
    @ViewChild(SettingsMenuComponent) private settingsMenu?: SettingsMenuComponent;

    readonly runtime = this.runtimeFacade;
    readonly keybinds$ = this.configService.keybinds$;
    readonly avatarUrl = "assets/Obraz%20ChatGPT%2028%20wrz%202026%2C%2021_39_52.png";
    readonly logoUrl = "assets/tars-logo-horizontal.svg";
    readonly commitHash = this.tauriService.commitHash;
    selectedView: TarsShellView = "tars";
    runMode: TarsApplicationState = "starting";
    usageDisclaimerAccepted = false;
    isQuestEditorOpen = false;
    diagnosticsOpen = false;
    logbookOpen = false;
    logsOpen = false;
    settingsCategory = 0;
    isInCombat = false;
    eliteDataLabel: "ELITE LIVE" | "LAST KNOWN" | "ELITE OFFLINE" = "ELITE OFFLINE";
    private lastLiveEliteAt: number | null = null;
    private hasEliteContext = false;
    private readonly subscriptions = new Subscription();

    constructor(
        private readonly applicationCoordinator: TarsApplicationCoordinator,
        private readonly runtimeFacade: TarsRuntimeFacade,
        private readonly configService: ConfigService,
        private readonly projectionsService: ProjectionsService,
        private readonly policyService: PolicyService,
        private readonly uiService: UIService,
        private readonly eventService: EventService,
        private readonly tauriService: TauriService,
        private readonly chatService: ChatService,
    ) {}

    ngOnInit(): void {
        let setupChecked = false;
        this.subscriptions.add(this.configService.config$.subscribe(config => {
            if (config && !setupChecked) { setupChecked = true; if (needsSetup(config)) this.selectView("settings"); }
        }));
        this.subscriptions.add(this.policyService.usageDisclaimerAccepted$.subscribe(
            (accepted) => this.usageDisclaimerAccepted = accepted,
        ));
        this.subscriptions.add(this.applicationCoordinator.state$.subscribe((mode) => {
            this.runMode = mode;
        }));
        this.subscriptions.add(this.configService.system$.subscribe((system) => {
            this.setHudColor("--hud-orange", system?.hud_accent_color);
            this.setHudColor("--hud-cyan", system?.hud_secondary_color);
        }));
        this.subscriptions.add(this.projectionsService.inCombat$.subscribe((value) => {
            this.isInCombat = typeof value === "boolean" ? value : Boolean(value?.InCombat || value?.combat || value?.active);
        }));
        this.subscriptions.add(this.runtime.eliteContext$.subscribe((context) => {
            this.hasEliteContext = context.available;
            this.refreshEliteDataLabel();
        }));
        this.subscriptions.add(this.eventService.events$.subscribe((events) => {
            const recent = events.slice().reverse().find((entry) => entry.event.kind === "game" && !entry.event.historic);
            if (recent?.event.kind === "game") {
                const eventTime = Date.parse(recent.event.content.timestamp || recent.event.timestamp);
                this.lastLiveEliteAt = Number.isFinite(eventTime) ? eventTime : null;
                this.refreshEliteDataLabel();
            }
        }));
        this.subscriptions.add(interval(15_000).subscribe(() => this.refreshEliteDataLabel()));
        this.subscriptions.add(this.uiService.changeUI$.subscribe((message) => {
            if (message?.scroll) {
                this.scrollCurrentView(message.scroll);
                return;
            }
            this.selectedView = viewForUiCommand(this.selectedView, message?.show);
        }));
        void this.applicationCoordinator.initialize();
    }

    async newSession(): Promise<void> {
        if (!confirm('Start a new conversation? Current short-term conversation context will be cleared. Persistent TARS memory is kept.')) return;
        const request_id = globalThis.crypto?.randomUUID?.() ?? String(Date.now());
        try {
            const response = firstValueFrom(this.tauriService.output$.pipe(filter(m=>m.type==='session_started' && m['request_id']===request_id),take(1),timeout(10000)));
            await this.tauriService.send_command({type:'new_session',timestamp:new Date().toISOString(),request_id});
            await response; this.chatService.clearChat();
        } catch { alert('TARS did not confirm a new session. Conversation was retained.'); }
    }

    clearVisibleChat(): void {
        if (confirm('Clear the visible chat in this window? This keeps TARS memory and backend conversation context.')) this.chatService.clearChat();
    }

    async interruptSpeech(): Promise<void> {
        await this.tauriService.send_command({type:'interrupt_tts',timestamp:new Date().toISOString()});
    }

    ngOnDestroy(): void { this.subscriptions.unsubscribe(); }

    private refreshEliteDataLabel(): void {
        this.eliteDataLabel = eliteDataStatus(this.hasEliteContext, this.lastLiveEliteAt);
    }

    activityLabel(phase: string): string { return tarsActivityStatus(this.runMode, phase); }

    selectView(view: TarsShellView): void { this.selectedView = view; }

    openActionDiagnostics(): void {
        this.selectedView = "settings";
        window.setTimeout(() => this.settingsMenu?.openSettingsTarget("actions"), 0);
    }

    focusPolicy(): void {
        this.selectedView = "settings";
        window.setTimeout(() => this.settingsMenu?.focusDisclaimer(), 0);
    }

    async start(): Promise<void> {
        if (!this.usageDisclaimerAccepted) {
            this.focusPolicy();
            return;
        }
        await this.applicationCoordinator.startAssistant();
    }

    async stop(): Promise<void> { await this.applicationCoordinator.returnToConfiguration(); }

    onQuestEditorVisibilityChange(open: boolean): void { this.isQuestEditorOpen = open; }

    private setHudColor(variable: "--hud-orange" | "--hud-cyan", color?: string): void {
        if (color && /^#[0-9a-fA-F]{6}$/.test(color)) document.documentElement.style.setProperty(variable, color);
    }

    private scrollCurrentView(direction: "top" | "up" | "down" | "bottom"): void {
        const panel = document.querySelector<HTMLElement>(`.view-panel[data-view="${this.selectedView}"]`);
        const scroller = panel && [panel, ...Array.from(panel.querySelectorAll<HTMLElement>("*"))]
            .find((element) => ["auto", "scroll"].includes(getComputedStyle(element).overflowY)
                && element.scrollHeight > element.clientHeight);
        if (!scroller) return;
        if (direction === "top" || direction === "bottom") {
            scroller.scrollTo({ top: direction === "top" ? 0 : scroller.scrollHeight, behavior: "smooth" });
        } else {
            scroller.scrollBy({ top: scroller.clientHeight * (direction === "up" ? -0.75 : 0.75), behavior: "smooth" });
        }
    }
}
