# RC20 Phase 3 — Make Chatter feel alive

Continue host PR #20 from 59c49efc5f4fd552cc924bb5cdef35a4c92400cb. Canonical plugin branch feature/chatter-session-context is stacked on Phase 2 PR #24. Source/pin: 74ea4644c8d5244fa6752e9e47f6a9ada42eb9c5 (Chatter 0.11.3). Earlier Phase 1/2 behavior and Explorer payload are preserved.

## Silence diagnosis

Visible defaults schedule opportunities every 180–300 seconds; runtime floors are 120/180. Concrete anchors expire after 90 seconds. The successful-remark gap defaults to 420 seconds (floor 360); ordinary assistant responses defer up to 20 seconds, user activity normally 45 seconds, gameplay activity 15 seconds. UI silence defaults to 50%; absent-setting runtime fallback remains 40%. Session scheduling stretches docked opportunities to 900–1500 seconds and long-idle opportunities to 720–1200 seconds. Admission, persistent novelty, quality rejection and model SKIP further reduce speech. No timer, silence preference or cooldown was changed.

A controlled baseline using the original source replayed six five-minute opportunities across 30 minutes, each with a jump 150 seconds earlier and an ordinary Explorer response 40 seconds earlier. With deliberate silence disabled and an idle host, it produced zero model calls and zero dispatches: every fresh anchor had expired. This demonstrates a reproducible starvation path, not a measurement of real gameplay.

## Grounded opportunity and costs

Fresh anchors remain preferred. When absent, use only cumulative journal counts observed during this chat: jumps, completed systems, biology signal events, organic-scan events and touchdowns. Require three jumps, two completed systems, one biology/organic event or two touchdowns; latest progress must be within 900 seconds. Clear these facts on chat start. Organic event totals are explicitly not completed organisms. Exclude stale scene/location/event records; never infer expedition distance, destination or live ship condition.

One unchanged progress snapshot allows one candidate attempt, including quality rejection, SKIP or provider failure. New progress allows another. Fresh event candidates retain their existing maximum three creative attempts. There is no new loop, wrapper or classification request. Host reservation still precedes generation and is revalidated afterward; direct questions retain priority. Persistent danger/overheat/charging/jump raw status prevents optional commentary beyond the short activity cooldown.

The new deterministic 30-minute replay passes in off/observe/enforce: three jumps eventually permit a travel observation, a later organic event permits a distinct field-work observation, and intervening opportunities respect context/cooldown. Each mode makes two underlying candidate calls, dispatches two events and submits two completed fake-TTS outputs; prepared host delivery adds zero model calls. First accepted remarks occur at minutes 15 and 25. Random silence is controlled in this test. This is an opportunity demonstration, not guaranteed frequency. Quiet verified context with SKIP makes one call, then zero calls for the unchanged snapshot; repeated-premise rejection is likewise bounded to one. Empty/historic/expired context makes zero calls. A direct question arriving during generation prevents Chatter dispatch after one call.

## Diagnostics and retained responsibilities

Plugin diagnostic_counts exposes fixed reasons: scheduled, cooldown, assistant/user/game activity, host busy/admission, deliberate silence, missing/used context, session context, quality rejection, model SKIP/unavailability/failure, candidate acceptance and dispatch. PluginHelper forwards only whitelisted codes to the existing optional speech trace. Assistant counts Chatter TTS terminal outcomes and emits chatter_delivery with playback_success unknown. Completed output is not proof of human audibility. Existing lifecycle traces cover other cancellation paths. No prompt, conversation, memory or gameplay facts are added to diagnostics; prior draft/visual-text log messages are redacted.

Host Speech Director retains admission, priorities, cancellation and lifecycle. Chatter retains personality, situational topic selection, novelty and conversational opportunities. Legacy base/Session LLM wrappers remain, including context/style, repetition, routine-flight silence, direct vision, routing certainty, memory-summary bypass and direct-response retry. Their optional-speech checks still overlap host freshness/suppression; migration is deferred. Generic host response retries remain separate from the bounded spontaneous-candidate path.

Visible labels become TARS Chatter and Response Quality; GUID, Session entrypoint and all setting keys remain unchanged. A restart test preserves explicitly saved settings while clearing session evidence.

## Executed validation and limits

- Canonical unittest suite: 104 passed, zero failures/skips (100 existing plus four new).
- First host cycle: 315 passed, four new-test failures: incorrect fake TTS settle keyword (three modes), and stale timestamp in the busy-reservation fixture.
- Second/final focused host cycle: 316 passed, three failures in that busy fixture because PluginEvent has plugin_event_content, not content. Corrected that field afterward; no third run was performed, respecting the two-cycle limit. Final fixture correction is unverified. These failures are test setup errors, not demonstrated product failures; a green final host suite is not claimed.
- Passing coverage includes real Session/helper/host integration, 30-minute opportunities in all modes, missing/stale context, safety, direct priority during generation, repetition, interrupted/dropped/failed/no-audio delivery, saved setting keys and labels, diagnostic privacy, and existing admission/Explorer/presentation/TTS/policy/Observatory regressions. Busy-host rejection coverage added here remains pending revalidation; prior admission regressions passed.
- Full release builds, full host suite and real-device/game validation were not repeated in this bounded phase. No environment blocker prevented implementation. No dependency changes or live OpenAI calls.
- Exact bundle verification covers all 27 payload files across six plugins/prompt against the pinned canonical Git objects. Explorer is unchanged from Phase 2.

Commands: source /workspace/.setup/runtime.sh; python -m unittest discover -s /workspace/TARS-Plugins/tests -v; python -m pytest -q test/lib/test_chatter_alive.py test/lib/test_chatter_admission.py test/lib/test_speech_trace.py test/lib/test_speech_arbiter.py test/lib/test_explorer_departure.py test/lib/test_rc20_presentation.py test/lib/test_speech_text.py test/lib/test_tts_terminal_outcomes.py test/lib/test_speech_policy.py test/lib/test_release_candidate_boundaries.py test/lib/test_TARSObservatoryBridge.py. Local logs: /workspace/.setup/rc20-phase3-*.log.

Next step: rerun the corrected busy-host fixture and focused host suite when a new validation budget is authorized, then assess actual pacing with opt-in fixed-reason diagnostics. Generated factual/style compliance still depends on the model and existing quality checks. Stop after Phase 3; do not merge or proceed to Phase 4/5.
