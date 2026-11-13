"""FolderSymbolsWindow: Adw.ApplicationWindow subclass."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from folder_symbols.selection import subtitle_text, tooltip_text


class FolderSymbolsWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(900, 600)

        self._title_widget = Adw.WindowTitle(
            title="Folder icon",
            subtitle="No folder selected",
        )
        header = Adw.HeaderBar()
        header.set_title_widget(self._title_widget)

        placeholder = Adw.StatusPage(
            title="Icon gallery",
            description="The symbol gallery will appear here in a later step.",
            icon_name="folder-open-symbolic",
            vexpand=True,
        )

        # Adw.ToolbarView (libadwaita >= 1.4; Ubuntu 24.04 ships 1.5)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(placeholder)
        self.set_content(view)

    def update_selection(self, dirs, total):
        """Update header subtitle and tooltip from a new folder selection."""
        self._title_widget.set_subtitle(subtitle_text(dirs, total))
        tip = tooltip_text(dirs)
        self._title_widget.set_tooltip_text(tip if tip else None)
