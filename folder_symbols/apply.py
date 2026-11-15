"""Setting and removing a folder's custom icon in Nautilus (gio metadata::custom-icon), and keeping
the manifest of those folders (store.py) up to date."""
import contextlib, dataclasses, hashlib, json, os, re, shlex, subprocess, sys

from . import accents, store, yaru
from .store import SYSTEM_ACCENT, Recipe
from .svg import make_svg_for
from .symbols import YARU_SYMBOLS, effective_params, find_symbols, load_overrides, symbol_name
from .yaru import DEFAULT_SIZE, Theme, builtin_themes, compose, find_theme_dir, render_symbol


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
def shell_path(path):
    """A path for a shell command, written from ~ when it is in $HOME and quoted where needed."""
    short = store.tilde(path)
    if short == path:
        return shlex.quote(path)
    return "~" if short == "~" else "~/" + shlex.quote(short[2:])


def _warn(manifest):
    for w in manifest.warnings:
        print(f"warning: {w}", file=sys.stderr)


# ---------------------------------------------------------------- apply
class ApplyError(Exception):
    """An apply that cannot go ahead for any folder (symbol not found, unknown accent, icon not built)."""


class RecordError(Exception):
    """apply_folders set the icons (results: the FolderResults) but could not save the manifest (error:
    the OSError), so the folders that got their icon are not recorded."""

    def __init__(self, results, error):
        super().__init__(f"the manifest could not be saved: {error}")
        self.results, self.error = results, error


@dataclasses.dataclass(frozen=True)
class FolderResult:
    folder: str          # absolute path
    ok: bool
    message: str         # "icon set", or why it was not


def lookup_symbol(symbol, symbols_dir):
    """The file of a symbol given as a path to an existing .svg or as a name looked up in symbols_dir."""
    if symbol.endswith(".svg") and os.path.exists(symbol):
        return symbol
    hit = find_symbols(symbols_dir, None).get(re.sub(r"-symbolic(\.svg)?$", "", symbol))
    if not hit:
        raise ApplyError(f"symbol '{symbol}' not found in {symbols_dir} (try: ls {symbols_dir}/*/ | grep -i word)")
    return hit


def find_symbol(symbol, symbols_dir):
    try:
        return lookup_symbol(symbol, symbols_dir)
    except ApplyError as e:
        sys.exit(str(e))


def recipe_symbol(symbol, svg, symbols_dir):
    """The symbol as the recipe keeps it: its name when it was looked up by name in Yaru's own tree,
    else the absolute path of its file (a path was given, or a non-default symbols directory)."""
    by_name = svg != symbol and symbols_dir == YARU_SYMBOLS
    return symbol_name(svg) if by_name else os.path.abspath(svg)


def resolve_theme(a):
    """(theme to build with, accent to record or None). --theme is used as given and pins its accent;
    --accent NAME pins NAME and takes the light/dark style from the system; with neither (or --accent
    system) the system's variant is used and the folder follows the system accent. A system theme that
    is not Yaru stops with exit status 2 then (nothing is built, set or recorded)."""
    if a.theme:
        v = yaru.parse_variant(a.theme)
        return a.theme, v[0] if v else None
    current = yaru.current_icon_theme()
    v = yaru.parse_variant(current)
    if a.accent and a.accent != SYSTEM_ACCENT:
        if not v:
            sys.exit(f"the current icon theme '{current}' is not a Yaru variant, so the light/dark style "
                     f"is unknown: give the full variant instead, e.g. --theme {yaru.variant_name(a.accent, True)}")
        return yaru.variant_name(a.accent, v[1]), a.accent
    if not v:
        print(f"error: the current icon theme '{current}' is not a Yaru variant: give the accent and style, "
              f"e.g. --theme {yaru.variant_name('sage', True)}, or set a Yaru icon theme and use "
              f"--accent", file=sys.stderr)
        sys.exit(2)
    return current, SYSTEM_ACCENT


def theme_ref(theme_name, fmt="svg", icons_root=None):
    """What to build the icon from: the built-in data of a Yaru variant for SVG (no installed theme
    needed), else the theme directory found in icons_root, ~/.local/share/icons or /usr/share/icons."""
    if fmt == "svg" and not icons_root and theme_name in builtin_themes():
        return theme_name
    roots = ([icons_root] if icons_root else []) + ["~/.local/share/icons", "/usr/share/icons"]
    return find_theme_dir(theme_name, roots)


