from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "icons"


def build_icon() -> Image.Image:
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    background = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    background_draw = ImageDraw.Draw(background)
    for y in range(size):
        t = y / (size - 1)
        r = int(44 + (116 - 44) * t)
        g = int(98 + (77 - 98) * t)
        b = int(255 + (180 - 255) * t)
        background_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((36, 36, size - 36, size - 36), radius=230, fill=255)

    image.alpha_composite(background)
    image.putalpha(mask)

    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    highlight_draw.ellipse((-160, -220, 680, 520), fill=(255, 255, 255, 70))
    image.alpha_composite(highlight.filter(ImageFilter.GaussianBlur(30)))

    note = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    note_draw = ImageDraw.Draw(note)
    white = (255, 255, 255, 245)
    note_draw.rounded_rectangle((540, 220, 640, 610), radius=48, fill=white)
    note_draw.rounded_rectangle((430, 250, 640, 345), radius=45, fill=white)
    note_draw.ellipse((340, 520, 520, 700), fill=white)
    note_draw.ellipse((520, 470, 700, 650), fill=white)

    cyan = (105, 236, 255, 255)
    note_draw.polygon(
        [(585, 605), (505, 705), (550, 705), (550, 790), (620, 790), (620, 705), (665, 705)],
        fill=cyan,
    )
    note_draw.rounded_rectangle((430, 820, 695, 870), radius=24, fill=(255, 255, 255, 210))

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((290, 790, 740, 910), fill=(0, 0, 0, 80))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))

    image.alpha_composite(note)
    return image


def write_png_and_ico(source: Image.Image) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    png_path = OUT_DIR / "app_icon.png"
    source.save(png_path)

    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    ico_images = [source.resize((size, size), Image.Resampling.LANCZOS) for size in ico_sizes]
    ico_path = OUT_DIR / "app_icon.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ico_sizes],
        append_images=ico_images[1:],
    )


def main() -> int:
    icon = build_icon()
    write_png_and_ico(icon)
    print(f"Generated icon assets in: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

