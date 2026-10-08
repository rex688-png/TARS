import assert from "node:assert/strict";
import test from "node:test";
import { BehaviorSubject, firstValueFrom, Subject } from "rxjs";

import { TarsApplicationCoordinator } from "../../ui/src/app/services/tars-application-coordinator.service";
import { TarsRuntimeFacade } from "../../ui/src/app/services/tars-runtime-facade.service";
import { TarsProviderRegistry } from "../../ui/src/app/services/tars-provider-registry";
import { ConfigService } from "../../ui/src/app/services/config.service";

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
    const output$ = new Subject<any>();
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
        { output$ } as never,
    );
    return { facade, output$, applicationState$ };
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

test("provider health uses observed initialization and resets on backend restart", () => {
    const { facade, output$, applicationState$ } = facadeHarness();
    const reports: any[] = [];
    const subscription = facade.health$.subscribe((health) => reports.push(health));
    output$.next({ type: "runtime_components", models: true, stt: true, tts: false, memory: true });
    assert.equal(reports.at(-1).find((entry: any) => entry.component === "models").status, "ready");
    assert.equal(reports.at(-1).find((entry: any) => entry.component === "tts").status, "unavailable");
    applicationState$.next("restarting");
    assert.equal(reports.at(-1).find((entry: any) => entry.component === "models").status, "busy");
    subscription.unsubscribe();
});

test("backend loss is an error without reclassifying optional Elite state", () => {
    const { facade, applicationState$ } = facadeHarness();
    const reports: any[] = [];
    const subscription = facade.health$.subscribe((health) => reports.push(health));
    applicationState$.next("error");
    const latest = reports.at(-1);
    assert.equal(latest.find((entry: any) => entry.component === "backend").status, "error");
    assert.equal(latest.find((entry: any) => entry.component === "elite-journal").status, "unknown");
    assert.equal(latest.find((entry: any) => entry.component === "plugins").status, "unknown");
    subscription.unsubscribe();
});

test("TARS provider registry filters inherited UI clutter centrally", () => {
    assert.deepEqual(
        TarsProviderRegistry.options("llm").map((option) => option.value),
        ["openai", "openrouter"],
    );
    assert.deepEqual(
        TarsProviderRegistry.options("stt").map((option) => option.value),
        ["openai", "none"],
    );
    assert.equal(TarsProviderRegistry.options("tts").some((option) => option.value === "edge-tts"), true);
    assert.equal(TarsProviderRegistry.options("embedding").some((option) => option.value === "google-ai-studio"), false);

    const legacy = TarsProviderRegistry.options("stt", "custom-multi-modal");
    assert.equal(legacy.at(-1)?.value, "custom-multi-modal");
    assert.equal(legacy.at(-1)?.legacy, true);
});

test("TARS provider registry accepts only controlled plugin providers", () => {
    const providers = [
        { kind: "stt", id: "parakeet-stt", label: "Parakeet STT", plugin_guid: "b77dec4f-8993-4213-8d44-caf902dabc6d", settings_config: [], is_builtin: true },
        { kind: "stt", id: "arbitrary", label: "Arbitrary", plugin_guid: "not-approved", settings_config: [], is_builtin: false },
    ] as const;
    assert.deepEqual(
        TarsProviderRegistry.filterPluginProviders(providers, "stt").map((provider) => provider.id),
        ["parakeet-stt"],
    );
});

test("missing local provider stays visible until real registration", () => {
    const current = "plugin:b77dec4f-8993-4213-8d44-caf902dabc6d:parakeet-stt";
    assert.match(TarsProviderRegistry.options("stt", current).at(-1)!.label, /not registered/);
    const registered = [{ kind: "stt" as const, id: "parakeet-stt", label: "Parakeet", plugin_guid: "b77dec4f-8993-4213-8d44-caf902dabc6d", settings_config: [], is_builtin: false }];
    assert.equal(TarsProviderRegistry.options("stt", current, registered).some(p => p.value === current), false);
    assert.equal(TarsProviderRegistry.filterPluginProviders(registered, "stt").length, 1);
});

test("prompt save waits for its backend acknowledgement and propagates disk failure", async () => {
    const output$ = new Subject<any>();
    const commands: any[] = [];
    const service: ConfigService = Object.assign(Object.create(ConfigService.prototype), {
        tauriService: { output$, send_command: async (message: any) => { commands.push(message); } },
    });
    let finished = false;
    const saving = service.setTarsPrompt("Saved prompt").then(value => { finished = true; return value; });
    output$.next({ type: "tars_prompt_result", request_id: "another-window", success: true, prompt: "Wrong" });
    await flush();
    assert.equal(finished, false);
    output$.next({ type: "tars_prompt_result", request_id: commands[0].request_id, success: true, prompt: "Saved prompt" });
    assert.equal(await saving, "Saved prompt");
    const resetting = service.resetTarsPrompt();
    output$.next({ type: "tars_prompt_result", request_id: commands[1].request_id, success: false, error: "Unable to save" });
    await assert.rejects(resetting, /Unable to save/);
});

test('settings Saved feedback requires the matching backend disk acknowledgement', async () => {
    const output$ = new Subject<any>();
    const commands: any[] = [];
    const service = new ConfigService({ output$, send_command: async (message: any) => { commands.push(message); } } as never);
    output$.next({ type:'config', config:{api_key:'synthetic-test-value', plugin_settings:{}} });
    const states: string[] = [];
    service.saveState$.subscribe(value => states.push(value));
    const saving = service.changeConfig({plugin_settings:{fixture:{onnx_threads:1}}});
    assert.equal(states.at(-1), 'Saving…');
    output$.next({type:'config_save_result',request_id:'unrelated',success:true});
    assert.equal(states.at(-1), 'Saving…');
    output$.next({type:'config_save_result',request_id:commands[0].request_id,success:true});
    await saving;
    assert.equal(states.at(-1), 'Saved');
    const failing = service.changeConfig({api_key:'synthetic-other-value'});
    output$.next({type:'config_save_result',request_id:commands[1].request_id,success:false,error:'Unable to save configuration'});
    await assert.rejects(failing, /Unable to save/);
    assert.match(states.at(-1)!, /Error saving/);
});
