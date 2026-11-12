#!/usr/bin/env python3
"""Draw a fake Nautilus screenshot for the README: one narrow window (no sidebar) with six columns of
folders, the left half in the light theme and the right half in the dark theme. The 24 folders carry
the symbols named in the labels; each of the 12 Yaru accent colours appears once on the light side
(light variants) and once on the dark side (dark variants).

The window frame and the folder names come from real screenshots (tools/screenshot_parts/, made by
prepare_screenshot_parts.py); the icons are our own SVGs rendered at 64 px, which matches what
Nautilus draws to within rounding.

The window sits on a diagonal gradient in the colours of Ubuntu's wallpaper (orange bottom left,
aubergine top right); --background transparent keeps the bare window with its shadow instead.

Usage: make_screenshot.py [--symbols-dir /usr/share/icons/Yaru/scalable] [--out docs/screenshot.png]
                          [--background gradient|transparent] [--margin 40] [--grid 6x4] [--size WxH]

GitHub's social preview is a wider picture on a 1280x640 canvas, eight columns by three rows:
  make_screenshot.py --grid 8x3 --size 1280x640 --out docs/social-preview.png
"""
import argparse, os, sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot_parts")
NAMES = ["applications-development", "applications-games", "applications-graphics", "applications-internet",
         "applications-multimedia", "applications-office", "applications-system", "applications-utilities",
         "audio-x-generic", "camera-photo", "camera-web", "community", "computer", "drive-harddisk",
         "emblem-favorite", "emblem-important", "input-gaming", "input-keyboard", "input-mouse",
         "library-music", "mail-unread", "network-wireless", "preferences-system", "printer"]
ACCENTS = ["Yaru", "Yaru-blue", "Yaru-purple", "Yaru-red", "Yaru-viridian", "Yaru-magenta",
           "Yaru-prussiangreen", "Yaru-olive", "Yaru-sage", "Yaru-bark", "Yaru-wartybrown", "Yaru-yellow"]
LABEL_COLS = 6                       # columns of the labels sheet (24 labels, 6 x 4, in NAMES order)
GRIDS = ("6x4", "8x3")               # 24 folders: an even number of columns, half light, half dark
# the path bar of the real screenshot reads "yaru-icons-demo"; its "icons" is cut out and used as the
# whole folder name (x ranges and rows are in the compact frame, 1x)
TITLE_ROWS, TITLE_TEXT = (36, 62), (293, 408)
TITLE_ICONS = (329, 363)
# Ubuntu wallpaper colours along the diagonal from bottom left to top right (measured from the desktop)
GRADIENT = [(0.0, (225, 95, 44)), (0.5, (148, 58, 69)), (1.0, (97, 33, 77))]
# geometry of the compact screenshot (see prepare_screenshot_parts.py)
GRID_TOP, GRID_BOTTOM, WIDEN_AT, CX0, PITCH_X, CY0, PITCH_Y = 76, 836, 480, 99, 118, 127, 124
TILE_W, TILE_TOP, TILE_BOTTOM, ICON = 118, 30, 84, 64


def load_script():
    """The folder_symbols modules this tool needs, as one namespace."""
    sys.path.insert(0, ROOT)
    from folder_symbols import engine, svg, symbols
    return argparse.Namespace(find_symbols=symbols.find_symbols, load_overrides=symbols.load_overrides,
                              make_svg=svg.make_svg, rasterise=engine.rasterise)


def retitle(im):
    """Replace the demo folder's name in the path bar by 'icons' (same font, cut from the same word)."""
    y0, y1 = TITLE_ROWS
    x0, x1 = TITLE_TEXT
    cut = im[y0:y1, TITLE_ICONS[0]:TITLE_ICONS[1]].copy()
    im[y0:y1, x0:x1] = im[y0:y1, x1 + 2:x1 + 3]                     # pill background
    im[y0:y1, x0:x0 + cut.shape[1]] = cut
    return im


def frame(theme, cols, rows):
    """Compact window, grid area resized to ROWS rows and widened by one column pitch per extra column."""
    im = np.array(Image.open(os.path.join(PARTS, f"frame-{theme}.png")).convert("RGBA"))
    im = retitle(im)
    new_body = GRID_BOTTOM - GRID_TOP - (6 - rows) * PITCH_Y             # six rows -> `rows` rows
    body = np.repeat(im[GRID_TOP + 4:GRID_TOP + 5], new_body, axis=0)
    im = np.concatenate([im[:GRID_TOP], body, im[GRID_BOTTOM:]], axis=0)
    extra = (cols - 5) * PITCH_X
    return np.concatenate([im[:, :WIDEN_AT], np.repeat(im[:, WIDEN_AT:WIDEN_AT + 1], extra, axis=1),
                           im[:, WIDEN_AT:]], axis=1)


