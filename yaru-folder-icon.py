#!/usr/bin/env python3
"""Compose a symbolic icon onto a Yaru folder icon, reproducing Yaru's embossed style.

Colours are calibrated from the theme itself (folder.png vs folder-publicshare.png),
so every Yaru accent / dark variant works without a colour table. Output is PNG or SVG.

Run without arguments (or with --help) for the full description of every command and option.
Requires: python3, python3-pil, python3-numpy, python3-scipy, rsvg-convert (librsvg2-bin).
"""
import argparse, functools, io, json, os, re, subprocess, sys

__version__ = "0.1.0"   # the one place the version lives; tag releases as v<__version__>
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

# Geometry measured on Yaru's own folder-publicshare (fractions of the icon size)
INK_CENTER = (247.5 / 512, 287.3 / 512)   # Yaru's own symbol position (--align yaru)
SYMBOL_PX = 190 / 512                     # a 16x16 symbolic viewBox is rendered at this fraction
EMBOSS = 4 / 512                          # inset-shadow / highlight offset
SS = 4                                    # supersampling
# Yaru's size directories. Sizes can be given as these names or as the aliases 256 / 512.
SIZE_DIRS = ["16x16", "16x16@2x", "24x24", "24x24@2x", "32x32", "32x32@2x",
             "48x48", "48x48@2x", "256x256", "256x256@2x"]
ALIAS = {"256": "256x256", "512": "256x256@2x"}
NO_SYMBOL = {"16x16", "16x16@2x"}         # Yaru draws no symbol on its smallest folders
EMBOSS_MIN_PX = 256                       # below this Yaru's symbols are flat, one colour


def size_dir(spec):
    d = ALIAS.get(str(spec), str(spec))
    if d not in SIZE_DIRS:
        raise ValueError(f"unknown size {spec!r}; use 256, 512 or one of {SIZE_DIRS}")
    return d


def size_px(spec):
    """Real pixel size of a size spec: 24x24@2x -> 48."""
    m = re.match(r"(\d+)x\d+(?:@(\d)x)?$", size_dir(spec))
    return int(m.group(1)) * int(m.group(2) or 1)


def load(theme_dir, size, name):
    path = f"{theme_dir}/{size_dir(size)}/places/{name}.png"
    if not os.path.exists(path):
        root = os.path.dirname(os.path.normpath(theme_dir)) or "."
        have = sorted(d for d in os.listdir(root) if d.startswith("Yaru")) if os.path.isdir(root) else []
        sys.exit(f"{path} not found: theme '{os.path.basename(os.path.normpath(theme_dir))}' is not installed "
                 f"(Yaru themes in {root}: {', '.join(have) or 'none'}). "
                 "Variants such as Yaru-mate live in separate packages (e.g. yaru-mate-icon-theme).")
    return Image.open(path).convert("RGBA")


def calibrate(theme_dir):
    """Return (D1, D2): the two symbol colours of this theme variant (always measured at 512)."""
    a = np.array(load(theme_dir, 512, "folder")).astype(float)
    b = np.array(load(theme_dir, 512, "folder-publicshare")).astype(float)
    t = round(EMBOSS * 512)
    d = np.abs(a - b).sum(2) > 0
    hl = a[:, :, :3] * 0.8 + 51
    S = ndi.binary_opening(d & ~(np.abs(b[:, :, :3] - hl).max(2) <= 2))
    up = np.zeros_like(S); up[t:] = S[:-t]
    d1 = ndi.binary_erosion(S & up, iterations=2)
    d2 = ndi.binary_erosion(S & ~up, iterations=1)
    return np.median(b[d1][:, :3], 0), np.median(b[d2][:, :3], 0)


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


class Theme:
    """Everything that depends only on the theme variant, loaded once."""
    def __init__(self, theme_dir, sizes=(256, 512)):
        self.dir = theme_dir
        self.D1, self.D2 = calibrate(theme_dir)
        self.base = {s: np.array(load(theme_dir, s, "folder")) for s in sizes}
        self.center = {}
        for s in sizes:
            if size_dir(s) not in NO_SYMBOL:
                self.center[s] = panel_center(Image.fromarray(self.base[s]))


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


MAX_INK_W, MAX_INK_H = 0.52, 0.38   # ink must fit this box (fractions of icon size); a full
                                    # 16x16 grid is ~0.37, wide symbols get more room horizontally
OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overrides.json")


