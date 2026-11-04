# Quartz Q mark

Redesigned on 4 November 2026 at the user's request: a six-sided quartz crystal
forming a Q. One geometry in `scripts/build_brand_assets.py` produces
`quartz-q.svg`, `quartz-q.png`, `quartz-q-48.png`, `quartz-q.ico` and
`brand-manifest.json`:

`python scripts/build_brand_assets.py`

Icon frames below 32 px use one solid tone so the mark stays legible. The in-app
mark in `ui/shell.py` uses the same polygons and follows the selected accent.
The PyInstaller, native window and Inno configuration select the ICO.
`scripts/verify_branding.py` checks actual PE icon resource payloads, not just
the file extension or HTML appearance.
