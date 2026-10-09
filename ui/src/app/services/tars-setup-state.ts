/** Completion is profile metadata, never inferred from optional provider installation. */
export interface SetupProfile { commander_name?: string; llm_provider?: string; llm_api_key?: string; api_key?: string; tars_setup_step?: number; tars_setup_complete?: boolean; }
export function needsSetup(config: SetupProfile): boolean {
    if (config.tars_setup_complete) return false;
    if ((config.tars_setup_step ?? 0) > 0) return true;
    const provider = config.llm_provider ?? '';
    const configured = provider.startsWith('plugin:') || ['custom','local-ai-server'].includes(provider) || Boolean(config.llm_api_key || config.api_key);
    return !(config.commander_name?.trim() && provider !== 'none' && configured);
}
