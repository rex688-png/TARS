// Black Box exports must not enter ordinary logs, remote broadcasts or replay caches.
export function isBlackBoxLine(value) {
  if (typeof value !== 'string') return false;
  try {
    const type = JSON.parse(value)?.type;
    return type === 'blackbox' || type === 'blackbox_result';
  } catch { return false; }
}
