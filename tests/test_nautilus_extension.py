"""Tests for nautilus/folder_symbols_nautilus.py with fake gi/Nautilus modules (no GTK, no Yaru, no real process)."""
import ast
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
EXT = ROOT / "nautilus" / "folder_symbols_nautilus.py"


class FakeMenuItem:
    def __init__(self, name=None, label=None):
        self.name, self.label, self.handlers = name, label, []

    def connect(self, signal, callback, *args):
        self.handlers.append((signal, callback, args))

    def activate(self):
        for signal, callback, args in self.handlers:
            if signal == "activate":
                callback(self, *args)


def make_gi(available=("4.1",)):
    gi = types.ModuleType("gi")
    gi.required = []

    def require_version(namespace, version):
        gi.required.append((namespace, version))
        if version not in available:
            raise ValueError(f"Namespace {namespace} not available for version {version}")

    gi.require_version = require_version
    repo = types.ModuleType("gi.repository")
    repo.GObject = types.SimpleNamespace(GObject=type("GObject", (), {}))
    repo.Nautilus = types.SimpleNamespace(MenuProvider=type("MenuProvider", (), {}), MenuItem=FakeMenuItem)
    gi.repository = repo
    return gi, repo


def load(monkeypatch, path=EXT, available=("4.1",)):
    gi, repo = make_gi(available)
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    spec = importlib.util.spec_from_file_location("folder_symbols_nautilus_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.gi_required = gi.required
    return mod


class Location:
    def __init__(self, path):
        self.path = path

    def get_path(self):
        return self.path


class FakeFile:
    def __init__(self, path, is_dir):
        self.path, self.is_dir = path, is_dir

    def is_directory(self):
        return self.is_dir

    def get_location(self):
        return Location(self.path)


def folder(p):
    return FakeFile(p, True)


def file_(p):
    return FakeFile(p, False)


class Recorder:
    """Stands in for subprocess.Popen and threading.Thread: records calls, never starts anything."""

    def __init__(self):
        self.popen_calls, self.threads, self.waited = [], [], 0

    def popen(self, argv, **kwargs):
        self.popen_calls.append((argv, kwargs))
        rec = self

        class Proc:
            def wait(self_):
                rec.waited += 1
        return Proc()

    def thread(self, target=None, daemon=None):
        rec = self

        class T:
            def start(self_):
                rec.threads.append((target, daemon))
        return T()


@pytest.fixture
def gui(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "folder-symbols-gui"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("FOLDER_SYMBOLS_GUI", str(exe))
    return str(exe)


@pytest.fixture
def ext(monkeypatch, gui):
    mod = load(monkeypatch)
    rec = Recorder()
    monkeypatch.setattr(mod.subprocess, "Popen", rec.popen)
    monkeypatch.setattr(mod.threading, "Thread", rec.thread)
    mod.rec = rec
    return mod


def items(mod, files):
    return mod.FolderSymbolsMenuProvider().get_file_items(files)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def test_requires_nautilus_4_1(monkeypatch):
    mod = load(monkeypatch, available=("4.1", "4.0"))
    assert mod.gi_required == [("Nautilus", "4.1")]


def test_falls_back_to_nautilus_4_0(monkeypatch):
    mod = load(monkeypatch, available=("4.0",))
    assert mod.gi_required == [("Nautilus", "4.1"), ("Nautilus", "4.0")]


def test_no_nautilus_at_all_fails_to_load(monkeypatch):
    with pytest.raises(ValueError):
        load(monkeypatch, available=())


def test_extension_imports_only_stdlib_and_gi():
    tree = ast.parse(EXT.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert imported == {"os", "shutil", "subprocess", "sys", "threading", "gi",
                        "gi.repository.GObject", "gi.repository.Nautilus"}


# ---------------------------------------------------------------------------
# when the item is shown
# ---------------------------------------------------------------------------

def test_one_folder(ext, gui):
    [item] = items(ext, [folder("/home/u/Music")])
    assert item.name == "FolderSymbols::ChooseIcon"
    assert item.label == "Choose Icon…"
    item.activate()
    argv, kwargs = ext.rec.popen_calls[0]
    assert argv == [gui, "/home/u/Music"]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_several_folders(ext, gui):
    [item] = items(ext, [folder("/a"), folder("/b"), folder("/c")])
    item.activate()
    assert ext.rec.popen_calls[0][0] == [gui, "/a", "/b", "/c"]


def test_folder_and_file_both_passed_in_order(ext, gui):
    [item] = items(ext, [file_("/x.txt"), folder("/a")])
    item.activate()
    assert ext.rec.popen_calls[0][0] == [gui, "/x.txt", "/a"]


def test_only_files_no_item(ext):
    assert items(ext, [file_("/x.txt"), file_("/y.png")]) == []


def test_empty_selection_no_item(ext):
    assert items(ext, []) == []


def test_only_non_local_no_item(ext):
    assert items(ext, [folder(None), folder(None)]) == []


def test_non_local_folder_with_local_file_no_item(ext):
    assert items(ext, [folder(None), file_("/x.txt")]) == []


def test_non_local_items_are_skipped(ext, gui):
    [item] = items(ext, [folder(None), folder("/a"), file_(None)])
    item.activate()
    assert ext.rec.popen_calls[0][0] == [gui, "/a"]


def test_no_location_is_skipped(ext):
    f = folder("/a")
    f.get_location = lambda: None
    assert items(ext, [f]) == []


def test_menu_building_does_not_launch(ext):
    items(ext, [folder("/a")])
    assert ext.rec.popen_calls == []


# ---------------------------------------------------------------------------
# launching
# ---------------------------------------------------------------------------

def test_popen_is_not_waited_on_in_the_caller(ext):
    [item] = items(ext, [folder("/a")])
    item.activate()
    assert ext.rec.waited == 0
    [(target, daemon)] = ext.rec.threads
    assert daemon is True
    target()                     # the reaper thread is what waits
    assert ext.rec.waited == 1


def test_popen_oserror_does_not_escape(ext, capsys):
    def boom(*a, **k):
        raise OSError("permission denied")
    ext.subprocess.Popen = boom
    [item] = items(ext, [folder("/a")])
    item.activate()
    assert "could not start" in capsys.readouterr().err
    assert ext.rec.threads == []


# ---------------------------------------------------------------------------
# failures
# ---------------------------------------------------------------------------

def test_executable_not_found_hides_item_and_warns_once(ext, monkeypatch, capsys):
    monkeypatch.delenv("FOLDER_SYMBOLS_GUI")
    monkeypatch.setattr(ext.shutil, "which", lambda name: None)
    assert items(ext, [folder("/a")]) == []
    assert items(ext, [folder("/b")]) == []
    err = capsys.readouterr().err
    assert err.count("folder-symbols-gui not found") == 1


def test_exception_in_file_object_is_skipped(ext):
    class Bad(FakeFile):
        def is_directory(self):
            raise RuntimeError("gone")
    assert items(ext, [Bad("/a", True)]) == []


def test_exception_inside_extension_returns_no_items(ext, monkeypatch, capsys):
    def boom():
        raise RuntimeError("unexpected")
    monkeypatch.setattr(ext, "find_gui", boom)
    assert items(ext, [folder("/a")]) == []
    assert "unexpected" in capsys.readouterr().err


def test_non_iterable_files_returns_no_items(ext):
    assert items(ext, 42) == []


# ---------------------------------------------------------------------------
# finding the executable
# ---------------------------------------------------------------------------

def make_repo_with_symlink(tmp_path):
    repo = tmp_path / "repo"
    (repo / "nautilus").mkdir(parents=True)
    target = repo / "nautilus" / EXT.name
    target.write_text(EXT.read_text())
    wrapper = repo / "folder-symbols-gui"
    wrapper.write_text("#!/bin/sh\nexit 0\n")
    wrapper.chmod(0o755)
    ext_dir = tmp_path / "extensions"
    ext_dir.mkdir()
    link = ext_dir / EXT.name
    link.symlink_to(target)
    return link, wrapper


def test_symlinked_install_finds_repo_wrapper(tmp_path, monkeypatch):
    monkeypatch.delenv("FOLDER_SYMBOLS_GUI", raising=False)
    link, wrapper = make_repo_with_symlink(tmp_path)
    mod = load(monkeypatch, path=link)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/folder-symbols-gui")
    assert mod.find_gui() == str(wrapper)


def test_env_beats_symlink(tmp_path, monkeypatch, gui):
    link, _ = make_repo_with_symlink(tmp_path)
    mod = load(monkeypatch, path=link)
    assert mod.find_gui() == gui


def test_env_not_executable_is_ignored(tmp_path, monkeypatch):
    plain = tmp_path / "not-exec"
    plain.write_text("")
    monkeypatch.setenv("FOLDER_SYMBOLS_GUI", str(plain))
    mod = load(monkeypatch)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/folder-symbols-gui")
    assert mod.find_gui() == "/usr/bin/folder-symbols-gui"


def test_regular_file_uses_path(tmp_path, monkeypatch):
    """A packaged (non-symlinked) copy never looks next to itself, even if a wrapper happens to be there."""
    monkeypatch.delenv("FOLDER_SYMBOLS_GUI", raising=False)
    (tmp_path / "nautilus").mkdir()
    copy = tmp_path / "nautilus" / EXT.name
    copy.write_text(EXT.read_text())
    wrapper = tmp_path / "folder-symbols-gui"
    wrapper.write_text("#!/bin/sh\n")
    wrapper.chmod(0o755)
    mod = load(monkeypatch, path=copy)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    assert mod.find_gui() is None


def test_symlink_without_wrapper_uses_path(tmp_path, monkeypatch):
    monkeypatch.delenv("FOLDER_SYMBOLS_GUI", raising=False)
    link, wrapper = make_repo_with_symlink(tmp_path)
    wrapper.unlink()
    mod = load(monkeypatch, path=link)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/folder-symbols-gui")
    assert mod.find_gui() == "/usr/bin/folder-symbols-gui"
