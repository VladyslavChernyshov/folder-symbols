"""Theme-independent rendering and compositing.

Nothing here knows about Yaru: sizes, geometry and colours are passed in by the caller
(see yaru.py for the values that reproduce Yaru's own folders).
"""
import io, re, subprocess
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

SS = 4                                    # supersampling


def svg_units(svg):
    """Canvas size of the symbol in 1/16 icon-grid units.

    Nearly all Yaru symbols are 16x16. Some declare width/height="16" with an odd viewBox
    (e.g. 4.2333, millimetre grids) - the nominal width/height wins. Symbols with no
    width/height and a viewBox far from 16 (8, 64) are normalised so their long side is 16.
    """
    head = open(svg, encoding="utf-8", errors="ignore").read(3000)
    tag = (re.search(r"<svg\b[^>]*>", head, re.S) or [""])[0]
    num = lambda k: (lambda m: float(m.group(1)) if m else None)(
        re.search(r'\s%s="\s*([\d.]+)' % k, tag))
    w, h = num("width"), num("height")
    if w and h:
        return w, h
    m = re.search(r'viewBox="\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)', tag)
    if not m:
        return 16.0, 16.0
    vw, vh = float(m.group(1)), float(m.group(2))
    if 12 <= max(vw, vh) <= 20:
        return vw, vh
    k = 16.0 / max(vw, vh)
    return vw * k, vh * k


def strip_opacity(text):
    """Remove opacity / fill-opacity / stroke-opacity so translucent 'secondary' parts become solid."""
    text = re.sub(r'\s(?:fill-|stroke-)?opacity\s*=\s*"[^"]*"', "", text)
    return re.sub(r'(?<![-\w])(?:fill-|stroke-)?opacity\s*:\s*[\d.]+\s*;?', "", text)


def _render(svg, px, symbol_frac, scale, solid):
    uw, uh = svg_units(svg)
    unit = symbol_frac * scale * px * SS / 16.0
    w, h = max(1, round(uw * unit)), max(1, round(uh * unit))
    text = open(svg, encoding="utf-8", errors="ignore").read()
    if solid:
        text = strip_opacity(text)
    out = subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h)],
                         input=text.encode("utf-8"), capture_output=True, check=True).stdout
    return np.array(Image.open(io.BytesIO(out)).convert("RGBA"))[:, :, 3] / 255.0


def render_fitted(svg, px, symbol_frac, max_w, max_h, scale=1.0, solid=True):
    """Alpha mask of the symbol at SS x supersampling for an icon of `px` pixels, and the effective
    scale. A 16-unit symbol grid spans symbol_frac x scale of the icon; if the ink is larger than
    max_w x max_h (fractions of the icon size), the symbol is rendered again, shrunk to fit.
    solid=True ignores SVG opacity, so every part of the symbol is fully opaque."""
    sym = _render(svg, px, symbol_frac, scale, solid)
    ys, xs = np.nonzero(sym > 0.02)
    if len(ys):
        k = min(1.0, max_w * px * SS / (xs.max() - xs.min() + 1),
                max_h * px * SS / (ys.max() - ys.min() + 1))
        if k < 1.0:
            scale, sym = scale * k, _render(svg, px, symbol_frac, scale * k, solid)
    return sym, scale


def down(m, k):
    h, w = m.shape
    return m.reshape(h // k, k, w // k, k).mean((1, 3))


def ink_center(sym, align):
    """Centre (cx, cy) of the symbol's ink in mask pixels, by bounding box or centre of mass."""
    ys, xs = np.nonzero(sym > 0.02)
    if len(ys) == 0:
        raise ValueError("empty symbol")
    if align == "mass":
        w = sym[ys, xs]
        return (xs * w).sum() / w.sum() + 0.5, (ys * w).sum() / w.sum() + 0.5
    return (xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2


def composite(base, sym, origin, d1, d2, shift):
    """Press the supersampled symbol mask `sym` into the RGBA array `base` (n x n), its top-left
    corner at mask pixel `origin` (ox, oy). shift: emboss offset in mask pixels; 0 draws a flat
    symbol in d1 only. Otherwise a white highlight below, the symbol in d2 and its shadowed inner
    part in d1. Returns a PIL image."""
    n = base.shape[0]
    ox, oy = origin
    t = shift
    # work only on the output-pixel region around the symbol
    sh, sw = sym.shape
    rx0, ry0 = max(0, ox // SS - 1), max(0, oy // SS - 1)
    rx1, ry1 = min(n, (ox + sw) // SS + 3), min(n, (oy + sh + t) // SS + 3)
    if rx1 <= rx0 or ry1 <= ry0:
        raise ValueError("symbol outside icon")
    S = np.zeros(((ry1 - ry0) * SS, (rx1 - rx0) * SS))
    py, px = oy - ry0 * SS, ox - rx0 * SS
    y0, x0 = max(py, 0), max(px, 0)
    y1, x1 = min(py + sh, S.shape[0]), min(px + sw, S.shape[1])
    S[y0:y1, x0:x1] = sym[y0 - py:y1 - py, x0 - px:x1 - px]
    out = base.astype(float)
    rgb = out[ry0:ry1, rx0:rx1, :3]
    if t == 0:
        layers = ((d1, down(S, SS)),)
    else:
        St = np.zeros_like(S); St[t:] = S[:-t]
        aS, aD1, aH = down(S, SS), down(S * St, SS), down(St * (1 - S), SS)
        layers = ((np.full(3, 255.0), 0.2 * aH), (d2, aS), (d1, aD1))
    for col, al in layers:
        rgb[:] = rgb * (1 - al[:, :, None]) + col * al[:, :, None]
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def panel_bbox(a):
    """Bounding box (x0, y0, x1, y1; x1/y1 exclusive) of the folder's front panel: the largest
    connected area of the body colour (the most common opaque colour)."""
    op = a[:, :, 3] == 255
    vals, counts = np.unique(a[op][:, :3], axis=0, return_counts=True)
    body = vals[counts.argmax()]
    near = (np.abs(a[:, :, :3].astype(int) - body).sum(2) <= 6) & op
    lab, n = ndi.label(near)
    big = 1 + np.argmax(ndi.sum(near, lab, range(1, n + 1)))
    ys, xs = np.nonzero(lab == big)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def panel_center(base):
    """Centre (x, y) in pixels of the folder's front panel."""
    x0, y0, x1, y1 = panel_bbox(np.array(base))
    return (x0 + x1) / 2, (y0 + y1) / 2


def hex_color(v):
    return "#%02x%02x%02x" % tuple(int(np.clip(round(x), 0, 255)) for x in v)


def rasterise(svg_text, px):
    out = subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px)], input=svg_text.encode("utf-8"),
                         capture_output=True, check=True).stdout
    return np.array(Image.open(io.BytesIO(out)).convert("RGBA")).astype(float)
