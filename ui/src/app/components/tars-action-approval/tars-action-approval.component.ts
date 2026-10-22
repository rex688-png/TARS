import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TauriService } from '../../services/tauri.service';
@Component({selector:'app-tars-action-approval',standalone:true,imports:[CommonModule],template:`
@for (item of pending; track item.id) {<section role="alert"><strong>Confirm game action: {{ item.action }}</strong><pre>{{ item.arguments }}</pre><p>Not executed. Confirmation expires after 60 seconds.</p><button (click)="answer(item.id,true)">Allow once</button><button (click)="answer(item.id,false)">Cancel</button></section>}
<p role="status">{{ error }}</p>`,styles:[`section{border:1px solid #b79958;background:#26241c;padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{margin-right:8px;padding:8px}`]})
export class TarsActionApprovalComponent implements OnDestroy {
 pending:{id:string;action:string;arguments:string}[]=[];error='';
 private timers=new Map<string,ReturnType<typeof setTimeout>>();
 private sub=this.transport.output$.subscribe(m=>{
  if(m.type==='action_approval'){const id=String(m['request_id']);this.pending=[...this.pending,{id,action:String(m['action']),arguments:String(m['arguments'])}];this.timers.set(id,setTimeout(()=>this.remove(id),60000));}
  if(m.type==='action_approval_closed')this.remove(String(m['request_id']));
 });
 constructor(private transport:TauriService){}
 private remove(id:string){this.pending=this.pending.filter(p=>p.id!==id);clearTimeout(this.timers.get(id));this.timers.delete(id);}
 async answer(id:string,approved:boolean){try{await this.transport.send_command({type:'confirm_action',timestamp:new Date().toISOString(),request_id:id,approved});this.remove(id);this.error='';}catch{this.error='Confirmation could not reach TARS. Nothing was approved.';}}
 ngOnDestroy(){this.sub.unsubscribe();for(const timer of this.timers.values())clearTimeout(timer);}
}
