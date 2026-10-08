import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { combineLatest, map } from 'rxjs';
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
        <p>Read-only snapshot of reported state. This does not test devices or send Elite actions.</p>
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
        <details><summary>Build information</summary><dl>
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
    constructor(private runtime: TarsRuntimeFacade, private config: ConfigService, private tauri: TauriService) {}
}