def _not_in_recipe(a):
    """apply options that change the icon but are not part of the recipe."""
    return [opt for opt, used in (("--format png", a.format == "png"), ("--size", a.size != DEFAULT_SIZE),
                                  ("--keep-opacity", a.keep_opacity), ("--no-overrides", a.no_overrides),
                                  ("--overrides", a.overrides is not None),
                                  ("--icons-root", a.icons_root is not None)) if used]


def icon_suffix(name, ov, scale=1.0, align="bbox", keep_opacity=False, png_size=None):
    """'' for an icon built with default options (the name stays {theme}-{symbol}), else a short hash
    of the options, so folders with the same symbol but e.g. another --scale do not share one file.
    png_size: the size of a PNG icon, None for SVG."""
    opts = {"scale": scale, "align": align, "keep_opacity": keep_opacity, "overrides": ov, "size": png_size}
    default = {"scale": 1.0, "align": "bbox", "keep_opacity": False,
               "size": None if png_size is None else DEFAULT_SIZE, "overrides": load_overrides().get(name, {})}
    if opts == default:
        return ""
    return "-" + hashlib.sha1(json.dumps(opts, sort_keys=True).encode()).hexdigest()[:8]


def write_icon(theme_dir, theme_name, svg, store_dir, ov, scale=1.0, align="bbox", keep_opacity=False,
               fmt="svg", size=DEFAULT_SIZE):
    """Build the icon into store_dir as {theme_name}-{symbol}{icon_suffix}.svg (or .png) and return its
    path. theme_dir: from theme_ref(); ov: the symbol's overrides entry ({} for none)."""
    name = symbol_name(svg)
    suffix = icon_suffix(name, ov, scale, align, keep_opacity, size if fmt == "png" else None)
    base = f"{theme_name}-{name}{suffix}"
    os.makedirs(store_dir, exist_ok=True)
    if fmt == "svg":
        path = os.path.join(store_dir, base + ".svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(make_svg_for(theme_dir, svg, ov, scale, align, keep_opacity))
    else:
        path = os.path.join(store_dir, base + ".png")
        theme = Theme(theme_dir, (size,))
        scale, align, dx, dy = effective_params(ov, scale, align)
        compose(theme, render_symbol(svg, size, scale, not keep_opacity), size, align, dx, dy).save(path, optimize=True)
    return path


def set_folder_icons(manifest, dirs, icon_path, recipe, set_icon=None):
    """Set icon_path as the custom icon of each folder, one by one: a failure is reported in that
    folder's FolderResult and does not stop the others. Only folders whose icon was set get the recipe
    in the manifest (recipe None: none is recorded); a failed folder keeps its old entry. The caller holds
    manifest in a store.editing() block, which saves it once at the end. set_icon(folder, uri) raises
    GioError or OSError on failure; None means gio_set (looked up at call time)."""
    set_icon = set_icon or gio_set
    uri = "file://" + icon_path
    results = []
    for folder in dirs:
        try:
            set_icon(folder, uri)
        except (GioError, OSError) as e:
            results.append(FolderResult(folder, False, str(e)))
            continue
        if recipe:
            manifest.record(folder, recipe)
        results.append(FolderResult(folder, True, "icon set"))
    return results


def apply_folders(dirs, symbol, accent, *, dark, symbols_dir, system_accent=None, store_dir=None,
                  manifest_path=None, set_icon=None):
    """Apply one recipe (symbol and accent, default scale and align) to several folders. The icon is built
    once into the store's icons directory, with the same name and content that `apply FOLDER SYMBOL
    --accent ACCENT --symbols-dir SYMBOLS_DIR` gives in the same light/dark style, then set on each
    folder. The manifest is changed under one lock and saved once, for the folders whose icon was set;
    an existing recipe of such a folder is replaced as a whole.

    accent: a Yaru accent name, which the folders keep (pinned), or SYSTEM_ACCENT: they follow the system
    accent, and the icon is built with system_accent (the window passes the accent its preview shows;
    None: the accent of the current icon theme). The icon file is the same as for that accent pinned.
    dark: the light/dark style to build in. The window passes the style its preview is drawn in
    (libadwaita's colour scheme); the CLI takes it from the icon theme's name, which normally agrees.
    symbol: a name looked up in symbols_dir, or a path to an .svg; it is recorded by name only for a name
    looked up in Yaru's own tree (YARU_SYMBOLS), else by absolute path. set_icon: see set_folder_icons.

    Returns one FolderResult per folder (duplicates dropped, order kept). Raises store.ManifestError
    (manifest damaged or newer) or ApplyError (unknown accent or symbol, no system accent to follow,
    icon not built) before any folder is changed, and RecordError when the icons were set but the
    manifest could not be saved afterwards. Other OSErrors (e.g. the lock file) come before anything is set."""
    seen, folders = set(), []
    for d in map(store.folder_path, dirs):
        if d not in seen:
            seen.add(d)
            folders.append(d)
    if not folders:
        return []
    results = None                   # set once the icons are set: an OSError after that is the save's
    try:
        with store.editing(manifest_path) as m:
            m.check_writable()
            build_accent = accent
            if accent == SYSTEM_ACCENT:
                build_accent = system_accent or accents.system_accent()
                if build_accent is None:
                    raise ApplyError("the current icon theme is not a Yaru variant (or cannot be read), so "
                                     "there is no system accent to follow; choose an accent")
            try:
                theme_name = yaru.variant_name(build_accent, dark)
            except ValueError as e:
                raise ApplyError(str(e)) from None
            svg = lookup_symbol(symbol, symbols_dir)
            recipe = Recipe(recipe_symbol(symbol, svg, symbols_dir), accent)
            try:
                ov = load_overrides().get(symbol_name(svg), {})
                icon = write_icon(theme_ref(theme_name), theme_name, svg, store_dir or store.icons_dir(), ov)
            except (OSError, subprocess.SubprocessError, ValueError) as e:
                raise ApplyError(f"cannot build the icon for {svg}: {e}") from e
            results = set_folder_icons(m, folders, icon, recipe, set_icon)
    except OSError as e:
        if results is None:
            raise
        raise RecordError(results, e) from e
    return results


def apply(a):
    folder = os.path.abspath(os.path.expanduser(a.folder))
    with store.editing() as m:
        _warn(m)
        m.check_writable()                     # fail before anything is built or set
        theme_name, accent = resolve_theme(a)
        theme_dir = theme_ref(theme_name, a.format, a.icons_root)
        svg = find_symbol(a.symbol, a.symbols_dir)
        name = symbol_name(svg)
        recipe = accent and Recipe(recipe_symbol(a.symbol, svg, a.symbols_dir), accent, a.scale, a.align)
        store_dir = os.path.expanduser(a.store or store.icons_dir())
        os.makedirs(store_dir, exist_ok=True)
        ov = {} if a.no_overrides else load_overrides(a.overrides).get(name, {})
        png = write_icon(theme_dir, theme_name, svg, store_dir, ov, a.scale, a.align, a.keep_opacity,
                         a.format, a.size)
        cmd = ["gio", "set", folder, "metadata::custom-icon", "file://" + png]
        print(f"{theme_name}: {name} -> {png}")
        if not recipe:
            print(f"warning: '{theme_name}' is not a Yaru variant, so {store.tilde(folder)} is not recorded "
                  "in the manifest ('list' and 'reset --all' will not see it)", file=sys.stderr)
        elif extra := _not_in_recipe(a):
            print(f"warning: the manifest keeps only symbol, accent, scale and align; not kept: "
                  f"{', '.join(extra)}", file=sys.stderr)
        if a.dry_run:
            print(" ".join(cmd))
            if recipe:
                print(f"would record {store.tilde(folder)} in {m.path}")
            return
        [result] = set_folder_icons(m, [folder], png, recipe)
        if not result.ok:
            sys.exit(f"gio failed: {result.message}")
    print(f"icon set on {folder} (restart Nautilus if it does not update: nautilus -q)")


# ---------------------------------------------------------------- reset
NOT_FOUND = "not found, entry kept"      # FolderResult.message of a folder that does not exist


def unset_folder_icons(manifest, folders, unset_icon=None):
    """Remove the custom icon of each folder, one by one: a failure is reported in that folder's
    FolderResult and does not stop the others. A folder that does not exist fails with NOT_FOUND (it may
    be on a drive that is not mounted). Only folders whose icon was removed lose their manifest entry;
    the caller holds manifest in a store.editing() block, which saves it once at the end.
    unset_icon(folder) raises GioError or OSError on failure; None means gio_unset (looked up at call time)."""
    unset_icon = unset_icon or gio_unset
    results = []
    for folder in folders:
        if not os.path.exists(folder):
            results.append(FolderResult(folder, False, NOT_FOUND))
            continue
        try:
            unset_icon(folder)
        except (GioError, OSError) as e:
            results.append(FolderResult(folder, False, str(e)))
            continue
        manifest.remove(folder)
        results.append(FolderResult(folder, True, "icon reset"))
    return results


def reset_folders(dirs, *, manifest_path=None, unset_icon=None):
    """Give several folders their normal icon again (what `reset --all` does, for these folders): the
    manifest is changed under one lock and saved once, and only folders whose icon was removed lose their
    entry. Returns one FolderResult per folder (duplicates dropped, order kept). Raises store.ManifestError
    (manifest damaged or newer) before any folder is touched, and RecordError when the icons were removed
    but the manifest could not be saved afterwards. unset_icon: see unset_folder_icons."""
    folders = list(dict.fromkeys(map(store.folder_path, dirs)))
    if not folders:
        return []
    results = None                   # set once the icons are removed: an OSError after that is the save's
    try:
        with store.editing(manifest_path) as m:
            m.check_writable()
            results = unset_folder_icons(m, folders, unset_icon)
    except OSError as e:
        if results is None:
            raise
        raise RecordError(results, e) from e
    return results


def reset(a):
    folder = os.path.abspath(os.path.expanduser(a.folder))
    with store.editing() as m:
        _warn(m)
        m.check_writable()
        if not os.path.exists(folder):
            if m.remove(folder):
                print(f"{store.tilde(folder)}: folder not found; removed from the manifest")
                return
            sys.exit(f"{folder}: no such folder")
        [result] = unset_folder_icons(m, [folder])
        if not result.ok:
            sys.exit(f"gio failed: {result.message}")


def reset_all(a):
    """Reset every folder in the manifest. Each one is tried on its own; failures are reported and
    their entries kept, and the exit status is 1 if there was any."""
    with store.editing() as m:
        _warn(m)
        m.check_writable()
        items = m.entries()
        results = unset_folder_icons(m, [e.folder for e in items])
        for r in results:
            label = store.tilde(r.folder)
            if r.ok:
                print(f"ok      {label}")
            elif r.message == NOT_FOUND:
                print(f"FAILED  {label}: not found, entry kept; run 'folder-symbols reset "
                      f"{shell_path(r.folder)}' to forget it")
            else:
                print(f"FAILED  {label}: {r.message}")
        failed = sum(1 for r in results if not r.ok)
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
        plan = store.cleanup_plan(m, a.include_external)
        stale = [e.folder for e in plan.stale]
        if not a.dry_run:
            stale = store.remove_missing(m, stale)
    total, unknown, skipped = plan.total, plan.unknown, plan.skipped
    for folder in stale:
        print(f"{'would remove' if a.dry_run else 'removed '}  {store.tilde(folder)}")
    for e, err in unknown:
        print(f"kept      {store.tilde(e.folder)}: cannot check ({err.strerror or err})")
    if skipped:
        print(f"Skipped {skipped} {'entry' if skipped == 1 else 'entries'} outside ~ (the drive may not be "
              "mounted); use --include-external to check them too")
    if not stale:
        print("Nothing to remove")
    else:
        print(f"{'Would remove' if a.dry_run else 'Removed'} {len(stale)} of {total} entries")


# ---------------------------------------------------------------- list
def apply_command(entry):
    """A ready-to-run command that applies this entry's recipe again (style taken from the system); a
    folder that follows the system accent gets `--accent system`."""
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
    # a following folder shows the system accent of now ("system (orange)"); read only when needed
    system = accents.system_accent() if any(e.recipe.follows_system for e in items) else None
    for e in items:
        r = e.recipe
        opts = " ".join(([f"scale {r.scale:g}"] if r.scale != 1.0 else []) +
                        ([f"align {r.align}"] if r.align != "bbox" else [])) or "-"
        sym = store.tilde(r.symbol) if os.path.isabs(r.symbol) else r.symbol
        accent = (f"{r.accent} ({system})" if system else r.accent) if r.follows_system else r.accent
        rows.append((store.tilde(e.folder), sym, accent, opts,
                     store.icon_status(e.folder, gio_custom_icon)))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + row[4])
