export class TarsPromptEditor {
    draft = '';
    saved = '';
    busy = false;
    error = false;
    get dirty(): boolean { return this.draft !== this.saved; }
    get feedback(): string { return this.busy ? 'Saving…' : this.error ? 'Error saving — unsaved changes' : this.dirty ? 'Unsaved changes' : 'Saved'; }
    receive(prompt: string): void { if (!this.dirty) this.draft = prompt; this.saved = prompt; }
    reload(): void { this.draft = this.saved; this.error = false; }
    async save(command: () => Promise<string>): Promise<void> {
        this.busy = true; this.error = false;
        try { this.saved = await command(); this.draft = this.saved; }
        catch { this.error = true; }
        finally { this.busy = false; }
    }
}
