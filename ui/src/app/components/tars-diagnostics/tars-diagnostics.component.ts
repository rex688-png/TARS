import { LoggingService } from '../../services/logging.service';
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { combineLatest, map, firstValueFrom } from 'rxjs';
import { TarsRuntimeFacade } from '../../services/tars-runtime-facade.service';
import { ConfigService } from '../../services/config.service';
import { TauriService } from '../../services/tauri.service';
import { healthLabel, selfCheck } from '../../services/tars-health-presentation';
import provenance from '../../../../../vendor/tars-plugins/provenance.json';
import metadata from '../../../../../package.json';

@Component({
    selector: 'app-tars-diagnostics', standalone: true, imports: [CommonModule],
    template: `<section class="diagnostic-card"><header><h2>Runtime self-check</h2>
        <button type="button" (click)="checked = true">Run self-check</button></header>
        <button type="button" [disabled]="exporting" (click)="exportDiagnostics()">Export diagnostics</button><p role="status">{{ exportStatus }}</p><p>Export includes health and log severity counts; private log text, prompt, memory, conversation and credentials are excluded.</p><p>Read-only snapshot of reported state. This does not test devices or send Elite actions.</p>
        @if (checked) {
            @if (check$ | async; as check) {
                <strong role="status">{{ check.result }}</strong>
                <dl>@for (item of check.health; track item.component) { <dt>{{ item.component }}</dt><dd>{{ label(item) }} — {{ item.detail }}</dd> }
                    <dt>Actions</dt><dd>{{ check.keybinds === null ? 'Not verified' : check.keybinds ? check.keybinds + ' missing keybinds' : 'Bindings ready' }}</dd>
                    <dt>Behavior plugins</dt><dd>{{ check.loaded }} settings registrations received; activity is not verified</dd>
                    <dt>Observatory feed</dt><dd>Not verified — use TARS Observatory diagnostics for file/cursor state. Optional feed absence is non-fatal.</dd>
                </dl>
            }
        }
        <details><summary>Configuration backup</summary><p>Stored beside your TARS profile. Contains API credentials and prompt; do not share it. Restore requires TARS to be stopped.</p><button type="button" (click)="createBackup()">Create local backup</button><button type="button" (click)="restoreBackup()">Restore local backup</button><p role="status">{{ backupStatus }}</p></details><details><summary>Build information</summary><dl>
            <dt>TARS package</dt><dd>{{ version }} (unreleased build)</dd>
            <dt>Frontend build</dt><dd>{{ commit }}</dd>
            <dt>Backend version</dt><dd>Not separately reported</dd>
            <dt>Behavior bundle</dt><dd>{{ bundle }}</dd>
        </dl></details></section>`,
    styles: [`.diagnostic-card {background:#171e26;border:1px solid #3d4c59;padding:18px;margin-bottom:20px;border-radius:4px}
      header {display:flex;align-items:center;justify-content:space-between} h2 {font-size:17px;color:#b6dbe9;margin:0} p,dl {font-size:12px;color:#b3c3d0}
      dl {display:grid;grid-template-columns:minmax(100px, 160px) 1fr;gap:8px} dd {margin:0;overflow-wrap:anywhere} button {background:#263743;color:#cde5ef;border:1px solid #4d6677;padding:8px 12px;cursor:pointer} summary {cursor:pointer;margin-top:16px}`],
})
export class TarsDiagnosticsComponent {
    exporting = false; exportStatus = ''; backupStatus = '';
    async createBackup() { try { await this.config.requestProductCommand('create_config_backup'); this.backupStatus='Local known-good backup created. It contains credentials; keep your Windows account private.'; } catch { this.backupStatus='Backup could not be created.'; } }
    async restoreBackup() { if (!confirm('Restore the saved TARS configuration? Current settings will be replaced. This only works while TARS is stopped.')) return;
        try { await this.config.requestProductCommand('restore_config_backup'); this.backupStatus='Local backup restored. Restart TARS before starting a session.'; } catch { this.backupStatus='Restore failed. Current settings were retained.'; } }

    async exportDiagnostics() {
        this.exporting = true;
        try {
            const check = await firstValueFrom(this.check$);
            const logs = await firstValueFrom(this.logs.logs$);
            const log_counts: Record<string,number> = {};
            for (const log of logs) log_counts[log.prefix] = (log_counts[log.prefix] ?? 0) + 1;
            const result = await this.config.requestProductCommand('export_diagnostics', {snapshot:{commit:this.commit, health:check.health.map(h=>({component:h.component,status:h.status})), missing_keybinds:check.keybinds, log_counts,log_entries:logs.slice(-100).map(log=>({level:log.prefix,timestamp:log.timestamp}))}});
            const bytes = Uint8Array.from(atob(String(result['data'])), c=>c.charCodeAt(0));
            const url = URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));
            const link = document.createElement('a'); link.href=url; link.download='TARS-support.zip'; link.click();
            setTimeout(()=>URL.revokeObjectURL(url),1000); this.exportStatus='Support bundle created. Review it before sharing.';
        } catch { this.exportStatus='Export failed. No support bundle was created.'; }
        finally { this.exporting=false; }
    }
    checked = false;
    readonly label = healthLabel;
    readonly bundle = provenance.source_revision;
    readonly version = metadata.version;
    private readonly behaviorKeys = new Set(Object.keys(provenance.files).filter(path => path.endsWith('/manifest.json')).map(path => path.split('/')[1]));
    readonly commit = this.tauri.commitHash;
    readonly check$ = combineLatest([this.runtime.health$, this.config.keybinds$, this.config.plugin_settings_message$]).pipe(
        map(([health, keybinds, plugins]) => ({
            health, keybinds: keybinds ? keybinds.missing.length : null,
            loaded: Object.values(plugins?.plugin_settings_configs ?? {}).filter(item => this.behaviorKeys.has(item.key)).length,
            result: selfCheck(health) === 'FAILED' ? 'FAILED' : keybinds?.missing.length ? 'WARNING' : selfCheck(health),
        })),
    );
    constructor(private runtime: TarsRuntimeFacade, private config: ConfigService, private tauri: TauriService, private logs: LoggingService) {}
}
