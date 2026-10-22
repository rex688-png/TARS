# TARS product profile

The packaged application continues to use the mature COVAS runtime internally,
but `TARS_RUNTIME_PROFILE=1` now establishes a deliberate product boundary.
This is a profile/adaptation layer, not a rewrite of journal ingestion, actions,
audio, models, memory, vision, or plugin interfaces.

## Factory source and secret handling

The factory profile was derived from the active `TARS` character at index 3 of
`rex688-png/TARS-config-reference-` revision
`65d343bd3f5f2386031fcb142dbf69add3902cdc`. Only product settings were
transcribed. API keys, commander identity, personal paths, plugin credentials,
and plugin data were not copied.

The authoritative identity prompt is the prompt from `TARS-Plugins` revision
`67b1a1cab5a67d675372477dbcde061697e80bf5`. The reference prompt and the
immutable bundled prompt are byte-identical (SHA-256
`802f042ac643da3583f0e0595caefb6d5a072746a8c0c0d17f64ec9dc29af4d7`). TARS
uses that bundled prompt for fresh profiles and explicit reset. A saved edit
lives in the active TARS character's `character` field in `config.json`, the
same field read by the runtime. No second editable prompt file is maintained.

## Clean profile

A new `%APPDATA%\TARS` profile contains one active identity named `TARS`, not the
three generic COVAS defaults. Its exact 302-event reaction map is preserved as
85 `on`, 207 `off`, and 10 `hidden` reactions. The regression fixture records
the authoritative `on` and `hidden` sets; every other known event is exactly
`off`.

Factory model selections are:

- main, agent, and vision: OpenAI `gpt-6-luna`;
- speech recognition: approved Parakeet provider;
- voice: approved Pocket-TTS 0.0.17-tarsfix provider;
- semantic memory: approved Gemma Embedding provider;
- voice and speed: `en-US-AvaMultilingualNeural`, `1.2`.
- main/agent tuning: reasoning `none`, temperature `0.3`, agent max tries `7`.

Credentials remain empty. Local providers remain explicit downloads, and their
status is shown as requiring installation until verified provider registration
completes after restart. The existing GPT-6 request behavior remains responsible
for omitting temperature and forwarding the configured reasoning effort.

## Migration and prompt persistence

`tars_profile_version=1` records the one-time product migration. Before that
marker, recognized inherited OpenAI defaults (`gpt-4.1-mini`, `gpt-5.4-nano`,
`gpt-5.4-mini`) move to `gpt-6-luna`; other models/providers remain unchanged.
After migration even a deliberate selection of those older model names is
retained. Old configs have no model-choice provenance, so the listed exact
names are the narrowly defined legacy-default heuristic, not a startup mandate.
Explicit reasoning, temperature, retries, keys, audio and plugin settings are
preserved, even when their values equal old defaults.

The prompt editor offers Save, Reload saved (discard unsaved edits) and Reset
to TARS Default. Successful saves are acknowledged only after atomic config
replacement. Prompt changes apply to the next runtime session. Updates do not
overwrite an edited prompt. Reaction reset uses the exact TARS event map.

## Product UI

The Overview is the TARS setup/status surface for AI credentials, speech,
voice, memory, Elite connection, action keybind readiness, and the fixed TARS
identity. The normal character-creation tab is removed; the underlying
abstraction remains to avoid destabilizing the runtime. Reactions, actions,
provider setup, and useful expert controls remain accessible. Upstream
attribution and licensing remain in the repository and distributable legal
material.

This profile has not passed physical Windows acceptance. Do not label it TARS
Alpha 0.1 until provider restart/native dependency, microphone, speaker, Elite,
MSI, and portable-build checks pass on a real machine.
