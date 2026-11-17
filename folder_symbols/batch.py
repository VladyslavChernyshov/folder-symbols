"""Batch mode: icons for many symbols x theme variants x sizes, in parallel worker processes."""
import os, sys

from .svg import make_svg
from .symbols import effective_params, find_symbols, load_overrides
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
    done = 0
    if _G["svg"]:
        for tname, tdir in _G["tdirs"].items():
            dest = os.path.join(o["out"], tname, "scalable", f"{name}.svg")
            if o["skip_existing"] and os.path.exists(dest):
                continue
            try:
                txt = make_svg(tdir, svg, *effective_params(ov, o["scale"], o["align"]), o["solid"])
            except Exception as e:
                return name, done, f"svg failed: {e}"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(txt)
            done += 1
    for size in _G["sizes"]:
        try:
            scale, align, dx, dy = effective_params(ov, o["scale"], o["align"])
            sym = render_symbol(svg, size, scale, o["solid"])
        except Exception as e:
            return name, 0, f"render failed: {e}"
        for tname, theme in _G["themes"].items():
            dest = os.path.join(o["out"], tname, str(size), f"{name}.png")
            if o["skip_existing"] and os.path.exists(dest):
                continue
            try:
                img = compose(theme, sym, size, align, dx, dy)
            except ValueError as e:
                return name, done, str(e)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            img.save(dest, optimize=True)
            done += 1
    return name, done, None


def _parse_sizes(spec):
    """--sizes value -> (PNG sizes, whether "svg" was asked for)."""
    sizes = tuple(d for d in SIZE_DIRS if d not in NO_SYMBOL) if spec == "all" \
        else tuple(spec.split(","))
    svg = "svg" in sizes
    return tuple(sz for sz in sizes if sz != "svg"), svg


def _pick_themes(themes_arg, icons_root, sizes):
    """--themes value -> {theme: directory or name}; exits when a theme is not available."""
    root = icons_root or "/usr/share/icons"
    if sizes or icons_root:          # PNG needs the theme directories; so does an explicit --icons-root
        avail = installed_themes(root)
        themes_of = lambda t: f"{root}/{t}"
        where = root
    else:                            # SVG only: the built-in table is enough
        avail = sorted(builtin_themes())
        themes_of = lambda t: t
        where = "the built-in table (assets/themes.json)"
    want = avail if themes_arg == "all" else [t for t in themes_arg.split(",")]
    missing = [t for t in want if t not in avail]
    if missing:
        sys.exit(f"themes not found in {where}: {missing}\navailable: {avail}")
    return {t: themes_of(t) for t in want}


def _drop_no_symbol(sizes):
    """Validate the PNG sizes, report and drop those where Yaru draws no symbol."""
    for sz in sizes:
        size_dir(sz)                                   # validate early
    skipped = [sz for sz in sizes if size_dir(sz) in NO_SYMBOL]
    if skipped:
        print(f"skipping {', '.join(skipped)}: Yaru draws no symbol at 16 px, the output would "
              "just be copies of the plain folder", flush=True)
        sizes = tuple(sz for sz in sizes if size_dir(sz) not in NO_SYMBOL)
    return sizes


def _summary_line(n_syms, n_themes, svg, sizes):
    fmts = len(sizes) + svg
    return (f"{n_syms} symbols x {n_themes} themes x {fmts} output{'s' if fmts != 1 else ''} "
            f"({', '.join((['svg'] if svg else []) + list(sizes))}) = "
            f"{n_syms * n_themes * fmts} icons")


def batch(a):
    from multiprocessing import Pool
    sizes, svg = _parse_sizes(a.sizes)
    themes = _pick_themes(a.themes, a.icons_root, sizes)
    sizes = _drop_no_symbol(sizes)
    syms = find_symbols(a.symbols_dir, a.only)
    print(_summary_line(len(syms), len(themes), svg, sizes), flush=True)
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