def load_overrides(path=None):
    """Per-symbol tweaks: {"name": {"scale": 1.6, "dx": 0.0, "dy": 0.0}} (dx/dy: fraction of icon)."""
    path = path or OVERRIDES_FILE
    if not os.path.exists(path):
        return {}
    import json
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def strip_opacity(text):
    """Remove opacity / fill-opacity / stroke-opacity so translucent 'secondary' parts become solid."""
    text = re.sub(r'\s(?:fill-|stroke-)?opacity\s*=\s*"[^"]*"', "", text)
    return re.sub(r'(?<![-\w])(?:fill-|stroke-)?opacity\s*:\s*[\d.]+\s*;?', "", text)


def _render(svg, size, scale, solid=True):
    size = size_px(size)
    uw, uh = svg_units(svg)
    unit = SYMBOL_PX * scale * size * SS / 16.0
    w, h = max(1, round(uw * unit)), max(1, round(uh * unit))
    text = open(svg, encoding="utf-8", errors="ignore").read()
    if solid:
        text = strip_opacity(text)
    out = subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h)],
                         input=text.encode("utf-8"), capture_output=True, check=True).stdout
    return np.array(Image.open(io.BytesIO(out)).convert("RGBA"))[:, :, 3] / 255.0


def render_symbol(svg, size, scale=1.0, solid=True, with_scale=False):
    """Alpha mask of the symbol at SS x supersampling for an icon of `size` px.
    solid=True (default) ignores SVG opacity, so every part of the symbol is fully opaque.
    with_scale=True also returns the effective scale after fitting into the size box."""
    sym = _render(svg, size, scale, solid)
    size = size_px(size)
    ys, xs = np.nonzero(sym > 0.02)
    if len(ys):
        k = min(1.0, MAX_INK_W * size * SS / (xs.max() - xs.min() + 1),
                MAX_INK_H * size * SS / (ys.max() - ys.min() + 1))
        if k < 1.0:
            scale, sym = scale * k, _render(svg, size, scale * k, solid)
    return (sym, scale) if with_scale else sym


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


def compose(theme, sym, size, align="bbox", dx=0.0, dy=0.0):
    """Composite supersampled symbol mask `sym` onto theme's folder. Returns a PIL image.
    Sizes below 256 px get a flat symbol (no emboss); the 16 px folders get no symbol."""
    if size_dir(size) in NO_SYMBOL:
        return Image.fromarray(theme.base[size], "RGBA")
    n = size_px(size)
    big = n * SS
    flat = n < EMBOSS_MIN_PX
    cx, cy = ink_center(sym, align)
    if align == "yaru":
        tx, ty = INK_CENTER[0] * big, INK_CENTER[1] * big
    else:
        tx, ty = theme.center[size][0] * SS, theme.center[size][1] * SS
    ox, oy = round(tx + dx * big - cx), round(ty + dy * big - cy)
    t = 0 if flat else round(EMBOSS * big)
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
    out = theme.base[size].astype(float)
    rgb = out[ry0:ry1, rx0:rx1, :3]
    if flat:
        layers = ((theme.D1, down(S, SS)),)
    else:
        St = np.zeros_like(S); St[t:] = S[:-t]
        aS, aD1, aH = down(S, SS), down(S * St, SS), down(St * (1 - S), SS)
        layers = ((np.full(3, 255.0), 0.2 * aH), (theme.D2, aS), (theme.D1, aD1))
    for col, al in layers:
        rgb[:] = rgb * (1 - al[:, :, None]) + col * al[:, :, None]
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def one(a):
    name = os.path.basename(a.symbol_svg).replace("-symbolic.svg", "").replace(".svg", "")
    ov = {} if a.no_overrides else load_overrides(a.overrides).get(name, {})
    if a.output_png.lower().endswith(".svg"):
        if not theme_ref_kind(a.theme_dir):
            sys.exit(f"theme '{a.theme_dir}' not found: give a theme directory or a built-in name "
                     f"({', '.join(sorted(builtin_themes()))})")
        with open(a.output_png, "w", encoding="utf-8") as f:
            f.write(make_svg(a.theme_dir, a.symbol_svg, a.scale * ov.get("scale", 1.0),
                             ov.get("align", a.align), a.dx + ov.get("dx", 0.0),
                             a.dy + ov.get("dy", 0.0), not a.keep_opacity))
        return
    theme = Theme(a.theme_dir, (a.size,))
    sym = render_symbol(a.symbol_svg, a.size, a.scale * ov.get("scale", 1.0), not a.keep_opacity)
    compose(theme, sym, a.size, ov.get("align", a.align), a.dx + ov.get("dx", 0.0),
            a.dy + ov.get("dy", 0.0)).save(a.output_png, optimize=True)


