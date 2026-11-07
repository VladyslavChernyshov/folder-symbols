#!/usr/bin/env python3
"""Cut the building blocks for tools/make_screenshot.py out of four real Nautilus screenshots.

Inputs (all with the same demo folders, default icon size, one theme per file):
  compact light / compact dark   the narrow window without the sidebar (5 columns)
  large light / large dark       the wide window with the sidebar (6 columns)
Outputs in tools/screenshot_parts/:
  frame-light.png, frame-dark.png     the compact window with the folder grid erased
  labels-light.png, labels-dark.png   the 4 x 6 folder-name labels of the large window, as a sheet

The sidebar of the large windows is not kept, only the folder names. Geometry (pixels, 1x):
window = (25, 25)-(646, 872) in the compact shot; icon centres at x = 99 + 118 c, y = 127 + 124 r.
"""
import argparse, os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = (25, 25, 646, 872)           # compact window rectangle (inclusive)
GRID_TOP, GRID_BOTTOM = 76, 836    # rows of the compact shot that hold the folder grid
CX0_COMPACT, CX0_LARGE, PITCH_X, CY0, PITCH_Y = 99, 369, 118, 127, 124
TILE_W, TILE_TOP, TILE_BOTTOM = 118, 30, 84    # label tile relative to the icon centre
COLS, ROWS = 6, 4


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--compact-light", required=True)
    p.add_argument("--compact-dark", required=True)
    p.add_argument("--large-light", required=True)
    p.add_argument("--large-dark", required=True)
    p.add_argument("--out", default=os.path.join(HERE, "screenshot_parts"))
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for theme, compact, large in (("light", a.compact_light, a.large_light), ("dark", a.compact_dark, a.large_dark)):
        c = Image.open(compact).convert("RGBA")
        bg = c.getpixel((WIN[0] + 40, GRID_TOP + 4))
        c.paste(Image.new("RGBA", (WIN[2] - WIN[0] - 1, GRID_BOTTOM - GRID_TOP), bg), (WIN[0] + 1, GRID_TOP))
        c.save(os.path.join(a.out, f"frame-{theme}.png"), optimize=True)
        big = Image.open(large).convert("RGB")
        sheet = Image.new("RGB", (COLS * TILE_W, ROWS * (TILE_BOTTOM - TILE_TOP)))
        for r in range(ROWS):
            for col in range(COLS):
                cx, cy = CX0_LARGE + PITCH_X * col, CY0 + PITCH_Y * r
                tile = big.crop((cx - TILE_W // 2, cy + TILE_TOP, cx + TILE_W // 2, cy + TILE_BOTTOM))
                sheet.paste(tile, (col * TILE_W, r * (TILE_BOTTOM - TILE_TOP)))
        sheet.save(os.path.join(a.out, f"labels-{theme}.png"), optimize=True)
        print(theme, "frame bg", bg[:3], "->", a.out)


if __name__ == "__main__":
    main()
