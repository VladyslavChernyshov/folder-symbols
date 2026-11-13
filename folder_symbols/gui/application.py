"""FolderSymbolsApplication: Adw.Application subclass."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from folder_symbols.selection import normalise_paths
from folder_symbols.gui.window import FolderSymbolsWindow

APP_ID = "io.github.VladyslavChernyshov.FolderSymbols"


class FolderSymbolsApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._window = None

    def do_activate(self):
        if self._window is None:
            self._window = FolderSymbolsWindow(application=self)
        self._window.present()

    def do_open(self, files, n_files, hint):
        # files is a list of Gio.File; get_path() returns the decoded local path.
        paths = [f.get_path() or f.get_uri() for f in files]
        dirs, ignored = normalise_paths(paths)
        self.activate()
        self._window.update_selection(dirs, len(dirs) + ignored)
