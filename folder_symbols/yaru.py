"""Everything specific to Yaru: its icon sizes and folder geometry, colour calibration from the
theme's own PNGs, the SVG folder templates, the built-in table assets/themes.json and finding
installed theme variants."""
import functools, json, os, re, subprocess, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .engine import SS, composite, hex_color, ink_center, panel_center, rasterise, render_fitted

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Geometry measured on Yaru's own folder-publicshare (fractions of the icon size)
INK_CENTER = (247.5 / 512, 287.3 / 512)   # Yaru's own symbol position (--align yaru)
SYMBOL_PX = 190 / 512                     # a 16x16 symbolic viewBox is rendered at this fraction
EMBOSS = 4 / 512                          # inset-shadow / highlight offset
# Yaru's size directories. Sizes can be given as these names or as the aliases 256 / 512.
SIZE_DIRS = ["16x16", "16x16@2x", "24x24", "24x24@2x", "32x32", "32x32@2x",
             "48x48", "48x48@2x", "256x256", "256x256@2x"]
ALIAS = {"256": "256x256", "512": "256x256@2x"}
NO_SYMBOL = {"16x16", "16x16@2x"}         # Yaru draws no symbol on its smallest folders
EMBOSS_MIN_PX = 256                       # below this Yaru's symbols are flat, one colour
MAX_INK_W, MAX_INK_H = 0.52, 0.38   # ink must fit this box (fractions of icon size); a full
                                    # 16x16 grid is ~0.37, wide symbols get more room horizontally


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


def render_symbol(svg, size, scale=1.0, solid=True, with_scale=False):
    """Alpha mask of the symbol at SS x supersampling for an icon of `size` (a Yaru size spec),
    at Yaru's symbol size and shrunk to fit the front panel.
    solid=True (default) ignores SVG opacity, so every part of the symbol is fully opaque.
    with_scale=True also returns the effective scale after fitting into the size box."""
    sym, scale = render_fitted(svg, size_px(size), SYMBOL_PX, MAX_INK_W, MAX_INK_H, scale, solid)
    return (sym, scale) if with_scale else sym


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
    return composite(theme.base[size], sym, (ox, oy), theme.D1, theme.D2, t)


# ---------------------------------------------------------------- SVG templates and built-in data
TEMPLATE = os.path.join(ROOT, "assets", "folder-template.svg")
TEMPLATE_MATE = os.path.join(ROOT, "assets", "folder-template-mate.svg")
DUMMY_ACCENT, DUMMY_DARK = "#00ff03", "#008502"      # Yaru's dummy colours in the template
THEMES_JSON = os.path.join(os.path.dirname(TEMPLATE), "themes.json")


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
    basis = {k: rasterise(t.replace(DUMMY_ACCENT, a).replace(DUMMY_DARK, o), 512)
             for k, (a, o) in {"0": ("#000000", "#000000"), "a": ("#ffffff", "#000000"),
                               "o": ("#000000", "#ffffff")}.items()}
    m = (ref[:, :, 3] > 250) & (basis["0"][:, :, 3] > 250)
    A, O = [], []
    for ch in range(3):
        c0 = basis["0"][:, :, ch][m]
        M = np.stack([(basis["a"][:, :, ch][m] - c0) / 255, (basis["o"][:, :, ch][m] - c0) / 255], 1)
        x = np.linalg.lstsq(M, ref[:, :, ch][m] - c0, rcond=None)[0]
        A.append(x[0]); O.append(x[1])
    return hex_color(A), hex_color(O)


def compute_svg_data(theme_dir):
    """Everything the SVG output needs to know about one theme variant, measured from its PNGs:
    fitted template colours (none for light Yaru-mate), emboss colours D1/D2, front-panel centre."""
    theme = Theme(theme_dir, (256,))
    colors = [c for c in fit_folder_colors(theme_dir) if c]
    return {"colors": colors, "d1": hex_color(theme.D1), "d2": hex_color(theme.D2),
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


def _split_variant(name):
    """'Yaru-purple-dark' -> ('purple', True), 'Yaru' -> ('orange', False); None for other names."""
    base, dark = (name[:-len("-dark")], True) if name.endswith("-dark") else (name, False)
    if base == "Yaru":
        return "orange", dark
    if base.startswith("Yaru-") and base[len("Yaru-"):] not in ("", "orange"):
        return base[len("Yaru-"):], dark
    return None


@functools.lru_cache(maxsize=None)
def accents():
    """Accent names of the built-in variants: 'orange' is plain Yaru, the others are the variant names
    without 'Yaru-' and '-dark' (bark, blue, ..., mate, ...)."""
    return tuple(sorted({v[0] for v in map(_split_variant, builtin_themes()) if v}))


def parse_variant(name):
    """(accent, dark) of a Yaru variant name such as 'Yaru-sage-dark', or None if it is not one."""
    v = _split_variant(name or "")
    return v if v and v[0] in accents() else None


def variant_name(accent, dark):
    """Inverse of parse_variant: ('purple', True) -> 'Yaru-purple-dark', ('orange', False) -> 'Yaru'."""
    if accent not in accents():
        raise ValueError(f"unknown accent {accent!r}; use one of {', '.join(accents())}")
    return "Yaru" + ("" if accent == "orange" else f"-{accent}") + ("-dark" if dark else "")


def current_icon_theme():
    """The GNOME icon theme in use now (on Ubuntu it names the Yaru accent and the light/dark style)."""
    out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip().strip("'")


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


# ---------------------------------------------------------------- installed themes
def installed_themes(root):
    """Names of the Yaru* theme directories with PNG folders in `root` (sorted)."""
    return sorted(d for d in os.listdir(root) if os.path.isdir(root)
                  and d.startswith("Yaru") and os.path.isdir(f"{root}/{d}/{SIZE_DIRS[-1]}/places")) \
        if os.path.isdir(root) else []


def find_theme_dir(name, roots):
    for r in roots:
        d = os.path.join(os.path.expanduser(r), name)
        if os.path.isdir(os.path.join(d, SIZE_DIRS[-1], "places")):
            return d
    sys.exit(f"theme '{name}' not found in {roots}")
