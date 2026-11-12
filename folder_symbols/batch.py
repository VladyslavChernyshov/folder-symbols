"""Batch mode: icons for many symbols x theme variants x sizes, in parallel worker processes."""
import os, sys

from .svg import make_svg
from .symbols import find_symbols, load_overrides
from .yaru import NO_SYMBOL, SIZE_DIRS, Theme, builtin_themes, compose, installed_themes, render_symbol, \
    size_dir

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


def batch(a):
    from multiprocessing import Pool
    sizes = tuple(d for d in SIZE_DIRS if d not in NO_SYMBOL) if a.sizes == "all" \
        else tuple(a.sizes.split(","))
    svg = "svg" in sizes
    sizes = tuple(sz for sz in sizes if sz != "svg")
    root = a.icons_root or "/usr/share/icons"
    if sizes or a.icons_root:        # PNG needs the theme directories; so does an explicit --icons-root
        avail = installed_themes(root)
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
