"""Build the Quartz Q mark from one geometry: SVG, PNG and multi-size ICO.

The mark is a six-sided quartz crystal seen end-on: six flat facets form the
bowl of the Q and one shard forms the tail. All geometry lives here so the
window icon, packaged PNGs and the SVG never drift apart. ``ui/brand.py`` holds
the same facets for the theme-aware in-app mark; a test keeps them identical.
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
CENTER = (122.0, 118.0)
OUTER = 104.0
INNER = 50.0
# Light falls from the upper left: the facets step from pale to deep rose.
FACET_TONES = ("#F4C4B7", "#E8A392", "#CE7E6D", "#A5513F", "#B8654F", "#DB8F7C")
TAIL_TONE = "#E8A392"
TAIL = ((122.0, 122.0), (152.0, 106.0), (236.0, 222.0), (200.0, 240.0))
# Below this size facet tones blur into noise, so the mark becomes one solid tone.
SOLID_BELOW = 32
SOLID_TONE = "#DB8F7C"


def _hexagon(radius):
    return [(CENTER[0] + radius * math.sin(math.radians(60 * i)),
             CENTER[1] - radius * math.cos(math.radians(60 * i))) for i in range(6)]


def facets():
    outer, inner = _hexagon(OUTER), _hexagon(INNER)
    return [(outer[i], outer[(i + 1) % 6], inner[(i + 1) % 6], inner[i]) for i in range(6)]


def _points(polygon):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)


def svg():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" role="img" aria-label="Quartz">']
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
    (target / "quartz-q.svg").write_text(svg(), encoding="utf-8", newline="\n")
    frames = {size: render(size) for size in ICO_SIZES}
    render(1024).save(target / "quartz-q.png", optimize=True)
    frames[48].save(target / "quartz-q-48.png", optimize=True)
    # Pillow scales one image unless given exact frames; small sizes must stay solid.
    frames[256].save(target / "quartz-q.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[frames[s] for s in ICO_SIZES if s != 256])
    digest = lambda name: hashlib.sha256((target / name).read_bytes()).hexdigest()
    manifest = {"source": "scripts/build_brand_assets.py", "sizes": [[s, s] for s in ICO_SIZES],
                "svg_sha256": digest("quartz-q.svg"), "png_sha256": digest("quartz-q.png"),
                "ico_sha256": digest("quartz-q.ico")}
    (target / "brand-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=ROOT / "assets/branding")
    print(json.dumps(build(parser.parse_args().target), indent=2))


if __name__ == "__main__":
    main()
