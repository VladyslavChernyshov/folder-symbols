"""Scenario-side helpers of the GUI harness for the gallery and the preview panel (scenarios B, C and D).

They find the widgets that have no name of their own by public type and CSS class under the named
preview-panel and gallery-grid, read the accent picker's state, and emulate input. GTK is not imported at
module level: the parent imports the scenario modules only for their metadata, and GTK comes from the driver
(d.Gtk, d.GLib).

Input is emulated at signal level. GTK 4 has no public way to inject real pointer or key events, so GTK's own
gesture recognition is not exercised:
- a click on a grid cell is the action "list.select-item" (position, no Ctrl, no Shift), which GTK's list
  item click triggers;
- a click on an accent swatch: the app's own capture-phase Gtk.GestureClick gets "pressed", then
  "released". Then GTK's check-button rule is applied with set_active: toggle, unless the button is already
  active in its radio group. GTK's own click gesture also runs in the capture phase, after the app's (GTK
  runs controllers in the order observe_controllers() lists them, the last added first), and toggles on
  release: the same order as here;
- a click on the "Follow system accent" row: the row's Gtk.GestureClick gets "pressed" and "released" at that
  point (the app's handler picks the widget there itself);
- the switch is Gtk.Switch.activate() (Space or Enter; it toggles after its animation); the split button's main part is
  Adw.SplitButton.activate();
- the arrow keys are the window's "move-focus" signal, which is the arrow keys' key binding.

Every fallback writes an info line."""
from registry import Fail

# Literal copies from folder_symbols/gui/accents.py and folder_symbols/accents.py: a changed text or order
# in the application shows up as a difference.
FOLLOW_LABEL = "Follow system accent"
FOLLOW_TOOLTIP = "Keep the folder in the system accent, instead of the colour chosen here"
NO_FOLLOW_TOOLTIP = "The system icon theme is not Yaru, so there is no system accent to follow"
PICKER_ORDER = ["orange", "blue", "purple", "red", "viridian", "magenta", "prussiangreen", "olive", "sage",
                "bark", "wartybrown", "yellow"]
WITH_MATE = PICKER_ORDER + ["mate"]


def wait_quietly(d, condition, what, timeout=5):
    """wait_until, but a timeout of this wait only returns (the checks after it record what did not happen),
    so a broken behaviour FAILs by assertion; the watchdog still ends the scenario."""
    try:
        d.wait_until(condition, what, timeout=timeout)
        return True
    except Fail:
        if d.watchdog_fired:
            raise
        return False


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def by_class(d, css_class, scope, mapped=True):
    """Every widget under scope with this CSS class (mapped ones only unless mapped is None)."""
    return [w for w in walk(scope) if w.has_css_class(css_class) and (mapped is None or w.get_mapped() == mapped)]


def by_type(d, gtype, scope, mapped=True):
    return [w for w in walk(scope) if isinstance(w, gtype) and (mapped is None or w.get_mapped() == mapped)]


def one(d, widgets, what):
    if len(widgets) != 1:
        raise Fail(f"step {d.step_no}: expected exactly one {what}, found {len(widgets)}")
    return widgets[0]


def controllers(widget):
    model = widget.observe_controllers()
    return [model.get_item(i) for i in range(model.get_n_items())]


# ------------------------------------------------------------- the accent picker
def panel(d):
    return d.find_one("preview-panel")


def picker(d):
    return one(d, by_class(d, "accent-picker", panel(d)), "mapped .accent-picker")


def swatches(d):
    """[(accent, Gtk.CheckButton)] of the mapped swatches, in the picker's order."""
    found = []
    for button in by_class(d, "accent-swatch", panel(d)):
        names = [c[len("accent-"):] for c in button.get_css_classes()
                 if c.startswith("accent-") and c != "accent-swatch"]
        if len(names) != 1:
            raise Fail(f"step {d.step_no}: a swatch with accent classes {names}")
        found.append((names[0], button))
    return found


def swatch(d, name):
    return one(d, [b for n, b in swatches(d) if n == name], f"mapped swatch {name!r}")


