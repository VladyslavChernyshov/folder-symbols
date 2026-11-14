"""What the window does after Apply (folder_symbols/outcome.py): no GTK, no gio, no files."""
import os
import subprocess
import sys

import pytest

from folder_symbols.apply import ApplyError, FolderResult, RecordError
from folder_symbols.outcome import Outcome, apply_block_reason, apply_outcome, apply_tooltip, summarize
from folder_symbols.store import ManifestError

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
    assert apply_tooltip(1) == "Set this symbol and accent on the selected folder"
    assert apply_tooltip(3) == "Set this symbol and accent on the 3 selected folders"


def test_outcome_module_does_not_import_gi():
    code = "import sys, folder_symbols.outcome; print('gi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
