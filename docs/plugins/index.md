# The six official TARS plugins

These behavior plugins are bundled with TARS and contribute to **one companion**.
You do not install six separate assistants. The verified payload is pinned to
`TARS-Plugins@6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2`; its 27 file hashes are
recorded in the bundled provenance manifest. Update them through a reviewed TARS
package, not by copying arbitrary folders into the profile.

## Explorer

Explorer builds system/body context from journals and selects useful exploration
callouts: noteworthy worlds, mapping/biology information and relevant progress.
Ask for a system summary, priority targets, body information or biology progress.
It distinguishes FSS discovery from DSS mapping and sampling milestones; it can
remain silent about an ordinary system. Keep raw scan/biology events known with
reaction off to avoid competing callouts. See [event reactions](../25_reactions.md).

## Chatter

Chatter supplies contextual spontaneous remarks and response-quality checks,
including restrained humor, repetition checks, cooldowns and deliberate silence.
Timer and gameplay opportunities do not guarantee a remark. Under **Settings →
Plugins → TARS Chatter**, adjust spontaneous/event opportunities, delay/pause
controls and silence chance. **Test chatter now (no screenshot)** provides a
focused test; it does not prove normal live-game timing.

Optional visual remarks are off by default and require working vision. See
[vision and screenshot privacy](../game-awareness.md#vision). Keep response-quality
checks enabled initially rather than removing them to force more speech.

## Navigator

Navigator tracks destination, route progress when Elite supplies NavRoute data,
actual jumps, travelled distance and journey milestones. Ask about journey
status or destination. It does not replace Elite's route planner or pilot the
ship. A route not supplied by Elite cannot be assumed complete.

## Galaxy

Galaxy supplements built-in station/service search with fallback and verification
tools, including coordinate-based searches for remote origins and optional
EDSM-synced commander information. Normal searches use the host finder tools
first; live journal state remains authoritative for current commander facts. External searches depend on the relevant online services,
connectivity and any required account configuration. Current live journal facts
and older external records may differ. Treat unavailable data as unavailable,
not proof that a station or service does not exist.

## Expedition

Expedition persists exploration trips across restarts, can reconstruct history
from existing journals, and exposes status, history and explicit expedition
controls. Ask about the current expedition or recent trips. Incomplete journals
can limit reconstruction. Exploration estimates and recorded sale proceeds are
separate facts; neither should be presented as proof of the other.

## Observatory Bridge

The sixth plugin relays live notifications from a separate Observatory-side
writer. The writer is optional and distributed separately. Follow the
[feed setup and diagnostics guide](../elite-observatory-bridge.md). It does not
reimplement Observatory's scientific plugins or turn historical Read All output
into live commentary.

## Providers are separate

Parakeet STT, Pocket-TTS, Supertonic TTS and Gemma Embedding are optional
[provider downloads](../tars-alpha-provider-setup.md), not additional behavior
plugins. The TARS product does not scan arbitrary plugin folders or enable
EDCoPilot. Upstream plugin-development instructions remain repository references,
not supported TARS installation instructions.
