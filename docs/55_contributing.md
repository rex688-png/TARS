# Contributing to TARS

Use the [TARS repository](https://github.com/rex688-png/TARS) for issues and pull
requests. For substantial work, discuss the problem and proposed scope in a TARS
issue first. No upstream Discord server is designated here as TARS support.

A useful bug report includes the reviewed build/source, Windows version, steps
to reproduce, expected versus actual behavior and sanitized diagnostics. Follow
[reporting guidance](60_support.md). Report security problems privately using the
[security policy](https://github.com/rex688-png/TARS/blob/main/SECURITY.md).

## Documentation and code

Check claims against current TARS code and interface labels. Do not copy an
upstream guide as evidence that TARS enables a feature. Keep historical reports
clearly separate from current user instructions and preserve attribution.

For source setup and focused checks, see [development](development.md). Submit a
small, reviewable PR against main and describe what changed, why, the checks
actually run and any Windows/live-game limitations. Never include credentials,
user profiles, journals, voice recordings or personal memory databases.

The host owns its runtime and packaging. The separate
[TARS-Plugins repository](https://github.com/rex688-png/TARS-Plugins) owns the
canonical behavior-plugin sources; a host change must preserve its documented
pin/provenance unless plugin synchronization is explicitly part of the work.
Do not edit bundled payloads casually or change a user's settings to make tests pass.

TARS is derived from COVAS:NEXT. Follow the [license and attribution](70_credits.md)
when redistributing or adapting inherited work. This page invites contributions
to TARS and does not speak for upstream maintainers.
