"""The accent picker's data (folder_symbols/accents.py): no GTK; gsettings is conftest's failing stub."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from folder_symbols import accents, yaru
from folder_symbols.accents import (MATE, PICKER_ORDER, accent_label, initial_accent, picker_accents,
                                    swatch_colors, swatch_tooltip, system_accent)

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
])
def test_initial_accent(recorded, system, expected):
    assert initial_accent(recorded, system) == expected


def test_accents_module_does_not_import_gi():
    code = "import folder_symbols.accents, sys; assert 'gi' not in sys.modules, 'gi was imported'"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
