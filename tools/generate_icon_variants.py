from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "icons" / "variants"


def rounded_gradient_background(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / (size - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
            255,
        )
        draw.line([(0, y), (size, y)], fill=color)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((36, 36, size - 36, size - 36), radius=230, fill=255)
    image.putalpha(mask)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-220, -260, 700, 500), fill=(255, 255, 255, 72))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28)))
    return image


def draw_aurora_note(size: int) -> Image.Image:
    icon = rounded_gradient_background(size, (45, 109, 255), (108, 63, 225))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    white = (255, 255, 255, 245)
    cyan = (104, 236, 255, 255)
    draw.rounded_rectangle((540, 220, 640, 610), radius=48, fill=white)
    draw.rounded_rectangle((430, 250, 640, 345), radius=45, fill=white)
    draw.ellipse((340, 520, 520, 700), fill=white)
    draw.ellipse((520, 470, 700, 650), fill=white)
    draw.polygon(
        [(585, 605), (505, 705), (550, 705), (550, 790), (620, 790), (620, 705), (665, 705)],
        fill=cyan,
    )
    draw.rounded_rectangle((430, 820, 695, 870), radius=24, fill=(255, 255, 255, 210))

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((290, 790, 740, 910), fill=(0, 0, 0, 78))
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    icon.alpha_composite(layer)
    return icon


def draw_vinyl_drop(size: int) -> Image.Image:
    icon = rounded_gradient_background(size, (26, 176, 145), (29, 102, 204))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    draw.ellipse((230, 230, 790, 790), fill=(19, 33, 66, 240))
    draw.ellipse((300, 300, 720, 720), fill=(33, 60, 118, 240))
    draw.ellipse((450, 450, 570, 570), fill=(240, 248, 255, 232))

    for offset in [0, 28, 56, 84]:
        draw.arc((250 + offset, 250 + offset, 770 - offset, 770 - offset), 25, 335, fill=(255, 255, 255, 70), width=6)

    draw.rounded_rectangle((470, 170, 560, 510), radius=40, fill=(255, 255, 255, 235))
    draw.polygon([(515, 500), (440, 596), (480, 596), (480, 680), (550, 680), (550, 596), (590, 596)], fill=(116, 249, 255, 255))
    draw.rounded_rectangle((388, 715, 640, 762), radius=22, fill=(255, 255, 255, 220))

    icon.alpha_composite(layer)
    return icon


def draw_wave_arrow(size: int) -> Image.Image:
    icon = rounded_gradient_background(size, (245, 122, 74), (229, 52, 125))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    white = (255, 255, 255, 245)
    for idx, width in enumerate([58, 48, 38]):
        y = 290 + idx * 115
        draw.rounded_rectangle((230, y, 620, y + width), radius=30, fill=white)

    draw.rounded_rectangle((650, 190, 750, 640), radius=42, fill=white)
    draw.polygon([(700, 620), (610, 730), (660, 730), (660, 825), (740, 825), (740, 730), (790, 730)], fill=(255, 244, 125, 255))
    draw.rounded_rectangle((500, 855, 845, 905), radius=25, fill=(255, 255, 255, 220))

    icon.alpha_composite(layer)
    return icon


def save_png_ico_icns(image: Image.Image, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    png_path = OUT_DIR / f"{name}.png"
    ico_path = OUT_DIR / f"{name}.ico"
    icns_path = OUT_DIR / f"{name}.icns"
    image.save(png_path)

    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    ico_images = [image.resize((size, size), Image.Resampling.LANCZOS) for size in ico_sizes]
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ico_sizes],
        append_images=ico_images[1:],
    )

    if shutil.which("iconutil") and shutil.which("sips"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset_dir = Path(tmp) / f"{name}.iconset"
            iconset_dir.mkdir(parents=True, exist_ok=True)
            for base in [16, 32, 128, 256, 512]:
                for scale in [1, 2]:
                    size = base * scale
                    target_name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
                    target_path = iconset_dir / target_name
                    subprocess.run(
                        [
                            "sips",
                            "-z",
                            str(size),
                            str(size),
                            str(png_path),
                            "--out",
                            str(target_path),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)


def main() -> int:
    variants = {
        "icon_aurora_note": draw_aurora_note(1024),
        "icon_vinyl_drop": draw_vinyl_drop(1024),
        "icon_wave_arrow": draw_wave_arrow(1024),
    }
    for name, image in variants.items():
        save_png_ico_icns(image, name)
        print(f"Generated variant: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

