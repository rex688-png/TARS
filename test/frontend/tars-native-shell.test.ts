import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import test from "node:test";
import { Subject } from "rxjs";

import { viewForUiCommand } from "../../ui/src/app/main-view/tars-shell-navigation";
import { ChatService } from "../../ui/src/app/services/chat.service";
import { eliteDataStatus, tarsActivityStatus } from "../../ui/src/app/main-view/tars-status";
import { shouldFollowConversation } from "../../ui/src/app/components/chat-container/chat-scroll";
import { toolPresentation, visibleInNormalChat } from "../../ui/src/app/components/chat-container/chat-presentation";
import { LoggingService } from "../../ui/src/app/services/logging.service";

test("legacy UI commands map into the persistent four-view shell", () => {
    assert.equal(viewForUiCommand("tars", "search"), "tars");
    assert.equal(viewForUiCommand("exploration", "search"), "exploration");
    assert.equal(viewForUiCommand("tars", "navigation"), "exploration");
    assert.equal(viewForUiCommand("tars", "storage"), "storage");
    assert.equal(viewForUiCommand("storage", "chat"), "tars");
    assert.equal(viewForUiCommand("tars", "actions"), "settings");
    assert.equal(viewForUiCommand("storage", "unknown"), "storage");
});

test("tool search result stays in conversation and clears with the session", () => {
    const output$ = new Subject<any>();
    const chat = new ChatService({ output$ } as never);
    const results: any[] = [];
    chat.searchResult$.subscribe(value => results.push(value));
    output$.next({ type: "event", event: {
        kind: "tool", request: [{ function: { name: "web_search_agent" } }],
        results: [{ content: "Petrie's Pride — outfitting, repair, refuel" }],
    } });
    assert.equal(results.at(-1).content, "Petrie's Pride — outfitting, repair, refuel");
    chat.clearChat();
    assert.equal(results.at(-1), null);
});

test("search cards follow conversation order and internal queries stay out of normal chat", () => {
    const output$ = new Subject<any>();
    const chat = new ChatService({ output$ } as never);
    output$.next({ type: "chat", role: "cmdr", message: "Find outfitting", index: 1, timestamp: "2026-10-08T12:00:00Z" });
    output$.next({ type: "event", index: 2, timestamp: "2026-10-08T12:00:01Z", event: {
        kind: "tool_processing", name: "web_search_agent", tool_call_id: "search-1",
        content: { query: "current live ship fuel level for commander", internal_tool_name: "web_search_agent" },
    } });
    assert.equal(chat.getCurrentChat()[1].message, "Checking fuel data…");
    assert.equal(chat.getCurrentChat()[1].message.includes("commander"), false);
    output$.next({ type: "event", index: 3, timestamp: "2026-10-08T12:00:02Z", event: {
        kind: "tool", request: [{ function: { name: "web_search_agent" } }],
        results: [{ tool_call_id: "search-1", content: "**Petrie's Pride**\nOutfitting" }],
    } });
    output$.next({ type: "chat", role: "covas", message: "Petrie's Pride has outfitting.", index: 4, timestamp: "2026-10-08T12:00:03Z" });
    assert.deepEqual(chat.getCurrentChat().map(entry => entry.role), ["cmdr", "search_result", "covas"]);
    assert.equal(chat.getCurrentChat()[1].searchDetails, "**Petrie's Pride**\nOutfitting");
});

test("raw actions stay diagnostic while results and transient activity stay in Chat", () => {
    const raw = { type: "chat", role: "action", message: "showUI" } as any;
    const transient = { type: "chat", role: "action", message: "Finding nearby stations…", synthetic: true, processingText: "In progress" } as any;
    const result = { type: "chat", role: "search_result", message: "Search result", searchDetails: "Station found" } as any;
    assert.equal(toolPresentation(raw), "diagnostic");
    assert.equal(visibleInNormalChat(raw), false);
    assert.equal(toolPresentation(transient), "transient");
    assert.equal(visibleInNormalChat(transient), true);
    assert.equal(toolPresentation(result), "result");
    assert.equal(visibleInNormalChat(result), true);

    const output$ = new Subject<any>();
    const diagnostics = new LoggingService({ output$ } as never);
    output$.next({ type: "event", timestamp: "2026-01-01T00:00:00Z", event: { kind: "tool_processing", name: "showUI", content: { query: "internal" } } });
    assert.match(diagnostics.getCurrentLogs()[0].message, /showUI/);
});

test("a failed search remains an inline result and does not navigate", () => {
    const output$ = new Subject<any>();
    const chat = new ChatService({ output$ } as never);
    output$.next({ type: "chat", role: "cmdr", message: "Find a station", index: 1, timestamp: "2026-01-01T00:00:00Z" });
    output$.next({ type: "event", index: 2, timestamp: "2026-01-01T00:00:01Z", event: {
        kind: "tool", request: [{ function: { name: "web_search_agent" } }],
        results: [{ content: "Station lookup unavailable; retry later." }],
    } });
    assert.deepEqual(chat.getCurrentChat().map(entry => entry.role), ["cmdr", "search_result"]);
    assert.match(chat.getCurrentChat()[1].searchDetails!, /unavailable/);
    assert.equal(viewForUiCommand("tars", "search"), "tars");
});

