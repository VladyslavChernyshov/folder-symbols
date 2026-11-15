"""The accent picker's data (no GTK): which accents it offers and in what order, their names, swatch colours,
the system accent, the initial choice, and the "Follow system accent" state with the apply_folders arguments
it gives. Accent names are the ones the manifest records (yaru.accents())."""
import dataclasses, subprocess
from typing import Optional

from . import yaru
from .store import SYSTEM_ACCENT

# The normal Yaru accents in the order of the mock7 mockup. Yaru-mate is a separate variant (another
# folder drawing in light), offered only when the folders or the system use it.
PICKER_ORDER = ("orange", "blue", "purple", "red", "viridian", "magenta", "prussiangreen", "olive", "sage",
                "bark", "wartybrown", "yellow")
MATE = "mate"
DEFAULT_ACCENT = "orange"            # plain Yaru, also the preview's fallback on a non-Yaru system
_LABELS = {"prussiangreen": "Prussian Green", "wartybrown": "Warty Brown", "mate": "MATE"}


def picker_accents(*needed):
    """The accents to show: PICKER_ORDER, plus MATE at the end when it is one of `needed`."""
    return list(PICKER_ORDER) + ([MATE] if MATE in needed else [])


def accent_label(accent):
    """'sage' -> 'Sage', 'prussiangreen' -> 'Prussian Green'."""
    return _LABELS.get(accent, accent.replace("-", " ").title())


def swatch_tooltip(accent, is_system):
    """Tooltip and accessible label of a swatch: 'Sage', or 'Sage (system accent)'."""
    return f"{accent_label(accent)} (system accent)" if is_system else accent_label(accent)


def swatch_colors(accent):
    """(light, dark): the folder colour of the accent's light and dark variant (themes.json colors[0]),
    the colour the preview is drawn in. Light Yaru-mate has fixed artwork without one, so it takes the
    dark variant's."""
    themes = yaru.builtin_themes()
    light = themes[yaru.variant_name(accent, False)]["colors"]
    dark = themes[yaru.variant_name(accent, True)]["colors"]
    return (light or dark)[0], dark[0]


def system_accent():
    """The accent of the current icon theme, or None when it is not a Yaru variant or cannot be read."""
    try:
        v = yaru.parse_variant(yaru.current_icon_theme())
    except (OSError, subprocess.CalledProcessError):
        return None
    return v[0] if v else None


# ------------------------------------------------------------- following the system accent
@dataclasses.dataclass(frozen=True)
class AccentChoice:
    """The picker's state: the "Follow system accent" switch, the selected swatch (the accent the preview
    draws) and the system accent (None when unknown). follow is only ever True with a known system accent,
    and then selected is the system accent."""
    follow: bool
    selected: str
    system: Optional[str]

    @property
    def follow_available(self):
        return self.system in yaru.accents()


def initial_follow(recorded, system):
    """Whether the switch starts on: the system accent is known and the folders record no concrete accent
    ("system", no entry or mixed folders (None), or a name that is not an accent)."""
    return system in yaru.accents() and recorded not in yaru.accents()


def initial_choice(recorded, system):
    """The state for a new folder selection (recorded: InitialState.accent)."""
    if initial_follow(recorded, system):
        return AccentChoice(True, system, system)
    known = system if system in yaru.accents() else None
    return AccentChoice(False, recorded if recorded in yaru.accents() else DEFAULT_ACCENT, known)


def pick(choice, accent):
    """The user chose a swatch (any one, even the system's or the one already selected): pinned to it."""
    return dataclasses.replace(choice, follow=False, selected=accent)


def set_follow(choice, on):
    """The user turned the switch on (the system swatch is selected; nothing happens without a system
    accent) or off (the current swatch is kept, pinned)."""
    if on and choice.follow_available:
        return dataclasses.replace(choice, follow=True, selected=choice.system)
    return dataclasses.replace(choice, follow=False)


def system_changed(choice, system):
    """The system icon theme changed: a following choice moves to the new system accent; a pinned one keeps
    its swatch. With no system accent following stops (the swatch shown is kept), and it does not come back
    by itself when the system accent is known again."""
    system = system if system in yaru.accents() else None
    if choice.follow and system:
        return AccentChoice(True, system, system)
    return AccentChoice(False, choice.selected, system)


def apply_choice(follow, selected, system):
    """(accent, system_accent) for apply_folders: following with a known system accent gives
    (SYSTEM_ACCENT, system), anything else pins the accent shown: (selected, None)."""
    if follow and system in yaru.accents():
        return SYSTEM_ACCENT, system
    return selected, None


@dataclasses.dataclass(frozen=True)
class PanelChoice:
    """What the preview panel would apply, as apply_folders takes it."""
    accent: str                         # SYSTEM_ACCENT or a concrete accent
    system_accent: Optional[str]        # the accent drawn when following, else None
    dark: bool                          # the style the preview was last drawn in
    symbol: Optional[object] = None     # the selected gallery.Symbol, None when there is none


def panel_choice(choice, dark, symbol):
    """The PanelChoice of an AccentChoice drawn in this style with this symbol."""
    accent, system = apply_choice(choice.follow, choice.selected, choice.system)
    return PanelChoice(accent, system, dark, symbol)
