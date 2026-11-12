"""Command line: the argument parsers of every command and main()."""
import argparse, os, sys

from . import __version__
from .apply import apply, reset
from .batch import batch
from .svg import make_svg
from .symbols import load_overrides
from .yaru import Theme, builtin_themes, compose, render_symbol, theme_ref_kind


def one(a):
    name = os.path.basename(a.symbol_svg).replace("-symbolic.svg", "").replace(".svg", "")
    ov = {} if a.no_overrides else load_overrides(a.overrides).get(name, {})
    if a.output_png.lower().endswith(".svg"):
        if not theme_ref_kind(a.theme_dir):
            sys.exit(f"theme '{a.theme_dir}' not found: give a theme directory or a built-in name "
                     f"({', '.join(sorted(builtin_themes()))})")
        with open(a.output_png, "w", encoding="utf-8") as f:
            f.write(make_svg(a.theme_dir, a.symbol_svg, a.scale * ov.get("scale", 1.0),
                             ov.get("align", a.align), a.dx + ov.get("dx", 0.0),
                             a.dy + ov.get("dy", 0.0), not a.keep_opacity))
        return
    theme = Theme(a.theme_dir, (a.size,))
    sym = render_symbol(a.symbol_svg, a.size, a.scale * ov.get("scale", 1.0), not a.keep_opacity)
    compose(theme, sym, a.size, ov.get("align", a.align), a.dx + ov.get("dx", 0.0),
            a.dy + ov.get("dy", 0.0)).save(a.output_png, optimize=True)


OVERVIEW = """\
folder-symbols - put a symbol on Ubuntu's Yaru folder icon, in Yaru's own embossed style.

Takes any symbolic icon (*-symbolic.svg, e.g. the ~1300 that ship in
/usr/share/icons/Yaru/scalable) and composites it onto the folder icon of any Yaru colour
variant (light/dark, every accent, MATE), either as a PNG or as a scalable SVG. The result looks
like the folder icons Yaru draws itself (a symbol pressed into the front panel). Colours are not
hard-coded: they are measured from the theme's own folder.png, so every variant works.

Commands:
  apply   FOLDER SYMBOL      build a scalable (SVG) icon for one folder and set it in Nautilus (Files)
  reset   FOLDER             remove a custom icon set with 'apply'
  batch   --out DIR          generate icons for many symbols x themes x sizes at once
  (none)  THEME_DIR SYMBOL.svg OUT.png|OUT.svg
                             compose a single icon file, no folder is touched

Run 'folder-symbols COMMAND --help' for one command only. Examples:
  folder-symbols apply ~/Music community
  folder-symbols reset ~/Music
  folder-symbols /usr/share/icons/Yaru-dark /usr/share/icons/Yaru/scalable/actions/share-symbolic.svg share.svg
  folder-symbols batch --out dist --themes Yaru,Yaru-dark --sizes svg,512

Requires: python3, python3-pil, python3-numpy, python3-scipy, rsvg-convert (librsvg2-bin).
Licence: script MIT; generated icons CC BY-SA 4.0 (derived from Yaru), see NOTICE.md.
"""

_FMT = argparse.HelpFormatter
_SIZES = "512 (= 256x256@2x, default), 256 (= 256x256) or a Yaru size directory such as 48x48 or 24x24@2x"


def _common(p, batch=False):
    """Options shared by every command that renders a symbol."""
    p.add_argument("--scale", type=float, default=1.0, metavar="X",
                   help="multiply the symbol's size by X (1.0 = Yaru's size; the symbol is still "
                        "shrunk to fit the folder's front panel). Default: 1.0")
    p.add_argument("--align", choices=("bbox", "mass", "yaru"), default="bbox",
                   help="how the symbol is centred on the front panel. bbox: centre of its visible "
                        "bounding box (default); mass: centre of mass; yaru: the fixed position "
                        "Yaru itself uses")
    p.add_argument("--keep-opacity", action="store_true",
                   help="keep the translucent parts of a symbol as in its SVG. By default every "
                        "part is drawn fully opaque so the symbol looks uniform")
    p.add_argument("--overrides", default=None, metavar="FILE",
                   help="JSON file with per-symbol exceptions {name: {scale, dx, dy, align}}. "
                        "Default: overrides.json next to this script")


