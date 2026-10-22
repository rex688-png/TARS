# What TARS does

TARS combines conversation with Elite Dangerous journal events, Status.json and
registered tools. You can speak or type a question, hear a response, ask about
available ship or exploration facts, and request permitted actions. TARS is an
AI copilot, not a replacement for piloting or checking the game itself.

## One companion, several sources of context

The bundled [six plugins](plugins/index.md) contribute exploration targets,
journey progress, service searches, spontaneous commentary, expedition history
and optional Observatory notifications. They share one TARS identity; they are
not six independent voices. Commentary can deliberately remain silent.

[Voice input and output](voice.md), [personality and memory](personality-memory.md)
and [vision](game-awareness.md#vision) are configurable. Cloud models require
credentials and may incur charges. Local STT, TTS and embedding packages are
explicit downloads; they do not make a cloud-selected language model offline.

## Information has limits

Live game facts depend on Elite writing accessible journals and status files.
**Last Known** state while the game is closed is not current telemetry. FSS
completion is not proof of DSS mapping; an estimate is not a recorded sale.
External service searches can fail or be out of date. Model responses can also
be wrong. Check critical navigation and action outcomes in Elite.

Actions depend on model tool support, permissions and sometimes Elite keybinds.
See [actions and approvals](20_actions.md). Unsupported tools or missing keybinds
do not imply that normal conversation is unavailable.

TARS retains substantial COVAS:NEXT infrastructure, including audio, model,
journal, memory, vision and tool systems. The [attribution page](70_credits.md)
separates those upstream foundations from the TARS product. EDCoPilot and
arbitrary plugin folders are not enabled by the TARS product profile.
