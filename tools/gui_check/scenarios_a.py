"""Scenarios A1-A7: starting the window, the welcome page and second launches.

The expected texts are literals copied from the code (appinfo.py, selection.py, outcome.py), so a changed
text in the application shows up here as a difference. No GTK import at module level: the parent reads
only the metadata; the bodies get GTK through the driver (d.Gtk, d.GLib)."""
import os

import fixtures
from registry import Fail, scenario

APP_TITLE = "Folder Symbols"
WELCOME_TITLE = "Choose a folder"
WELCOME_TEXT = "In Files, right-click a folder and choose “Choose Icon…”."
MENU = [("Clean up…", "win.clean-up"), ("About", "app.about")]
APPLY_NEEDS_SYMBOL = "Choose a symbol first"
APPLY_ONE = "Set this symbol and accent on the selected folder.\nFiles may need a refresh (F5) to show the new icon."
RESET_NOT_RECORDED = "This folder has no icon from Folder Symbols"
RESET_ONE = "Give the folder its normal icon again"
RESET_ONE_OF_SEVERAL = "Give the one folder with an icon from Folder Symbols its normal icon again"
NO_FOLDER = "folder-symbols-gui: no existing folder among the given paths"
NO_CALLS = {"apply": 0, "reset": 0, "plan_cleanup": 0, "run_cleanup": 0}
# The plain folder's preview: PreviewSession.build_plain writes "{variant}-plain.svg"; the gsettings stub
# reports the icon theme 'Yaru' (orange) and the keyfile pins the light style, so the variant is "Yaru".
PLAIN_PREVIEW = "Yaru-plain.svg"
SEARCH = "view"
CATEGORY = "actions"


def no_folder_error(items):
    """The launcher's error for these "path: reason" items (at most 10 listed, then "... and N more")."""
    lines = [NO_FOLDER] + [f"  {item}" for item in items[:10]]
    if len(items) > 10:
        lines.append(f"  ... and {len(items) - 10} more")
    return "\n".join(lines) + "\n"


def expected_symbols(d):
    """The number of symbols the gallery must show, counted without the package's code: the generator's
    own list for the fixture, an independent count of the directory for Yaru."""
    if d.ctx.symbols_source == "fixture":
        return len(fixtures.fixture_names())
    return fixtures.count_symbols(d.ctx.symbols_dir)


def fixture_matches(query, category=None):
    return sum(1 for name, cat in fixtures.fixture_names().items()
               if query in name and (category is None or cat == category))


def menu_items(d, button):
    model = button.get_menu_model()
    s = d.GLib.VariantType.new("s")
    return [(model.get_item_attribute_value(i, "label", s).get_string(),
             model.get_item_attribute_value(i, "action", s).get_string()) for i in range(model.get_n_items())]


def check_buttons(d, apply, reset):
    """apply: (sensitive, tooltip); reset: (label, sensitive, tooltip)."""
    button = d.find_one("apply-button")
    d.check("Apply label", button.get_label(), "Apply")
    d.check("Apply sensitive", button.get_sensitive(), apply[0])
    d.check("Apply tooltip", button.get_tooltip_text(), apply[1])
    button = d.find_one("reset-button")
    d.check("Reset label", button.get_label(), reset[0])
    d.check("Reset sensitive", button.get_sensitive(), reset[1])
    d.check("Reset tooltip", button.get_tooltip_text(), reset[2])


def accent(d):
    return d.find_one("preview-panel").current_choice().accent


# ------------------------------------------------------------- A1
@scenario("A1", "start without paths: the welcome page",
          steps=("window shown", "welcome page", "lazy build", "main menu", "actions", "no backend calls"))
