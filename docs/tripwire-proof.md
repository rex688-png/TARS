# Task 1 tripwire proof

Baseline: TARS `f0153840016e33c498eafd5ea197963bcf776987`; TARS-Plugins `685e16a19d5a5cd83f16297b90ee4c58ba8e11b5`. Mutations were applied only to the local working tree, tested, and completely reverted. No broken state was committed or pushed.

## Native schema subtle rename

Mutation: rename the nested `system_finder` parameter `reference_system` to `referenceSystem`. Evidence patch: `tripwire-mutations/native-schema-rename.patch`.

Command:

```text
.venv/bin/pytest -q test/tars_baseline/test_baseline.py::test_tool_schema_snapshot_is_deterministic test/tars_baseline/test_baseline.py::test_native_finder_schema_tripwires
```

RED: `test_tool_schema_snapshot_is_deterministic` failed because `native_host.nested_web_agent_tools` differed from the checked-in schema; 1 failed, 1 passed. This is the required subtle mutation: a valid-looking camelCase rename rather than deletion of the tool.

## Prompt marker removal

Mutation: remove `REVISION` from the authoritative character prompt as it enters the real `PromptGenerator`. Evidence patch: `tripwire-mutations/prompt-marker-removal.patch`.

Command:

```text
.venv/bin/pytest -q test/tars_baseline/test_baseline.py::test_prompt_snapshot_is_deterministic test/tars_baseline/test_baseline.py::test_prompt_fixtures_preserve_high_value_context
```

RED: the normal-ship, active-route, and memory full-text snapshots failed at the system message. The semantic test continued to protect fictional route/memory/Director markers and prompt role/section order; 4 failed, 1 passed (the fourth failure exposed and led to correcting the status-message selector in that test before final validation).

## Callback double execution

Mutation: make the one-argument registration adapter invoke a callback twice. Evidence patch: `tripwire-mutations/callback-double-execution.patch`.

Command:

```text
.venv/bin/pytest -q test/tars_baseline/test_baseline.py::test_callback_adapter_calls_one_argument_callback_once test/tars_baseline/test_baseline.py::test_callback_adapter_does_not_retry_callback_type_error
```

RED: the once-only assertion observed `['MODEL', 'MODEL']` rather than `['MODEL']`; 1 failed, 1 passed. The internal-`TypeError` case was not retried.

## Revert and GREEN

All three changes were reversed with explicit patches. The final focused suite command and outcome were:

```text
.venv/bin/pytest -q test/tars_baseline/test_baseline.py
13 passed
```

The final validation section in the PR records the post-revert determinism and regression commands as well.
