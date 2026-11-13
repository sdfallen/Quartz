"""Build the SpeS mark from one geometry: SVG, PNG and multi-size ICO.

The mark is a sun rising over a horizon ("spes" = hope): a smooth half disc,
five short rays that do not touch it, and one horizon bar. All geometry lives
here so the window icon, packaged PNGs and the SVG never drift apart.
``ui/shell.py`` holds the same polygons for the theme-aware in-app mark; a test
keeps them identical.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
VIEW = 256
CENTER = (128.0, 164.0)
SUN = 56.0
RAY_FROM, RAY_TO, RAY_HALF = 72.0, 100.0, 7.0
RAY_ANGLES = (162, 126, 90, 54, 18)
SUN_STEPS = 36
# Sun first, then the rays from left to right: dawn gold to rose.
FACET_TONES = ("#F0AC72", "#F6C98A", "#F2B57B", "#EDA073", "#E68A6E", "#DD756D")
# The horizon is the ground of hope: sage green.
TAIL_TONE = "#8FCFB0"
TAIL = ((20.0, 178.0), (236.0, 178.0), (236.0, 194.0), (20.0, 194.0))
# Below this size the rays blur into noise, so the mark becomes one solid tone.
SOLID_BELOW = 32
SOLID_TONE = "#EDA073"


def _at(radius, angle, shift=0.0):
    """Point at ``radius`` along ``angle`` (degrees, 0 = right, 90 = up), moved sideways by ``shift``."""
    a = math.radians(angle)
    return (round(CENTER[0] + radius * math.cos(a) - shift * math.sin(a), 2),
            round(CENTER[1] - radius * math.sin(a) - shift * math.cos(a), 2))


def facets():
    sun = tuple(_at(SUN, 180 - 180 * k / SUN_STEPS) for k in range(SUN_STEPS + 1))
    rays = [(_at(RAY_FROM, a, -RAY_HALF), _at(RAY_TO, a, -RAY_HALF * .7),
             _at(RAY_TO, a, RAY_HALF * .7), _at(RAY_FROM, a, RAY_HALF)) for a in RAY_ANGLES]
    return [sun, *rays]


def _points(polygon):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)


def svg():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" role="img" aria-label="SpeS">']
    for polygon, tone in zip(facets(), FACET_TONES):
        parts.append(f'<polygon points="{_points(polygon)}" fill="{tone}"/>')
    parts.append(f'<polygon points="{_points(TAIL)}" fill="{TAIL_TONE}"/>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def render(size):
    scale = 8
    canvas = size * scale
    factor = canvas / VIEW
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    solid = size < SOLID_BELOW
    for polygon, tone in zip(facets(), FACET_TONES):
        draw.polygon([(x * factor, y * factor) for x, y in polygon], fill=SOLID_TONE if solid else tone)
    if not solid:
        # Polygon edges leave hairline gaps after downsampling; hide them.
        for polygon, tone in zip(facets(), FACET_TONES):
            points = [(x * factor, y * factor) for x, y in polygon]
            draw.line(points + points[:1], fill=tone, width=max(1, scale // 2))
    draw.polygon([(x * factor, y * factor) for x, y in TAIL], fill=SOLID_TONE if solid else TAIL_TONE)
    # Box keeps the solid small frames free of resampling ringing.
    return image.resize((size, size), Image.Resampling.BOX if size < 64 else Image.Resampling.LANCZOS)


def build(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "spes-mark.svg").write_text(svg(), encoding="utf-8", newline="\n")
    frames = {size: render(size) for size in ICO_SIZES}
    render(1024).save(target / "spes-mark.png", optimize=True)
    frames[48].save(target / "spes-mark-48.png", optimize=True)
    # Pillow scales one image unless given exact frames; small sizes must stay solid.
    frames[256].save(target / "spes-mark.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[frames[s] for s in ICO_SIZES if s != 256])
    digest = lambda name: hashlib.sha256((target / name).read_bytes()).hexdigest()
    manifest = {"source": "scripts/build_brand_assets.py", "sizes": [[s, s] for s in ICO_SIZES],
                "svg_sha256": digest("spes-mark.svg"), "png_sha256": digest("spes-mark.png"),
                "ico_sha256": digest("spes-mark.ico")}
    (target / "brand-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=ROOT / "assets/branding")
    print(json.dumps(build(parser.parse_args().target), indent=2))


if __name__ == "__main__":
    main()
