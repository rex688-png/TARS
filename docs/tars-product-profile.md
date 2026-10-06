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
`685e16a19d5a5cd83f16297b90ee4c58ba8e11b5`. The reference prompt and the
immutable bundled prompt are byte-identical (SHA-256
`802f042ac643da3583f0e0595caefb6d5a072746a8c0c0d17f64ec9dc29af4d7`). TARS
loads that bundled prompt; the product profile does not maintain a competing
copy.

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

Credentials remain empty. Local providers remain explicit downloads, and their
status is shown as requiring installation until verified provider registration
completes after restart. The existing GPT-6 request behavior remains responsible
for omitting temperature and forwarding the configured reasoning effort.

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
