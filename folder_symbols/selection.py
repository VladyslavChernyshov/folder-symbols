"""Path normalisation, the launcher's path check and sidebar-header text helpers (no GTK dependency)."""
import os
import re
import stat
from dataclasses import dataclass
from urllib.parse import urlparse, unquote

from folder_symbols.store import folder_path

PROG = "folder-symbols-gui"
MAX_LISTED = 10                     # rejected paths listed in the error before "... and N more"
_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class Selection:
    """The resolved arguments of a launch.

    dirs – existing folders (absolute, symlinks not resolved), input order, duplicates merged
    rejected – (path, reason) for every other argument, input order, duplicates merged; path is absolute,
               or the URI itself for a non-file URI with no local path
    paths – the paths of dirs and rejected together, in input order
    empty – True if an empty argument was given (skipped and not counted, like a duplicate)
    """
    dirs: tuple
    rejected: tuple
    paths: tuple
    empty: bool = False

    @property
    def total(self):
        return len(self.dirs) + len(self.rejected)


def _reason(path):
    """None if path is an existing folder (a symlink to one included), otherwise why it is not."""
    try:
        st = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return "broken link" if os.path.islink(path) else "not found"
    except OSError as e:
        return f"cannot access ({e.strerror})"
    return None if stat.S_ISDIR(st.st_mode) else "not a folder"


def resolve_selection(args, local_path=None):
    """Resolve launch arguments: plain paths or URIs.

    file:// URIs are decoded. Other URIs (smb://, sftp://, ...) go through local_path(uri) -> str | None
    (the GUI passes Gio's get_path, which gives the FUSE path of a mounted GVfs share) and are rejected as
    "not a local folder" when it gives none. Paths get store.folder_path (abspath + expanduser, symlinks
    not resolved). Empty arguments are skipped and not counted.
    """
    seen, dirs, rejected, paths, empty = set(), [], [], [], False
    for arg in args:
        if arg == "":
            empty = True
            continue
        reason = None
        if arg.startswith("file://"):
            path = folder_path(unquote(urlparse(arg).path))
        elif _URI.match(arg):
            local = local_path(arg) if local_path else None
            path, reason = (folder_path(local), None) if local else (arg, "not a local folder")
        else:
            path = folder_path(arg)
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
        reason = reason or _reason(path)
        if reason:
            rejected.append((path, reason))
        else:
            dirs.append(path)
    return Selection(tuple(dirs), tuple(rejected), tuple(paths), empty)


def selection_error(selection):
    """The launcher's error text when arguments were given but none is an existing folder, else None.
    The rejected paths are listed one per line, at most MAX_LISTED of them."""
    if selection.dirs or not (selection.rejected or selection.empty):
        return None
    items = [f"{path}: {reason}" for path, reason in selection.rejected]
    if selection.empty:
        items.append('"": empty argument')
    lines = [f"{PROG}: no existing folder among the given paths"]
    lines += [f"  {item}" for item in items[:MAX_LISTED]]
    if len(items) > MAX_LISTED:
        lines.append(f"  ... and {len(items) - MAX_LISTED} more")
    return "\n".join(lines)


def launch_argv(argv, local_path=None):
    """Check a launch's argv before GApplication sees it. Returns (argv to run, None) or (None, error).

    No arguments, or any argument starting with "-" (GApplication's own options): argv unchanged.
    Otherwise the arguments are resolved (resolve_selection): with no existing folder among them, the
    error text; else argv[0] and the resolved paths, so the open handler sees exactly what was checked.
    """
    args = list(argv[1:])
    if not args or any(a.startswith("-") for a in args):
        return list(argv), None
    selection = resolve_selection(args, local_path)
    error = selection_error(selection)
    if error:
        return None, error
    return [argv[0], *selection.paths], None


def tilde(path):
    """Format an absolute path replacing $HOME with ~."""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def panel_title(dirs):
    """Return the title of the sidebar header: the folder name or "N folders".

    dirs – normalised existing directory list (resolve_selection(...).dirs), not empty: the window shows its
    welcome page, not the sidebar, until it has folders
    """
    if len(dirs) == 1:
        return os.path.basename(dirs[0]) or dirs[0]
    return f"{len(dirs)} folders"


def panel_tooltip(dirs, total):
    """Return the tooltip of the sidebar header: one path per line (under $HOME as ~/...), preceded by
    "N of M selected items are folders" when some selected items were not folders; "" if there is none.

    total – len(dirs) + ignored_count  (duplicates do not contribute to total)
    """
    lines = [tilde(d) for d in dirs]
    if total > len(dirs):
        lines.insert(0, f"{len(dirs)} of {total} selected items are folders")
    return "\n".join(lines)
