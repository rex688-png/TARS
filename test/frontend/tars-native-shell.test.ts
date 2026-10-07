import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import test from "node:test";
import { Subject } from "rxjs";

import { viewForUiCommand } from "../../ui/src/app/main-view/tars-shell-navigation";
import { ChatService } from "../../ui/src/app/services/chat.service";

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