def over(dst, src, x, y):
    """Alpha-composite float RGBA src onto uint8 RGBA dst at (x, y)."""
    h, w = src.shape[:2]
    reg = dst[y:y + h, x:x + w].astype(float)
    a = src[:, :, 3:4] / 255
    reg[:, :, :3] = src[:, :, :3] * a + reg[:, :, :3] * (1 - a)
    dst[y:y + h, x:x + w] = np.clip(reg + 0.5, 0, 255).astype(np.uint8)


def gradient(w, h):
    """Diagonal gradient, bottom left -> top right, as an (h, w, 3) float array."""
    t = (np.arange(w)[None, :] / max(w - 1, 1) + 1 - np.arange(h)[:, None] / max(h - 1, 1)) / 2
    pos = [p for p, _ in GRADIENT]
    out = np.stack([np.interp(t, pos, [c[i] for _, c in GRADIENT]) for i in range(3)], axis=2)
    return out + np.random.default_rng(0).uniform(-0.5, 0.5, (h, w, 1))      # dither: no banding


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols-dir", default="/usr/share/icons/Yaru/scalable")
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "screenshot.png"))
    p.add_argument("--background", choices=("gradient", "transparent"), default="gradient",
                   help="gradient: Ubuntu-wallpaper colours behind the window (default); transparent: none")
    p.add_argument("--margin", type=int, default=40,
                   help="extra space around the window (it already has a shadow margin), px. Default: 40")
    p.add_argument("--grid", choices=GRIDS, default="6x4", help="columns x rows of folders. Default: 6x4")
    p.add_argument("--size", metavar="WxH",
                   help="exact canvas size, e.g. 1280x640 (GitHub social preview); the window is centred on the "
                        "gradient and cropped if it does not fit. Overrides --margin; needs --background gradient")
    a = p.parse_args()
    size = None
    if a.size:
        try:
            size = tuple(int(v) for v in a.size.lower().split("x"))
            assert len(size) == 2 and min(size) > 0
        except (ValueError, AssertionError):
            sys.exit(f"--size must look like 1280x640, got {a.size!r}")
        if a.background != "gradient":
            sys.exit("--size needs --background gradient")
    cols, rows = (int(v) for v in a.grid.split("x"))
    y = load_script()
    found = y.find_symbols(a.symbols_dir, None)
    missing = [n for n in NAMES if n not in found]
    if missing:
        sys.exit(f"symbols not found in {a.symbols_dir}: {', '.join(missing)}")
    ov = y.load_overrides()
    light, dark = frame("light", cols, rows), frame("dark", cols, rows)
    split = CX0 + PITCH_X * (cols // 2) - PITCH_X // 2                    # boundary between the middle columns
    out = np.concatenate([light[:, :split], dark[:, split:]], axis=1)
    labels = {t: np.array(Image.open(os.path.join(PARTS, f"labels-{t}.png")).convert("RGB")) for t in ("light", "dark")}
    th = TILE_BOTTOM - TILE_TOP
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            n = NAMES[i]
            lr, lc = divmod(i, LABEL_COLS)                                # position in the labels sheet
            side = "light" if c < cols // 2 else "dark"
            cx, cy = CX0 + PITCH_X * c, CY0 + PITCH_Y * r
            tile = labels[side][lr * th:(lr + 1) * th, lc * TILE_W:(lc + 1) * TILE_W]
            out[cy + TILE_TOP:cy + TILE_BOTTOM, cx - TILE_W // 2:cx + TILE_W // 2, :3] = tile
            accent = ACCENTS[r * (cols // 2) + c % (cols // 2)]
            theme = accent + ("" if side == "light" else "-dark")
            o = ov.get(n, {})
            svg = y.make_svg(theme, found[n], o.get("scale", 1.0), o.get("align", "bbox"), o.get("dx", 0.0), o.get("dy", 0.0))
            over(out, y.rasterise(svg, ICON), cx - ICON // 2, cy - ICON // 2)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if a.background == "gradient":
        h, w = out.shape[:2]
        if size:
            cw, ch = size
            canvas = gradient(cw, ch)
            ox, oy = (cw - w) // 2, (ch - h) // 2                       # negative = window cropped
            sx, sy = max(-ox, 0), max(-oy, 0)                           # source offset when cropping
            dx, dy = max(ox, 0), max(oy, 0)
            ww, hh = min(w - sx, cw - dx), min(h - sy, ch - dy)
            win = out[sy:sy + hh, sx:sx + ww]
            al = win[:, :, 3:4] / 255
            canvas[dy:dy + hh, dx:dx + ww] = win[:, :, :3] * al + canvas[dy:dy + hh, dx:dx + ww] * (1 - al)
        else:
            m = max(a.margin, 0)
            canvas = gradient(w + 2 * m, h + 2 * m)
            al = out[:, :, 3:4] / 255
            canvas[m:m + h, m:m + w] = out[:, :, :3] * al + canvas[m:m + h, m:m + w] * (1 - al)
        out = np.dstack([np.clip(canvas + 0.5, 0, 255), np.full(canvas.shape[:2], 255)]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(a.out, optimize=True)
    print(f"{out.shape[1]}x{out.shape[0]} -> {a.out}")


if __name__ == "__main__":
    main()
