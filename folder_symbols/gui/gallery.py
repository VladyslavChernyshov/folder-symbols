"""SymbolGallery: search row and a virtualised grid of symbols with single selection."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GObject, Gtk, Pango

from folder_symbols.gallery import categories, matches

ALL_CATEGORIES = "All categories"
GALLERY_MARGIN = 16                      # window edge -> search row and grid cards (mockup .main padding)
ROW_GAP = 10                             # search entry -> category drop-down (mockup .row gap)
CARD_GAP = 7                             # between neighbouring cards, both ways (mockup .grid gap)
CARD_HEIGHT = 78                         # outer height, border included (mockup .tile, border-box)
CARD_MIN_WIDTH = 81                      # outer; with the margins 88 px per column, as before
CARD_BORDER = 1
CARD_RADIUS = 10
RING_WIDTH = 3                           # accent ring of the selected card
RING_OFFSET = -1
RING_OUTSET = RING_WIDTH + RING_OFFSET   # how far the ring reaches outside the card: 2 px
# Each grid child has margins that add up to CARD_GAP between neighbours (GTK margins are whole pixels).
# Horizontally 3 + 4. Vertically the top margin is only RING_OUTSET, the least that keeps the ring of a
# first-row card from being clipped at the top edge of the scrolled window.
CARD_MARGIN_START = 3
CARD_MARGIN_END = CARD_GAP - CARD_MARGIN_START
CARD_MARGIN_TOP = RING_OUTSET
CARD_MARGIN_BOTTOM = CARD_GAP - CARD_MARGIN_TOP
# Padding under the search row, above the scroll divider (the top edge of the scrolled window). With the
# first row's CARD_MARGIN_TOP below the divider, the cards sit exactly GALLERY_MARGIN under the row at
# scroll position 0, the same as the row's distance to the title bar.
SEARCH_BAR_PADDING = GALLERY_MARGIN - CARD_MARGIN_TOP
ICON_SIZE = 32
NAME_GAP = 9                             # symbol -> its name (mockup: 6 margin + 3 gap)
NAME_FONT_SIZE = 10
NAME_MAX_CHARS = 13                      # about the mockup's 80 px label width at 10 px

# CSS padding of the grid, inside the scrolled content (as in GTK's file chooser grid), so the outer
# edges of the cards sit GALLERY_MARGIN from the sides and GALLERY_MARGIN after the last row when
# scrolled to the end. No top padding: SEARCH_BAR_PADDING + CARD_MARGIN_TOP already make GALLERY_MARGIN.
GRID_PADDING = (0, GALLERY_MARGIN - CARD_MARGIN_END,
                GALLERY_MARGIN - CARD_MARGIN_BOTTOM, GALLERY_MARGIN - CARD_MARGIN_START)   # top right bottom left

# Only named theme colours, so light, dark and high-contrast themes keep working.
# - The grid is transparent and sits on the window background, like the search row.
# - The grid child is the selection/hover node: its own fill is removed (this provider's priority beats
#   the theme for every state), and it has no padding, so the theme's focus ring on it follows the card.
# - The scrolled window's undershoot.top node is what GTK draws over the top edge only while the content
#   is scrolled; libadwaita gives it a faint shade, and a 1 px border line marks the search row's edge.
# - Every cell is a card. The selected one gets an accent ring instead of a fill, and an undimmed name.
_px = lambda values: " ".join(f"{v}px" for v in values)
GRID_CSS = f"""
gridview.symbol-gallery {{ background: transparent; padding: {_px(GRID_PADDING)}; }}
gridview.symbol-gallery > child {{
  background: none; padding: 0; border-radius: {CARD_RADIUS}px;
  margin: {_px((CARD_MARGIN_TOP, CARD_MARGIN_END, CARD_MARGIN_BOTTOM, CARD_MARGIN_START))};
}}
.symbol-card {{
  min-width: {CARD_MIN_WIDTH - 2 * CARD_BORDER}px; min-height: {CARD_HEIGHT - 2 * CARD_BORDER}px;
  background-color: @card_bg_color; border: {CARD_BORDER}px solid @borders; border-radius: {CARD_RADIUS}px;
}}
.symbol-card label {{ font-size: {NAME_FONT_SIZE}px; }}
gridview.symbol-gallery > child:selected .symbol-card {{
  border-color: transparent; outline: {RING_WIDTH}px solid @accent_bg_color; outline-offset: {RING_OFFSET}px;
}}
gridview.symbol-gallery > child:selected .symbol-card label {{ opacity: 1; }}
scrolledwindow.symbol-scroller > undershoot.top {{ box-shadow: inset 0 1px @borders; }}
"""
_css_loaded = False


def _load_css():
    global _css_loaded
    if _css_loaded:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(GRID_CSS)           # GTK 4.12
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_loaded = True


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
        _load_css()
        self._categories = categories(symbols)

        self._search = Gtk.SearchEntry(
            placeholder_text=f"Search {len(symbols)} symbols…",
            hexpand=True,
        )
        self._search.connect("search-changed", self._on_filter_changed)
        self._category = Gtk.DropDown.new_from_strings([ALL_CATEGORIES, *self._categories])
        self._category.connect("notify::selected", self._on_filter_changed)

        row = Gtk.Box(spacing=ROW_GAP, margin_top=GALLERY_MARGIN, margin_bottom=SEARCH_BAR_PADDING,
                      margin_start=GALLERY_MARGIN, margin_end=GALLERY_MARGIN)
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
        grid = Gtk.GridView(model=self._selection, factory=factory, min_columns=2, max_columns=12,
                            css_classes=["symbol-gallery"])
        # No margins here: the insets are the grid's CSS padding. The overlay scrollbar floats over the
        # padding, so it neither moves cells nor changes the number of columns. The divider under the
        # search row while scrolled is CSS on this widget (see GRID_CSS), so the layout does not change.
        scroller = Gtk.ScrolledWindow(child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                      overlay_scrolling=True, css_classes=["symbol-scroller"])

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
        # The card fills the grid cell (its size comes from GRID_CSS); the content is centred in it.
        cell = Gtk.Box(css_classes=["symbol-card"])
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=NAME_GAP,
                          hexpand=True, vexpand=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        # A file named *-symbolic.svg is loaded as a symbolic icon and recoloured with the theme's
        # foreground colour, so it is dark on a light theme and light on a dark one.
        content.append(Gtk.Image(pixel_size=ICON_SIZE))
        content.append(Gtk.Label(ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=NAME_MAX_CHARS,
                                 css_classes=["dim-label"]))
        cell.append(content)
        list_item.set_child(cell)

    def _on_bind(self, _factory, list_item):
        sym = list_item.get_item().symbol
        box = list_item.get_child()
        image = box.get_first_child().get_first_child()
        image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(sym.path)))
        image.get_next_sibling().set_text(sym.name)
        box.set_tooltip_text(sym.name)
