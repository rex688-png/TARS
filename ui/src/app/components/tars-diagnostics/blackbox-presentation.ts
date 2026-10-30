export interface BlackBoxRecord {
    seq: number; timestamp: string; component: string; stage: string;
    severity: string; reason?: string; outcome?: string; trace_id?: string;
    event_id?: string; generation_id?: string; delivery_id?: string;
}
export function filterBlackBox(records: BlackBoxRecord[], component = '', severity = '', decision = ''): BlackBoxRecord[] {
    return records.filter(r => (!component || r.component === component) && (!severity || r.severity === severity) && (!decision || r.reason === decision)).slice(-200);
}
export function blackBoxFilename(session: string, text: boolean, privateExport: boolean): string {
    if (!/^[a-f0-9]{32}$/.test(session)) throw new Error('Invalid session');
    return `TARS-${session}.${privateExport ? 'PRIVATE' : 'sanitized'}.${text ? 'txt' : 'jsonl'}`;
}
