# Approved Quartz Q artwork

User supplied the approved artwork on 21 October 2026:
`715d52a3-0f49-49c1-9fe1-b6733ea89145.png` and `download.ico` in the project root.
`quartz-q.png` and `quartz-q.ico` preserve those files byte-for-byte. The ICO
contains 16, 24, 32, 48, 64, 128 and 256 px frames. A 48 px decoded PNG is used
only for the custom titlebar. No new logo was generated.

The import command was:

`python scripts/import_brand_icon.py 715d52a3-0f49-49c1-9fe1-b6733ea89145.png --ico download.ico`

The PyInstaller, native window and Inno configuration select this ICO.
`brand-manifest.json` records hashes. `scripts/verify_branding.py` checks
actual PE icon resource payloads, not just the file extension or HTML appearance.
