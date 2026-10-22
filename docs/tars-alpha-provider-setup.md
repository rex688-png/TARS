# AI providers and local downloads

TARS separates its six bundled behavior plugins from replaceable model
providers. **Settings → AI & Voice** contains detailed language, agent, vision,
speech and embedding configuration. The factory main/agent/vision selection is
OpenAI `gpt-6-luna`; access requires your own API credentials and account access.
A ChatGPT subscription does not include OpenAI API usage. OpenRouter is available
for LLM configuration, and Mistral is a built-in provider integration.

Use the provider's model name, endpoint and credentials for the selected API.
Custom endpoints must implement the required interface and capabilities; not
every model can perform tools or image analysis. Avoid changing every subsystem
at once. Confirm a direct text conversation before adding speech and vision.
Cloud requests can incur charges. External account/key references:
[OpenAI API keys](https://platform.openai.com/api-keys) and
[OpenRouter](https://openrouter.ai/).

## Optional local packages

The base MSI/portable package does **not** contain these model packages:

| Package | Approved version | Purpose | Approximate download |
| --- | --- | --- | --- |
| Parakeet STT | 0.0.10 | Local speech recognition | 714 MiB |
| Pocket-TTS | 0.0.17-tarsfix | Local speech and reference-voice support | 177 MiB |
| Supertonic TTS | 0.1.5 | Local multilingual speech | 311 MiB |
| Gemma Embedding | 0.0.11 | Local semantic-memory embeddings | 416 MiB |

These are controlled upstream packages, not a general plugin marketplace.
TARS verifies pinned archives/manifests and installs only approved providers.
Pocket-TTS uses the verified upstream 0.0.16 Windows payload with the bundled,
verified TARS fix overlay; its displayed completed version is 0.0.17-tarsfix.
Model/package terms remain those of the upstream providers and dependencies.

## Install and register

1. Open **Settings → Plugins → TARS Provider Setup**.
2. Start each desired download explicitly. Allow disk space for extraction as
   well as the download. Progress distinguishes **Downloading**, **Verifying**
   and **Extracting**.
3. Wait for **Installed — Restart required**, then restart TARS.
4. Select the registered speech, voice or embedding provider in the relevant
   settings. Merely selecting a provider does not download or register it.
5. Test [voice](voice.md) and [memory](personality-memory.md) separately.

Packages are stored under `%APPDATA%\TARS\providers`; provider-specific settings
are retained in the private profile. Do not edit the registry, bypass verification
or copy arbitrary plugin directories as an installation workaround. Personal
reference-voice recordings are not supplied; configure your own permitted file
through the provider's settings and keep it private.

If installation fails, record the stage and sanitized error. Check connectivity
and free disk space; do not replace approved files with unverified downloads.
If a package is installed but unavailable, restart and inspect Diagnostics.
Closing during an active installation requires explicit cancellation confirmation;
allow the installation or cancellation to finish rather than force-killing it.

Local STT/TTS/embedding packages do not make a cloud-selected LLM or vision model
offline. Native provider performance and actual devices still need physical
Windows testing. See [troubleshooting](troubleshooting.md) and
[release acceptance](release-readiness.md).
