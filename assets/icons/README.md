# App Icon Assets

- `app_icon.png`: source raster icon (1024x1024)
- `app_icon.ico`: Windows packaging icon
- `app_icon.icns`: macOS packaging icon

Regenerate PNG/ICO from the drawing script:

```bash
.venv/bin/python tools/generate_app_icon.py
```

Generate additional style variants (PNG/ICO/ICNS):

```bash
.venv/bin/python tools/generate_icon_variants.py
```

Variant outputs are under `assets/icons/variants/`.

To switch one variant as the default build icon:

```bash
cp assets/icons/variants/icon_aurora_note.png assets/icons/app_icon.png
cp assets/icons/variants/icon_aurora_note.ico assets/icons/app_icon.ico
cp assets/icons/variants/icon_aurora_note.icns assets/icons/app_icon.icns
```

Regenerate macOS ICNS from the PNG (macOS only):

```bash
rm -rf assets/icons/app_icon.iconset
mkdir -p assets/icons/app_icon.iconset
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" assets/icons/app_icon.png --out "assets/icons/app_icon.iconset/icon_${size}x${size}.png" >/dev/null
  sips -z "$((size*2))" "$((size*2))" assets/icons/app_icon.png --out "assets/icons/app_icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns assets/icons/app_icon.iconset -o assets/icons/app_icon.icns
rm -rf assets/icons/app_icon.iconset
```

