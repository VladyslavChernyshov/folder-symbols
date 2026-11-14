"""Tests for folder_symbols.selection (no GTK, no Yaru required)."""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).parent.parent

from folder_symbols.selection import (
    launch_argv,
    normalise_paths,
    resolve_selection,
    selection_error,
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


# ---------------------------------------------------------------------------
# resolve_selection, selection_error, launch_argv: the launcher's path check
# ---------------------------------------------------------------------------

def _error_lines(*lines):
    return "\n".join(["folder-symbols-gui: no existing folder among the given paths",
                      *[f"  {line}" for line in lines]])


def test_all_bad_paths_error(tmp_path):
    f = tmp_path / "notes.txt"; f.write_text("x")
    missing = tmp_path / "nope"
    s = resolve_selection([str(missing), str(f)])
    assert s.dirs == ()
    assert s.rejected == ((str(missing), "not found"), (str(f), "not a folder"))
    assert selection_error(s) == _error_lines(f"{missing}: not found", f"{f}: not a folder")
    assert launch_argv(["prog", str(missing), str(f)]) == (None, selection_error(s))


def test_one_good_plus_bad_no_error(tmp_path):
    d = tmp_path / "good"; d.mkdir()
    f = tmp_path / "notes.txt"; f.write_text("x")
    s = resolve_selection([str(tmp_path / "nope"), str(d), str(f)])
    assert s.dirs == (str(d),)
    assert s.total == 3
    assert selection_error(s) is None


def test_files_only_error(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("x")
    s = resolve_selection([str(f1), str(f2)])
    assert selection_error(s) == _error_lines(f"{f1}: not a folder", f"{f2}: not a folder")


def test_file_uris_resolved(tmp_path):
    d = tmp_path / "My Music"; d.mkdir()
    missing = tmp_path / "Lost Album"
    s = resolve_selection(["file://" + quote(str(d)), "file://" + quote(str(missing))])
    assert s.dirs == (str(d),)
    assert s.rejected == ((str(missing), "not found"),)


def test_duplicates_merged_good_and_bad(tmp_path):
    d = tmp_path / "a"; d.mkdir()
    missing = tmp_path / "gone"
    s = resolve_selection([str(d), str(d) + "/", "file://" + str(d), str(missing), str(missing) + "/"])
    assert s.dirs == (str(d),)
    assert s.rejected == ((str(missing), "not found"),)
    assert s.total == 2
    assert normalise_paths([str(missing), str(missing)]) == ([], 1)


def test_symlink_to_folder_kept_as_link(tmp_path):
    d = tmp_path / "real"; d.mkdir()
    link = tmp_path / "link"; link.symlink_to(d)
    s = resolve_selection([str(link)])
    assert s.dirs == (str(link),)
    assert selection_error(s) is None


def test_broken_symlink(tmp_path):
    link = tmp_path / "dangling"; link.symlink_to(tmp_path / "missing")
    s = resolve_selection([str(link)])
    assert selection_error(s) == _error_lines(f"{link}: broken link")


def test_path_under_a_file_not_found(tmp_path):
    f = tmp_path / "notes.txt"; f.write_text("x")
    s = resolve_selection([str(f / "x")])
    assert s.rejected == ((str(f / "x"), "not found"),)


def test_empty_string_alone_is_an_error():
    s = resolve_selection([""])
    assert (s.dirs, s.rejected, s.empty) == ((), (), True)
    assert selection_error(s) == _error_lines('"": empty argument')
    assert launch_argv(["prog", ""]) == (None, selection_error(s))


def test_empty_string_with_good_is_skipped(tmp_path, monkeypatch):
    d = tmp_path / "good"; d.mkdir()
    monkeypatch.chdir(tmp_path)                       # "" must not become the cwd
    s = resolve_selection(["", str(d)])
    assert s.dirs == (str(d),)
    assert s.total == 1
    assert launch_argv(["prog", "", str(d)]) == (["prog", str(d)], None)


def test_error_listing_capped(tmp_path):
    missing = [str(tmp_path / f"m{i:02}") for i in range(15)]
    lines = selection_error(resolve_selection(missing)).split("\n")
    assert len(lines) == 1 + 10 + 1
    assert lines[1:11] == [f"  {m}: not found" for m in missing[:10]]
    assert lines[-1] == "  ... and 5 more"


def test_ten_rejected_not_capped(tmp_path):
    lines = selection_error(resolve_selection([str(tmp_path / f"m{i}") for i in range(10)])).split("\n")
    assert len(lines) == 11
    assert "more" not in lines[-1]


def test_non_file_uri_mapped_to_local_path(tmp_path):
    share = tmp_path / "gvfs" / "smb-share"; share.mkdir(parents=True)
    mapping = {"smb://host/share": str(share)}
    s = resolve_selection(["smb://host/share", "sftp://host/x"], local_path=mapping.get)
    assert s.dirs == (str(share),)
    assert s.rejected == (("sftp://host/x", "not a local folder"),)


def test_non_file_uri_without_local_path_rejected():
    s = resolve_selection(["sftp://host/x"])
    assert selection_error(s) == _error_lines("sftp://host/x: not a local folder")


def test_launch_argv_no_arguments_unchanged():
    assert launch_argv(["prog"]) == (["prog"], None)


def test_launch_argv_options_unchanged(tmp_path):
    argv = ["prog", "--help", str(tmp_path / "nope")]
    assert launch_argv(argv) == (argv, None)


def test_launch_argv_returns_resolved_paths(tmp_path, monkeypatch):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b b"; b.mkdir()
    f = tmp_path / "f.txt"; f.write_text("x")
    monkeypatch.chdir(tmp_path)
    argv, error = launch_argv(["prog", "a", str(f), "file://" + quote(str(b)), "a/"])
    assert error is None
    assert argv == ["prog", str(a), str(f), str(b)]
    assert normalise_paths(argv[1:]) == ([str(a), str(b)], 1)


def test_gui_launcher_bad_paths_exit_1(tmp_path):
    """folder-symbols-gui with only bad paths prints the error and exits 1 without opening a window. No
    display and no session bus, so a broken check fails here instead of opening a window or reaching a
    running instance."""
    try:
        import gi  # noqa: F401
    except ImportError:
        pytest.skip("PyGObject not installed")
    missing = tmp_path / "nope"
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["DBUS_SESSION_BUS_ADDRESS"] = "disabled:"
    r = subprocess.run([sys.executable, str(ROOT / "folder-symbols-gui"), str(missing)],
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
    assert r.stderr == _error_lines(f"{missing}: not found") + "\n"
