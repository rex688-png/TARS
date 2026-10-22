import { Component, OnDestroy } from '@angular/core';
import type { Character } from "../../services/character.service";
import { FormsModule } from '@angular/forms';
import { ConfigService } from '../../services/config.service';
import { TarsPromptEditor } from './tars-prompt-editor';

@Component({
    selector: 'app-tars-prompt-settings', standalone: true, imports: [FormsModule],
    template: `<section class="prompt-card"><h2>TARS personality</h2>
        <p>One TARS. Your saved prompt persists across updates; changes apply to the next session.</p>
        <label for="tars-prompt">System prompt</label>
        <textarea id="tars-prompt" rows="12" [(ngModel)]="editor.draft" [disabled]="editor.busy"></textarea>
        <div class="prompt-actions"><span role="status">{{ editor.feedback }}</span>
            <button type="button" [disabled]="editor.busy || !editor.dirty || !editor.draft.trim()" (click)="save()">Save</button>
            <button type="button" [disabled]="editor.busy" (click)="editor.reload()">Reload saved</button>
            <button type="button" [disabled]="editor.busy" (click)="reset()">Reset to TARS Default</button>
        </div></section>`,
    styles: [`.prompt-card {background:#171e26;border:1px solid #3d4c59;padding:20px;margin-bottom:20px;border-radius:4px}
      h2 {color:#b6dbe9;font-size:18px;margin-top:0} p {color:#aebdc9;font-size:13px}
      textarea {display:block;box-sizing:border-box;width:100%;margin:12px 0;padding:12px;color:#dae5ed;background:#0f151b;border:1px solid #485b6b;line-height:1.6;resize:vertical}
      .prompt-actions {display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:12px} button {background:#263743;color:#cde5ef;border:1px solid #4d6677;padding:8px 12px;cursor:pointer} button:disabled {opacity:.5;cursor:default}`],
})
export class TarsPromptSettingsComponent implements OnDestroy {
    readonly editor = new TarsPromptEditor();
    private subscription = this.configService.config$.subscribe(config => {
        const character = config?.characters[config.active_character_index] as Character | undefined;
        this.editor.receive(character?.character ?? '');
    });
    constructor(private configService: ConfigService) {}
    save(): Promise<void> { return this.editor.save(() => this.configService.setTarsPrompt(this.editor.draft)); }
    reset(): Promise<void> { return this.editor.save(() => this.configService.resetTarsPrompt()); }
    ngOnDestroy(): void { this.subscription.unsubscribe(); }
}