def a1(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("welcome page")
    d.check("page", win.page, "empty")
    d.check("window title", win.get_title(), APP_TITLE)
    status = d.find_one("welcome-status")
    d.check("welcome title", status.get_title(), WELCOME_TITLE)
    d.check("welcome description", status.get_description(), WELCOME_TEXT)
    d.step("lazy build")
    d.check("gallery-grid widgets (any)", len(d.find_all("gallery-grid")), 0)
    d.check("preview-panel widgets (any)", len(d.find_all("preview-panel")), 0)
    d.step("main menu")
    d.check("menu items", menu_items(d, d.find_one("main-menu-button")), MENU)
    d.step("actions")
    cleanup = win.lookup_action("clean-up")
    d.require(cleanup is not None, "win.clean-up does not exist")
    d.check("win.clean-up enabled", cleanup.get_enabled(), True)
    about = d.app.lookup_action("about")
    d.require(about is not None, "app.about does not exist")
    d.check("app.about enabled", about.get_enabled(), True)
    d.step("no backend calls")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


# ------------------------------------------------------------- A2, A2b
def prepare_a2(ctx):
    return [ctx.folder("Music")]


@scenario("A2", "start with one folder without a manifest entry", prepare=prepare_a2,
          steps=("window shown", "main page", "gallery", "buttons", "plain preview", "no backend calls"))
def a2(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("main page")
    d.check("page", win.page, "main")
    title = d.find_one("folder-title")
    d.check("folder title", title.get_title(), "Music")
    d.check("folder tooltip", title.get_tooltip_text(), "~/Music")
    d.step("gallery")
    model = d.grid_model()
    d.check("gallery symbols", model.get_n_items(), expected_symbols(d))
    d.check("gallery selection", d.selected_name(), None)
    d.step("buttons")
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), ("Reset", False, RESET_NOT_RECORDED))
    d.step("plain preview")
    # The file icon build_plain wrote, not the theme "folder" icon that gui/preview.py falls back to.
    d.check("preview file", d.preview_file(), PLAIN_PREVIEW)
    gicon = d.find_one("preview-image").get_gicon()
    path = gicon.get_file().get_path() if isinstance(gicon, d.Gio.FileIcon) else None
    run_dir = os.path.realpath(os.environ["GUI_CHECK_RUN_DIR"]) + os.sep
    d.check("preview file exists under the run directory",
            bool(path) and os.path.isfile(path) and os.path.realpath(path).startswith(run_dir), True)
    d.step("no backend calls")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


def prepare_a2b(ctx):
    music = ctx.folder("Music")
    ctx.symbol_a = ctx.symbol("folder-music", "audio-x-generic", "star")
    ctx.record(music, ctx.symbol_a, "red")
    return [music]


@scenario("A2b", "start with one folder that has a manifest entry", prepare=prepare_a2b,
          steps=("window shown", "recorded symbol selected", "buttons", "preview", "no backend calls"))
def a2b(d):
    d.step("window shown")
    d.wait_window()
    d.step("recorded symbol selected")
    d.check("gallery selection", d.selected_name(), d.ctx.symbol_a)
    d.step("buttons")
    check_buttons(d, (True, APPLY_ONE), ("Reset", True, RESET_ONE))
    d.step("preview")
    d.check("preview accent", accent(d), "red")
    d.check("preview file", d.preview_file(), f"Yaru-red-{d.ctx.symbol_a}.svg")
    d.step("no backend calls")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


# ------------------------------------------------------------- A3
def prepare_a3(ctx):
    music, pictures, videos = ctx.folder("Music"), ctx.folder("Pictures"), ctx.folder("Videos")
    notes = ctx.file("notes.txt")
    ctx.record(music, ctx.symbol("folder-music", "audio-x-generic", "star"), "red")
    ctx.a3_paths = [music, notes, pictures, videos]
    return ctx.a3_paths


@scenario("A3", "start with three folders and one file (one folder recorded)", prepare=prepare_a3,
          steps=("window shown", "header", "file ignored", "buttons", "no backend calls"))
def a3(d):
    d.step("window shown")
    d.wait_window()
    d.step("header")
    title = d.find_one("folder-title")
    d.check("folder title", title.get_title(), "3 folders")
    d.check("folder tooltip", title.get_tooltip_text(),
            "3 of 4 selected items are folders\n~/Music\n~/Pictures\n~/Videos")
    d.step("file ignored")
    d.check("paths of the Open", d.opens, [d.ctx.a3_paths])
    d.check("gallery selection", d.selected_name(), None)
    d.step("buttons")
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), ("Reset 1 of 3", True, RESET_ONE_OF_SEVERAL))
    d.step("no backend calls")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


# ------------------------------------------------------------- A4
def prepare_a4(ctx):
    ctx.a4_three = [ctx.path("missing"), ctx.file("notes.txt"), ctx.broken_link("broken")]
    ctx.a4_many = [ctx.path(f"gone-{i:02d}") for i in range(1, 13)]
    return []


NO_DISPLAY = {"DISPLAY": None, "WAYLAND_DISPLAY": None, "GDK_BACKEND": "x11"}


@scenario("A4", "start with only bad paths: the error, exit 1, no window", prepare=prepare_a4, needs_display=False,
          steps=("three bad paths", "twelve bad paths"))
