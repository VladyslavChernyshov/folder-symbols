"""PreviewPanel: the sidebar content with the folder icon for the selected symbol."""
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

from folder_symbols.accents import initial_choice, panel_choice, pick, set_follow, system_accent, system_changed
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
    preview.PreviewSession) in the accent chosen below it and the system's light/dark style. The accent
    state (follow the system or a pinned swatch) is an accents.AccentChoice; current_choice() tells what
    would be applied."""

    def __init__(self, session, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["preview-panel"],
                         hexpand=False, vexpand=True, **kwargs)
        _load_css()
        self._session = session
        self._symbol = None
        self._choice = None
        self._drawn_dark = Adw.StyleManager.get_default().get_dark()
        # hexpand centres the image along the box; vexpand would propagate and stretch the box downwards.
        self._image = Gtk.Image(pixel_size=PREVIEW_ICON_SIZE, hexpand=True,
                                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        box = Gtk.Box(css_classes=["preview-box"])
        box.append(self._image)
        self.append(box)
        self._picker = AccentPicker()
        self._picker.connect("picked", lambda _p, accent: self._update(pick(self._choice, accent)))
        self._picker.connect("follow-toggled", lambda _p, on: self._update(set_follow(self._choice, on)))
        self.append(self._picker)
        self.set_initial_accent(None)
        # Follow the system style while the window is open: a new accent on Ubuntu is a new icon theme.
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self._show())
        Gtk.Settings.get_default().connect("notify::gtk-icon-theme-name", lambda *_: self._on_system_theme())

    def set_initial_accent(self, recorded):
        """Start from the folders' recorded accent (InitialState.accent): "system" or none follows the
        system accent (switch on), a concrete accent is pinned (switch off, that swatch)."""
        self._update(initial_choice(recorded, system_accent()))

    def _on_system_theme(self):
        """The system accent changed: the mark moves, and a following choice moves with it."""
        self._update(system_changed(self._choice, system_accent()))

    def _update(self, choice):
        """Show this AccentChoice in the picker (programmatically: no signal comes back) and redraw."""
        self._choice = choice
        self._picker.set_choices(choice.selected, choice.system)
        self._picker.set_follow(choice.follow, choice.follow_available)
        self._show()

    def current_choice(self):
        """An accents.PanelChoice: what Apply would pass to apply_folders (accent, system_accent), the
        light/dark style the preview was last drawn in, and the selected symbol (None: nothing to apply)."""
        return panel_choice(self._choice, self._drawn_dark, self._symbol)

    def set_symbol(self, symbol):
        """symbol: a gallery.Symbol, or None."""
        self._symbol = symbol
        self._show()

    def _show(self):
        """The folder in the selected accent and the system's light/dark style, with the symbol when one
        is selected; the system's own folder icon if it cannot be built."""
        if self._choice is None:
            return
        self._drawn_dark = dark = Adw.StyleManager.get_default().get_dark()
        try:
            variant = variant_for(self._choice.selected, dark)
            if self._symbol is not None:
                path = self._session.build(self._symbol.path, variant)
            else:
                path = self._session.build_plain(variant)
        except PreviewError as e:
            print(f"folder-symbols: {e}", file=sys.stderr)
            self._image.set_from_icon_name("folder")
        else:
            self._image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
