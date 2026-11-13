"""FolderSymbolsWindow: Adw.ApplicationWindow subclass."""
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject

from folder_symbols.gallery import list_symbols
from folder_symbols.selection import subtitle_text, tooltip_text
from folder_symbols.symbols import default_symbols_dir
from folder_symbols.gui.gallery import SymbolGallery


class FolderSymbolsWindow(Adw.ApplicationWindow):
    # The gallery.Symbol selected in the gallery, or None.
    selected_symbol = GObject.Property(type=GObject.TYPE_PYOBJECT, nick="selected-symbol")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(900, 600)

        self._title_widget = Adw.WindowTitle(
            title="Folder icon",
            subtitle="No folder selected",
        )
        header = Adw.HeaderBar()
        header.set_title_widget(self._title_widget)

        # Adw.ToolbarView (libadwaita >= 1.4; Ubuntu 24.04 ships 1.5)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self._build_body(default_symbols_dir()))
        self.set_content(view)

    def _build_body(self, symbols_dir):
        """The symbol gallery, or a status page when symbols_dir has no symbols."""
        if not os.path.isdir(symbols_dir):
            return self._no_symbols(f"Folder does not exist: {symbols_dir}")
        try:
            symbols = list_symbols(symbols_dir)
        except OSError as e:
            return self._no_symbols(f"Cannot read {symbols_dir}: {e.strerror or e}")
        if not symbols:
            return self._no_symbols(f"No *-symbolic.svg files in {symbols_dir}")
        gallery = SymbolGallery(symbols)
        gallery.bind_property("selected-symbol", self, "selected-symbol", GObject.BindingFlags.SYNC_CREATE)
        return gallery

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
        """Update header subtitle and tooltip from a new folder selection."""
        self._title_widget.set_subtitle(subtitle_text(dirs, total))
        tip = tooltip_text(dirs)
        self._title_widget.set_tooltip_text(tip if tip else None)
