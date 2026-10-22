# TARS brand assets

This directory contains the TARS-specific visual identity that replaces inherited COVAS branding.

## Source of truth

- `vector/tars-mark.svg` — simplified scalable mark for UI and small sizes.
- `vector/tars-wordmark.svg` — font-independent geometric TARS wordmark.
- `vector/tars-logo-horizontal.svg` and `vector/tars-logo-stacked.svg` — scalable production lockups.
- `vector/tars-app-icon.svg` — source for app icons.
- `export_assets.py` — generates PNG and Windows ICO derivatives from the SVG masters.
- `dist/` — generated output; intentionally ignored in Git.

## Rules

1. Do not use the inherited COVAS eagle as TARS branding.
2. Do not distort, recolor arbitrarily or change the proportions of the production marks.
3. Keep the canonical conversational avatar separate from the logo system. Do not crop or repurpose the avatar as the app icon.
4. Prefer dark/charcoal surfaces with restrained TARS orange. Blue is reserved primarily for the robot eyes and small support accents.
5. Do not duplicate the TARS avatar/mark unnecessarily within one screen.
6. Use the same brand shell whether TARS is offline or online.

No runtime wiring is performed by this branding package. App integration should deliberately select the appropriate asset for titlebar, installer, executable, splash and UI contexts.
