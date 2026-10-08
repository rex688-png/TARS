# Getting started with TARS

TARS is an Elite Dangerous AI copilot built on COVAS:NEXT. Start with the
[TARS installation guide](tars-installation.md), not an upstream COVAS installer.
Windows is the supported platform; the current build still requires physical
acceptance and is not an accepted Alpha 0.1 release.

1. Install a reviewed TARS MSI or unpack the portable build from this repository.
2. Enter your commander name and API credentials. OpenAI GPT-6 Luna is the
   factory main/agent/vision selection. A ChatGPT subscription does not include
   API usage. OpenRouter LLM configuration is available under Advanced.
3. Select microphone/output devices and set PTT or voice activation. A headset
   helps prevent TARS hearing its own speech.
4. Explicitly install the desired [local providers](tars-alpha-provider-setup.md).
   Wait for **Installed — Restart required**, then restart. A selected but
   unregistered provider is not ready to use.
5. Start TARS, check what it heard in Chat, and verify speech output.
6. With Elite running, check journal access and Actions/keybind readiness.
   Configure missing keybinds in Elite's controls; missing actions do not mean
   all conversation is broken.

[Observatory Bridge](elite-observatory-bridge.md) is optional. Missing Observatory
or its feed file does not prevent TARS from operating. The writer and feed are
separate from Elite Journal and Status.json.

## When something is unavailable

- **API/request error:** check the selected provider, its API key, account
  credits/rate limits and connectivity. Do not paste credentials into an issue.
- **No transcript:** check the selected STT provider is registered, microphone
  permissions/device and PTT binding.
- **No speech:** check the TTS provider, output device and volume.
- **No memory/vision:** check the selected embedding/vision provider and its
  configuration; availability is not implied by merely selecting it.
- **No Elite state:** start Elite, verify the journal directory and Status.json
  access. Keybind-file detection alone is not a live connection indicator.
- **Provider installation active:** let it finish. The shutdown guard protects
  installation; do not force-kill the app.
- **Security software warning:** do not assume a false positive or disable
  protection. Check provenance/checksums and report a sanitized diagnostic.

## Settings, updates and upstream guides

The TARS prompt has Save, Reload saved and Reset to TARS Default controls.
Saved changes apply to the next runtime session. Back up your local profile
privately before an update; it contains credentials and personal data.

TARS does not contact the COVAS updater. Use reviewed TARS builds.
The remaining advanced guides document retained COVAS-derived capabilities;
some upstream-specific instructions are historical and are not TARS product
recommendations. Current TARS installation/provider/profile guides take priority.
See [profile behavior](tars-product-profile.md), [actions](20_actions.md) and
[first steps](05_first_steps.md).

For development and regression work, see the [runtime contracts](runtime-contracts.md)
and [hardening/coverage audit](runtime-hardening-audit.md).

For the latest real-PC fixes, see [Settings/runtime refinement](runtime-refinement.md).
