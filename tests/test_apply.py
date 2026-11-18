"""apply_folders: one recipe applied to several folders, shared by the CLI and the window. Everything runs
in the temporary home of the isolated_home fixture with a stubbed setter; gio itself is never run (the gio
wrappers are tested against a fake gio executable in the test's temporary directory)."""
import json, os, shutil, subprocess, sys, types

import pytest

from folder_symbols import apply as ap, cli, store, yaru
from folder_symbols.apply import NOT_FOUND, ApplyError, FolderResult, apply_folders, reset_folders
from folder_symbols.preview import PreviewSession
from folder_symbols.store import ManifestError, Recipe

SQUARE = '<rect x="3" y="3" width="10" height="10" fill="#222" opacity="0.5"/>'


class Setter:
    """A fake gio set: records calls, raises GioError for the folders in `fail`."""

    def __init__(self, *fail):
        self.fail, self.calls = set(fail), []

    def __call__(self, folder, uri):
        self.calls.append((folder, uri))
        if folder in self.fail:
            raise ap.GioError(f"fake failure on {folder}")


@pytest.fixture
def symbols_dir(tmp_path, svg):
    """A symbols tree with 'sq' and 'adaptive' (which has an entry in overrides.json)."""
    d = tmp_path / "symbols" / "actions"
    d.mkdir(parents=True)
    for name in ("sq", "adaptive"):
        (d / f"{name}-symbolic.svg").write_text(open(svg(name, SQUARE, 'viewBox="0 0 16 16"')).read())
    return str(tmp_path / "symbols")


def folders(home, *names):
    out = []
    for n in names:
        (home / n).mkdir(parents=True, exist_ok=True)
        out.append(str(home / n))
    return out


def icon_files():
    d = store.icons_dir()
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def read(path):
    with open(path, "rb") as f:
        return f.read()


# ------------------------------------------------------------- the happy path
def test_one_icon_is_built_and_set_on_every_folder(isolated_home, symbols_dir):
    dirs = folders(isolated_home, "A", "B", "C")
    setter = Setter()
    results = apply_folders(dirs, "sq", "sage", dark=True, symbols_dir=symbols_dir, set_icon=setter)
    icon = os.path.join(store.icons_dir(), "Yaru-sage-dark-sq.svg")
    assert results == [FolderResult(d, True, "icon set") for d in dirs]
    assert setter.calls == [(d, "file://" + icon) for d in dirs]
    assert icon_files() == ["Yaru-sage-dark-sq.svg"]
    sym = os.path.join(symbols_dir, "actions", "sq-symbolic.svg")
    assert [(e.folder, e.recipe) for e in store.entries()] == [(d, Recipe(sym, "sage")) for d in dirs]


@pytest.mark.parametrize("accent, dark, variant", [
    ("sage", False, "Yaru-sage"), ("sage", True, "Yaru-sage-dark"), ("orange", False, "Yaru"),
    ("orange", True, "Yaru-dark"), ("mate", False, "Yaru-mate"), ("mate", True, "Yaru-mate-dark"),
])
def test_dark_picks_the_style_of_the_icon(isolated_home, symbols_dir, accent, dark, variant):
    [d] = folders(isolated_home, "A")
    apply_folders([d], "sq", accent, dark=dark, symbols_dir=symbols_dir, set_icon=Setter())
    assert icon_files() == [f"{variant}-sq.svg"]
    assert store.lookup(d).recipe.accent == accent


@pytest.mark.parametrize("name", ["sq", "adaptive"])
@pytest.mark.parametrize("variant", ["Yaru-purple", "Yaru-purple-dark", "Yaru-mate"])
def test_applied_icon_is_the_preview_byte_for_byte(isolated_home, symbols_dir, tmp_path, name, variant):
    accent, dark = yaru.parse_variant(variant)
    [d] = folders(isolated_home, "A")
    setter = Setter()
    apply_folders([d], name, accent, dark=dark, symbols_dir=symbols_dir, set_icon=setter)
    icon = setter.calls[0][1][len("file://"):]
    (tmp_path / "base").mkdir()
    with PreviewSession(base_dir=tmp_path / "base") as s:
        shown = s.build(os.path.join(symbols_dir, "actions", f"{name}-symbolic.svg"), variant)
        assert read(icon) == read(shown)
        assert os.path.dirname(icon) == store.icons_dir() and not icon.startswith(s.dir)