def parser_compose():
    p = argparse.ArgumentParser(
        prog="folder-symbols", formatter_class=_FMT,
        usage="folder-symbols THEME_DIR SYMBOL_SVG OUTPUT [options]",
        description="Compose one symbol onto one theme's folder icon and write it to a file. The "
                    "output type follows the extension: .png (raster) or .svg (scalable, one "
                    "self-contained file). No folder or setting is changed.")
    p.add_argument("theme_dir", help="icon theme directory with the PNG folders, e.g. "
                   "/usr/share/icons/Yaru-dark (or Yaru-purple, Yaru-mate-dark, ...). For .svg output "
                   "a plain built-in variant name such as Yaru-dark works too, with no theme installed")
    p.add_argument("symbol_svg", help="the symbolic icon to put on the folder, e.g. "
                   "/usr/share/icons/Yaru/scalable/actions/share-symbolic.svg")
    p.add_argument("output_png", metavar="OUTPUT", help="file to write, ending in .png or .svg")
    p.add_argument("--size", default="512", metavar="SIZE",
                   help="PNG only: icon size, one of " + _SIZES + ". Ignored for .svg")
    _common(p)
    p.add_argument("--dx", type=float, default=0.0, metavar="F",
                   help="move the symbol right by F x icon size (negative = left). Default: 0")
    p.add_argument("--dy", type=float, default=0.0, metavar="F",
                   help="move the symbol down by F x icon size (negative = up). Default: 0")
    p.add_argument("--no-overrides", action="store_true", help="ignore overrides.json completely")
    return p


def parser_apply():
    p = argparse.ArgumentParser(
        prog="folder-symbols apply", formatter_class=_FMT,
        usage="folder-symbols apply FOLDER SYMBOL [options]",
        description="Build an icon for the given folder (scalable SVG by default, stored under --store) and set it as "
                    "the folder's custom icon in Nautilus via 'gio set ... metadata::custom-icon'. "
                    "The icon uses the colours of the GNOME icon theme that is active now, so "
                    "re-run it after changing theme or accent colour.")
    p.add_argument("apply", help=argparse.SUPPRESS)
    p.add_argument("folder", help="the folder that gets the icon, e.g. ~/Music")
    p.add_argument("symbol", help="symbol name, e.g. community (the file name without "
                   "'-symbolic.svg', searched in --symbols-dir), or a path to a *-symbolic.svg")
    p.add_argument("--theme", default=None, metavar="NAME",
                   help="Yaru theme variant to take colours from, e.g. Yaru-purple-dark. "
                        "Default: the current GNOME icon theme (gsettings)")
    p.add_argument("--icons-root", default=None, metavar="DIR",
                   help="measure the theme from the PNG folders in this directory instead of using "
                        "the built-in data (SVG), and look here first for PNG themes (then "
                        "~/.local/share/icons and /usr/share/icons). Default: built-in data for "
                        "SVG, installed themes for PNG")
    p.add_argument("--symbols-dir", default="/usr/share/icons/Yaru/scalable", metavar="DIR",
                   help="where symbol names are looked up. Default: /usr/share/icons/Yaru/scalable")
    p.add_argument("--store", default="~/.local/share/folder-icons", metavar="DIR",
                   help="where the generated icon file is kept; Nautilus reads it from there, so do not "
                        "delete it. Default: ~/.local/share/folder-icons")
    p.add_argument("--format", choices=("svg", "png"), default="svg",
                   help="svg: one scalable file, sharp at any size (default); png: a raster icon, "
                        "see --size")
    p.add_argument("--size", default="512", metavar="SIZE",
                   help="PNG only (--format png): icon size, one of " + _SIZES + ". Nautilus scales it down")
    _common(p)
    p.add_argument("--no-overrides", action="store_true", help="ignore overrides.json completely")
    p.add_argument("--dry-run", action="store_true",
                   help="build the icon file and print the gio command, but do not run it")
    return p


