import assert from "node:assert/strict";
import test from "node:test";
import { BehaviorSubject, firstValueFrom } from "rxjs";

import { TarsApplicationCoordinator } from "../../ui/src/app/services/tars-application-coordinator.service";
import { TarsRuntimeFacade } from "../../ui/src/app/services/tars-runtime-facade.service";

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function lifecycleHarness(initialConfig: Record<string, unknown> | null = null) {
    const calls: string[] = [];
    const runMode$ = new BehaviorSubject<"starting" | "configuring" | "running" | "error">("starting");
    const config$ = new BehaviorSubject<any>(initialConfig);
    const tauri = {
        runMode$,
        runExe: async () => { calls.push("runExe"); return []; },
        requestRuntimeState: async () => { calls.push("requestState"); },
        send_start_signal: async () => { calls.push("sendStart"); },
        restart_process: async () => { calls.push("restart"); },
        createOverlay: async () => { calls.push("createOverlay"); },
        destroyOverlay: async () => { calls.push("destroyOverlay"); },
    };
    const coordinator = new TarsApplicationCoordinator(
        tauri as never,
        { config$ } as never,
        { clearLogs: () => calls.push("clearLogs") } as never,
        { clearChat: () => calls.push("clearChat") } as never,
        { open: () => undefined } as never,
    );
    return { calls, config$, coordinator, runMode$ };
}

test("coordinator initializes once and propagates runtime state", async () => {
    const { calls, coordinator, runMode$ } = lifecycleHarness();
    const states: string[] = [];
    coordinator.state$.subscribe((state) => states.push(state));

    await coordinator.initialize();
    await coordinator.initialize();
    runMode$.next("configuring");
    runMode$.next("running");

    assert.deepEqual(calls, ["runExe"]);
    assert.deepEqual(states, ["stopped", "starting", "configuring", "running"]);
});

test("secondary renderer attaches without owning backend startup", async () => {
    const { calls, config$, coordinator, runMode$ } = lifecycleHarness();
    await coordinator.attachToExistingRuntime();
    config$.next({ cn_autostart: true });
    await flush();
    runMode$.next("running");

    assert.deepEqual(calls, ["requestState"]);
    assert.equal(coordinator.getCurrentState(), "running");
    await assert.rejects(() => coordinator.returnToConfiguration(), /attached read-only/);
});

test("autostart preserves session clear and backend start sequencing", async () => {
    const { calls, config$, coordinator } = lifecycleHarness();
    await coordinator.initialize();
    config$.next({
        cn_autostart: true,
        overlay_mode: "disabled",
        overlay_show_avatar: true,
        overlay_show_chat: true,
        overlay_show_hud: false,
    });
    await flush();

    assert.deepEqual(calls, ["runExe", "clearLogs", "clearChat", "sendStart"]);
});

test("start and restart preserve overlay sequencing", async () => {
    const { calls, coordinator } = lifecycleHarness({
        cn_autostart: false,
        overlay_mode: "desktop",
        overlay_show_avatar: true,
        overlay_show_chat: true,
        overlay_show_hud: false,
        overlay_screen_id: -1,
    });
    await coordinator.initialize();
    await coordinator.startAssistant();
    await coordinator.returnToConfiguration();

    assert.deepEqual(calls, [
        "runExe",
        "createOverlay",
        "clearLogs",
        "clearChat",
        "sendStart",
        "destroyOverlay",
        "restart",
    ]);
    assert.equal(coordinator.getCurrentState(), "restarting");
});

function facadeHarness() {
    const applicationState$ = new BehaviorSubject<any>("running");
    const action$ = new BehaviorSubject<any>("thinking");
    const chatHistory$ = new BehaviorSubject<any[]>([
        { index: 1, timestamp: "2026-01-01T00:00:00Z", role: "cmdr", message: "Report." },
        { index: 2, timestamp: "2026-01-01T00:00:01Z", role: "covas", message: "Still here." },
        { index: 3, timestamp: "2026-01-01T00:00:02Z", role: "action", message: "Checking route" },
    ]);
    const config$ = new BehaviorSubject<any>({
        llm_provider: "openai",
        llm_model_name: "gpt-6-luna",
        api_key: "TOP-SECRET-OPENAI",
        llm_api_key: "",
        agent_llm_provider: "openai",
        agent_llm_model_name: "gpt-6-luna",
        agent_llm_api_key: "",
        vision_provider: "openai",
        vision_model_name: "gpt-6-luna",
        vision_api_key: "",
        vision_var: true,
        stt_provider: "plugin:parakeet",
        stt_model_name: "parakeet",
        stt_api_key: "",
        tts_provider: "plugin:pocket-tts",
        tts_model_name: "pocket-tts",
        tts_api_key: "",
        embedding_provider: "plugin:gemma",
        embedding_model_name: "gemma",
        embedding_api_key: "TOP-SECRET-EMBEDDING",
        ptt_var: "push_to_talk",
    });
    const provider_install_status$ = new BehaviorSubject<any>(null);
    const emptyProjection = () => new BehaviorSubject<any>(null);
    const currentStatus$ = new BehaviorSubject<any>({ flags: { Docked: false } });
    const coordinator = {
        state$: applicationState$,
        initialize: async () => undefined,
        attachToExistingRuntime: async () => undefined,
        startAssistant: async () => undefined,
        returnToConfiguration: async () => undefined,
    };
    const facade = new TarsRuntimeFacade(
        coordinator as never,
        { action$ } as never,
        { chatHistory$ } as never,
        { config$, provider_install_status$ } as never,
        {
            commander$: new BehaviorSubject({ Commander: "Test Commander" }),
            location$: new BehaviorSubject({ StarSystem: "Sol", Body: "Earth" }),
            shipInfo$: new BehaviorSubject({ Ship: "CobraMkIII", ShipIdent: "TARS" }),
            target$: emptyProjection(),
            currentStatus$,
        } as never,
        { logs$: new BehaviorSubject<any[]>([]) } as never,
    );
    return { facade };
}

test("facade exposes typed interaction and conversation state", async () => {
    const { facade } = facadeHarness();
    assert.deepEqual(await firstValueFrom(facade.interactionState$), {
        phase: "thinking",
        derived: true,
    });
    const conversation = await firstValueFrom(facade.conversation$);
    assert.deepEqual(conversation.map((entry) => entry.role), ["commander", "tars", "activity"]);
});

test("general runtime facade never emits credential values", async () => {
    const { facade } = facadeHarness();
    const summary = await firstValueFrom(facade.configuration$);
    const serialized = JSON.stringify(summary);

    assert.equal(serialized.includes("api_key"), false);
    assert.equal(serialized.includes("API"), false);
    assert.equal(serialized.includes("TOP-SECRET"), false);
    assert.equal(summary?.llm.configured, true);
    assert.equal(summary?.stt.configured, true);
});

test("health remains honest and leaves external integrations empty", async () => {
    const { facade } = facadeHarness();
    const health = await firstValueFrom(facade.health$);
    const journal = health.find((item) => item.component === "elite-journal");
    const plugins = health.find((item) => item.component === "plugins");

    assert.equal(journal?.status, "unknown");
    assert.equal(journal?.evidence, "not-exposed");
    assert.equal(plugins?.status, "unknown");
    assert.deepEqual(await firstValueFrom(facade.externalIntegrations$), []);
});
