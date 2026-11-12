"""Setting and removing a folder's custom icon in Nautilus (gio metadata::custom-icon)."""
import os, re, subprocess, sys

from .svg import make_svg
from .symbols import find_symbols, load_overrides
from .yaru import Theme, builtin_themes, compose, find_theme_dir, render_symbol


def current_icon_theme():
    out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip().strip("'")


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

