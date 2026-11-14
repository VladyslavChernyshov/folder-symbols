"""PreviewPanel: the right-hand panel with the folder icon for the selected symbol."""
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

from folder_symbols.preview import PreviewError, system_variant

PANEL_WIDTH = 270                        # outer width, as the mockup's .side
PANEL_PADDING = 18
PREVIEW_BOX_HEIGHT = 190                 # outer height, border included (mockup .prevbox, border-box)
PREVIEW_BOX_BORDER = 1
PREVIEW_BOX_RADIUS = 12
PREVIEW_ICON_SIZE = 150

# Only named theme colours. The panel is a faint foreground tint over the window background: slightly
# darker than the gallery on a light theme and slightly lighter on a dark one, as in the mockup. The
# preview box uses the same tokens as the gallery cards.
PANEL_CSS = f"""
.preview-panel {{ background-color: alpha(@window_fg_color, 0.03); padding: {PANEL_PADDING}px; }}
.preview-box {{
  min-height: {PREVIEW_BOX_HEIGHT - 2 * PREVIEW_BOX_BORDER}px;
  background-color: @card_bg_color; border: {PREVIEW_BOX_BORDER}px solid @borders;
  border-radius: {PREVIEW_BOX_RADIUS}px;
}}
"""
_css_loaded = False


def _load_css():
    global _css_loaded
    if _css_loaded:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(PANEL_CSS)          # GTK 4.12
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_loaded = True


class PreviewPanel(Gtk.Box):
    """Shows the plain system folder when no symbol is selected, else the Yaru folder with the symbol,
    built by session (a preview.PreviewSession) in the system's accent and light/dark style."""

    def __init__(self, session, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["preview-panel"],
                         width_request=PANEL_WIDTH, hexpand=False, vexpand=True, **kwargs)
        _load_css()
        self._session = session
        self._symbol = None
        # hexpand centres the image along the box; vexpand would propagate and stretch the box downwards.
        self._image = Gtk.Image(pixel_size=PREVIEW_ICON_SIZE, hexpand=True,
                                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        box = Gtk.Box(css_classes=["preview-box"])
        box.append(self._image)
        self.append(box)
        self._show()
        # Follow the system style while the window is open: a new accent on Ubuntu is a new icon theme.
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self._show())
        Gtk.Settings.get_default().connect("notify::gtk-icon-theme-name", lambda *_: self._show())

    def set_symbol(self, symbol):
        """symbol: a gallery.Symbol, or None."""
        self._symbol = symbol
        self._show()

    def _show(self):
        if self._symbol is not None:
            try:
                variant = system_variant(Adw.StyleManager.get_default().get_dark())
                path = self._session.build(self._symbol.path, variant)
            except PreviewError as e:
                print(f"folder-symbols: {e}", file=sys.stderr)
            else:
                self._image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
                return
        self._image.set_from_icon_name("folder")
