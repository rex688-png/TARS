# App integration map

Use these assets when the TARS-native shell is implemented. This branch deliberately does not change the current runtime UI yet.

| Surface | Preferred asset | Notes |
|---|---|---|
| Windows EXE / MSI icon | generated `dist/ico/tars.ico` | Generate with `python branding/export_assets.py`, then wire through Electron Builder build resources. |
| Electron/titlebar mark | `vector/tars-mark.svg` | Compact identity mark; do not use the inherited COVAS eagle. |
| App sidebar/header | `vector/tars-mark.svg` or `vector/tars-logo-horizontal.svg` | Use one identity element per screen; avoid duplicate TARS portraits. |
| Splash / installer artwork | `vector/tars-logo-horizontal.svg` or `vector/tars-logo-stacked.svg` | Prefer the full lockup where space allows. |
| README / docs | `vector/tars-logo-horizontal.svg` | SVG is the canonical scalable source. |
| Favicon / tray | generated 16/24/32/48 px PNG or ICO entries | Generated from `vector/tars-app-icon.svg`. |
| Light-background documents | `vector/tars-logo-mono-dark.svg` | Keep adequate clear space. |
| Dark-background documents | `vector/tars-logo-mono-light.svg` or primary horizontal lockup | Use orange sparingly as the instrumentation accent. |

## Avatar boundary

The existing canonical conversational TARS avatar remains a separate asset. Do not crop it, resize its source bytes, convert it into a sprite, or substitute it for the app logo. The logo family and conversational avatar serve different purposes.

## UI direction

The TARS-native shell should remain the same whether the AI is offline or online. Chat is the primary cockpit surface; Exploration and Storage are the main optional visual data surfaces, while Settings/Diagnostics are secondary. Search results should stay inline in Chat rather than navigating away automatically.
