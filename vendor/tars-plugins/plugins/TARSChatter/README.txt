TARS Chatter — Director v0.11.0

INSTALL
1. Stop COVAS:NEXT and close it.
2. Replace only the existing TARSChatter folder inside:
   %APPDATA%\com.covas-next.ui\plugins\
3. Extract this archive so the manifest is located at:
   %APPDATA%\com.covas-next.ui\plugins\TARSChatter\manifest.json
4. Keep TARSGalaxy and TARSExplorer in their own separate plugin folders.
5. Launch COVAS and start the AI. Chatter appears as TARS Chatter — Director.

WHAT IT DOES
- Schedules quiet-time opportunities 180–300 seconds apart by default, with at least
  seven minutes configured between actual remarks and a hard six-minute runtime floor
  for older persisted settings. It can also open low-probability opportunities
  after selected meaningful gameplay events. These never force speech and still obey
  the same global remark gap, silence, priority, anti-repeat, and quality guards.
- Routine journal events do not reset the timer; danger, jumps, Explorer milestone-source
  events, commander speech, and COVAS replies still have priority.
- After an ordinary COVAS response, it waits up to 20 seconds. The configurable
  speech cooldown applies after an actual Chatter line (45 seconds by default).
- Before sending an event to COVAS, Chatter asks its model for a natural remark.
  It can start a small conversation during quiet travel without inventing game
  facts. If the model returns SKIP, Chatter accepts the silence immediately. A rejected
  cliché may try a genuinely different grounded subject, but Chatter no longer searches
  through unrelated topics merely to force a line.
  Approved remarks are delivered as written rather than generated again.
- The output director asks for plain factual responses to routine flight events,
  including approaching a body, glide, supercruise exit, and landing gear.
  A cheesy draft gets one retry, then a short factual fallback for that event.
- Requires every unsolicited remark to use a concrete gameplay or visual anchor observed
  within the last 90 seconds. If no such anchor exists, it stays silent. Current mode,
  confirmed system/body and route context support a fresh anchor but never create a
  generic remark by themselves.
- Recognizes jumps, supercruise exits, glide, touchdown/liftoff, vessel/SRV deployment,
  SCO, fuel scooping, FSS activity, route changes, docking and exobiology activity as
  possible anchors. This does not add triggers or change the existing cadence.
- Keeps broad premise cooldowns for sample spacing, exobiology effort/payout, long-route
  commentary and landing, so paraphrasing the same idea does not make it new.
- Tracks recent TARS lines and joke themes across restarts. It injects continuity
  guidance into the main model prompt and retries a near-duplicate once.
- Uses unique event name TARSChatter; it registers no navigation or database
  actions. Galaxy and Explorer keep ownership of their own actions.

V0.9.3 CHATTER STYLE FIX
- Cosmic-philosophy chatter is now hard-blocked in code, not merely discouraged
  by the character prompt. Lines about the universe/galaxy/stars/void/silence
  whispering, hiding secrets, watching, remembering, telling stories, refusing
  answers, and similar premises are rejected before COVAS can speak them.
- Each spontaneous opportunity is assigned a concrete topic such as copilot
  dynamics, exploration routine, navigation, ship life, exobiology procedure,
  surface operations, human systems, or a fresh visual observation.
- Recent chatter topics are remembered across restarts and moved to the back of
  the selection pool, reducing same-subject runs.
- Up to three screened attempts may use different topics. If all are weak, TARS
  stays silent instead of falling back to a generic or philosophical line.
- Reflective filler openings such as "Sometimes I think..." are rejected for
  spontaneous chatter. Direct philosophical questions from the commander are
  unaffected.

