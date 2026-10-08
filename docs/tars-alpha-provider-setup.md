# TARS provider setup

TARS keeps behavior plugins and model providers separate. The six official
plugins remain immutable installed resources. Mistral remains a built-in cloud
provider, while local providers are installed only from the explicit registry
below. TARS never scans arbitrary provider folders.

## Pinned controlled providers

| Provider | Official release | Download | Installed | Purpose |
| --- | --- | ---: | ---: | --- |
| Parakeet STT | `v0.0.10` | 714 MiB | 789 MiB | Local multilingual speech recognition |
| Pocket-TTS | `v0.0.17-tarsfix` | 177 MiB | 266 MiB | Local speech and reference-voice support |
| Supertonic TTS | `v0.1.5` | 311 MiB | 357 MiB | Local multilingual speech |
| Gemma Embedding | `v0.0.11` | 416 MiB | 513 MiB | Local semantic-memory embeddings |

The large Windows payloads come from the corresponding pinned
`COVAS-Labs/plugin-*` releases. Each URL, source revision, archive length,
manifest GUID/version/entrypoint and SHA-256 digest is pinned in
`src/lib/TarsProviderRegistry.py`.

Pocket-TTS is intentionally different: TARS downloads and verifies the official
0.0.16 Windows payload for its model, native dependencies and voice assets, then
applies the small known-good 0.0.17-tarsfix source overlay from
`TARS-config-reference-@65d343bd3f5f2386031fcb142dbf69add3902cdc`.
Every overlay file has its own pinned SHA-256 digest and is bundled with Chat.exe;
the base manifest is validated as 0.0.16 before the overlay and the completed
manifest is validated as 0.0.17 afterward. Existing installs are replaced only
when their manifest and marker exactly match the former allowlisted 0.0.16 build.
The patch lowers generation temperature to 0.3, caps and migrates inference
passes to 30 tokens, corrects punctuation splitting, hard-splits long clauses,
and filters empty tokenizer/decoder chunks.

The provider projects do not currently expose a top-level license for their own
plugin source. TARS therefore does not redistribute those large archives. The
reference-backed Pocket-TTS overlay is included with its upstream third-party
notices retained by the downloaded payload. A user starts
each download from **Settings → Plugins → Provider Setup**, directly from the
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

1. Install a reviewed TARS MSI on a machine that does not rely on COVAS.
2. Launch TARS and confirm `%APPDATA%\TARS` is created.
3. Configure an OpenAI API model; do not enter keys into provider download fields.
4. Open **Settings → Plugins → Provider Setup** and install Parakeet STT.
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

## Physical-build rejection and Task 4 repair

The first Task 4 MSI is rejected for product acceptance. All four archives were
downloaded and verified, but restart loading failed before provider code ran. The
loader derived dotted import names from the installed directory and entrypoint
filenames. Official provider names contain hyphens, so imports such as
`cn-plugin-pocket-tts.cn-plugin-pocket-tts` were not valid package imports; the
external provider root was also outside the bundled behavior-plugin import root.

The repaired loader imports the already allowlisted and marker-verified
entrypoint by absolute file path under a synthetic Python package. This retains
package-relative imports such as `.vendor`, adds only that verified provider and
its `deps` directory to Python's lookup path, and retains Windows native-DLL
directory handles. A subprocess regression now performs verified installation,
process termination/restart, hyphenated entrypoint import, relative import,
provider registration, and provider lookup.

Provider setup now emits explicit `Downloading`, `Verifying`, `Extracting`,
`Installed — Restart required`, and failure states. The UI displays downloaded
MiB, total MiB, percentage, and a determinate progress bar, and disables the
provider's install control until the operation completes or fails. Installations
remain temporary until verification and extraction finish, then become visible
through a single atomic rename. Closing TARS while download, verification, or
extraction is active requires an explicit cancellation confirmation.

The rejected build's update banner came from the inherited frontend call to the
upstream COVAS release API. That call and its upstream release dialog path are
removed from the TARS product. No TARS-specific update source exists yet.

The reported `ACTIONS — 31 missing` state was not 31 absent runtime actions. It
was the preflight summary shortening the existing Elite keybinding diagnostic to
the ambiguous word `missing`. Runtime action permissions still match the native
action registration inventory. The summary now reports `missing keybinds`, and
the detailed binding names remain visible; no warning is hidden and no action is
silently enabled.

This repair still requires a fresh physical Windows acceptance pass. It must not
be called TARS Alpha 0.1 until the restarted providers instantiate against their
real native dependencies and microphone/speaker/Elite tests pass.
