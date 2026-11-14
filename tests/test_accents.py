"""The accent picker's data (folder_symbols/accents.py): no GTK; gsettings is conftest's failing stub."""
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from folder_symbols import accents, yaru
from folder_symbols.accents import (MATE, PICKER_ORDER, AccentChoice, PanelChoice, accent_label, apply_choice,
                                    initial_accent, initial_choice, initial_follow, panel_choice, pick,
                                    picker_accents, set_follow, swatch_colors, swatch_tooltip, system_accent,
                                    system_changed)
from folder_symbols.store import SYSTEM_ACCENT

ROOT = Path(__file__).parent.parent
THEMES = json.loads((ROOT / "assets" / "themes.json").read_text())["themes"]


def test_picker_order_is_every_accent_but_mate():
    assert len(PICKER_ORDER) == len(set(PICKER_ORDER)) == 12
    assert set(PICKER_ORDER) == set(yaru.accents()) - {MATE}


def test_mate_only_when_needed():
    assert picker_accents() == list(PICKER_ORDER)
    assert picker_accents("sage", None) == list(PICKER_ORDER)
    assert picker_accents("mate", "sage") == list(PICKER_ORDER) + ["mate"]
    assert picker_accents(None, "mate") == list(PICKER_ORDER) + ["mate"]


@pytest.mark.parametrize("accent, label", [
    ("orange", "Orange"), ("sage", "Sage"), ("prussiangreen", "Prussian Green"),
    ("wartybrown", "Warty Brown"), ("mate", "MATE"), ("viridian", "Viridian"),
])
def test_labels(accent, label):
    assert accent_label(accent) == label


def test_every_accent_has_a_label():
    for a in yaru.accents():
        assert accent_label(a) and accent_label(a)[0].isupper()


def test_tooltips():
    assert swatch_tooltip("sage", False) == "Sage"
    assert swatch_tooltip("sage", True) == "Sage (system accent)"


@pytest.mark.parametrize("accent", sorted(set(PICKER_ORDER)))
def test_swatch_colors_are_the_folder_colours(accent):
    light, dark = swatch_colors(accent)
    assert light == THEMES[yaru.variant_name(accent, False)]["colors"][0]
    assert dark == THEMES[yaru.variant_name(accent, True)]["colors"][0]


def test_mate_light_swatch_takes_the_dark_colour():
    assert THEMES["Yaru-mate"]["colors"] == []
    assert swatch_colors("mate") == (THEMES["Yaru-mate-dark"]["colors"][0],) * 2


@pytest.mark.parametrize("theme, accent", [
    ("Yaru-sage-dark", "sage"), ("Yaru", "orange"), ("Yaru-dark", "orange"), ("Yaru-mate", "mate"),
    ("Adwaita", None), ("Yaru-nosuch", None), ("", None),
])
def test_system_accent(monkeypatch, theme, accent):
    monkeypatch.setattr(yaru, "current_icon_theme", lambda: theme)
    assert system_accent() == accent


def test_system_accent_when_gsettings_fails(monkeypatch):
    assert system_accent() is None                      # conftest's gsettings stub exits with an error
    monkeypatch.setenv("PATH", "/nonexistent")          # gsettings missing altogether
    assert system_accent() is None


@pytest.mark.parametrize("recorded, system, expected", [
    ("purple", "sage", "purple"), ("mate", None, "mate"), (None, "sage", "sage"),
    ("nosuch", "sage", "sage"), (None, None, "orange"), ("nosuch", None, "orange"), (None, "nosuch", "orange"),
    ("system", "sage", "sage"), ("system", None, "orange"),     # a following folder previews the system's
])
def test_initial_accent(recorded, system, expected):
    assert initial_accent(recorded, system) == expected


def test_accents_module_does_not_import_gi():
    code = "import folder_symbols.accents, sys; assert 'gi' not in sys.modules, 'gi was imported'"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------------- follow the system accent
RECORDED = [None, "system", "nosuch", "sage", "mate"]
SYSTEMS = ["sage", "orange", "mate", None, "nosuch"]


@pytest.mark.parametrize("system", SYSTEMS)
@pytest.mark.parametrize("recorded", RECORDED)
def test_initial_follow(recorded, system):
    expected = system in yaru.accents() and recorded in (None, "system", "nosuch")
    assert initial_follow(recorded, system) is expected