OPTIONAL VISION
Visual remarks are OFF by default. In Chatter settings, turn on Allow occasional
screenshots. In COVAS settings, turn on Vision, select a vision provider and model,
and allow the built-in getVisuals action under Actions permissions. Restart the AI
after changing these COVAS settings. COVAS may charge for vision requests.
If your main API key is an OpenRouter key, selecting OpenAI Vision with a blank
Override Vision API Key sends that OpenRouter key to OpenAI and authentication
fails. To use your existing OpenRouter balance, set Vision Provider to Custom,
then set Vision Endpoint to https://openrouter.ai/api/v1 and Vision Model Name
to openai/gpt-5.4-nano. Leave Override Vision API Key empty to reuse your main
OpenRouter key. Change the endpoint and model AFTER selecting Custom, as COVAS
initializes default values when the provider selection changes. Restart the AI.
Alternatively, keep OpenAI Vision and enter a separate valid OpenAI key in the
Override Vision API Key field; that bills OpenAI separately.
Chatter attempts a screenshot only after a recent noteworthy game event, at most
once per configured interval (15 minutes by default), and only when it is already
eligible to speak. The description must explicitly report a notable visible scene;
ordinary views, unavailable screenshots, denied permissions and errors are ignored.
It never claims to have seen something when getVisuals did not produce a result.

Explicit commander requests such as "getVisual", "getVisuals", "what do you see?",
"look at the screen" and "take a screenshot" call COVAS's registered getVisuals
action directly. These requested screenshots do not require the optional chatter
screenshots toggle and do not use its interval. The answer is the vision model's
description of the captured game image. A plain "getvisual" now asks for one
grounded sentence about the scene and omits routine HUD numbers. Specific
visual questions can still receive detailed answers. If Vision is off, getVisuals is blocked,
the game window cannot be captured, or the model fails, TARS says so plainly.
It cannot answer a visual question from system-map memory without a screenshot.

QUICK CHECK
1. Start the AI, open Chatter settings, and click "Test chatter now (no screenshot)".
   TARS should say "TARS Chatter is online." within a few seconds. This button
   bypasses timer, cooldown and screenshot checks. The log records whether the
   event was dispatched, accepted and given to the prompt generator.
2. If old timer settings are still saved, use 180 and 300 seconds for the delay
   fields. Set "Minimum between companion remarks" to 420 seconds or longer and
   "Silence after Chatter speaks" to 45 seconds. At 0% chance to
   say nothing, random silence is off; a weak candidate still gets skipped.
   Settings saved by older versions remain in effect until you change them.
3. Repeat a similar exobiology sampling sequence. A repetitive draft should be
   rejected once; logs may show "TARS Director rejected repetitive draft".
4. For a direct vision check, leave Elite Dangerous open and visible, then click
   "Test vision now (one screenshot)" under Optional Visual Remarks. The COVAS log
   should show "TARS vision diagnostic: CAPTURE OK; model described: ..." and TARS
   should read the result. If it fails, the log records the specific missing setting
   or capture error. You can also say "getVisual" or "what do you see?"; the log
   should show "TARS vision: explicit request succeeded with getVisuals."
5. To check optional spontaneous visual remarks, enable Allow occasional screenshots,
   then land or scan and wait for a chatter window. No remark is guaranteed;
   screenshots with no noteworthy content are suppressed. The interval can be set
   to 5 minutes while testing.
6. The COVAS log should show "TARS Chatter Director v0.11.0 started." If it does not,
   check the folder nesting and Python error log.

COVAS COMPATIBILITY
System-level output guarding, direct semantic recall and direct getVisuals invocation
still need COVAS services that are not exposed by the documented public PluginHelper
methods. v0.9.7 centralizes those accesses behind a compatibility bridge, prefers
future/public attribute names when available, falls back to the current COVAS private
fields, and disables only the affected feature when a capability disappears.

The Director now identifies the main COVAS model prompt using multiple structural
markers instead of relying on one exact sentence. Unknown model calls fail closed:
they pass through untouched rather than being modified accidentally.

Startup logs include a boolean-only compatibility capability report. No API keys,
endpoints or credential values are logged by that report. Recheck the plugin after
major COVAS updates; the public plugin API still does not expose an LLM output
middleware hook or a supported direct built-in-action invocation method.


v0.9.4 novelty lock: 24-line prompt memory, 40-line similarity guard, 8-topic cooldown, six distinct-subject attempts, broader grounded topic pool, and hard silence when a spontaneous retry is still repetitive.


V0.9.6 VISUAL DIVERSITY PASS
----------------------------
- Replaces the single exact visual fingerprint with session-level visual novelty memory.
- Near-duplicate screenshot observations and repeated visual premises are suppressed.
- Physical cockpit structure may still earn an occasional remark, but cockpit-structure
  commentary is limited to one such visual premise per chat session.
