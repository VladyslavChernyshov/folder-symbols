"""The accent picker's data (no GTK): which accents it offers and in what order, their names, swatch colours,
the system accent and the initial choice. Accent names are the ones the manifest records (yaru.accents())."""
import subprocess

from . import yaru

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


def initial_accent(recorded, system):
    """The accent selected when a folder selection is shown: the folders' recorded one when it is a known
    accent, else the system's, else DEFAULT_ACCENT."""
    if recorded in yaru.accents():
        return recorded
    return system if system in yaru.accents() else DEFAULT_ACCENT
