import json, os, re, subprocess, sys
import numpy as np
import pytest
from PIL import Image

from conftest import ICONS_ROOT, SYMBOLS_DIR, ROOT, THEMES
from check_centering import measure

SQUARE = '<rect x="3" y="3" width="10" height="10" fill="#222"/>'


def ink_size(g, mask, size):
    ys, xs = np.nonzero(mask > 0.02)
    return (xs.max() - xs.min() + 1) / (size * g.SS), (ys.max() - ys.min() + 1) / (size * g.SS)


# ------------------------------------------------------------- pure functions
def test_svg_units(g, svg):
    assert g.svg_units(svg("a", SQUARE, 'viewBox="0 0 16 16"')) == (16, 16)
    assert g.svg_units(svg("b", SQUARE, 'viewBox="0 0 16.18 16"')) == (16.18, 16)
    # nominal width/height wins over an odd millimetre viewBox
    assert g.svg_units(svg("c", SQUARE, 'width="16" height="16" viewBox="0 0 4.2333 4.2333"')) == (16, 16)
    # far-from-16 viewBox is normalised so the long side is 16
    assert g.svg_units(svg("d", SQUARE, 'viewBox="0 0 64 64"')) == (16, 16)
    assert g.svg_units(svg("e", SQUARE, 'viewBox="0 0 8 8"')) == (16, 16)


def test_strip_opacity(g):
    s = '<path opacity="0.35" fill-opacity=".5" style="fill:#000;opacity:0.3;stroke-opacity:.4;stop-opacity:1"/>'
    out = g.strip_opacity(s)
    assert "opacity=" not in out.replace("stop-opacity", "")
    assert "opacity:0.3" not in out and "fill-opacity" not in out and "stroke-opacity" not in out
    assert "stop-opacity:1" in out            # gradients are left alone
    assert "fill:#000" in out


def test_overrides_shipped_file_is_valid(g):
    ov = g.load_overrides(os.path.join(ROOT, "overrides.json"))
    assert ov, "overrides.json should not be empty"
    for name, v in ov.items():
        assert not name.startswith("_")
        assert set(v) <= {"scale", "dx", "dy", "align"}, name
        assert 0.2 < v.get("scale", 1.0) < 3.0, name
        assert abs(v.get("dx", 0)) < 0.2 and abs(v.get("dy", 0)) < 0.2, name


@pytest.mark.skipif(not os.path.isdir(SYMBOLS_DIR), reason="no Yaru symbols")
@pytest.mark.skipif(not os.path.isdir(SYMBOLS_DIR), reason="Yaru symbols not installed")
def test_symbol_names_are_unique_except_known_clashes():
    """The manifest stores symbol names without their category, so a name must mean one picture.
    Names that occur twice for the same file (symlinks) are fine; 'resources' is the one known clash
    (generic-symbols/ vs status/, the latter is power-profile-balanced), and find_symbols always picks
    generic-symbols. If this fails, Yaru added a clash: the recipe may need the category after all."""
    pictures = {}
    for dp, _, fs in os.walk(SYMBOLS_DIR):
        for f in fs:
            if f.endswith("-symbolic.svg"):
                pictures.setdefault(f[:-len("-symbolic.svg")], set()).add(os.path.realpath(os.path.join(dp, f)))
    assert {n for n, ps in pictures.items() if len(ps) > 1} <= {"resources"}


@pytest.mark.skipif(not THEMES or not os.path.isdir(SYMBOLS_DIR), reason="no Yaru theme/symbols")
def test_overrides_refer_to_existing_symbols(g):
    names = g.find_symbols(SYMBOLS_DIR, None)
    for name in g.load_overrides(os.path.join(ROOT, "overrides.json")):
        assert name in names, f"overrides.json: unknown symbol {name!r}"


# ------------------------------------------------------------- symbol rendering
def test_viewbox_variants_have_comparable_size(g, svg):
    """The odd-canvas cases that used to come out tiny/huge now land near the normal size."""
    sizes = []
    for i, attrs in enumerate(('viewBox="0 0 16 16"', 'viewBox="0 0 16.18 16"',
                               'width="16" height="16" viewBox="0 0 4.2333 4.2333"')):
        body = SQUARE if i < 2 else '<rect x="0.8" y="0.8" width="2.6" height="2.6" fill="#222"/>'
        w, _ = ink_size(g, g.render_symbol(svg(f"v{i}", body, attrs), 512), 512)
        sizes.append(w)
    assert max(sizes) / min(sizes) < 1.2, sizes