def follow_widgets(d):
    """(switch, row, label, marker) of the "Follow system accent" row."""
    switch = one(d, by_type(d, d.Gtk.Switch, panel(d)), "mapped Gtk.Switch in the preview panel")
    row = switch.get_parent()
    label = one(d, [w for w in by_type(d, d.Gtk.Label, row, mapped=None) if w.get_label() == FOLLOW_LABEL],
                f"label {FOLLOW_LABEL!r} in the switch's row")
    marker = one(d, by_class(d, "accent-legend-dot", row, mapped=None), ".accent-legend-dot in the switch's row")
    return switch, row, label, marker


def accent_state(d):
    sw = swatches(d)
    switch, row, _label, marker = follow_widgets(d)
    return {"count": len(sw), "order": [n for n, _ in sw], "selected": [n for n, b in sw if b.get_active()],
            "system": [n for n, b in sw if b.has_css_class("system")], "switch": switch.get_active(),
            "row_sensitive": row.get_sensitive(), "row_tooltip": row.get_tooltip_text(),
            "marker": marker.get_visible(), "dark": picker(d).has_css_class("dark")}


def check_accents(d, **expected):
    """One check per given key of accent_state."""
    state = accent_state(d)
    for key, value in expected.items():
        d.check(f"accent picker: {key.replace('_', ' ')}", state[key], value)


def choice(d):
    """(accent, system_accent) that Apply would pass to apply_folders."""
    c = panel(d).current_choice()
    return c.accent, c.system_accent


def capture_clicks(d, widget):
    Gtk = d.Gtk
    return [c for c in controllers(widget) if isinstance(c, Gtk.GestureClick)
            and c.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE]


def app_swatch_gesture(d, button, name):
    """The app's own capture-phase Gtk.GestureClick on a swatch. A Gtk.CheckButton has capture-phase click
    gestures of its own (one on GTK 4.22, counted here on a new grouped check button). The app adds its
    gesture later, and observe_controllers() lists the controllers added last first (checked on GTK 4.22 with
    a named gesture), so it is the first one. FAIL unless the swatch has exactly one more than a new check
    button."""
    Gtk = d.Gtk
    first = Gtk.CheckButton()
    fresh = Gtk.CheckButton()
    fresh.set_group(first)
    own = len(capture_clicks(d, fresh))
    found = capture_clicks(d, button)
    if len(found) != own + 1:
        raise Fail(f"step {d.step_no}: the swatch {name!r} has {len(found)} capture-phase click gestures, a new "
                   f"check button {own}: expected exactly one added by the app")
    return found[0]


def click_swatch(d, name):
    """A primary click on the swatch, emulated (see the module docstring)."""
    button = swatch(d, name)
    gesture = app_swatch_gesture(d, button, name)
    x, y = button.get_width() / 2, button.get_height() / 2
    gesture.emit("pressed", 1, x, y)
    gesture.emit("released", 1, x, y)
    if not button.get_active():          # all swatches are one radio group: an active one stays active
        button.set_active(True)


def click_row(d, target):
    """A primary click on the "Follow system accent" row at the centre of target ("label" or "switch"),
    through the row's own Gtk.GestureClick."""
    switch, row, label, _marker = follow_widgets(d)
    widget = label if target == "label" else switch
    gesture = one(d, [c for c in controllers(row) if isinstance(c, d.Gtk.GestureClick)],
                  "Gtk.GestureClick on the switch's row")
    ok, rect = widget.compute_bounds(row)
    d.require(ok, f"the bounds of the {target} in the row")
    x, y = rect.get_x() + rect.get_width() / 2, rect.get_y() + rect.get_height() / 2
    gesture.emit("pressed", 1, x, y)
    gesture.emit("released", 1, x, y)


def toggle_switch(d):
    """Space or Enter on the switch. Gtk.Switch toggles at the end of its animation, so wait for the new state
    (a timeout only returns: the checks after it record that it did not toggle)."""
    switch = follow_widgets(d)[0]
    before = switch.get_active()
    switch.activate()
    wait_quietly(d, lambda: switch.get_active() != before, "the switch to toggle")


