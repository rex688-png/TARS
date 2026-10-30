import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfigService } from '../../services/config.service';
import { TauriService } from '../../services/tauri.service';
import { BlackBoxRecord, filterBlackBox, blackBoxFilename } from './blackbox-presentation';

interface Session { session_id: string; started: string; active: boolean; clean_shutdown: boolean; private_available: boolean; bytes: number; dropped: number; }
interface Status { session_id: string; mode: string; recording: boolean; dropped: number; written: number; queue_depth: number; part_mib: number; sessions_limit: number; }
@Component({
    selector:'app-tars-blackbox', standalone:true, imports:[CommonModule, FormsModule],
    template:`<section aria-label="Black Box diagnostics"><h2>Black Box</h2>
      <p>Continuous local software evidence, not hidden model reasoning. Standard excludes conversation, prompts, screenshots, credentials and personal paths. Audio writes do not prove that you heard the output.</p>
      <p role="status">{{ message }}</p>
      @if (status) {
        <p>{{ status.recording ? 'Recording' : 'Recorder unavailable or stopped' }} · {{ status.mode }} · Session {{ status.session_id }}<br>
        {{ status.written }} recorded · {{ status.dropped }} dropped · {{ status.queue_depth }} queued</p>
        <label>Recording mode <select [(ngModel)]="recordingMode" (ngModelChange)="setMode($event)" [disabled]="busy"><option value="standard">Standard</option><option value="verbose">Verbose Debug — private</option></select></label>
        <p>Verbose may retain redacted input, final output and tool context locally. It can contain personal conversation. It is never included in ordinary support bundles and resets to Standard next backend session.</p>
        <details><summary>Storage limits</summary><label>Segment MiB <input type="number" min="1" max="16" [(ngModel)]="partMiB"></label>
          <label>Sessions retained <input type="number" min="1" max="20" [(ngModel)]="retention"></label><button (click)="setLimits()" [disabled]="busy">Apply limits</button>
          <p>At most 16 segments per session and 256 MiB across recorded sessions. Old segments rotate out; a long session may retain only a recent window. Dropped records and abrupt tails mean evidence is incomplete.</p></details>
      }
      <button (click)="refresh()" [disabled]="busy">Refresh</button>
      <button (click)="openFolder()" [disabled]="!desktop">Open Black Box folder</button>
      <label>Session <select [(ngModel)]="selected" (ngModelChange)="loadActivity()"><option value="">Select session</option>@for (s of sessions; track s.session_id) { <option [value]="s.session_id">{{ s.started }} · {{ s.active ? 'active' : s.clean_shutdown ? 'closed' : 'unclean / interrupted' }} · {{ s.session_id }}</option> }</select></label>
      <div><button (click)="exportSession(false,false)" [disabled]="!selected || exporting">Export sanitized JSONL</button>
      <button (click)="exportSession(true,false)" [disabled]="!selected || exporting">Export readable TXT</button>
      <button (click)="exportSession(false,true)" [disabled]="!selected || exporting">Export PRIVATE context</button></div>
      <label>Component <select [(ngModel)]="component"><option value="">All</option>@for (v of components; track v) { <option [value]="v">{{ v }}</option> }</select></label>
      <label>Severity <select [(ngModel)]="severity"><option value="">All</option><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option></select></label>
      <label>Decision reason <select [(ngModel)]="decision"><option value="">All</option>@for (v of reasons; track v) { <option [value]="v">{{ v }}</option> }</select></label>
      <p>Recent retained activity (up to 200 rows). Export for the full retained timeline. Unknown reasons remain unknown.</p>
      <div class="timeline"><table><thead><tr><th>UTC / sequence</th><th>Component / stage</th><th>Observed reason / outcome</th><th>Correlation</th></tr></thead><tbody>
        @for (row of visible; track row.seq) { <tr><td>{{ row.timestamp }} #{{ row.seq }}</td><td>{{ row.component }} / {{ row.stage }}</td><td>{{ row.reason || row.outcome || 'Not reported' }}</td><td>{{ row.event_id || row.trace_id || row.delivery_id || '' }}</td></tr> }
      </tbody></table></div>
    </section>`,
    styles:[`section{background:#171e26;border:1px solid #3d4c59;padding:18px;margin-bottom:20px;color:#cde5ef}h2{font-size:17px}p,label,table{font-size:12px}label{display:inline-block;margin:8px}select,input,button{background:#263743;color:#cde5ef;border:1px solid #4d6677;padding:6px;max-width:100%}button{margin:4px;cursor:pointer}button:disabled{opacity:.5}.timeline{max-height:320px;overflow:auto}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px;border-bottom:1px solid #3d4c59;overflow-wrap:anywhere}`],
})
export class TarsBlackBoxComponent implements OnInit, OnDestroy {
    status:Status|null=null; sessions:Session[]=[]; records:BlackBoxRecord[]=[];
    recordingMode='standard';
    selected=''; component=''; severity=''; decision=''; message='Recorder status not yet reported.';
    busy=false; exporting=false; partMiB=8; retention=8;
    readonly desktop=!!window.electronAPI;
    private timer:ReturnType<typeof setInterval>|undefined;
    private destroyed=false;
    constructor(private config:ConfigService, private tauri:TauriService) {}
    get components() { return [...new Set(this.records.map(r=>r.component))].sort(); }
    get reasons() { return [...new Set(this.records.map(r=>r.reason).filter((r):r is string=>!!r))].sort(); }
    get visible() { return filterBlackBox(this.records,this.component,this.severity,this.decision); }
    ngOnInit() { void this.refresh(); this.timer=setInterval(()=>{ if (!this.busy && !this.exporting) void this.refresh(); },5000); }
    ngOnDestroy() { this.destroyed=true; if(this.timer) clearInterval(this.timer); }
    async refresh() {
        if(this.busy || this.destroyed) return; this.busy=true;
        try {
            const result=await this.config.requestProductCommand('blackbox',{action:'status'});
            if(this.destroyed) return;
            const initial=this.status===null;
            this.status=result['status'] as Status; this.recordingMode=this.status.mode; this.sessions=result['sessions'] as Session[];
            if(initial) { this.partMiB=this.status.part_mib; this.retention=this.status.sessions_limit; }
            if(!this.selected) this.selected=this.status.session_id;
            this.message=this.status.recording ? 'Local recording active.' : 'Recording unavailable. Check disk access; gameplay continues.';
            await this.loadActivity();
        } catch { if(!this.destroyed) this.message='Black Box is not responding. Use the local desktop app and start or reconnect the backend.'; }
        finally { this.busy=false; }
    }
    async loadActivity() {
        if(!this.selected) return;
        const selection=this.selected;
        try { const r=await this.config.requestProductCommand('blackbox',{action:'activity',session_id:selection});
            if(!this.destroyed && selection===this.selected) this.records=r['records'] as BlackBoxRecord[];
        } catch { this.records=[]; }
    }
    async setMode(mode:string) {
        if(mode==='verbose' && !confirm('Enable private Verbose Debug for this backend session? Redacted conversation and tool context may contain personal information. Do not share private exports without reviewing them.')) { this.recordingMode=this.status?.mode ?? 'standard'; return; }
        try { await this.config.requestProductCommand('blackbox',{action:'mode',mode,confirm_private:mode==='verbose'}); await this.refresh(); }
        catch { this.recordingMode=this.status?.mode ?? 'standard'; this.message='Recording mode was not changed.'; }
    }
    async setLimits() {
        try { await this.config.requestProductCommand('blackbox',{action:'limits',part_mib:this.partMiB,sessions:this.retention}); await this.refresh(); }
        catch { this.message='Limits not changed. Use 1–16 MiB and 1–20 sessions.'; }
    }
    async openFolder() { try { await this.tauri.openBlackBoxFolder(); } catch { this.message='Folder opening requires the local desktop app.'; } }
    async exportSession(text:boolean, privateExport:boolean) {
        if(this.exporting || !this.selected) return;
        if(privateExport && !confirm('Export PRIVATE diagnostic context? It may contain personal conversation despite redaction. This file is not an ordinary sanitized support bundle. Review before sharing.')) return;
        this.exporting=true; this.message='Preparing bounded session export…';
        let token='';
        try {
            const session=this.selected;
            const prepared=await this.config.requestProductCommand('blackbox',{action:'export',session_id:session,text,private:privateExport,confirm_private:privateExport},120000);
            token=String(prepared['token']); const chunks:Uint8Array[]=[]; let offset=0;
            while(!this.destroyed) {
                const part=await this.config.requestProductCommand('blackbox',{action:'chunk',token,offset,text});
                chunks.push(Uint8Array.from(atob(String(part['data'])),c=>c.charCodeAt(0))); offset=Number(part['next_offset']);
                if(part['done']) break;
            }
            if(this.destroyed) return;
            const url=URL.createObjectURL(new Blob(chunks,{type:text?'text/plain;charset=utf-8':'application/x-ndjson'}));
            const link=document.createElement('a'); link.href=url; link.download=blackBoxFilename(session,text,privateExport); link.click();
            setTimeout(()=>URL.revokeObjectURL(url),1000);
            this.message=privateExport?'PRIVATE export downloaded. Review it carefully before sharing.':'Sanitized retained timeline downloaded. Sequence gaps indicate incomplete evidence.';
        } catch { this.message='Export failed or expired. Recording continues.'; }
        finally {
            if(token) void this.config.requestProductCommand('blackbox',{action:'chunk',token,offset:0,text,remove:true}).catch(()=>{});
            this.exporting=false;
        }
    }
}