def test_oversized_symbol_is_shrunk_into_box(g, svg):
    big = svg("big", '<rect x="0" y="0" width="16" height="16" fill="#222"/>', 'viewBox="0 0 16 16"')
    w, h = ink_size(g, g.render_symbol(big, 512, scale=3.0), 512)
    assert w <= g.MAX_INK_W + 0.003 and h <= g.MAX_INK_H + 0.003, (w, h)


def test_wide_symbol_may_use_more_width(g, svg):
    wide = svg("wide", '<rect x="0" y="6" width="16" height="4" fill="#222"/>', 'viewBox="0 0 16 16"')
    w, h = ink_size(g, g.render_symbol(wide, 512, scale=1.4), 512)
    assert w > g.MAX_INK_H + 0.01 and w <= g.MAX_INK_W + 0.003


def test_opacity_default_is_solid(g, svg):
    p = svg("ghost", '<rect x="3" y="3" width="10" height="10" fill="#222" opacity="0.3"/>', 'viewBox="0 0 16 16"')
    assert g.render_symbol(p, 256).max() > 0.99
    assert g.render_symbol(p, 256, solid=False).max() < 0.5


# ------------------------------------------------------------- composing on every installed theme
def test_calibration_is_plausible(g, themes, theme_name):
    t = themes(theme_name)
    body = np.median(t.base[512][t.base[512][:, :, 3] == 255][:, :3], 0)
    assert t.D1.sum() < body.sum() and t.D2.sum() < t.D1.sum(), (t.D1, t.D2, body)


@pytest.mark.parametrize("size", [256, 512])
def test_compose_keeps_folder_shape_and_changes_only_the_symbol(g, themes, theme_name, svg, size):
    t = themes(theme_name)
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    img = np.array(g.compose(t, g.render_symbol(p, size), size))
    base = t.base[size]
    assert img.shape == base.shape == (size, size, 4)
    assert (img[:, :, 3] == base[:, :, 3]).all(), "alpha channel (folder silhouette) must not change"
    changed = (np.abs(img.astype(int) - base.astype(int)).sum(2) > 0)
    ys, xs = np.nonzero(changed)
    assert changed.sum() > 0.01 * size * size, "symbol not drawn"
    assert ys.min() > 0.25 * size and ys.max() < 0.85 * size, "symbol must stay on the front panel"
    assert xs.min() > 0.15 * size and xs.max() < 0.85 * size


@pytest.mark.parametrize("align", ["bbox", "mass"])
def test_symbol_is_centred_on_front_panel(g, themes, theme_name, svg, align):
    t = themes(theme_name)
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    img = np.array(g.compose(t, g.render_symbol(p, 512), 512, align))
    dx, dy, w, h = measure(img)
    assert abs(dx) <= 0.01 * 512 and abs(dy) <= 0.01 * 512, (dx, dy)


def test_deterministic(g, themes, theme_name, svg):
    t = themes(theme_name)
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    a = g.compose(t, g.render_symbol(p, 256), 256)
    b = g.compose(t, g.render_symbol(p, 256), 256)
    assert a.tobytes() == b.tobytes()


