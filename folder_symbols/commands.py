"""The manifest commands of the command line (apply, reset, reset --all, prune, list): they print and stop
with sys.exit; the work is done by apply.py, the library the window uses too."""
import contextlib, os, shlex, sys

from . import accents, store, yaru
from . import apply as ap
from .apply import (NOT_FOUND, ApplyError, lookup_symbol, recipe_symbol, set_folder_icons, theme_ref,
                    unset_folder_icons, write_icon)
from .store import SYSTEM_ACCENT, Recipe
from .symbols import load_overrides, symbol_name
from .yaru import DEFAULT_SIZE


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
def find_symbol(symbol, symbols_dir):
    try:
        return lookup_symbol(symbol, symbols_dir)
    except ApplyError as e:
        sys.exit(str(e))


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


def _not_in_recipe(a):
    """apply options that change the icon but are not part of the recipe."""
    return [opt for opt, used in (("--format png", a.format == "png"), ("--size", a.size != DEFAULT_SIZE),
                                  ("--keep-opacity", a.keep_opacity), ("--no-overrides", a.no_overrides),
                                  ("--overrides", a.overrides is not None),
                                  ("--icons-root", a.icons_root is not None)) if used]


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
                     store.icon_status(e.folder, ap.gio_custom_icon)))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + row[4])
