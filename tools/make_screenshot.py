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
                          [--background gradient|transparent] [--margin 40]
"""
import argparse, importlib.util, os, sys
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
COLS, ROWS = 6, 4
# Ubuntu wallpaper colours along the diagonal from bottom left to top right (measured from the desktop)
GRADIENT = [(0.0, (225, 95, 44)), (0.5, (148, 58, 69)), (1.0, (97, 33, 77))]
# geometry of the compact screenshot (see prepare_screenshot_parts.py)
GRID_TOP, GRID_BOTTOM, WIDEN_AT, CX0, PITCH_X, CY0, PITCH_Y = 76, 836, 480, 99, 118, 127, 124
TILE_W, TILE_TOP, TILE_BOTTOM, ICON = 118, 30, 84, 64


def load_script():
    spec = importlib.util.spec_from_file_location("yfi", os.path.join(ROOT, "yaru-folder-icon.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def frame(theme):
    """Compact window, grid area resized to ROWS rows and widened by one column pitch per extra column."""
    im = np.array(Image.open(os.path.join(PARTS, f"frame-{theme}.png")).convert("RGBA"))
    new_body = GRID_BOTTOM - GRID_TOP - 2 * PITCH_Y                       # six rows -> four rows
    body = np.repeat(im[GRID_TOP + 4:GRID_TOP + 5], new_body, axis=0)
    im = np.concatenate([im[:GRID_TOP], body, im[GRID_BOTTOM:]], axis=0)
    extra = (COLS - 5) * PITCH_X
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
    a = p.parse_args()
    y = load_script()
    found = y.find_symbols(a.symbols_dir, None)
    missing = [n for n in NAMES if n not in found]
    if missing:
        sys.exit(f"symbols not found in {a.symbols_dir}: {', '.join(missing)}")
    ov = y.load_overrides()
    light, dark = frame("light"), frame("dark")
    split = CX0 + PITCH_X * (COLS // 2) - PITCH_X // 2                    # boundary between the middle columns
    out = np.concatenate([light[:, :split], dark[:, split:]], axis=1)
    labels = {t: np.array(Image.open(os.path.join(PARTS, f"labels-{t}.png")).convert("RGB")) for t in ("light", "dark")}
    th = TILE_BOTTOM - TILE_TOP
    for r in range(ROWS):
        for c in range(COLS):
            n = NAMES[r * COLS + c]
            side = "light" if c < COLS // 2 else "dark"
            cx, cy = CX0 + PITCH_X * c, CY0 + PITCH_Y * r
            tile = labels[side][r * th:(r + 1) * th, c * TILE_W:(c + 1) * TILE_W]
            out[cy + TILE_TOP:cy + TILE_BOTTOM, cx - TILE_W // 2:cx + TILE_W // 2, :3] = tile
            accent = ACCENTS[r * (COLS // 2) + c % (COLS // 2)]
            theme = accent + ("" if side == "light" else "-dark")
            o = ov.get(n, {})
            svg = y.make_svg(theme, found[n], o.get("scale", 1.0), o.get("align", "bbox"), o.get("dx", 0.0), o.get("dy", 0.0))
            over(out, y._rasterise(svg, ICON), cx - ICON // 2, cy - ICON // 2)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if a.background == "gradient":
        m = max(a.margin, 0)
        h, w = out.shape[:2]
        canvas = gradient(w + 2 * m, h + 2 * m)
        al = out[:, :, 3:4] / 255
        canvas[m:m + h, m:m + w] = out[:, :, :3] * al + canvas[m:m + h, m:m + w] * (1 - al)
        out = np.dstack([np.clip(canvas + 0.5, 0, 255), np.full(canvas.shape[:2], 255)]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(a.out, optimize=True)
    print(f"{out.shape[1]}x{out.shape[0]} -> {a.out}")


if __name__ == "__main__":
    main()
