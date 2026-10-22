# RC20 release blocker: historical prompt isolation

Continue PR #20 from 5f98e8b9bdc81216142d52a433ddf9c4a83f0a1d. No production source, security workflow, saved settings, plugin files or historical snapshot JSON is modified.

## Exact cause and differences

All three affected scenarios (normal_ship, active_route, memory_context) have the same message count and unchanged non-system context. Only message 0's system content differs. The expected text says: "You do not ask questions or initiate conversations. You respond only when addressed and in a single sentence. Don't repeat the same words and sentences, mix it up." Current behavior deliberately permits prioritized enabled events, natural response length and silence for routine events; it adds LIVE_EXPLORATION_SPEECH_POLICY (selective tallies/science, landing uncertainty, immersion, Vista reactions) and presentation policy for compact bodies, numeric display and DSS efficiency. Ship/route/memory content is not lost. This is an epoch-mixing test harness, not evidence of a production prompt regression or nondeterminism.

The harness labeled historical audit metadata with original TARS f0153840016e33c498eafd5ea197963bcf776987 and plugin 685e16a19d5a5cd83f16297b90ee4c58ba8e11b5, but imported lib.PromptGenerator/projections/dependencies from the current host process. That could also inherit already-imported current modules. Git provenance shows all three affected snapshot JSONs were last deliberately updated by product commit 8fa6b62f829e25467d7fc859fd9e0f2916059aca, later than original audit baseline. Public baseline cd460841c57a29ac0cd9fe670379db6551d55193 remains the safe rewritten ancestry marker; original private/old history is not fetched.

## Minimal correction

SNAPSHOT_HOST_REVISION explicitly pins the render-source epoch 8fa6b62f829e25467d7fc859fd9e0f2916059aca. build_baseline now creates temporary detached Git worktrees at that host commit and the existing exact plugin baseline, then invokes the existing builder in an isolated Python subprocess (-I). Thus PromptGenerator and its transitive host imports are pinned together, unaffected by the parent test process's module cache. Worktrees are removed afterward; primary checkouts, release pin and branches remain untouched. The fixture verifies availability of historical Git objects instead of demanding a permanent downgrade of the sibling checkout. No historical evidence JSON or metadata fields are regenerated/relabelled; the distinction between original audit identity and later snapshot render epoch is explicitly recorded here and in the constant comment.

Historical sources must exist locally; the tool raises an explicit error if they do not. The existing optional historical-test fixture reports a conditional, revision-specific skip only when a source checkout/object is genuinely unavailable. It never substitutes current code or an unconditional pass/skip. In this validation all historical source objects were available: zero skipped tests. Historical validation should be provisioned with those source objects in CI if independently required; current release semantics are tested separately.

Three new current-source assertions use real current PromptGenerator, a custom personality marker, synthetic ship identity, route and memory. They require natural response length, preserved context, and verify that current module identity still points to current src after historical execution. Existing productization tests also cover saved custom personality compatibility. No obsolete one-sentence rule is restored.

## Executed validation

1. Re-ran only the three affected historical snapshot cases first: 3 passed in 1.38 seconds.
2. Related prompt/current-context/productization and Phase 1–4 Speech Director regressions: 369 passed, zero failed/skipped in 4.40 seconds. This includes all baseline tests plus current personality/ship/route/memory, speech modes, admission, Chatter, SKIP, TTS, Explorer, journal accuracy and Observatory tests. Five warnings: two existing Python deprecations and three synthetic route-fixture serializer warnings; no product failure.
3. All 27 six-plugin payload files still match pinned source 6f85f5b8dee4f8ea399df4e86d7cb0a5df03bcc2. Plugin repository is unchanged. Saved settings hash is identical; no production prompt or snapshot file changed.

Logs: /workspace/.setup/rc20-blocker-three.log and /workspace/.setup/rc20-blocker-regression.log. No full-suite repeat, dependency upgrades, new PR, branch rewrite or merge into main. This report supersedes the three unresolved-snapshot blocker in docs/tars-rc20-phase5.md without changing the historical integration record.

## CI and readiness

For starting head 5f98e8b9bdc81216142d52a433ddf9c4a83f0a1d, Windows Build Executable and security were successful when inspected; Electron packaging and E2E were in progress. Those results do not certify the new harness-fix head. Final-head Windows executable/MSI/portable packaging, packaged-profile validation, E2E and required security must be checked on the new commit. Exact latest status is in PR #20 and the final session report. If pending, PR #20 stays draft and is not READY TO MERGE. No workflow retry/poll loop or final merge is performed.
