"""The symbol gallery's data: listing, categories and filtering of symbols, and the page shown instead of the
gallery when there are none (no GTK)."""
import os
from dataclasses import dataclass

from .symbols import find_symbols

ROOT_CATEGORY = "other"   # category of symbols that lie directly in the symbols directory
NO_SYMBOLS_TITLE = "Symbols not found"   # title of the page shown instead of the gallery


@dataclass(frozen=True)
class Symbol:
    name: str       # without "-symbolic", the name `apply` accepts
    category: str   # first-level subfolder of the symbols directory (actions, apps, ...)
    path: str


def _category(symbols_dir, path):
    rel = os.path.relpath(os.path.dirname(path), symbols_dir)
    return ROOT_CATEGORY if rel == os.curdir else rel.split(os.sep)[0]


def list_symbols(symbols_dir):
    """All *-symbolic.svg under symbols_dir, one per name (the same winner as the CLI), sorted by name
    case-insensitively. A missing or empty directory gives []."""
    found = find_symbols(symbols_dir, None)
    syms = [Symbol(name, _category(symbols_dir, path), path) for name, path in found.items()]
    return sorted(syms, key=lambda s: (s.name.casefold(), s.name))


def load_symbols(symbols_dir):
    """Return (symbols, problem); problem is a message when there is nothing to show."""
    if not os.path.isdir(symbols_dir):
        return [], f"Folder does not exist: {symbols_dir}"
    try:
        symbols = list_symbols(symbols_dir)
    except OSError as e:
        return [], f"Cannot read {symbols_dir}: {e.strerror or e}"
    if not symbols:
        return [], f"No *-symbolic.svg files in {symbols_dir}"
    return symbols, None


def no_symbols_description(problem):
    """The text of the page shown instead of the gallery: the problem from load_symbols and the install hint."""
    return (f"{problem}\n\nInstall yaru-theme-icon or point YARU_SYMBOLS_DIR at a folder with "
            "*-symbolic.svg files.")


def categories(symbols):
    return sorted({s.category for s in symbols})


def matches(symbol, query, category):
    """query: case-insensitive substring of the name (surrounding spaces ignored, empty matches all);
    category None means all categories."""
    if category is not None and symbol.category != category:
        return False
    return query.strip().casefold() in symbol.name.casefold()


def search_placeholder(symbols, category):
    """Placeholder of the search entry, with the number of symbols the search runs over:
    "Search 1323 symbols…" for all categories (category None), "Search 87 symbols in apps…" for one."""
    n = len(symbols) if category is None else sum(1 for s in symbols if s.category == category)
    noun = "symbol" if n == 1 else "symbols"
    return f"Search {n} {noun}…" if category is None else f"Search {n} {noun} in {category}…"


def category_tooltip(category):
    """Tooltip of the button that clears the chosen category."""
    return f"Category: {category}. Click to show all"
