"""What the window does after Apply, Reset and Clean up (folder_symbols/outcome.py): no GTK, no gio, no files."""
import os
import subprocess
import sys

import pytest

from folder_symbols.apply import ApplyError, FolderResult, RecordError
from folder_symbols.outcome import (REFRESH_HINT, RESET, CleanupDialog, CleanupOutcome, Outcome,
                                    apply_block_reason, apply_outcome, apply_tooltip, cleanup_dialog,
                                    cleanup_enabled, cleanup_outcome, reset_button_state, reset_confirmation,
                                    reset_outcome, summarize)
from folder_symbols.store import CleanupPlan, CleanupResult, Entry, ManifestError, Recipe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def home(*names):
    return [os.path.join(os.path.expanduser("~"), n) for n in names]


def ok(folder):
    return FolderResult(folder, True, "icon set")


def bad(folder, message="fake failure"):
    return FolderResult(folder, False, message)


# ------------------------------------------------------------- summarize
def test_summarize_empty():
    assert summarize([]) == ("No folders were changed", "")


@pytest.mark.parametrize("n, title", [(1, "Applied to 1 folder"), (5, "Applied to 5 folders")])
def test_summarize_all_ok(n, title):
    assert summarize([ok(f) for f in home(*map(str, range(n)))]) == (title, "")


def test_summarize_some_failed_lists_only_the_failed_folders_from_tilde():
    a, b, c, d, e = home("A", "B", "C", "D", "E")
    title, details = summarize([ok(a), ok(b), bad(c, "gio: permission denied"), ok(d), ok(e)])
    assert title == "Applied to 4 of 5, 1 failed"
    assert details == "~/C: gio: permission denied"


def test_summarize_one_folder_failed():
    [a] = home("Music")
    assert summarize([bad(a)]) == ("Could not apply to the folder", "~/Music: fake failure")


def test_summarize_all_failed_keeps_order_and_paths_outside_home(tmp_path):
    a, b = home("A", "B")
    outside = str(tmp_path / "Disk")
    title, details = summarize([bad(a, "one"), bad(outside, "two"), bad(b, "three")])
    assert title == "Could not apply to any of the 3 folders"
    assert details.splitlines() == ["~/A: one", f"{outside}: two", "~/B: three"]


# ------------------------------------------------------------- apply_outcome
def test_all_ok_closes_without_a_dialog():
    assert apply_outcome(results=[ok(f) for f in home("A", "B")]) == Outcome(True, "Applied to 2 folders")


def test_partial_failure_stays_open_and_offers_close_window():
    a, b = home("A", "B")
    o = apply_outcome(results=[ok(a), bad(b)])
    assert not o.close and o.close_button
    assert o.title == "Applied to 1 of 2, 1 failed" and o.details == "~/B: fake failure"
    assert "other folders have their new icon" in o.body


def test_all_failed_stays_open_with_ok_only():
    o = apply_outcome(results=[bad(f) for f in home("A", "B")])
    assert not o.close and not o.close_button
    assert o.title == "Could not apply to any of the 2 folders" and "No folder was changed" in o.body


def test_an_empty_result_does_not_close():
    o = apply_outcome(results=[])
    assert not o.close and not o.close_button and o.title == "No folders were changed"


@pytest.mark.parametrize("error", [ManifestError("manifest.json is damaged (oops)"),
                                   ApplyError("symbol 'x' not found in /syms")])
def test_errors_before_anything_was_set(error):
    o = apply_outcome(error=error)
    assert o == Outcome(False, "Nothing was applied", str(error))


def test_record_error_says_the_icons_were_set_but_not_recorded():
    a, b, c = home("A", "B", "C")
    o = apply_outcome(error=RecordError([ok(a), bad(b), ok(c)], PermissionError(13, "Permission denied")))
    assert not o.close and not o.close_button and o.title == "Icons set, but not recorded"
    assert "set on 2 of 3 folders" in o.body and "could not be saved" in o.body
    assert "Permission denied" in o.body and "'folder-symbols list'" in o.body
    assert o.details == "~/B: fake failure"


def test_an_unexpected_error_still_gives_a_dialog():
    o = apply_outcome(error=KeyError("boom"))
    assert not o.close and o.title == "Something went wrong" and "KeyError" in o.body


# ------------------------------------------------------------- the button
@pytest.mark.parametrize("has_symbol, n_dirs, running, reason", [
    (True, 1, False, None), (True, 5, False, None),
    (False, 1, False, "Choose a symbol first"), (True, 0, False, "No folder selected"),
    (False, 0, False, "No folder selected"),
    (True, 1, True, "Applying…"), (False, 0, True, "Applying…"),
])
def test_apply_block_reason(has_symbol, n_dirs, running, reason):
    assert apply_block_reason(has_symbol, n_dirs, running) == reason


