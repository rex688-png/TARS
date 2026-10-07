# Approved TARS identity direction

The approved direction from the 2026-10-07 design pass is:

- TARS-specific identity replaces the inherited COVAS eagle.
- Primary mark is based on TARS' rectangular robot body, not an eagle/wing motif.
- Gunmetal/steel mechanical surfaces, restrained Elite-style orange instrumentation, blue LED eyes.
- Main app identity should feel like a practical ship AI terminal rather than a generic assistant product.
- Use one deliberate TARS identity element per screen. Avoid duplicate avatars or a large blurred TARS image behind every page.
- The conversational avatar and the logo system are separate assets and should not be repurposed interchangeably.
- Dark/charcoal UI remains the base; orange is an accent, not a full-surface fill.
- The same brand shell should remain visible whether TARS is offline or online.

## Production family

- `vector/tars-mark.svg`: simplified mark for UI/sidebar/titlebar.
- `vector/tars-wordmark.svg`: geometric wordmark without font dependency.
- `vector/tars-logo-horizontal.svg`: primary horizontal lockup.
- `vector/tars-logo-stacked.svg`: vertical lockup.
- `vector/tars-logo-mono-light.svg`: light monochrome lockup.
- `vector/tars-logo-mono-dark.svg`: dark monochrome lockup.
- `vector/tars-logo-orange.svg`: orange accent lockup.
- `vector/tars-app-icon.svg`: app-icon master.

Raster and Windows-icon derivatives are generated from these masters with `export_assets.py`.
