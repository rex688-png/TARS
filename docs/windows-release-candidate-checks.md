# Windows release-candidate boundaries

This branch is a source and automated-test check before a physical MSI test. It
does not certify audio hardware, live Elite input, or an in-place Windows upgrade.

## Profile and upgrade

Electron sets `userData` to `%APPDATA%\TARS` before launching Chat, and launches
the backend with that directory as its working directory. `config.json`, its
previous-good and manual backups, plugin settings, database, and downloaded
providers remain under this user directory. The MSI replaces application files;
the build configuration does not place user profile files in the package. Loading
an existing profile merges missing defaults without replacing deliberate model,
provider, prompt, audio, permission, or plugin selections. Regression tests load
the saved profile again and check those values. A real MSI upgrade still needs a
before/after comparison on Windows.

The manual backup is a fixed local `config.manual-backup.json` next to the active
profile. It **contains credentials and the saved TARS prompt** because both are
part of configuration. It must not be uploaded publicly. Restore validates the
candidate before replacing the active file. Atomic writes and the previous-good
backup remain in use. Restore is available only while TARS is stopped; the
running backend deliberately rejects it.

The support ZIP has a separate allowlisted format. It contains bounded version,
provider, health and severity metadata; log message text is replaced with
`[redacted]`. It does not contain raw configuration, prompt, conversation,
memory, paths or private exception details. Tests inspect every ZIP member.

## Runtime limits to check on the PC

- Stop Speaking sets the shared TTS abort flag, drains queued lines, and stops
  writing further audio chunks. Provider generation may still be blocked until
  it yields another chunk; speaker interruption latency requires physical test.
- ASK and BLOCK are enforced before the central action method calls game input.
  Approval is one-use and expires after 60 seconds. Live Elite input remains to
  be tested on the PC.
- Explorer and Observatory event replies suppress **exact** repeated sentences
  in the same location within 12 seconds. Paraphrased overlapping findings may
  still produce two callouts; removing those without losing unique facts needs
  real event captures and physical validation. The six bundled plugins are not
  changed by this branch.
- Blank model turns no longer produce `...`. Spaced numeric quantities with an
  explicit unit are displayed with comma grouping and spoken naturally. A model
  can still invent a wrong number; this formatting does not validate source data.
- An action that returns no result is shown as unconfirmed after approval. The
  model policy also instructs TARS to claim success only from a confirming tool
  result. Real tool outcomes and model wording need PC acceptance checks.
