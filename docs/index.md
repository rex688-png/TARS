# TARS manual

TARS is a Windows AI copilot for Elite Dangerous: one conversational companion
with a dry sense of humor, voice input and output, game-state awareness, actions,
memory and optional vision. It builds on COVAS:NEXT by RatherRude and contributors;
see [credits and attribution](70_credits.md).

Start with [installation and upgrading](tars-installation.md), then follow
[first steps](05_first_steps.md). Local speech and memory providers are
[separate downloads](tars-alpha-provider-setup.md); selecting one does not install it.

## Find your way

- **Getting Started:** what TARS does, Windows packages and first launch.
- **Configuration:** AI providers, voice, personality, memory and event reactions.
- **Using TARS:** game context, vision and action permissions.
- **Official TARS Plugins:** the six bundled plugins and the optional Observatory feed.
- **Troubleshooting:** diagnostics, common problems and TARS support.
- **Development and Releases:** contributing, source builds and release approval.
- **Credits and Attribution:** upstream foundations and the license.

## Current validation boundary

The repository package version is **0.0.0**, an unreleased placeholder. Automated
Windows builds validate backend, Electron, MSI/ZIP packaging, packaged-profile
checks and disposable MSI upgrade scenarios. This manual does not announce an
approved beta or stable release. Full application installation/upgrading on a
physical Windows 11 PC, real microphone/speaker operation and live Elite gameplay
still require acceptance. See [release readiness](release-readiness.md).

Use reviewed TARS packages. The inherited COVAS installer, updater and plugin
installation instructions are not TARS setup instructions.
