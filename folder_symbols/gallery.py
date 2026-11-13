"""The symbol gallery's data: listing, categories and filtering of symbols (no GTK)."""
import os
from dataclasses import dataclass

from .symbols import find_symbols

ROOT_CATEGORY = "other"   # category of symbols that lie directly in the symbols directory


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


def categories(symbols):
    return sorted({s.category for s in symbols})


def matches(symbol, query, category):
    """query: case-insensitive substring of the name (surrounding spaces ignored, empty matches all);
    category None means all categories."""
    if category is not None and symbol.category != category:
        return False
    return query.strip().casefold() in symbol.name.casefold()


def filter_symbols(symbols, query, category):
    return [s for s in symbols if matches(s, query, category)]
