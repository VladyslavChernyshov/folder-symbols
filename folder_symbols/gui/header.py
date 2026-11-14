"""Header bars of the two window panes: GalleryHeader (window buttons, search, categories) above the symbol
grid, and FolderHeader (selected folder, main menu) above the preview sidebar."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from folder_symbols.gallery import categories, category_tooltip, search_placeholder
from folder_symbols.selection import panel_title, panel_tooltip

ALL_CATEGORIES = "All categories"
HEADER_GAP = 8                           # window buttons -> search -> category button (mockup .hbl gap)
CATEGORY_MENU_WIDTH = 230                # mockup .pop width
CATEGORY_LIST_MAX_HEIGHT = 300           # the scrolled part of the menu, below "All categories"
# Margins around each category radio button, vertical and horizontal. The button is 28 px high by itself,
# so 2 px makes 32 px rows, about the mockup's .pop .it (7 px padding around a 16-17 px line).
CATEGORY_ROW_MARGIN = (2, 10)
NO_CATEGORY_ICON = "view-list-symbolic"
CLEAR_CATEGORY_ICONS = ["cross-small-symbolic", "window-close-symbolic"]   # first one the theme has


class GalleryHeader(Adw.Bin):
    """Header bar of the content pane: window buttons at the start (when the system layout puts them on
    the left), a search entry that fills the free space, and a split button for the category. The arrow
    opens the category list; the main part clears the category and is insensitive while none is chosen.

    Properties: query (the search text) and category ("" = all categories).

    Adw.HeaderBar keeps its title widget centred even when it expands, so the whole row is one title
    widget and the header bar's own window buttons are off. The end-side buttons are never needed here:
    this header never touches the window's right edge (the sidebar does, and its header shows them)."""

    query = GObject.Property(type=str, default="")
    category = GObject.Property(type=str, default="")

    def __init__(self, symbols, **kwargs):
        super().__init__(**kwargs)
        self._symbols = symbols

        self._category_action = Gio.SimpleAction.new_stateful(
            "category", GLib.VariantType.new("s"), GLib.Variant.new_string(""))
        self._category_action.connect("change-state", self._on_category_change)
        self._show_all_action = Gio.SimpleAction.new("show-all", None)
        self._show_all_action.connect("activate", lambda *_: self._set_category(""))
        actions = Gio.SimpleActionGroup()
        actions.add_action(self._category_action)
        actions.add_action(self._show_all_action)
        self.insert_action_group("gallery", actions)

        controls = Gtk.WindowControls(side=Gtk.PackType.START)
        controls.bind_property("empty", controls, "visible",
                               GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN)
        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.connect("search-changed", lambda entry: self.set_property("query", entry.get_text()))
        self._button_icon = Gtk.Image()
        self._button = Adw.SplitButton(child=self._button_icon, action_name="gallery.show-all",
                                       dropdown_tooltip="Choose a category",
                                       popover=self._category_menu(categories(symbols)))
        if not symbols:
            self.search.set_sensitive(False)
            self._button.set_sensitive(False)

        row = Gtk.Box(spacing=HEADER_GAP, hexpand=True)
        row.append(controls)
        row.append(self.search)
        row.append(self._button)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.set_title_widget(row)
        self.set_child(header)
        self._update()

    def _category_menu(self, names):
        """A popover with "All categories", a separator and a scrolled list of the categories. Each row is
        a radio button bound to gallery.category, so GTK marks the current category itself."""
        def row(label, target):
            return Gtk.CheckButton(label=label, action_name="gallery.category",
                                   action_target=GLib.Variant.new_string(target),
                                   margin_top=CATEGORY_ROW_MARGIN[0], margin_bottom=CATEGORY_ROW_MARGIN[0],
                                   margin_start=CATEGORY_ROW_MARGIN[1], margin_end=CATEGORY_ROW_MARGIN[1])
        listed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for name in names:
            listed.append(row(name, name))
        scroller = Gtk.ScrolledWindow(child=listed, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      max_content_height=CATEGORY_LIST_MAX_HEIGHT,
                                      propagate_natural_height=True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=CATEGORY_MENU_WIDTH)
        content.append(row(ALL_CATEGORIES, ""))
        content.append(Gtk.Separator())
        content.append(scroller)
        return Gtk.Popover(child=content)

    def _on_category_change(self, action, value):
        action.set_state(value)
        self._button.popdown()
        self._set_category(value.get_string())

    def _set_category(self, name):
        if self._category_action.get_state().get_string() != name:
            self._category_action.set_state(GLib.Variant.new_string(name))
        if self.category != name:
            self.category = name
        self._update()

    def _update(self):
        name = self.category or None
        self.search.set_placeholder_text(search_placeholder(self._symbols, name))
        self._show_all_action.set_enabled(name is not None)
        if name is None:
            self._button_icon.set_from_icon_name(NO_CATEGORY_ICON)
            self._button.set_tooltip_text(None)
        else:
            self._button_icon.set_from_gicon(Gio.ThemedIcon.new_from_names(CLEAR_CATEGORY_ICONS))
            self._button.set_tooltip_text(category_tooltip(name))


class FolderHeader(Adw.Bin):
    """Header bar of the sidebar: the selected folder's name (or "N folders"), with the paths in its
    tooltip, and the main menu. "Clean up…" and "About" name app actions that do not exist yet, so GTK
    shows them disabled."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._title = Adw.WindowTitle()
        menu = Gio.Menu()
        menu.append("Clean up…", "app.clean-up")
        menu.append("About", "app.about")
        button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True,
                                tooltip_text="Main Menu")
        header = Adw.HeaderBar(title_widget=self._title)
        header.pack_end(button)
        self.set_child(header)
        self.set_selection([], 0)

    def set_selection(self, dirs, total):
        self._title.set_title(panel_title(dirs))
        tip = panel_tooltip(dirs, total)
        self._title.set_tooltip_text(tip or None)
