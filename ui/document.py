"""Assemble the single HTML document that pywebview loads.

``gui.py`` still owns the body markup and the application JavaScript (the
JavaScript syntax check and many tests read them from there). This module owns
the document head, the base theme and the offline asset injection that used to
run at the bottom of ``gui.py``. The output is byte-identical to the former
inline assembly.
"""
import base64
import sys
from pathlib import Path

from ui.styles import BASE_CSS
from ui.theme import MODERN_CSS

# Everything before the stylesheet. The leading newline matches the former
# ``r\"\"\"`` literal in gui.py, which started with a line break.
DOCUMENT_HEAD = (
    "\n"
    "<!DOCTYPE html>\n"
    '<html lang="tr">\n'
    "<head>\n"
    '<meta charset="UTF-8">\n'
    "<title>Quartz</title>\n"
)

WORKSPACE_CSS = "workspace.css"
BRAND_MARK = "branding/quartz-q-48.png"
BRAND_PLACEHOLDER = '<div class="brand">QUARTZ</div>'


def asset_root() -> Path:
    """Source checkout ``assets/`` or the PyInstaller bundle's ``assets/``."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[1]
    return Path(base) / "assets"


def brand_markup(png: bytes) -> str:
    return ('<div class="brand"><img class="brand-icon" alt="Quartz Q" width="28" height="28" '
            'src="data:image/png;base64,' + base64.b64encode(png).decode("ascii") + '">QUARTZ</div>')


def build_document(body: str, assets: Path | None = None) -> str:
    """Return the full document.

    ``body`` is everything from ``</head>`` to ``</html>``, exactly as it sits
    in gui.py. The modern theme (``ui/theme.py``) is appended after
    ``workspace.css`` so it wins the cascade. ``workspace.css`` is required (as before, a missing file raises);
    the brand mark is optional and only replaces the text placeholder when the
    PNG exists.
    """
    assets = asset_root() if assets is None else Path(assets)
    html = DOCUMENT_HEAD + "<style>\n" + BASE_CSS + "</style>" + body
    workspace_css = (assets / WORKSPACE_CSS).read_text(encoding="utf-8")
    html = html.replace("</head>", "<style>" + workspace_css + "</style>"
                        + '<style id="quartz-modern-theme">' + MODERN_CSS + "</style></head>")
    mark = assets / BRAND_MARK
    if mark.is_file():
        html = html.replace(BRAND_PLACEHOLDER, brand_markup(mark.read_bytes()))
    return html