def a4(d):
    d.step("three bad paths")
    missing, notes, link = d.ctx.a4_three
    status, out, err = d.run_gui(d.ctx.a4_three, NO_DISPLAY)
    d.check("exit status", status, 1)
    d.check("stdout", out, "")
    d.check("stderr", err, no_folder_error([f"{missing}: not found", f"{notes}: not a folder",
                                            f"{link}: broken link"]))
    d.step("twelve bad paths")
    status, out, err = d.run_gui(d.ctx.a4_many, NO_DISPLAY)
    d.check("exit status", status, 1)
    d.check("stdout", out, "")
    d.check("stderr", err, no_folder_error([f"{p}: not found" for p in d.ctx.a4_many]))


# ------------------------------------------------------------- A5
def prepare_a5(ctx):
    music, videos = ctx.folder("Music"), ctx.folder("Videos")
    ctx.s1 = ctx.symbol("folder-music", "audio-x-generic", "star")
    ctx.s2 = ctx.symbol("folder-videos", "video-x-generic", "circle")
    ctx.s3 = ctx.symbol("network-wireless", "network-server", "square")
    ctx.record(music, ctx.s1, "red")
    ctx.record(videos, ctx.s2, "blue")
    ctx.music, ctx.videos = music, videos
    return [music]


def set_search(d, text):
    """Type text into the search entry and wait until the gallery has filtered (search-changed is
    delayed): the query property is the text and the grid has fewer items."""
    header, before = d.find_one("gallery-header"), d.grid_model().get_n_items()
    d.find_one("search-entry").set_text(text)
    d.wait_until(lambda: header.get_property("query") == text and d.grid_model().get_n_items() < before,
                 f"the search {text!r} to filter the grid")
    return header


@scenario("A5", "a second launch with another folder updates the same window", prepare=prepare_a5,
          steps=("window shown", "first selection", "search set", "category set", "manifest edited",
                 "second launch", "same window updated"))
