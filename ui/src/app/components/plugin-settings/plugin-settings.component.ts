import { TarsProviderRegistry } from "../../services/tars-provider-registry";
import { TarsRuntimeFacade } from "../../services/tars-runtime-facade.service";
import { TarsComponentHealth } from "../../services/tars-runtime-facade.models";
import { providerRuntimeLabel } from "../../services/tars-health-presentation";
import { ModelProviderDefinition } from "../../services/plugin-settings";
import { Component, OnDestroy, OnInit } from "@angular/core";
import { MatCardModule } from "@angular/material/card";
import { MatTabsModule } from "@angular/material/tabs";
import { MatIconModule } from "@angular/material/icon";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatInputModule } from "@angular/material/input";
import { MatSelectModule } from "@angular/material/select";
import { MatSlideToggleModule } from "@angular/material/slide-toggle";
import { FormsModule } from "@angular/forms";
import { Config, ConfigService } from "../../services/config.service";
import { Subscription } from "rxjs";
import { MatButtonModule } from "@angular/material/button";
import { KeyValue, KeyValuePipe } from "@angular/common";
import { MatExpansionModule } from "@angular/material/expansion";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { CommonModule } from "@angular/common";
import { MatDividerModule } from "@angular/material/divider";
import { MatCheckboxModule } from "@angular/material/checkbox";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import {
  ConfirmationDialogComponent,
  ConfirmationDialogData,
} from "../../components/confirmation-dialog/confirmation-dialog.component";
import { ConfirmationDialogService } from "../../services/confirmation-dialog.service";
import {
  PluginSettings,
  ProviderInstallStatusMessage,
  SettingsGrid,
} from "../../services/plugin-settings";
import { SettingsGridComponent } from "../settings-grid/settings-grid.component";

@Component({
  selector: "app-plugin-settings",
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTabsModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatButtonModule,
    FormsModule,
    KeyValuePipe,
    MatExpansionModule,
    MatSnackBarModule,
    MatDividerModule,
    MatCheckboxModule,
    MatDialogModule,
    MatProgressSpinnerModule,
    MatProgressBarModule,
    SettingsGridComponent,
  ],
  templateUrl: "./plugin-settings.component.html",
  styleUrls: ["../settings-menu/settings-menu.component.scss"],
})
export class PluginSettingsComponent implements OnInit, OnDestroy {
  config: Config | null = null;
  private runtimeSubscriptions = new Subscription();
  private application = "stopped";
  private health: readonly TarsComponentHealth[] = [];
  private providers: ModelProviderDefinition[] = [];
  private configSubscription?: Subscription;
  private plugin_settings_message_subscription?: Subscription;
  private provider_install_status_subscription?: Subscription;

  // Plugin settings
  plugin_settings_configs: [string, PluginSettings][] = [];
  providerConfigs: [string, PluginSettings][] = [];
  behaviorConfigs: [string, PluginSettings][] = [];
  providerInstallStatuses: Record<string, ProviderInstallStatusMessage> = {};

  constructor(
    public configService: ConfigService,
    private runtime: TarsRuntimeFacade,
    private snackBar: MatSnackBar,
    private dialog: MatDialog,
    private confirmationDialog: ConfirmationDialogService,
  ) {}

  ngOnInit() {
    this.runtimeSubscriptions.add(this.runtime.applicationState$.subscribe(value => this.application = value));
    this.runtimeSubscriptions.add(this.runtime.health$.subscribe(value => this.health = value));
    this.runtimeSubscriptions.add(this.configService.plugin_model_providers$.subscribe(value => this.providers = value));
    this.configSubscription = this.configService.config$.subscribe(
      (config) => {
        if (config) {
          // Store the new config
          this.config = config;

          console.log("Config loaded in plugin settings component");
        } else {
          console.error("Received null config in plugin settings component");
        }
      },
    );
    this.plugin_settings_message_subscription = this.configService
      .plugin_settings_message$
      .subscribe(
        (plugin_settings_message) => {
          this.plugin_settings_configs = Object.entries(
            plugin_settings_message?.plugin_settings_configs || {}
          );
          this.providerConfigs = this.plugin_settings_configs.filter(([guid]) => !this.isBehaviorPlugin(guid));
          this.behaviorConfigs = this.plugin_settings_configs.filter(([guid]) => this.isBehaviorPlugin(guid));

          if (plugin_settings_message?.plugin_settings_configs) {
            console.log("Plugin settings loaded", {
              plugin_settings_configs:
                plugin_settings_message.plugin_settings_configs,
            });
          } else {
            console.error("Received null plugin settings");
          }
        },
      );
    this.provider_install_status_subscription = this.configService
      .provider_install_status$
      .subscribe((status) => {
        if (status) {
          this.providerInstallStatuses = {
            ...this.providerInstallStatuses,
            [status.provider_key]: status,
          };
        }
      });
  }

