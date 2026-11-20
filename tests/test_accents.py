"""The accent picker's data (folder_symbols/accents.py): no GTK; gsettings is conftest's failing stub."""
import ast
import json
import re
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from folder_symbols import yaru
from folder_symbols.accents import (MATE, PICKER_ORDER, AccentChoice, PanelChoice, accent_label, apply_choice,
                                    initial_choice, initial_follow, panel_choice, pick,
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


# ------------------------------------------------------------- the window's CSS (still no GTK)
GUI_ACCENTS = ROOT / "folder_symbols" / "gui" / "accents.py"
_LENGTH = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)(px|%|pt|em|rem|ex|cm|mm|in|pc)?$")
_STOP_KEYWORDS = {"circle", "ellipse", "to", "at", "closest-side", "farthest-side", "closest-corner",
                  "farthest-corner"}


def _split_top(text, on_space):
    """Split on commas (or runs of whitespace) outside parentheses, so rgb(0 0 0 / 50%) stays one piece."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and (ch.isspace() if on_space else ch == ","):
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def gradient_stop_errors(css):
    """The colour stops inside every *-gradient(...) of `css` that have more than one position. GTK 4.14's
    parser takes one position per stop, and drops the whole declaration on a second one."""
    errors = []
    for m in re.finditer(r"[\w-]*gradient\(", css):
        depth, i = 1, m.end()
        while i < len(css) and depth:
            depth += (css[i] == "(") - (css[i] == ")")
            i += 1
        for arg in _split_top(css[m.end():i - 1], on_space=False):
            tokens = _split_top(arg, on_space=True)
            if not tokens or tokens[0] in _STOP_KEYWORDS or "at" in tokens or re.match(r"^[\d.]+(deg|rad|turn)$", tokens[0]):
                continue                                    # the shape, size, direction or angle argument
            if sum(bool(_LENGTH.match(t)) for t in tokens[1:]) > 1:
                errors.append(f"{m.group(0)}...{arg}")
    return errors


def _is_gi_import(node):
    """An absolute `import gi...` / `from gi... import ...`."""
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] == "gi" for a in node.names)
    return isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "gi"


def _gi_names(tree):
    """The names that gi imports bind anywhere in the module: `import gi` and `import gi.repository` bind gi,
    `import gi.repository as R` binds R, `from gi.repository import Gtk, Gdk as D` binds Gtk and D."""
    names = set()
    for node in ast.walk(tree):
        if not _is_gi_import(node):
            continue
        for alias in node.names:
            if alias.name == "*":
                pytest.fail(f"{GUI_ACCENTS.name}:{node.lineno}: `from gi... import *` binds names the test cannot "
                            f"know; import them by name, or teach _gi_names about them")
            bound = alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name
            names.add(alias.asname or bound)
    return names


def _gui_accents_namespace():
    """Run the top-level statements of gui/accents.py that need no GTK (constants, imports of our own modules,
    function definitions), so the CSS is the text the window really loads. A statement is skipped if it imports
    from gi or mentions a name a gi import bound (a class that depends on gi, a `gi.require_version(...)` call,
    a try/if around either); anything else is run, and a failure names the file and line."""
    tree = ast.parse(GUI_ACCENTS.read_text(), str(GUI_ACCENTS))
    gi_names = _gi_names(tree)
    namespace = {"__name__": "gui_accents_css"}
    for node in tree.body:
        if any(_is_gi_import(n) or (isinstance(n, ast.Name) and n.id in gi_names) for n in ast.walk(node)):
            continue
        try:
            exec(compile(ast.Module([node], []), str(GUI_ACCENTS), "exec"), namespace)
        except Exception as e:
            pytest.fail(f"{GUI_ACCENTS.name}:{node.lineno}: this top-level statement cannot be evaluated without "
                        f"GTK ({type(e).__name__}: {e}); move what it needs into a GTK-free module or teach "
                        f"_gui_accents_namespace to skip it")
    for name in ("BASE_CSS", "_accent_css"):
        assert name in namespace, f"{GUI_ACCENTS.name} no longer defines {name}; update _gui_accents_namespace"
    return namespace


def test_gui_css_has_no_two_position_color_stops():
    """GTK 4.18.6 rejects `color 3px 4px` in a radial-gradient (and drops the declaration); the API floor
    is 4.14, which takes one position per stop. Checks the generated text, not a copy of it."""
    namespace = _gui_accents_namespace()
    css = namespace["BASE_CSS"] + namespace["_accent_css"]()
    assert css.count("gradient(") >= 2, "no gradients found: the check would pass without looking at anything"
    assert gradient_stop_errors(css) == []


def test_gradient_stop_checker():
    assert gradient_stop_errors("a { background-image: radial-gradient(circle, red 3px, blue 3px 4px); }")
    assert gradient_stop_errors("a { background-image: linear-gradient(to right, red 1px 2px, blue); }")
    assert not gradient_stop_errors("radial-gradient(circle, red 3px, blue 3px, blue 4px, transparent 4px)")
    assert not gradient_stop_errors("radial-gradient(circle at 50% 50%, rgb(0 0 0 / 50%) 3px, @x 4px)")
    assert not gradient_stop_errors("linear-gradient(45deg, red, blue 50%)")
