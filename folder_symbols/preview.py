"""The GUI's folder preview: the Yaru folder with a symbol on it, built as an SVG in a per-session temporary
directory (no GTK). It never touches the manifest, the icon store, gio or any folder."""
import os, subprocess, tempfile

from . import yaru
from .svg import make_plain_svg, make_svg_for
from .symbols import load_overrides, symbol_name


class PreviewError(Exception):
    pass


def resolve_variant(icon_theme, dark):
    """The built-in Yaru variant to preview with: icon_theme itself when it is one, else the default
    accent (plain Yaru) in the given light/dark style, so a non-Yaru system still gets a preview."""
    if yaru.parse_variant(icon_theme) and icon_theme in yaru.builtin_themes():
        return icon_theme
    return yaru.variant_name("orange", dark)


def system_variant(dark):
    """resolve_variant for the current icon theme (the same detection as `apply`). dark is the style to
    fall back to when that theme is not Yaru or cannot be read."""
    try:
        current = yaru.current_icon_theme()
    except (OSError, subprocess.CalledProcessError):
        current = None
    return resolve_variant(current, dark)


def variant_for(accent, dark):
    """The built-in variant to preview with: the given accent (e.g. a folder's recorded one) in the given
    light/dark style when it is a known Yaru accent, else system_variant(dark)."""
    if accent in yaru.accents():
        return yaru.variant_name(accent, dark)
    return system_variant(dark)


class PreviewSession:
    """Owns a temporary directory for preview SVGs, removed by close() (or at interpreter exit)."""

    def __init__(self, base_dir=None):
        self._tmp = tempfile.TemporaryDirectory(prefix="folder-symbols-preview-", dir=base_dir)
        self.dir = self._tmp.name
        self._overrides = None

    def build(self, symbol_svg, variant):
        """Path of an SVG of the folder in this built-in variant with the symbol on it, with the symbol's
        overrides applied as in `apply`; None (and nothing built) when symbol_svg is None."""
        if symbol_svg is None:
            return None
        if variant not in yaru.builtin_themes():
            raise PreviewError(f"unknown theme variant {variant!r}")
        if self._overrides is None:
            try:
                self._overrides = load_overrides()
            except (OSError, ValueError) as e:
                raise PreviewError(f"cannot read overrides: {e}") from e
        name = symbol_name(symbol_svg)
        path = os.path.join(self.dir, f"{variant}-{name}.svg")
        try:
            text = make_svg_for(variant, symbol_svg, self._overrides.get(name, {}))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError) as e:
            raise PreviewError(f"cannot build a preview of {symbol_svg}: {e}") from e
        return path

    def build_plain(self, variant):
        """Path of an SVG of the plain folder (no symbol) in this built-in variant."""
        if variant not in yaru.builtin_themes():
            raise PreviewError(f"unknown theme variant {variant!r}")
        path = os.path.join(self.dir, f"{variant}-plain.svg")
        try:
            text = make_plain_svg(variant)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except (OSError, ValueError) as e:
            raise PreviewError(f"cannot build a preview of the plain folder: {e}") from e
        return path

    def close(self):
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
