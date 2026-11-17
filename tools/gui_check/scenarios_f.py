"""Scenarios F1-F5: Reset (gui/window.py _on_reset, _reset and _run; outcome.py reset_button_state,
reset_confirmation and reset_outcome). The expected texts are literals copied from outcome.py."""
import functools

import registry
import stubs
import ui
from scenarios_e import (DENIED, INJECTED, MISSING, NO_SPACE, OK_AND_CLOSE, OK_ONLY, UNEXPECTED_LINE, apply_tooltip,
                         choose_symbol, relaunch, symbol, tilde)

scenario = functools.partial(registry.scenario, in_session_run=False)
CONFIRM_BODY = "They get the normal folder icon of the theme again."
CONFIRM_RESPONSES = {"cancel": ("Cancel", "default"), "reset": ("Reset", "destructive")}


def recorded(ctx, names, record=None, accent="red"):
    """Folders by name; the ones in record (default: all) get a manifest entry with symbol(ctx)."""
    ctx.sym = symbol(ctx)
    ctx.paths = [ctx.folder(n) for n in names]
    for path, name in zip(ctx.paths, names):
        if record is None or name in record:
            ctx.record(path, ctx.sym, accent)
    return ctx.paths


def reset_and_confirm(d):
    ui.click(d, "reset-button")
    ui.visible_dialog(d, "the Reset confirmation")
    ui.answer_dialog(d, "reset")


# ------------------------------------------------------------- F1
FIVE = ("Music", "Videos", "Pictures", "Documents", "Downloads")


@scenario("F1", "the Reset label and tooltip: Reset 5, Reset 3 of 5, Reset, insensitive without records",
          prepare=lambda ctx: recorded(ctx, FIVE),
          steps=("window shown", "five recorded", "three of five", "one recorded", "none of two", "one without"))
def f1(d):
    ctx = d.ctx
    reset = lambda: ui.buttons_state(d)["reset"]
    d.step("window shown")
    d.wait_window()
    d.step("five recorded")
    d.check("Reset (label, sensitive, tooltip)", reset(),
            ("Reset 5", True, "Give the 5 selected folders their normal icon again"))
    d.step("three of five")
    ctx.forget(ctx.paths[3])
    ctx.forget(ctx.paths[4])
    relaunch(d, ctx.paths, "the five folders, three recorded")
    d.check("Reset (label, sensitive, tooltip)", reset(),
            ("Reset 3 of 5", True, "Give the 3 folders with an icon from Folder Symbols their normal icon again"))
    d.step("one recorded")
    relaunch(d, ctx.paths[:1], "Music")
    d.check("Reset (label, sensitive, tooltip)", reset(), ("Reset", True, "Give the folder its normal icon again"))
    d.step("none of two")
    relaunch(d, ctx.paths[3:], "Documents and Downloads, not recorded")
    d.check("Reset (label, sensitive, tooltip)", reset(),
            ("Reset", False, "None of the selected folders has an icon from Folder Symbols"))
    d.step("one without")
    relaunch(d, ctx.paths[3:4], "Documents, not recorded")
    d.check("Reset (label, sensitive, tooltip)", reset(),
            ("Reset", False, "This folder has no icon from Folder Symbols"))
    d.check("backend calls", d.backend.calls()["reset"], 0)


# ------------------------------------------------------------- F2, F2b
@scenario("F2", "Reset of one folder: no confirmation, called at once; a full success closes the window",
          prepare=lambda ctx: recorded(ctx, ("Music",)), steps=("window shown", "reset", "call"))
