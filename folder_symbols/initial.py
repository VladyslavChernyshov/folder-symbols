"""The window's initial state for a folder selection, worked out from the manifest only (no GTK, no gio,
no gsettings; nothing is written and no lock is taken): which symbol to select and which accent to preview.

- every selected folder has a usable entry whose symbol is in the gallery, all with the same symbol:
  that symbol (and the accent, when they all share one; "system" (store.SYSTEM_ACCENT) when they all
  follow the system accent, none when some follow and some are pinned);
- anything else (no entry, some with and some without, different symbols): no symbol;
- an entry whose symbol is not in the gallery counts as no entry (and is named in one stderr line);
- a damaged or unreadable manifest counts as no entries; a newer schema is read normally."""
import os
from dataclasses import dataclass
from typing import Optional

from . import store
from .gallery import Symbol
from .selection import tilde
from .symbols import symbol_name


@dataclass(frozen=True)
class InitialState:
    symbol: Optional[Symbol] = None     # the gallery.Symbol to select, or None
    accent: Optional[str] = None        # the recorded accent every selected folder shares (an accent name,
                                        # or "system" when they all follow the system accent), or None
    message: Optional[str] = None       # one line for stderr (recorded symbols not found), or None


def read_manifest(path=None):
    """(manifest, message): the manifest read with store.load() (read only, no lock), or (None, one line)
    when it is damaged or cannot be read. A missing file is an empty manifest."""
    try:
        return store.load(path), None
    except store.ManifestError as e:
        return None, f"folder-symbols: {e}; recorded icons are ignored"


def resolve_symbol(recorded, by_name):
    """The gallery Symbol for a recipe's symbol, or None. apply records a name when the default symbols
    directory was used, else the absolute path of the file; a path matches the gallery symbol of the same
    name only if both are the same file (realpath, so a symlinked duplicate matches too)."""
    if not os.path.isabs(recorded):
        return by_name.get(recorded)
    candidate = by_name.get(symbol_name(recorded))
    if candidate and os.path.realpath(candidate.path) == os.path.realpath(recorded):
        return candidate
    return None


def initial_state(dirs, manifest, symbols, symbols_dir=None):
    """dirs: normalised folders (selection.normalise_paths); manifest: a store.Manifest or None;
    symbols: the gallery's Symbols; symbols_dir: only used in the message."""
    if manifest is None or not dirs:
        return InitialState()
    recipes = {e.folder: e.recipe for e in manifest.entries()}
    by_name = {s.name: s for s in symbols}
    found, missing = [], []
    for folder in dirs:
        recipe = recipes.get(folder)
        symbol = recipe and resolve_symbol(recipe.symbol, by_name)
        if recipe and not symbol:
            missing.append(f"{recipe.symbol} ({tilde(folder)})")
        found.append((symbol, recipe.accent) if symbol else None)
    message = None
    if missing:
        where = f" in {symbols_dir}" if symbols_dir else ""
        message = f"folder-symbols: recorded symbol not found{where}, showing none: {', '.join(missing)}"
    if any(f is None for f in found):
        return InitialState(message=message)
    symbols_found = {s for s, _ in found}
    accents = {a for _, a in found}
    return InitialState(symbol=symbols_found.pop() if len(symbols_found) == 1 else None,
                        accent=accents.pop() if len(accents) == 1 else None,
                        message=message)
