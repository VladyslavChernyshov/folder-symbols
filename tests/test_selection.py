"""Tests for folder_symbols.selection (no GTK, no Yaru required)."""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).parent.parent

from folder_symbols.selection import (
    normalise_paths,
    subtitle_text,
    tooltip_text,
)


# ---------------------------------------------------------------------------
# normalise_paths
# ---------------------------------------------------------------------------

def test_plain_absolute_path(tmp_path):
    d = tmp_path / "alpha"
    d.mkdir()
    dirs, ignored = normalise_paths([str(d)])
    assert dirs == [str(d)]
    assert ignored == 0


def test_plain_relative_path(tmp_path, monkeypatch):
    d = tmp_path / "beta"
    d.mkdir()
    monkeypatch.chdir(tmp_path)
    dirs, ignored = normalise_paths(["beta"])
    assert dirs == [str(d)]
    assert ignored == 0


def test_file_uri(tmp_path):
    d = tmp_path / "gamma"
    d.mkdir()
    uri = "file://" + str(d)
    dirs, ignored = normalise_paths([uri])
    assert dirs == [str(d)]
    assert ignored == 0


def test_percent_encoded_uri(tmp_path):
    d = tmp_path / "My Music"
    d.mkdir()
    encoded = "file://" + quote(str(d))
    dirs, ignored = normalise_paths([encoded])
    assert dirs == [str(d)]
    assert ignored == 0


def test_file_ignored(tmp_path):
    f = tmp_path / "readme.txt"
    f.write_text("hello")
    dirs, ignored = normalise_paths([str(f)])
    assert dirs == []
    assert ignored == 1


def test_nonexistent_ignored(tmp_path):
    dirs, ignored = normalise_paths([str(tmp_path / "does_not_exist")])
    assert dirs == []
    assert ignored == 1


def test_duplicate_silent(tmp_path):
    """Duplicate paths are dropped silently: ignored_count stays 0."""
    d = tmp_path / "delta"
    d.mkdir()
    dirs, ignored = normalise_paths([str(d), str(d)])
    assert dirs == [str(d)]
    assert ignored == 0


def test_order_preserved(tmp_path):
    names = ["cc", "aa", "bb"]
    for n in names:
        (tmp_path / n).mkdir()
    paths = [str(tmp_path / n) for n in names]
    dirs, ignored = normalise_paths(paths)
    assert dirs == paths
    assert ignored == 0


def test_empty_input():
    dirs, ignored = normalise_paths([])
    assert dirs == []
    assert ignored == 0


def test_mixed_valid_and_invalid(tmp_path):
    d1 = tmp_path / "d1"; d1.mkdir()
    d2 = tmp_path / "d2"; d2.mkdir()
    f  = tmp_path / "f.txt"; f.write_text("x")
    dirs, ignored = normalise_paths([str(d1), str(f), str(d2)])
    assert dirs == [str(d1), str(d2)]
    assert ignored == 1


# ---------------------------------------------------------------------------
# subtitle_text
# ---------------------------------------------------------------------------

def test_subtitle_empty():
    assert subtitle_text([], 0) == "No folder selected"


def test_subtitle_one_folder(isolated_home):
    music = isolated_home / "Music"
    music.mkdir()
    dirs, ignored = normalise_paths([str(music)])
    result = subtitle_text(dirs, len(dirs) + ignored)
    assert result == "Music · ~/Music"


def test_subtitle_home_itself(isolated_home):
    dirs, ignored = normalise_paths([str(isolated_home)])
    result = subtitle_text(dirs, len(dirs) + ignored)
    # basename of home is the temp dir name; display path should be "~"
    name = isolated_home.name
    assert result == f"{name} · ~"


def test_subtitle_several_folders(tmp_path):
    names = ["d1", "d2", "d3"]
    paths = []
    for n in names:
        d = tmp_path / n
        d.mkdir()
        paths.append(str(d))
    dirs, ignored = normalise_paths(paths)
    assert subtitle_text(dirs, len(dirs) + ignored) == "3 folders"


def test_subtitle_some_ignored(tmp_path):
    d1 = tmp_path / "good1"; d1.mkdir()
    d2 = tmp_path / "good2"; d2.mkdir()
    f  = tmp_path / "bad.txt"; f.write_text("x")
    dirs, ignored = normalise_paths([str(d1), str(f), str(d2)])
    assert subtitle_text(dirs, len(dirs) + ignored) == "2 of 3 selected items are folders"


def test_subtitle_all_ignored(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("x")
    dirs, ignored = normalise_paths([str(f1), str(f2)])
    assert subtitle_text(dirs, len(dirs) + ignored) == "0 of 2 selected items are folders"


def test_subtitle_duplicate_no_ignored_msg(isolated_home):
    """Passing the same folder twice must not trigger the 'X of Y' ignored message."""
    music = isolated_home / "Music"
    music.mkdir()
    dirs, ignored = normalise_paths([str(music), str(music)])
    result = subtitle_text(dirs, len(dirs) + ignored)
    assert result == "Music · ~/Music"


# ---------------------------------------------------------------------------
# tooltip_text
# ---------------------------------------------------------------------------

def test_tooltip_empty():
    assert tooltip_text([]) == ""


def test_tooltip_single(tmp_path):
    d = tmp_path / "Jazz"
    d.mkdir()
    dirs, _ = normalise_paths([str(d)])
    assert tooltip_text(dirs) == "Jazz"


def test_tooltip_multiple(tmp_path):
    names = ["Aaa", "Bbb", "Ccc"]
    paths = []
    for n in names:
        d = tmp_path / n
        d.mkdir()
        paths.append(str(d))
    dirs, _ = normalise_paths(paths)
    assert tooltip_text(dirs) == "Aaa\nBbb\nCcc"


# ---------------------------------------------------------------------------
# gi isolation: CLI modules must never import gi
# ---------------------------------------------------------------------------

def test_cli_modules_do_not_import_gi():
    """Importing CLI/store/apply modules in a fresh process must not pull in gi."""
    code = (
        "import folder_symbols.cli, folder_symbols.store, folder_symbols.apply;"
        "import sys; assert 'gi' not in sys.modules,"
        " f'gi was imported: {[k for k in sys.modules if k.startswith(\"gi\")]}'"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# folder-symbols-gui: friendly error when gi is missing
# ---------------------------------------------------------------------------

def test_gui_missing_gi_error(tmp_path):
    """folder-symbols-gui prints a helpful message and exits 1 when gi is unavailable."""
    gi_stub = tmp_path / "gi" / "__init__.py"
    gi_stub.parent.mkdir()
    gi_stub.write_text("raise ImportError('stubbed gi for test')\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")

    r = subprocess.run(
        [sys.executable, str(ROOT / "folder-symbols-gui")],
        env=env, capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "python3-gi" in r.stderr


# ---------------------------------------------------------------------------
# GUI import smoke test (skipped when gi or display is unavailable)
# ---------------------------------------------------------------------------

def test_gui_modules_importable():
    """GUI modules can be imported when gi and a display are present."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("no display available")
    try:
        import gi  # noqa: F401
    except ImportError:
        pytest.skip("PyGObject not installed")
    import folder_symbols.gui.application  # noqa: F401
    import folder_symbols.gui.window  # noqa: F401
