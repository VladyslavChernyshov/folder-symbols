"""AccentPicker: the "Accent" heading, a grid of colour swatches (one radio group) and the "system accent"
legend, under the folder preview."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GObject, Gtk

from folder_symbols import yaru
from folder_symbols.accents import picker_accents, swatch_colors, swatch_tooltip

SWATCH_SIZE = 26                         # mockup .sw i
SWATCH_COLUMNS = 6                       # 12 accents in 2 rows; the columns share the width equally
ROW_GAP = 8                              # mockup .sw gap
RING_WIDTH = 3                           # selected swatch (mockup .sw i.on outline)
RING_OFFSET = 2
HEADING_MARGINS = (16, 6)                # top, bottom (mockup .lbl)
LEGEND_MARGIN_TOP = 10                   # mockup .note
DOT_RADIUS = 3                           # the system dot: 8 px across with its 1 px ring (mockup .sw i u)

# The swatch is the check button's radio node, so GTK's own radio group does the selection and keyboard
# focus; the theme's bullet is not drawn. Only named theme colours for the marks: the selected ring is the
# foreground colour, the focus ring is the theme's own (moved outside the swatch), and the system dot is
# the accent foreground on a thin shade ring. The fills are the only literal colours, generated from the
# folder colours in assets/themes.json (light, and under .dark the dark variant's).
_DOT = (f"radial-gradient(circle, @accent_fg_color {DOT_RADIUS}px, @shade_color {DOT_RADIUS}px "
        f"{DOT_RADIUS + 1}px, transparent {DOT_RADIUS + 1}px)")
BASE_CSS = f"""
checkbutton.accent-swatch {{ padding: 0; }}
checkbutton.accent-swatch > radio {{
  min-width: {SWATCH_SIZE}px; min-height: {SWATCH_SIZE}px; padding: 0; margin: 0; border: none;
  border-radius: 50%; box-shadow: none; -gtk-icon-source: none; background-image: none;
}}
checkbutton.accent-swatch > radio:checked {{
  outline: {RING_WIDTH}px solid @window_fg_color; outline-offset: {RING_OFFSET}px;
}}
checkbutton.accent-swatch:focus:focus-visible {{ outline-offset: {RING_OFFSET}px; }}
checkbutton.accent-swatch.system > radio {{ background-image: {_DOT}; }}
.accent-legend-dot {{
  min-width: {2 * DOT_RADIUS + 2}px; min-height: {2 * DOT_RADIUS + 2}px; border-radius: 50%;
  background-image: {_DOT};
}}
"""
_css_loaded = False


def _accent_css():
    rules = []
    for accent in yaru.accents():
        light, dark = swatch_colors(accent)
        rules.append(f"checkbutton.accent-{accent} > radio {{ background-color: {light}; }}")
        rules.append(f".accent-picker.dark checkbutton.accent-{accent} > radio {{ background-color: {dark}; }}")
    return "\n".join(rules)


def _load_css():
    global _css_loaded
    if _css_loaded:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(BASE_CSS + _accent_css())   # GTK 4.12
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_loaded = True


class AccentPicker(Gtk.Box):
    """The property accent holds the selected accent name (as the manifest records it)."""

    accent = GObject.Property(type=str, default="")

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["accent-picker"], **kwargs)
        _load_css()
        self._buttons = {}
        self._choices = None
        self.append(Gtk.Label(label="Accent", xalign=0, css_classes=["caption-heading", "dim-label"],
                              margin_top=HEADING_MARGINS[0], margin_bottom=HEADING_MARGINS[1]))
        self._grid = Gtk.Grid(column_homogeneous=True, row_spacing=ROW_GAP)
        self.append(self._grid)
        self._legend = Gtk.Box(spacing=6, margin_top=LEGEND_MARGIN_TOP, visible=False)
        self._legend.append(Gtk.Box(css_classes=["accent-legend-dot"], valign=Gtk.Align.CENTER))
        self._legend.append(Gtk.Label(label="system accent", css_classes=["caption", "dim-label"]))
        self.append(self._legend)
        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_: self._follow_style())
        self._follow_style()

    def _follow_style(self):
        if Adw.StyleManager.get_default().get_dark():
            self.add_css_class("dark")
        else:
            self.remove_css_class("dark")

    def set_choices(self, selected, system):
        """Show the swatches for these accents (MATE only when selected or system is mate), mark the
        system accent (None: no mark, e.g. a non-Yaru theme) and select `selected`."""
        choices = picker_accents(selected, system)
        if choices != self._choices:
            self._build(choices)
        for name, button in self._buttons.items():
            is_system = name == system
            if is_system:
                button.add_css_class("system")
            else:
                button.remove_css_class("system")
            tip = swatch_tooltip(name, is_system)
            button.set_tooltip_text(tip)
            button.update_property([Gtk.AccessibleProperty.LABEL], [tip])
        self._legend.set_visible(system in self._buttons)
        if selected in self._buttons:
            self._buttons[selected].set_active(True)

    def _build(self, choices):
        while (child := self._grid.get_first_child()) is not None:
            self._grid.remove(child)
        self._buttons, self._choices = {}, choices
        columns = max(SWATCH_COLUMNS, (len(choices) + 1) // 2)
        group = None
        for i, name in enumerate(choices):
            button = Gtk.CheckButton(css_classes=["accent-swatch", f"accent-{name}"], halign=Gtk.Align.CENTER)
            button.set_group(group)
            group = group or button
            button.connect("toggled", self._on_toggled, name)
            self._grid.attach(button, i % columns, i // columns, 1, 1)
            self._buttons[name] = button

    def _on_toggled(self, button, name):
        if button.get_active() and self.accent != name:
            self.accent = name