test("Elite status does not mistake cached state for live telemetry", () => {
    assert.equal(eliteDataStatus(false, null, 100_000), "ELITE OFFLINE");
    assert.equal(eliteDataStatus(true, null, 100_000), "LAST KNOWN");
    assert.equal(eliteDataStatus(true, 99_000, 100_000), "ELITE LIVE");
    assert.equal(eliteDataStatus(true, 1_000, 100_000), "LAST KNOWN");
});

test("TARS activity distinguishes readiness from failure and optional Elite state", () => {
    assert.equal(tarsActivityStatus("running", "idle"), "READY");
    assert.equal(tarsActivityStatus("running", "listening"), "LISTENING");
    assert.equal(tarsActivityStatus("running", "thinking"), "THINKING");
    assert.equal(tarsActivityStatus("starting", "idle"), "STARTING");
    assert.equal(tarsActivityStatus("configuring", "idle"), "OFFLINE");
    assert.equal(tarsActivityStatus("error", "idle"), "ERROR");
});

test("conversation follows the tail but preserves deliberate upward scrolling", () => {
    assert.equal(shouldFollowConversation(1000, 490, 500), true);
    assert.equal(shouldFollowConversation(1000, 200, 500), false);
    const cardCss = readFileSync("ui/src/app/components/chat-container/chat-container.component.css", "utf8");
    assert.doesNotMatch(cardCss, /\.search-result-card\s*\{[^}]*position:\s*(sticky|fixed)/);
});

test("Settings use TARS categories and keep raw action logs in Diagnostics", () => {
    const settings = readFileSync("ui/src/app/components/settings-menu/settings-menu.component.html", "utf8");
    const shell = readFileSync("ui/src/app/main-view/main-view.component.html", "utf8");
    for (const label of ["GENERAL", "AI &amp; VOICE", "PERSONALITY", "PLUGINS", "DIAGNOSTICS"]) {
        assert.ok(settings.includes(label));
    }
    assert.match(settings, /app-actions-settings/);
    assert.match(shell, /settingsCategory === 4/);
    assert.match(shell, /app-log-container/);
    const pluginUi = readFileSync("ui/src/app/components/plugin-settings/plugin-settings.component.ts", "utf8");
    for (const icon of ["travel_explore", "public", "sensors"]) assert.ok(pluginUi.includes(icon));
});

test("only four TARS destinations are primary and chat retains an inline result card", () => {
    const root = path.resolve("ui/src/app");
    const shell = readFileSync(path.join(root, "main-view/main-view.component.html"), "utf8");
    const chat = readFileSync(path.join(root, "components/chat-container/chat-container.component.html"), "utf8");
    const nav = [...shell.matchAll(/selectView\('(tars|exploration|storage|settings)'\)/g)].map(match => match[1]);
    assert.deepEqual(nav.slice(0, 4), ["tars", "exploration", "storage", "settings"]);
    assert.equal(nav.length, 5); // Configure PTT is a settings entry point, not primary navigation.
    assert.match(chat, /class="search-result-card"/);
    assert.match(chat, /<details/);
    assert.doesNotMatch(shell, /<mat-tab/);
    assert.match(shell, /app-settings-menu/);
    assert.match(shell, /app-chat-container/);
    assert.match(shell, /<app-actions-container>/);
    assert.match(shell, /<app-memories-container>/);
    assert.match(shell, /\[class\.is-hidden\]="selectedView !== 'tars'"/);
    assert.doesNotMatch(shell, /showRuntimeView/);
});

