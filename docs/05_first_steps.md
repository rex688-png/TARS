# First steps

1. Install a reviewed Windows MSI, or extract the **entire** portable ZIP, using
   [installation and upgrading](tars-installation.md). Launch **TARS.exe**.
2. Open **Settings → General**. Review the local-use notice, enter your commander
   name and configure your API credentials. The Setup guide can help an incomplete
   profile. Its readiness summary is not a physical device or live-game test.
3. Review **AI & Voice**. The factory main, agent and vision model is OpenAI
   `gpt-6-luna`; access depends on your API account. A ChatGPT subscription does
   not include API usage. Alternative LLM configuration includes OpenRouter.
4. Under **Plugins → TARS Provider Setup**, explicitly install the selected local
   providers. Wait for **Installed — Restart required**, restart TARS and select
   the registered providers. Follow the [provider guide](tars-alpha-provider-setup.md).
5. Select your input/output devices and listening mode. Try Push-to-Talk and a
   headset first. Start TARS, ask a short question, check the transcript in Chat
   and confirm audible speech. See [voice](voice.md).
6. Start Elite Dangerous. Review journal and status readiness and missing
   keybinds in **Diagnostics**. Saved **Last Known** data is not a live connection.
   See [game-state awareness](game-awareness.md).

## Make TARS your companion

Edit **Settings → Personality → System prompt**, then **Save**. Changes apply
to the next session. **Reload saved** discards unsaved edits; **Reset to TARS
Default** restores the bundled prompt. Review [personality and memory](personality-memory.md)
before resetting or clearing anything.

Keep the factory exploration reactions initially: Explorer already selects useful
callouts. [Chatter](plugins/index.md#chatter) can choose silence, and missing
Observatory is normal if you have not installed its separate writer.

If a stage fails, use [diagnostics](troubleshooting.md) before changing several
settings at once. Back up `%APPDATA%\TARS` privately before upgrading. Physical
Windows/audio/Elite acceptance remains pending for the future beta.
