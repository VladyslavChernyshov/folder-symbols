"""Scenarios D1-D6: the accent panel (the swatches, the "Follow system accent" row, the system accent and the
light/dark style changing while the window is open).

The system accent is what the gsettings stub reports (ctx.icon_theme). A change while the window is open is
emulated the way the system announces it: the stub reports the new theme, then Gtk.Settings'
gtk-icon-theme-name changes (ui.set_system_theme). D4 (MATE) and D6 (the exact folder colours) need the real
Yaru data by the harness's rule; they are NOT VERIFIED with the fixture symbols."""
import functools

import fixtures
import registry
import ui

scenario = functools.partial(registry.scenario, in_session_run=False)


def recorded(ctx, accent, theme=None, name="Music"):
    folder = ctx.folder(name)
    ctx.sym = ctx.symbol("folder-music", "audio-x-generic", "star")
    ctx.record(folder, ctx.sym, accent)
    if theme:
        ctx.icon_theme(theme)
    return [folder]


def check_preview(d, variant):
    d.check("preview file", d.preview_file(), f"{variant}-{d.ctx.sym}.svg")


# ------------------------------------------------------------- D1
@scenario("D1", "a click on any swatch turns the switch off, moves the ring and recolours the preview",
          prepare=lambda ctx: recorded(ctx, "system", "Yaru-sage"),
          steps=("window shown", "following", "click the selected system swatch", "switch on again",
                 "click another swatch", "click it again", "click the system swatch"))
def d1(d):
    d.step("window shown")
    d.wait_window()
    d.step("following")
    ui.check_accents(d, selected=["sage"], system=["sage"], switch=True)
    check_preview(d, "Yaru-sage")
    d.step("click the selected system swatch")
    ui.click_swatch(d, "sage")
    ui.check_accents(d, selected=["sage"], system=["sage"], switch=False)
    check_preview(d, "Yaru-sage")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("sage", None))
    d.step("switch on again")
    ui.toggle_switch(d)
    ui.check_accents(d, selected=["sage"], switch=True)
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "sage"))
    d.step("click another swatch")
    ui.click_swatch(d, "blue")
    ui.check_accents(d, selected=["blue"], system=["sage"], switch=False)
    check_preview(d, "Yaru-blue")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("blue", None))
    d.step("click it again")
    ui.click_swatch(d, "blue")
    ui.check_accents(d, selected=["blue"], system=["sage"], switch=False)
    check_preview(d, "Yaru-blue")
    d.step("click the system swatch")
    ui.click_swatch(d, "sage")
    ui.check_accents(d, selected=["sage"], system=["sage"], switch=False)
    check_preview(d, "Yaru-sage")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("sage", None))


# ------------------------------------------------------------- D2
@scenario("D2", "the switch selects the system swatch; a click on the label toggles it",
          prepare=lambda ctx: recorded(ctx, "red", "Yaru-sage"),
          steps=("window shown", "pinned", "switch on", "label click", "label click again", "click on the switch"))
def d2(d):
    d.step("window shown")
    d.wait_window()
    d.step("pinned")
    ui.check_accents(d, selected=["red"], system=["sage"], switch=False, row_sensitive=True,
                     row_tooltip=ui.FOLLOW_TOOLTIP)
    d.step("switch on")
    ui.toggle_switch(d)
    ui.check_accents(d, selected=["sage"], system=["sage"], switch=True)
    check_preview(d, "Yaru-sage")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "sage"))
    d.step("label click")
    ui.click_row(d, "label")
    ui.check_accents(d, selected=["sage"], switch=False)
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("sage", None))
    d.step("label click again")
    ui.click_row(d, "label")
    ui.check_accents(d, selected=["sage"], switch=True)
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "sage"))
    d.step("click on the switch")
    # The row's handler leaves a click on the switch to the switch's own gesture (not emulated here), so
    # it must not toggle the switch itself: a real click would otherwise toggle it twice.
    ui.click_row(d, "switch")
    ui.check_accents(d, switch=True)


# ------------------------------------------------------------- D3
@scenario("D3", "a system icon theme that is not Yaru: the row is insensitive, with its tooltip",
          prepare=lambda ctx: recorded(ctx, "system", "Adwaita"),
          steps=("window shown", "no system accent", "label click"))
def d3(d):
    d.step("window shown")
    d.wait_window()
    d.step("no system accent")
    ui.check_accents(d, count=12, selected=["orange"], system=[], switch=False, row_sensitive=False,
                     row_tooltip=ui.NO_FOLLOW_TOOLTIP, marker=False)
    check_preview(d, "Yaru")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("orange", None))
    d.step("label click")
    ui.click_row(d, "label")
    ui.check_accents(d, switch=False, row_sensitive=False)


# ------------------------------------------------------------- D4
def prepare_d4(ctx):
    paths = recorded(ctx, "red")
    ctx.videos = ctx.folder("Videos")
    ctx.record(ctx.videos, ctx.sym, "mate")
    return paths