# ------------------------------------------------------------- the same result as the CLI
@pytest.mark.parametrize("accent, system", [("sage", "Yaru-dark"), ("sage", "Yaru-bark"),
                                            ("orange", "Yaru-red-dark"), ("mate", "Yaru")])
@pytest.mark.parametrize("by_name", [True, False])
@pytest.mark.parametrize("name", ["sq", "adaptive"])
def test_same_file_name_content_and_recipe_as_the_cli(isolated_home, symbols_dir, tmp_path, monkeypatch,
                                                      accent, system, by_name, name):
    """`apply F NAME --accent A --symbols-dir D` with the system in some style and apply_folders with that
    style give the same file name, the same bytes and the same recipe. by_name: D is Yaru's own tree, so
    the recipe keeps the name; else it keeps the absolute path."""
    if by_name:
        monkeypatch.setattr(ap, "YARU_SYMBOLS", symbols_dir)
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: system)
    monkeypatch.setattr(ap, "gio_set", Setter())
    cli_dir, gui_dir = folders(isolated_home, "CLI", "GUI")
    cli.main(["apply", cli_dir, name, "--accent", accent, "--symbols-dir", symbols_dir])
    [cli_icon] = icon_files()

    gui_store, gui_manifest = str(tmp_path / "gui-store"), str(tmp_path / "gui" / "manifest.json")
    setter = Setter()
    apply_folders([gui_dir], name, accent, dark=yaru.parse_variant(system)[1], symbols_dir=symbols_dir,
                  store_dir=gui_store, manifest_path=gui_manifest, set_icon=setter)
    assert os.listdir(gui_store) == [cli_icon]
    assert read(os.path.join(gui_store, cli_icon)) == read(os.path.join(store.icons_dir(), cli_icon))
    cli_recipe, gui_recipe = store.lookup(cli_dir).recipe, store.lookup(gui_dir, gui_manifest).recipe
    assert cli_recipe == gui_recipe
    assert (gui_recipe.symbol == name) == by_name


def test_symbol_given_as_a_path_is_recorded_by_path(isolated_home, symbols_dir, monkeypatch):
    monkeypatch.setattr(ap, "YARU_SYMBOLS", symbols_dir)
    [d] = folders(isolated_home, "A")
    path = os.path.join(symbols_dir, "actions", "sq-symbolic.svg")
    apply_folders([d], path, "red", dark=False, symbols_dir=symbols_dir, set_icon=Setter())
    assert store.lookup(d).recipe == Recipe(path, "red")


# ------------------------------------------------------------- failures and the manifest
def test_a_failing_folder_does_not_stop_the_others_and_is_not_recorded(isolated_home, symbols_dir):
    a, b, c = folders(isolated_home, "A", "B", "C")
    store.record(b, Recipe("old", "red", 1.3, "mass"))
    results = apply_folders([a, b, c], "sq", "blue", dark=False, symbols_dir=symbols_dir,
                            set_icon=Setter(b))
    assert [(r.folder, r.ok) for r in results] == [(a, True), (b, False), (c, True)]
    assert results[1].message == f"fake failure on {b}"
    assert store.lookup(b).recipe == Recipe("old", "red", 1.3, "mass")      # its icon did not change
    assert store.lookup(a).recipe.accent == store.lookup(c).recipe.accent == "blue"


def test_os_errors_of_the_setter_are_per_folder_too(isolated_home, symbols_dir):
    a, b = folders(isolated_home, "A", "B")

    def setter(folder, uri):
        if folder == a:
            raise PermissionError(13, "Permission denied")
    results = apply_folders([a, b], "sq", "blue", dark=False, symbols_dir=symbols_dir, set_icon=setter)
    assert [r.ok for r in results] == [False, True] and "Permission denied" in results[0].message
    assert store.lookup(a) is None and store.lookup(b) is not None


@pytest.mark.parametrize("fail, saves", [((), 1), (("A", "B", "C", "D"), 0)])
def test_the_manifest_is_saved_once_or_not_at_all(isolated_home, symbols_dir, monkeypatch, fail, saves):
    dirs = folders(isolated_home, "A", "B", "C", "D")
    calls, real = [], store.Manifest.save
    monkeypatch.setattr(store.Manifest, "save", lambda self: (calls.append(1), real(self)))
    apply_folders(dirs, "sq", "blue", dark=False, symbols_dir=symbols_dir,
                  set_icon=Setter(*(str(isolated_home / n) for n in fail)))
    assert len(calls) == saves
    assert os.path.exists(store.manifest_path()) == bool(saves)