def parser_reset():
    p = argparse.ArgumentParser(
        prog="folder-symbols reset", formatter_class=_FMT,
        usage="folder-symbols reset FOLDER",
        description="Remove the custom icon of a folder (gio set -t unset ... metadata::custom-icon), "
                    "so Nautilus shows the theme's normal folder again. The generated file is not deleted.")
    p.add_argument("reset", help=argparse.SUPPRESS)
    p.add_argument("folder", help="the folder to restore, e.g. ~/Music")
    return p


def parser_batch():
    p = argparse.ArgumentParser(
        prog="folder-symbols batch", formatter_class=_FMT,
        usage="folder-symbols batch --out DIR [options]",
        description="Generate icons for many symbols and many theme variants at once, in parallel. "
                    "Output layout: OUT/<theme>/scalable/<symbol>.svg for SVGs and "
                    "OUT/<theme>/<size>/<symbol>.png for PNGs. 1323 symbols x 26 themes as SVG "
                    "take under a minute.")
    p.add_argument("batch", help=argparse.SUPPRESS)
    p.add_argument("--out", required=True, metavar="DIR", help="directory to write the icon sets into")
    p.add_argument("--icons-root", default=None, metavar="DIR",
                   help="directory holding the Yaru* theme directories (installed themes, or "
                        "yaru/src/icons from Yaru's source tree). Needed for PNG output (default "
                        "/usr/share/icons); with --sizes svg and no --icons-root the built-in data "
                        "in assets/themes.json is used and no Yaru theme has to be installed. "
                        "Giving it measures the themes from these directories instead")
    p.add_argument("--symbols-dir", default="/usr/share/icons/Yaru/scalable", metavar="DIR",
                   help="directory searched recursively for *-symbolic.svg. "
                        "Default: /usr/share/icons/Yaru/scalable")
    p.add_argument("--themes", default="all", metavar="LIST",
                   help="'all' (every Yaru* theme found, default) or a comma-separated list, "
                        "e.g. Yaru,Yaru-dark")
    p.add_argument("--sizes", default="512,256", metavar="LIST",
                   help="comma-separated outputs: svg (scalable), 512, 256, or Yaru size directories "
                        "(24x24, 48x48@2x, ...); or 'all' = every PNG size that carries a symbol "
                        "(all except the two 16 px ones, where Yaru draws none). "
                        "Example: svg,512. Default: 512,256")
    p.add_argument("--only", default=None, metavar="REGEX",
                   help="only symbols whose name matches this regular expression, e.g. '^(share|folder)'")
    p.add_argument("--jobs", type=int, default=os.cpu_count(), metavar="N",
                   help="parallel worker processes. Default: number of CPUs")
    _common(p, batch=True)
    p.add_argument("--skip-existing", action="store_true",
                   help="do not regenerate files that already exist (resume an interrupted run)")
    return p


def main(argv):
    if argv and argv[0] in ("-V", "--version"):
        print(f"folder-symbols {__version__}")
        return
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(OVERVIEW)
        for name, mk in (("COMPOSE ONE FILE", parser_compose), ("apply", parser_apply),
                         ("reset", parser_reset), ("batch", parser_batch)):
            print("=" * 78 + f"\n{name}\n" + "=" * 78)
            print(mk().format_help())
        return
    cmd = argv[0]
    if cmd == "reset":
        reset(parser_reset().parse_args(argv))
    elif cmd == "apply":
        apply(parser_apply().parse_args(argv))
    elif cmd == "batch":
        batch(parser_batch().parse_args(argv))
    else:
        one(parser_compose().parse_args(argv))

