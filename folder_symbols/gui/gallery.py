"""SymbolGallery: search row and a virtualised grid of symbols with single selection."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GObject, Gtk, Pango

from folder_symbols.gallery import categories, matches

ALL_CATEGORIES = "All categories"
CELL_WIDTH, CELL_HEIGHT = 88, 80
ICON_SIZE = 32


class SymbolItem(GObject.Object):
    """One gallery.Symbol in a Gio.ListStore."""
    def __init__(self, symbol):
        super().__init__()
        self.symbol = symbol


class SymbolGallery(Gtk.Box):
    """Search entry and category drop-down above a grid of symbols.
    The property selected-symbol holds the selected gallery.Symbol, or None."""

    selected_symbol = GObject.Property(type=GObject.TYPE_PYOBJECT, nick="selected-symbol")

    def __init__(self, symbols, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._categories = categories(symbols)

        self._search = Gtk.SearchEntry(
            placeholder_text=f"Search {len(symbols)} symbols…",
            hexpand=True,
        )
        self._search.connect("search-changed", self._on_filter_changed)
        self._category = Gtk.DropDown.new_from_strings([ALL_CATEGORIES, *self._categories])
        self._category.connect("notify::selected", self._on_filter_changed)

        row = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        row.append(self._search)
        row.append(self._category)
        self.append(row)

        store = Gio.ListStore(item_type=SymbolItem)
        store.splice(0, 0, [SymbolItem(s) for s in symbols])
        self._filter = Gtk.CustomFilter.new(self._match_item)
        self._filtered = Gtk.FilterListModel(model=store, filter=self._filter)
        self._filtered.connect("items-changed", self._on_items_changed)
        self._selection = Gtk.SingleSelection(model=self._filtered, autoselect=False, can_unselect=True)
        self._selection.set_selected(Gtk.INVALID_LIST_POSITION)
        self._selection.connect("notify::selected-item", self._on_selected)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        grid = Gtk.GridView(model=self._selection, factory=factory, min_columns=2, max_columns=12)
        scroller = Gtk.ScrolledWindow(child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)

        empty = Adw.StatusPage(
            title="No symbols match",
            description="Try another name or category.",
            icon_name="edit-find-symbolic",
        )
        self._stack = Gtk.Stack(vexpand=True)
        self._stack.add_named(scroller, "grid")
        self._stack.add_named(empty, "empty")
        self.append(self._stack)

    def _current_category(self):
        i = self._category.get_selected()
        return self._categories[i - 1] if 0 < i <= len(self._categories) else None

    def _match_item(self, item):
        return matches(item.symbol, self._search.get_text(), self._current_category())

    def _on_filter_changed(self, *_):
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_items_changed(self, model, *_):
        self._stack.set_visible_child_name("grid" if model.get_n_items() else "empty")

    def _on_selected(self, selection, _pspec):
        item = selection.get_selected_item()
        self.selected_symbol = item.symbol if item is not None else None

    def _on_setup(self, _factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        box.set_size_request(CELL_WIDTH, CELL_HEIGHT)
        # A file named *-symbolic.svg is loaded as a symbolic icon and recoloured with the theme's
        # foreground colour, so it is dark on a light theme and light on a dark one.
        box.append(Gtk.Image(pixel_size=ICON_SIZE))
        box.append(Gtk.Label(ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=10,
                             css_classes=["caption"]))
        list_item.set_child(box)

    def _on_bind(self, _factory, list_item):
        sym = list_item.get_item().symbol
        box = list_item.get_child()
        image = box.get_first_child()
        image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(sym.path)))
        image.get_next_sibling().set_text(sym.name)
        box.set_tooltip_text(sym.name)
