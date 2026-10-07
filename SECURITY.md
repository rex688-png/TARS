# Security policy

Please report vulnerabilities privately through
[GitHub's private vulnerability reporting](https://github.com/rex688-png/TARS/security/advisories/new).
If private reporting is unavailable, open an issue asking for a private contact
without including exploit details, credentials, logs or personal configuration.
The current development baseline is the supported security target; no stable
release support lifetime is promised yet.

Never attach your exported working config, API keys, tokens, recordings or raw
conversation database to public issues. Redact commander names and local paths
from diagnostic logs. Configuration currently stores credentials locally and
legacy settings UI receives them; the general runtime facade omits them. Protect
your Windows profile and backups. Do not expose the remote WebSocket interface
to untrusted networks.

Approved provider packages use pinned hashes/manifests, safe extraction and
atomic installation. Downloads remain explicit. The bundled behavior plugins
are pinned separately; do not bypass verification to install arbitrary code.
An absent optional Observatory feed is not a reason to disable security checks.

Current-tree scanning complements, but cannot prove the absence of, secrets.
Historical cached PR refs are being handled separately through GitHub Support;
this stabilization work neither rewrites history nor attempts to remove them.
