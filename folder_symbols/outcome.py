"""What the window does after Apply (no GTK): close, or show a dialog with a summary and the failed folders;
and the Apply button's state. Works on apply.FolderResult lists and the errors apply_folders raises."""
import dataclasses
from typing import Optional

from .apply import ApplyError, RecordError
from .selection import tilde
from .store import ManifestError

RECORD_HINT = "'folder-symbols list' and 'reset --all' will not see them."


@dataclasses.dataclass(frozen=True)
class Outcome:
    close: bool                  # all folders done: close the window, no dialog
    title: str = ""              # the dialog's heading
    body: str = ""               # the dialog's text
    details: str = ""            # one line per failed folder ("~/A: message"), or ""
    close_button: bool = False   # offer "Close Window" next to "OK" (some folders were done)


def _folders(n):
    return "1 folder" if n == 1 else f"{n} folders"


def _lines(results):
    return "\n".join(f"{tilde(r.folder)}: {r.message}" for r in results if not r.ok)


def summarize(results):
    """(title, details) for a list of FolderResult: details has one line per failed folder."""
    failed = sum(1 for r in results if not r.ok)
    if not results:
        return "No folders were changed", ""
    if not failed:
        return f"Applied to {_folders(len(results))}", ""
    if failed == len(results):
        title = ("Could not apply to the folder" if failed == 1
                 else f"Could not apply to any of the {failed} folders")
        return title, _lines(results)
    return f"Applied to {len(results) - failed} of {len(results)}, {failed} failed", _lines(results)


def apply_outcome(results=None, error=None):
    """The Outcome of an Apply: results (the FolderResult list) or error (what apply_folders raised)."""
    if error is not None:
        if isinstance(error, RecordError):
            done = sum(1 for r in error.results if r.ok)
            return Outcome(False, "Icons set, but not recorded",
                           f"The icon was set on {done} of {_folders(len(error.results))}, but the manifest "
                           f"could not be saved: {error.error}. {RECORD_HINT}",
                           _lines(error.results))
        if isinstance(error, (ManifestError, ApplyError)):
            return Outcome(False, "Nothing was applied", str(error))
        return Outcome(False, "Something went wrong",
                       f"{type(error).__name__}: {error}. Some folders may already have their new icon; "
                       "'folder-symbols list' shows them.")
    results = list(results or [])
    title, details = summarize(results)
    if results and not details:
        return Outcome(True, title)
    partial = bool(details) and any(r.ok for r in results)
    body = ("The other folders have their new icon." if partial
            else "No folder was changed." if results else "")
    return Outcome(False, title, body, details, close_button=partial)


def apply_block_reason(has_symbol, n_dirs, running) -> Optional[str]:
    """Why Apply cannot be clicked now (its tooltip), or None when it can."""
    if running:
        return "Applying…"
    if not n_dirs:
        return "No folder selected"
    if not has_symbol:
        return "Choose a symbol first"
    return None


def apply_tooltip(n_dirs):
    """The tooltip of the Apply button when it can be clicked."""
    return ("Set this symbol and accent on the selected folder" if n_dirs == 1
            else f"Set this symbol and accent on the {n_dirs} selected folders")
