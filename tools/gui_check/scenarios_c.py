"""Scenarios C1-C6: the gallery (search, categories, selection, keyboard focus, no symbols, columns).

The expected counts are computed without the package's code (fixtures.count_matching, category_counts), and
the expected texts are literals copied from gallery.py, gui/gallery.py, gui/header.py and gui/window.py. Input
is emulated at signal level (ui.py)."""
import functools
import os

import fixtures
import registry
import ui
from scenarios_a import APPLY_NEEDS_SYMBOL, APPLY_ONE, PLAIN_PREVIEW, check_buttons, expected_symbols

scenario = functools.partial(registry.scenario, in_session_run=False)
SEARCH = "view"
NO_MATCH = "zzqx-no-symbol"
EMPTY_TITLE = "No symbols match"
EMPTY_TEXT = "Try another name or category."
ALL_CATEGORIES = "All categories"
NO_CATEGORY_ICON = "view-list-symbolic"
CLEAR_CATEGORY_ICONS = ["cross-small-symbolic", "window-close-symbolic"]
CAP_FALLBACK = "folder-symbols: category menu height not limited (unexpected menu layout)"
MENU_MAX_HEIGHT = 400
NO_SYMBOLS_TITLE = "Symbols not found"
INSTALL_HINT = "\n\nInstall yaru-theme-icon or point YARU_SYMBOLS_DIR at a folder with *-symbolic.svg files."
WIDTHS = (519, 700, 1000)


def prepare_music(ctx):
    return [ctx.folder("Music")]


def placeholder(n, category=None):
    noun = "symbol" if n == 1 else "symbols"
    return f"Search {n} {noun}…" if category is None else f"Search {n} {noun} in {category}…"


def count(d):
    """The number of symbols the gallery lists now, also while the grid is hidden by the placeholder."""
    grids = d.find_all("gallery-grid")
    d.require(len(grids) == 1, f"expected one gallery-grid widget, found {len(grids)}")
    return grids[0].get_model().get_n_items()


def matching(d, query, category=None):
    return fixtures.count_matching(d.ctx.symbols_dir, query, category)


# ------------------------------------------------------------- C1
def search(d, text, until, what):
    header = d.find_one("gallery-header")
    d.find_one("search-entry").set_text(text)
    ui.wait_quietly(d, lambda: header.get_property("query") == text and until(), what)


@scenario("C1", "search filters, no match shows the placeholder, clearing restores the list", prepare=prepare_music,
          steps=("window shown", "search filters", "no match", "search cleared"))
def c1(d):
    d.step("window shown")
    d.wait_window()
    total = expected_symbols(d)
    d.check("gallery symbols", count(d), total)
    d.check("search placeholder", d.find_one("search-entry").get_placeholder_text(), placeholder(total))
    d.step("search filters")
    wanted = matching(d, SEARCH)
    search(d, SEARCH, lambda: count(d) == wanted, f"the search {SEARCH!r} to filter the grid")
    d.check(f"symbols matching {SEARCH!r}", count(d), wanted)
    d.check(f"{SEARCH!r} narrows the list", 0 < wanted < total, True)
    d.step("no match")
    search(d, NO_MATCH, lambda: count(d) == 0, "the grid to be empty")
    d.check(f"symbols matching {NO_MATCH!r}", count(d), 0)
    d.check("mapped gallery-grid widgets", len(d.find_all("gallery-grid", mapped=True)), 0)
    empty = d.find_one("gallery-empty")
    d.check("placeholder title", empty.get_title(), EMPTY_TITLE)
    d.check("placeholder description", empty.get_description(), EMPTY_TEXT)
    d.step("search cleared")
    search(d, "", lambda: count(d) == total, "the full list after clearing the search")
    d.check("gallery symbols", count(d), total)
    d.check("mapped gallery-empty widgets", len(d.find_all("gallery-empty", mapped=True)), 0)
    d.check("mapped gallery-grid widgets", len(d.find_all("gallery-grid", mapped=True)), 1)


# ------------------------------------------------------------- C2
def menu_entries(d, button):
    """[(label, target)] of the split button's menu, section by section."""
    s = d.GLib.VariantType.new("s")
    model, entries = button.get_menu_model(), []
    for i in range(model.get_n_items()):
        section = model.get_item_link(i, "section")
        for j in range(section.get_n_items()):
            entries.append((section.get_item_attribute_value(j, "label", s).get_string(),
                            section.get_item_attribute_value(j, "target", s).get_string()))
    return entries


