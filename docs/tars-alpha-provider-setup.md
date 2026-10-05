# TARS Alpha provider setup

TARS keeps behavior plugins and model providers separate. The five behavior
plugins remain immutable installed resources. Mistral remains a built-in cloud
provider, while local providers are installed only from the explicit registry
below. TARS never scans arbitrary provider folders.

## Pinned official providers

| Provider | Official release | Download | Installed | Purpose |
| --- | --- | ---: | ---: | --- |
| Parakeet STT | `v0.0.10` | 714 MiB | 789 MiB | Local multilingual speech recognition |
| Pocket-TTS | `v0.0.16` | 177 MiB | 266 MiB | Local speech and reference-voice support |
| Supertonic TTS | `v0.1.5` | 311 MiB | 357 MiB | Local multilingual speech |
| Gemma Embedding | `v0.0.11` | 416 MiB | 513 MiB | Local semantic-memory embeddings |

These are the official Windows release archives from the corresponding
`COVAS-Labs/plugin-*` repositories. Each URL, source revision, archive length,
manifest GUID/version/entrypoint and SHA-256 digest is pinned in
`src/lib/TarsProviderRegistry.py`.

The provider projects do not currently expose a top-level license for their own
plugin source. TARS therefore does not redistribute those archives. A user starts
each download from **Plugin Settings → TARS Provider Setup**, directly from the
official GitHub release. Downloads use a temporary directory, retry up to three
times, verify the pinned digest, reject unsafe ZIP paths, validate the plugin
manifest, and atomically install below `%APPDATA%\TARS\providers`. Restart TARS
after installation so the approved provider can register.

The official archives already contain their model assets and CPython 3.12 Windows
dependencies. Parakeet includes Sherpa ONNX native DLLs; Pocket-TTS and Supertonic
include ONNX Runtime and audio resampling binaries; Gemma includes ONNX Runtime
and tokenizer dependencies. TARS adds only the verified provider's dependency
and DLL directories at runtime. Custom Pocket-TTS reference recordings are not
included. Keep personal voice files inside the TARS profile and select their path
in the provider settings.

## First physical Windows/Elite test

1. Download and install the Task 4 MSI on a machine that does not rely on COVAS.
2. Launch TARS and confirm `%APPDATA%\TARS` is created.
3. Configure an OpenAI API model; do not enter keys into provider download fields.
4. Open **Plugin Settings → TARS Provider Setup** and install Parakeet STT.
5. Install Pocket-TTS or Supertonic TTS.
6. Install Gemma Embedding.
7. Restart TARS and select the installed STT, TTS and embedding providers.
8. Select the intended microphone and speakers.
9. Press PTT, say a sentence, and verify the transcription.
10. Verify TARS produces a model response and audible speech.
11. Interrupt speech and confirm playback stops cleanly.
12. Launch Elite Dangerous and perform a jump.
13. Confirm the journal and `Status.json` state reach TARS.
14. Ask TARS about the current system/body state.
15. Invoke a Galaxy action and confirm Explorer/Navigator actions are registered.
16. Trigger a screenshot request where vision is configured and confirm that only
    the requested frame is sent.
17. Restart TARS and confirm configuration, provider selection and semantic memory
    persist.

Automated CI validates registration, interfaces, packaging and deterministic test
fixtures. It does not prove physical microphone/speaker operation, live Elite
telemetry, GPU acceleration or a live vision request. Only after this checklist
passes should the build be called TARS Alpha 0.1.
