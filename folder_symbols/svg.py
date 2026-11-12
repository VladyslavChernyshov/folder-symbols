"""Scalable (SVG) output: Yaru's folder template with the symbol embossed on it, using masks."""
import re

from .engine import SS, ink_center, strip_opacity, svg_units
from .yaru import DUMMY_ACCENT, DUMMY_DARK, EMBOSS, INK_CENTER, SYMBOL_PX, render_symbol, svg_data, \
    template_path


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
<clipPath id="fs-clip"><rect x="{f(vx)}" y="{f(vy)}" width="{f(vw)}" height="{f(vh)}"/></clipPath>
<g id="fs-symbol" transform="translate({f(ox + px_)},{f(oy + py_)}) scale({f(k)})"><g clip-path="url(#fs-clip)">{inner}</g></g>
<filter id="fs-white" {fbox}><feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0"/></filter>
<filter id="fs-black" {fbox}><feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"/></filter>
<mask id="fs-m-body" {box}><g filter="url(#fs-white)"><use xlink:href="#fs-symbol"/></g></mask>
<mask id="fs-m-light" {box}><g filter="url(#fs-white)"><use xlink:href="#fs-symbol" y="{f(t)}"/></g><g filter="url(#fs-black)"><use xlink:href="#fs-symbol"/></g></mask>
<mask id="fs-m-inner" {box}><g mask="url(#fs-m-body)"><g filter="url(#fs-white)"><use xlink:href="#fs-symbol" y="{f(t)}"/></g></g></mask>
"""
    layers = f"""<g id="fs-emboss">
<rect width="256" height="256" fill="#ffffff" fill-opacity="0.2" mask="url(#fs-m-light)"/>
<rect width="256" height="256" fill="{d2}" mask="url(#fs-m-body)"/>
<rect width="256" height="256" fill="{d1}" mask="url(#fs-m-inner)"/>
</g>"""
    text = open(tpl, encoding="utf-8").read()
    if data["colors"]:
        text = text.replace(DUMMY_ACCENT, data["colors"][0]).replace(DUMMY_DARK, data["colors"][1])
    return text.replace("<!--SYMBOL-DEFS-->", defs).replace("<!--SYMBOL-LAYERS-->", layers)