def test_a_recipe_with_other_scale_and_align_is_replaced_as_a_whole(isolated_home, symbols_dir):
    [d] = folders(isolated_home, "Music")
    os.makedirs(store.data_dir())
    with open(store.manifest_path(), "w", encoding="utf-8") as f:
        json.dump({"schema_version": 1, "extra": 1, "folders": [
            {"path": "Music", "note": "kept", "recipe": {"symbol": "x", "accent": "red", "scale": 1.3,
                                                          "align": "mass", "future": True}}]}, f)
    apply_folders([d], "sq", "sage", dark=False, symbols_dir=symbols_dir, set_icon=Setter())
    with open(store.manifest_path(), encoding="utf-8") as f:
        data = json.load(f)
    sym = os.path.join(symbols_dir, "actions", "sq-symbolic.svg")
    assert data["extra"] == 1
    assert data["folders"] == [{"path": "Music", "note": "kept",
                                "recipe": {"symbol": sym, "accent": "sage", "scale": 1.0, "align": "bbox"}}]


@pytest.mark.parametrize("text, match", [("{oops", "damaged"),
                                         (json.dumps({"schema_version": 99, "folders": []}), "newer")])
def test_a_damaged_or_newer_manifest_changes_nothing(isolated_home, symbols_dir, text, match):
    [d] = folders(isolated_home, "A")
    os.makedirs(store.data_dir())
    with open(store.manifest_path(), "w", encoding="utf-8") as f:
        f.write(text)
    setter = Setter()
    with pytest.raises(ManifestError, match=match):
        apply_folders([d], "sq", "sage", dark=False, symbols_dir=symbols_dir, set_icon=setter)
    assert setter.calls == [] and icon_files() == []
    assert read(store.manifest_path()).decode() == text


@pytest.mark.parametrize("symbol, accent, match", [("nosuch", "sage", "symbol 'nosuch' not found"),
                                                   ("sq", "nosuch", "unknown accent 'nosuch'")])
def test_unknown_symbol_or_accent_changes_nothing(isolated_home, symbols_dir, symbol, accent, match):
    [d] = folders(isolated_home, "A")
    setter = Setter()
    with pytest.raises(ApplyError, match=match):
        apply_folders([d], symbol, accent, dark=False, symbols_dir=symbols_dir, set_icon=setter)
    assert setter.calls == [] and icon_files() == [] and not os.path.exists(store.manifest_path())


def test_an_icon_that_cannot_be_built_is_an_apply_error(isolated_home, symbols_dir, tmp_path):
    [d] = folders(isolated_home, "A")
    blocked = tmp_path / "file"
    blocked.write_text("")                                   # store_dir below a file: cannot be created
    setter = Setter()
    with pytest.raises(ApplyError, match="cannot build the icon"):
        apply_folders([d], "sq", "sage", dark=False, symbols_dir=symbols_dir, store_dir=str(blocked / "icons"),
                      set_icon=setter)
    assert setter.calls == [] and not os.path.exists(store.manifest_path())


def test_no_folders_builds_nothing(isolated_home, symbols_dir):
    assert apply_folders([], "nosuch", "nosuch", dark=False, symbols_dir=symbols_dir, set_icon=Setter()) == []
    assert icon_files() == [] and not os.path.exists(store.data_dir())


# ------------------------------------------------------------- folders and the default setter
def test_folders_are_normalised_and_duplicates_set_once(isolated_home, symbols_dir, monkeypatch):
    [d] = folders(isolated_home, "A")
    setter = Setter()
    monkeypatch.setattr(ap, "gio_set", setter)               # the default setter is looked up at call time
    results = apply_folders([d, d + "/", "~/A", os.path.join(d, "..", "A")], "sq", "sage", dark=False,
                            symbols_dir=symbols_dir)
    assert [r.folder for r in results] == [d] and [c[0] for c in setter.calls] == [d]


def test_apply_module_does_not_import_gtk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = "import sys, folder_symbols.apply, folder_symbols.store; print('gi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------- following the system accent
SYSTEM = store.SYSTEM_ACCENT


