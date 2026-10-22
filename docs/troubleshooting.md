# Diagnostics and common problems

Start with the failing stage: application launch, provider registration, input
transcription, model response, audio playback, or game data. Change one thing at
a time. A missing optional service is not proof that the whole assistant is down.

## Record the build and reported state

Open **Settings → Diagnostics**. **Run self-check** reads reported health; it
does not physically test devices or execute Elite actions. **Build information**
shows **TARS package** and **Frontend build**. Version 0.0.0 is the current
unreleased placeholder; identify the reviewed source/workflow as well.

**Export diagnostics** creates a limited support bundle with reported health,
versions, keybind counts and log severity/timing information. It excludes raw log
messages, credentials, prompts, memory and conversations. Review attachments
before posting. Manually copied logs under `%APPDATA%\TARS\logs` can contain
private information; they are not equivalent to that limited export.

## TARS will not start

Use a reviewed TARS MSI or a fully extracted portable ZIP and launch **TARS.exe**,
not an inherited `start` script. Keep the backend and resources with the app.
Check that `%APPDATA%\TARS` is accessible, then inspect a sanitized startup error.
A missing local model is addressed by [provider installation](tars-alpha-provider-setup.md),
not by replacing the application with a COVAS package.

For security-software warnings, keep protection enabled. Verify the package's
reviewed source and available checksums and report the detection name. Do not
assume a false positive, bypass quarantine or disable antivirus protection.

## No microphone transcript

Check Windows microphone permissions, **Input Device**, listening mode and the
PTT hotkey. Confirm the selected STT provider was installed and registered after
restart; cloud STT also needs valid account/API configuration. Use a headset to
reduce self-triggering from TARS's output. Follow the [voice test](voice.md).

## No response or no speech

If there is no transcript, investigate STT first. If typed/direct questions also
fail, check the selected language model, endpoint, credentials, account access,
credits/rate limits and connectivity. Do not post keys or complete request payloads.

If text appears but sound does not, check TTS registration, output device,
**Output level**, Windows volume and provider errors. **Stop speaking** deliberately
interrupts output. A completed queue item alone is not proof you heard audio.
Spontaneous Chatter may remain silent by design; test a direct question separately.

## Missing memory or vision

Install/register the selected embedding provider and distinguish missing records
from a failed semantic search. **Clear visible chat** is not a database reset.
For vision, check the selected model, action permission and availability of the
Elite game window. Chatter's occasional screenshots are a separate opt-in.
See [memory](personality-memory.md) and [vision](game-awareness.md#vision).

## Missing or stale Elite information

Start Elite, verify the journal folder and permissions, and check that new events
arrive. **Last Known** is saved state. Missing keybinds affect particular actions;
review **Action and keybind diagnostics** and [permissions](20_actions.md).
A missing [Observatory feed](elite-observatory-bridge.md) is normal without its
separate writer. Read All history is intentionally not relayed as live speech.

## Too much, delayed or repetitive commentary

Retain known exploration events without enabling every raw reaction. Review
[reaction settings](25_reactions.md), Chatter delays/silence and the timing of a
particular trigger. Some opportunities become stale or are deferred while busy.
Do not disable quality checks or delete memory as a general cure.

## Settings or upgrade concerns

Privately back up the whole profile before an update. Diagnostics has
**Configuration backup → Create local backup / Restore local backup**; restore
requires TARS to be stopped and does not replace a full database/provider backup.
Keep MSI and portable copies from running against the same profile simultaneously.
See [installation](tars-installation.md) before changing directories or reinstalling.

For an unresolved problem, follow [TARS support](60_support.md). Physical
Windows/audio/live Elite acceptance remains required; a green self-check is not
that acceptance.