@scenario("D4", "the 13th swatch (MATE) only when the recorded or the system accent is mate", prepare=prepare_d4,
          needs_yaru=True,
          steps=("window shown", "twelve swatches", "system accent mate", "system accent orange",
                 "second launch: recorded mate"))
def d4(d):
    d.step("window shown")
    d.wait_window()
    d.step("twelve swatches")
    ui.check_accents(d, count=12, order=ui.PICKER_ORDER, selected=["red"], system=["orange"])
    d.step("system accent mate")
    ui.set_system_theme(d, "Yaru-mate")
    ui.check_accents(d, count=13, order=ui.WITH_MATE, selected=["red"], system=["mate"], switch=False)
    d.step("system accent orange")
    ui.set_system_theme(d, "Yaru")
    ui.check_accents(d, count=12, order=ui.PICKER_ORDER, selected=["red"], system=["orange"])
    d.step("second launch: recorded mate")
    opens = len(d.opens)
    launch = d.launch([d.ctx.videos], "folder Videos (recorded mate)")
    d.check("second launch exit status", launch.status, 0)
    d.check("second launch stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) > opens, "the Open of the second launch")
    ui.check_accents(d, count=13, order=ui.WITH_MATE, selected=["mate"], system=["orange"], switch=False)
    check_preview(d, "Yaru-mate")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("mate", None))


# ------------------------------------------------------------- D5, D5b
@scenario("D5", "the system accent changes while open: a following folder moves with it",
          prepare=lambda ctx: recorded(ctx, "system"),
          steps=("window shown", "following orange", "system accent blue", "system icon theme not Yaru",
                 "system accent sage"))
def d5(d):
    d.step("window shown")
    d.wait_window()
    d.step("following orange")
    ui.check_accents(d, selected=["orange"], system=["orange"], switch=True)
    check_preview(d, "Yaru")
    d.step("system accent blue")
    ui.set_system_theme(d, "Yaru-blue")
    ui.check_accents(d, system=["blue"], selected=["blue"], switch=True, marker=True)
    check_preview(d, "Yaru-blue")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("system", "blue"))
    d.step("system icon theme not Yaru")
    ui.set_system_theme(d, "Adwaita")
    ui.check_accents(d, system=[], selected=["blue"], switch=False, row_sensitive=False, marker=False)
    check_preview(d, "Yaru-blue")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("blue", None))
    d.step("system accent sage")
    # following does not come back by itself (accents.system_changed)
    ui.set_system_theme(d, "Yaru-sage")
    ui.check_accents(d, system=["sage"], selected=["blue"], switch=False, row_sensitive=True, marker=True)
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("blue", None))


@scenario("D5b", "the system accent changes while open: a pinned folder keeps its swatch",
          prepare=lambda ctx: recorded(ctx, "red"),
          steps=("window shown", "pinned red", "system accent blue"))
def d5b(d):
    d.step("window shown")
    d.wait_window()
    d.step("pinned red")
    ui.check_accents(d, selected=["red"], system=["orange"], switch=False)
    d.step("system accent blue")
    ui.set_system_theme(d, "Yaru-blue")
    ui.check_accents(d, system=["blue"], selected=["red"], switch=False)
    check_preview(d, "Yaru-red")
    d.check("apply choice (accent, system_accent)", ui.choice(d), ("red", None))


# ------------------------------------------------------------- D6
def check_style(d, dark):
    variant = "Yaru-red-dark" if dark else "Yaru-red"
    other = "Yaru-red" if dark else "Yaru-red-dark"
    d.check("style manager dark", d.Adw.StyleManager.get_default().get_dark(), dark)
    check_preview(d, variant)
    svg = ui.preview_svg(d).lower()
    d.check(f"preview SVG has the {variant} folder colour {fixtures.theme_color(variant)}",
            fixtures.theme_color(variant).lower() in svg, True)
    d.check(f"preview SVG lacks the {other} folder colour {fixtures.theme_color(other)}",
            fixtures.theme_color(other).lower() in svg, False)
    ui.check_accents(d, dark=dark, selected=["red"])
    d.check("current_choice().dark", ui.panel(d).current_choice().dark, dark)


@scenario("D6", "light/dark changes while open: the preview and the swatches follow", needs_yaru=True,
          prepare=lambda ctx: recorded(ctx, "red"), steps=("window shown", "light", "dark", "light again"))
def d6(d):
    d.step("window shown")
    d.wait_window()
    style = d.Adw.StyleManager.get_default()
    try:
        d.step("light")
        check_style(d, False)
        d.step("dark")
        ui.set_dark(d, True)
        ui.wait_quietly(d, lambda: style.get_dark(), "the dark style")
        check_style(d, True)
    finally:
        ui.set_dark(d, False)             # restore the scheme the harness pins (light)
    d.step("light again")
    ui.wait_quietly(d, lambda: not style.get_dark(), "the light style again")
    check_style(d, False)
