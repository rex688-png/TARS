import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConfigService } from '../../services/config.service';
@Component({selector:'app-tars-action-permissions',standalone:true,imports:[CommonModule],template:`
<section><h2>Action permissions</h2><p>Allow executes immediately. Ask requires a one-time confirmation before game input. Block never executes. Existing disabled actions remain blocked.</p>
@if (config.config$ | async; as profile) { @for (entry of profile.allowed_actions | keyvalue; track entry.key) {
<label>{{ label(entry.key) }} <select [disabled]="entry.value === false" [value]="mode(profile,entry.key)" (change)="set(entry.key,$any($event.target).value)"><option value="allow">ALLOW</option><option value="ask">ASK</option><option value="block">BLOCK</option></select>@if (entry.value === false) {<small>Disabled in Action settings</small>}</label>
} }<button (click)="reset()">Reset permission defaults</button><p role="status">{{ error || (config.saveState$ | async) }}</p></section>`,styles:[`section{background:#182129;padding:18px;border:1px solid #3e5665}label{display:flex;justify-content:space-between;padding:7px;gap:12px;font-size:13px}select,button{background:#243541;color:#d9e6ed;padding:6px;border:1px solid #4b6575}h2{font-size:18px}`]})
export class TarsActionPermissionsComponent {
 error=''; readonly risky=new Set(['textMessage','fireWeapons','fireWeaponsBuggy','ejectAllCargo','ejectAllCargoBuggy']);
 constructor(public config:ConfigService){}
 label(key:string):string {return ({textMessage:'Send Elite chat message',fireWeapons:'Fire ship weapons',fireWeaponsBuggy:'Fire SRV weapons',ejectAllCargo:'Jettison ship cargo',ejectAllCargoBuggy:'Jettison SRV cargo'} as Record<string,string>)[key] ?? key.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());}
 mode(p:NonNullable<ReturnType<ConfigService['getCurrentConfig']>>,key:string){return p.allowed_actions[key]===false?'block':p.action_permissions?.[key]??(this.risky.has(key)?'ask':'allow');}
 async set(key:string,mode:'allow'|'ask'|'block'){try{await this.config.changeConfig({action_permissions:{...this.config.getCurrentConfig()?.action_permissions,[key]:mode}});this.error='';}catch{this.error='Permissions were not saved.';}}
 async reset(){try{await this.config.changeConfig({action_permissions:{}});this.error='Explicit permissions reset. Existing disabled actions remain blocked.';}catch{this.error='Permissions were not saved.';}}
}
