# Development and documentation

The host source is in [rex688-png/TARS](https://github.com/rex688-png/TARS).
The application is Windows-only; running isolated tests on another operating
system does not establish supported runtime behavior there. See the repository's
[current README](https://github.com/rex688-png/TARS/blob/main/readme.md) for source
setup and focused backend, frontend and Electron commands.

## Product boundaries

The TARS runtime loads its verified six-plugin bundle and approved provider
packages. Canonical behavior-plugin development belongs in
[TARS-Plugins](https://github.com/rex688-png/TARS-Plugins); do not follow the
inherited arbitrary-folder installation workflow as TARS product instructions.
`vendor/tars-plugins/provenance.json` records the exact source pin and payload
hashes. `python tools/verify_tars_bundle.py` checks the vendored payload.

Current code references (external repository links):

- [PluginManager](https://github.com/rex688-png/TARS/blob/main/src/lib/PluginManager.py)
  defines the fixed behavior-plugin order and provider boundary.
- [Runtime contracts](https://github.com/rex688-png/TARS/blob/main/docs/runtime-contracts.md)
  record a historical lifecycle audit. Compare its findings with current code;
  it is developer reference, not an end-user guide.
- [Security policy](https://github.com/rex688-png/TARS/blob/main/SECURITY.md)
  explains private reporting and profile safety.

## Work on this manual

Install `mkdocs-material` in an isolated Python environment, then run
`mkdocs build --strict` from the repository root. MkDocs 1.6 or newer supports the
`exclude_docs` policy used here. The existing Pages workflow installs Material
and deploys main; a local build neither publishes nor changes repository settings.

`mkdocs.yml` contains both the public navigation and an explicit publication
allowlist using supported exclusion patterns. A page needs to be admitted there
to be built. Merely omitting a file from navigation would not prevent publication.
Inspect generated HTML and search output for unwanted pages and broken links.
Keep the seven top-level navigation groups concise for mobile readers.

The repository's documentation inventory records classification and publication
status. Historical TARS phase reports and inherited COVAS references remain in
source control but are excluded from this public site, including raw legacy HTML,
troubleshooting data, screenshots and voice-training material. Do not rewrite old
test evidence to describe the current product. Preserve licensing and attribution.

Read [contributing](55_contributing.md) before submitting changes, and
[release approval](release-readiness.md) before interpreting a CI artifact as a release.
