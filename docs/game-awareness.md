# Game-state awareness and vision

## Journals and status

TARS reads Elite Dangerous journals and Status.json to build ship, system,
route and activity context. In **Settings → General**, check **Journal folder**
and **Elite settings folder** if the defaults do not match your installation.
Start Elite and confirm fresh events before relying on a live reading.

**Last Known** state can remain visible after Elite closes. It is saved context,
not proof of live fuel, cargo, route or ship status. Missing keybinds are a
separate issue: they affect individual [actions](20_actions.md), not journal
access or all conversation.

[Explorer and Navigator](plugins/index.md) use journal facts to provide selective
exploration and journey callouts. Journal coverage can be incomplete; FSS body
discovery, DSS mapping and biological sampling are distinct stages. External
service data and old journal facts should not override newer live facts.

## Vision

A configured vision model can analyze a captured Elite window image through
registered tools. Try a question about what is visible on screen while Elite is
running. The model must support the requested capability, the relevant action
must be permitted, and Windows must make the game window available for capture.
This is not a guarantee that every visual element will be recognized correctly.

**Settings → Plugins → TARS Chatter** also has **Optional Visual Remarks**.
**Allow occasional screenshots** is off by default; **Test vision now (one
screenshot)** is an explicit test. Enabling occasional screenshots permits
Chatter to use visual context without a fresh screenshot question each time.
Do not enable it if you do not want those captures.

Screenshots sent to a cloud vision provider leave your PC. Consider what the game
window contains and the provider's policy before requesting or enabling captures.
There is no claim here of completed live vision acceptance on a physical PC.

## Optional Observatory facts

[Observatory Bridge](elite-observatory-bridge.md) consumes a separate external
writer's live notification feed. It does not replace Elite journals, run
Observatory's scientific analysis or imply that an absent feed is a TARS failure.
