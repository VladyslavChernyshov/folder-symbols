"""The local store and manifest, and the commands that use it (apply, reset, reset --all, list).
Everything runs in the temporary home of the isolated_home fixture; gio and gsettings are faked."""
import json, os, shlex, types
import pytest

from folder_symbols import apply as ap, cli, store, yaru
from folder_symbols.store import ManifestError, Recipe

SQUARE = '<rect x="3" y="3" width="10" height="10" fill="#222"/>'


@pytest.fixture
def gio(monkeypatch):
    """Fake gio (custom icons kept in a dict) and a fake system icon theme."""
    state = types.SimpleNamespace(icons={}, fail=set(), theme="Yaru-dark", calls=[])

    def check(folder):
        state.calls.append(folder)
        if folder in state.fail:
            raise ap.GioError(f"fake failure on {folder}")

    def set_icon(folder, uri):
        check(folder)
        state.icons[folder] = uri

    def unset_icon(folder):
        check(folder)
        state.icons.pop(folder, None)

    monkeypatch.setattr(ap, "gio_set", set_icon)
    monkeypatch.setattr(ap, "gio_unset", unset_icon)
    monkeypatch.setattr(ap, "gio_custom_icon", lambda folder: state.icons.get(folder))
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: state.theme)
    return state


@pytest.fixture
def sym(svg):
    return svg("sq", SQUARE, 'viewBox="0 0 16 16"')


def folder(home, name):
    p = home / name
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def raw_manifest():
    with open(store.manifest_path(), encoding="utf-8") as f:
        return json.load(f)


