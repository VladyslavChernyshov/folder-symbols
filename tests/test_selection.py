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
    panel_title,
    panel_tooltip,
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
# panel_title
# ---------------------------------------------------------------------------

def test_title_empty():
    assert panel_title([]) == "No folder selected"


def test_title_one_folder(isolated_home):
    music = isolated_home / "Music"
    music.mkdir()
    dirs, _ = normalise_paths([str(music)])
    assert panel_title(dirs) == "Music"


def test_title_home_itself(isolated_home):
    dirs, _ = normalise_paths([str(isolated_home)])
    assert panel_title(dirs) == isolated_home.name


def test_title_root():
    assert panel_title(["/"]) == "/"


def test_title_several_folders(tmp_path):
    paths = []
    for n in ["d1", "d2", "d3"]:
        d = tmp_path / n
        d.mkdir()
        paths.append(str(d))
    dirs, _ = normalise_paths(paths)
    assert panel_title(dirs) == "3 folders"


def test_title_ignores_non_folders(tmp_path):
    d1 = tmp_path / "good1"; d1.mkdir()
    d2 = tmp_path / "good2"; d2.mkdir()
    f  = tmp_path / "bad.txt"; f.write_text("x")
    dirs, _ = normalise_paths([str(d1), str(f), str(d2)])
    assert panel_title(dirs) == "2 folders"


def test_title_all_ignored(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("x")
    dirs, _ = normalise_paths([str(f1), str(f2)])
    assert panel_title(dirs) == "No folder selected"


def test_title_duplicate(isolated_home):
    music = isolated_home / "Music"
    music.mkdir()
    dirs, _ = normalise_paths([str(music), str(music)])
    assert panel_title(dirs) == "Music"


# ---------------------------------------------------------------------------
# panel_tooltip
# ---------------------------------------------------------------------------

def test_tooltip_empty():
    assert panel_tooltip([], 0) == ""


def test_tooltip_single_under_home(isolated_home):
    jazz = isolated_home / "Music" / "Jazz"
    jazz.mkdir(parents=True)
    dirs, ignored = normalise_paths([str(jazz)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == "~/Music/Jazz"


def test_tooltip_home_itself(isolated_home):
    dirs, ignored = normalise_paths([str(isolated_home)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == "~"


def test_tooltip_outside_home_is_absolute(isolated_home, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    assert not str(outside).startswith(str(isolated_home) + os.sep)
    dirs, ignored = normalise_paths([str(outside)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == str(outside)


def test_tooltip_root():
    assert panel_tooltip(["/"], 1) == "/"


def test_tooltip_multiple(isolated_home):
    paths = []
    for n in ["Aaa", "Bbb", "Ccc"]:
        d = isolated_home / n
        d.mkdir()
        paths.append(str(d))
    dirs, ignored = normalise_paths(paths)
    assert panel_tooltip(dirs, len(dirs) + ignored) == "~/Aaa\n~/Bbb\n~/Ccc"


def test_tooltip_some_ignored(isolated_home):
    d1 = isolated_home / "good1"; d1.mkdir()
    d2 = isolated_home / "good2"; d2.mkdir()
    f  = isolated_home / "bad.txt"; f.write_text("x")
    dirs, ignored = normalise_paths([str(d1), str(f), str(d2)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == (
        "2 of 3 selected items are folders\n~/good1\n~/good2")


def test_tooltip_all_ignored(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("x")
    dirs, ignored = normalise_paths([str(f1), str(f2)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == "0 of 2 selected items are folders"


def test_tooltip_duplicate_no_ignored_line(isolated_home):
    """Passing the same folder twice must not add the 'X of Y' line."""
    music = isolated_home / "Music"
    music.mkdir()
    dirs, ignored = normalise_paths([str(music), str(music)])
    assert panel_tooltip(dirs, len(dirs) + ignored) == "~/Music"


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
    import folder_symbols.gui.header  # noqa: F401
