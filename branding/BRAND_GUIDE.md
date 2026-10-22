# TARS visual identity

## Brand idea

TARS should read as a practical ship AI: industrial, competent and understated rather than glossy consumer-tech branding. The mark is based on TARS' rectangular body, with gunmetal surfaces, an orange ship-instrumentation accent and blue LED eyes.

## Palette

| Token | Hex | Use |
|---|---|---|
| Deep Space | `#0B0D10` | primary dark background |
| Charcoal | `#15181D` | elevated surfaces |
| Gunmetal | `#3A3F46` | mechanical surfaces / secondary UI |
| Steel | `#A8AFB8` | wordmark / neutral highlights |
| TARS Orange | `#FF8A00` | primary accent, selection, instrumentation |
| Eye Blue | `#62B8FF` | TARS eyes, limited secondary accent |
| Status Green | `#41D66D` | healthy/connected state only |

## Logo hierarchy

### Primary vector lockup
Use `vector/tars-logo-horizontal.svg` for general product, documentation and UI use.

### Simplified mark
Use `vector/tars-mark.svg` for titlebars, sidebar identity and other compact UI placements.

### Wordmark
The vector wordmark is path-based and does not depend on a local font. Keep its proportions unchanged.

### App icon
Use `vector/tars-app-icon.svg` as the master. Generate PNG and ICO derivatives with `export_assets.py`.

## Clear space

Keep at least one eye-height of clear space around the mark. Do not place body text or active controls directly against it.

## Minimum sizes

- simplified mark: 24 px minimum in UI
- wordmark: 60 px wide minimum
- app icon: use the generated size-specific raster/ICO derivative

## Product usage

The TARS app should use one deliberate TARS identity element per major surface. Avoid a large blurred avatar behind every page. The conversational avatar and the brand logo are different assets with different jobs.

The final application shell should remain visually consistent whether TARS is offline or online. Branding should not change between those states; only status and available runtime content should change.
