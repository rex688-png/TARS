import type { TarsComponentHealth } from './tars-runtime-facade.models';

export function healthLabel(item: TarsComponentHealth): string {
    if (item.evidence === 'not-exposed' || item.status === 'unknown') return 'Not verified';
    return ({ ready: 'READY', available: 'AVAILABLE', busy: 'STARTING', unavailable: 'UNAVAILABLE', error: 'ERROR' } as const)[item.status];
}

export function selfCheck(health: readonly TarsComponentHealth[]): 'READY' | 'WARNING' | 'FAILED' {
    if (health.some(item => item.evidence === 'observed' && item.status === 'error'
        && ['backend', 'models', 'stt', 'tts', 'memory'].includes(item.component))) return 'FAILED';
    if (health.some(item => item.status !== 'ready' || item.evidence !== 'observed')) return 'WARNING';
    return health.length ? 'READY' : 'WARNING';
}

export function providerRuntimeLabel(installed: boolean, selected: boolean, application: string,
    observed: TarsComponentHealth | undefined): string {
    if (!installed) return 'UNAVAILABLE';
    if (!selected || application === 'stopped' || application === 'configuring') return 'INSTALLED';
    if (application === 'starting' || application === 'restarting') return 'STARTING';
    if (observed?.evidence === 'observed') return healthLabel(observed);
    return 'AVAILABLE';
}