def c2_category(symbols_dir):
    """The category with the most symbols that still narrows the list (ties by name)."""
    counts, total = fixtures.category_counts(symbols_dir, ""), fixtures.count_symbols(symbols_dir)
    narrower = [(n, cat) for cat, n in counts.items() if n < total]
    return min(narrower, key=lambda x: (-x[0], x[1]))[1] if narrower else None


def check_split(d, category, total):
    button = d.find_one("category-button")
    image = button.get_child()
    d.check("category", d.find_one("gallery-header").get_property("category"), category)
    if category:
        gicon = image.get_gicon()
        # Gio.ThemedIcon.new_from_names appends the generic fallbacks ("cross-small", ...): the first names
        # are the app's own list
        names = list(gicon.get_names()) if isinstance(gicon, d.Gio.ThemedIcon) else None
        d.check("split button icon names (first ones)", names[:len(CLEAR_CATEGORY_ICONS)] if names else names,
                CLEAR_CATEGORY_ICONS)
        d.check("split button tooltip", button.get_tooltip_text(), f"Category: {category}. Click to show all")
        d.check("search placeholder", d.find_one("search-entry").get_placeholder_text(),
                placeholder(matching(d, "", category), category))
    else:
        d.check("split button icon", image.get_icon_name(), NO_CATEGORY_ICON)
        d.check("split button tooltip", button.get_tooltip_text(), None)
        d.check("search placeholder", d.find_one("search-entry").get_placeholder_text(), placeholder(total))
    d.check("gallery symbols", count(d), matching(d, "", category or None))


def choose(d, category, what):
    header = d.find_one("gallery-header")
    header.activate_action("gallery.category", d.GLib.Variant.new_string(category))
    ui.wait_quietly(d, lambda: header.get_property("category") == category
                    and count(d) == matching(d, "", category or None), what)


@scenario("C2", "categories: the split button's reset, its tooltip, All categories, the menu height cap",
          prepare=prepare_music, allowed_stderr=(CAP_FALLBACK,),
          steps=("window shown", "menu", "main part without a category", "category chosen", "main part clears",
                 "All categories", "menu opens"),
          not_verified_if=lambda symbols_dir, _source: None if c2_category(symbols_dir) else
          "no category narrows the list in this symbol set")
def c2(d):
    total, category = expected_symbols(d), c2_category(d.ctx.symbols_dir)
    d.step("window shown")
    d.wait_window()
    button = d.find_one("category-button")
    d.info(f"C2: category {category!r} ({matching(d, '', category)} of {total} symbols)")
    d.step("menu")
    categories = sorted(fixtures.category_counts(d.ctx.symbols_dir, ""))
    d.check("menu entries", menu_entries(d, button), [(ALL_CATEGORIES, "")] + [(c, c) for c in categories])
    check_split(d, "", total)
    d.step("main part without a category")
    button.activate()                     # the main part is insensitive: nothing happens
    ui.next_frames(d, button)
    check_split(d, "", total)
    d.step("category chosen")
    choose(d, category, f"the category {category!r} to filter the grid")
    check_split(d, category, total)
    d.step("main part clears")
    header = d.find_one("gallery-header")
    button.activate()
    ui.wait_quietly(d, lambda: header.get_property("category") == "" and count(d) == total,
                    "the main part to clear the category")
    check_split(d, "", total)
    d.step("All categories")
    choose(d, category, f"the category {category!r} again")
    choose(d, "", "All categories to restore the list")
    check_split(d, "", total)
    d.step("menu opens")
    popover = button.get_popover()
    scroller = popover.get_child() if popover is not None else None
    if isinstance(scroller, d.Gtk.ScrolledWindow) and scroller.get_max_content_height() == MENU_MAX_HEIGHT:
        d.info(f"C2: menu height capped (max-content-height {MENU_MAX_HEIGHT} px, propagate-natural-height "
               f"{scroller.get_propagate_natural_height()})")
    else:
        d.info(f"C2: menu height fallback (popover child {type(scroller).__name__}, not capped)")
    button.popup()
    ui.wait_quietly(d, lambda: popover is not None and popover.get_mapped(), "the category menu to open")
    d.check("category menu mapped after popup()", popover is not None and popover.get_mapped(), True)
    if popover is not None and popover.get_mapped():
        ui.next_frames(d, popover)
        d.info(f"C2: open menu {popover.get_width()}x{popover.get_height()} px"
               + (f", scrolled part {scroller.get_height()} px" if isinstance(scroller, d.Gtk.ScrolledWindow) else ""))
    button.popdown()
    ui.wait_quietly(d, lambda: popover is None or not popover.get_mapped(), "the category menu to close")
    d.check("category menu unmapped after popdown()", popover is not None and popover.get_mapped(), False)