def a5(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.step("first selection")
    d.check("folder title", d.find_one("folder-title").get_title(), "Music")
    d.check("gallery selection", d.selected_name(), ctx.s1)
    d.check("preview accent", accent(d), "red")
    d.step("search set")
    header = set_search(d, SEARCH)
    if ctx.symbols_source == "fixture":
        d.check("symbols matching the search", d.grid_model().get_n_items(), fixture_matches(SEARCH))
    d.step("category set")
    after_search = d.grid_model().get_n_items()
    header.activate_action("gallery.category", d.GLib.Variant.new_string(CATEGORY))
    try:
        d.wait_until(lambda: header.get_property("category") == CATEGORY
                     and d.grid_model().get_n_items() < after_search,
                     f"the category {CATEGORY!r} to narrow the grid", timeout=5)
    except Fail:
        if d.watchdog_fired:
            raise
        # the checks below record what did not happen
    after_category = d.grid_model().get_n_items()
    d.check("category", header.get_property("category"), CATEGORY)
    d.check(f"category narrows the grid ({after_category} < {after_search})", after_category < after_search, True)
    if ctx.symbols_source == "fixture":
        expected = fixture_matches(SEARCH, CATEGORY)
    else:
        expected = fixtures.count_matching(ctx.symbols_dir, SEARCH, CATEGORY)
    d.check("symbols matching search and category", after_category, expected)
    d.step("manifest edited")
    ctx.record(ctx.videos, ctx.s3, "purple")         # after the start: a cached state would show s2/blue
    d.step("second launch")
    opens = len(d.opens)
    launch = d.launch([ctx.videos], "folder Videos")
    d.check("second launch exit status", launch.status, 0)
    d.check("second launch stdout", launch.out, "")
    d.check("second launch stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) > opens, "the Open of the second launch")
    d.check("Open emissions", len(d.opens), opens + 1)
    d.check("paths of the new Open", d.opens[-1], [ctx.videos])
    d.info(f"emissions: open {len(d.opens)}, activate {d.activates}")
    d.step("same window updated")
    d.check("windows", len(d.app.get_windows()), 1)
    d.check("mapped gallery-grid widgets", len(d.find_all("gallery-grid", mapped=True)), 1)
    d.check("mapped folder-title widgets", len(d.find_all("folder-title", mapped=True)), 1)
    d.check("folder title", d.find_one("folder-title").get_title(), "Videos")
    d.check("search text", d.find_one("search-entry").get_text(), "")
    d.check("query", header.get_property("query"), "")
    d.check("category", header.get_property("category"), "")
    d.check("gallery symbols", d.grid_model().get_n_items(), expected_symbols(d))
    d.check("gallery selection", d.selected_name(), ctx.s3)
    d.check("preview accent", accent(d), "purple")
    d.check("preview file", d.preview_file(), f"Yaru-purple-{ctx.s3}.svg")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


# ------------------------------------------------------------- A6
def prepare_a6(ctx):
    music = ctx.folder("Music")
    ctx.pictures = ctx.folder("Pictures")
    ctx.missing, ctx.notes = ctx.path("missing"), ctx.file("notes.txt")
    ctx.record(music, ctx.symbol("folder-music", "audio-x-generic", "star"), "red")
    return [music]


def window_state(d):
    header, title = d.find_one("gallery-header"), d.find_one("folder-title")
    return {"windows": len(d.app.get_windows()), "page": d.window.page, "title": title.get_title(),
            "tooltip": title.get_tooltip_text(), "selected": d.selected_name(),
            "search": d.find_one("search-entry").get_text(), "query": header.get_property("query"),
            "category": header.get_property("category"), "items": d.grid_model().get_n_items(),
            "accent": accent(d)}


@scenario("A6", "a second launch with only bad paths leaves the open window alone", prepare=prepare_a6,
          steps=("window shown", "state before", "bad second launch", "state unchanged", "good second launch"))
def a6(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.step("state before")
    set_search(d, SEARCH)
    before, opens, activates = window_state(d), len(d.opens), d.activates
    d.step("bad second launch")
    launch = d.launch([ctx.missing, ctx.notes], "only bad paths")
    d.check("bad launch exit status", launch.status, 1)
    d.check("bad launch stdout", launch.out, "")
    d.check("bad launch stderr", launch.err,
            no_folder_error([f"{ctx.missing}: not found", f"{ctx.notes}: not a folder"]))
    d.step("state unchanged")
    d.check("window state", window_state(d), before)
    d.check("Open emissions", len(d.opens), opens)
    d.check("activate emissions", d.activates, activates)
    d.step("good second launch")
    launch = d.launch([ctx.pictures], "a good path")
    d.check("good launch exit status", launch.status, 0)
    d.check("good launch stdout", launch.out, "")
    d.check("good launch stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) > opens, "the Open of the good launch")
    d.check("Open emissions", len(d.opens), opens + 1)
    d.check("paths of the new Open", d.opens[-1], [ctx.pictures])
    d.check("folder title", d.find_one("folder-title").get_title(), "Pictures")
    d.check("backend calls", d.backend.calls(), NO_CALLS)


# ------------------------------------------------------------- A7
def prepare_a7(ctx):
    ctx.music = ctx.folder("Music")
    return []


@scenario("A7", "the welcome page gives way to the main layout at the first selection", prepare=prepare_a7,
          steps=("window shown", "welcome page", "second launch with a folder", "main layout", "no way back"))
def a7(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("welcome page")
    d.check("page", win.page, "empty")
    d.check("gallery-grid widgets (any)", len(d.find_all("gallery-grid")), 0)
    d.step("second launch with a folder")
    launch = d.launch([d.ctx.music], "folder Music")
    d.check("second launch exit status", launch.status, 0)
    d.check("second launch stdout", launch.out, "")
    d.check("second launch stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) == 1 and win.page == "main", "the main page after the Open")
    d.step("main layout")
    d.check("windows", len(d.app.get_windows()), 1)
    d.check("gallery-grid widgets (any)", len(d.find_all("gallery-grid")), 1)
    d.check("mapped gallery-grid widgets", len(d.find_all("gallery-grid", mapped=True)), 1)
    d.check("mapped folder-title widgets", len(d.find_all("folder-title", mapped=True)), 1)
    d.check("mapped welcome-status widgets", len(d.find_all("welcome-status", mapped=True)), 0)
    d.check("folder title", d.find_one("folder-title").get_title(), "Music")
    d.check("gallery symbols", d.grid_model().get_n_items(), expected_symbols(d))
    d.step("no way back")
    # A check of update_selection's early return for an empty selection, not of appinfo.page_for: the
    # launcher never forwards an empty selection, so this path is otherwise dead.
    before = (win.page, d.find_one("folder-title").get_title(), d.grid_model().get_n_items(), d.selected_name())
    win.update_selection([], 0)
    after = (win.page, d.find_one("folder-title").get_title(), d.grid_model().get_n_items(), d.selected_name())
    d.check("state after an empty selection", after, before)
    d.check("backend calls", d.backend.calls(), NO_CALLS)
