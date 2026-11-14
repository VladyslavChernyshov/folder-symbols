"""The GUI's folder preview builder (folder_symbols/preview.py): no GTK, temporary directories only."""
import os
import xml.etree.ElementTree as ET

import pytest

from conftest import SYMBOLS_DIR
from folder_symbols import preview, yaru
from folder_symbols.preview import PreviewError, PreviewSession, resolve_variant, system_variant, variant_for
from folder_symbols.svg import make_svg
from folder_symbols.symbols import find_symbols, load_overrides, symbol_name

SQUARE = '<rect x="3" y="3" width="10" height="10" fill="#222"/>'


@pytest.fixture
def symbol(svg):
    return svg("sq", SQUARE, 'viewBox="0 0 16 16"')


@pytest.fixture
def session(tmp_path):
    with PreviewSession(base_dir=tmp_path / "session-base") as s:
        yield s


@pytest.fixture(autouse=True)
def session_base(tmp_path):
    (tmp_path / "session-base").mkdir()


# ------------------------------------------------------------- choosing the variant
@pytest.mark.parametrize("theme", ["Yaru", "Yaru-dark", "Yaru-sage-dark", "Yaru-mate"])
def test_yaru_variant_is_kept(theme):
    assert resolve_variant(theme, dark=False) == theme
    assert resolve_variant(theme, dark=True) == theme


@pytest.mark.parametrize("theme", ["Adwaita", "breeze", None, "", "Yaru-nosuch", "Yaru-nosuch-dark"])
def test_non_yaru_theme_falls_back_to_default_yaru_in_the_given_style(theme):
    assert resolve_variant(theme, dark=False) == "Yaru"
    assert resolve_variant(theme, dark=True) == "Yaru-dark"


def test_system_variant_when_gsettings_fails(monkeypatch):
    # conftest replaces gsettings with a stub that fails
    assert system_variant(dark=True) == "Yaru-dark"
    monkeypatch.setenv("PATH", "/nonexistent")             # gsettings missing altogether
    assert system_variant(dark=False) == "Yaru"


def test_system_variant_uses_the_current_icon_theme(monkeypatch):
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: "Yaru-blue")
    assert system_variant(dark=True) == "Yaru-blue"
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: "Adwaita")
    assert system_variant(dark=True) == "Yaru-dark"


@pytest.mark.parametrize("accent, dark, expected", [
    ("purple", False, "Yaru-purple"), ("purple", True, "Yaru-purple-dark"),
    ("orange", False, "Yaru"), ("orange", True, "Yaru-dark"), ("mate", True, "Yaru-mate-dark"),
])
def test_variant_for_a_recorded_accent(accent, dark, expected):
    assert variant_for(accent, dark) == expected


@pytest.mark.parametrize("accent", [None, "", "nosuch"])
def test_variant_for_no_or_unknown_accent_is_the_system_variant(monkeypatch, accent):
    # conftest's gsettings stub fails, so the system variant is plain Yaru in the given style
    assert variant_for(accent, True) == "Yaru-dark"
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: "Yaru-blue")
    assert variant_for(accent, False) == "Yaru-blue"


@pytest.mark.parametrize("path, name", [
    ("/x/apps/community-symbolic.svg", "community"), ("/x/logo.svg", "logo"), ("rel/a-b-symbolic.svg", "a-b"),
])
def test_symbol_name(path, name):
    assert symbol_name(path) == name


# ------------------------------------------------------------- building
def test_no_symbol_builds_nothing(session):
    assert session.build(None, "Yaru") is None
    assert os.listdir(session.dir) == []


@pytest.mark.parametrize("variant", ["Yaru", "Yaru-purple-dark", "Yaru-mate"])
def test_selected_symbol_gives_a_valid_svg_in_the_session_dir(session, symbol, variant):
    path = session.build(symbol, variant)
    assert os.path.dirname(path) == session.dir
    assert os.path.basename(path) == f"{variant}-sq.svg"
    root = ET.parse(path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    text = open(path, encoding="utf-8").read()
    assert 'id="fs-symbol"' in text
    colors = yaru.builtin_themes()[variant]["colors"]
    assert not colors or colors[0] in text                 # light Yaru-mate has fixed colours


def test_non_yaru_system_theme_still_builds(session, symbol):
    path = session.build(symbol, resolve_variant("Adwaita", dark=True))
    assert os.path.basename(path) == "Yaru-dark-sq.svg"
    ET.parse(path)


def test_preview_is_make_svg_without_options(session, symbol):
    path = session.build(symbol, "Yaru-dark")
    assert open(path, encoding="utf-8").read() == make_svg("Yaru-dark", symbol)


def test_unknown_variant_is_an_error_not_an_exit(session, symbol):
    with pytest.raises(PreviewError):
        session.build(symbol, "Adwaita")
    assert os.listdir(session.dir) == []


@pytest.mark.parametrize("content", ["not an svg", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"/>'])
def test_broken_symbol_is_a_preview_error(session, tmp_path, content):
    p = tmp_path / "broken-symbolic.svg"
    p.write_text(content)
    with pytest.raises(PreviewError):
        session.build(str(p), "Yaru")


def test_missing_symbol_is_a_preview_error(session, tmp_path):
    with pytest.raises(PreviewError):
        session.build(str(tmp_path / "gone-symbolic.svg"), "Yaru")


# ------------------------------------------------------------- the temporary directory
def test_close_removes_the_directory_and_can_be_repeated(tmp_path, symbol):
    s = PreviewSession(base_dir=tmp_path / "session-base")
    s.build(symbol, "Yaru")
    assert os.path.isdir(s.dir)
    s.close()
    assert not os.path.exists(s.dir)
    s.close()


def test_with_block_removes_the_directory(tmp_path, symbol):
    with PreviewSession(base_dir=tmp_path / "session-base") as s:
        s.build(symbol, "Yaru")
    assert not os.path.exists(s.dir)
    assert os.listdir(tmp_path / "session-base") == []


def test_default_directory_is_in_the_system_temp_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(preview.tempfile, "tempdir", str(tmp_path / "session-base"))
    with PreviewSession() as s:
        assert os.path.dirname(s.dir) == str(tmp_path / "session-base")
        assert os.path.basename(s.dir).startswith("folder-symbols-preview-")


def test_building_writes_nothing_outside_the_session_dir(isolated_home, session, symbol):
    session.build(symbol, "Yaru")
    assert list(isolated_home.rglob("*")) == []            # no store, no manifest


# ------------------------------------------------------------- with the real Yaru symbols
needs_symbols = pytest.mark.skipif(not os.path.isdir(SYMBOLS_DIR), reason=f"no Yaru symbols in {SYMBOLS_DIR}")


@needs_symbols
def test_real_symbol(session):
    path = session.build(find_symbols(SYMBOLS_DIR, None)["audio-x-generic"], "Yaru-sage")
    ET.parse(path)


@needs_symbols
def test_overridden_symbol_gets_its_overrides(session):
    name, ov = next(iter(load_overrides().items()))
    sym = find_symbols(SYMBOLS_DIR, None)[name]
    expected = make_svg("Yaru", sym, ov.get("scale", 1.0), ov.get("align", "bbox"), ov.get("dx", 0.0),
                        ov.get("dy", 0.0))
    assert expected != make_svg("Yaru", sym)
    assert open(session.build(sym, "Yaru"), encoding="utf-8").read() == expected
