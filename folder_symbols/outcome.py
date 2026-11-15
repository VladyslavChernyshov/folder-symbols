"""What the window does after Apply or Reset (no GTK): close, or show a dialog with a summary and the
failed folders; the buttons' state; the Reset confirmation. Works on apply.FolderResult lists and the
errors apply_folders and reset_folders raise. Also the texts of Clean up (store.CleanupPlan and
store.CleanupResult)."""
import dataclasses
import functools
from typing import Optional

from .apply import ApplyError, RecordError
from .selection import MAX_LISTED, tilde
from .store import ManifestError


@dataclasses.dataclass(frozen=True)
class Wording:
    """The texts of one action; {n}, {done}, {total} and {error} are filled in."""
    done_one: str                # all ok, one folder
    done_many: str               # all ok, several
    partial: str                 # "{done} of {total}, {failed} failed"
    partial_body: str
    failed_one: str
    failed_many: str
    nothing: str                 # an error before anything was touched
    record_title: str
    record_body: str
    unexpected_body: str


APPLY = Wording(
    done_one="Applied to 1 folder", done_many="Applied to {n} folders",
    partial="Applied to {done} of {total}, {failed} failed",
    partial_body="The other folders have their new icon.",
    failed_one="Could not apply to the folder", failed_many="Could not apply to any of the {n} folders",
    nothing="Nothing was applied",
    record_title="Icons set, but not recorded",
    record_body="The icon was set on {done} of {total}, but the manifest could not be saved: {error}. "
                "'folder-symbols list' and 'reset --all' will not see them.",
    unexpected_body="{error}. Some folders may already have their new icon; 'folder-symbols list' shows them.",
)
RESET = Wording(
    done_one="Reset 1 folder", done_many="Reset {n} folders",
    partial="Reset {done} of {total}, {failed} failed",
    partial_body="The other folders have their normal icon again.",
    failed_one="Could not reset the folder", failed_many="Could not reset any of the {n} folders",
    nothing="Nothing was reset",
    record_title="Icons reset, but not recorded",
    record_body="The icon was reset on {done} of {total}, but the manifest could not be saved: {error}. "
                "'folder-symbols list' still shows them, as 'no icon'.",
    unexpected_body="{error}. Some folders may already have their normal icon again; 'folder-symbols list' "
                    "shows them.",
)


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


def summarize(results, wording=APPLY):
    """(title, details) for a list of FolderResult: details has one line per failed folder."""
    failed = sum(1 for r in results if not r.ok)
    if not results:
        return "No folders were changed", ""
    if not failed:
        return (wording.done_one if len(results) == 1 else wording.done_many.format(n=len(results))), ""
    if failed == len(results):
        title = wording.failed_one if failed == 1 else wording.failed_many.format(n=failed)
        return title, _lines(results)
    return wording.partial.format(done=len(results) - failed, total=len(results), failed=failed), _lines(results)


def run_outcome(wording, results=None, error=None):
    """The Outcome of an Apply or Reset: results (the FolderResult list) or error (what was raised)."""
    if error is not None:
        if isinstance(error, RecordError):
            done = sum(1 for r in error.results if r.ok)
            return Outcome(False, wording.record_title,
                           wording.record_body.format(done=done, total=_folders(len(error.results)),
                                                      error=error.error),
                           _lines(error.results))
        if isinstance(error, (ManifestError, ApplyError)):
            return Outcome(False, wording.nothing, str(error))
        return Outcome(False, "Something went wrong",
                       wording.unexpected_body.format(error=f"{type(error).__name__}: {error}"))
    results = list(results or [])
    title, details = summarize(results, wording)
    if results and not details:
        return Outcome(True, title)
    partial = bool(details) and any(r.ok for r in results)
    body = wording.partial_body if partial else "No folder was changed." if results else ""
    return Outcome(False, title, body, details, close_button=partial)


apply_outcome = functools.partial(run_outcome, APPLY)
reset_outcome = functools.partial(run_outcome, RESET)


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


