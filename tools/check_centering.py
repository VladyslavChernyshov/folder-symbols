#!/usr/bin/env python3
"""Measure how far each generated icon's symbol is from the centre of the folder's front panel.

Usage: check_centering.py DIR_WITH_PNGS [--max-offset PERCENT]
Exit status 1 if any icon is off-centre by more than --max-offset (default 1.0 % of icon size).
"""
import argparse, os, sys
import numpy as np
from PIL import Image


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from folder_symbols.engine import panel_bbox


def measure(im):
    """im: RGBA uint8 array. Returns (dx, dy, ink_w, ink_h) in px; dx/dy = symbol bbox centre
    minus front-panel centre. Returns None if no symbol is found."""
    n = im.shape[0]
    x0, y0, x1, y1 = panel_bbox(im)
    pcx, pcy = (x0 + x1) / 2, (y0 + y1) / 2
    im = im.astype(int)
    vals, cnt = np.unique(im[im[:, :, 3] == 255][:, :3], axis=0, return_counts=True)
    body = vals[cnt.argmax()]
    m = np.zeros(im.shape[:2], bool)
    m[int(y0 + .08 * n):int(y1 - .08 * n), int(x0 + .08 * n):int(x1 - .08 * n)] = True
    ys, xs = np.nonzero((np.abs(im[:, :, :3] - body).sum(2) > 30) & m)
    if not len(ys):
        return None
    return ((xs.min() + xs.max() + 1) / 2 - pcx, (ys.min() + ys.max() + 1) / 2 - pcy,
            xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dir")
    p.add_argument("--max-offset", type=float, default=1.0, help="percent of icon size")
    a = p.parse_args()
    res = []
    for f in sorted(os.listdir(a.dir)):
        if not f.endswith(".png"):
            continue
        im = np.array(Image.open(os.path.join(a.dir, f)).convert("RGBA"))
        r = measure(im)
        n = im.shape[0]
        res.append((f, None) if r is None else (f, (abs(r[0]) / n * 100, abs(r[1]) / n * 100, r[2], r[3])))
    ok = [r for r in res if r[1]]
    empty = [r[0] for r in res if r[1] is None]
    arr = np.array([r[1][:2] for r in ok])
    print("icons: %d  |dx| mean %.2f%% max %.2f%%  |dy| mean %.2f%% max %.2f%% (of icon size)"
          % (len(res), arr[:, 0].mean(), arr[:, 0].max(), arr[:, 1].mean(), arr[:, 1].max()))
    print("worst 10 by offset:")
    for f, v in sorted(ok, key=lambda r: -max(r[1][:2]))[:10]:
        print("  dx %.2f%%  dy %.2f%%  %s  ink %dx%d" % (v[0], v[1], f, v[2], v[3]))
    print("smallest 5 / largest 5 by ink:")
    for f, v in sorted(ok, key=lambda r: max(r[1][2:]))[:5] + sorted(ok, key=lambda r: -max(r[1][2:]))[:5]:
        print("  ink %dx%d  %s" % (v[2], v[3], f))
    if empty:
        print("NO SYMBOL FOUND:", ", ".join(empty))
    bad = [f for f, v in ok if max(v[:2]) > a.max_offset]
    if bad:
        print("OFF-CENTRE (> %.1f%%): %s" % (a.max_offset, ", ".join(bad)))
    sys.exit(1 if bad or empty else 0)


if __name__ == "__main__":
    main()
