"""PreviewPanel: the sidebar content with the folder icon for the selected symbol."""
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

from folder_symbols import yaru
from folder_symbols.accents import initial_accent, system_accent
from folder_symbols.preview import PreviewError, variant_for
from folder_symbols.gui.accents import AccentPicker

PANEL_PADDING = (6, 18, 18, 18)          # top right bottom left (mockup .side, under the sidebar header)
PREVIEW_BOX_HEIGHT = 190                 # outer height, border included (mockup .prevbox, border-box)
PREVIEW_BOX_BORDER = 1
PREVIEW_BOX_RADIUS = 12
PREVIEW_ICON_SIZE = 150

# Only named theme colours. The panel has no background of its own: it sits in the split view's sidebar,
# which draws the sidebar colour and the border to the gallery. The preview box uses the same tokens as
# the gallery cards.
PANEL_CSS = f"""
.preview-panel {{ padding: {" ".join(f"{v}px" for v in PANEL_PADDING)}; }}
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
    """The Yaru folder with the selected symbol (or without one), built by session (a
    preview.PreviewSession) in the accent chosen below it and the system's light/dark style."""

    def __init__(self, session, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["preview-panel"],
                         hexpand=False, vexpand=True, **kwargs)
        _load_css()
        self._session = session
        self._symbol = None
        self._accent = None
        self._accent_is_default = True      # the accent is the system's default, not recorded or picked
        self._setting_choices = False
        # hexpand centres the image along the box; vexpand would propagate and stretch the box downwards.
        self._image = Gtk.Image(pixel_size=PREVIEW_ICON_SIZE, hexpand=True,
                                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        box = Gtk.Box(css_classes=["preview-box"])
        box.append(self._image)
        self.append(box)
        self._picker = AccentPicker()
        self._picker.connect("notify::accent", self._on_picked)
        self.append(self._picker)
        self.set_initial_accent(None)
        # Follow the system style while the window is open: a new accent on Ubuntu is a new icon theme.
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self._show())
        Gtk.Settings.get_default().connect("notify::gtk-icon-theme-name", lambda *_: self._on_system_theme())

    def set_initial_accent(self, recorded):
        """Select the folders' recorded accent (InitialState.accent), or the system's when there is none,
        and mark the system accent in the picker."""
        self._accent_is_default = recorded not in yaru.accents()
        system = system_accent()
        self._set_choices(initial_accent(recorded, system), system)

    def _set_choices(self, selected, system):
        self._setting_choices = True
        try:
            self._picker.set_choices(selected, system)
        finally:
            self._setting_choices = False
        self.set_accent(self._picker.accent)

    def _on_picked(self, picker, _pspec):
        if not self._setting_choices:
            self._accent_is_default = False
            self.set_accent(picker.accent)

    def _on_system_theme(self):
        """The system accent changed: move the mark, and follow it unless an accent was recorded or picked."""
        system = system_accent()
        self._set_choices(initial_accent(None, system) if self._accent_is_default else self._picker.accent,
                          system)
        self._show()

    def set_accent(self, accent):
        """accent: the accent to preview with, or None for the system's. The light/dark style always
        follows the system."""
        if accent != self._accent:
            self._accent = accent
            self._show()

    def set_symbol(self, symbol):
        """symbol: a gallery.Symbol, or None."""
        self._symbol = symbol
        self._show()

    def _show(self):
        """The folder in the selected accent and the system's light/dark style, with the symbol when one
        is selected; the system's own folder icon if it cannot be built."""
        try:
            variant = variant_for(self._accent, Adw.StyleManager.get_default().get_dark())
            if self._symbol is not None:
                path = self._session.build(self._symbol.path, variant)
            else:
                path = self._session.build_plain(variant)
        except PreviewError as e:
            print(f"folder-symbols: {e}", file=sys.stderr)
            self._image.set_from_icon_name("folder")
        else:
            self._image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
