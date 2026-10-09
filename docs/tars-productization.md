# TARS native product controls

The Windows shell keeps Settings available while the assistant is stopped or running. General presents readiness and configuration cards. Detailed preflight, device, overlay, VR, and profile controls remain behind **Advanced device, overlay and profile controls**. AI & Voice uses subsystem cards with expandable controls; Personality, Plugins, and Diagnostics retain their existing functions. The browser regression test clicks all five tabs in both states and verifies the displayed panel.

## First run

`needsSetup` opens the Setup guide for a genuinely incomplete profile. An existing profile with a commander, selected AI provider, and required credential or local provider keeps its normal Settings view. Progress and completion are stored in `config.json` as `tars_setup_step` and `tars_setup_complete`; optional audio and Elite steps may be skipped. The summary reflects reported state and is not a microphone, speaker, or live Elite test. Configuration fields still use the existing provider selectors. Provider packages remain separate explicit installations.

## Actions and conversation

`action_permissions` is stored beside the existing `allowed_actions` map. The registered action permission key is the enforcement point. A disabled action stays blocked. Without an explicit policy, Elite chat, weapon firing, and cargo jettison require **ASK**; other allowed actions use **ALLOW**. ASK creates a random, one-use 60-second approval, shown by the persistent shell, and does not dispatch input until confirmed. A denied, expired, or blocked request never reaches the action method. Existing intent and recipient checks remain in force for chat. Approval of a tool result does not retroactively change the earlier AI reply; confirmation is reported separately. Verify human-facing timing and wording on Windows with live Elite.

**New session** clears short-term conversation events and the current UI transcript after backend acknowledgement. It preserves persistent long-term memory. **Clear visible chat** only clears the local rendered transcript and does not alter backend context or persistent memory. Neither is a database erase operation. The speaking state offers **Stop speaking** through the existing TTS abort method. Physical device interruption still requires Windows testing.

## Diagnostics and profile safety

**Export diagnostics** creates a zip with build and config/profile versions, approved provider package names and versions, bundled behavior plugin names and versions, reported health, keybind count, self-check, log severity counts, and a timeline of log timestamps and levels. Every log message is redacted. The backend accepts only allowlisted fields and does not read or export configuration values, credentials, prompts, memory, conversation, game identifiers, or Observatory feed contents. A provider version in this bundle describes the approved package version, not an installation integrity check.

Config writes serialize and validate a complete profile, write a flushed temporary file, then atomically replace `config.json`. The preceding valid file is retained as `config.backup.json`. If the main file is corrupt and the backup is valid, startup moves the corrupt file to `config.corrupt.json` and restores the backup. A manual local `config.manual-backup.json` can be created in Diagnostics and restored only while the assistant is stopped. These local backup and corrupt files **do contain credentials**; keep them private. The older JSON export/import also includes private settings by design and is distinct from the redacted support bundle. Current profile migrations and provider-specific settings remain in the existing config layer.

Facts supplied to the model now carry a source and `LIVE`, `CURRENT SNAPSHOT`, or `LAST KNOWN` freshness label. LIVE requires a recent nonhistoric journal event. Cached projection values alone are not treated as live. The model sees one preferred value per fact, keeping prior events and memories subordinate to the current snapshot. The label is informational; it does not change the Elite state parser.

## Windows validation still needed

Test first-run flow on a genuinely clean `%APPDATA%\TARS`, MSI upgrade of an existing profile, manual backup restoration, local device selection, Stop Speaking on PocketTTS and other installed providers, real Elite action approval with keyboard focus, and the support zip contents from a physical installation. The cloud browser and Python tests use simulated transport and disposable profiles; they do not prove those physical paths.