- Generic HUD/interface commentary is no longer a standing spontaneous-chatter topic.
- The vision prompt strongly prefers the outside scene and specific physical subjects.
- HUD graphics, menus, reticles, status colors, indicators and ordinary cockpit layout
  are treated as background rather than spontaneous-commentary subjects.
- UI appearance alone can never justify invented warnings, faults, disabled systems,
  COM failures, module states or damage claims.
- Recent visual observations are supplied to the candidate generator so wording changes
  do not resurrect the same visual joke.


V0.9.7 COVAS COMPATIBILITY HARDENING
------------------------------------
- centralizes COVAS LLM, assistant, event-manager, action-manager, vision-model and config access behind one compatibility bridge
- supports both potential public attribute names and the private names used by current COVAS releases
- replaces single-string main-prompt detection with multiple structural markers and a fail-closed policy
- routes vision and semantic-memory access through the bridge instead of scattering private-field access throughout Chatter
- logs a boolean-only startup capability report for faster diagnosis after COVAS updates
- adds automated compatibility regression tests


V0.9.8 EXPLORER SPEECH PRIORITY
-------------------------------
- ScanOrganic, SAAScanComplete, CodexEntry and FSSAllBodiesFound now trigger the
  normal short activity cooldown for spontaneous Chatter.
- This prevents a timer-driven TARSChatter line from slipping between an
  exploration milestone's journal event and the queued TARSExplorerTarget reply.
- Routine exploration traffic still does not reset Chatter continuously; only
  events likely to produce a meaningful Explorer milestone receive this quiet window.


V0.9.9 ROUTINE EVENT SCOPE
--------------------------
- Routine exobiology classification now examines only the current/latest game-event turn.
- Older Known-only ScanOrganicFarEnough / sample-progress events may remain in COVAS
  context, but they can no longer hijack an unrelated later response into lines such
  as "Sampling distance reached."
- This keeps No react (known) useful for context without turning stale routine events
  into delayed spoken confirmations.


V0.10.0 EVENT-TRIGGERED OPPORTUNITIES
------------------------------------
Selected gameplay events can now create an optional spontaneous Chatter opportunity:
- Disembark: 12% base chance
- Embark: 8%
- Liftoff: 12%
- Touchdown: 10%
- Docked: 18%
- Undocked: 12%

These are opportunities, NOT raw reactions. Chatter waits briefly after the event so
Explorer/Navigator/native COVAS replies can claim the moment first. It then checks:
- minimum gap since the previous Chatter line
- recent assistant/user activity
- Explorer-priority game activity
- whether COVAS is already replying
- the event probability
- deliberate-silence probability
- normal topic novelty, anti-repetition, and candidate-quality screening

Repeated surface-operation cycles can modestly increase the chance, especially when
recent exobiology sampling is present, but the chance is capped at 30%. This is meant
to make repeated landing/repositioning feel context-aware without making TARS speak on
every takeoff or disembark.

The event only supplies a context/topic hint. Spoken lines are still generated and
screened by Chatter; there are no hardcoded event jokes.

Use the "Allow event-triggered chatter opportunities" toggle under Spontaneous Chatter
to disable this path while keeping ordinary timer-driven Chatter enabled.


V0.10.1 SESSION REGRESSION PASS
-------------------------------
A four-hour exploration readout exposed that the Director was still finding a line
too reliably. This pass makes silence a first-class result rather than a failed attempt.

- default timer window raised from 90–150 to 180–300 seconds
- default minimum remark gap raised from 240 to 420 seconds; runtime keeps at least
  six minutes even when an older profile still stores the previous 240-second value
- deliberate-silence default raised from 40% to 50%
- event opportunities reduced and capped at 18% instead of 30%
- SKIP from the candidate model now ends the opportunity immediately
- candidate search is capped at three genuinely different subjects instead of six
- maintenance, economics, risk and human-system remarks require matching recent context
  instead of living permanently in the generic timer topic pool
- recurring "I handle X, you handle Y"/division-of-labour and "earn its/their keep"
  premises are rejected in code and remembered as themes
- Explorer/Navigator priority and visual grounding behavior are unchanged