def test_apply_tooltip():
    assert apply_tooltip(1) == ("Set this symbol and accent on the selected folder.\n"
                                "Files may need a refresh (F5) to show the new icon.")
    assert apply_tooltip(3) == ("Set this symbol and accent on the 3 selected folders.\n"
                                "Files may need a refresh (F5) to show the new icon.")


@pytest.mark.parametrize("n_dirs", [1, 2, 7])
def test_apply_tooltip_ends_with_the_refresh_hint(n_dirs):
    assert REFRESH_HINT == "Files may need a refresh (F5) to show the new icon."
    assert apply_tooltip(n_dirs).splitlines()[-1] == REFRESH_HINT


def test_only_the_active_apply_tooltip_has_the_refresh_hint():
    reasons = {apply_block_reason(s, n, r) for s in (True, False) for n in (0, 1, 3) for r in (True, False)}
    resets = {reset_button_state(n, k, r)[2] for n in (0, 1, 3) for k in range(n + 1) for r in (True, False)}
    assert None in reasons and all("F5" not in t for t in (reasons | resets) - {None})


def test_outcome_module_does_not_import_gi():
    code = "import sys, folder_symbols.outcome; print('gi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------- Reset
def test_reset_summaries():
    a, b, c, d, e = home("A", "B", "C", "D", "E")
    assert summarize([], RESET) == ("No folders were changed", "")
    assert summarize([ok(a)], RESET) == ("Reset 1 folder", "")
    assert summarize([ok(a), ok(b)], RESET) == ("Reset 2 folders", "")
    assert summarize([ok(a), ok(b), ok(c), bad(d, "not found, entry kept"), ok(e)], RESET) == \
        ("Reset 4 of 5, 1 failed", "~/D: not found, entry kept")
    assert summarize([bad(a)], RESET) == ("Could not reset the folder", "~/A: fake failure")
    assert summarize([bad(a), bad(b), bad(c)], RESET)[0] == "Could not reset any of the 3 folders"


def test_reset_outcomes():
    a, b = home("A", "B")
    assert reset_outcome(results=[ok(a), ok(b)]) == Outcome(True, "Reset 2 folders")
    o = reset_outcome(results=[ok(a), bad(b)])
    assert (o.close, o.close_button, o.title) == (False, True, "Reset 1 of 2, 1 failed")
    assert o.body == "The other folders have their normal icon again." and o.details == "~/B: fake failure"
    o = reset_outcome(results=[bad(a), bad(b)])
    assert (o.close, o.close_button, o.body) == (False, False, "No folder was changed.")
    assert reset_outcome(error=ManifestError("damaged")) == Outcome(False, "Nothing was reset", "damaged")


def test_reset_record_error_says_the_icons_were_reset_but_not_recorded():
    a, b = home("A", "B")
    o = reset_outcome(error=RecordError([ok(a), bad(b)], OSError(28, "No space left on device")))
    assert o.title == "Icons reset, but not recorded" and not o.close and not o.close_button
    assert "reset on 1 of 2 folders" in o.body and "No space left on device" in o.body
    assert "still shows them, as 'no icon'" in o.body and o.details == "~/B: fake failure"


def test_reset_unexpected_error():
    o = reset_outcome(error=RuntimeError("boom"))
    assert o.title == "Something went wrong" and "RuntimeError: boom" in o.body and "normal icon again" in o.body


def test_apply_texts_are_unchanged_by_the_reset_wording():
    a, b = home("A", "B")
    assert apply_outcome(results=[ok(a), bad(b)]).title == "Applied to 1 of 2, 1 failed"
    assert apply_outcome(error=ApplyError("x")).title == "Nothing was applied"
    assert "not recorded" in apply_outcome(error=RecordError([ok(a)], OSError("x"))).title


@pytest.mark.parametrize("n_dirs, n_recorded, running, expected", [
    (0, 0, False, ("Reset", False, "No folder selected")),
    (1, 1, False, ("Reset", True, "Give the folder its normal icon again")),
    (1, 0, False, ("Reset", False, "This folder has no icon from Folder Symbols")),
    (5, 5, False, ("Reset 5", True, "Give the 5 selected folders their normal icon again")),
    (5, 3, False, ("Reset 3 of 5", True,
                   "Give the 3 folders with an icon from Folder Symbols their normal icon again")),
    (5, 1, False, ("Reset 1 of 5", True,
                   "Give the one folder with an icon from Folder Symbols its normal icon again")),
    (5, 0, False, ("Reset", False, "None of the selected folders has an icon from Folder Symbols")),
    (5, 3, True, ("Reset 3 of 5", False, "Working…")),
    (1, 1, True, ("Reset", False, "Working…")),
])
def test_reset_button_state(n_dirs, n_recorded, running, expected):
    assert reset_button_state(n_dirs, n_recorded, running) == expected


