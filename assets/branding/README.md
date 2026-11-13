# SpeS mark

Redesigned on 13 November 2026 when Quartz became SpeS (Latin *spes*, hope): a
sun rising over a horizon. A smooth half disc, five short rays that do not touch
it, and one sage horizon bar. The earlier gauge-like segmented version was
rejected because the user asked for a calm desk, not a cockpit.

One geometry in `scripts/build_brand_assets.py` produces `spes-mark.svg`,
`spes-mark.png`, `spes-mark-48.png`, `spes-mark.ico` and `brand-manifest.json`:

`python scripts/build_brand_assets.py`

Icon frames below 32 px use one solid tone so the mark stays legible. The in-app
mark in `ui/shell.py` uses the same polygons; its colours come from the theme
tokens (sun and rays in warm tones, horizon in the selected accent).
The PyInstaller, native window and Inno configuration select the ICO.
`scripts/verify_branding.py` checks actual PE icon resource payloads, not just
the file extension or HTML appearance.