def write_manifest(data):
    os.makedirs(store.data_dir(), exist_ok=True)
    with open(store.manifest_path(), "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


# ------------------------------------------------------------- locations
def test_data_dir_respects_xdg_data_home(isolated_home, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert store.data_dir() == str(tmp_path / "xdg" / "folder-symbols")
    assert store.manifest_path() == str(tmp_path / "xdg" / "folder-symbols" / "manifest.json")
    assert store.icons_dir() == str(tmp_path / "xdg" / "folder-symbols" / "icons")
    for value in ("", "relative/dir"):          # unset or relative: the XDG default under $HOME
        monkeypatch.setenv("XDG_DATA_HOME", value)
        assert store.data_dir() == str(isolated_home / ".local" / "share" / "folder-symbols")


# ------------------------------------------------------------- reading and writing
def test_round_trip_with_home_relative_and_absolute_paths(isolated_home, tmp_path):
    music, outside = folder(isolated_home, "Music"), str(tmp_path / "outside dir")
    r1, r2 = Recipe("community", "purple"), Recipe("/x/y-symbolic.svg", "orange", 1.25, "mass")
    store.record(music, r1)
    store.record(str(isolated_home), r2)
    store.record(outside, r1)
    data = raw_manifest()
    assert data["schema_version"] == store.SCHEMA_VERSION
    assert [e["path"] for e in data["folders"]] == sorted([".", "Music", outside])
    assert data["folders"][1]["recipe"] == {"symbol": "community", "accent": "purple", "scale": 1.0,
                                            "align": "bbox"}
    assert "mtime" not in json.dumps(data) and "style" not in json.dumps(data)
    got = {e.folder: e.recipe for e in store.entries()}
    assert got == {music: r1, str(isolated_home): r2, outside: r1}
    assert store.lookup(isolated_home / "Music") == store.Entry(music, r1)
    assert store.lookup(isolated_home / "Other") is None
    assert store.remove(music) and not store.remove(music)
    assert store.lookup(music) is None


def test_record_replaces_the_recipe_of_the_same_folder(isolated_home):
    music = folder(isolated_home, "Music")
    store.record(music, Recipe("a", "red"))
    store.record(music + "/", Recipe("b", "sage"))
    assert [(e.folder, e.recipe.symbol) for e in store.entries()] == [(music, "b")]


def test_missing_manifest_is_empty_and_not_created_by_reading(isolated_home):
    assert store.entries() == [] and store.lookup(isolated_home) is None
    assert not os.path.exists(store.manifest_path())


def test_save_is_atomic_and_leaves_no_temporary_files(isolated_home, monkeypatch):
    store.record(folder(isolated_home, "A"), Recipe("a", "red"))
    assert sorted(os.listdir(store.data_dir())) == ["manifest.json", "manifest.lock"]
    before = open(store.manifest_path()).read()

    def broken_replace(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        store.record(folder(isolated_home, "B"), Recipe("b", "red"))
    assert open(store.manifest_path()).read() == before
    assert sorted(os.listdir(store.data_dir())) == ["manifest.json", "manifest.lock"]


def test_unknown_fields_are_ignored_but_kept(isolated_home):
    write_manifest({"schema_version": 1, "future": {"x": 1},
                    "folders": [{"path": "Music", "note": "keep me",
                                 "recipe": {"symbol": "a", "accent": "red", "later": True}}]})
    assert [e.recipe for e in store.entries()] == [Recipe("a", "red")]
    store.record(folder(isolated_home, "Other"), Recipe("b", "blue"))
    store.record(folder(isolated_home, "Music"), Recipe("c", "sage"))     # the entry's own fields stay
    data = raw_manifest()
    assert data["future"] == {"x": 1}
    music = next(e for e in data["folders"] if e["path"] == "Music")
    assert music["note"] == "keep me" and music["recipe"]["symbol"] == "c"


@pytest.mark.parametrize("text, why", [
    ("{not json", "not valid JSON"),
    ("[]", "not a JSON object"),
    ('{"folders": []}', "schema_version"),
    ('{"schema_version": "1", "folders": []}', "schema_version"),
    ('{"schema_version": 1, "folders": {}}', "not a list"),
])
def test_damaged_manifest_gives_a_clear_error_and_is_never_overwritten(isolated_home, text, why):
    write_manifest(text)
    with pytest.raises(ManifestError, match=why) as e:
        store.entries()
    assert store.manifest_path() in str(e.value) and "move it away" in str(e.value)
    with pytest.raises(ManifestError):
        store.record(folder(isolated_home, "A"), Recipe("a", "red"))
    assert open(store.manifest_path()).read() == text


def test_unusable_entries_are_skipped_with_a_warning_but_kept(isolated_home):
    bad = [{"path": "NoRecipe"}, {"recipe": {"symbol": "a", "accent": "red"}},
           {"path": "BadScale", "recipe": {"symbol": "a", "accent": "red", "scale": -1}}, "junk"]
    write_manifest({"schema_version": 1,
                    "folders": bad + [{"path": "Good", "recipe": {"symbol": "a", "accent": "red"}}]})
    m = store.load()
    assert [e.folder for e in m.entries()] == [str(isolated_home / "Good")]
    assert len(m.warnings) == 4
    store.record(folder(isolated_home, "New"), Recipe("b", "red"))
    kept = raw_manifest()["folders"]
    assert all(b in kept for b in bad) and len(kept) == 6


def test_newer_schema_can_be_read_but_not_written(isolated_home):
    data = {"schema_version": store.SCHEMA_VERSION + 1,
            "folders": [{"path": "Music", "recipe": {"symbol": "a", "accent": "red"}}]}
    write_manifest(data)
    assert [e.recipe.symbol for e in store.entries()] == ["a"]
    with pytest.raises(ManifestError, match="newer folder-symbols"):
        store.record(folder(isolated_home, "A"), Recipe("a", "red"))
    assert raw_manifest() == data


def test_older_schema_goes_through_the_migrations(isolated_home, monkeypatch):
    monkeypatch.setattr(store, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(store, "MIGRATIONS", {1: lambda d: {**d, "folders": d["entries"]}})
    write_manifest({"schema_version": 1, "entries": [{"path": "M", "recipe": {"symbol": "a", "accent": "red"}}]})
    assert [e.recipe.symbol for e in store.entries()] == ["a"]
    monkeypatch.setattr(store, "MIGRATIONS", {})
    with pytest.raises(ManifestError, match="no migration from schema 1"):
        store.entries()


def test_nested_editing_reuses_the_lock(isolated_home):
    with store.editing() as outer:
        store.record(folder(isolated_home, "A"), Recipe("a", "red"))      # would deadlock on a second lock
        assert outer.lookup(isolated_home / "A")
    assert store.lookup(isolated_home / "A")


def test_icon_status(isolated_home, tmp_path):
    icons = {}
    d = folder(isolated_home, "D")
    assert store.icon_status(str(tmp_path / "gone"), icons.get) == "missing"
    assert store.icon_status(d, icons.get) == "no icon"
    icons[d] = "file://" + os.path.join(store.icons_dir(), "Yaru-x.svg")
    assert store.icon_status(d, icons.get) == "ok"
    icons[d] = "file://" + str(tmp_path / "elsewhere.svg")
    assert store.icon_status(d, icons.get) == "other icon"
    icons[d] = "file://" + store.icons_dir() + "-old/x.svg"           # a prefix is not the directory
    assert store.icon_status(d, icons.get) == "other icon"


# ------------------------------------------------------------- variant names
def test_variant_names_round_trip_over_all_builtin_themes():
    names = sorted(yaru.builtin_themes())
    assert len(names) == 26 and len(yaru.accents()) == 13 and "orange" in yaru.accents()
    for name in names:
        assert yaru.variant_name(*yaru.parse_variant(name)) == name
    assert yaru.parse_variant("Yaru-dark") == ("orange", True)
    assert yaru.parse_variant("Yaru-mate") == ("mate", False)
    for other in ("Adwaita", "Yaru-orange", "Yaru-nosuch-dark", "Yaru-", "", None):
        assert yaru.parse_variant(other) is None
    with pytest.raises(ValueError):
        yaru.variant_name("nosuch", False)


# ------------------------------------------------------------- apply
def test_apply_records_the_folder_and_dry_run_does_not(isolated_home, gio, sym, capsys):
    d = folder(isolated_home, "Music")
    cli.main(["apply", d, sym, "--dry-run"])
    assert "would record ~/Music" in capsys.readouterr().out
    assert not os.path.exists(store.manifest_path()) and gio.calls == []
    cli.main(["apply", d, sym])
    icon = os.path.join(store.icons_dir(), "Yaru-dark-sq.svg")
    assert gio.icons == {d: "file://" + icon} and os.path.exists(icon)
    assert store.lookup(d).recipe == Recipe(os.path.abspath(sym), "orange")


@pytest.mark.parametrize("system, args, theme, accent", [
    ("Yaru-dark", ["--accent", "purple"], "Yaru-purple-dark", "purple"),
    ("Yaru-sage", ["--accent", "purple"], "Yaru-purple", "purple"),
    ("Yaru-bark-dark", [], "Yaru-bark-dark", "bark"),
    ("Yaru-mate-dark", ["--accent", "orange"], "Yaru-dark", "orange"),
    ("Yaru", ["--theme", "Yaru-red-dark"], "Yaru-red-dark", "red"),      # the style is not recorded
])
def test_apply_theme_and_recorded_accent(isolated_home, gio, sym, system, args, theme, accent):
    gio.theme = system
    d = folder(isolated_home, "F")
    cli.main(["apply", d, sym] + args)
    assert gio.icons[d] == "file://" + os.path.join(store.icons_dir(), f"{theme}-sq.svg")
    assert store.lookup(d).recipe.accent == accent


def test_apply_accent_needs_a_yaru_system_theme(isolated_home, gio, sym):
    gio.theme = "Adwaita"
    with pytest.raises(SystemExit, match="not a Yaru variant.*--theme Yaru-purple-dark"):
        cli.main(["apply", folder(isolated_home, "F"), sym, "--accent", "purple"])
    with pytest.raises(SystemExit):
        cli.main(["apply", folder(isolated_home, "F"), sym, "--accent", "purple", "--theme", "Yaru"])


def test_apply_without_theme_or_accent_needs_a_yaru_system_theme(isolated_home, gio, sym, capsys):
    gio.theme = "Adwaita"
    d = folder(isolated_home, "F")
    for extra in ([], ["--dry-run"]):
        with pytest.raises(SystemExit) as e:
            cli.main(["apply", d, sym] + extra)
        assert e.value.code == 2
        err = capsys.readouterr().err
        assert "'Adwaita' is not a Yaru variant" in err and "--theme" in err and "--accent" in err
    assert gio.calls == [] and store.lookup(d) is None and not os.path.exists(store.icons_dir())


def test_apply_symbol_by_name_is_recorded_by_name(isolated_home, gio, svg, monkeypatch):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    monkeypatch.setattr(ap, "YARU_SYMBOLS", os.path.dirname(p))          # pretend it is Yaru's tree
    d = folder(isolated_home, "F")
    cli.main(["apply", d, "sq", "--symbols-dir", os.path.dirname(p)])
    assert store.lookup(d).recipe.symbol == "sq"


def test_apply_options_outside_the_recipe_warn_and_use_their_own_file(isolated_home, gio, sym, capsys):
    a, b, c = (folder(isolated_home, n) for n in "ABC")
    cli.main(["apply", a, sym])
    cli.main(["apply", b, sym, "--scale", "1.3", "--align", "mass"])
    assert "warning" not in capsys.readouterr().err
    cli.main(["apply", c, sym, "--keep-opacity"])
    assert "not kept: --keep-opacity" in capsys.readouterr().err
    assert len(set(gio.icons.values())) == 3
    assert store.lookup(b).recipe == Recipe(os.path.abspath(sym), "orange", 1.3, "mass")
    assert store.lookup(c).recipe == Recipe(os.path.abspath(sym), "orange")


def test_apply_with_a_damaged_manifest_changes_nothing(isolated_home, gio, sym):
    write_manifest("{oops")
    with pytest.raises(SystemExit, match="damaged"):
        cli.main(["apply", folder(isolated_home, "F"), sym])
    assert gio.calls == [] and not os.path.exists(store.icons_dir())


def test_apply_that_fails_in_gio_is_not_recorded(isolated_home, gio, sym):
    d = folder(isolated_home, "F")
    gio.fail.add(d)
    with pytest.raises(SystemExit, match="gio failed"):
        cli.main(["apply", d, sym])
    assert store.lookup(d) is None


# ------------------------------------------------------------- reset
def test_reset_removes_the_icon_and_the_entry(isolated_home, gio, sym):
    d = folder(isolated_home, "F")
    cli.main(["apply", d, sym])
    cli.main(["reset", d])
    assert gio.icons == {} and store.lookup(d) is None
    cli.main(["reset", d])                      # a folder that is not in the manifest: as before


def test_reset_of_a_missing_folder_forgets_it(isolated_home, gio, sym, capsys):
    d = folder(isolated_home, "Gone")
    cli.main(["apply", d, sym])
    os.rmdir(d)
    cli.main(["reset", d])
    assert "folder not found; removed from the manifest" in capsys.readouterr().out
    assert store.lookup(d) is None
    with pytest.raises(SystemExit, match="no such folder"):
        cli.main(["reset", d])


@pytest.mark.parametrize("args", [["reset"], ["reset", "/tmp", "--all"]])
def test_reset_needs_a_folder_or_all(args):
    with pytest.raises(SystemExit) as e:
        cli.main(args)
    assert e.value.code == 2


def test_reset_all_reports_each_folder_and_keeps_going(isolated_home, gio, sym, capsys):
    a, b, c, gone = (folder(isolated_home, n) for n in ("A", "B", "C", "Gone"))
    for d in (a, b, c, gone):
        cli.main(["apply", d, sym])
    os.rmdir(gone)
    gio.fail.add(b)
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli.main(["reset", "--all"])
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "ok      ~/A" in out and "ok      ~/C" in out
    assert "FAILED  ~/B: fake failure" in out
    assert "FAILED  ~/Gone: not found, entry kept; run 'folder-symbols reset ~/Gone'" in out
    assert "Reset 2 of 4 folders" in out
    assert set(gio.icons) == {b, gone}          # gone's icon is only in the (fake) metadata store
    assert [e.folder for e in store.entries()] == [b, gone]
    gio.fail.clear()
    os.mkdir(gone)
    cli.main(["reset", "--all"])
    assert store.entries() == [] and gio.icons == {}
    cli.main(["reset", "--all"])
    assert "No folders in the manifest" in capsys.readouterr().out


# ------------------------------------------------------------- list
def test_list_shows_the_status_of_each_folder(isolated_home, gio, sym, capsys, tmp_path):
    ok, gone, other, none = (folder(isolated_home, n) for n in ("Ok", "Gone", "Other", "None"))
    for d in (ok, gone, other, none):
        cli.main(["apply", d, sym])
    os.rmdir(gone)
    gio.icons[other] = "file://" + str(tmp_path / "someone-else.svg")
    del gio.icons[none]
    capsys.readouterr()
    cli.main(["list"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["FOLDER", "SYMBOL", "ACCENT", "OPTIONS", "STATUS"]
    status = {line.split()[0]: line.split("  ")[-1].strip() for line in lines[1:]}
    assert status == {"~/Ok": "ok", "~/Gone": "missing", "~/Other": "other icon", "~/None": "no icon"}
    assert store.folders_with_icon(ap.gio_custom_icon) == [store.lookup(ok)]


def test_list_with_nothing_recorded(isolated_home, gio, capsys):
    cli.main(["list"])
    assert "No folders recorded" in capsys.readouterr().out
    cli.main(["list", "--format", "commands"])
    assert capsys.readouterr().out == ""


def test_list_commands_are_quoted_and_give_back_the_same_recipes(isolated_home, gio, capsys, tmp_path,
                                                                 monkeypatch):
    recipes = {
        str(isolated_home / "Music"): Recipe("community", "purple"),
        str(isolated_home / "My Files" / "it's here"): Recipe("folder-open", "orange", 1.25, "mass"),
        str(isolated_home): Recipe(str(isolated_home / "my syms" / "x-symbolic.svg"), "sage", 0.8, "yaru"),
        str(tmp_path / "outside $dir"): Recipe("/opt/s y/z-symbolic.svg", "mate"),
    }
    for d, r in recipes.items():                 # the folders do not exist: commands are not checked
        store.record(d, r)
    monkeypatch.setattr(ap, "gio_custom_icon", lambda f: pytest.fail("list --format commands checked a folder"))
    cli.main(["list", "--format", "commands"])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(recipes)
    assert "folder-symbols apply ~/Music community --accent purple" in lines
    assert "folder-symbols apply ~/'My Files/it'\"'\"'s here' folder-open --accent orange --scale 1.25 " \
           "--align mass" in lines
    for line in lines:
        words = shlex.split(line)
        assert words[:2] == ["folder-symbols", "apply"]
        a = cli.parser_apply().parse_args(words[1:])
        d = os.path.expanduser(a.folder)
        sym = os.path.expanduser(a.symbol)
        assert recipes[d] == Recipe(sym, a.accent, a.scale, a.align), line
        assert d == str(isolated_home) or not os.path.exists(d)      # nothing was created


# ------------------------------------------------------------- prune
def recorded(*folders):
    for d in folders:
        store.record(d, Recipe("a", "red"))


def test_prune_removes_missing_folders_and_keeps_the_others(isolated_home, gio, capsys):
    keep, gone, afile = (str(isolated_home / n) for n in ("Keep", "Gone", "AFile"))
    os.mkdir(keep)
    open(afile, "w").close()                    # a file at the path: not a folder, so it counts as missing
    recorded(keep, gone, afile, str(isolated_home), str(isolated_home / "AFile" / "below"))
    cli.main(["prune"])
    out = capsys.readouterr().out.splitlines()
    assert out == ["removed   ~/AFile", "removed   ~/AFile/below", "removed   ~/Gone",
                   "Removed 3 of 5 entries"]
    assert [e.folder for e in store.entries()] == [str(isolated_home), keep]   # home is never removed
    assert gio.calls == [] and os.path.exists(afile)
    cli.main(["prune"])
    assert capsys.readouterr().out == "Nothing to remove\n"


def test_prune_writes_the_manifest_once(isolated_home, gio, monkeypatch):
    recorded(*(str(isolated_home / n) for n in ("A", "B", "C")))
    saves = []
    real = store.Manifest.save
    monkeypatch.setattr(store.Manifest, "save", lambda self: (saves.append(1), real(self)))
    cli.main(["prune"])
    assert len(saves) == 1 and store.entries() == []
    cli.main(["prune"])                         # nothing to remove: nothing written
    assert len(saves) == 1


def test_prune_dry_run_changes_nothing(isolated_home, gio, capsys):
    recorded(str(isolated_home / "Gone"))
    before = open(store.manifest_path(), "rb").read()
    os.unlink(os.path.join(store.data_dir(), "manifest.lock"))
    cli.main(["prune", "--dry-run"])
    assert capsys.readouterr().out.splitlines() == ["would remove  ~/Gone", "Would remove 1 of 1 entries"]
    assert open(store.manifest_path(), "rb").read() == before
    assert os.listdir(store.data_dir()) == ["manifest.json"]          # not even a lock file


def test_prune_dry_run_without_a_manifest_creates_nothing(isolated_home, gio, capsys):
    cli.main(["prune", "--dry-run"])
    assert capsys.readouterr().out == "Nothing to remove\n"
    assert not os.path.exists(store.data_dir())


def test_prune_skips_folders_outside_home_unless_asked(isolated_home, gio, capsys, tmp_path):
    ext_gone, ext_ok = str(tmp_path / "drive" / "Photos"), str(tmp_path / "here")
    os.mkdir(ext_ok)
    recorded(ext_gone, ext_ok, str(isolated_home / "Gone"))
    cli.main(["prune", "--dry-run"])
    out = capsys.readouterr().out
    assert "Skipped 2 entries outside ~ (the drive may not be mounted); use --include-external" in out
    assert ext_gone not in out and "Would remove 1 of 3 entries" in out
    cli.main(["prune"])
    assert {e.folder for e in store.entries()} == {ext_gone, ext_ok}
    capsys.readouterr()
    cli.main(["prune", "--include-external"])
    out = capsys.readouterr().out
    assert f"removed   {ext_gone}" in out and "Skipped" not in out and "Removed 1 of 2 entries" in out
    assert [e.folder for e in store.entries()] == [ext_ok]


def test_prune_keeps_entries_it_cannot_check(isolated_home, gio, capsys, monkeypatch):
    locked, gone = str(isolated_home / "Locked"), str(isolated_home / "Gone")
    recorded(locked, gone)
    real = os.lstat

    def lstat(p, *args, **kw):
        if os.fspath(p) == locked:
            raise PermissionError(13, "Permission denied", p)
        return real(p, *args, **kw)
    monkeypatch.setattr(os, "lstat", lstat)
    cli.main(["prune"])
    out = capsys.readouterr().out
    assert "kept      ~/Locked: cannot check (Permission denied)" in out and "removed   ~/Gone" in out
    assert [e.folder for e in store.entries()] == [locked]


def test_prune_follows_symlinks_and_keeps_dangling_ones(isolated_home, gio, capsys, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    good, dangling = isolated_home / "Good", isolated_home / "Dangling"
    good.symlink_to(target)
    dangling.symlink_to(tmp_path / "unmounted" / "x")
    recorded(str(good), str(dangling))
    cli.main(["prune"])
    out = capsys.readouterr().out
    assert "kept      ~/Dangling: cannot check" in out and "Nothing to remove" in out
    assert len(store.entries()) == 2


def test_prune_never_deletes_icon_files(isolated_home, gio, sym):
    d = folder(isolated_home, "Moved")
    cli.main(["apply", d, sym])
    before = sorted(os.listdir(store.icons_dir()))
    os.rmdir(d)
    cli.main(["prune"])
    assert store.entries() == [] and before and sorted(os.listdir(store.icons_dir())) == before
    assert gio.calls == [d]                      # only the apply


def test_prune_keeps_unknown_fields_and_unusable_entries(isolated_home, gio):
    folder(isolated_home, "Music")
    write_manifest({"schema_version": 1, "future": {"x": 1},
                    "folders": [{"path": "Music", "note": "keep me",
                                 "recipe": {"symbol": "a", "accent": "red", "later": True}},
                                {"path": "Gone", "recipe": {"symbol": "a", "accent": "red"}},
                                {"path": "NoRecipe"}]})
    cli.main(["prune"])
    data = raw_manifest()
    assert data["future"] == {"x": 1}
    assert data["folders"] == [{"path": "Music", "note": "keep me",
                                "recipe": {"symbol": "a", "accent": "red", "later": True}},
                               {"path": "NoRecipe"}]


@pytest.mark.parametrize("args", [["prune"], ["prune", "--dry-run"]])
def test_prune_with_a_damaged_or_newer_manifest_changes_nothing(isolated_home, gio, args):
    write_manifest("{oops")
    with pytest.raises(SystemExit, match="folder-symbols: .*damaged"):
        cli.main(args)
    assert open(store.manifest_path()).read() == "{oops"
    newer = json.dumps({"schema_version": store.SCHEMA_VERSION + 1,
                        "folders": [{"path": "Gone", "recipe": {"symbol": "a", "accent": "red"}}]})
    write_manifest(newer)
    with pytest.raises(SystemExit, match="newer folder-symbols"):
        cli.main(args)
    assert open(store.manifest_path()).read() == newer


def test_remove_many_drops_all_entries_of_each_folder(isolated_home):
    a, b = str(isolated_home / "A"), str(isolated_home / "B")
    write_manifest({"schema_version": 1, "folders": [{"path": "A", "recipe": {"symbol": "x", "accent": "red"}},
                                                     {"path": "A"}, {"path": "B"}]})
    assert store.remove_many([a + "/", str(isolated_home / "C")]) == [a]
    assert raw_manifest()["folders"] == [{"path": "B"}]
    assert store.remove_many([]) == []


def test_prune_keeps_folders_below_a_dangling_symlinked_parent(isolated_home, gio, capsys, tmp_path):
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    (isolated_home / "Drive").symlink_to(tmp_path / "unmounted")          # the drive is not mounted
    (isolated_home / "Disk").symlink_to(mounted)                           # mounted, but X is really gone
    below_dangling = str(isolated_home / "Drive" / "Photos" / "2026")
    below_valid, plain = str(isolated_home / "Disk" / "X"), str(isolated_home / "Gone")
    recorded(below_dangling, below_valid, plain)
    cli.main(["prune"])
    out = capsys.readouterr().out
    assert "kept      ~/Drive/Photos/2026: cannot check (a parent directory is a symlink to a missing " \
           "target)" in out
    assert "removed   ~/Disk/X" in out and "removed   ~/Gone" in out and "Removed 2 of 3 entries" in out
    assert [e.folder for e in store.entries()] == [below_dangling]
