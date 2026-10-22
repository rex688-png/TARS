# Event reactions and commentary

Open **Settings → Personality → Configure event reactions**. Use **Enable Event
Reactions** and search for an event or category. The event controls expose these
states:

| State | Meaning |
| --- | --- |
| **React** | The event is eligible to trigger a response and can supply context. |
| **No reaction** | Keep the event known as context without requesting a direct reaction. |
| **Hidden** | Exclude that event from the language-model context. |

Eligibility does not guarantee speech. The runtime and plugins also account for
freshness, ongoing replies, duplicate facts, cooldowns and silence decisions.
Hiding information can make answers less informed; prefer **No reaction** when
you want context without commentary.

## Explorer and Chatter

Keep the factory exploration event settings to begin with. Explorer consumes
known scan and biology facts and emits its own selective callouts. Enabling raw
scan/organic reactions as well can create overlapping commentary. FSS completion
does not mean every body has been DSS-mapped.

In **Settings → Plugins → TARS Chatter**, use **Enable spontaneous chatter**,
**Allow event-triggered chatter opportunities**, the delay/pause controls and
**Chance to deliberately say nothing (%)** to tune optional remarks. Intervals
are opportunities, not a promise to speak at a fixed frequency. Repetition checks,
current activity and direct questions also affect timing.

**Reset to Defaults** restores the TARS reaction map. Back up a deliberately
customized profile before resetting. If commentary is unexpected, record the
trigger and timing for [support](60_support.md); do not enable every reaction as
a general remedy for silence.
