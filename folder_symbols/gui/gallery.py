"""SymbolGallery: a virtualised grid of symbols with single selection, filtered by search text and category."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from folder_symbols.gallery import matches

GALLERY_MARGIN = 16                      # pane edges and header bar -> grid cards (mockup .main padding)
CARD_GAP = 7                             # between neighbouring cards, both ways (mockup .grid gap)
CARD_HEIGHT = 78                         # outer height, border included (mockup .tile, border-box)
CARD_MIN_WIDTH = 81                      # outer; with the margins 88 px per column, as before
CARD_BORDER = 1
CARD_RADIUS = 10
RING_WIDTH = 3                           # accent ring of the selected card
RING_OFFSET = -1
RING_OUTSET = RING_WIDTH + RING_OFFSET   # how far the ring reaches outside the card: 2 px
# Each grid child has margins that add up to CARD_GAP between neighbours (GTK margins are whole pixels).
# Horizontally 3 + 4. Vertically the top margin is RING_OUTSET, so the ring of a first-row card stays
# inside the grid's top padding.
CARD_MARGIN_START = 3
CARD_MARGIN_END = CARD_GAP - CARD_MARGIN_START
CARD_MARGIN_TOP = RING_OUTSET
CARD_MARGIN_BOTTOM = CARD_GAP - CARD_MARGIN_TOP
ICON_SIZE = 32
NAME_GAP = 9                             # symbol -> its name (mockup: 6 margin + 3 gap)
NAME_FONT_SIZE = 10
NAME_MAX_CHARS = 13                      # about the mockup's 80 px label width at 10 px

# CSS padding of the grid, inside the scrolled content (as in GTK's file chooser grid), so the outer
# edges of the cards sit GALLERY_MARGIN from the header bar at scroll position 0, from the sides, and
# after the last row when scrolled to the end.
GRID_PADDING = (GALLERY_MARGIN - CARD_MARGIN_TOP, GALLERY_MARGIN - CARD_MARGIN_END,
                GALLERY_MARGIN - CARD_MARGIN_BOTTOM, GALLERY_MARGIN - CARD_MARGIN_START)   # top right bottom left

# Only named theme colours, so light, dark and high-contrast themes keep working.
# - The grid is transparent and sits on the window background, like the flat header bar above it.
# - The grid child is the selection/hover node: its own fill is removed (this provider's priority beats
#   the theme for every state), and it has no padding, so the theme's focus ring on it follows the card.
# - The divider under the header bar while the grid is scrolled is libadwaita's own (Adw.ToolbarView with
#   a flat top bar styles the scrolled window's undershoot), so there is no rule for it here.
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
    """A grid of symbols, filtered with set_filter(), or "No symbols match".
    The property selected-symbol holds the selected gallery.Symbol, or None."""

    selected_symbol = GObject.Property(type=GObject.TYPE_PYOBJECT, nick="selected-symbol")

    def __init__(self, symbols, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        _load_css()
        self._query = ""
        self._category = None
        self._pending_scroll = None              # (position, flags) to scroll to once the grid has its size
        self._scroll_tick = None

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
        self._grid = grid = Gtk.GridView(model=self._selection, factory=factory, min_columns=2, max_columns=12,
                            css_classes=["symbol-gallery"], name="gallery-grid")
        # No margins here: the insets are the grid's CSS padding. The overlay scrollbar floats over the
        # padding, so it neither moves cells nor changes the number of columns.
        scroller = Gtk.ScrolledWindow(child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                      overlay_scrolling=True)

        empty = Adw.StatusPage(
            title="No symbols match",
            description="Try another name or category.",
            icon_name="edit-find-symbolic",
            name="gallery-empty",
        )
        self._stack = Gtk.Stack(vexpand=True)
        self._stack.add_named(scroller, "grid")
        self._stack.add_named(empty, "empty")
        self.append(self._stack)

    def select_symbol(self, symbol):
        """Select symbol (a gallery.Symbol, or None for no selection) as if it had been clicked, and scroll
        it into view with keyboard focus on it (or scroll to the top for None, focus unchanged). A symbol
        that the current filter hides is not selected."""
        position = next((i for i, item in enumerate(self._filtered) if item.symbol == symbol),
                        Gtk.INVALID_LIST_POSITION) if symbol is not None else Gtk.INVALID_LIST_POSITION
        self._selection.set_selected(position)
        if position != Gtk.INVALID_LIST_POSITION:
            self._scroll_to(position, Gtk.ListScrollFlags.FOCUS)   # arrow keys start from the selected cell
        else:
            self._scroll_to(0, Gtk.ListScrollFlags.NONE)

    def _scroll_to(self, position, flags):
        """Scroll position into view on the next frame in which the grid has a size. Gtk.GridView.scroll_to
        called before the grid's first allocation (the window is opened with a selection) leaves the view
        at the top and the grid half drawn, so it waits for a tick callback."""
        self._pending_scroll = (position, flags)
        if self._scroll_tick is None:
            self._scroll_tick = self._grid.add_tick_callback(self._on_scroll_tick)

    def _on_scroll_tick(self, grid, _clock):
        if grid.get_height() <= 0:
            return GLib.SOURCE_CONTINUE
        self._scroll_tick = None
        position, flags = self._pending_scroll
        if position < self._filtered.get_n_items():
            grid.scroll_to(position, flags, None)                                    # GTK 4.12
        return GLib.SOURCE_REMOVE

    def set_filter(self, query, category):
        """Show the symbols whose name contains query and, unless category is None, of that category."""
        if (query, category) != (self._query, self._category):
            self._query, self._category = query, category
            self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def _match_item(self, item):
        return matches(item.symbol, self._query, self._category)

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
