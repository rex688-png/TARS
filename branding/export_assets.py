#!/usr/bin/env python3
"""Render production TARS logo/icon derivatives from canonical SVG masters."""
from pathlib import Path
from PIL import Image
import cairosvg

ROOT = Path(__file__).resolve().parent
VECTOR = ROOT / "vector"
DIST = ROOT / "dist"
PNG = DIST / "png"
ICO = DIST / "ico"
PNG.mkdir(parents=True, exist_ok=True)
ICO.mkdir(parents=True, exist_ok=True)


def render(svg_name: str, output_name: str, width: int, height: int | None = None) -> Path:
    out = PNG / output_name
    kwargs = {"output_width": width}
    if height is not None:
        kwargs["output_height"] = height
    cairosvg.svg2png(url=str(VECTOR / svg_name), write_to=str(out), **kwargs)
    return out


render("tars-logo-horizontal.svg", "tars-logo-horizontal-1600.png", 1600)
render("tars-logo-stacked.svg", "tars-logo-stacked-1200.png", 1200)
render("tars-mark.svg", "tars-mark-1024.png", 1024)
render("tars-wordmark.svg", "tars-wordmark-1200.png", 1200)
render("tars-logo-mono-light.svg", "tars-logo-mono-light-1600.png", 1600)
render("tars-logo-mono-dark.svg", "tars-logo-mono-dark-1600.png", 1600)
render("tars-logo-orange.svg", "tars-logo-orange-1600.png", 1600)

icon_sizes = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
for size in icon_sizes:
    render("tars-app-icon.svg", f"tars-icon-{size}.png", size, size)

base = Image.open(PNG / "tars-icon-1024.png").convert("RGBA")
base.save(
    ICO / "tars.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)

print(f"TARS brand exports written to {DIST}")
