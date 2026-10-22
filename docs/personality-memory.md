# Personality and memory

TARS uses one active companion identity. In **Settings → Personality**, edit the
**System prompt** to adjust tone and preferences. Its factory prompt supplies the
TARS identity and restrained humor; a saved custom prompt is retained across
updates rather than being replaced by the bundled default.

- **Save** persists the edit for the next session.
- **Reload saved** discards unsaved changes in the editor.
- **Reset to TARS Default** replaces the prompt with the bundled TARS prompt.

Back up the private profile before a reset or upgrade. The prompt is in
`%APPDATA%\TARS\config.json`; it can contain personal information. Configuration
backups can also contain API credentials. See [profile storage](tars-installation.md#profile-build-identity-and-startup-checks).

## Conversation and longer-term memory

The runtime keeps recent conversation context and can summarize events and
conversation into longer-term memory. Semantic retrieval depends on a configured,
working embedding provider. The factory local choice, **Gemma Embedding**, must
be [installed separately](tars-alpha-provider-setup.md) and registered after restart.
Memory is fallible context, not a complete or guaranteed record of every fact.

**New session** clears short-term conversation context and the displayed
transcript after backend acknowledgement; persistent long-term memory remains.
**Clear visible chat** clears only the rendered transcript. Neither operation
is a memory/database erase command. The Logbook can browse recorded entries and
search them with a question; empty results can reflect missing records or an
unavailable embedding provider.

Keep the entire `%APPDATA%\TARS` folder private when backing up memory. Do not
attach databases, prompts or full profiles to issues. Selected conversation,
recalled memory and game context may be sent to your configured language model;
local embedding storage does not make a cloud language-model request private or
offline. Check the selected providers' own data policies.