# ---------------------------------------------------------------- SVG output
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "folder-template.svg")
TEMPLATE_MATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "folder-template-mate.svg")
DUMMY_ACCENT, DUMMY_DARK = "#00ff03", "#008502"      # Yaru's dummy colours in the template


def _hex(v):
    return "#%02x%02x%02x" % tuple(int(np.clip(round(x), 0, 255)) for x in v)


def _rasterise(svg_text, px):
    out = subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px)], input=svg_text.encode("utf-8"),
                         capture_output=True, check=True).stdout
    return np.array(Image.open(io.BytesIO(out)).convert("RGBA")).astype(float)


def template_path(theme_dir):
    """Light Yaru-mate has its own folder drawing with fixed colours; all others share one template."""
    return TEMPLATE_MATE if os.path.basename(os.path.normpath(theme_dir)) == "Yaru-mate" else TEMPLATE


def template_text(theme_dir=None):
    t = open(template_path(theme_dir) if theme_dir else TEMPLATE, encoding="utf-8").read()
    return t.replace("<!--SYMBOL-DEFS-->", "").replace("<!--SYMBOL-LAYERS-->", "")


@functools.lru_cache(maxsize=None)
def fit_folder_colors(theme_dir):
    """Find the two colours Yaru substitutes for its dummy colours in this theme variant, by
    least squares against the theme's own folder.png (the result is linear in both colours)."""
    ref = np.array(load(theme_dir, 512, "folder")).astype(float)
    t = template_text(theme_dir)
    if DUMMY_ACCENT not in t:                          # fixed-colour template (Yaru-mate)
        return None, None
    basis = {k: _rasterise(t.replace(DUMMY_ACCENT, a).replace(DUMMY_DARK, o), 512)
             for k, (a, o) in {"0": ("#000000", "#000000"), "a": ("#ffffff", "#000000"),
                               "o": ("#000000", "#ffffff")}.items()}
    m = (ref[:, :, 3] > 250) & (basis["0"][:, :, 3] > 250)
    A, O = [], []
    for ch in range(3):
        c0 = basis["0"][:, :, ch][m]
        M = np.stack([(basis["a"][:, :, ch][m] - c0) / 255, (basis["o"][:, :, ch][m] - c0) / 255], 1)
        x = np.linalg.lstsq(M, ref[:, :, ch][m] - c0, rcond=None)[0]
        A.append(x[0]); O.append(x[1])
    return _hex(A), _hex(O)


