import { Component, OnDestroy, OnInit, ViewChild } from "@angular/core";
import { CommonModule } from "@angular/common";
import { MatButtonModule } from "@angular/material/button";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { MatDialogModule } from "@angular/material/dialog";
import { MatSnackBarModule } from "@angular/material/snack-bar";
import { LogContainerComponent } from "../components/log-container/log-container.component";
import { SettingsMenuComponent } from "../components/settings-menu/settings-menu.component";
import { InputContainerComponent } from "../components/input-container/input-container.component";
import {Config, ConfigService} from "../services/config.service";
import { Subscription } from "rxjs";
import { MatTabsModule } from "@angular/material/tabs";
import { ChatContainerComponent } from "../components/chat-container/chat-container.component.js";
import { StatusContainerComponent } from "../components/status-container/status-container.component";
import { StorageContainerComponent } from "../components/storage-container/storage-container.component";
import { StationContainerComponent } from "../components/station-container/station-container.component";
import { TasksContainerComponent } from "../components/tasks-container/tasks-container.component";
import { ProjectionsService } from "../services/projections.service";
import { MemoriesContainerComponent } from "../components/memories-container/memories-container.component";
import { SearchResultsComponent } from "../components/search-results-container/search-results-container.component";
import { NavigationContainerComponent } from "../components/navigation-container/navigation-container.component";
import { PolicyService } from "../services/policy.service.js";
import {UIService} from "../services/ui.service";
import { ActionsContainerComponent } from "../components/actions-container/actions-container.component";
import {
    TarsApplicationCoordinator,
    TarsApplicationState,
} from "../services/tars-application-coordinator.service";

@Component({
    selector: "app-main-view",
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatIconModule,
        MatProgressBarModule,
        MatDialogModule,
        MatSnackBarModule,
        LogContainerComponent,
        SettingsMenuComponent,
        InputContainerComponent,
        MatTabsModule,
        ChatContainerComponent,
        StatusContainerComponent,
        StorageContainerComponent,
        StationContainerComponent,
        TasksContainerComponent,
        MemoriesContainerComponent,
        SearchResultsComponent,
        NavigationContainerComponent,
        ActionsContainerComponent,
    ],
    templateUrl: "./main-view.component.html",
    styleUrl: "./main-view.component.css",
})
export class MainViewComponent implements OnInit, OnDestroy {
    @ViewChild(SettingsMenuComponent) private settingsMenu?: SettingsMenuComponent;

    runMode: TarsApplicationState = "starting";
    isLoading = true;
    isRunning = false;
    showRuntimeView = false;
    isInCombat = false;
    isDockedAtStation = false;
    isShipIdentUnknown = false;
    private currentStatusData: any = null;
    private shipInfo: any = null;
    currentGameModeLabel = "Status";
    currentGameModeIcon = "info";
    selectedTabIndex: number = 0;
    config: Config|undefined;
    hasLogbook = true;
    private uiChangeSubscription?: Subscription;
    private configSubscription!: Subscription;
    private inCombatSubscription!: Subscription;
    private currentStatusSubscription!: Subscription;
    private shipInfoSubscription!: Subscription;
    private applicationStateSubscription!: Subscription;
    public usageDisclaimerAccepted = false;
    public isQuestEditorOpen = false;
    private systemSubscription?: Subscription;

    constructor(
        private applicationCoordinator: TarsApplicationCoordinator,
        private configService: ConfigService,
        private projectionsService: ProjectionsService,
        private policyService: PolicyService,
        private uiService: UIService,
    ) {
        this.policyService.usageDisclaimerAccepted$.subscribe(
            (accepted) => {
                this.usageDisclaimerAccepted = accepted;
            },
        );
    }

    private applyHudColors(system?: { hud_accent_color?: string; hud_secondary_color?: string } | null): void {
        this.setHudColor("--hud-orange", system?.hud_accent_color);
        this.setHudColor("--hud-cyan", system?.hud_secondary_color);
    }

    private setHudColor(variable: "--hud-orange" | "--hud-cyan", color?: string): void {
        if (!color || !/^#[0-9a-fA-F]{6}$/.test(color)) {
            return;
        }

        document.documentElement.style.setProperty(variable, color);
    }