def test_reset_confirmation(tmp_path):
    a, b = home("A", "My Files")
    heading, body, details = reset_confirmation([a, b, str(tmp_path / "X")])
    assert heading == "Reset the icons of 3 folders?" and "normal folder icon" in body
    assert details.splitlines() == ["~/A", "~/My Files", str(tmp_path / "X")]


# ------------------------------------------------------------- Clean up
def plan(stale=(), unknown=0, skipped=0, total=None):
    entries = tuple(Entry(f, Recipe("a", "red")) for f in stale)
    unk = tuple((Entry(f, Recipe("a", "red")), OSError(13, "Permission denied"))
                for f in home(*(f"U{i}" for i in range(unknown))))
    return CleanupPlan(entries, unk, skipped, len(entries) + unknown + skipped + 1 if total is None else total)


EXTERNAL_1 = "1 folder outside your home was not checked."
UNKNOWN_1 = "1 entry was kept because its folder could not be checked."
SAFE = "The entries are only forgotten: no icon files are deleted and no folder's icon is changed."


def test_cleanup_is_enabled_unless_busy():
    assert cleanup_enabled(False) is True and cleanup_enabled(True) is False


@pytest.mark.parametrize("p, body", [
    (plan(total=0), "No folders are recorded."),
    (plan(), "Every recorded folder still exists."),
    (plan(skipped=1), f"Every checked folder still exists.\n\n{EXTERNAL_1}"),
    (plan(skipped=3), "Every checked folder still exists.\n\n3 folders outside your home were not checked."),
    (plan(unknown=1), f"Every checked folder still exists.\n\n{UNKNOWN_1}"),
    (plan(unknown=2), "Every checked folder still exists.\n\n"
                      "2 entries were kept because their folders could not be checked."),
    (plan(skipped=1, unknown=1), f"Every checked folder still exists.\n\n{EXTERNAL_1}\n\n{UNKNOWN_1}"),
])
def test_cleanup_dialog_with_nothing_to_remove(p, body):
    assert cleanup_dialog(p) == CleanupDialog("Nothing to clean up", body, "", False)


def test_cleanup_dialog_asks_before_removing_one():
    [a] = home("Gone")
    assert cleanup_dialog(plan([a])) == CleanupDialog(
        "Remove 1 entry for a folder that no longer exists?", SAFE, "~/Gone", True)


def test_cleanup_dialog_lists_the_folders_with_the_notes():
    a, b, c = home("A", "B", "C d")
    d = cleanup_dialog(plan([a, b, c], unknown=1, skipped=1))
    assert d.heading == "Remove 3 entries for folders that no longer exist?" and d.confirm
    assert d.body == f"{SAFE}\n\n{EXTERNAL_1}\n\n{UNKNOWN_1}"
    assert d.details == "~/A\n~/B\n~/C d"


def test_cleanup_dialog_lists_at_most_ten_folders():
    folders = home(*(f"F{i:02}" for i in range(12)))
    d = cleanup_dialog(plan(folders))
    assert d.heading == "Remove 12 entries for folders that no longer exist?"
    assert d.details.splitlines() == [f"~/F{i:02}" for i in range(10)] + ["... and 2 more"]
    assert len(cleanup_dialog(plan(folders[:10])).details.splitlines()) == 10


def test_cleanup_dialog_shows_folders_outside_home_as_they_are():
    assert cleanup_dialog(plan(["/media/drive/Photos"])).details == "/media/drive/Photos"


@pytest.mark.parametrize("removed, kept, toast", [(1, 0, "Removed 1 entry"), (3, 0, "Removed 3 entries"),
                                                   (2, 1, "Removed 2 of 3 entries")])
def test_cleanup_outcome_success_is_a_toast(removed, kept, toast):
    folders = home(*(f"F{i}" for i in range(removed + kept)))
    result = CleanupResult(tuple(folders[:removed]), tuple(folders[removed:]))
    assert cleanup_outcome(result) == CleanupOutcome(toast=toast)


def test_cleanup_outcome_when_every_folder_came_back():
    assert cleanup_outcome(CleanupResult((), tuple(home("A", "B")))) == CleanupOutcome(
        title="Nothing was removed",
        body="When checked again, none of the folders was surely missing (a drive may have been mounted "
             "meanwhile), so every entry was kept.")


def test_cleanup_outcome_of_errors():
    assert cleanup_outcome(error=ManifestError("m.json is damaged (x); fix it")) == CleanupOutcome(
        title="Nothing was cleaned up", body="m.json is damaged (x); fix it")
    assert cleanup_outcome(error=OSError(28, "No space left on device")) == CleanupOutcome(
        title="Nothing was cleaned up",
        body="The manifest could not be saved: [Errno 28] No space left on device. Nothing was changed.")
    assert cleanup_outcome(error=RuntimeError("boom")) == CleanupOutcome(
        title="Something went wrong", body="RuntimeError: boom. Nothing was changed.")
