"""Fixtures of the GUI harness (no GTK): the generated symbol set used when the real Yaru symbols are absent,
an independent count of a symbols directory, and the folders and manifest entries of a scenario.

The symbols are simple shapes drawn here (our own work, MIT like the rest of the code), not copies of
Yaru. They are written at start-up into the run directory; nothing is committed."""
import os

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
       '<path fill="#2e3436" fill-rule="evenodd" d="{d}"/></svg>\n')
SHAPES = {
    "circle": "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z",
    "square": "M2 2h12v12H2z",
    "triangle": "M8 1l7 14H1z",
    "diamond": "M8 1l7 7-7 7-7-7z",
    "cross": "M6 1h4v5h5v4h-5v5H6v-5H1V6h5z",
    "ring": "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1zm0 3a4 4 0 1 1 0 8 4 4 0 1 1 0-8z",
    "bars": "M1 2h14v3H1zm0 4.5h14v3H1zm0 4.5h14v3H1z",
    "star": "M8 1l2.1 4.6 5 .5-3.8 3.3 1.1 4.9L8 11.8l-4.4 2.5 1.1-4.9L.9 6.1l5-.5z",
}
ROOT = ""            # symbols directly in the symbols directory: the gallery's category "other"

# (category, name). Several names contain "view" in different categories, so a search and a category
# narrow the grid differently; "star" lies in the root and in status: the root one wins (find_symbols
# walks the tree sorted, the first file of a name wins), so the gallery shows it once.
SYMBOLS = (
    ("actions", "edit-copy"), ("actions", "edit-paste"), ("actions", "go-next"), ("actions", "go-previous"),
    ("actions", "list-add"), ("actions", "view-grid"), ("actions", "view-list"), ("actions", "view-refresh"),
    ("apps", "app-calculator"), ("apps", "app-mail"), ("apps", "app-music"), ("apps", "app-photos"),
    ("apps", "app-terminal"), ("apps", "app-weather"),
    ("devices", "camera-photo"), ("devices", "drive-disk"), ("devices", "input-keyboard"),
    ("devices", "input-mouse"), ("devices", "phone"), ("devices", "printer"),
    ("places", "folder-home"), ("places", "folder-music"), ("places", "folder-pictures"),
    ("places", "folder-videos"), ("places", "network-server"), ("places", "user-trash"), ("places", "view-pin"),
    ("status", "audio-volume"), ("status", "battery-full"), ("status", "dialog-info"),
    ("status", "network-wireless"), ("status", "star"), ("status", "weather-clear"),
    (ROOT, "circle"), (ROOT, "square"), (ROOT, "star"), (ROOT, "triangle"),
)


def fixture_names():
    """{name: category} of the generated set as the gallery shows it (the root "star" wins)."""
    names = {}
    for category, name in sorted(SYMBOLS, key=lambda s: (s[0] != ROOT, s[0], s[1])):
        names.setdefault(name, category or "other")
    return names


def write_symbols(dest):
    """Write the generated set under dest; returns dest."""
    shapes = list(SHAPES.values())
    for i, (category, name) in enumerate(SYMBOLS):
        folder = os.path.join(dest, category) if category else dest
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{name}-symbolic.svg"), "w", encoding="utf-8") as f:
            f.write(SVG.format(d=shapes[i % len(shapes)]))
    return dest


def count_symbols(symbols_dir):
    """The number of distinct symbol names under symbols_dir, counted here and not with the package's own
    code: every *-symbolic.svg that exists (a broken symlink does not), each name once."""
    names = set()
    for dirpath, _dirs, files in os.walk(symbols_dir):
        for f in files:
            if f.endswith("-symbolic.svg") and os.path.exists(os.path.join(dirpath, f)):
                names.add(f[:-len("-symbolic.svg")])
    return len(names)


def count_matching(symbols_dir, query, category):
    """The number of symbols the gallery shows for this search text and category, counted here and not with
    the package's own code, by the gallery's rule: the directory is walked in sorted order and the first
    existing *-symbolic.svg of a name wins (its first-level subdirectory is the category, "other" for files
    directly in symbols_dir); a symbol matches when the stripped, casefolded query is a substring of its
    casefolded name (the name only) and its category equals category (None: any)."""
    winners = {}
    for dirpath, _dirs, files in sorted(os.walk(symbols_dir)):
        for f in sorted(files):
            name = f[:-len("-symbolic.svg")]
            if not f.endswith("-symbolic.svg") or name in winners or not os.path.exists(os.path.join(dirpath, f)):
                continue
            rel = os.path.relpath(dirpath, symbols_dir)
            winners[name] = "other" if rel == os.curdir else rel.split(os.sep)[0]
    needle = query.strip().casefold()
    return sum(1 for name, cat in winners.items()
               if needle in name.casefold() and (category is None or cat == category))


def has_symbols(symbols_dir):
    return os.path.isdir(symbols_dir) and count_symbols(symbols_dir) > 0


def symbol_exists(symbols_dir, name):
    for dirpath, _dirs, files in os.walk(symbols_dir):
        if f"{name}-symbolic.svg" in files:
            return True
    return False


class Context:
    """What prepare(ctx) works with, in the scenario's sandbox HOME: folders, files, links and manifest
    entries (through folder_symbols.store, which computes the manifest path in this environment)."""

    def __init__(self, home, symbols_dir, symbols_source):
        self.home = home
        self.symbols_dir = symbols_dir
        self.symbols_source = symbols_source       # "yaru" or "fixture"

    def path(self, name):
        return os.path.join(self.home, name)

    def folder(self, name):
        p = self.path(name)
        os.makedirs(p, exist_ok=True)
        return p

    def file(self, name, text="x\n"):
        p = self.path(name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def broken_link(self, name):
        p = self.path(name)
        os.symlink(self.path(name + "-target-that-does-not-exist"), p)
        return p

    def symbol(self, *preferred):
        """The first of these names that the symbols directory has."""
        for name in preferred:
            if symbol_exists(self.symbols_dir, name):
                return name
        raise LookupError(f"none of {preferred} in {self.symbols_dir}")

    @staticmethod
    def record(folder, symbol, accent):
        from folder_symbols import store
        store.record(folder, store.Recipe(symbol, accent))

    @staticmethod
    def manifest_path():
        from folder_symbols import store
        return store.manifest_path()
