import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConfigService } from '../../services/config.service';
import { needsSetup } from '../../services/tars-setup-state';
import { TarsRuntimeFacade } from '../../services/tars-runtime-facade.service';
import { healthLabel } from '../../services/tars-health-presentation';
@Component({selector:'app-tars-setup',standalone:true,imports:[CommonModule],template:`
@if (config.config$ | async; as profile) {
 @if (needsSetup(profile)) {
 <section class="setup" aria-label="First-run setup"><h2>{{ steps[profile.tars_setup_step ?? 0] }}</h2>
 <p>Step {{ (profile.tars_setup_step ?? 0) + 1 }} of {{ steps.length }} · Progress is saved in your TARS profile.</p>
 <p>{{ descriptions[profile.tars_setup_step ?? 0] }}</p>
 @if ((profile.tars_setup_step ?? 0) === 2) {<label>OpenAI API key (optional if another provider is configured) <input #keyInput type="password" autocomplete="off" placeholder="Enter key" /></label><button [disabled]="busy" (click)="saveKey(keyInput)">Save key</button>}
 <button (click)="configure.emit(targets[profile.tars_setup_step ?? 0])">Open settings for this step</button>
 @if ((profile.tars_setup_step ?? 0) >= 6) {
  <ul>@for (health of runtime.health$ | async; track health.component) {<li>{{ health.component }}: {{ label(health) }}</li>}</ul>
  <p>Configured is not a device test. Start TARS to verify models and audio. Elite and Observatory are optional.</p>
 }
 <div><button [disabled]="busy || !(profile.tars_setup_step ?? 0)" (click)="save((profile.tars_setup_step ?? 0)-1)">Back</button>
 <button [disabled]="busy" (click)="save((profile.tars_setup_step ?? 0)+1)">{{ (profile.tars_setup_step ?? 0) === 7 ? 'Finish setup' : 'Save & continue' }}</button>
 @if ((profile.tars_setup_step ?? 0) >= 3 && (profile.tars_setup_step ?? 0) <= 5) {<button [disabled]="busy" (click)="save((profile.tars_setup_step ?? 0)+1)">Skip optional step</button>}
 </div><p role="status">{{ error }}</p></section>
 }
}`,styles:[`.setup{background:#15232c;border:1px solid #426273;padding:18px;margin:12px}h2{color:#aedbe9;font-size:18px}p,li{font-size:13px}button{background:#253e4b;color:#d8e9ed;border:1px solid #526e7a;padding:8px;margin:4px}`]})
export class TarsSetupComponent {
 @Output() configure=new EventEmitter<number>();
 readonly needsSetup=needsSetup; readonly label=healthLabel; busy=false;error='';
 readonly steps=['Welcome to TARS','Commander','AI / model / API','Microphone & speech','Voice & output','Elite integration','System check','Ready'];
 readonly targets=[0,0,1,1,1,0,4,0];
 readonly descriptions=['Your Windows copilot. Configure the essentials, then add optional capabilities.','Set the commander name used by TARS.','Choose a provider and model. Credentials stay in your local profile; key fields are masked.','Choose an input device and speech provider. Local providers are separate, explicit downloads under Plugins.','Choose a voice provider and output device. Provider tuning is saved independently of selection.','Check journal and bindings detection. Elite does not need to be running to finish setup.','Review reported readiness below. Missing optional components can be configured later.','Finish to keep this setup closed on future launches. Settings remain available.'];
 constructor(public config:ConfigService,public runtime:TarsRuntimeFacade){}
 async saveKey(input:HTMLInputElement) { const value=input.value.trim(); if(!value)return; this.busy=true;this.error='';
  try { await this.config.changeConfig({api_key:value}); input.value=''; this.error='Key saved in the local TARS profile.'; }
  catch { this.error='Key could not be saved.'; } finally { this.busy=false; }
 }
 async save(step:number){this.busy=true;this.error='';try{await this.config.changeConfig({tars_setup_step:Math.min(7,Math.max(0,step)),tars_setup_complete:step>=8});}catch{this.error='Setup progress was not saved. Try again.';}finally{this.busy=false;}}
}
