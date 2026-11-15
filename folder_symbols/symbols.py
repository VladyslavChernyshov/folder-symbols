"""Finding symbolic icons (*-symbolic.svg) and the per-symbol tweaks in overrides.json."""
import json, os, re

YARU_SYMBOLS = "/usr/share/icons/Yaru/scalable"   # where symbol names are looked up by default
OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overrides.json")


def symbol_name(symbol_svg):
    """The name of a symbol file: 'community' for .../community-symbolic.svg, the stem for other files."""
    base = os.path.basename(symbol_svg)
    return base[:-len("-symbolic.svg")] if base.endswith("-symbolic.svg") else os.path.splitext(base)[0]


def default_symbols_dir():
    """The symbols directory for the GUI: $YARU_SYMBOLS_DIR if set, else YARU_SYMBOLS."""
    return os.environ.get("YARU_SYMBOLS_DIR") or YARU_SYMBOLS


def load_overrides(path=None):
    """Per-symbol tweaks: {"name": {"scale": 1.6, "dx": 0.0, "dy": 0.0}} (dx/dy: fraction of icon)."""
    path = path or OVERRIDES_FILE
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def effective_params(ov, scale, align, dx=None, dy=None):
    """(scale, align, dx, dy) for a symbol with overrides entry `ov` ({} for none): its scale multiplies
    `scale`, its align wins over `align`, its dx/dy are added to `dx`/`dy`. dx/dy None: the caller has no
    offset of its own, so the entry's value (default 0.0) is used as it is."""
    return (scale * ov.get("scale", 1.0), ov.get("align", align),
            ov.get("dx", 0.0) if dx is None else dx + ov.get("dx", 0.0),
            ov.get("dy", 0.0) if dy is None else dy + ov.get("dy", 0.0))


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
