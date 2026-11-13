"""Tests for folder_symbols.gallery (no GTK; only the last test needs Yaru)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SYMBOLS_DIR
from folder_symbols.gallery import Symbol, categories, filter_symbols, list_symbols
from folder_symbols.symbols import default_symbols_dir, YARU_SYMBOLS

ROOT = Path(__file__).parent.parent


def touch(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    return p


def names(symbols):
    return [s.name for s in symbols]


# ---------------------------------------------------------------------------
# list_symbols
# ---------------------------------------------------------------------------

def test_name_category_and_path(tmp_path):
    p = touch(tmp_path, "actions/edit-copy-symbolic.svg")
    assert list_symbols(str(tmp_path)) == [Symbol("edit-copy", "actions", str(p))]


def test_category_is_first_level_subfolder(tmp_path):
    touch(tmp_path, "apps/sub/deeper/thing-symbolic.svg")
    assert list_symbols(str(tmp_path))[0].category == "apps"


def test_files_in_root_get_other_category(tmp_path):
    touch(tmp_path, "flat-symbolic.svg")
    assert list_symbols(str(tmp_path))[0].category == "other"


def test_symlinked_duplicate_listed_once_from_first_category(tmp_path):
    real = touch(tmp_path, "status/battery-symbolic.svg")
    (tmp_path / "devices").mkdir()
    os.symlink(real, tmp_path / "devices" / "battery-symbolic.svg")
    syms = list_symbols(str(tmp_path))
    assert names(syms) == ["battery"]
    assert syms[0].category == "devices"   # first in sorted order, as in the CLI


def test_name_clash_generic_symbols_wins(tmp_path):
    touch(tmp_path, "status/resources-symbolic.svg")
    touch(tmp_path, "generic-symbols/resources-symbolic.svg")
    syms = list_symbols(str(tmp_path))
    assert [(s.name, s.category) for s in syms] == [("resources", "generic-symbols")]


def test_ignores_other_files_and_broken_symlinks(tmp_path):
    touch(tmp_path, "actions/keep-symbolic.svg")
    touch(tmp_path, "actions/plain.svg")
    touch(tmp_path, "actions/note-symbolic.png")
    touch(tmp_path, "actions/readme.txt")
    os.symlink(tmp_path / "nowhere.svg", tmp_path / "actions" / "broken-symbolic.svg")
    assert names(list_symbols(str(tmp_path))) == ["keep"]


def test_sorted_case_insensitive(tmp_path):
    for n in ("beta", "Alpha", "gamma", "Delta"):
        touch(tmp_path, f"actions/{n}-symbolic.svg")
    assert names(list_symbols(str(tmp_path))) == ["Alpha", "beta", "Delta", "gamma"]


def test_empty_directory(tmp_path):
    assert list_symbols(str(tmp_path)) == []


def test_missing_directory(tmp_path):
    assert list_symbols(str(tmp_path / "missing")) == []


# ---------------------------------------------------------------------------
# categories and filter_symbols
# ---------------------------------------------------------------------------

SYMS = [
    Symbol("edit-copy", "actions", "/x/a"),
    Symbol("Edit-Paste", "actions", "/x/b"),
    Symbol("camera-photo", "devices", "/x/c"),
    Symbol("folder", "places", "/x/d"),
    Symbol("folder-music", "places", "/x/e"),
]


def test_categories_sorted_unique():
    assert categories(SYMS) == ["actions", "devices", "places"]
    assert categories([]) == []


def test_filter_empty_query_matches_all():
    assert filter_symbols(SYMS, "", None) == SYMS
    assert filter_symbols(SYMS, "   ", None) == SYMS


def test_filter_by_query():
    assert names(filter_symbols(SYMS, "folder", None)) == ["folder", "folder-music"]


def test_filter_query_case_insensitive_and_stripped():
    assert names(filter_symbols(SYMS, "  EDIT-p ", None)) == ["Edit-Paste"]
    assert names(filter_symbols(SYMS, "edit", None)) == ["edit-copy", "Edit-Paste"]


def test_filter_by_category():
    assert names(filter_symbols(SYMS, "", "places")) == ["folder", "folder-music"]


def test_filter_by_query_and_category():
    assert names(filter_symbols(SYMS, "o", "devices")) == ["camera-photo"]
    assert filter_symbols(SYMS, "folder", "actions") == []


def test_filter_no_matches():
    assert filter_symbols(SYMS, "zzz", None) == []
    assert filter_symbols(SYMS, "", "nonexistent") == []


# ---------------------------------------------------------------------------
# default_symbols_dir, gi isolation
# ---------------------------------------------------------------------------

def test_default_symbols_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("YARU_SYMBOLS_DIR", raising=False)
    assert default_symbols_dir() == YARU_SYMBOLS
    monkeypatch.setenv("YARU_SYMBOLS_DIR", "")
    assert default_symbols_dir() == YARU_SYMBOLS
    monkeypatch.setenv("YARU_SYMBOLS_DIR", str(tmp_path))
    assert default_symbols_dir() == str(tmp_path)


def test_gallery_module_does_not_import_gi():
    code = ("import folder_symbols.gallery, sys;"
            "assert 'gi' not in sys.modules, 'gi was imported'")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# real Yaru
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isdir(SYMBOLS_DIR), reason=f"no Yaru symbols in {SYMBOLS_DIR}")
def test_real_yaru_symbols():
    syms = list_symbols(SYMBOLS_DIR)
    assert len(syms) > 500
    assert len({s.name for s in syms}) == len(syms)
    assert {s.name: s.category for s in syms}["resources"] == "generic-symbols"
    assert "generic-symbols" in categories(syms)