test("shell uses production TARS branding and the unmodified canonical avatar", () => {
    const shell = readFileSync("ui/src/app/main-view/main-view.component.ts", "utf8");
    const style = readFileSync("ui/src/app/main-view/main-view.component.css", "utf8");
    const overlayStyle = readFileSync("ui/src/app/overlay-view/overlay-view.component.css", "utf8");
    const settingsStyle = readFileSync("ui/src/app/components/general-settings/general-settings.component.css", "utf8");
    assert.match(shell, /tars-logo-horizontal\.svg/);
    assert.doesNotMatch(shell + style, /EDAI_logo/);
    assert.deepEqual(readFileSync("ui/src/assets/tars-logo-horizontal.svg"), readFileSync("branding/vector/tars-logo-horizontal.svg"));
    const avatar = readFileSync("ui/src/assets/Obraz ChatGPT 28 wrz 2026, 21_39_52.png");
    assert.equal(createHash("sha256").update(avatar).digest("hex"), "4e0103a45a548ef7e700b1c015b42039250d4aad470c4d5d0826b59be5e29143");
    assert.match(style, /\.avatar-frame img \{[^}]*width: 200%/);
    assert.match(overlayStyle, /background-size: 200%/);
    assert.doesNotMatch(overlayStyle, /\.overlay-pngtuber\.canonical-tars-avatar\s*\{/);
    assert.doesNotMatch(settingsStyle, /\.minimal-avatar-image\.canonical-tars-avatar\s*\{/);
});

// Presentation contracts do not require a desktop or live Elite session.
import { providerRuntimeLabel, selfCheck, healthLabel } from '../../ui/src/app/services/tars-health-presentation';
import { TarsProviderRegistry } from '../../ui/src/app/services/tars-provider-registry';
import { TarsPromptEditor } from '../../ui/src/app/components/tars-prompt-settings/tars-prompt-editor';

test('providers are installed before startup, ready only on an observed initialization report', () => {
    const ready = {component: 'tts', status: 'ready', evidence: 'observed', detail: 'Initialized'} as const;
    assert.equal(providerRuntimeLabel(true, true, 'configuring', ready), 'INSTALLED');
    assert.equal(providerRuntimeLabel(true, true, 'starting', undefined), 'STARTING');
    assert.equal(providerRuntimeLabel(true, true, 'running', ready), 'READY');
    assert.equal(providerRuntimeLabel(true, false, 'running', ready), 'INSTALLED');
    assert.equal(providerRuntimeLabel(false, true, 'running', ready), 'UNAVAILABLE');
    assert.equal(providerRuntimeLabel(true, true, 'running', {...ready,status:'error'}), 'ERROR');
    assert.equal(providerRuntimeLabel(true, true, 'running', undefined), 'AVAILABLE');
});

test('self-check does not mistake missing optional telemetry for TARS failure', () => {
    const backend = {component:'backend',status:'ready',evidence:'observed',detail:'Running'} as const;
    const optional = {component:'elite-journal',status:'unknown',evidence:'not-exposed',detail:'No telemetry'} as const;
    assert.equal(selfCheck([backend]), 'READY');
    assert.equal(selfCheck([backend, optional]), 'WARNING');
    assert.equal(healthLabel(optional), 'Not verified');
    assert.equal(selfCheck([{...backend,status:'error'},optional]), 'FAILED');
});

test('normal provider labels never expose UUIDs', () => {
    assert.equal(TarsProviderRegistry.label('plugin:fixture-uuid:pocket-tts'), 'PocketTTS');
    assert.equal(TarsProviderRegistry.label('plugin:fixture-uuid:parakeet-stt'), 'Parakeet STT');
    assert.equal(TarsProviderRegistry.label('plugin:fixture-uuid:gemma-embedding'), 'Gemma Embedding');
    assert.equal(TarsProviderRegistry.label('plugin:fixture-uuid:unknown'), 'Local provider');
});

test('prompt feedback preserves a dirty draft on unrelated updates and disk failure', async () => {
    const editor = new TarsPromptEditor();
    editor.receive('Saved prompt');
    editor.draft = 'Edited prompt';
    editor.receive('Saved prompt');
    assert.equal(editor.feedback, 'Unsaved changes');
    await editor.save(async () => { throw new Error('Disk failure'); });
    assert.equal(editor.draft, 'Edited prompt');
    assert.match(editor.feedback, /Error saving/);
    await editor.save(async () => 'Edited prompt');
    assert.equal(editor.feedback, 'Saved');
    editor.draft = 'More edits'; editor.reload();
    assert.equal(editor.draft, 'Edited prompt');
});

test('Settings offer compact system cards and Personality owns the prompt editor', () => {
    const advanced = readFileSync('ui/src/app/components/advanced-settings/advanced-settings.component.html','utf8');
    const settings = readFileSync('ui/src/app/components/settings-menu/settings-menu.component.html','utf8');
    assert.match(advanced, /tars-setting-card/);
    assert.match(advanced, /subsystem-grid/);
    for (const label of ['AI model','Speech / microphone','Voice / output','Memory','Vision']) assert.ok(advanced.includes(label));
    assert.match(settings, /app-tars-prompt-settings/);
    assert.match(settings, /app-tars-diagnostics/);
    assert.doesNotMatch(settings, /edit the system prompt from General/);
    const styles = readFileSync('ui/src/app/main-view/main-view.component.css','utf8');
    for (const state of ['READY','LISTENING','THINKING','ERROR','ELITE LIVE','LAST KNOWN','ELITE OFFLINE']) assert.ok(styles.includes(`data-status="${state}"`));
});

test('provider presentation uses the central approved names rather than inherited package labels', () => {
    assert.equal(TarsProviderRegistry.pluginLabel('b7ddc677-0cfc-4081-af61-b2ebc2af5fe3', 'COVAS provider'), 'PocketTTS');
    assert.equal(TarsProviderRegistry.pluginLabel('b77dec4f-8993-4213-8d44-caf902dabc6d', 'COVAS provider'), 'Parakeet STT');
});
