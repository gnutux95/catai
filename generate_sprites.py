#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 CATAI Linux contributors
# SPDX-FileCopyrightText: 2025 wil-pe (MIT-licensed original CATAI HSB tinting logic)
"""Generate tinted sprite PNGs for all cat colors.

Reads the orange cat sprites and applies per-pixel HSB tinting
to produce black, white, grey, brown, and cream variants.
This matches the original macOS CATAI tintSprite() logic exactly.
"""

from pathlib import Path
from PIL import Image
import sys

SPRITE_DIR = Path(__file__).parent / "sprites"

# HSB tinting parameters from the original Swift cat.swift
CAT_TINTS = {
    "black": {"hue_shift": 0,    "sat_mul": 0.1,  "bri_off": -0.45},
    "white": {"hue_shift": 0,    "sat_mul": 0.05, "bri_off":  0.4},
    "grey":  {"hue_shift": 0,    "sat_mul": 0,    "bri_off": -0.05},
    "brown": {"hue_shift": -0.03,"sat_mul": 0.7,  "bri_off": -0.2},
    "cream": {"hue_shift": 0.02, "sat_mul": 0.3,  "bri_off":  0.15},
}


def rgb_to_hsb(r, g, b):
    """RGB [0..1] -> HSB (hue [0..1], saturation [0..1], brightness [0..1])."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    delta = mx - mn
    h = 0.0
    if delta > 0.001:
        if mx == r:
            h = ((g - b) / delta) % 6 / 6
        elif mx == g:
            h = ((b - r) / delta + 2) / 6
        else:
            h = ((r - g) / delta + 4) / 6
        if h < 0:
            h += 1.0
    s = delta / mx if mx > 0.001 else 0.0
    return (h, s, mx)


def hsb_to_rgb(h, s, b):
    """HSB -> RGB [0..1]."""
    c = b * s
    x = c * (1 - abs((h * 6) % 2 - 1))
    m = b - c
    sector = int(h * 6) % 6
    if sector == 0:   r1, g1, b1 = c, x, 0
    elif sector == 1: r1, g1, b1 = x, c, 0
    elif sector == 2: r1, g1, b1 = 0, c, x
    elif sector == 3: r1, g1, b1 = 0, x, c
    elif sector == 4: r1, g1, b1 = x, 0, c
    else:             r1, g1, b1 = c, 0, x
    return (r1 + m, g1 + m, b1 + m)


def tint_sprite(img: Image.Image, tint: dict) -> Image.Image:
    """Apply HSB tinting to a sprite image. Matches original Swift tintSprite()."""
    hs = tint["hue_shift"]
    sm = tint["sat_mul"]
    bo = tint["bri_off"]

    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 3:
                continue

            af = a / 255.0
            # Unpremultiply
            rf = r / (255.0 * af) if af > 0 else 0
            gf = g / (255.0 * af) if af > 0 else 0
            bf = b / (255.0 * af) if af > 0 else 0

            hue, sat, bri = rgb_to_hsb(rf, gf, bf)

            nh = (hue + hs + 1) % 1.0
            ns = max(0, min(1, sat * sm))
            nb = max(0, min(1, bri + bo))

            nr, ng, nbb = hsb_to_rgb(nh, ns, nb)

            # Premultiply and write back
            pixels[x, y] = (
                int(max(0, min(255, nr * af * 255))),
                int(max(0, min(255, ng * af * 255))),
                int(max(0, min(255, nbb * af * 255))),
                a,
            )

    return img


def main():
    orange_dir = SPRITE_DIR / "orange"
    if not orange_dir.exists():
        print(f"Error: Orange sprite directory not found at {orange_dir}")
        sys.exit(1)

    # Collect all relative paths of PNG files under orange/
    orange_pngs = sorted(orange_dir.rglob("frame_*.png")) + \
                  sorted(orange_dir.rglob("rotations/*.png"))

    # Also handle any .png files in rotations directly
    for p in sorted((orange_dir / "rotations").glob("*.png")):
        if p not in orange_pngs:
            orange_pngs.append(p)

    print(f"Found {len(orange_pngs)} orange sprite files")

    for color_name, tint in CAT_TINTS.items():
        color_dir = SPRITE_DIR / color_name
        count = 0

        for orange_path in orange_pngs:
            rel = orange_path.relative_to(orange_dir)
            dest = color_dir / rel

            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Skip if already exists
            if dest.exists():
                continue

            # Load, tint, save
            try:
                img = Image.open(orange_path)
                tinted = tint_sprite(img, tint)
                tinted.save(dest)
                count += 1
            except Exception as e:
                print(f"  Error processing {orange_path} -> {dest}: {e}")

        print(f"  {color_name}: generated {count} sprites")

    print("Done! All cat colors now have proper sprite assets.")


if __name__ == "__main__":
    main()