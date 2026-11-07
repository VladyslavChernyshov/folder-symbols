#!/usr/bin/env python3
"""Make a contact sheet PNG from a directory of icons (for eyeballing a generated set).

Usage: contact_sheet.py DIR OUT.png [--every N] [--cols 10] [--cell 160]
"""
import argparse, os
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument("dir"); p.add_argument("out")
p.add_argument("--every", type=int, default=1, help="take every Nth icon")
p.add_argument("--cols", type=int, default=10)
p.add_argument("--cell", type=int, default=160)
a = p.parse_args()
fs = sorted(f for f in os.listdir(a.dir) if f.endswith(".png"))[::a.every]
rows = (len(fs) + a.cols - 1) // a.cols
sheet = Image.new("RGBA", (a.cols * a.cell, rows * a.cell), (40, 40, 40, 255))
for i, f in enumerate(fs):
    im = Image.open(os.path.join(a.dir, f)).convert("RGBA").resize((a.cell, a.cell), Image.LANCZOS)
    sheet.alpha_composite(im, ((i % a.cols) * a.cell, (i // a.cols) * a.cell))
sheet.save(a.out)
print(f"{len(fs)} icons -> {a.out}")
