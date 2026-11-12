"""The local store: $XDG_DATA_HOME/folder-symbols/ (default ~/.local/share/folder-symbols/) with
manifest.json, one recipe per folder that has a custom icon, and icons/, the generated files Nautilus
reads. No gio and no theme code here: callers pass in what they need, so any front end can use it.

manifest.json, schema 1:
  {"schema_version": 1,
   "folders": [{"path": "Music", "recipe": {"symbol": "community", "accent": "purple",
                                            "scale": 1.0, "align": "bbox"}}, ...]}
"path" is relative to $HOME for folders inside it ("." is $HOME itself), absolute for the others.
The light/dark style is not stored: it follows the system theme whenever an icon is built."""
import contextlib, dataclasses, errno, fcntl, json, os, stat, tempfile, urllib.parse

SCHEMA_VERSION = 1
# {version: function(data) -> data in schema version + 1}; the first one comes with schema 2.
MIGRATIONS = {}


class ManifestError(Exception):
    """The manifest cannot be read or must not be written; the message says why and what to do."""


def data_dir():
    base = os.environ.get("XDG_DATA_HOME", "")
    if not os.path.isabs(base):                   # the XDG spec says to ignore relative values
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "folder-symbols")


def icons_dir():
    return os.path.join(data_dir(), "icons")


def manifest_path():
    return os.path.join(data_dir(), "manifest.json")


def _home():
    return os.path.abspath(os.path.expanduser("~"))


def folder_path(folder):
    """The absolute form used everywhere in this module (no symlinks resolved, like gio)."""
    return os.path.abspath(os.path.expanduser(folder))


def folder_key(folder):
    """Absolute folder -> the manifest's "path": relative to $HOME inside it, absolute outside."""
    folder, home = folder_path(folder), _home()
    return os.path.relpath(folder, home) if os.path.commonpath([folder, home]) == home else folder


def folder_from_key(key):
    return os.path.normpath(os.path.join(_home(), key))     # an absolute key ignores $HOME


@dataclasses.dataclass(frozen=True)
class Recipe:
    """How a folder's icon is built. symbol: a name in Yaru's scalable tree, or an absolute file path."""
    symbol: str
    accent: str
    scale: float = 1.0
    align: str = "bbox"

    def to_json(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, d):
        """Raises ValueError for a recipe that cannot be used; fields it does not know are ignored."""
        if not isinstance(d, dict):
            raise ValueError("recipe is not an object")
        for k in ("symbol", "accent"):
            if not isinstance(d.get(k), str) or not d[k]:
                raise ValueError(f"recipe has no valid {k!r}")
        scale = d.get("scale", 1.0)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not scale > 0:
            raise ValueError(f"recipe has an invalid scale {scale!r}")
        align = d.get("align", "bbox")
        if not isinstance(align, str):
            raise ValueError(f"recipe has an invalid align {align!r}")
        return cls(d["symbol"], d["accent"], float(scale), align)


@dataclasses.dataclass(frozen=True)
class Entry:
    folder: str          # absolute path
    recipe: Recipe


def _folder_of(raw):
    """Absolute folder of a raw manifest entry, or None if it has no usable path."""
    if isinstance(raw, dict) and isinstance(raw.get("path"), str) and raw["path"]:
        return folder_from_key(raw["path"])
    return None


