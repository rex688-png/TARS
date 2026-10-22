# TARS — Elite Dangerous AI copilot

TARS is a voice-first companion for Elite Dangerous, built on the mature
[COVAS:NEXT](https://github.com/RatherRude/Elite-Dangerous-AI-Integration) runtime.
It combines conversation, game context, actions, search, memory and vision with
one TARS identity. It is actively evolving and supports Windows only.
Physical Windows acceptance of the current stabilization build is still
pending. This is **not an accepted Alpha 0.1 release**.

## Install and configure

Follow the [TARS installation guide](docs/tars-installation.md). Use only TARS
MSI/portable packages from this repository's reviewed builds or
[Releases](https://github.com/rex688-png/TARS/releases), when available. Actions
artifacts are temporary test builds, not permanent user releases. TARS does not
query or install upstream COVAS updates.

A clean installation uses `%APPDATA%\TARS`, one TARS character and the exact
302-event factory reaction map. Main/agent/vision defaults are OpenAI GPT-6 Luna;
you supply your own API credentials. OpenRouter is also supported for LLMs.
Provider availability and usage costs depend on your account and hardware.

Local Parakeet STT, Pocket-TTS **0.0.17-tarsfix**, Supertonic TTS and Gemma
Embedding are explicit opt-in downloads, not multi-gigabyte MSI payloads.
Install them from the provider settings, wait for verification/extraction to
finish, then restart. See [provider setup](docs/tars-alpha-provider-setup.md).
Existing user settings and saved prompt edits are retained across upgrades;
**Reset to TARS Default** is an explicit action.

## One TARS, six official behavior plugins

The controlled, verified bundle contains TARSExplorer, TARSNavigator, TARSGalaxy,
TARSChatter, TARSExpedition and TARSObservatoryBridge. They are internal parts of
one assistant, not separate personas. Source and file hashes are recorded in
[`vendor/tars-plugins/provenance.json`](vendor/tars-plugins/provenance.json).
Arbitrary plugin directories are not enabled by the TARS profile.

[Observatory Bridge](docs/elite-observatory-bridge.md) is optional. It consumes
the external Observatory feed at `%LOCALAPPDATA%\TARS\observatory\events.jsonl`.
A missing feed is non-fatal; the Observatory-side writer is not bundled here.

## Development and verification

Use Python 3.12 with `requirements.txt`, then `npm ci` and `npm ci --prefix ui`.
Key checks on a configured Windows development machine:

```sh
python -m pytest --timeout 10 test -v --capture=no
python tools/verify_tars_bundle.py
node --test test/electron/*.test.js
npm run test:frontend-foundation
npm run build:ui
```

Windows CI builds and tests the Python executable, UI, Electron package and MSI.
Audio and live Elite behavior still require real-PC validation. Linux and
Flatpak are not supported. See [profile behavior](docs/tars-product-profile.md),
[Windows baseline notes](docs/windows-baseline-audit.md), and
[security guidance](SECURITY.md). Historical Task 1 evidence deliberately keeps
its original five-plugin baseline and revision labels.

## Attribution

TARS builds on COVAS:NEXT by RatherRude and contributors. Its journal/Status
pipeline, model/audio lifecycle, tools, memory, vision, overlays and other mature
infrastructure remain essential. Preserve the LICENSE and upstream and
third-party notices. Elite Dangerous belongs to Frontier Developments;
this is an independent community project.
