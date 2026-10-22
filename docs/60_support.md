# TARS support and issue reports

Report TARS problems through [TARS GitHub Issues](https://github.com/rex688-png/TARS/issues).
Search existing issues first. Upstream COVAS maintainers, issue trackers and
Discord communities are not designated TARS support channels.

## Include enough to reproduce

- TARS package version and frontend build SHA from **Settings → Diagnostics →
  Build information**, plus the release/workflow you downloaded.
- Windows version, MSI or portable use, and whether this is a fresh install or upgrade.
- Selected provider names and whether installation/restart completed, without keys.
- Steps, expected/actual outcome and whether the problem happens without Elite,
  with Elite, or only with the optional Observatory feed.
- A sanitized diagnostic export if useful. Review all attachments before posting.

Use [troubleshooting](troubleshooting.md) for initial checks. **Export diagnostics**
is designed to exclude credentials, prompt, memory, conversation and raw log
messages; arbitrary log/config files do not have that guarantee. Do not upload
`config.json`, backups, your full profile, journals, databases, recordings or
screenshots containing private information. Redact commander names and local
paths from any manually shared material.

## Security concerns

Use [private vulnerability reporting](https://github.com/rex688-png/TARS/security/advisories/new)
where available. If it is unavailable, open an issue asking for a private contact
without disclosing the vulnerability or private data. See the
[security policy](https://github.com/rex688-png/TARS/blob/main/SECURITY.md).

A security-software detection is not automatically a false positive. Keep
protection enabled, verify the reviewed build and available checksums, and report
the detection name and source without posting quarantined binaries publicly.
No response-time guarantee or stable-release support lifetime is promised here.
