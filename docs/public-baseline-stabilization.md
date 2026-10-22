# Public baseline stabilization

This pass preserves the rewritten public functional baseline and does not
rewrite history, modify main, publish a release or redesign the GUI.

## Baseline and public-main security evidence

The stabilization branch descends from the rewritten public Task 6 commit
`83d6dc0a4ddbfeb95e8aa1870a70f286860822e8`, which includes rewritten Task 5
`4c216a030656429c0ea17357b8b2915bebb4eedc` and Task 4
`181db5777f78435c98463467655d5cf1458d7614`. All three pass Git ancestor checks.
The old Task 5 SHA `a8694a2e1fce23eb5d052fe4ef1dedd64a64ddf4` is not an ancestor.
No old private-history branch was merged or pushed.

Live main was compared at `f5549b9ebdda941b876b1fafa89bfd7706d683a3`.
Its three security fixes (`d40fbb80`, `8a057006`, `f5549b9e`) were explicitly
cherry-picked from the public history. `docs/tars-boundary.md` and
`.github/workflows/gitleaks-audit.yml` match public main exactly. The original
manual full-history audit remains intact; a separate redacted current-tree
scan is added for PRs/main. Hidden GitHub refs remain outside this task.

The larger comparison against main includes the already-written Task 4/5/6
functionality because those branches had not been merged into main. It is not
a new backend rewrite. Task 4 provider loading/integrity/shutdown protections,
Task 5 factory profile/GPT-6 defaults/no-updater boundary, and Task 6 coordinator
and secret-free facade remain covered by their existing tests. Models.py,
Assistant.py, EDJournal.py, StatusParser.py, PluginHelper.py, provider installer
logic and Pocket-TTS overlay bytes are unchanged from the Task 6 baseline.

Historical Task 1 snapshots retain their original provenance labels. The dump
now checks ancestry against the corresponding rewritten public baseline
`cd460841c57a29ac0cd9fe670379db6551d55193`; no snapshot content was regenerated.

## Changes and safeguards

- Six official behavior plugins are bundled at
  `TARS-Plugins@67b1a1cab5a67d675372477dbcde061697e80bf5`. All 27 files match
  those exact Git objects. The original five plugins and canonical prompt are
  unchanged. The external reference checkout was not modified.
- Observatory has only the official vendored implementation; no parallel
  `src/plugins`/built-in bridge is installed. Tests cover missing feed, attach
  at EOF, replacement, realtime/read-all filtering, persistent deduplication,
  fact-preserving prompt, registration and lifecycle shutdown. Its external
  writer and real Observatory still require a local PC test.
- One frontend provider policy serves all TARS dropdowns. Registered approved
  local/Mistral providers remain visible. An existing nonstandard selection is
  retained as an existing setting, not offered to fresh users. Installer
  allowlisting, hashes and manifests remain authoritative in Python.
- Profile migration is one-time and preserves explicit tuning, audio, provider,
  plugin and credential settings. Exact recognized old OpenAI default names
  migrate once; older configs have no provenance distinguishing a deliberate
  choice of that exact name. After the marker, those choices are preserved too.
- Saving an API key no longer resets providers/models/audio. Prompt Save and
  Reset wait for an atomic-write acknowledgement; Reload saved discards only
  unsaved edits. Saved prompts are used on the next session. Atomic replacement
  closes the input handle first for Windows compatibility.
- The original supplied avatar filename/bytes are retained:
  `Obraz ChatGPT 28 wrz 2026, 21_39_52.png`, SHA-256
  `4e0103a45a548ef7e700b1c015b42039250d4aad470c4d5d0826b59be5e29143`.
  CharacterService, General Settings, avatar catalog and overlay fallback now
  reference it. CSS fits the complete image without sprite crops or hover zoom;
  custom legacy sprites still work. One asset copy is required for packaging;
  no rename or image edit was made.
- Status copy distinguishes profile loaded/keybind-file found from actual live
  connectivity. README/setup/security docs describe TARS, optional components
  and upstream credit without claiming physical acceptance.
- CI uses PR builds plus main/tag pushes, concurrency cancellation, verified
  checkout/setup v6 majors and lockfile installs. Artifacts expire after seven
  days. Tagged Windows builds prepare MSI/portable ZIP/checksums in a draft
  release only. No tag or release was created by this pass.

## Validation and limits

The runnable Python suite uses the headless input backend and excludes five
modules requiring unavailable PyAudio/PortAudio or X11. This is explicitly a
subset, not a full-suite pass. The exact normal full command was attempted and
failed collection for `test_EDKeys.py`, `test_STT.py`, `test_TTS.py`,
`test_actions_web.py` and `test_platform_support.py` on those prerequisites.
No tests were weakened or permanently skipped to accommodate this host.

Frontend tests cover coordinator sequencing, facade state/secret exclusion,
provider filtering and prompt-save acknowledgement/failure. Electron tests,
TypeScript compilation and Angular development build pass. Production Angular
build is blocked by Google Fonts HTTP 403 in this cloud environment. The two
deterministic baseline dumps compare byte-for-byte equal. Current-tree Gitleaks
8.30.0 reports no leaks; this does not prove the absence of every possible
secret or sensitive content in historical documentation images.

Windows CI/artifact status and exact final counts belong in the PR report.
Physical microphone/speaker/PTT, Elite/journal/keybinds, local provider native
runtime, Observatory writer/rotation and MSI/portable update acceptance are
**REQUIRES LOCAL PC VALIDATION**. Do not label this Alpha 0.1.

## Deliberately retained legacy areas

| Area | Classification and decision |
| --- | --- |
| Old default anime avatar assets | Confirmed replaced; deleted with references updated. |
| Duplicate built-in Observatory approach | Not imported; official external plugin is the only implementation. |
| Generic character editor/presets | Not in normal TARS navigation; retained until remaining imports/migrations can be retired safely. |
| Custom provider forms, SVG/sprite handling | Required compatibility for existing user settings. |
| COVAS class names, database name, UI build directory | Required compatibility, not user-facing rebranding targets. |
| Linux Flatpak ID/old Tauri-era build comments | Legacy packaging; retain pending Linux runtime verification. |
| Old advanced XTTS docs, backup files and stock screenshots | Probably stale; not automatically deleted without reference/visual verification. |
| Journal, Status, audio, model, memory, vision, native finder/action code | Working backend; deliberately retained. |

Before the full TARS-native GUI redesign, review this PR and complete the
physical Windows acceptance checklist using artifacts from this branch. Keep
the Task 6 coordinator/facade boundary; do not reintroduce lifecycle ownership
in visual components.