class Manifest:
    """The manifest in memory. Entries are kept as the raw dicts read from the file, so fields this
    version does not know, and entries it cannot use, are written back unchanged."""

    def __init__(self, path, version=SCHEMA_VERSION, folders=(), extra=None):
        self.path, self.version = path, version
        self._raw, self.extra = list(folders), dict(extra or {})
        self.changed = False

    @property
    def warnings(self):
        """One message per entry that cannot be used (it is skipped, but kept in the file)."""
        out = []
        for i, raw in enumerate(self._raw):
            if _folder_of(raw) is None:
                out.append(f"{self.path}: entry {i + 1} has no valid path, skipped")
                continue
            try:
                Recipe.from_json(raw.get("recipe"))
            except ValueError as e:
                out.append(f"{self.path}: entry for {raw['path']!r} skipped: {e}")
        return out

    def entries(self):
        """Usable entries, one per folder (the last one wins if the file lists a folder twice)."""
        found = {}
        for raw in self._raw:
            folder = _folder_of(raw)
            if folder is None:
                continue
            try:
                found[folder] = Entry(folder, Recipe.from_json(raw.get("recipe")))
            except ValueError:
                continue
        return sorted(found.values(), key=lambda e: e.folder)

    def lookup(self, folder):
        folder = folder_path(folder)
        return next((e for e in self.entries() if e.folder == folder), None)

    def record(self, folder, recipe):
        """Add or replace the recipe of a folder; other fields of an existing entry are kept."""
        folder = folder_path(folder)
        same = [r for r in self._raw if _folder_of(r) == folder]
        raw = same[-1] if same else {}
        self._raw = [r for r in self._raw if _folder_of(r) != folder]
        self._raw.append({**raw, "path": folder_key(folder), "recipe": recipe.to_json()})
        self.changed = True

    def remove(self, folder):
        """Drop every entry of a folder, usable or not. True if there was one."""
        folder = folder_path(folder)
        n = len(self._raw)
        self._raw = [r for r in self._raw if _folder_of(r) != folder]
        self.changed |= len(self._raw) != n
        return len(self._raw) != n

    def remove_many(self, folders):
        """Drop every entry of each of these folders in one pass. Returns the folders that had one."""
        wanted = {folder_path(f) for f in folders}
        found = {_folder_of(r) for r in self._raw} & wanted
        self._raw = [r for r in self._raw if _folder_of(r) not in found]
        self.changed |= bool(found)
        return sorted(found)

    def check_writable(self):
        if self.version > SCHEMA_VERSION:
            raise ManifestError(f"{self.path} was written by a newer folder-symbols (schema "
                                f"{self.version}, this one knows {SCHEMA_VERSION}); update folder-symbols "
                                "to change it")

    def save(self):
        """Write atomically: a temporary file in the same directory, fsync, then rename over the old one."""
        self.check_writable()
        order = lambda r: (0, r["path"]) if _folder_of(r) else (1, "")   # sorted; unusable ones last
        data = {"schema_version": SCHEMA_VERSION, "folders": sorted(self._raw, key=order), **self.extra}
        d = os.path.dirname(self.path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        self.changed = False


def _damaged(path, why):
    return ManifestError(f"{path} is damaged ({why}); fix it or move it away. Nothing was changed")


def _migrate(data, version, path):
    """Bring data from an older schema up to SCHEMA_VERSION, one version at a time."""
    while version < SCHEMA_VERSION:
        if version not in MIGRATIONS:
            raise ManifestError(f"{path}: no migration from schema {version}")
        data = MIGRATIONS[version](data)
        version += 1
    return data


def load(path=None):
    """Read the manifest. A missing file is an empty manifest; a damaged one raises ManifestError
    and is left alone. A newer schema can be read but not written (see check_writable)."""
    path = path or manifest_path()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return Manifest(path)
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(f"cannot read {path}: {e}") from None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise _damaged(path, f"not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise _damaged(path, "not a JSON object")
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _damaged(path, "no valid schema_version")
    if version < SCHEMA_VERSION:
        data = _migrate(data, version, path)
    folders = data.get("folders", [])
    if not isinstance(folders, list):
        raise _damaged(path, "'folders' is not a list")
    extra = {k: v for k, v in data.items() if k not in ("schema_version", "folders")}
    return Manifest(path, version, folders, extra)


_editing = {}    # manifest path -> Manifest, while an editing() block holds its lock


@contextlib.contextmanager
def editing(path=None):
    """Load the manifest under an exclusive lock and save it when the block ends without an error
    (only if it changed). Nested use for the same file reuses the outer manifest and lock."""
    path = os.path.abspath(path or manifest_path())
    if path in _editing:
        yield _editing[path]
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(os.path.splitext(path)[0] + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        m = _editing[path] = load(path)
        try:
            yield m
            if m.changed:
                m.save()
        finally:
            del _editing[path]


# ---------------------------------------------------------------- one-call API
def record(folder, recipe, path=None):
    with editing(path) as m:
        m.check_writable()
        m.record(folder, recipe)


def remove(folder, path=None):
    with editing(path) as m:
        m.check_writable()
        return m.remove(folder)


def remove_many(folders, path=None):
    """Forget several folders in one locked read-modify-write (one save)."""
    with editing(path) as m:
        m.check_writable()
        return m.remove_many(folders)


def entries(path=None):
    return load(path).entries()


def lookup(folder, path=None):
    return load(path).lookup(folder)


def icon_status(folder, get_icon, icons=None):
    """'missing' (no such folder), 'no icon', 'ok' (the custom icon is a file in our icons
    directory) or 'other icon'. get_icon(folder) returns the metadata::custom-icon value or None."""
    if not os.path.exists(folder):
        return "missing"
    uri = get_icon(folder)
    if not uri:
        return "no icon"
    icons = os.path.abspath(icons or icons_dir())
    target = urllib.parse.unquote(uri[len("file://"):]) if uri.startswith("file://") else ""
    return "ok" if target and os.path.commonpath([os.path.abspath(target), icons]) == icons else "other icon"


def statuses(get_icon, path=None, icons=None):
    """[(Entry, status)] for every usable entry; see icon_status."""
    return [(e, icon_status(e.folder, get_icon, icons)) for e in entries(path)]


def folders_with_icon(get_icon, path=None, icons=None):
    """Entries whose folder exists and still shows the icon from our store."""
    return [e for e, s in statuses(get_icon, path, icons) if s == "ok"]


def is_external(folder):
    """True for a folder outside $HOME (stored with an absolute path; its drive may not be mounted)."""
    return os.path.isabs(folder_key(folder))


def folder_state(folder):
    """("present" | "missing" | "unknown", OSError or None). Only a sure answer is "missing": the path
    does not exist, or is something other than a directory. A symlink is followed; a dangling one, or
    any other error (e.g. no permission), is "unknown", as its target may be on an unmounted drive.
    The same goes for a missing path below a dangling symlinked parent (~/Drive/X, ~/Drive -> /mnt/drive)."""
    try:
        st = os.lstat(folder)
    except (FileNotFoundError, NotADirectoryError):
        parent = os.path.dirname(folder_path(folder))
        while True:
            if os.path.islink(parent) and not os.path.exists(parent):
                return "unknown", OSError(errno.ENOENT, "a parent directory is a symlink to a missing "
                                                        "target", parent)
            if parent == os.path.dirname(parent):
                return "missing", None
            parent = os.path.dirname(parent)
    except OSError as e:
        return "unknown", e
    if stat.S_ISLNK(st.st_mode):
        try:
            st = os.stat(folder)
        except OSError as e:
            return "unknown", e
    return ("present" if stat.S_ISDIR(st.st_mode) else "missing"), None


def stale_entries(manifest, include_external=False):
    """(stale, unknown, skipped) for the usable entries of a manifest: stale entries are of folders that
    surely do not exist, unknown is [(Entry, OSError)] for folders that cannot be checked, skipped is the
    number of entries outside $HOME left unchecked (unless include_external). $HOME itself is never stale."""
    stale, unknown, skipped, home = [], [], 0, _home()
    for e in manifest.entries():
        if e.folder == home:
            continue
        if not include_external and is_external(e.folder):
            skipped += 1
            continue
        state, err = folder_state(e.folder)
        if state == "missing":
            stale.append(e)
        elif state == "unknown":
            unknown.append((e, err))
    return stale, unknown, skipped
