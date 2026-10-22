# Actions, approvals and keybinds

TARS can request registered tools as part of a model response. Depending on the
available tools, these include Elite input actions, information searches,
exploration/journey queries and vision requests. A model must support tool use;
ordinary text saying an action happened is not proof it was executed.

## Review permissions

Open **Settings → Diagnostics → Action permissions — Allow / Ask / Block**.
The available action inventory comes from the running backend, rather than a
static list of every tool inherited from COVAS:NEXT.

- **Allow:** an enabled, valid request can execute without a separate approval.
- **Ask:** TARS displays a one-use approval before dispatch; confirm only the
  action you intend. Approvals expire after 60 seconds.
- **Block:** the action is not allowed to execute.

An action disabled in the underlying action settings remains blocked. Without an
explicit policy, Elite chat, weapon firing and cargo jettison require **Ask**;
other allowed actions use **Allow**. Existing intent/recipient checks still apply.
A denied or expired approval does not dispatch input. Check the resulting game
state yourself, especially for consequential actions.

## Missing keybinds

Use **Settings → Diagnostics → Action and keybind diagnostics** to identify
missing bindings. Set the corresponding controls in Elite, then review readiness
again. Check game focus, current ship/on-foot context and permissions if an input
action does nothing. Do not assume missing bindings disable all conversation or
information queries.

TARS Navigator tracks journey context; it is not an autonomous route planner or
autopilot. External searches require connectivity and can return unavailable or
stale information. See [official plugins](plugins/index.md) and
[game awareness](game-awareness.md) for their boundaries.

Physical acceptance must verify actual input and approval timing with Elite
running. No such completed live-game acceptance is implied by this guide.
