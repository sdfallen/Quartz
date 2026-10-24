"""Convert the user-supplied approved Q PNG, never generate replacement art."""
import argparse
from pathlib import Path
import shutil
import hashlib
import json
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[1]
SIZES=(16,32,48,128,256)


def import_assets(source, target, supplied_ico=None):
    source=Path(source).resolve(strict=True)
    target=Path(target)
    with Image.open(source) as original:
        if original.format!="PNG" or original.width!=original.height or original.width<256:
            raise ValueError("Approved original must be a square PNG of at least 256 px; no invented padding/upscale")
        image=original.convert("RGBA")
    png,ico=target/"quartz-q.png",target/"quartz-q.ico"
    if png.exists() or ico.exists(): raise FileExistsError("Preserve existing branding; checkpoint and replace explicitly")
    supplied=Path(supplied_ico).resolve(strict=True) if supplied_ico else None
    if supplied:
        with Image.open(supplied) as check:
            if check.format!="ICO" or not {(size,size) for size in SIZES}.issubset(check.ico.sizes()):
                raise ValueError("Supplied ICO must contain every required size")
            frame=check.ico.getimage((256,256)).convert("RGBA")
            if any(extreme!=(0,0) for extreme in ImageChops.difference(image.resize((256,256),Image.Resampling.LANCZOS),frame).getextrema()):
                raise ValueError("Supplied ICO does not exactly match the approved PNG at 256 px; review explicitly")
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,png)
    if supplied: shutil.copy2(supplied,ico)
    else: image.save(ico,format="ICO",sizes=[(size,size) for size in SIZES])
    with Image.open(ico) as check:
        sizes=sorted(check.ico.sizes())
        if not {(size,size) for size in SIZES}.issubset(sizes): raise RuntimeError("ICO size verification failed")
        # Small, mechanically decoded UI asset; original supplied PNG/ICO remain byte-identical.
        check.ico.getimage((48,48)).save(target/"quartz-q-48.png")
    manifest={"source_png":str(source),"source_ico":str(supplied) if supplied else None,
              "supplied_ico_preserved":bool(supplied),"sizes":sizes,
              "png_sha256":hashlib.sha256(png.read_bytes()).hexdigest(),
              "ico_sha256":hashlib.sha256(ico.read_bytes()).hexdigest()}
    (target/"brand-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("approved_png",type=Path)
    parser.add_argument("--ico",type=Path,help="Reuse the supplied ICO exactly, including additional sizes")
    args=parser.parse_args()
    print(json.dumps(import_assets(args.approved_png,ROOT/"assets/branding",args.ico),indent=2))


if __name__=="__main__": main()
