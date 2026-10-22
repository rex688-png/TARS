# Voice input and text-to-speech

Speech recognition (STT) turns microphone audio into text. The language model
creates a response; text-to-speech (TTS) renders it using your selected voice and
output device. A transcript proves recognition, not that playback succeeded.

## Configure and test

1. In **Settings → General**, select the speech provider and **Input Device**.
   For an optional local provider, complete [installation and restart](tars-alpha-provider-setup.md)
   first. A selected but unregistered provider is not ready.
2. Choose the listening mode. The current controls include **Push-to-Talk**,
   **Push-to-Mute**, **Voice Detection (Use Headphones)**, and **Toggle Mic On/Off**. Configure the relevant
   key binding before testing; Push-to-Talk helps avoid accidental activation.
3. Select the voice provider, **Output Device** and **Output level**. Provider
   voices and model options depend on the selected provider; legacy Edge/Kokoro
   voice lists are not a universal TARS voice catalog.
4. Start a session and ask a short direct question. Check what TARS heard in
   Chat, then listen for the response. Check Windows microphone permissions,
   device availability, speaker volume and provider errors if either stage fails.

Use a headset if TARS hears its own output. After changing devices, refresh the
available device list and confirm the intended selection. **AI & Voice** exposes
more detailed model/provider controls; custom endpoints must match their API.

## Silence and interruption

While TARS is speaking, **Stop speaking** interrupts its output. A new commander
question takes priority over optional commentary. Plugin cooldowns, repetition
checks and deliberate silence can make a spontaneous opportunity produce no
speech; a quiet Chatter interval is not by itself an audio failure.

If a direct question has a transcript but no response or sound, check
[diagnostics](troubleshooting.md#no-response-or-no-speech). Physical device timing,
echo behavior and interruption still require testing on Windows hardware.
Cloud STT/TTS process audio or text through the selected provider; do not assume
all processing is local merely because a local package is installed.
