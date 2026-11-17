"""Folder Symbols: the "Choose Icon…" item in the Nautilus context menu (nautilus-python extension).

Nautilus loads this file in its own process, so it stays small and self-contained: no folder_symbols or Gtk
imports, and no exception may escape get_file_items. The item appears only when at least one selected item is
a local folder. It launches folder-symbols-gui with every selected local path (the window ignores the files).

The executable is looked up on every right-click, in this order:
  1. $FOLDER_SYMBOLS_GUI, if it is set and executable (development);
  2. if this file is a symlink (`make nautilus-install`), the folder-symbols-gui wrapper in the repository the
     symlink points into;
  3. folder-symbols-gui on PATH.
If none is found, no item is shown and one line goes to stderr (once per Nautilus process).
"""
import os
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Nautilus", "4.1")   # Ubuntu 26.04 (Nautilus 50)
from gi.repository import GObject, Nautilus  # noqa: E402

ITEM_NAME = "FolderSymbols::ChooseIcon"
ITEM_LABEL = "Choose Icon…"
GUI_NAME = "folder-symbols-gui"
ENV_VAR = "FOLDER_SYMBOLS_GUI"

_warned = set()


def _log(message):
    sys.stderr.write(f"folder-symbols (Nautilus): {message}\n")


def _warn_once(message):
    if message not in _warned:
        _warned.add(message)
        _log(message)


def _executable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def find_gui(module_file=__file__):
    """The folder-symbols-gui to launch, or None."""
    env = os.environ.get(ENV_VAR)
    if _executable(env):
        return env
    if os.path.islink(module_file):
        repo = os.path.dirname(os.path.dirname(os.path.realpath(module_file)))
        candidate = os.path.join(repo, GUI_NAME)
        if _executable(candidate):
            return candidate
    return shutil.which(GUI_NAME)


def local_paths(files):
    """(paths, has_folder): local paths of the selected items in selection order, and whether one is a folder.
    Items without a local path (smb, sftp, trash, recent) are skipped; an item that fails to answer is too."""
    paths, has_folder = [], False
    for f in files or ():
        try:
            location = f.get_location()
            path = location.get_path() if location is not None else None
            if not path:
                continue
            is_dir = bool(f.is_directory())
        except Exception:
            continue
        paths.append(path)
        has_folder = has_folder or is_dir
    return paths, has_folder


def launch(exe, paths):
    """Start the window without blocking Nautilus; a thread reaps the child so no zombie is left behind."""
    try:
        proc = subprocess.Popen([exe, *paths], stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        _log(f"could not start {exe}: {e}")
        return None
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


class FolderSymbolsMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files):
        try:
            paths, has_folder = local_paths(files)
            if not has_folder:
                return []
            exe = find_gui()
            if exe is None:
                _warn_once(f"{GUI_NAME} not found (set {ENV_VAR} or put it on PATH); menu item hidden")
                return []
            item = Nautilus.MenuItem(name=ITEM_NAME, label=ITEM_LABEL)
            item.connect("activate", self._on_activate, exe, paths)
            return [item]
        except Exception as e:
            _warn_once(f"menu item hidden after an error: {e!r}")
            return []

    def _on_activate(self, _item, exe, paths):
        try:
            launch(exe, paths)
        except Exception as e:
            _log(f"launch failed: {e!r}")