    ngOnInit(): void {
        this.applyHudColors(this.configService.systemInfo);
        this.systemSubscription = this.configService.system$.subscribe((system) => {
            this.applyHudColors(system);
        });

        this.configSubscription = this.configService.config$.subscribe(
            (config) => {
                this.config = config ?? undefined;
                this.hasLogbook = this.config?.embedding_provider != 'none';
            },
        );

        // Subscribe to the running state
        this.applicationStateSubscription = this.applicationCoordinator.state$.subscribe(
            (mode) => {
                this.runMode = mode;
                this.isRunning = mode === "running";
                this.isLoading = mode === "starting" || mode === "restarting";
                this.showRuntimeView = mode === "running" || mode === "error";
                if (mode === "error") {
                    this.selectedTabIndex = 0;
                }
            },
        );


        this.uiChangeSubscription = this.uiService.changeUI$.subscribe(
            (uiMessage) => {
                if (uiMessage === null) return;
                if (uiMessage.scroll) {
                    this.scrollActiveTab(uiMessage.scroll);
                    return;
                }
                const tabName = uiMessage.show;
                if (!tabName) return;
                
                let current = 0;
                if (tabName === 'chat') {
                    this.selectedTabIndex = current;
                    return;
                }
                current++;

                if (!this.isShipIdentUnknown) {
                    if (tabName === 'status') {
                        this.selectedTabIndex = current;
                        return;
                    }
                    current++;
                }

                if (tabName === 'navigation') {
                    this.selectedTabIndex = current;
                    return;
                }
                current++;
                if (!this.isShipIdentUnknown) {

                    if (tabName === 'storage') { this.selectedTabIndex = current; return; }
                    current++;
                    if (tabName === 'tasks') { this.selectedTabIndex = current; return; }
                    current++;
                    if (this.isDockedAtStation) {
                        if (tabName === 'station') { this.selectedTabIndex = current; return; }
                        current++;
                    }
                }

                if (this.hasLogbook) {
                    if (tabName === 'logbook') { this.selectedTabIndex = current; return; }
                    current++;
                }


                if (tabName === 'search') {
                    this.selectedTabIndex = current;
                    return;
                }
            }
        )

        // Subscribe to InCombat projection
        this.inCombatSubscription = this.projectionsService.inCombat$
            .subscribe((inCombatData) => {
                // InCombat projection might be a boolean or an object
                if (typeof inCombatData === 'boolean') {
                    this.isInCombat = inCombatData;
                } else if (inCombatData && typeof inCombatData === 'object') {
                    // If it's an object, check for a combat flag or status
                    this.isInCombat = Boolean(inCombatData.InCombat || inCombatData.combat || inCombatData.active);
                } else {
                    this.isInCombat = false;
                }
            });

        // Subscribe to CurrentStatus projection to track station docking
        this.currentStatusSubscription = this.projectionsService.currentStatus$
            .subscribe((currentStatusData) => {
                this.currentStatusData = currentStatusData;
                this.isDockedAtStation = Boolean(currentStatusData?.flags?.Docked === true);
                this.currentGameModeLabel = this.getCurrentGameModeLabel(currentStatusData);
                this.currentGameModeIcon = this.getCurrentGameModeIcon(currentStatusData);
            });

        // Subscribe to ShipInfo projection to track unknown ship ident
        this.shipInfoSubscription = this.projectionsService.shipInfo$
            .subscribe((shipInfo) => {
                this.shipInfo = shipInfo;
                const shipIdent = shipInfo?.ShipIdent ?? 'Unknown';
                this.isShipIdentUnknown = shipIdent === 'Unknown';
                this.currentGameModeLabel = this.getCurrentGameModeLabel(this.currentStatusData);
                this.currentGameModeIcon = this.getCurrentGameModeIcon(this.currentStatusData);
            });

        // Initialize the main view
        void this.applicationCoordinator.initialize();
    }

    ngOnDestroy(): void { // Implement ngOnDestroy
        if (this.systemSubscription) {
            this.systemSubscription.unsubscribe();
        }
        if (this.configSubscription) {
            this.configSubscription.unsubscribe();
        }
        if (this.uiChangeSubscription) {
            this.uiChangeSubscription.unsubscribe();
        }
        if (this.inCombatSubscription) {
            this.inCombatSubscription.unsubscribe();
        }
        if (this.currentStatusSubscription) {
            this.currentStatusSubscription.unsubscribe();
        }
        if (this.shipInfoSubscription) {
            this.shipInfoSubscription.unsubscribe();
        }
        if (this.applicationStateSubscription) {
            this.applicationStateSubscription.unsubscribe();
        }
    }

    private getCurrentGameModeLabel(currentStatusData: any): string {
        if (!currentStatusData) {
            return "Status";
        }

        if (currentStatusData.flags2?.OnFoot) {
            return "Suit";
        }
        if (currentStatusData.flags?.InFighter || (currentStatusData.flags?.InSRV && this.shipInfo?.fighter_loadout === "base")) {
            return "SLF";
        }
        if (currentStatusData.flags?.InSRV) {
            return "SRV";
        }

        return "Ship";
    }

    private getCurrentGameModeIcon(currentStatusData: any): string {
        if (!currentStatusData) {
            return "info";
        }

        if (currentStatusData.flags2?.OnFoot) {
            return "directions_walk";
        }
        if (currentStatusData.flags?.InFighter || (currentStatusData.flags?.InSRV && this.shipInfo?.fighter_loadout === "base")) {
            return "flight";
        }
        if (currentStatusData.flags?.InSRV) {
            return "directions_car";
        }

        return "rocket_launch";
    }

    private scrollActiveTab(direction: "top" | "up" | "down" | "bottom"): void {
        const activeTab = document.querySelector<HTMLElement>(".mat-mdc-tab-body-active");
        if (!activeTab) return;

        const scrollContainer = Array.from(activeTab.querySelectorAll<HTMLElement>("*")).find((element) => {
            const overflowY = getComputedStyle(element).overflowY;
            return (overflowY === "auto" || overflowY === "scroll") && element.scrollHeight > element.clientHeight;
        });
        if (!scrollContainer) return;

        if (direction === "top" || direction === "bottom") {
            scrollContainer.scrollTo({
                top: direction === "top" ? 0 : scrollContainer.scrollHeight,
                behavior: "smooth",
            });
            return;
        }

        scrollContainer.scrollBy({
            top: (direction === "up" ? -1 : 1) * scrollContainer.clientHeight * 0.75,
            behavior: "smooth",
        });
    }

    // Called by the floating FAB when the policy is not yet accepted
    focusPolicy(): void {
        // Ensure the settings menu is visible (only visible when not running)
        this.settingsMenu?.focusDisclaimer();
    }

    acceptUsageDisclaimer() {
        this.policyService.acceptUsageDisclaimer();
    }

    async start(): Promise<void> {
        await this.applicationCoordinator.startAssistant();
    }

    async stop(): Promise<void> {
        await this.applicationCoordinator.returnToConfiguration();
    }

    onQuestEditorVisibilityChange(isOpen: boolean): void {
        this.isQuestEditorOpen = isOpen;
    }
}