def reset_button_state(n_dirs, n_recorded, running):
    """(label, sensitive, tooltip) of the Reset button: n_dirs selected folders, n_recorded of them with a
    manifest entry (the ones Reset acts on)."""
    if n_dirs > 1 and n_recorded:
        label = f"Reset {n_recorded}" if n_recorded == n_dirs else f"Reset {n_recorded} of {n_dirs}"
    else:
        label = "Reset"
    if running:
        return label, False, "Working…"
    if not n_dirs:
        return label, False, "No folder selected"
    if not n_recorded:
        return label, False, ("This folder has no icon from Folder Symbols" if n_dirs == 1
                              else "None of the selected folders has an icon from Folder Symbols")
    if n_dirs == 1:
        return label, True, "Give the folder its normal icon again"
    if n_recorded == n_dirs:
        return label, True, f"Give the {n_dirs} selected folders their normal icon again"
    if n_recorded == 1:
        return label, True, "Give the one folder with an icon from Folder Symbols its normal icon again"
    return label, True, f"Give the {n_recorded} folders with an icon from Folder Symbols their normal icon again"


def reset_confirmation(folders):
    """(heading, body, details) of the question asked before resetting several folders."""
    return (f"Reset the icons of {len(folders)} folders?", "They get the normal folder icon of the theme again.",
            "\n".join(tilde(f) for f in folders))


# ---------------------------------------------------------------- Clean up
@dataclasses.dataclass(frozen=True)
class CleanupDialog:
    """What a click on Clean up shows: a question (confirm: Cancel and Remove) or a notice (OK)."""
    heading: str
    body: str
    details: str = ""            # the folders to forget, one per line
    confirm: bool = False


@dataclasses.dataclass(frozen=True)
class CleanupOutcome:
    """After Remove, or an error at any step: a toast (success), else a dialog."""
    toast: str = ""
    title: str = ""
    body: str = ""


def cleanup_enabled(running):
    """The menu item works on the whole manifest: the selection does not matter."""
    return not running


def _entries(n):
    return "1 entry" if n == 1 else f"{n} entries"


def cleanup_notes(plan):
    """The lines about entries that were not checked (outside $HOME) or could not be checked."""
    notes = []
    if plan.skipped:
        notes.append("1 folder outside your home was not checked." if plan.skipped == 1
                     else f"{plan.skipped} folders outside your home were not checked.")
    if plan.unknown:
        n = len(plan.unknown)
        notes.append("1 entry was kept because its folder could not be checked." if n == 1
                     else f"{n} entries were kept because their folders could not be checked.")
    return notes


def listed(paths):
    """The paths from ~, one per line, at most MAX_LISTED of them, then "... and N more"."""
    lines = [tilde(p) for p in paths[:MAX_LISTED]]
    if len(paths) > MAX_LISTED:
        lines.append(f"... and {len(paths) - MAX_LISTED} more")
    return "\n".join(lines)


def cleanup_dialog(plan):
    notes = cleanup_notes(plan)
    if not plan.stale:
        first = ("No folders are recorded." if not plan.total else
                 "Every checked folder still exists." if notes else "Every recorded folder still exists.")
        return CleanupDialog("Nothing to clean up", "\n\n".join([first, *notes]))
    n = len(plan.stale)
    heading = ("Remove 1 entry for a folder that no longer exists?" if n == 1
               else f"Remove {n} entries for folders that no longer exist?")
    body = "The entries are only forgotten: no icon files are deleted and no folder's icon is changed."
    return CleanupDialog(heading, "\n\n".join([body, *notes]), listed([e.folder for e in plan.stale]), True)


def cleanup_outcome(result=None, error=None):
    if error is not None:
        if isinstance(error, ManifestError):
            return CleanupOutcome(title="Nothing was cleaned up", body=str(error))
        if isinstance(error, OSError):
            return CleanupOutcome(title="Nothing was cleaned up",
                                  body=f"The manifest could not be saved: {error}. Nothing was changed.")
        return CleanupOutcome(title="Something went wrong",
                              body=f"{type(error).__name__}: {error}. Nothing was changed.")
    removed, asked = len(result.removed), len(result.removed) + len(result.kept)
    if not removed:
        return CleanupOutcome(title="Nothing was removed",
                              body="When checked again, none of the folders was surely missing (a drive may have "
                                   "been mounted meanwhile), so every entry was kept.")
    if removed == asked:
        return CleanupOutcome(toast=f"Removed {_entries(removed)}")
    return CleanupOutcome(toast=f"Removed {removed} of {asked} entries")