def _symbol_markup(svg, solid):
    """Contents of the symbol SVG (ids prefixed to avoid clashes) and its viewBox."""
    text = open(svg, encoding="utf-8", errors="ignore").read()
    if solid:
        text = strip_opacity(text)
    root = re.search(r"<svg\b[^>]*>", text, re.S).group(0)
    inner = text[text.index(root) + len(root):text.rindex("</svg>")]
    inner = re.sub(r"<(metadata|sodipodi:namedview)\b.*?(</\1>|/>)", "", inner, flags=re.S)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S)
    inner = re.sub(r'\bid="([^"]+)"', r'id="s-\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", r"url(#s-\1)", inner)
    inner = re.sub(r'((?:xlink:)?href)="#([^"]+)"', r'\1="#s-\2"', inner)
    inner = re.sub(r'\s(?:xmlns:\w+|inkscape:[\w-]+|sodipodi:[\w-]+)="[^"]*"', "", inner)
    vb = re.search(r'viewBox="\s*([-\d.]+)[ ,]+([-\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)', root)
    return inner, tuple(float(x) for x in vb.groups()) if vb else None


THEMES_JSON = os.path.join(os.path.dirname(TEMPLATE), "themes.json")


def compute_svg_data(theme_dir):
    """Everything the SVG output needs to know about one theme variant, measured from its PNGs:
    fitted template colours (none for light Yaru-mate), emboss colours D1/D2, front-panel centre."""
    theme = Theme(theme_dir, (256,))
    colors = [c for c in fit_folder_colors(theme_dir) if c]
    return {"colors": colors, "d1": _hex(theme.D1), "d2": _hex(theme.D2),
            "center": [round(float(v), 4) for v in theme.center[256]]}


@functools.lru_cache(maxsize=None)
def builtin_themes():
    """assets/themes.json: precomputed compute_svg_data() of every known Yaru variant, so SVGs
    can be made without any Yaru icon theme installed (rebuild: tools/build_themes_json.py)."""
    try:
        with open(THEMES_JSON, encoding="utf-8") as f:
            return json.load(f)["themes"]
    except (OSError, KeyError, ValueError):
        return {}


def theme_ref_kind(ref):
    """'dir' if ref is a theme directory with PNG folders, 'builtin' if it names a theme in
    assets/themes.json, else None."""
    if os.path.isdir(os.path.join(ref, SIZE_DIRS[-1], "places")):
        return "dir"
    if os.path.basename(os.path.normpath(ref)) in builtin_themes():
        return "builtin"
    return None


@functools.lru_cache(maxsize=None)
def svg_data(ref):
    """Data for the SVG output of a theme given as a directory (measured now; wins when you
    point at one explicitly) or as a plain name (taken from the built-in table)."""
    kind = theme_ref_kind(ref)
    if kind == "dir":
        return compute_svg_data(ref)
    if kind == "builtin":
        return builtin_themes()[os.path.basename(os.path.normpath(ref))]
    sys.exit(f"theme '{ref}' is neither a theme directory with PNG folders nor one of the built-in "
             f"variants ({', '.join(sorted(builtin_themes())) or 'none'}). "
             "Give the path of an installed theme, e.g. /usr/share/icons/Yaru-dark.")


def make_svg(theme_ref, symbol_svg, scale=1.0, align="bbox", dx=0.0, dy=0.0, solid=True):
    """A single scalable SVG: Yaru's folder in this theme variant with the symbol embossed on it.
    theme_ref: a theme directory, or the name of a built-in variant such as 'Yaru-dark'."""
    theme_dir = theme_ref
    data = svg_data(theme_ref)
    sym, eff = render_symbol(symbol_svg, 256, scale, solid, with_scale=True)
    cx, cy = ink_center(sym, align)                      # mask px; at size 256, 1 user unit = SS px
    tx, ty = data["center"] if align != "yaru" else (INK_CENTER[0] * 256, INK_CENTER[1] * 256)
    ox, oy = tx + dx * 256 - cx / SS, ty + dy * 256 - cy / SS
    uw, uh = svg_units(symbol_svg)
    unit = SYMBOL_PX * eff * 256 / 16.0                  # user units per nominal symbol unit
    cw, ch = uw * unit, uh * unit
    inner, vb = _symbol_markup(symbol_svg, solid)
    vx, vy, vw, vh = vb or (0.0, 0.0, uw, uh)
    k = min(cw / vw, ch / vh)                            # viewBox -> canvas, preserveAspectRatio meet
    px_, py_ = (cw - vw * k) / 2 - vx * k, (ch - vh * k) / 2 - vy * k
    t = EMBOSS * 256
    tpl = template_path(theme_dir)
    d1, d2 = data["d1"], data["d2"]
    f = lambda v: ("%.4f" % v).rstrip("0").rstrip(".")
    box = 'maskUnits="userSpaceOnUse" x="0" y="0" width="256" height="256"'
    fbox = 'filterUnits="userSpaceOnUse" x="0" y="0" width="256" height="256" color-interpolation-filters="sRGB"'
    defs = f"""
<clipPath id="yfi-clip"><rect x="{f(vx)}" y="{f(vy)}" width="{f(vw)}" height="{f(vh)}"/></clipPath>
<g id="yfi-symbol" transform="translate({f(ox + px_)},{f(oy + py_)}) scale({f(k)})"><g clip-path="url(#yfi-clip)">{inner}</g></g>
<filter id="yfi-white" {fbox}><feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0"/></filter>
<filter id="yfi-black" {fbox}><feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"/></filter>
<mask id="yfi-m-body" {box}><g filter="url(#yfi-white)"><use xlink:href="#yfi-symbol"/></g></mask>
<mask id="yfi-m-light" {box}><g filter="url(#yfi-white)"><use xlink:href="#yfi-symbol" y="{f(t)}"/></g><g filter="url(#yfi-black)"><use xlink:href="#yfi-symbol"/></g></mask>
<mask id="yfi-m-inner" {box}><g mask="url(#yfi-m-body)"><g filter="url(#yfi-white)"><use xlink:href="#yfi-symbol" y="{f(t)}"/></g></g></mask>
"""
    layers = f"""<g id="yfi-emboss">
<rect width="256" height="256" fill="#ffffff" fill-opacity="0.2" mask="url(#yfi-m-light)"/>
<rect width="256" height="256" fill="{d2}" mask="url(#yfi-m-body)"/>
<rect width="256" height="256" fill="{d1}" mask="url(#yfi-m-inner)"/>
</g>"""
    text = open(tpl, encoding="utf-8").read()
    if data["colors"]:
        text = text.replace(DUMMY_ACCENT, data["colors"][0]).replace(DUMMY_DARK, data["colors"][1])
    return text.replace("<!--SYMBOL-DEFS-->", defs).replace("<!--SYMBOL-LAYERS-->", layers)


# ---------------------------------------------------------------- batch mode
_G = {}

def _init(themes, sizes, opts, svg=False):
    _G["themes"] = {name: Theme(path, sizes) for name, path in themes.items()} if sizes else {}
    _G["tdirs"], _G["svg"] = themes, svg
    _G["sizes"], _G["opts"] = sizes, opts


def _work(job):
    name, svg = job
    o = _G["opts"]
    ov = o["overrides"].get(name, {})
    done = skipped = 0
    if _G["svg"]:
        for tname, tdir in _G["tdirs"].items():
            dest = os.path.join(o["out"], tname, "scalable", f"{name}.svg")
            if o["skip_existing"] and os.path.exists(dest):
                continue
            try:
                txt = make_svg(tdir, svg, o["scale"] * ov.get("scale", 1.0), ov.get("align", o["align"]),
                               ov.get("dx", 0.0), ov.get("dy", 0.0), o["solid"])
            except Exception as e:
                return name, done, f"svg failed: {e}"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(txt)
            done += 1
    for size in _G["sizes"]:
        try:
            sym = render_symbol(svg, size, o["scale"] * ov.get("scale", 1.0), o["solid"])
        except Exception as e:
            return name, 0, f"render failed: {e}"
        for tname, theme in _G["themes"].items():
            dest = os.path.join(o["out"], tname, str(size), f"{name}.png")
            if o["skip_existing"] and os.path.exists(dest):
                skipped += 1
                continue
            try:
                img = compose(theme, sym, size, ov.get("align", o["align"]),
                              ov.get("dx", 0.0), ov.get("dy", 0.0))
            except ValueError as e:
                return name, done, str(e)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            img.save(dest, optimize=True)
            done += 1
    return name, done, None


def find_symbols(root, pattern):
    """name -> svg path; skips broken symlinks and duplicate names."""
    found = {}
    for dp, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            if not f.endswith("-symbolic.svg"):
                continue
            p = os.path.join(dp, f)
            name = f[:-len("-symbolic.svg")]
            if not os.path.exists(p) or name in found:
                continue
            if pattern and not re.search(pattern, name):
                continue
            found[name] = p
    return found


def batch(a):
    from multiprocessing import Pool
    sizes = tuple(d for d in SIZE_DIRS if d not in NO_SYMBOL) if a.sizes == "all" \
        else tuple(a.sizes.split(","))
    svg = "svg" in sizes
    sizes = tuple(sz for sz in sizes if sz != "svg")
    root = a.icons_root or "/usr/share/icons"
    if sizes or a.icons_root:        # PNG needs the theme directories; so does an explicit --icons-root
        avail = sorted(d for d in os.listdir(root) if os.path.isdir(root)
                       and d.startswith("Yaru") and os.path.isdir(f"{root}/{d}/{SIZE_DIRS[-1]}/places")) \
            if os.path.isdir(root) else []
        themes_of = lambda t: f"{root}/{t}"
        where = root
    else:                            # SVG only: the built-in table is enough
        avail = sorted(builtin_themes())
        themes_of = lambda t: t
        where = "the built-in table (assets/themes.json)"
    want = avail if a.themes == "all" else [t for t in a.themes.split(",")]
    missing = [t for t in want if t not in avail]
    if missing:
        sys.exit(f"themes not found in {where}: {missing}\navailable: {avail}")
    themes = {t: themes_of(t) for t in want}
    for sz in sizes:
        size_dir(sz)                                   # validate early
    skipped = [sz for sz in sizes if size_dir(sz) in NO_SYMBOL]
    if skipped:
        print(f"skipping {', '.join(skipped)}: Yaru draws no symbol at 16 px, the output would "
              "just be copies of the plain folder", flush=True)
        sizes = tuple(sz for sz in sizes if size_dir(sz) not in NO_SYMBOL)
    syms = find_symbols(a.symbols_dir, a.only)
    fmts = len(sizes) + svg
    print(f"{len(syms)} symbols x {len(themes)} themes x {fmts} output{'s' if fmts != 1 else ''} "
          f"({', '.join((['svg'] if svg else []) + list(sizes))}) = "
          f"{len(syms) * len(themes) * fmts} icons", flush=True)
    opts = dict(out=a.out, scale=a.scale, align=a.align, skip_existing=a.skip_existing,
                overrides=load_overrides(a.overrides), solid=not a.keep_opacity)
    errors = 0
    with Pool(a.jobs, _init, (themes, sizes, opts, svg)) as pool:
        for i, (name, n, err) in enumerate(pool.imap_unordered(_work, list(syms.items())), 1):
            if err:
                errors += 1
                print(f"  ! {name}: {err}", flush=True)
            if i % 50 == 0 or i == len(syms):
                print(f"  {i}/{len(syms)}", flush=True)
    print(f"done, {errors} symbols with errors")


# ---------------------------------------------------------------- apply / reset
def current_icon_theme():
    out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip().strip("'")


def find_theme_dir(name, roots):
    for r in roots:
        d = os.path.join(os.path.expanduser(r), name)
        if os.path.isdir(os.path.join(d, SIZE_DIRS[-1], "places")):
            return d
    sys.exit(f"theme '{name}' not found in {roots}")


def find_symbol(symbol, symbols_dir):
    if symbol.endswith(".svg") and os.path.exists(symbol):
        return symbol
    hit = find_symbols(symbols_dir, None).get(re.sub(r"-symbolic(\.svg)?$", "", symbol))
    if not hit:
        sys.exit(f"symbol '{symbol}' not found in {symbols_dir} (try: ls {symbols_dir}/*/ | grep -i word)")
    return hit


def apply(a):
    theme_name = a.theme or current_icon_theme()
    roots = ([a.icons_root] if a.icons_root else []) + ["~/.local/share/icons", "/usr/share/icons"]
    if a.format == "svg" and not a.icons_root and theme_name in builtin_themes():
        theme_dir = theme_name                         # built-in data: no installed theme needed
    else:
        theme_dir = find_theme_dir(theme_name, roots)
    svg = find_symbol(a.symbol, a.symbols_dir)
    name = os.path.basename(svg)[:-len("-symbolic.svg")] if svg.endswith("-symbolic.svg") \
        else os.path.splitext(os.path.basename(svg))[0]
    store = os.path.expanduser(a.store)
    os.makedirs(store, exist_ok=True)
    ov = {} if a.no_overrides else load_overrides(a.overrides).get(name, {})
    if a.format == "svg":
        png = os.path.join(store, f"{theme_name}-{name}.svg")
        with open(png, "w", encoding="utf-8") as f:
            f.write(make_svg(theme_dir, svg, a.scale * ov.get("scale", 1.0), ov.get("align", a.align),
                             ov.get("dx", 0.0), ov.get("dy", 0.0), not a.keep_opacity))
    else:
        png = os.path.join(store, f"{theme_name}-{name}.png")
        theme = Theme(theme_dir, (a.size,))
        compose(theme, render_symbol(svg, a.size, a.scale * ov.get("scale", 1.0), not a.keep_opacity), a.size,
                ov.get("align", a.align), ov.get("dx", 0.0), ov.get("dy", 0.0)).save(png, optimize=True)
    folder = os.path.abspath(os.path.expanduser(a.folder))
    cmd = ["gio", "set", folder, "metadata::custom-icon", "file://" + png]
    print(f"{theme_name}: {name} -> {png}")
    if a.dry_run:
        print(" ".join(cmd)); return
    subprocess.run(cmd, check=True)
    print(f"icon set on {folder} (restart Nautilus if it does not update: nautilus -q)")


def reset(a):
    subprocess.run(["gio", "set", "-t", "unset", os.path.abspath(os.path.expanduser(a.folder)),
                    "metadata::custom-icon"], check=True)


# ---------------------------------------------------------------- command line
OVERVIEW = """\
yaru-folder-icon.py - put a symbol on Ubuntu's Yaru folder icon, in Yaru's own embossed style.

Takes any symbolic icon (*-symbolic.svg, e.g. the ~1300 that ship in
/usr/share/icons/Yaru/scalable) and composites it onto the folder icon of any Yaru colour
variant (light/dark, every accent, MATE), either as a PNG or as a scalable SVG. The result looks
like the folder icons Yaru draws itself (a symbol pressed into the front panel). Colours are not
hard-coded: they are measured from the theme's own folder.png, so every variant works.

Commands:
  apply   FOLDER SYMBOL      build a scalable (SVG) icon for one folder and set it in Nautilus (Files)
  reset   FOLDER             remove a custom icon set with 'apply'
  batch   --out DIR          generate icons for many symbols x themes x sizes at once
  (none)  THEME_DIR SYMBOL.svg OUT.png|OUT.svg
                             compose a single icon file, no folder is touched

Run 'yaru-folder-icon.py COMMAND --help' for one command only. Examples:
  yaru-folder-icon.py apply ~/Music community
  yaru-folder-icon.py reset ~/Music
  yaru-folder-icon.py /usr/share/icons/Yaru-dark /usr/share/icons/Yaru/scalable/actions/share-symbolic.svg share.svg
  yaru-folder-icon.py batch --out dist --themes Yaru,Yaru-dark --sizes svg,512

Requires: python3, python3-pil, python3-numpy, python3-scipy, rsvg-convert (librsvg2-bin).
Licence: script MIT; generated icons CC BY-SA 4.0 (derived from Yaru), see NOTICE.md.
"""

_FMT = argparse.HelpFormatter
_SIZES = "512 (= 256x256@2x, default), 256 (= 256x256) or a Yaru size directory such as 48x48 or 24x24@2x"


def _common(p, batch=False):
    """Options shared by every command that renders a symbol."""
    p.add_argument("--scale", type=float, default=1.0, metavar="X",
                   help="multiply the symbol's size by X (1.0 = Yaru's size; the symbol is still "
                        "shrunk to fit the folder's front panel). Default: 1.0")
    p.add_argument("--align", choices=("bbox", "mass", "yaru"), default="bbox",
                   help="how the symbol is centred on the front panel. bbox: centre of its visible "
                        "bounding box (default); mass: centre of mass; yaru: the fixed position "
                        "Yaru itself uses")
    p.add_argument("--keep-opacity", action="store_true",
                   help="keep the translucent parts of a symbol as in its SVG. By default every "
                        "part is drawn fully opaque so the symbol looks uniform")
    p.add_argument("--overrides", default=None, metavar="FILE",
                   help="JSON file with per-symbol exceptions {name: {scale, dx, dy, align}}. "
                        "Default: overrides.json next to this script")


def parser_compose():
    p = argparse.ArgumentParser(
        prog="yaru-folder-icon.py", formatter_class=_FMT,
        usage="yaru-folder-icon.py THEME_DIR SYMBOL_SVG OUTPUT [options]",
        description="Compose one symbol onto one theme's folder icon and write it to a file. The "
                    "output type follows the extension: .png (raster) or .svg (scalable, one "
                    "self-contained file). No folder or setting is changed.")
    p.add_argument("theme_dir", help="icon theme directory with the PNG folders, e.g. "
                   "/usr/share/icons/Yaru-dark (or Yaru-purple, Yaru-mate-dark, ...). For .svg output "
                   "a plain built-in variant name such as Yaru-dark works too, with no theme installed")
    p.add_argument("symbol_svg", help="the symbolic icon to put on the folder, e.g. "
                   "/usr/share/icons/Yaru/scalable/actions/share-symbolic.svg")
    p.add_argument("output_png", metavar="OUTPUT", help="file to write, ending in .png or .svg")
    p.add_argument("--size", default="512", metavar="SIZE",
                   help="PNG only: icon size, one of " + _SIZES + ". Ignored for .svg")
    _common(p)
    p.add_argument("--dx", type=float, default=0.0, metavar="F",
                   help="move the symbol right by F x icon size (negative = left). Default: 0")
    p.add_argument("--dy", type=float, default=0.0, metavar="F",
                   help="move the symbol down by F x icon size (negative = up). Default: 0")
    p.add_argument("--no-overrides", action="store_true", help="ignore overrides.json completely")
    return p


def parser_apply():
    p = argparse.ArgumentParser(
        prog="yaru-folder-icon.py apply", formatter_class=_FMT,
        usage="yaru-folder-icon.py apply FOLDER SYMBOL [options]",
        description="Build an icon for the given folder (scalable SVG by default, stored under --store) and set it as "
                    "the folder's custom icon in Nautilus via 'gio set ... metadata::custom-icon'. "
                    "The icon uses the colours of the GNOME icon theme that is active now, so "
                    "re-run it after changing theme or accent colour.")
    p.add_argument("apply", help=argparse.SUPPRESS)
    p.add_argument("folder", help="the folder that gets the icon, e.g. ~/Music")
    p.add_argument("symbol", help="symbol name, e.g. community (the file name without "
                   "'-symbolic.svg', searched in --symbols-dir), or a path to a *-symbolic.svg")
    p.add_argument("--theme", default=None, metavar="NAME",
                   help="Yaru theme variant to take colours from, e.g. Yaru-purple-dark. "
                        "Default: the current GNOME icon theme (gsettings)")
    p.add_argument("--icons-root", default=None, metavar="DIR",
                   help="measure the theme from the PNG folders in this directory instead of using "
                        "the built-in data (SVG), and look here first for PNG themes (then "
                        "~/.local/share/icons and /usr/share/icons). Default: built-in data for "
                        "SVG, installed themes for PNG")
    p.add_argument("--symbols-dir", default="/usr/share/icons/Yaru/scalable", metavar="DIR",
                   help="where symbol names are looked up. Default: /usr/share/icons/Yaru/scalable")
    p.add_argument("--store", default="~/.local/share/folder-icons", metavar="DIR",
                   help="where the generated icon file is kept; Nautilus reads it from there, so do not "
                        "delete it. Default: ~/.local/share/folder-icons")
    p.add_argument("--format", choices=("svg", "png"), default="svg",
                   help="svg: one scalable file, sharp at any size (default); png: a raster icon, "
                        "see --size")
    p.add_argument("--size", default="512", metavar="SIZE",
                   help="PNG only (--format png): icon size, one of " + _SIZES + ". Nautilus scales it down")
    _common(p)
    p.add_argument("--no-overrides", action="store_true", help="ignore overrides.json completely")
    p.add_argument("--dry-run", action="store_true",
                   help="build the icon file and print the gio command, but do not run it")
    return p


def parser_reset():
    p = argparse.ArgumentParser(
        prog="yaru-folder-icon.py reset", formatter_class=_FMT,
        usage="yaru-folder-icon.py reset FOLDER",
        description="Remove the custom icon of a folder (gio set -t unset ... metadata::custom-icon), "
                    "so Nautilus shows the theme's normal folder again. The generated file is not deleted.")
    p.add_argument("reset", help=argparse.SUPPRESS)
    p.add_argument("folder", help="the folder to restore, e.g. ~/Music")
    return p


def parser_batch():
    p = argparse.ArgumentParser(
        prog="yaru-folder-icon.py batch", formatter_class=_FMT,
        usage="yaru-folder-icon.py batch --out DIR [options]",
        description="Generate icons for many symbols and many theme variants at once, in parallel. "
                    "Output layout: OUT/<theme>/scalable/<symbol>.svg for SVGs and "
                    "OUT/<theme>/<size>/<symbol>.png for PNGs. 1323 symbols x 26 themes as SVG "
                    "take under a minute.")
    p.add_argument("batch", help=argparse.SUPPRESS)
    p.add_argument("--out", required=True, metavar="DIR", help="directory to write the icon sets into")
    p.add_argument("--icons-root", default=None, metavar="DIR",
                   help="directory holding the Yaru* theme directories (installed themes, or "
                        "yaru/src/icons from Yaru's source tree). Needed for PNG output (default "
                        "/usr/share/icons); with --sizes svg and no --icons-root the built-in data "
                        "in assets/themes.json is used and no Yaru theme has to be installed. "
                        "Giving it measures the themes from these directories instead")
    p.add_argument("--symbols-dir", default="/usr/share/icons/Yaru/scalable", metavar="DIR",
                   help="directory searched recursively for *-symbolic.svg. "
                        "Default: /usr/share/icons/Yaru/scalable")
    p.add_argument("--themes", default="all", metavar="LIST",
                   help="'all' (every Yaru* theme found, default) or a comma-separated list, "
                        "e.g. Yaru,Yaru-dark")
    p.add_argument("--sizes", default="512,256", metavar="LIST",
                   help="comma-separated outputs: svg (scalable), 512, 256, or Yaru size directories "
                        "(24x24, 48x48@2x, ...); or 'all' = every PNG size that carries a symbol "
                        "(all except the two 16 px ones, where Yaru draws none). "
                        "Example: svg,512. Default: 512,256")
    p.add_argument("--only", default=None, metavar="REGEX",
                   help="only symbols whose name matches this regular expression, e.g. '^(share|folder)'")
    p.add_argument("--jobs", type=int, default=os.cpu_count(), metavar="N",
                   help="parallel worker processes. Default: number of CPUs")
    _common(p, batch=True)
    p.add_argument("--skip-existing", action="store_true",
                   help="do not regenerate files that already exist (resume an interrupted run)")
    return p


def main(argv):
    if argv and argv[0] in ("-V", "--version"):
        print(f"yaru-folder-icon.py {__version__}")
        return
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(OVERVIEW)
        for name, mk in (("COMPOSE ONE FILE", parser_compose), ("apply", parser_apply),
                         ("reset", parser_reset), ("batch", parser_batch)):
            print("=" * 78 + f"\n{name}\n" + "=" * 78)
            print(mk().format_help())
        return
    cmd = argv[0]
    if cmd == "reset":
        reset(parser_reset().parse_args(argv))
    elif cmd == "apply":
        apply(parser_apply().parse_args(argv))
    elif cmd == "batch":
        batch(parser_batch().parse_args(argv))
    else:
        one(parser_compose().parse_args(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
