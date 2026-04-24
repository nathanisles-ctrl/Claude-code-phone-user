#!/usr/bin/env python3
"""Generate PWA icons for Creative Video Studio.
Run: python generate_icons.py
Requires: Pillow (pip install Pillow)
"""
import math
import os
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(BASE_DIR, "static", "icons")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "static", "screenshots")

# Warm palette
C_TOP    = (240, 167,  85)   # #f0a755  warm gold-orange (top)
C_BOTTOM = (192,  69,  53)   # #c04535  rust red        (bottom)
C_BG     = ( 26,  17,   8)   # #1a1108  dark bark (app background)


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def fill_gradient(draw: ImageDraw.ImageDraw, width: int, height: int,
                  c1: tuple, c2: tuple) -> None:
    """Fill draw area with a top-to-bottom gradient between c1 and c2."""
    for y in range(height):
        t = y / max(height - 1, 1)
        color = (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t), 255)
        draw.line([(0, y), (width - 1, y)], fill=color)


def make_icon(size: int, maskable: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Gradient background ───────────────────────────────────────────────────
    fill_gradient(draw, size, size, C_TOP, C_BOTTOM)

    # ── Rounded-rect mask (regular icons) ─────────────────────────────────────
    if not maskable:
        radius = int(size * 0.22)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=radius, fill=255
        )
        img.putalpha(mask)

    # ── Re-draw on top of alpha ───────────────────────────────────────────────
    draw = ImageDraw.Draw(img)
    cx = size / 2
    cy = size / 2

    # Safe-zone for maskable: keep design within inner 80 % (10 % padding each side)
    safe = size * (0.70 if maskable else 0.78)

    # Subtle inner glow ring
    glow_r = safe * 0.53
    draw.ellipse(
        [cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r],
        fill=(255, 255, 255, 30),
    )

    # ── Film-strip strip at top edge ──────────────────────────────────────────
    strip_h = size * 0.08
    strip_y0 = cy - safe * 0.45
    strip_y1 = strip_y0 + strip_h
    strip_x0 = cx - safe * 0.48
    strip_x1 = cx + safe * 0.48
    draw.rectangle([strip_x0, strip_y0, strip_x1, strip_y1], fill=(255, 255, 255, 60))
    # Perforation holes in strip
    hole_r = strip_h * 0.3
    n_holes = 6
    for i in range(n_holes):
        hx = strip_x0 + (i + 0.5) * ((strip_x1 - strip_x0) / n_holes)
        hy = (strip_y0 + strip_y1) / 2
        draw.ellipse([hx - hole_r, hy - hole_r, hx + hole_r, hy + hole_r],
                     fill=(192, 69, 53, 200))

    # Matching strip at bottom
    strip_y0b = cy + safe * 0.45 - strip_h
    strip_y1b = strip_y0b + strip_h
    draw.rectangle([strip_x0, strip_y0b, strip_x1, strip_y1b], fill=(255, 255, 255, 60))
    for i in range(n_holes):
        hx = strip_x0 + (i + 0.5) * ((strip_x1 - strip_x0) / n_holes)
        hy = (strip_y0b + strip_y1b) / 2
        draw.ellipse([hx - hole_r, hy - hole_r, hx + hole_r, hy + hole_r],
                     fill=(192, 69, 53, 200))

    # ── Play triangle ─────────────────────────────────────────────────────────
    tri_h = safe * 0.42
    tri_w = tri_h * (math.sqrt(3) / 2)
    ox = size * 0.02           # slight optical right-shift
    pts = [
        (cx - tri_w / 2 + ox, cy - tri_h / 2),
        (cx - tri_w / 2 + ox, cy + tri_h / 2),
        (cx + tri_w / 2 + ox, cy),
    ]
    draw.polygon(pts, fill=(255, 255, 255, 255))

    # Shadow behind play button for depth
    shadow_pts = [
        (pts[0][0] + size * 0.015, pts[0][1] + size * 0.015),
        (pts[1][0] + size * 0.015, pts[1][1] + size * 0.015),
        (pts[2][0] + size * 0.015, pts[2][1] + size * 0.015),
    ]
    # Draw shadow before the main triangle (re-draw main triangle on top)
    shadow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_img)
    sdraw.polygon(shadow_pts, fill=(0, 0, 0, 50))
    img = Image.alpha_composite(img, shadow_img)
    # Re-draw play triangle cleanly
    draw = ImageDraw.Draw(img)
    draw.polygon(pts, fill=(255, 255, 255, 255))

    return img


def make_screenshot_placeholder() -> Image.Image:
    """540×720 dark placeholder screenshot for the PWA manifest."""
    w, h = 540, 720
    img = Image.new("RGBA", (w, h), C_BG + (255,))
    draw = ImageDraw.Draw(img)

    # Gradient header bar
    bar_h = 80
    for y in range(bar_h):
        t = y / max(bar_h - 1, 1)
        color = (lerp(C_TOP[0], C_BOTTOM[0], t),
                 lerp(C_TOP[1], C_BOTTOM[1], t),
                 lerp(C_TOP[2], C_BOTTOM[2], t), 255)
        draw.line([(0, y), (w - 1, y)], fill=color)

    # Simulated UI cards
    card_color = (44, 31, 20, 255)
    border_color = (150, 63, 22, 255)
    for i, top in enumerate([110, 210, 310, 420, 530]):
        draw.rounded_rectangle(
            [20, top, w - 20, top + 80],
            radius=12, fill=card_color, outline=border_color, width=1,
        )
        # Fake text lines
        draw.rounded_rectangle([40, top + 18, 220, top + 32], radius=4,
                                fill=(232, 175, 106, 180))
        draw.rounded_rectangle([40, top + 46, 320, top + 56], radius=4,
                                fill=(150, 63, 22, 120))

    # Bottom tab bar
    draw.rectangle([0, h - 60, w, h], fill=(26, 17, 8, 255))
    draw.line([(0, h - 60), (w, h - 60)], fill=(60, 42, 24, 255), width=1)
    for i in range(5):
        tx = 54 + i * 108
        draw.rounded_rectangle([tx - 18, h - 46, tx + 18, h - 22],
                                radius=6, fill=(44, 31, 20, 255))

    return img


def main() -> None:
    os.makedirs(ICONS_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    specs = [
        ("icon-192.png",          192, False),
        ("icon-512.png",          512, False),
        ("icon-maskable-192.png", 192, True),
        ("icon-maskable-512.png", 512, True),
    ]
    for fname, size, maskable in specs:
        path = os.path.join(ICONS_DIR, fname)
        make_icon(size, maskable).save(path, "PNG", optimize=True)
        print(f"  ✓  {fname}  ({size}×{size}, maskable={maskable})")

    ss_path = os.path.join(SCREENSHOTS_DIR, "screenshot1.png")
    make_screenshot_placeholder().save(ss_path, "PNG", optimize=True)
    print(f"  ✓  screenshot1.png  (540×720)")

    print("\nAll icons generated in static/icons/")


if __name__ == "__main__":
    main()