@pytest.mark.parametrize("recorded, system, expected", [
    ("system", "sage", AccentChoice(True, "sage", "sage")),
    (None, "sage", AccentChoice(True, "sage", "sage")),             # no entry or mixed folders
    ("nosuch", "bark", AccentChoice(True, "bark", "bark")),         # not an accent: like no entry
    ("system", "mate", AccentChoice(True, "mate", "mate")),
    ("purple", "sage", AccentChoice(False, "purple", "sage")),
    ("sage", "sage", AccentChoice(False, "sage", "sage")),          # pinned to the system's colour
    ("mate", "orange", AccentChoice(False, "mate", "orange")),
    ("system", None, AccentChoice(False, "orange", None)),          # no system accent: orange, pinned
    (None, None, AccentChoice(False, "orange", None)),
    ("red", None, AccentChoice(False, "red", None)),
    ("system", "nosuch", AccentChoice(False, "orange", None)),      # an unknown system accent is none
])
def test_initial_choice(recorded, system, expected):
    assert initial_choice(recorded, system) == expected


FOLLOWING = AccentChoice(True, "sage", "sage")
PINNED = AccentChoice(False, "red", "sage")


@pytest.mark.parametrize("start", [FOLLOWING, PINNED, AccentChoice(False, "orange", None)])
@pytest.mark.parametrize("accent", ["sage", "red", "blue", "orange"])
def test_any_swatch_click_pins(start, accent):
    """Also the system's own swatch while following, and the swatch that is already selected."""
    assert pick(start, accent) == AccentChoice(False, accent, start.system)


def test_switch_on_selects_the_system_swatch():
    assert set_follow(PINNED, True) == AccentChoice(True, "sage", "sage")
    assert set_follow(FOLLOWING, True) == FOLLOWING


def test_switch_on_without_a_system_accent_stays_pinned():
    c = AccentChoice(False, "red", None)
    assert not c.follow_available and set_follow(c, True) == c


def test_switch_off_keeps_the_swatch_pinned():
    assert set_follow(FOLLOWING, False) == AccentChoice(False, "sage", "sage")
    assert set_follow(PINNED, False) == PINNED


def test_system_change_moves_a_following_choice_and_keeps_a_pinned_one():
    assert system_changed(FOLLOWING, "bark") == AccentChoice(True, "bark", "bark")
    assert system_changed(PINNED, "bark") == AccentChoice(False, "red", "bark")


@pytest.mark.parametrize("unknown", [None, "nosuch"])
def test_losing_the_system_accent_stops_following_and_it_does_not_come_back(unknown):
    lost = system_changed(FOLLOWING, unknown)
    assert lost == AccentChoice(False, "sage", None) and not lost.follow_available
    assert system_changed(lost, "bark") == AccentChoice(False, "sage", "bark")      # stays pinned
    assert system_changed(PINNED, unknown) == AccentChoice(False, "red", None)


@pytest.mark.parametrize("follow", [True, False])
@pytest.mark.parametrize("selected", ["sage", "red", "mate"])
@pytest.mark.parametrize("system", ["sage", "mate", None, "nosuch"])
def test_apply_choice(follow, selected, system):
    expected = (SYSTEM_ACCENT, system) if follow and system in yaru.accents() else (selected, None)
    assert apply_choice(follow, selected, system) == expected


def test_follow_can_never_be_applied_without_a_system_accent():
    for c in (initial_choice("system", None), system_changed(FOLLOWING, None),
              set_follow(AccentChoice(False, "orange", None), True)):
        assert panel_choice(c, False, None).accent != SYSTEM_ACCENT


def test_panel_choice_is_frozen_and_carries_style_and_symbol():
    sym = object()
    c = panel_choice(FOLLOWING, True, sym)
    assert c == PanelChoice(SYSTEM_ACCENT, "sage", True, sym)
    assert panel_choice(PINNED, False, None) == PanelChoice("red", None, False, None)
    with pytest.raises(FrozenInstanceError):
        c.dark = False
    with pytest.raises(FrozenInstanceError):
        FOLLOWING.follow = False


def test_the_choice_drawn_is_the_choice_applied():
    """Following draws the system accent and passes it as system_accent; pinned draws and passes selected."""
    for c in (FOLLOWING, PINNED, set_follow(PINNED, True), pick(FOLLOWING, "sage")):
        p = panel_choice(c, False, None)
        assert (p.system_accent if p.accent == SYSTEM_ACCENT else p.accent) == c.selected
