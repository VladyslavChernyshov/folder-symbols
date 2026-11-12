import importlib.util, os, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

ICONS_ROOT = os.environ.get("YARU_ICONS_ROOT", "/usr/share/icons")
SYMBOLS_DIR = os.environ.get("YARU_SYMBOLS_DIR", os.path.join(ICONS_ROOT, "Yaru", "scalable"))


def _load():
    spec = importlib.util.spec_from_file_location("yfi", os.path.join(ROOT, "yaru-folder-icon.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="session")
def g():
    return _load()


def installed_themes():
    if not os.path.isdir(ICONS_ROOT):
        return []
    return sorted(d for d in os.listdir(ICONS_ROOT) if d.startswith("Yaru")
                  and os.path.exists(f"{ICONS_ROOT}/{d}/256x256@2x/places/folder-publicshare.png"))


THEMES = installed_themes()
ALLOW_NO_YARU = os.environ.get("ALLOW_NO_YARU") == "1"


def pytest_sessionstart(session):
    """Most tests need the real Yaru themes and symbols. Without them they would be skipped and the run
    would still look green, so stop with an error unless skipping was asked for (ALLOW_NO_YARU=1)."""
    if ALLOW_NO_YARU or (THEMES and os.path.isdir(SYMBOLS_DIR)):
        return
    pytest.exit(
        f"Yaru themes or symbols not found (themes in {ICONS_ROOT}: {len(THEMES)}, symbols dir: {SYMBOLS_DIR}).\n"
        "Install them (sudo apt install yaru-theme-icon), point YARU_ICONS_ROOT / YARU_SYMBOLS_DIR at them,\n"
        "or set ALLOW_NO_YARU=1 to run only the tests that do not need Yaru (the rest are skipped).",
        returncode=2)


def pytest_generate_tests(metafunc):
    if "theme_name" in metafunc.fixturenames:
        metafunc.parametrize("theme_name", THEMES or [pytest.param(None, marks=pytest.mark.skip(
            reason=f"no Yaru themes in {ICONS_ROOT} (set YARU_ICONS_ROOT)"))])


@pytest.fixture(scope="session")
def themes(g):
    cache = {}
    def get(name, sizes=(256, 512)):
        key = (name, sizes)
        if key not in cache:
            cache[key] = g.Theme(f"{ICONS_ROOT}/{name}", sizes)
        return cache[key]
    return get


@pytest.fixture
def svg(tmp_path):
    """Write a synthetic SVG and return its path."""
    def make(name, body, root_attrs):
        p = tmp_path / f"{name}-symbolic.svg"
        p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" {root_attrs}>{body}</svg>')
        return str(p)
    return make