# ------------------------------------------------------------- C3
def prepare_c3(ctx):
    ctx.sa = ctx.symbol("folder-music", "audio-x-generic", "star")
    ctx.sb = ctx.symbol("folder-videos", "video-x-generic", "circle")
    return [ctx.folder("Music")]


@scenario("C3", "a click selects and previews; a second click on the selected symbol keeps it", prepare=prepare_c3,
          steps=("window shown", "nothing selected", "first click", "second click", "another symbol"))
def c3(d):
    sa, sb = d.ctx.sa, d.ctx.sb
    d.step("window shown")
    d.wait_window()
    d.step("nothing selected")
    d.check("gallery selection", d.selected_name(), None)
    d.check("preview file", d.preview_file(), PLAIN_PREVIEW)
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), ("Reset", False, "This folder has no icon from Folder Symbols"))
    d.step("first click")
    ui.click_cell(d, sa)
    ui.wait_quietly(d, lambda: d.selected_name() == sa, f"{sa} to be selected")
    d.check("gallery selection", d.selected_name(), sa)
    d.check("preview file", d.preview_file(), f"Yaru-{sa}.svg")
    d.check("Apply sensitive", d.find_one("apply-button").get_sensitive(), True)
    d.check("Apply tooltip", d.find_one("apply-button").get_tooltip_text(), APPLY_ONE)
    d.step("second click")
    ui.click_cell(d, sa)
    ui.next_frames(d, ui.grid(d))
    d.check("gallery selection after the second click", d.selected_name(), sa)
    d.check("preview file", d.preview_file(), f"Yaru-{sa}.svg")
    d.check("Apply sensitive", d.find_one("apply-button").get_sensitive(), True)
    d.step("another symbol")
    ui.click_cell(d, sb)
    ui.wait_quietly(d, lambda: d.selected_name() == sb, f"{sb} to be selected")
    d.check("gallery selection", d.selected_name(), sb)
    d.check("preview file", d.preview_file(), f"Yaru-{sb}.svg")


# ------------------------------------------------------------- C4
def prepare_c4(ctx):
    music = ctx.folder("Music")
    ctx.sym = ctx.symbol("weather-clear", "user-trash", "star")
    ctx.record(music, ctx.sym, "red")
    return [music]


def item_widget(d, name):
    """The grid's focusable item widget that holds the symbol's card, or None."""
    c = ui.card(d, name)
    return c.get_parent() if c is not None else None


@scenario("C4", "keyboard: the focus starts on the selected cell; arrow keys switch the accent", prepare=prepare_c4,
          steps=("window shown", "focus on the selected cell", "focus on the red swatch", "Right", "Left"))
def c4(d):
    sym = d.ctx.sym
    d.step("window shown")
    win = d.wait_window()
    d.step("focus on the selected cell")
    ui.wait_quietly(d, lambda: item_widget(d, sym) is not None and win.get_focus() is item_widget(d, sym),
                    f"the focus on the cell of {sym}")
    focus = win.get_focus()
    d.check("focus widget is the selected cell's item", focus is not None and focus is item_widget(d, sym), True)
    d.info(f"C4: focus {type(focus).__name__ if focus is not None else None}; window is_active "
           f"{win.is_active()} (no window manager on Xvfb: informational)")
    d.step("focus on the red swatch")
    red = ui.swatch(d, "red")
    red.grab_focus()
    d.check("focus widget is the red swatch", win.get_focus() is red, True)
    ui.check_accents(d, selected=["red"], switch=False)
    d.step("Right")
    ui.arrow(d, win, "RIGHT")
    ui.wait_quietly(d, lambda: ui.accent_state(d)["selected"] == ["viridian"], "viridian to be selected")
    d.check("focus widget is the viridian swatch", win.get_focus() is ui.swatch(d, "viridian"), True)
    ui.check_accents(d, selected=["viridian"], switch=False)
    d.check("preview file", d.preview_file(), f"Yaru-viridian-{sym}.svg")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("viridian", None))
    d.step("Left")
    ui.arrow(d, win, "LEFT")
    ui.wait_quietly(d, lambda: ui.accent_state(d)["selected"] == ["red"], "red to be selected again")
    d.check("focus widget is the red swatch", win.get_focus() is ui.swatch(d, "red"), True)
    ui.check_accents(d, selected=["red"], switch=False)
    d.check("preview file", d.preview_file(), f"Yaru-red-{sym}.svg")