# ------------------------------------------------------------- real Yaru symbols
@pytest.mark.skipif(not THEMES or not os.path.isdir(SYMBOLS_DIR), reason="no Yaru theme/symbols")
def test_real_symbols_fit_and_are_centred(g, themes):
    syms = g.find_symbols(SYMBOLS_DIR, None)
    names = sorted(syms)[::max(1, len(syms) // 60)][:60]     # an even sample of up to 60
    names += [n for n in ("share", "adaptive", "device-support-adaptive") if n in syms and n not in names]
    ov = g.load_overrides(os.path.join(ROOT, "overrides.json"))
    t = themes("Yaru-dark" if "Yaru-dark" in THEMES else THEMES[0], (256,))
    for n in names:
        sym = g.render_symbol(syms[n], 256, ov.get(n, {}).get("scale", 1.0))
        w, h = ink_size(g, sym, 256)
        assert w <= g.MAX_INK_W + 0.004 and h <= g.MAX_INK_H + 0.004, (n, w, h)
        r = measure(np.array(g.compose(t, sym, 256)))
        assert r is not None, n
        assert abs(r[0]) <= 0.01 * 256 and abs(r[1]) <= 0.01 * 256, (n, r)


# ------------------------------------------------------------- SVG output
def _premul(a):
    return a[:, :, :3] * a[:, :, 3:4] / 255


def test_svg_colors_match_theme(g, theme_name):
    A, O = g.fit_folder_colors(f"{ICONS_ROOT}/{theme_name}")
    if theme_name == "Yaru-mate":
        assert A is None                       # fixed-colour template
    else:
        assert A.startswith("#") and O.startswith("#") and A != O


def test_svg_matches_raster(g, themes, theme_name, svg):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    text = g.make_svg(f"{ICONS_ROOT}/{theme_name}", p)
    assert g.DUMMY_ACCENT not in text and g.DUMMY_DARK not in text and "<!--SYMBOL" not in text
    vec = g.rasterise(text, 512)
    ras = np.array(g.compose(themes(theme_name), g.render_symbol(p, 512), 512)).astype(float)
    d = np.abs(_premul(vec) - _premul(ras)).max(2)
    assert d.max() <= 40 and (d > 25).sum() < 400, (d.max(), (d > 25).sum())


def test_svg_clips_content_outside_viewbox(g, svg, theme_name):
    """Yaru's library-music has a stray glyph outside its viewBox; it must not show up."""
    body = SQUARE + '<circle cx="-6" cy="3" r="3"/>'
    p = svg("stray", body, 'viewBox="0 0 16 16"')
    q = svg("clean", SQUARE, 'viewBox="0 0 16 16"')
    d = f"{ICONS_ROOT}/{theme_name}"
    a = g.rasterise(g.make_svg(d, p), 256)
    b = g.rasterise(g.make_svg(d, q), 256)
    assert np.abs(a - b).max() <= 1


def test_svg_override_scale_applied(g, svg, theme_name):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    d = f"{ICONS_ROOT}/{theme_name}"
    a = g.rasterise(g.make_svg(d, p, scale=0.5), 256)
    b = g.rasterise(g.make_svg(d, p, scale=1.0), 256)
    assert (a != b).any()


@pytest.mark.skipif(not THEMES, reason="no Yaru themes installed")
def test_svg_cli_extension(tmp_path, svg):
    import subprocess
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    out = tmp_path / "o.svg"
    th = f"{ICONS_ROOT}/{THEMES[0]}"
    subprocess.run([sys.executable, os.path.join(ROOT, "folder-symbols"), th, p, str(out)], check=True)
    assert out.read_text().startswith("<?xml") or "<svg" in out.read_text()[:400]


# ------------------------------------------------------------- command line
@pytest.mark.skipif(not THEMES or not os.path.isdir(SYMBOLS_DIR), reason="no Yaru theme/symbols")
def test_batch_cli(tmp_path):
    out = tmp_path / "dist"
    two = THEMES[:2]
    subprocess.run([sys.executable, os.path.join(ROOT, "folder-symbols"), "batch",
                    "--icons-root", ICONS_ROOT, "--symbols-dir", SYMBOLS_DIR, "--out", str(out),
                    "--themes", ",".join(two), "--sizes", "256", "--only", "^(share|adaptive)$",
                    "--jobs", "2"], check=True)
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.png"))
    assert len(files) >= len(two), files
    for f in files:
        assert Image.open(out / f).size == (256, 256)


# ------------------------------------------------------------- every Yaru size
def test_size_helpers(g):
    assert [g.size_px(d) for d in g.SIZE_DIRS] == [16, 32, 24, 48, 32, 64, 48, 96, 256, 512]
    assert g.size_dir(512) == "256x256@2x" and g.size_dir("256") == "256x256"
    with pytest.raises(ValueError):
        g.size_dir("128x128")


def test_all_sizes(g, themes, theme_name, svg):
    from conftest import ICONS_ROOT
    t = g.Theme(f"{ICONS_ROOT}/{theme_name}", tuple(g.SIZE_DIRS))
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    for d in g.SIZE_DIRS:
        px = g.size_px(d)
        base = t.base[d]
        img = np.array(g.compose(t, g.render_symbol(p, d), d))
        assert img.shape == base.shape, d
        assert (img[:, :, 3] == base[:, :, 3]).all(), d
        changed = np.abs(img.astype(int) - base.astype(int)).sum(2) > 0
        if d in g.NO_SYMBOL:
            assert not changed.any(), f"{d}: Yaru has no symbol at this size"
            continue
        assert changed.sum() > 0.01 * px * px, f"{d}: symbol not drawn"
        ys, xs = np.nonzero(changed)
        x0, y0, x1, y1 = g.panel_bbox(base)
        # centred on the front panel (within 1.5 px, or 1 % for big sizes)
        tol = max(1.5, 0.01 * px)
        assert abs((xs.min() + xs.max() + 1) / 2 - (x0 + x1) / 2) <= tol, d
        assert abs((ys.min() + ys.max() + 1) / 2 - (y0 + y1) / 2) <= tol + 1, d
        if px < g.EMBOSS_MIN_PX:      # flat: the core of the symbol is exactly one colour (D1)
            diff = np.abs(img[:, :, :3].astype(float) - t.D1).sum(2)
            assert (diff < 6).sum() > 0.2 * changed.sum(), f"{d}: flat colour missing"


# ------------------------------------------------------------- help
SCRIPT = os.path.join(ROOT, "folder-symbols")


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def test_no_arguments_prints_full_help():
    r = _run()
    assert r.returncode == 0
    for word in ("apply", "reset", "batch", "--sizes", "--align", "--keep-opacity", "--skip-existing",
                 "--dry-run", "--overrides", "--only", "--jobs", "--theme", "--store", "list", "--all",
                 "--accent", "--format"):
        assert word in r.stdout, word
    assert r.stdout == _run("--help").stdout


def test_every_command_has_help_for_every_option():
    for cmd in ("apply", "reset", "list", "batch"):
        r = _run(cmd, "--help")
        assert r.returncode == 0 and "usage:" in r.stdout
    # every option of every command is documented (argparse prints a help text next to it)
    from folder_symbols import cli as m
    for mk in (m.parser_compose, m.parser_apply, m.parser_reset, m.parser_list, m.parser_batch):
        for act in mk()._actions:
            assert act.help, (mk.__name__, act.dest)


@pytest.mark.skipif(not THEMES, reason="no Yaru themes installed")
def test_apply_dry_run_svg_and_png(tmp_path, svg):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    th = THEMES[0]
    for fmt, ext in ((None, ".svg"), ("svg", ".svg"), ("png", ".png")):
        cmd = ["apply", str(tmp_path), p, "--theme", th, "--icons-root", ICONS_ROOT,
               "--store", str(tmp_path / "store"), "--dry-run"] + (["--format", fmt] if fmt else [])
        r = _run(*cmd)
        assert r.returncode == 0, r.stderr
        out = tmp_path / "store" / f"{th}-sq{ext}"
        assert out.exists() and f"file://{out}" in r.stdout
    assert "<svg" in (tmp_path / "store" / f"{th}-sq.svg").read_text()[:600]


# ------------------------------------------------------------- built-in theme data (assets/themes.json)
def test_themes_json_is_complete_and_up_to_date(g, theme_name):
    """If this fails after a Yaru update: python3 tools/build_themes_json.py --icons-root <icons dir>"""
    table = g.builtin_themes()
    assert theme_name in table, f"{theme_name} missing from assets/themes.json (rebuild it)"
    mine, now = table[theme_name], g.compute_svg_data(f"{ICONS_ROOT}/{theme_name}")
    near = lambda x, y, tol: all(abs(int(x[i:i + 2], 16) - int(y[i:i + 2], 16)) <= tol for i in (1, 3, 5))
    ok = len(mine["colors"]) == len(now["colors"]) \
        and all(near(x, y, 3) for x, y in zip(mine["colors"] + [mine["d1"], mine["d2"]],
                                              now["colors"] + [now["d1"], now["d2"]])) \
        and all(abs(x - y) <= 1 for x, y in zip(mine["center"], now["center"]))
    assert ok, f"assets/themes.json is out of date for {theme_name} (rebuild it): {mine} vs {now}"


def test_builtin_data_gives_same_svg_as_theme_directory(g, svg, theme_name):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    assert g.make_svg(theme_name, p) == g.make_svg(f"{ICONS_ROOT}/{theme_name}", p)


def test_cli_svg_by_name_without_any_theme_installed(tmp_path, svg):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    out = tmp_path / "o.svg"
    r = _run("Yaru-dark", p, str(out))
    assert r.returncode == 0, r.stderr
    assert "<svg" in out.read_text()[:600]
    r = _run("No-such-theme", p, str(out))
    assert r.returncode != 0 and "built-in" in r.stderr


def test_batch_svg_uses_builtin_data_without_icons_root(tmp_path, svg):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    r = _run("batch", "--symbols-dir", str(tmp_path), "--out", str(tmp_path / "o"), "--sizes", "svg",
             "--themes", "Yaru-dark,Yaru-mate", "--jobs", "1")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "o" / "Yaru-dark" / "scalable" / "sq.svg").exists()
    assert (tmp_path / "o" / "Yaru-mate" / "scalable" / "sq.svg").exists()


def test_apply_svg_by_name_dry_run(tmp_path, svg):
    p = svg("sq", SQUARE, 'viewBox="0 0 16 16"')
    r = _run("apply", str(tmp_path), p, "--theme", "Yaru-purple-dark", "--store", str(tmp_path / "s"),
             "--dry-run")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "s" / "Yaru-purple-dark-sq.svg").exists()


