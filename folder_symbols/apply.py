"""Setting and removing a folder's custom icon in Nautilus (gio metadata::custom-icon), and keeping
the manifest of those folders (store.py) up to date."""
import contextlib, hashlib, json, os, re, shlex, subprocess, sys

from . import store, yaru
from .store import Recipe
from .svg import make_svg
from .symbols import YARU_SYMBOLS, find_symbols, load_overrides
from .yaru import Theme, builtin_themes, compose, find_theme_dir, render_symbol


# ---------------------------------------------------------------- gio (the only place it is called)
class GioError(Exception):
    pass


def _gio(*args):
    try:
        r = subprocess.run(["gio", *args], capture_output=True, text=True)
    except OSError as e:
        raise GioError(f"cannot run gio: {e.strerror}") from None
    if r.returncode:
        raise GioError(r.stderr.strip() or f"gio exited with status {r.returncode}")
    return r.stdout


def gio_set(folder, uri):
    _gio("set", folder, "metadata::custom-icon", uri)


def gio_unset(folder):
    _gio("set", "-t", "unset", folder, "metadata::custom-icon")


def gio_custom_icon(folder):
    """The folder's metadata::custom-icon, or None if it has none (or gio cannot read it)."""
    try:
        out = _gio("info", "-a", "metadata::custom-icon", folder)
    except GioError:
        return None
    for line in out.splitlines():
        key, _, value = line.strip().partition(": ")
        if key == "metadata::custom-icon":
            return value
    return None


# ---------------------------------------------------------------- paths as the user sees them
def display_path(path):
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    return "~/" + os.path.relpath(path, home) if path.startswith(home.rstrip("/") + "/") else path


def shell_path(path):
    """A path for a shell command, written from ~ when it is in $HOME and quoted where needed."""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home.rstrip("/") + "/"):
        return "~/" + shlex.quote(os.path.relpath(path, home))
    return shlex.quote(path)


def _warn(manifest):
    for w in manifest.warnings:
        print(f"warning: {w}", file=sys.stderr)


# ---------------------------------------------------------------- apply
def find_symbol(symbol, symbols_dir):
    if symbol.endswith(".svg") and os.path.exists(symbol):
        return symbol
    hit = find_symbols(symbols_dir, None).get(re.sub(r"-symbolic(\.svg)?$", "", symbol))
    if not hit:
        sys.exit(f"symbol '{symbol}' not found in {symbols_dir} (try: ls {symbols_dir}/*/ | grep -i word)")
    return hit


def resolve_theme(a):
    """(theme to build with, accent to record or None). --theme is used as given; --accent takes the
    light/dark style from the system; with neither, the system's variant is used, and a system theme
    that is not Yaru stops with exit status 2 (nothing is built, set or recorded)."""
    if a.theme:
        v = yaru.parse_variant(a.theme)
        return a.theme, v[0] if v else None
    current = yaru.current_icon_theme()
    v = yaru.parse_variant(current)
    if a.accent:
        if not v:
            sys.exit(f"the current icon theme '{current}' is not a Yaru variant, so the light/dark style "
                     f"is unknown: give the full variant instead, e.g. --theme {yaru.variant_name(a.accent, True)}")
        return yaru.variant_name(a.accent, v[1]), a.accent
    if not v:
        print(f"error: the current icon theme '{current}' is not a Yaru variant: give the accent and style, "
              f"e.g. --theme {yaru.variant_name('sage', True)}, or set a Yaru icon theme and use "
              f"--accent", file=sys.stderr)
        sys.exit(2)
    return current, v[0]


def _not_in_recipe(a):
    """apply options that change the icon but are not part of the recipe."""
    return [opt for opt, used in (("--format png", a.format == "png"), ("--size", a.size != "512"),
                                  ("--keep-opacity", a.keep_opacity), ("--no-overrides", a.no_overrides),
                                  ("--overrides", a.overrides is not None),
                                  ("--icons-root", a.icons_root is not None)) if used]