def test_following_builds_with_the_given_system_accent_and_records_system(isolated_home, symbols_dir):
    a, b = folders(isolated_home, "A", "B")
    setter = Setter()
    results = apply_folders([a, b], "sq", SYSTEM, dark=True, symbols_dir=symbols_dir, system_accent="sage",
                            set_icon=setter)
    assert [r.ok for r in results] == [True, True]
    assert icon_files() == ["Yaru-sage-dark-sq.svg"]
    assert all(e.recipe.accent == SYSTEM and e.recipe.follows_system for e in store.entries())


@pytest.mark.parametrize("system, dark, variant", [("Yaru-bark", False, "Yaru-bark"),
                                                   ("Yaru-bark-dark", True, "Yaru-bark-dark"),
                                                   ("Yaru-mate-dark", False, "Yaru-mate"),
                                                   ("Yaru", True, "Yaru-dark")])
def test_following_without_a_given_accent_takes_the_icon_themes(isolated_home, symbols_dir, monkeypatch,
                                                                system, dark, variant):
    """The accent comes from the icon theme; the style is still `dark` (what the preview shows)."""
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: system)
    [d] = folders(isolated_home, "A")
    apply_folders([d], "sq", SYSTEM, dark=dark, symbols_dir=symbols_dir, set_icon=Setter())
    assert icon_files() == [f"{variant}-sq.svg"] and store.lookup(d).recipe.follows_system


@pytest.mark.parametrize("theme", ["Adwaita", None])
def test_following_without_a_system_accent_changes_nothing(isolated_home, symbols_dir, monkeypatch, theme):
    def current():
        if theme is None:
            raise subprocess.CalledProcessError(1, "gsettings")
        return theme
    monkeypatch.setattr(yaru, "current_icon_theme", current)
    [d] = folders(isolated_home, "A")
    setter = Setter()
    with pytest.raises(ApplyError, match="no system accent to follow"):
        apply_folders([d], "sq", SYSTEM, dark=False, symbols_dir=symbols_dir, set_icon=setter)
    assert setter.calls == [] and icon_files() == [] and not os.path.exists(store.manifest_path())


def test_a_following_and_a_pinned_folder_share_the_icon_file(isolated_home, symbols_dir):
    follows, pinned = folders(isolated_home, "Follows", "Pinned")
    s1, s2 = Setter(), Setter()
    apply_folders([follows], "sq", SYSTEM, dark=False, symbols_dir=symbols_dir, system_accent="blue",
                  set_icon=s1)
    first = read(os.path.join(store.icons_dir(), "Yaru-blue-sq.svg"))
    apply_folders([pinned], "sq", "blue", dark=False, symbols_dir=symbols_dir, set_icon=s2)
    assert s1.calls[0][1] == s2.calls[0][1] and icon_files() == ["Yaru-blue-sq.svg"]
    assert read(os.path.join(store.icons_dir(), "Yaru-blue-sq.svg")) == first
    assert store.lookup(follows).recipe.accent == SYSTEM and store.lookup(pinned).recipe.accent == "blue"


@pytest.mark.parametrize("system", ["Yaru-dark", "Yaru-sage", "Yaru-mate", "Yaru-mate-dark"])
def test_following_gives_the_same_file_and_recipe_as_the_cli_without_options(isolated_home, symbols_dir,
                                                                            tmp_path, monkeypatch, system):
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: system)
    monkeypatch.setattr(ap, "gio_set", Setter())
    cli_dir, gui_dir = folders(isolated_home, "CLI", "GUI")
    cli.main(["apply", cli_dir, "sq", "--symbols-dir", symbols_dir])
    [cli_icon] = icon_files()
    accent, dark = yaru.parse_variant(system)
    gui_store, gui_manifest = str(tmp_path / "gui-store"), str(tmp_path / "gui" / "manifest.json")
    apply_folders([gui_dir], "sq", SYSTEM, dark=dark, symbols_dir=symbols_dir, system_accent=accent,
                  store_dir=gui_store, manifest_path=gui_manifest, set_icon=Setter())
    assert os.listdir(gui_store) == [cli_icon]
    assert read(os.path.join(gui_store, cli_icon)) == read(os.path.join(store.icons_dir(), cli_icon))
    assert store.lookup(cli_dir).recipe == store.lookup(gui_dir, gui_manifest).recipe
    assert store.lookup(gui_dir, gui_manifest).recipe.follows_system


