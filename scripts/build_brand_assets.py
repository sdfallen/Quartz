"""Build the SpeS mark from one geometry: SVG, PNG and multi-size ICO.

Redesigned 27 Nov 2026 (the user did not like the sun-over-horizon mark). SpeS is Latin for
hope; the mark is a hope star at dawn: a rounded tile whose night indigo turns to dawn coral, a
four-pointed star of warm light, a small companion star and the first arc of the horizon.
All geometry lives here so the window icon, packaged PNGs, the Android launcher and the SVG never
drift apart. ``ui/shell.py`` holds the same polygons for the theme-aware in-app mark; tests keep
them identical.
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
# The tile: a rounded square (corner radius 64 of 256), night → dawn.
TILE = (12.0, 12.0, 244.0, 244.0)
TILE_RADIUS = 64.0
GRADIENT = (("#1B1650", 0.0), ("#4B34C9", 0.52), ("#FF7A59", 1.0))
# The hope star and its small companion: concave four-pointed sparkles of warm light.
STAR = ((122.0, 112.0), 76.0, 66.0)        # centre, vertical reach, horizontal reach
COMPANION = ((184.0, 62.0), 24.0, 21.0)
SPARKLE_POWER = 3.1                         # higher = thinner arms
STAR_TONE = "#FFF4E3"
COMPANION_TONE = "#FFD7A8"
# The horizon: a thin arc of dawn across the lower tile.
HORIZON_CENTER, HORIZON_R, HORIZON_W = (128.0, 380.0), 168.0, 11.0
HORIZON_FROM, HORIZON_TO = 62.0, 118.0
TAIL_TONE = "#FFB86B"
STEPS = 64
# Below this size the gradient and the horizon blur into noise: a flat tile and the star only.
SOLID_BELOW = 32
SOLID_TONE = "#3A2BA8"


def _rounded_rect(box, radius, steps=12):
    x0, y0, x1, y1 = box
    corners = ((x1 - radius, y0 + radius, -90), (x1 - radius, y1 - radius, 0),
               (x0 + radius, y1 - radius, 90), (x0 + radius, y0 + radius, 180))
    points = []
    for cx, cy, start in corners:
        for k in range(steps + 1):
            a = math.radians(start + 90 * k / steps)
            points.append((round(cx + radius * math.cos(a), 2), round(cy + radius * math.sin(a), 2)))
    return tuple(points)


def _sparkle(spec):
    (cx, cy), ry, rx = spec
    points = []
    for k in range(STEPS):
        t = 2 * math.pi * k / STEPS
        c, s = math.cos(t), math.sin(t)
        points.append((round(cx + rx * math.copysign(abs(c) ** SPARKLE_POWER, c), 2),
                       round(cy - ry * math.copysign(abs(s) ** SPARKLE_POWER, s), 2)))
    return tuple(points)


def _arc_band():
    (cx, cy), r, w = HORIZON_CENTER, HORIZON_R, HORIZON_W
    outer = [(round(cx + (r + w / 2) * math.cos(math.radians(a)), 2),
              round(cy - (r + w / 2) * math.sin(math.radians(a)), 2))
             for a in [HORIZON_FROM + (HORIZON_TO - HORIZON_FROM) * k / 24 for k in range(25)]]
    inner = [(round(cx + (r - w / 2) * math.cos(math.radians(a)), 2),
              round(cy - (r - w / 2) * math.sin(math.radians(a)), 2))
             for a in [HORIZON_TO - (HORIZON_TO - HORIZON_FROM) * k / 24 for k in range(25)]]
    return tuple(outer + inner)


TAIL = _arc_band()


def facets():
    """Tile, hope star, companion star (the horizon is ``TAIL``)."""
    return [_rounded_rect(TILE, TILE_RADIUS), _sparkle(STAR), _sparkle(COMPANION)]


FACET_TONES = ("url(#spesDawn)", STAR_TONE, COMPANION_TONE)


def _points(polygon):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)


def svg():
    stops = "".join(f'<stop offset="{offset:g}" stop-color="{tone}"/>' for tone, offset in GRADIENT)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" role="img" aria-label="SpeS">',
             f'<defs><linearGradient id="spesDawn" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient></defs>']
    tile, star, companion = facets()
    parts.append(f'<polygon points="{_points(tile)}" fill="url(#spesDawn)"/>')
    parts.append(f'<polygon points="{_points(TAIL)}" fill="{TAIL_TONE}"/>')
    parts.append(f'<polygon points="{_points(star)}" fill="{STAR_TONE}"/>')
    parts.append(f'<polygon points="{_points(companion)}" fill="{COMPANION_TONE}"/>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def _hex(tone):
    return tuple(int(tone[i:i + 2], 16) for i in (1, 3, 5))


def _gradient(canvas):
    """Diagonal night → dawn ramp, computed per diagonal band."""
    image = Image.new("RGB", (canvas, canvas))
    draw = ImageDraw.Draw(image)
    stops = [(_hex(t), o) for t, o in GRADIENT]
    span = 2 * canvas
    for d in range(span):
        f = d / (span - 1)
        for (c0, o0), (c1, o1) in zip(stops, stops[1:]):
            if o0 <= f <= o1:
                u = (f - o0) / (o1 - o0)
                color = tuple(round(a + (b - a) * u) for a, b in zip(c0, c1))
                break
        draw.line([(d, 0), (0, d)], fill=color, width=2)
    return image


def render(size):
    scale = 8
    canvas = size * scale
    factor = canvas / VIEW
    scaled = lambda polygon: [(x * factor, y * factor) for x, y in polygon]
    tile, star, companion = facets()
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(mask).polygon(scaled(tile), fill=255)
    solid = size < SOLID_BELOW
    ground = Image.new("RGB", (canvas, canvas), _hex(SOLID_TONE)) if solid else _gradient(canvas)
    image.paste(ground, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    if not solid:
        draw.polygon(scaled(TAIL), fill=TAIL_TONE)
    draw.polygon(scaled(star), fill=STAR_TONE)
    if not solid:
        draw.polygon(scaled(companion), fill=COMPANION_TONE)
    # Box keeps the flat small frames free of resampling ringing.
    return image.resize((size, size), Image.Resampling.BOX if size < 64 else Image.Resampling.LANCZOS)


def android_vector():
    """The launcher foreground for Android (108dp viewport, mark in the 72dp safe zone)."""
    tile, star, companion = facets()
    path = lambda polygon: "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in polygon) + " Z"
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    xmlns:aapt="http://schemas.android.com/aapt"\n'
            '    android:width="108dp" android:height="108dp"\n'
            '    android:viewportWidth="384" android:viewportHeight="384">\n'
            '  <group android:translateX="64" android:translateY="64">\n'
            f'    <path android:pathData="{path(tile)}">\n'
            '      <aapt:attr name="android:fillColor">\n'
            '        <gradient android:type="linear" android:startX="0" android:startY="0"\n'
            '            android:endX="256" android:endY="256">\n'
            + "".join(f'          <item android:offset="{o:g}" android:color="{t}"/>\n' for t, o in GRADIENT)
            + '        </gradient>\n      </aapt:attr>\n    </path>\n'
            f'    <path android:fillColor="{TAIL_TONE}" android:pathData="{path(TAIL)}"/>\n'
            f'    <path android:fillColor="{STAR_TONE}" android:pathData="{path(star)}"/>\n'
            f'    <path android:fillColor="{COMPANION_TONE}" android:pathData="{path(companion)}"/>\n'
            '  </group>\n</vector>\n')


def build(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "spes-mark.svg").write_text(svg(), encoding="utf-8", newline="\n")
    frames = {size: render(size) for size in ICO_SIZES}
    render(1024).save(target / "spes-mark.png", optimize=True)
    frames[48].save(target / "spes-mark-48.png", optimize=True)
    # Pillow scales one image unless given exact frames; small sizes must stay flat.
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
    parser.add_argument("--android", type=Path, default=None,
                        help="also write the Android launcher foreground vector here")
    args = parser.parse_args()
    print(json.dumps(build(args.target), indent=2))
    if args.android:
        args.android.write_text(android_vector(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