def _file_suffix(a, name, ov):
    """'' for an icon built with default options (the name stays {theme}-{symbol}), else a short hash
    of the options, so folders with the same symbol but e.g. another --scale do not share one file."""
    opts = {"scale": a.scale, "align": a.align, "keep_opacity": a.keep_opacity, "overrides": ov,
            "size": a.size if a.format == "png" else None}
    default = {"scale": 1.0, "align": "bbox", "keep_opacity": False, "size": "512" if a.format == "png" else None,
               "overrides": load_overrides().get(name, {})}
    if opts == default:
        return ""
    return "-" + hashlib.sha1(json.dumps(opts, sort_keys=True).encode()).hexdigest()[:8]


def apply(a):
    folder = os.path.abspath(os.path.expanduser(a.folder))
    with store.editing() as m:
        _warn(m)
        m.check_writable()                     # fail before anything is built or set
        theme_name, accent = resolve_theme(a)
        roots = ([a.icons_root] if a.icons_root else []) + ["~/.local/share/icons", "/usr/share/icons"]
        if a.format == "svg" and not a.icons_root and theme_name in builtin_themes():
            theme_dir = theme_name                         # built-in data: no installed theme needed
        else:
            theme_dir = find_theme_dir(theme_name, roots)
        svg = find_symbol(a.symbol, a.symbols_dir)
        name = os.path.basename(svg)[:-len("-symbolic.svg")] if svg.endswith("-symbolic.svg") \
            else os.path.splitext(os.path.basename(svg))[0]
        by_name = svg != a.symbol and a.symbols_dir == YARU_SYMBOLS
        recipe = accent and Recipe(name if by_name else os.path.abspath(svg), accent, a.scale, a.align)
        store_dir = os.path.expanduser(a.store or store.icons_dir())
        os.makedirs(store_dir, exist_ok=True)
        ov = {} if a.no_overrides else load_overrides(a.overrides).get(name, {})
        base = f"{theme_name}-{name}{_file_suffix(a, name, ov)}"
        if a.format == "svg":
            png = os.path.join(store_dir, base + ".svg")
            with open(png, "w", encoding="utf-8") as f:
                f.write(make_svg(theme_dir, svg, a.scale * ov.get("scale", 1.0), ov.get("align", a.align),
                                 ov.get("dx", 0.0), ov.get("dy", 0.0), not a.keep_opacity))
        else:
            png = os.path.join(store_dir, base + ".png")
            theme = Theme(theme_dir, (a.size,))
            compose(theme, render_symbol(svg, a.size, a.scale * ov.get("scale", 1.0), not a.keep_opacity),
                    a.size, ov.get("align", a.align), ov.get("dx", 0.0), ov.get("dy", 0.0)).save(png, optimize=True)
        cmd = ["gio", "set", folder, "metadata::custom-icon", "file://" + png]
        print(f"{theme_name}: {name} -> {png}")
        if not recipe:
            print(f"warning: '{theme_name}' is not a Yaru variant, so {display_path(folder)} is not recorded "
                  "in the manifest ('list' and 'reset --all' will not see it)", file=sys.stderr)
        elif _not_in_recipe(a):
            print(f"warning: the manifest keeps only symbol, accent, scale and align; not kept: "
                  f"{', '.join(_not_in_recipe(a))}", file=sys.stderr)
        if a.dry_run:
            print(" ".join(cmd))
            if recipe:
                print(f"would record {display_path(folder)} in {m.path}")
            return
        try:
            gio_set(folder, "file://" + png)
        except GioError as e:
            sys.exit(f"gio failed: {e}")
        if recipe:
            m.record(folder, recipe)
    print(f"icon set on {folder} (restart Nautilus if it does not update: nautilus -q)")