def arrow(d, window, direction):
    """An arrow key (direction: "LEFT", "RIGHT", "UP", "DOWN") as the window's move-focus binding."""
    value = getattr(d.Gtk.DirectionType, direction)
    try:
        window.emit("move-focus", value)
    except TypeError as e:                 # no such signal: what GtkWindow's move-focus does
        d.info(f"FALLBACK: the window has no move-focus signal ({e}); used child_focus({direction})")
        window.child_focus(value)


# ------------------------------------------------------------- the system accent and style
def set_system_theme(d, name, gtk_name=None):
    """Emulate a new system accent: the gsettings stub reports name from now on, then Gtk.Settings'
    gtk-icon-theme-name is set (gtk_name, default name): the notification the window reacts to. FAIL
    unless the notification was emitted."""
    d.ctx.icon_theme(name)
    settings = d.Gtk.Settings.get_default()
    notified = []
    handler = settings.connect("notify::gtk-icon-theme-name", lambda *_: notified.append(True))
    try:
        settings.set_property("gtk-icon-theme-name", gtk_name or name)
    finally:
        settings.disconnect(handler)
    d.require(notified, f"no notify::gtk-icon-theme-name for {gtk_name or name!r}")


def set_dark(d, dark):
    Adw = d.Adw
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.DEFAULT)


def preview_svg(d):
    gicon = d.find_one("preview-image").get_gicon()
    if not isinstance(gicon, d.Gio.FileIcon):
        return ""
    with open(gicon.get_file().get_path(), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------- the gallery
def grid(d):
    return d.find_one("gallery-grid")


def position_of(d, name):
    model = grid(d).get_model()
    for i in range(model.get_n_items()):
        if model.get_item(i).symbol.name == name:
            return i
    raise Fail(f"step {d.step_no}: {name!r} is not in the gallery's current list")


def click_cell(d, name):
    """A primary click on the symbol's cell, emulated (see the module docstring)."""
    g, pos = grid(d), position_of(d, name)
    if not g.activate_action("list.select-item", d.GLib.Variant("(ubb)", (pos, False, False))):
        d.info("FALLBACK: the grid has no list.select-item action; used select_item(position, True)")
        g.get_model().select_item(pos, True)


def card(d, name):
    """The mapped .symbol-card of this symbol, or None (the grid creates cards only near the view)."""
    cards = [c for c in by_class(d, "symbol-card", grid(d)) if c.get_tooltip_text() == name]
    return cards[0] if len(cards) == 1 else None


def card_in_view(d, name):
    """True when the symbol's card lies entirely inside the scrolled window's visible area."""
    c = card(d, name)
    if c is None:
        return False
    scroller = grid(d).get_parent()
    ok, rect = c.compute_bounds(scroller)
    return bool(ok and rect.get_y() >= 0 and rect.get_y() + rect.get_height() <= scroller.get_height()
                and rect.get_x() >= 0 and rect.get_x() + rect.get_width() <= scroller.get_width())


def vadjustment(d):
    adj = grid(d).get_vadjustment()
    return adj.get_value(), adj.get_upper()


def columns(d):
    """The number of cards in the first row of the grid (distinct x positions at the smallest y)."""
    g = grid(d)
    rows = []
    for c in by_class(d, "symbol-card", g):
        ok, rect = c.compute_bounds(g)
        if ok:
            rows.append((round(rect.get_y()), round(rect.get_x())))
    if not rows:
        return 0
    top = min(y for y, _ in rows)
    return len({x for y, x in rows if y == top})


def next_frames(d, widget, n=2):
    """Wait until widget's frame clock has ticked n times (layout and drawing have caught up)."""
    ticks = [0]

    def tick(_widget, _clock):
        ticks[0] += 1
        return ticks[0] < n                # True: keep ticking

    widget.add_tick_callback(tick)
    widget.queue_draw()
    d.wait_until(lambda: ticks[0] >= n, f"{n} frames of {type(widget).__name__}")
