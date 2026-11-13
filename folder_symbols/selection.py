"""Path normalisation and window-title helpers (no GTK dependency)."""
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


def subtitle_text(dirs, total):
    """Return the Adw.WindowTitle subtitle string.

    dirs  – normalised existing directory list (output of normalise_paths)
    total – len(dirs) + ignored_count  (duplicates do not contribute to total)
    """
    ignored = total - len(dirs)
    if total == 0:
        return "No folder selected"
    if ignored > 0:
        return f"{len(dirs)} of {total} selected items are folders"
    if len(dirs) == 1:
        name = os.path.basename(dirs[0]) or dirs[0]
        return f"{name} · {_tilde(dirs[0])}"
    return f"{len(dirs)} folders"


def tooltip_text(dirs):
    """Return newline-separated folder names for the header tooltip."""
    return "\n".join(os.path.basename(d) or d for d in dirs)