# ------------------------------------------------------------- C5, C5b
def no_symbols(d, reason_of):
    folder = os.environ["YARU_SYMBOLS_DIR"]
    run_dir = os.path.realpath(os.environ["GUI_CHECK_RUN_DIR"]) + os.sep
    d.step("window shown")
    d.wait_window()
    d.step("problem page")
    d.check("symbols directory under the run directory", os.path.realpath(folder).startswith(run_dir), True)
    page = d.find_one("no-symbols-page")
    d.check("page title", page.get_title(), NO_SYMBOLS_TITLE)
    d.check("page description", page.get_description(), reason_of(folder) + INSTALL_HINT)
    d.check("page icon", page.get_icon_name(), "dialog-warning-symbolic")
    d.step("controls")
    d.check("gallery-grid widgets (any)", len(d.find_all("gallery-grid")), 0)
    d.check("search sensitive", d.find_one("search-entry").get_sensitive(), False)
    d.check("search placeholder", d.find_one("search-entry").get_placeholder_text(), placeholder(0))
    d.check("category button sensitive", d.find_one("category-button").get_sensitive(), False)
    check_buttons(d, (False, APPLY_NEEDS_SYMBOL), ("Reset", False, "This folder has no icon from Folder Symbols"))
    d.check("preview file", d.preview_file(), PLAIN_PREVIEW)


@scenario("C5", "the symbols directory is missing: the problem page and the install hint", prepare=prepare_music,
          symbols_dir="missing", steps=("window shown", "problem page", "controls"))
def c5(d):
    d.require(not os.path.exists(os.environ["YARU_SYMBOLS_DIR"]), "the missing symbols directory exists")
    no_symbols(d, lambda folder: f"Folder does not exist: {folder}")


@scenario("C5b", "the symbols directory is empty: the problem page and the install hint", prepare=prepare_music,
          symbols_dir="empty", steps=("window shown", "problem page", "controls"))
def c5b(d):
    d.require(os.listdir(os.environ["YARU_SYMBOLS_DIR"]) == [], "the empty symbols directory is not empty")
    no_symbols(d, lambda folder: f"No *-symbolic.svg files in {folder}")


# ------------------------------------------------------------- C6
@scenario("C6", "the grid's column count does not decrease as the window grows", prepare=prepare_music,
          steps=("window shown", *(f"{w} px" for w in WIDTHS), "non-decreasing"))
def c6(d):
    d.step("window shown")
    win = d.wait_window()
    ui.next_frames(d, win)
    default_width, default_height = win.get_default_size()
    # The default size is the window's size including its client-side frame (drawn by GTK when there is no
    # compositing window manager, as on the harness's Xvfb), get_width() the size without it.
    frame = default_width - win.get_width()
    d.info(f"C6: default size {default_width}x{default_height}, window {win.get_width()}x{win.get_height()}: "
           f"frame {frame} px wide (no window manager), added to each requested width")
    measured = []
    for width in WIDTHS:
        d.step(f"{width} px")
        minimum = win.measure(d.Gtk.Orientation.HORIZONTAL, -1)[0]
        target = max(width, minimum)
        if target != width:
            d.info(f"FALLBACK C6: {width} px is below the window's minimum width {minimum} px; expecting {target} px")
        win.set_default_size(target + frame, default_height)
        ui.wait_quietly(d, lambda: win.get_width() == target, f"the window to be {target} px wide")
        ui.next_frames(d, ui.grid(d))
        d.check(f"window width after set_default_size({width})", win.get_width(), target)
        n = ui.columns(d)
        d.check(f"columns at {win.get_width()} px within 2..12", 2 <= n <= 12, True)
        measured.append((width, win.get_width(), n))
    d.step("non-decreasing")
    counts = [n for _, _, n in measured]
    d.info("C6: columns " + ", ".join(f"{w} px (window {a} px) -> {n}" for w, a, n in measured))
    d.check(f"column counts {counts} non-decreasing", all(a <= b for a, b in zip(counts, counts[1:])), True)
