"""Path normalisation and sidebar-header text helpers (no GTK dependency)."""
import os
from urllib.parse import urlparse, unquote

from folder_symbols.store import folder_path


def normalise_paths(paths):
    """Return (dirs, ignored_count).

    Accepts plain paths or file:// URIs (percent-encoded names are decoded).
    Applies the same normalisation as store.folder_path (abspath + expanduser).
    Keeps only existing directories; deduplicates preserving input order.
    Duplicates are dropped silently and do NOT increment ignored_count.
    ignored_count counts only inputs that are not existing directories.
    """
    seen, dirs, ignored = set(), [], 0
    for p in paths:
        if p.startswith("file://"):
            p = unquote(urlparse(p).path)
        p = folder_path(p)
        if p in seen:
            continue
        if not os.path.isdir(p):
            ignored += 1
            continue
        seen.add(p)
        dirs.append(p)
    return dirs, ignored


def _tilde(path):
    """Format an absolute path replacing $HOME with ~."""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def panel_title(dirs):
    """Return the title of the sidebar header: the folder name, "N folders", or "No folder selected".

    dirs – normalised existing directory list (output of normalise_paths)
    """
    if not dirs:
        return "No folder selected"
    if len(dirs) == 1:
        return os.path.basename(dirs[0]) or dirs[0]
    return f"{len(dirs)} folders"


def panel_tooltip(dirs, total):
    """Return the tooltip of the sidebar header: one path per line (under $HOME as ~/...), preceded by
    "N of M selected items are folders" when some selected items were not folders; "" if there is none.

    total – len(dirs) + ignored_count  (duplicates do not contribute to total)
    """
    lines = [_tilde(d) for d in dirs]
    if total > len(dirs):
        lines.insert(0, f"{len(dirs)} of {total} selected items are folders")
    return "\n".join(lines)
