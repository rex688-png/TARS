# Frequently asked questions

## Which systems are supported?

TARS is a Windows-only project. Linux, Flatpak, Steam Deck, Proton, and Wine are
not supported or validated.

## Are local providers included in the installer?

No. Parakeet STT, Pocket-TTS 0.0.17-tarsfix, Supertonic TTS, and Gemma Embedding
are optional downloads through the controlled provider setup. Cloud API usage
may incur provider charges. A ChatGPT subscription does not include OpenAI API
usage.

## Why does TARS show Last Known Elite data?

When Elite is not running, saved journal state may still be available. Last
Known does not mean live fuel, route, or ship telemetry. Start Elite and verify
journal access before reporting a live-state issue.

## What if voice input or output is interrupted?

Check the selected provider and audio device, then try PTT or headphones to
prevent the microphone from hearing TARS. Local providers require separate
installation and a restart before use.

## What if security software flags a build?

Do not assume it is a false positive or disable protection. Check the build's
provenance and checksum, then report the detection with sanitized diagnostics.
Never post API keys or your full private configuration.

## Where can I find logs?

TARS stores logs under `%APPDATA%\TARS\logs`. See the
[installation guide](tars-installation.md) for other profile paths. Remove
credentials and personal data before sharing any diagnostic file.
