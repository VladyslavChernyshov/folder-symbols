"""Scenarios B1-B5: the window's initial state from the manifest (initial.py, gui/window.py update_selection).

Each scenario writes its own manifest in its own HOME. The system accent is whatever the gsettings stub
reports (ctx.icon_theme; 'Yaru', that is orange, by default). The expected stderr lines are literal templates
of the texts in initial.py and store.py, filled in by the parent (stderr_lines). They are allowed only in
the scenario that prints them, which must print each of them exactly once."""
import functools
import os

import registry
import ui
from scenarios_a import APPLY_NEEDS_SYMBOL, RESET_NOT_RECORDED, RESET_ONE, check_buttons

scenario = functools.partial(registry.scenario, in_session_run=False)
MISSING = "gui-check-missing-symbol"


def manifest_of(home):
    return os.path.join(home, ".local", "share", "folder-symbols", "manifest.json")


def late_symbol(ctx):
    """A symbol near the end of the sorted gallery, so selecting it needs a scroll with Yaru."""
    return ctx.symbol("weather-clear", "user-trash", "star")


# ------------------------------------------------------------- B1
def prepare_b1(ctx):
    music = ctx.folder("Music")
    ctx.sym = late_symbol(ctx)
    ctx.record(music, ctx.sym, "purple")
    return [music]


@scenario("B1", "a recorded symbol and a pinned accent: selected, scrolled to, switch off", prepare=prepare_b1,
          steps=("window shown", "symbol selected", "scrolled into view", "accent pinned", "preview"))
def b1(d):
    sym = d.ctx.sym
    d.step("window shown")
    d.wait_window()
    d.step("symbol selected")
    d.check("gallery selection", d.selected_name(), sym)
    d.step("scrolled into view")
    ui.wait_quietly(d, lambda: ui.card_in_view(d, sym), f"the card of {sym} inside the viewport")
    d.check("card of the selected symbol inside the viewport", ui.card_in_view(d, sym), True)
    value, upper = ui.vadjustment(d)
    d.info(f"B1: vadjustment {value:.0f} of {upper:.0f} ({d.ctx.symbols_source})")
    if d.ctx.symbols_source == "yaru":
        d.check("scrolled (vadjustment > 0: a scroll is required with Yaru)", value > 0, True)
    d.step("accent pinned")
    ui.check_accents(d, count=12, order=ui.PICKER_ORDER, selected=["purple"], system=["orange"], switch=False,
                     row_sensitive=True, row_tooltip=ui.FOLLOW_TOOLTIP, marker=True)
    d.step("preview")
    d.check("preview file", d.preview_file(), f"Yaru-purple-{sym}.svg")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("purple", None))


# ------------------------------------------------------------- B2
def prepare_b2(ctx):
    music = ctx.folder("Music")
    ctx.sym = ctx.symbol("folder-music", "audio-x-generic", "star")
    ctx.record(music, ctx.sym, "system")
    ctx.icon_theme("Yaru-sage")
    return [music]


@scenario("B2", "a recorded symbol that follows the system accent: switch on, the system swatch",
          prepare=prepare_b2, steps=("window shown", "symbol selected", "following", "preview"))
def b2(d):
    sym = d.ctx.sym
    d.step("window shown")
    d.wait_window()
    d.step("symbol selected")
    d.check("gallery selection", d.selected_name(), sym)
    d.step("following")
    ui.check_accents(d, count=12, selected=["sage"], system=["sage"], switch=True, row_sensitive=True, marker=True)
    d.step("preview")
    d.check("preview file", d.preview_file(), f"Yaru-sage-{sym}.svg")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "sage"))


# ------------------------------------------------------------- B3
def prepare_b3(ctx):
    music, videos, ctx.pictures = ctx.folder("Music"), ctx.folder("Videos"), ctx.folder("Pictures")
    ctx.music = music
    s1 = ctx.symbol("folder-music", "audio-x-generic", "star")
    s2 = ctx.symbol("folder-videos", "video-x-generic", "circle")
    ctx.record(music, s1, "red")
    ctx.record(videos, s2, "blue")
    ctx.icon_theme("Yaru-sage")
    return [music, videos]


