"""AccentPicker: the "Accent" heading, a grid of colour swatches (one radio group) and the "Follow system
accent" row (the mini system swatch that marks the system accent, the label and a switch), under the folder
preview."""
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
LEGEND_MARGIN_TOP = 10                   # mockup .note (now the "Follow system accent" row)
FOLLOW_LABEL = "Follow system accent"
FOLLOW_TOOLTIP = "Keep the folder in the system accent, instead of the colour chosen here"
NO_FOLLOW_TOOLTIP = "The system icon theme is not Yaru, so there is no system accent to follow"
DOT_RADIUS = 3                           # the system dot: 8 px across with its 1 px ring (mockup .sw i u)
LEGEND_SIZE = 12                         # the legend marker: a miniature system swatch
LEGEND_DOT_RADIUS = 2                    # its inner dot, 4 px across

# The swatch is the check button's radio node, so GTK's own radio group does the selection and keyboard
# focus; the theme's bullet is not drawn. Only named theme colours for the marks: the selected ring is the
# foreground colour, the focus ring is the theme's own (moved outside the swatch), and the system dot is
# the accent foreground on a thin shade ring. The legend marker is a miniature system swatch in the GNOME
# accent (@accent_bg_color with an @accent_fg_color dot), so it may differ slightly from the swatch. The
# fills are the only literal colours, generated from the folder colours in assets/themes.json (light, and
# under .dark the dark variant's).
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
  min-width: {LEGEND_SIZE}px; min-height: {LEGEND_SIZE}px; border-radius: 50%;
  background-color: @accent_bg_color;
  background-image: radial-gradient(circle, @accent_fg_color {LEGEND_DOT_RADIUS}px,
                                    transparent {LEGEND_DOT_RADIUS}px);
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
    """The property accent holds the selected accent name (as the manifest records it). The signals are
    emitted for the user's own actions only, never for set_choices() or set_follow(): picked(accent) for a
    click (or Space, or an arrow key) on any swatch, also the one already selected; follow-toggled(on) for
    the switch or a click on its row."""

    accent = GObject.Property(type=str, default="")
    __gsignals__ = {
        "picked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "follow-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["accent-picker"], **kwargs)
        _load_css()
        self._buttons = {}
        self._choices = None
        self._programmatic = False
        self._pressed_selected = None        # the swatch that was already selected when it was pressed
        self.append(Gtk.Label(label="Accent", xalign=0, css_classes=["caption-heading", "dim-label"],
                              margin_top=HEADING_MARGINS[0], margin_bottom=HEADING_MARGINS[1]))
        self._grid = Gtk.Grid(column_homogeneous=True, row_spacing=ROW_GAP)
        self.append(self._grid)
        # One row like a GNOME Settings row: the mini system swatch (the legend of the swatch dot), the
        # label and the switch; a click anywhere on it toggles the switch, which is the only tab stop.
        self._follow_row = Gtk.Box(spacing=6, margin_top=LEGEND_MARGIN_TOP)
        self._marker = Gtk.Box(css_classes=["accent-legend-dot"], valign=Gtk.Align.CENTER, visible=False)
        self._follow_row.append(self._marker)
        self._follow_row.append(Gtk.Label(label=FOLLOW_LABEL, xalign=0, hexpand=True,
                                          css_classes=["caption", "dim-label"]))
        self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._switch.update_property([Gtk.AccessibleProperty.LABEL], [FOLLOW_LABEL])
        self._switch.connect("notify::active", self._on_switch)
        self._follow_row.append(self._switch)
        row_click = Gtk.GestureClick()
        row_click.connect("released", self._on_row_click)
        self._follow_row.add_controller(row_click)
        self.append(self._follow_row)
        self.set_follow(False, False)
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
        self._programmatic = True
        try:
            self._set_choices(selected, system)
        finally:
            self._programmatic = False

    def _set_choices(self, selected, system):
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
        self._marker.set_visible(system in self._buttons)
        if selected in self._buttons:
            self._buttons[selected].set_active(True)

    def set_follow(self, active, available):
        """Show the switch on or off; without a system accent (available False) it is insensitive and says
        why in its tooltip."""
        self._programmatic = True
        try:
            self._switch.set_active(active and available)
        finally:
            self._programmatic = False
        self._follow_row.set_sensitive(available)
        tip = FOLLOW_TOOLTIP if available else NO_FOLLOW_TOOLTIP
        self._follow_row.set_tooltip_text(tip)
        self._switch.update_property([Gtk.AccessibleProperty.DESCRIPTION], [tip])

    def _on_switch(self, switch, _pspec):
        if not self._programmatic:
            self.emit("follow-toggled", switch.get_active())

    def _on_row_click(self, gesture, _n, x, y):
        """A click on the row but not on the switch (which handles its own) toggles the switch."""
        hit = self._follow_row.pick(x, y, Gtk.PickFlags.DEFAULT)
        while hit is not None and hit is not self._follow_row:
            if hit is self._switch:
                return
            hit = hit.get_parent()
        if self._switch.get_sensitive() and self._follow_row.get_sensitive():
            self._switch.set_active(not self._switch.get_active())     # emits follow-toggled

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
            # GTK does not toggle a radio that is already active, so a click or Space on the selected
            # swatch is caught here: the press records whether it was selected, the release picks it.
            click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
            click.connect("pressed", self._on_swatch_pressed, name)
            click.connect("released", self._on_swatch_released, name)
            button.add_controller(click)
            button.connect("activate", lambda b, n=name: b.get_active() and self._picked(n))
            self._grid.attach(button, i % columns, i // columns, 1, 1)
            self._buttons[name] = button

    def _on_toggled(self, button, name):
        if button.get_active():
            if self.accent != name:
                self.accent = name
            self._picked(name)

    def _on_swatch_pressed(self, _gesture, _n, _x, _y, name):
        self._pressed_selected = self._buttons[name].get_active() and name

    def _on_swatch_released(self, _gesture, _n, _x, _y, name):
        if self._pressed_selected == name:
            self._picked(name)
        self._pressed_selected = None

    def _picked(self, name):
        if not self._programmatic:
            self.emit("picked", name)
