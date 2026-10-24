"""
create_icon.py
Creates the Quartz icon files needed for the exe.
Run once: python create_icon.py
"""

from PIL import Image, ImageDraw
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def create_quartz_icon():
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img  = Image.new("RGBA", (size, size),
                         (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx = size // 2
        cy = size // 2

        # Black background circle
        draw.ellipse(
            [1, 1, size-1, size-1],
            fill=(1, 10, 18, 255))

        # Outer ring
        draw.ellipse(
            [1, 1, size-2, size-2],
            outline=(0, 200, 255, 255),
            width=max(1, size//32))

        # Middle ring
        m = size // 5
        draw.ellipse(
            [m, m, size-m, size-m],
            outline=(0, 150, 200, 180),
            width=max(1, size//48))

        # Inner glow
        g = size // 3
        draw.ellipse(
            [g, g, size-g, size-g],
            fill=(0, 100, 150, 100))

        # Center dot
        d = size // 2 - max(2, size//16)
        draw.ellipse(
            [d, d, size-d, size-d],
            fill=(0, 220, 255, 255))

        images.append(img)

    # Save as .ico
    ico_path = os.path.join(BASE_DIR, "quartz.ico")
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"Icon saved: {ico_path}")

    # Save as .png too
    png_path = os.path.join(BASE_DIR, "quartz.png")
    images[-1].save(png_path)
    print(f"PNG saved: {png_path}")

if __name__ == "__main__":
    create_quartz_icon()
    print("Done!")
    input("Press Enter to close...")