def f2(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.backend.reset.returns = stubs.folder_results(ctx.paths)
    d.step("reset")
    with d.allow_app_close():
        ui.click(d, "reset-button")
        ui.wait_quietly(d, lambda: not d.app.get_windows(), "the window to close after a full success")
    d.check("windows after a full success", len(d.app.get_windows()), 0)
    d.check("windows closed by the application", d.app_closes, 1)
    d.check("dialogs presented (no confirmation for one folder)", d.dialogs, [])
    d.step("call")
    d.check("reset_folders calls", d.backend.reset.calls, [((tuple(ctx.paths),), ())])


@scenario("F2b", "Reset of two folders: the confirmation (Cancel default, Reset destructive); Cancel does nothing",
          prepare=lambda ctx: recorded(ctx, ("Music", "Videos")),
          steps=("window shown", "confirmation", "Cancel", "Reset"))
def f2b(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.backend.reset.returns = stubs.folder_results(ctx.paths)
    d.step("confirmation")
    ui.click(d, "reset-button")
    ui.check_dialog(d, "Reset the icons of 2 folders?", CONFIRM_BODY,
                    "\n".join(tilde(d, p) for p in ctx.paths), CONFIRM_RESPONSES, default="cancel", close="cancel")
    d.step("Cancel")
    ui.answer_dialog(d, "cancel")
    ui.no_dialog(d, "after Cancel")
    d.check("reset_folders calls after Cancel", len(d.backend.reset.calls), 0)
    d.check("windows after Cancel", len(d.app.get_windows()), 1)
    d.step("Reset")
    ui.click(d, "reset-button")
    ui.visible_dialog(d, "the Reset confirmation again")
    ui.answer_closing(d, "reset")
    d.check("windows after a full success", len(d.app.get_windows()), 0)
    d.check("windows closed by the application", d.app_closes, 1)
    d.check("reset_folders calls", d.backend.reset.calls, [((tuple(ctx.paths),), ())])


# ------------------------------------------------------------- F3
@scenario("F3", "Reset outcomes: partial, all failed, ManifestError, RecordError, an unexpected error",
          prepare=lambda ctx: recorded(ctx, ("Music", "Videos")),
          steps=("window shown", "partial", "all failed", "ManifestError", "RecordError", "unexpected error"),
          stderr_tracebacks=(UNEXPECTED_LINE,))
def f3(d):
    from folder_symbols.apply import RecordError
    from folder_symbols.store import ManifestError
    ctx = d.ctx
    music, videos = ctx.paths
    two = ("Reset 2", True, "Give the 2 selected folders their normal icon again")
    d.step("window shown")
    d.wait_window()
    rounds = (
        ("partial", None, stubs.folder_results(ctx.paths, {videos: DENIED}),
         ("Reset 1 of 2, 1 failed", "The other folders have their normal icon again.",
          f"{tilde(d, videos)}: {DENIED}", OK_AND_CLOSE)),
        ("all failed", None, stubs.folder_results(ctx.paths, {music: DENIED, videos: MISSING}),
         ("Could not reset any of the 2 folders", "No folder was changed.",
          f"{tilde(d, music)}: {DENIED}\n{tilde(d, videos)}: {MISSING}", OK_ONLY)),
        ("ManifestError", ManifestError(f"the manifest is damaged ({INJECTED})"), None,
         ("Nothing was reset", f"the manifest is damaged ({INJECTED})", None, OK_ONLY)),
        ("RecordError", RecordError(stubs.folder_results(ctx.paths, {videos: DENIED}),
                                    OSError(28, "No space left on device")), None,
         ("Icons reset, but not recorded",
          f"The icon was reset on 1 of 2 folders, but the manifest could not be saved: {NO_SPACE}. "
          "'folder-symbols list' still shows them, as 'no icon'.", f"{tilde(d, videos)}: {DENIED}", OK_ONLY)),
        ("unexpected error", RuntimeError(INJECTED), None,
         ("Something went wrong", f"{UNEXPECTED_LINE}. Some folders may already have their normal icon again; "
          "'folder-symbols list' shows them.", None, OK_ONLY)),
    )
    for step, raises, returns, dialog in rounds:
        d.step(step)
        d.backend.reset.raises, d.backend.reset.returns = raises, returns
        reset_and_confirm(d)
        ui.check_dialog(d, *dialog)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, f"after {step}")
        d.check(f"windows after {step}", len(d.app.get_windows()), 1)
        d.check(f"Reset after {step}", ui.buttons_state(d)["reset"], two)
    d.check("reset_folders calls", d.backend.reset.calls, [((tuple(ctx.paths),), ())] * 5)


# ------------------------------------------------------------- F4
def prepare_f4(ctx):
    paths = recorded(ctx, ("Music", "Videos", "Pictures"))
    ctx.sym2 = ctx.symbol("folder-videos", "video-x-generic", "circle")
    return paths


@scenario("F4", "after an incomplete Reset: the count is recalculated, the selection and the accent are kept",
          prepare=prepare_f4, steps=("window shown", "another symbol and accent", "partial reset", "after OK"))
def f4(d):
    ctx = d.ctx
    music, videos, pictures = ctx.paths
    d.step("window shown")
    d.wait_window()
    d.check("Reset before", ui.buttons_state(d)["reset"],
            ("Reset 3", True, "Give the 3 selected folders their normal icon again"))
    d.step("another symbol and accent")
    choose_symbol(d, ctx.sym2)
    ui.click_swatch(d, "blue")
    ui.check_accents(d, selected=["blue"], switch=False)
    d.step("partial reset")
    d.backend.reset.returns = stubs.folder_results(ctx.paths, {videos: DENIED, pictures: MISSING})
    d.backend.reset.during = lambda *a, **k: ctx.forget(music)      # what the real reset does to Music
    reset_and_confirm(d)
    ui.check_dialog(d, "Reset 1 of 3, 2 failed", "The other folders have their normal icon again.",
                    f"{tilde(d, videos)}: {DENIED}\n{tilde(d, pictures)}: {MISSING}", OK_AND_CLOSE)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.step("after OK")
    d.check("Reset after (recounted)", ui.buttons_state(d)["reset"],
            ("Reset 2 of 3", True, "Give the 2 folders with an icon from Folder Symbols their normal icon again"))
    d.check("Apply after", ui.buttons_state(d)["apply"], (True, apply_tooltip(3)))
    d.check("gallery selection kept", d.selected_name(), ctx.sym2)
    ui.check_accents(d, selected=["blue"], switch=False)
    d.check("preview kept", d.preview_file(), f"Yaru-blue-{ctx.sym2}.svg")


# ------------------------------------------------------------- F5
@scenario("F5", "at the window's minimum width, 'Reset 2 of 3' and Apply fit side by side",
          prepare=lambda ctx: recorded(ctx, ("Music", "Videos", "Pictures"), record=("Music", "Videos")),
          steps=("window shown", "minimum width", "buttons fit"))
def f5(d):
    ctx = d.ctx
    d.step("window shown")
    win = d.wait_window()
    choose_symbol(d, ctx.sym)
    d.check("Reset label", ui.buttons_state(d)["reset"][0], "Reset 2 of 3")
    d.step("minimum width")
    ui.next_frames(d, win)
    default_width, default_height = win.get_default_size()
    frame = default_width - win.get_width()
    minimum = win.measure(d.Gtk.Orientation.HORIZONTAL, -1)[0]
    win.set_default_size(minimum + frame, default_height)
    ui.wait_quietly(d, lambda: win.get_width() == minimum, f"the window to be {minimum} px wide")
    ui.next_frames(d, win)
    d.check("window width is its minimum", win.get_width(), minimum)
    d.step("buttons fit")
    panel = ui.panel(d)
    boxes = {}
    for name in ("reset-button", "apply-button"):
        button = d.find_one(name)
        ok, rect = button.compute_bounds(panel)
        d.require(ok, f"the bounds of {name}")
        need = button.measure(d.Gtk.Orientation.HORIZONTAL, -1)[0]
        boxes[name] = (rect.get_x(), rect.get_width())
        d.check(f"{name} not narrower than its minimum ({rect.get_width():.0f} >= {need})", rect.get_width() >= need,
                True)
        d.check(f"{name} inside the panel", rect.get_x() >= 0 and rect.get_x() + rect.get_width() <= panel.get_width(),
                True)
    (rx, rw), (ax, _aw) = boxes["reset-button"], boxes["apply-button"]
    d.check("Reset ends before Apply starts", rx + rw <= ax, True)
    d.info(f"F5: window minimum {minimum} px (+ frame {frame}), panel {panel.get_width()} px, Reset {rx:.0f}+{rw:.0f}, "
           f"Apply {ax:.0f}+{boxes['apply-button'][1]:.0f}")
