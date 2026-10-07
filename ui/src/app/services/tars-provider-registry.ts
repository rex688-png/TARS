import { ModelProviderDefinition } from "./plugin-settings";

export type TarsProviderKind = "llm" | "vlm" | "stt" | "tts" | "embedding";

export interface TarsProviderOption {
    value: string;
    label: string;
    legacy?: boolean;
}

/**
 * Product-level provider policy for every TARS-facing selector.
 *
 * The Python provider registry remains authoritative for download integrity and
 * controlled loading. This registry is the single UI allowlist: it deliberately
 * does not expose every provider inherited from the generic COVAS UI.
 */
export class TarsProviderRegistry {
    private static readonly builtin: Record<TarsProviderKind, readonly TarsProviderOption[]> = {
        llm: [
            { value: "openai", label: "OpenAI" },
            { value: "openrouter", label: "OpenRouter" },
        ],
        vlm: [
            { value: "openai", label: "OpenAI" },
            { value: "none", label: "None" },
        ],
        stt: [
            { value: "openai", label: "OpenAI" },
            { value: "none", label: "None" },
        ],
        tts: [
            { value: "openai", label: "OpenAI" },
            { value: "edge-tts", label: "Edge TTS" },
            { value: "none", label: "None" },
        ],
        embedding: [
            { value: "openai", label: "OpenAI" },
            { value: "none", label: "None" },
        ],
    };

    private static readonly approvedPluginGuids = new Set([
        "d17f20f6-2514-4a1f-9e54-2a3c089f5c2b", // built-in Mistral provider
        "b77dec4f-8993-4213-8d44-caf902dabc6d", // Parakeet STT
        "b7ddc677-0cfc-4081-af61-b2ebc2af5fe3", // Pocket-TTS 0.0.17-tarsfix
        "7fd3d108-4e50-49db-8eb4-f3b4b8d53e66", // Supertonic TTS
        "88d3df68-d949-11f0-b7d9-e768d0e4b754", // Gemma Embedding
    ]);

    static options(kind: TarsProviderKind, current?: string | null, registered: readonly ModelProviderDefinition[] = []): TarsProviderOption[] {
        const options = this.builtin[kind].map((option) => ({ ...option }));
        if (current?.startsWith("plugin:") && !registered.some(
            provider => provider.kind === kind && current === `plugin:${provider.plugin_guid}:${provider.id}`,
        )) {
            options.push({ value: current, label: `${current.split(":").at(-1)} — not registered; install/restart required` });
        }
        if (current && !current.startsWith("plugin:") && !options.some((option) => option.value === current)) {
            options.push({
                value: current,
                label: `${this.label(current)} (existing setting)`,
                legacy: true,
            });
        }
        return options;
    }

    static filterPluginProviders(
        providers: readonly ModelProviderDefinition[],
        kind: TarsProviderKind,
    ): ModelProviderDefinition[] {
        return providers.filter(
            (provider) => provider.kind === kind && this.approvedPluginGuids.has(provider.plugin_guid),
        );
    }

    static label(provider: string | null | undefined): string {
        if (!provider) return "Not set";
        const known = Object.values(this.builtin)
            .flat()
            .find((option) => option.value === provider);
        if (known) return known.label;
        return ({
            "google-ai-studio": "Google AI Studio",
            "local-ai-server": "Local AIServer",
            "custom": "Custom",
            "custom-multi-modal": "Custom Multi-Modal",
        } as Record<string, string>)[provider] ?? provider;
    }
}
