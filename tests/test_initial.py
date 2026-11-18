"""The window's initial state from the manifest (folder_symbols/initial.py): no GTK, no gio, temporary
directories and the temporary $HOME / $XDG_DATA_HOME from conftest only."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from folder_symbols import store
from folder_symbols.gallery import Symbol
from folder_symbols.initial import (InitialState, initial_state, read_manifest, recorded_folders,
                                    resolve_symbol)
from folder_symbols.selection import resolve_selection
from folder_symbols.store import Recipe

ROOT = Path(__file__).parent.parent

COMMUNITY = Symbol("community", "apps", "/syms/apps/community-symbolic.svg")
STARRED = Symbol("starred", "status", "/syms/status/starred-symbolic.svg")
SYMBOLS = [COMMUNITY, STARRED]


@pytest.fixture
def folders(isolated_home):
    """make('Music', 'Work') -> the normalised folders, created under the temporary $HOME."""
    def make(*names):
        paths = []
        for n in names:
            (isolated_home / n).mkdir(exist_ok=True)
            paths.append(str(isolated_home / n))
        dirs = list(resolve_selection(paths).dirs)
        return dirs
    return make


def record(**recipes):
    """record(Music=Recipe(...)) -> the manifest saved at store.manifest_path(), read back with read_manifest."""
    m = store.Manifest(store.manifest_path())
    for name, recipe in recipes.items():
        m.record(os.path.join(os.path.expanduser("~"), name), recipe)
    m.save()
    manifest, message = read_manifest()
    assert message is None
    return manifest


def write_raw(text):
    path = store.manifest_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ------------------------------------------------------------- the rules
def test_no_entry(folders):
    manifest = record(Other=Recipe("starred", "blue"))
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState()


def test_empty_manifest_file_missing(folders):
    manifest, message = read_manifest()
    assert message is None
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState()


def test_no_dirs():
    manifest = record(Music=Recipe("community", "purple"))
    assert initial_state([], manifest, SYMBOLS) == InitialState()


def test_one_folder_with_an_entry(folders):
    manifest = record(Music=Recipe("community", "purple"))
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState(COMMUNITY, "purple")


def test_several_folders_same_symbol_same_accent(folders):
    manifest = record(Music=Recipe("community", "sage"), Work=Recipe("community", "sage"))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState(COMMUNITY, "sage")


def test_several_folders_same_symbol_different_accents(folders):
    manifest = record(Music=Recipe("community", "sage"), Work=Recipe("community", "red"))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState(COMMUNITY, None)


def test_different_symbols(folders):
    manifest = record(Music=Recipe("community", "sage"), Work=Recipe("starred", "sage"))
    state = initial_state(folders("Music", "Work"), manifest, SYMBOLS)
    assert state.symbol is None
    assert state.accent == "sage"            # kept for the accent picker; unused without a symbol
    assert state.message is None


def test_one_following_folder_gives_system(folders):
    manifest = record(Music=Recipe("community", store.SYSTEM_ACCENT))
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState(COMMUNITY, "system")


def test_several_following_folders_give_system(folders):
    manifest = record(Music=Recipe("community", "system"), Work=Recipe("community", "system", 1.3))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState(COMMUNITY, "system")


@pytest.mark.parametrize("pinned", ["orange", "sage"])
def test_following_and_pinned_give_no_accent(folders, pinned):
    """Even when the pinned accent is the one the system has now: following is not the same as pinned."""
    manifest = record(Music=Recipe("community", "system"), Work=Recipe("community", pinned))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState(COMMUNITY, None)


def test_following_with_different_symbols_keeps_system_for_the_picker(folders):
    manifest = record(Music=Recipe("community", "system"), Work=Recipe("starred", "system"))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState(None, "system")


def test_different_symbols_and_accents(folders):
    manifest = record(Music=Recipe("community", "sage"), Work=Recipe("starred", "red"))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState()


def test_one_with_an_entry_one_without(folders):
    manifest = record(Music=Recipe("community", "purple"))
    assert initial_state(folders("Music", "Work"), manifest, SYMBOLS) == InitialState()


def test_symbol_not_in_the_gallery_is_like_no_entry(folders):
    manifest = record(Music=Recipe("nosuch", "purple"))
    state = initial_state(folders("Music"), manifest, SYMBOLS, symbols_dir="/syms")
    assert (state.symbol, state.accent) == (None, None)
    assert state.message == "recorded symbol not found in /syms, showing none: nosuch (~/Music)"


def test_missing_symbol_with_others_found_is_like_one_without_entry(folders):
    manifest = record(Music=Recipe("community", "purple"), Work=Recipe("nosuch", "purple"))
    state = initial_state(folders("Music", "Work"), manifest, SYMBOLS)
    assert (state.symbol, state.accent) == (None, None)
    assert "nosuch (~/Work)" in state.message


def test_two_missing_symbols_give_one_line(folders):
    manifest = record(Music=Recipe("nosuch", "purple"), Work=Recipe("gone", "red"))
    state = initial_state(folders("Music", "Work"), manifest, SYMBOLS)
    assert "\n" not in state.message
    assert "nosuch (~/Music)" in state.message and "gone (~/Work)" in state.message


def test_unusable_entry_is_like_no_entry(folders):
    write_raw(json.dumps({"schema_version": 1,
                          "folders": [{"path": "Music", "recipe": {"symbol": "community"}}]}))
    manifest, message = read_manifest()
    assert message is None
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState()


# ------------------------------------------------------------- the recorded symbol
def symbol_tree(tmp_path):
    root = tmp_path / "symbols"
    (root / "apps").mkdir(parents=True)
    (root / "legacy").mkdir()
    real = root / "apps" / "community-symbolic.svg"
    real.write_text("<svg/>")
    (root / "legacy" / "community-symbolic.svg").symlink_to(real)
    return root, Symbol("community", "apps", str(real))


def test_path_form_symbol(folders, tmp_path):
    root, gallery_symbol = symbol_tree(tmp_path)
    manifest = record(Music=Recipe(gallery_symbol.path, "blue"))
    assert initial_state(folders("Music"), manifest, [gallery_symbol]) == InitialState(gallery_symbol, "blue")


def test_path_form_symbol_through_a_symlinked_duplicate(folders, tmp_path):
    root, gallery_symbol = symbol_tree(tmp_path)
    manifest = record(Music=Recipe(str(root / "legacy" / "community-symbolic.svg"), "blue"))
    assert initial_state(folders("Music"), manifest, [gallery_symbol]).symbol == gallery_symbol


def test_path_form_symbol_from_another_directory_is_not_found(folders, tmp_path):
    root, gallery_symbol = symbol_tree(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / "community-symbolic.svg").write_text("<svg/>")
    manifest = record(Music=Recipe(str(other / "community-symbolic.svg"), "blue"))
    state = initial_state(folders("Music"), manifest, [gallery_symbol])
    assert state.symbol is None
    assert str(other / "community-symbolic.svg") in state.message


def test_resolve_symbol_by_name_and_path():
    by_name = {s.name: s for s in SYMBOLS}
    assert resolve_symbol("starred", by_name) == STARRED
    assert resolve_symbol("nosuch", by_name) is None
    assert resolve_symbol("/elsewhere/nosuch-symbolic.svg", by_name) is None


# ------------------------------------------------------------- reading the manifest
@pytest.mark.parametrize("text, why", [("{not json", "not valid JSON"), ("[]", "not a JSON object")])
def test_damaged_manifest_counts_as_no_entries(folders, text, why):
    write_raw(text)
    manifest, message = read_manifest()
    assert manifest is None
    assert why in message and "recorded icons are ignored" in message and "\n" not in message
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_manifest_counts_as_no_entries():
    path = write_raw('{"schema_version": 1, "folders": []}')
    os.chmod(path, 0)
    try:
        manifest, message = read_manifest()
    finally:
        os.chmod(path, 0o644)
    assert manifest is None
    assert message.startswith("cannot read ")


def test_newer_schema_is_read(folders):
    write_raw(json.dumps({"schema_version": store.SCHEMA_VERSION + 1, "future": True,
                          "folders": [{"path": "Music", "recipe": {"symbol": "community", "accent": "red"}}]}))
    manifest, message = read_manifest()
    assert message is None
    assert initial_state(folders("Music"), manifest, SYMBOLS) == InitialState(COMMUNITY, "red")


def test_folder_outside_home_uses_an_absolute_key(tmp_path_factory, isolated_home):
    outside = tmp_path_factory.mktemp("outside")
    assert not str(outside).startswith(str(isolated_home) + os.sep)
    m = store.Manifest(store.manifest_path())
    m.record(str(outside), Recipe("starred", "olive"))
    m.save()
    with open(store.manifest_path(), encoding="utf-8") as f:
        assert json.load(f)["folders"][0]["path"] == str(outside)
    manifest, _ = read_manifest()
    dirs = list(resolve_selection([str(outside)]).dirs)
    assert initial_state(dirs, manifest, SYMBOLS) == InitialState(STARRED, "olive")


def test_second_launch_with_other_paths(folders):
    record(Music=Recipe("community", "purple"), Work=Recipe("starred", "red"))
    first = initial_state(folders("Music"), read_manifest()[0], SYMBOLS)
    second = initial_state(folders("Work"), read_manifest()[0], SYMBOLS)
    third = initial_state(folders("Docs"), read_manifest()[0], SYMBOLS)
    assert first == InitialState(COMMUNITY, "purple")
    assert second == InitialState(STARRED, "red")
    assert third == InitialState()


def test_second_launch_rereads_a_changed_manifest(folders):
    record(Music=Recipe("community", "purple"))
    assert initial_state(folders("Music"), read_manifest()[0], SYMBOLS).symbol == COMMUNITY
    record(Music=Recipe("starred", "purple"))          # e.g. `apply` ran in between
    assert initial_state(folders("Music"), read_manifest()[0], SYMBOLS).symbol == STARRED


def test_reading_writes_nothing(isolated_home):
    data = Path(store.data_dir())
    assert not data.exists()
    manifest, message = read_manifest()
    assert message is None and manifest.entries() == []
    assert not data.exists()                            # no directory, manifest or lock file created
    write_raw('{"schema_version": 1, "folders": []}')
    before = sorted(os.listdir(data))
    read_manifest()
    assert sorted(os.listdir(data)) == before == ["manifest.json"]


def test_initial_module_does_not_import_gi():
    code = ("import folder_symbols.initial, sys;"
            "assert 'gi' not in sys.modules, 'gi was imported'")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------------- the folders Reset acts on

def test_recorded_folders_keeps_the_selection_order_and_skips_folders_without_an_entry(folders):
    manifest = record(Work=Recipe("community", "sage"), Music=Recipe("starred", "system"))
    dirs = folders("Work", "Other", "Music")
    assert recorded_folders(dirs, manifest) == [dirs[0], dirs[2]]
    assert recorded_folders(folders("Other"), manifest) == []


def test_recorded_folders_without_a_usable_manifest(folders):
    assert recorded_folders(folders("Music"), None) == []
