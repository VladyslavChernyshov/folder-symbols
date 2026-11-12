"""Finding symbolic icons (*-symbolic.svg) and the per-symbol tweaks in overrides.json."""
import json, os, re

YARU_SYMBOLS = "/usr/share/icons/Yaru/scalable"   # where symbol names are looked up by default
OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overrides.json")


def load_overrides(path=None):
    """Per-symbol tweaks: {"name": {"scale": 1.6, "dx": 0.0, "dy": 0.0}} (dx/dy: fraction of icon)."""
    path = path or OVERRIDES_FILE
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


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