# ------------------------------------------------------------- fake README screenshot
def test_make_screenshot(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import make_screenshot as ms
    syms = tmp_path / "syms"
    syms.mkdir()
    for n in ms.NAMES:
        (syms / f"{n}-symbolic.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{SQUARE}</svg>')
    out = tmp_path / "shot.png"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshot.py"),
                        "--symbols-dir", str(syms), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    im = np.array(Image.open(out).convert("RGBA")).astype(int)
    assert im.shape[:2] == (730, 870)                                      # window + shadow + 40 px margin
    assert im[600, 6, 0] > im[100, 860, 0] and im[100, 860, 2] > 60        # orange bottom left, aubergine top right
    assert im[300, 100, :3].min() > 240 and im[300, 770, :3].max() < 60    # light left, dark right
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshot.py"), "--symbols-dir",
                        str(syms), "--out", str(out), "--background", "transparent"], capture_output=True, text=True)
    assert r.returncode == 0 and np.array(Image.open(out)).shape[:2] == (650, 790)
    # GitHub social preview: 8 x 3 folders on an exact 1280 x 640 canvas, window centred; wrong values are rejected
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshot.py"), "--symbols-dir",
                        str(syms), "--out", str(out), "--grid", "8x3", "--size", "1280x640"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    sp = np.array(Image.open(out).convert("RGBA")).astype(int)
    assert sp.shape[:2] == (640, 1280) and sp[:, :, 3].min() == 255
    assert sp[500, 200, :3].min() > 240 and sp[500, 1080, :3].max() < 60     # light left half, dark right half
    for bad in (["--size", "big"], ["--size", "1280x640", "--background", "transparent"], ["--grid", "7x3"]):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshot.py"), "--symbols-dir",
                            str(syms), "--out", str(out)] + bad, capture_output=True, text=True)
        assert r.returncode != 0
    # a missing symbol is reported by name
    (syms / "printer-symbolic.svg").unlink()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshot.py"),
                        "--symbols-dir", str(syms), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode != 0 and "printer" in r.stderr


def test_version_flag():
    import subprocess
    for flag in ("--version", "-V"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "folder-symbols"), flag],
                           capture_output=True, text=True, check=True)
        assert re.fullmatch(r"folder-symbols \d+\.\d+\.\d+\n", r.stdout), r.stdout
