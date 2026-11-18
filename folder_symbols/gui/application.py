"""FolderSymbolsApplication: Adw.Application subclass."""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from folder_symbols.apply import apply_folders, reset_folders
from folder_symbols.appinfo import APP_NAME
from folder_symbols.preview import PreviewSession
from folder_symbols.store import plan_cleanup, run_cleanup
from folder_symbols.selection import launch_argv, resolve_selection, selection_error
from folder_symbols.gui.welcome import about_dialog
from folder_symbols.gui.window import FolderSymbolsWindow

APP_ID = "io.github.VladyslavChernyshov.FolderSymbols"
APP_ID_ENV = "FOLDER_SYMBOLS_APP_ID"     # another application id, for the GUI harness (tools/gui_check)


def _app_id():
    """$FOLDER_SYMBOLS_APP_ID when it is a valid application id, else APP_ID."""
    value = os.environ.get(APP_ID_ENV)
    return value if value and Gio.Application.id_is_valid(value) else APP_ID


class FolderSymbolsApplication(Adw.Application):
    def __init__(self, apply_func=apply_folders, reset_func=reset_folders, plan_cleanup_func=plan_cleanup,
                 run_cleanup_func=run_cleanup):
        """apply_func, reset_func: what the window's Apply and Reset call, apply.apply_folders and
        apply.reset_folders by default; plan_cleanup_func, run_cleanup_func: what Clean up calls,
        store.plan_cleanup and store.run_cleanup by default (stubs in self-checks)."""
        super().__init__(
            application_id=_app_id(),
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        GLib.set_application_name(APP_NAME)
        self._window = None
        self._preview_session = None
        self._apply_func, self._reset_func = apply_func, reset_func
        self._plan_cleanup_func, self._run_cleanup_func = plan_cleanup_func, run_cleanup_func

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._preview_session = PreviewSession()
        about = Gio.SimpleAction.new("about", None)       # app.about, the "About" item of the main menu
        about.connect("activate", lambda *_: self._window is not None and about_dialog().present(self._window))
        self.add_action(about)

    def do_shutdown(self):
        if self._preview_session is not None:
            self._preview_session.close()      # removes the preview SVGs of this session
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        if self._window is None:
            self._window = FolderSymbolsWindow(application=self, preview_session=self._preview_session,
                                               apply_func=self._apply_func, reset_func=self._reset_func,
                                               plan_cleanup_func=self._plan_cleanup_func,
                                               run_cleanup_func=self._run_cleanup_func)
        self._window.present()

    def run(self, argv=None):
        """Check the paths in the launching process, before GApplication registers or forwards them to a
        running instance: with no existing folder among them, print the error and return 1 (no window
        opens, an open window is not touched). None and a bare [argv0] run as before."""
        if argv is None:
            return super().run(None)
        argv, error = launch_argv(list(argv), local_path=_gio_local_path)
        if error:
            print(error, file=sys.stderr)
            return 1
        return super().run(argv)

    def do_open(self, files, n_files, hint):
        # files is a list of Gio.File; get_path() returns the decoded local path. run() has checked the
        # paths already; this guard covers an Open that did not go through it (and a folder removed since).
        paths = [f.get_path() or f.get_uri() for f in files]
        selection = resolve_selection(paths, local_path=_gio_local_path)
        if not selection.dirs:
            error = selection_error(selection)
            if error:
                print(error, file=sys.stderr)
            return
        self.activate()
        self._window.update_selection(list(selection.dirs), selection.total)


def _gio_local_path(uri):
    """The local path of a URI (the FUSE path of a mounted GVfs share), or None."""
    return Gio.File.new_for_uri(uri).get_path()
