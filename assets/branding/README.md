# SpeS mark

Redesigned on 27 November 2026 (the user asked for a new logo and interface with a strong first
impression). SpeS is Latin for *hope*; the mark is a **hope star at dawn**: a rounded tile whose
night indigo turns to dawn coral, a four-pointed star of warm light, a small companion star and
the first arc of the horizon. The earlier marks (Quartz crystal; 13 Nov sun over a horizon) are
retired.

One geometry in `scripts/build_brand_assets.py` produces `spes-mark.svg`, `spes-mark.png`,
`spes-mark-48.png`, `spes-mark.ico`, `brand-manifest.json` and, with `--android`, the Android
launcher foreground:

`python scripts/build_brand_assets.py --android android/app/src/main/res/drawable/ic_launcher_foreground.xml`

Icon frames below 32 px are a flat tile with the star only, so the mark stays legible. The in-app
mark in `ui/shell.py` uses the same polygons and the `#spesDawn` gradient from the icon sprite.
The interface palette "Şafak" (`ui/styles.py`) takes its accent and brand ramp from the mark.
The PyInstaller, native window and Inno configuration select the ICO.
`scripts/verify_branding.py` checks actual PE icon resource payloads, not just the file
extension or HTML appearance.
