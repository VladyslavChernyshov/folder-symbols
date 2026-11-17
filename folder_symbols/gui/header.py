"""Header bars of the two window panes: GalleryHeader (window buttons, search, categories) above the symbol
grid, and FolderHeader (selected folder, main menu) above the preview sidebar."""
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from folder_symbols.gallery import categories, category_tooltip, search_placeholder
from folder_symbols.selection import panel_title, panel_tooltip

ALL_CATEGORIES = "All categories"
HEADER_GAP = 8                           # window buttons -> search -> category button (mockup .hbl gap)
CATEGORY_MENU_MAX_HEIGHT = 400          # content height of the category menu, about 12 rows; it scrolls above
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
        self.search = Gtk.SearchEntry(hexpand=True, name="search-entry")
        self.search.connect("search-changed", lambda entry: self.set_property("query", entry.get_text()))
        self._button_icon = Gtk.Image()
        self._button = Adw.SplitButton(child=self._button_icon, action_name="gallery.show-all",
                                       dropdown_tooltip="Choose a category",
                                       menu_model=self._category_menu(categories(symbols)), name="category-button")
        self._button.connect("notify::popover", lambda button, _pspec: _cap_menu_height(button))
        _cap_menu_height(self._button)
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

    def reset_filter(self):
        """Clear the search and show all categories. query is set directly, so listeners see the change
        now rather than after the search entry's typing delay."""
        self.search.set_text("")
        if self.query:
            self.query = ""
        self._set_category("")

    @staticmethod
    def _category_menu(names):
        """A native menu, as in Nautilus' view menu: "All categories", then the categories in a second
        section (the theme draws the separator between sections). Every item targets gallery.category, so
        the theme draws them as radio items and marks the current one. The menu scrolls by itself when it
        is taller than the space available, and closes when an item is chosen."""
        def section(*items):
            menu = Gio.Menu()
            for label, target in items:
                item = Gio.MenuItem.new(label, None)
                item.set_action_and_target_value("gallery.category", GLib.Variant.new_string(target))
                menu.append_item(item)
            return menu
        menu = Gio.Menu()
        menu.append_section(None, section((ALL_CATEGORIES, "")))
        menu.append_section(None, section(*((name, name) for name in names)))
        return menu

    def _on_category_change(self, action, value):
        action.set_state(value)
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


def _cap_menu_height(button):
    """Limit the height of a split button's menu to CATEGORY_MENU_MAX_HEIGHT, so a long menu scrolls
    inside it instead of reaching past the window. Gtk.PopoverMenu has no maximum height of its own, but
    its child is a Gtk.ScrolledWindow with propagate-natural-height (GTK 4.14 to 4.22 at least), which
    takes a max-content-height. Only public API; when the layout is not the expected one, the menu is
    left as it is."""
    try:
        popover = button.get_popover()
        if popover is None:
            return
        scroller = popover.get_child() if isinstance(popover, Gtk.PopoverMenu) else None
        if not isinstance(scroller, Gtk.ScrolledWindow):
            print("folder-symbols: category menu height not limited (unexpected menu layout)", file=sys.stderr)
            return
        scroller.set_max_content_height(CATEGORY_MENU_MAX_HEIGHT)
        scroller.set_propagate_natural_height(True)
    except Exception as e:                  # never let a cosmetic tweak break the window
        print(f"folder-symbols: category menu height not limited ({e})", file=sys.stderr)


def main_menu():
    """The main menu, one model shared by the menu buttons of both window pages: "Clean up…" is the
    window's action win.clean-up, "About" the application's action app.about."""
    menu = Gio.Menu()
    menu.append("Clean up…", "win.clean-up")
    menu.append("About", "app.about")
    return menu


def menu_button(menu):
    """The "≡" button that opens menu (main_menu())."""
    return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True, tooltip_text="Main Menu",
                          name="main-menu-button")


class FolderHeader(Adw.Bin):
    """Header bar of the sidebar: the selected folder's name (or "N folders"), with the paths in its
    tooltip, and the main menu (main_menu()). It exists only once there are folders: set_selection is
    called right after it is made."""

    def __init__(self, menu, **kwargs):
        super().__init__(**kwargs)
        self._title = Adw.WindowTitle(name="folder-title")
        header = Adw.HeaderBar(title_widget=self._title)
        header.pack_end(menu_button(menu))
        self.set_child(header)

    def set_selection(self, dirs, total):
        self._title.set_title(panel_title(dirs))
        tip = panel_tooltip(dirs, total)
        self._title.set_tooltip_text(tip or None)
