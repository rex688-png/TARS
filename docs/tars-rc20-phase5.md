# RC20 Phase 5 integration audit

Release integration only. No final PR merge is authorized or performed. Both integrating PRs remain drafts and are blocked on validation.

## Complete required ancestry

### TARS

| Branch / PR chain | Verified commit | Included in final development head |
| --- | --- | --- |
| product/tars-native-productization | `8fa6b62f829e25467d7fc859fd9e0f2916059aca` | yes |
| stabilize/tars-windows-rc | `7a447a4c37d5b91808ad9b4fc5b4147e0336f4c9` | yes |
| audit/tars-safe-persistence-phase1 | `d3886b4eff27268b7d8fa489ffebb01fa07fb0b3` | yes |
| feature/speech-lifecycle-tracing | `b4d0bb90dc9facdf5695d37ed0d5d8a605e25fd0` | yes |
| feature/speech-admission-gate | `d61d903e8f780b36d6be650b72cf37aac60d2bd6` | yes |
| feature/chatter-admission-integration | `b3e539444136f5030ad1ab12cde204a857d25589` | yes |
| feature/tts-terminal-outcomes | `f4d68a4e4d23c4d9bb8d17d9757a76f673ab056f` | yes |
| feature/quiet-first-discovery-tallies | `8c3511c1e68fbf048c0fc621ed04c5e8db4e2e07` | yes |
| feature/tars-rc20 | `5c5e7f8342f4df4b87bd10e7ee3e2fe2ca750449` | yes |

Initial behind/ahead main: 3 / 72. No duplicate stable patch IDs among non-merge commits unique to this release branch. No missing required PR-head ancestors.

### TARS-Plugins

| Branch / PR chain | Verified commit | Included in final development head |
| --- | --- | --- |
| main | `67b1a1cab5a67d675372477dbcde061697e80bf5` | yes |
| optimize/unchanged-state-persistence | `8c4223a8764db12f841fe3de3acf6836a63073e2` | yes |
| feature/chatter-host-admission | `fef38e9f11350555d7b06dbcc88d13d52ddcfa8e` | yes |
| feature/explorer-early-departure | `f68fa83b1d2a83d5553623e5860e6feb3b8b64e7` | yes |
| feature/chatter-session-context | `74ea4644c8d5244fa6752e9e47f6a9ada42eb9c5` | yes |
| feature/rc20-data-accuracy | `6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2` | yes |

Initial behind/ahead main: 0 / 6. No duplicate stable patch IDs among non-merge commits unique to this release branch. No missing required PR-head ancestors.

Host graph: product foundation -> #13 -> #14 -> #15 -> #16 -> #17 -> #18 -> #19 -> #20. Plugin graph: main -> #22 -> #23 -> #24 -> #25 -> #26. Each listed PR head is an ancestor of its integrating head; earlier product/runtime/frontend work is retained through the verified product foundation. Ancestor PRs remain open and their branches unchanged.

## Main reconciliation and diff review

Host main was f5549b9ebdda941b876b1fafa89bfd7706d683a3. The three main-only commits are d40fbb80 (sanitize local Windows path in boundary docs), 8a057006 (full-history Gitleaks workflow), f5549b9e (correct Gitleaks installer). Normal non-fast-forward merge into feature/tars-rc20 completed without conflicts. Before this report was added, both the working tree and index were byte-identical to pre-integration HEAD 5c5e7f8342f4df4b87bd10e7ee3e2fe2ca750449: the main-side content had already converged, but its commit ancestry was missing. Both current-tree scanning and the full-history workflow are retained. No security or release configuration was overwritten.

Reviewed all 239 host and 17 plugin changed paths relative to the old main merge bases: product branding/runtime/UI, Windows packaging, providers, tests/synthetic fixtures, documentation and six-plugin payloads align with the development chain. Windows-only cleanup removes the Linux build/Flatpak paths intentionally. No live journal, user profile, credentials, database or local logs are introduced. The tracked test/browser/profile.json and factory fixtures are synthetic product test data. The named PNG is a pre-existing product branding asset. No unrelated files were added by integration.

## Actual validation

- Full backend command: python -m pytest --timeout 10 test -q. Result: 620 passed, 9 setup errors requiring historical TARS-Plugins baseline 685e16a19d5a5cd83f16297b90ee4c58ba8e11b5 rather than the release source. These are pre-existing fixture dependency errors, not a permanent plugin downgrade.
- Only those nine cases were rerun using the existing validation-only pytest plugin /workspace/.setup/pr3_legacy_fixture.py and detached worktree /tmp/tars-pr3-legacy-plugins at that exact historical revision. Result: 6 passed, 3 failed. Remaining failures: normal_ship, active_route and memory_context prompt snapshots in test/tars_baseline/test_baseline.py::test_prompt_snapshot_is_deterministic. No snapshot was overwritten. Combined coverage is 626 passing unique test cases and three unresolved snapshot failures. The integration changed no source before validation, so the mismatches predate this main reconciliation. Whether the expected snapshots or current prompt contract should change remains unreviewed; they block declaring a fully green release.
- Full canonical plugins: python -m unittest discover -s tests -v -> 108 passed.
- Electron: node --test test/electron/*.test.js -> 16 passed.
- Frontend foundation: npm run test:frontend-foundation -> 34 passed.
- Production UI: npm run build:ui -> success, existing CommonJS warnings. No dependency upgrades.
- Gitleaks 8.30.0, official binary verified against the SHA-256 pinned by current-tree-security.yml, scanned an exported tracked source tree with --redact: no leaks found. Historical Git scanning is retained as a separate existing workflow, not claimed as executed locally.
- python tools/verify_tars_bundle.py --source /workspace/TARS-Plugins -> all 27 payload files across six plugins/prompt match 6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2 exactly.
- Full backend includes off/observe/enforce admission, SKIP suppression, TTS terminal lifecycle, Explorer early departure, Chatter opportunities/admission/delivery, source body identity/FSS evidence, independent sale reactions, startup/configuration and plugin loading tests. The release bundle is unchanged by integration.

## Pin, settings and merge plan

Plugin PR #26 can target main because it contains current plugin main 67b1a1cab5a67d675372477dbcde061697e80bf5 and the entire #22–#25 stack. Final source/pin remains 6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2. Use an explicitly approved normal merge commit, never squash/rebase: this keeps the exact pin reachable from plugin main. Merge plugins before host when later approved; no new consolidation PR is needed. Host #20 targets main after reconciliation. Do not close ancestors or delete branches until the final integrations succeed.

Manifest versions: Explorer 1.4.10 (Phase 4 source changes distinguished by exact pin), Chatter 0.11.3. Both use their existing Session entrypoints/GUIDs. Saved config hash remained identical; local SellOrganicData stays on, SellExplorationData and MultiSellExplorationData stay off. No profile, prompts, API credentials or memory were modified/committed.

## Pending release evidence and decision

Windows executable, Electron MSI/portable packaging, clean packaged-install validation, E2E and security must succeed for the final integrated head. Local Linux validation does not substitute for those Windows checks. Their exact latest status is reported in PR #20 and the final session report; do not reuse an earlier head as final build evidence. If still pending, stop rather than waiting/retrying indefinitely.

NOT READY TO MERGE: three pre-existing baseline snapshot failures require explicit contract review, and final-head required CI/build validation must finish successfully. No production code or tests changed during integration. No live-game, microphone/speaker, real provider or human-audibility validation is claimed. Missing journal identity and bounded session-local transaction reaction deduplication limitations from Phase 4 remain. Stop and wait for further instructions; nothing is merged into main.