# ---------------------------------------------------------------- reset
def reset(a):
    folder = os.path.abspath(os.path.expanduser(a.folder))
    with store.editing() as m:
        _warn(m)
        m.check_writable()
        if not os.path.exists(folder):
            if m.remove(folder):
                print(f"{display_path(folder)}: folder not found; removed from the manifest")
                return
            sys.exit(f"{folder}: no such folder")
        try:
            gio_unset(folder)
        except GioError as e:
            sys.exit(f"gio failed: {e}")
        m.remove(folder)


def reset_all(a):
    """Reset every folder in the manifest. Each one is tried on its own; failures are reported and
    their entries kept, and the exit status is 1 if there was any."""
    with store.editing() as m:
        _warn(m)
        m.check_writable()
        items = m.entries()
        failed = 0
        for e in items:
            label = display_path(e.folder)
            if not os.path.exists(e.folder):
                print(f"FAILED  {label}: not found, entry kept; run 'folder-symbols reset "
                      f"{shell_path(e.folder)}' to forget it")
                failed += 1
                continue
            try:
                gio_unset(e.folder)
            except (GioError, OSError) as err:
                print(f"FAILED  {label}: {err}")
                failed += 1
                continue
            m.remove(e.folder)
            print(f"ok      {label}")
    print(f"Reset {len(items) - failed} of {len(items)} folders" if items else "No folders in the manifest")
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------- prune
def prune(a):
    """Forget the manifest entries of folders that no longer exist, in one save. Only the manifest
    changes: no gio, no icon files deleted (a folder moved in Nautilus may still point to one)."""
    with contextlib.nullcontext(store.load()) if a.dry_run else store.editing() as m:
        _warn(m)
        m.check_writable()
        total = len(m.entries())
        stale, unknown, skipped = store.stale_entries(m, a.include_external)
        if not a.dry_run:
            m.remove_many(e.folder for e in stale)
    for e in stale:
        print(f"{'would remove' if a.dry_run else 'removed '}  {display_path(e.folder)}")
    for e, err in unknown:
        print(f"kept      {display_path(e.folder)}: cannot check ({err.strerror or err})")
    if skipped:
        print(f"Skipped {skipped} {'entry' if skipped == 1 else 'entries'} outside ~ (the drive may not be "
              "mounted); use --include-external to check them too")
    if not stale:
        print("Nothing to remove")
    else:
        print(f"{'Would remove' if a.dry_run else 'Removed'} {len(stale)} of {total} entries")


# ---------------------------------------------------------------- list
def apply_command(entry):
    """A ready-to-run command that applies this entry's recipe again (style taken from the system)."""
    r = entry.recipe
    sym = shell_path(r.symbol) if os.path.isabs(r.symbol) else shlex.quote(r.symbol)
    parts = ["folder-symbols", "apply", shell_path(entry.folder), sym, "--accent", shlex.quote(r.accent)]
    if r.scale != 1.0:
        parts += ["--scale", repr(r.scale)]
    if r.align != "bbox":
        parts += ["--align", shlex.quote(r.align)]
    return " ".join(parts)


def list_folders(a):
    m = store.load()
    _warn(m)
    items = m.entries()
    if a.format == "commands":                 # no checks: folders may exist only on the other computer
        for e in items:
            print(apply_command(e))
        return
    if not items:
        print(f"No folders recorded (manifest: {m.path})")
        return
    rows = [("FOLDER", "SYMBOL", "ACCENT", "OPTIONS", "STATUS")]
    for e in items:
        r = e.recipe
        opts = " ".join(([f"scale {r.scale:g}"] if r.scale != 1.0 else []) +
                        ([f"align {r.align}"] if r.align != "bbox" else [])) or "-"
        sym = display_path(r.symbol) if os.path.isabs(r.symbol) else r.symbol
        rows.append((display_path(e.folder), sym, r.accent, opts,
                     store.icon_status(e.folder, gio_custom_icon)))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + row[4])