def test_pinning_and_following_replace_each_other(isolated_home, symbols_dir):
    [d] = folders(isolated_home, "A")
    store.record(d, Recipe("old", "red", 1.3, "mass"))
    apply_folders([d], "sq", SYSTEM, dark=False, symbols_dir=symbols_dir, system_accent="red", set_icon=Setter())
    sym = os.path.join(symbols_dir, "actions", "sq-symbolic.svg")
    assert store.lookup(d).recipe == Recipe(sym, SYSTEM)
    apply_folders([d], "sq", "red", dark=False, symbols_dir=symbols_dir, set_icon=Setter())
    assert store.lookup(d).recipe == Recipe(sym, "red")


def test_system_is_not_a_concrete_accent_to_build_with(isolated_home, symbols_dir):
    [d] = folders(isolated_home, "A")
    with pytest.raises(ApplyError, match="unknown accent 'nosuch'"):
        apply_folders([d], "sq", SYSTEM, dark=False, symbols_dir=symbols_dir, system_accent="nosuch",
                      set_icon=Setter())
    assert icon_files() == []


# ------------------------------------------------------------- a manifest that cannot be saved
def test_a_save_failure_after_gio_is_a_record_error_with_the_results(isolated_home, symbols_dir, monkeypatch):
    a, b = folders(isolated_home, "A", "B")

    def broken_save(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(store.Manifest, "save", broken_save)
    setter = Setter(b)
    with pytest.raises(ap.RecordError) as e:
        apply_folders([a, b], "sq", "sage", dark=False, symbols_dir=symbols_dir, set_icon=setter)
    assert [c[0] for c in setter.calls] == [a, b]                 # the icons were set
    assert [(r.folder, r.ok) for r in e.value.results] == [(a, True), (b, False)]
    assert isinstance(e.value.error, PermissionError) and "could not be saved" in str(e.value)
    assert not os.path.exists(store.manifest_path())


def test_an_os_error_before_anything_is_set_stays_an_os_error(isolated_home, symbols_dir, tmp_path):
    [d] = folders(isolated_home, "A")
    blocked = tmp_path / "blocked"
    blocked.write_text("")                                         # the manifest's directory is a file
    setter = Setter()
    with pytest.raises(OSError) as e:
        apply_folders([d], "sq", "sage", dark=False, symbols_dir=symbols_dir,
                      manifest_path=str(blocked / "manifest.json"), set_icon=setter)
    assert not isinstance(e.value, ap.RecordError) and setter.calls == []


# ------------------------------------------------------------- reset_folders

class Unsetter(Setter):
    def __call__(self, folder):
        super().__call__(folder, None)


def recorded_in(isolated_home, *names):
    dirs = folders(isolated_home, *names)
    for d in dirs:
        store.record(d, Recipe("sq", "system"))
    return dirs


def test_reset_removes_only_the_entries_of_folders_that_were_reset(isolated_home):
    a, b, c = recorded_in(isolated_home, "A", "B", "C")
    unset = Unsetter(b)
    results = reset_folders([a, b, c], unset_icon=unset)
    assert [(r.folder, r.ok, r.message) for r in results] == [(a, True, "icon reset"),
                                                              (b, False, f"fake failure on {b}"),
                                                              (c, True, "icon reset")]
    assert [c_[0] for c_ in unset.calls] == [a, b, c]
    assert [e.folder for e in store.entries()] == [b]


def test_reset_of_a_missing_folder_fails_and_keeps_its_entry(isolated_home):
    a, gone = recorded_in(isolated_home, "A", "Gone")
    os.rmdir(gone)
    unset = Unsetter()
    results = reset_folders([gone, a], unset_icon=unset)
    assert [(r.ok, r.message) for r in results] == [(False, NOT_FOUND), (True, "icon reset")]
    assert [c[0] for c in unset.calls] == [a] and [e.folder for e in store.entries()] == [gone]


@pytest.mark.parametrize("fail, saves", [(False, 1), (True, 0)])
def test_reset_saves_the_manifest_once_or_not_at_all(isolated_home, monkeypatch, fail, saves):
    dirs = recorded_in(isolated_home, "A", "B", "C")
    calls, real = [], store.Manifest.save
    monkeypatch.setattr(store.Manifest, "save", lambda self: (calls.append(1), real(self)))
    reset_folders(dirs, unset_icon=Unsetter(*(dirs if fail else ())))
    assert len(calls) == saves


@pytest.mark.parametrize("text, match", [("{oops", "damaged"),
                                         (json.dumps({"schema_version": 99, "folders": []}), "newer")])
def test_reset_with_a_damaged_or_newer_manifest_touches_nothing(isolated_home, text, match):
    [d] = folders(isolated_home, "A")
    os.makedirs(store.data_dir())
    with open(store.manifest_path(), "w", encoding="utf-8") as f:
        f.write(text)
    unset = Unsetter()
    with pytest.raises(ManifestError, match=match):
        reset_folders([d], unset_icon=unset)
    assert unset.calls == [] and read(store.manifest_path()).decode() == text


def test_reset_save_failure_is_a_record_error(isolated_home, monkeypatch):
    a, b = recorded_in(isolated_home, "A", "B")
    monkeypatch.setattr(store.Manifest, "save", lambda self: (_ for _ in ()).throw(OSError(28, "No space")))
    with pytest.raises(ap.RecordError) as e:
        reset_folders([a, b], unset_icon=Unsetter())
    assert [r.ok for r in e.value.results] == [True, True] and "No space" in str(e.value.error)
    assert len(store.entries()) == 2                               # the old manifest is still there


def test_reset_drops_duplicates_and_uses_gio_unset_by_default(isolated_home, monkeypatch):
    [a] = recorded_in(isolated_home, "A")
    unset = Unsetter()
    monkeypatch.setattr(ap, "gio_unset", unset)                    # looked up at call time
    assert [r.folder for r in reset_folders([a, a + "/", "~/A"])] == [a]
    assert [c[0] for c in unset.calls] == [a]
    assert reset_folders([]) == []


def test_reset_of_a_folder_without_an_entry_still_unsets_it(isolated_home):
    """reset_folders does not filter; the window passes only the folders with an entry."""
    [d] = folders(isolated_home, "A")
    unset = Unsetter()
    assert [r.ok for r in reset_folders([d], unset_icon=unset)] == [True] and unset.calls
    assert not os.path.exists(store.manifest_path())               # nothing changed, nothing saved


def test_reset_an_os_error_before_anything_is_unset_stays_an_os_error(isolated_home, tmp_path):
    """The mirror of test_an_os_error_before_anything_is_set_stays_an_os_error: the window's reset_outcome
    expects a RecordError to carry results, so an early OSError must not become one."""
    [d] = recorded_in(isolated_home, "A")
    blocked = tmp_path / "blocked"
    blocked.write_text("")                                         # the manifest's directory is a file
    unset = Unsetter()
    with pytest.raises(OSError) as e:
        reset_folders([d], manifest_path=str(blocked / "manifest.json"), unset_icon=unset)
    assert not isinstance(e.value, ap.RecordError) and unset.calls == []


# ------------------------------------------------------------- the gio wrappers, against a fake gio on PATH
FAKE_GIO = """#!/bin/sh
dir=$(dirname "$0")
printf '%s\\0' "$@" > "$dir/argv"
cat "$dir/stdout"
cat "$dir/stderr" >&2
exit "$(cat "$dir/status")"
"""


@pytest.fixture
def fake_gio(isolated_home, tmp_path, monkeypatch):
    """A fake `gio` in tmp_path, first on PATH (before the conftest stub that exits 99): it records its
    arguments and answers with the status, stdout and stderr given to reply()."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "gio").write_text(FAKE_GIO)
    (bindir / "gio").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    assert shutil.which("gio") == str(bindir / "gio")

    def reply(status=0, stdout="", stderr=""):
        for name, text in (("status", str(status)), ("stdout", stdout), ("stderr", stderr)):
            (bindir / name).write_text(text)

    def argv():
        return (bindir / "argv").read_bytes().decode().split("\0")[:-1]
    reply()
    return types.SimpleNamespace(reply=reply, argv=argv)


def gio_info(*attribute_lines):
    """What `gio info -a metadata::custom-icon FOLDER` prints: header lines, then the attributes indented."""
    return ("uri: file:///f\nlocal path: /f\nunix mount: tmpfs /tmp tmpfs rw 0 0\nattributes:\n"
            + "".join(f"  {line}\n" for line in attribute_lines))


def test_gio_set_runs_gio_set_with_the_uri(fake_gio, tmp_path):
    fake_gio.reply(0, stderr="a warning that is not an error\n")   # only the status counts
    assert ap.gio_set(str(tmp_path / "F"), "file:///i.svg") is None
    assert fake_gio.argv() == ["set", str(tmp_path / "F"), "metadata::custom-icon", "file:///i.svg"]


def test_gio_unset_runs_gio_set_type_unset(fake_gio, tmp_path):
    assert ap.gio_unset(str(tmp_path / "F")) is None
    assert fake_gio.argv() == ["set", "-t", "unset", str(tmp_path / "F"), "metadata::custom-icon"]


@pytest.mark.parametrize("stdout, want", [
    (gio_info("metadata::custom-icon: file:///home/u/a.svg"), "file:///home/u/a.svg"),
    (gio_info("metadata::custom-icon: file:///home/u/a: b.svg"), "file:///home/u/a: b.svg"),
    (gio_info(), None),                                            # no custom icon: no attribute line
    (gio_info("metadata::custom-icon-name: folder-music"), None),  # another attribute with the same prefix
    # pins current behaviour (an empty value reads as no icon), see the report of TASK 13, finding F1
    (gio_info("metadata::custom-icon: "), None),
    (gio_info("metadata::custom-icon: file:///a.svg  "), "file:///a.svg"),
], ids=["present", "value-with-colon-space", "absent", "other-attribute", "empty-value", "trailing-spaces"])
def test_gio_custom_icon_parses_gio_info(fake_gio, tmp_path, stdout, want):
    fake_gio.reply(0, stdout)
    assert ap.gio_custom_icon(str(tmp_path / "F")) == want
    assert fake_gio.argv() == ["info", "-a", "metadata::custom-icon", str(tmp_path / "F")]


def test_gio_custom_icon_is_none_when_gio_fails(fake_gio, tmp_path):
    # pins current behaviour (a failure reads as no icon), see the report of TASK 13, finding F1
    fake_gio.reply(1, gio_info("metadata::custom-icon: file:///a.svg"), "gio: file:///f: No such file\n")
    assert ap.gio_custom_icon(str(tmp_path / "F")) is None


@pytest.mark.parametrize("status, stderr, message", [
    (1, "gio: file:///f: Operation not supported\n", "gio: file:///f: Operation not supported"),
    (3, " \n", "gio exited with status 3"),
], ids=["stderr", "no-stderr"])
@pytest.mark.parametrize("call", [lambda f: ap.gio_set(f, "file:///i.svg"), ap.gio_unset], ids=["set", "unset"])
def test_a_gio_failure_is_a_gio_error(fake_gio, tmp_path, call, status, stderr, message):
    fake_gio.reply(status, stderr=stderr)
    with pytest.raises(ap.GioError) as e:
        call(str(tmp_path / "F"))
    assert str(e.value) == message


def test_gio_that_cannot_be_run_is_a_gio_error(isolated_home, tmp_path, monkeypatch):
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))            # no gio at all
    f = str(tmp_path / "F")
    for call in (lambda: ap.gio_set(f, "file:///i.svg"), lambda: ap.gio_unset(f)):
        with pytest.raises(ap.GioError) as e:
            call()
        assert str(e.value) == "cannot run gio: No such file or directory"
    assert ap.gio_custom_icon(f) is None


# ---------------------------------------------------------------- the default PNG size
def _size_action(parser):
    return next(a for a in parser._actions if a.option_strings == ["--size"])


@pytest.mark.parametrize("parser", [cli.parser_apply, cli.parser_compose])
def test_size_default_and_its_help_follow_default_size(parser):
    action = _size_action(parser())
    assert action.default == yaru.DEFAULT_SIZE
    # the help prose names the default size as such (it is a literal there, so this keeps them together)
    assert f"{yaru.DEFAULT_SIZE} (= {yaru.ALIAS[yaru.DEFAULT_SIZE]}, default)" in action.help


def test_icon_suffix_treats_default_size_as_default():
    assert ap.icon_suffix("x", {}, png_size=yaru.DEFAULT_SIZE) == ""
    assert ap.icon_suffix("x", {}, png_size="256") != ""
