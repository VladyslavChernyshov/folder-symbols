"""FolderSymbolsWindow: Adw.ApplicationWindow subclass."""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from folder_symbols.gallery import list_symbols
from folder_symbols.initial import initial_state, read_manifest
from folder_symbols.symbols import default_symbols_dir
from folder_symbols.gui.gallery import SymbolGallery
from folder_symbols.gui.header import FolderHeader, GalleryHeader
from folder_symbols.gui.preview import PreviewPanel

APP_TITLE = "Folder Symbols"
DEFAULT_SIZE = (850, 600)                # mockup .win
SIDEBAR_WIDTH_FRACTION = 0.32            # about 270 px at 850 px (mockup .right)
SIDEBAR_MIN_WIDTH = 220
SIDEBAR_MAX_WIDTH = 300


class FolderSymbolsWindow(Adw.ApplicationWindow):
    # The gallery.Symbol selected in the gallery, or None.
    selected_symbol = GObject.Property(type=GObject.TYPE_PYOBJECT, nick="selected-symbol")

    def __init__(self, preview_session, **kwargs):
        super().__init__(title=APP_TITLE, **kwargs)
        self._preview_session = preview_session
        self._symbols_dir = default_symbols_dir()
        self._symbols, self._gallery_header, self._gallery = [], None, None
        self.set_default_size(*DEFAULT_SIZE)

        # Nautilus-style split (Adw.OverlaySplitView, libadwaita >= 1.4): the gallery on the left, the
        # preview sidebar on the right, never collapsed. Each pane has its own flat header bar, so the
        # gallery's header has the window's colour and the sidebar's the sidebar colour. Each header bar
        # shows only the window buttons on its window-edge side.
        self._folder_header = FolderHeader()
        self._panel = PreviewPanel(self._preview_session)
        self.connect("notify::selected-symbol", lambda *_: self._panel.set_symbol(self.selected_symbol))
        sidebar = Adw.ToolbarView()
        sidebar.add_top_bar(self._folder_header)
        sidebar.set_content(self._panel)

        split = Adw.OverlaySplitView(
            sidebar_position=Gtk.PackType.END, collapsed=False, show_sidebar=True,
            sidebar_width_fraction=SIDEBAR_WIDTH_FRACTION,
            min_sidebar_width=SIDEBAR_MIN_WIDTH, max_sidebar_width=SIDEBAR_MAX_WIDTH,
            content=self._build_content(self._symbols_dir), sidebar=sidebar,
        )
        self.set_content(split)

    def _build_content(self, symbols_dir):
        """The gallery pane: its header bar over the symbol grid, or over a status page when symbols_dir
        has no symbols. The divider under the header while the grid is scrolled is the ToolbarView's."""
        symbols, problem = self._load_symbols(symbols_dir)
        header = self._gallery_header = GalleryHeader(symbols)
        header.search.set_key_capture_widget(self)      # typing anywhere in the window starts the search
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        if problem:
            view.set_content(self._no_symbols(problem))
            return view
        self._symbols = symbols
        gallery = self._gallery = SymbolGallery(symbols)
        gallery.bind_property("selected-symbol", self, "selected-symbol", GObject.BindingFlags.SYNC_CREATE)
        update = lambda *_: gallery.set_filter(header.query, header.category or None)
        header.connect("notify::query", update)
        header.connect("notify::category", update)
        view.set_content(gallery)
        return view

    @staticmethod
    def _load_symbols(symbols_dir):
        """Return (symbols, problem); problem is a message when there is nothing to show."""
        if not os.path.isdir(symbols_dir):
            return [], f"Folder does not exist: {symbols_dir}"
        try:
            symbols = list_symbols(symbols_dir)
        except OSError as e:
            return [], f"Cannot read {symbols_dir}: {e.strerror or e}"
        if not symbols:
            return [], f"No *-symbolic.svg files in {symbols_dir}"
        return symbols, None

    @staticmethod
    def _no_symbols(reason):
        return Adw.StatusPage(
            title="Symbols not found",
            description=f"{reason}\n\nInstall yaru-theme-icon or point YARU_SYMBOLS_DIR at a folder with "
                        "*-symbolic.svg files.",
            icon_name="dialog-warning-symbolic",
            vexpand=True,
        )

    def update_selection(self, dirs, total):
        """Show a new folder selection: the sidebar header's title and tooltip, and the initial state from
        the manifest (read only): the recorded symbol selected and scrolled to, previewed in the recorded
        accent, or nothing selected. The search and the category are reset first, so the symbol can be
        shown even when the previous filter would hide it."""
        self._folder_header.set_selection(dirs, total)
        if self._gallery is None:                         # no symbols: only the status page
            return
        manifest, problem = read_manifest()
        state = initial_state(dirs, manifest, self._symbols, self._symbols_dir)
        for line in (problem, state.message):
            if line:
                print(line, file=sys.stderr)
        self._gallery_header.reset_filter()
        self._panel.set_accent(state.accent)
        self._gallery.select_symbol(state.symbol)
