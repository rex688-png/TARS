/** Completion is profile metadata, never inferred from optional provider installation. */
import type { ModelProviderDefinition } from './plugin-settings';
export interface SetupProfile { commander_name?: string; llm_provider?: string; llm_api_key?: string; api_key?: string; tars_setup_step?: number; tars_setup_complete?: boolean; }
export function needsSetup(config: SetupProfile): boolean {
    if (config.tars_setup_complete) return false;
    if ((config.tars_setup_step ?? 0) > 0) return true;
    const provider = config.llm_provider ?? '';
    const configured = provider.startsWith('plugin:') || ['custom','local-ai-server'].includes(provider) || Boolean(config.llm_api_key || config.api_key);
    return !(config.commander_name?.trim() && provider !== 'none' && configured);
}

/** Only the required AI choice gates finishing setup; speech and Elite remain optional. */
export function setupFinishProblem(config: SetupProfile, providers: readonly ModelProviderDefinition[]): string | null {
    if (!config.commander_name?.trim()) return 'Set a commander name in General before finishing setup.';
    const selected = config.llm_provider ?? '';
    if (selected === 'openai' || selected === 'openrouter') {
        if (!config.llm_api_key?.trim() && !config.api_key?.trim()) return 'Save an API key in AI & Voice before finishing setup.';
        return null;
    }
    if (selected.startsWith('plugin:') && providers.some(provider =>
        provider.kind === 'llm' && selected === `plugin:${provider.plugin_guid}:${provider.id}`)) return null;
    return 'Choose an available AI provider in AI & Voice before finishing setup.';
}