  private readonly behaviorIcons: Record<string, string> = {
    "f8b87f19-f65e-4bf2-bd3f-26d30c128a04": "travel_explore",
    "348ea6cb-1443-47e9-a3a3-6e8c1c17f523": "public",
    "5a80ff76-201c-49c7-a632-6f00d671a99a": "sensors",
    "8d3c25ce-49d4-4526-8041-ed6303510cef": "navigation",
    "cac18803-add3-4f2d-a07d-306d5704bb7f": "forum",
    "eeb92d2d-9656-441c-92e9-98513d43cac2": "explore",
  };

  isBehaviorPlugin(guid: string): boolean { return guid in this.behaviorIcons; }

  iconFor(guid: string, config: PluginSettings): string {
    return this.behaviorIcons[guid] ?? config.icon ?? "extension";
  }

  ngOnDestroy() {
    this.runtimeSubscriptions.unsubscribe();
    if (this.configSubscription) {
      this.configSubscription.unsubscribe();
    }
    if (this.plugin_settings_message_subscription) {
      this.plugin_settings_message_subscription.unsubscribe();
    }
    this.provider_install_status_subscription?.unsubscribe();
  }

  async onConfigChange(partialConfig: Partial<Config>) {
    if (this.config) {
      try {
        await this.configService.changeConfig(partialConfig);
      } catch (error) {
        console.error("Error updating config:", error);
        this.snackBar.open("Error updating configuration", "OK", {
          duration: 5000,
        });
      }
    }
  }

  async onEventConfigChange(section: string, event: string, enabled: boolean) {
    if (this.config) {
      console.log("onEventConfigChange", section, event, enabled);
      await this.configService.changeEventConfig(section, event, enabled);
    }
  }

  // Create a getValue function for a specific plugin
  createGetValueFn(pluginGuid: string): (fieldKey: string, defaultValue: any) => any {
    return (fieldKey: string, defaultValue: any) => {
      return this.config?.plugin_settings?.[pluginGuid]?.[fieldKey] ?? defaultValue;
    };
  }

  // Create a setValue function for a specific plugin
  createSetValueFn(pluginGuid: string): (fieldKey: string, value: any) => void {
    return (fieldKey: string, value: any) => {
      if (this.config == null) {
        return;
      }
      void this.onConfigChange({ plugin_settings: { [pluginGuid]: { [fieldKey]: value } } });
    };
  }

  createButtonClickFn(pluginGuid: string): (fieldKey: string) => void {
    return (fieldKey: string) => {
      this.configService.clickPluginSettingsButton(pluginGuid, fieldKey).catch((error) => {
        console.error("Error handling plugin settings button click:", error);
        this.snackBar.open("Error handling plugin button click", "OK", { duration: 5000 });
      });
    };
  }

  providerDisplayLabel(guid: string, settings: PluginSettings): string {
    return TarsProviderRegistry.pluginLabel(guid, settings.label);
  }

  providerRuntimeState(guid: string): string {
    if (guid.startsWith('failed_') || this.plugin_settings_configs.find(([key]) => key === guid)?.[1].grids.some(grid => grid.fields.some(field => field.type === 'error'))) return 'ERROR';
    const provider = this.providers.find(item => item.plugin_guid === guid &&
      this.config?.[({llm: 'llm_provider', vlm: 'vision_provider', stt: 'stt_provider',
        tts: 'tts_provider', embedding: 'embedding_provider'} as const)[item.kind]] === `plugin:${guid}:${item.id}`);
    const installed = this.providers.some(item => item.plugin_guid === guid);
    const component = provider ? ({llm: 'models', vlm: 'vision', stt: 'stt', tts: 'tts', embedding: 'memory'} as const)[provider.kind] : undefined;
    return providerRuntimeLabel(installed, Boolean(provider), this.application, this.health.find(item => item.component === component));
  }

  providerStatus(gridKey: string): ProviderInstallStatusMessage | undefined {
    return this.providerInstallStatuses[gridKey];
  }

  providerButtonEnabled(gridKey: string): boolean {
    const status = this.providerStatus(gridKey);
    return !status || status.state === "failed";
  }

  providerStatusText(status: ProviderInstallStatusMessage): string {
    switch (status.state) {
      case "downloading":
        return `Downloading — ${this.toMiB(status.downloaded_bytes)} / ${this.toMiB(status.total_bytes)} MB — ${status.percent}%`;
      case "verifying":
        return "Verifying…";
      case "extracting":
        return "Extracting…";
      case "installed":
        return "Installed ✓ — Restart required";
      case "failed":
        return `Installation failed${status.error ? ` — ${status.error}` : ""}`;
    }
  }

  private toMiB(bytes: number): string {
    return (bytes / (1024 * 1024)).toFixed(1);
  }

  // Legacy methods kept for backward compatibility
  getPluginSetting(
    pluginGuid: string,
    fieldKey: string,
    defaultValue: any,
  ): boolean {
    return this.config?.plugin_settings?.[pluginGuid]?.[fieldKey] ??
      defaultValue;
  }

  setPluginSetting(
    pluginGuid: string,
    fieldKey: string,
    value: any,
  ): void {
    if (this.config == null) {
      return;
    }
    void this.onConfigChange({ plugin_settings: { [pluginGuid]: { [fieldKey]: value } } });
  }
}