def check_plain_following(d):
    d.check("gallery selection", d.selected_name(), None)
    d.check("preview file", d.preview_file(), "Yaru-sage-plain.svg")
    ui.check_accents(d, selected=["sage"], system=["sage"], switch=True)
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "sage"))


@scenario("B3", "folders with different symbols, or one without a record: nothing selected, a plain preview",
          prepare=prepare_b3, steps=("window shown", "different symbols", "second launch", "one without a record"))
def b3(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.step("different symbols")
    d.check("folder title", d.find_one("folder-title").get_title(), "2 folders")
    check_plain_following(d)
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), ("Reset 2", True, "Give the 2 selected folders their normal icon again"))
    d.step("second launch")
    opens = len(d.opens)
    launch = d.launch([ctx.music, ctx.pictures], "Music (recorded) and Pictures (no record)")
    d.check("second launch exit status", launch.status, 0)
    d.check("second launch stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) > opens, "the Open of the second launch")
    d.step("one without a record")
    d.check("Reset label (the window took the new selection)", d.find_one("reset-button").get_label(), "Reset 1 of 2")
    check_plain_following(d)


# ------------------------------------------------------------- B4, B4b, B5
def check_as_without_record(d, reset):
    d.check("gallery selection", d.selected_name(), None)
    d.check("preview file", d.preview_file(), "Yaru-plain.svg")
    ui.check_accents(d, selected=["orange"], system=["orange"], switch=True)
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), reset)


def prepare_b4(ctx):
    music = ctx.folder("Music")
    ctx.record(music, MISSING, "red")
    return [music]


@scenario("B4", "the recorded symbol is not in the gallery: as without a record, one stderr line", prepare=prepare_b4,
          steps=("window shown", "as without a record"),
          stderr_lines=lambda home, symbols_dir: (
              f"folder-symbols: recorded symbol not found in {symbols_dir}, showing none: {MISSING} (~/Music)",))
def b4(d):
    d.step("window shown")
    d.wait_window()
    d.step("as without a record")
    # Pinned current behaviour: the entry exists, so Reset can still remove it.
    check_as_without_record(d, ("Reset", True, RESET_ONE))


def prepare_b4b(ctx):
    music = ctx.folder("Music")
    ctx.manifest_text("[]\n")
    return [music]


@scenario("B4b", "a damaged manifest: as without a record, one stderr line", prepare=prepare_b4b,
          steps=("window shown", "as without a record"),
          stderr_lines=lambda home, symbols_dir: (
              f"folder-symbols: {manifest_of(home)} is damaged (not a JSON object); fix it or move it away. "
              "Nothing was changed; recorded icons are ignored",))
def b4b(d):
    d.step("window shown")
    d.wait_window()
    d.step("as without a record")
    check_as_without_record(d, ("Reset", False, RESET_NOT_RECORDED))


def prepare_b5(ctx):
    music = ctx.folder("Music")
    ctx.record(music, ctx.symbol("folder-music", "audio-x-generic", "star"), "red")
    ctx.b5_manifest = ctx.manifest_path()
    ctx.make_unreadable(ctx.b5_manifest)
    return [music]


def b5_root(_symbols_dir, _source):
    if os.geteuid() == 0:
        return "running as root: chmod 0 does not block reading the manifest"
    return None


@scenario("B5", "an unreadable manifest: as without a record, one stderr line", prepare=prepare_b5,
          steps=("window shown", "as without a record"), not_verified_if=b5_root,
          stderr_lines=lambda home, symbols_dir: (
              f"folder-symbols: cannot read {manifest_of(home)}: [Errno 13] Permission denied: "
              f"'{manifest_of(home)}'; recorded icons are ignored",))
def b5(d):
    try:
        d.step("window shown")
        d.wait_window()
        d.step("as without a record")
        check_as_without_record(d, ("Reset", False, RESET_NOT_RECORDED))
    finally:
        os.chmod(d.ctx.b5_manifest, 0o600)
        d.info(f"B5: manifest mode restored to 0600 ({oct(os.stat(d.ctx.b5_manifest).st_mode & 0o777)})")

