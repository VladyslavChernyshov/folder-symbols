"""Scenarios E1-E9: Apply (gui/window.py _on_apply and _run, outcome.py apply_outcome).

The backend is the stub (stubs.py): each scenario presets what apply_folders returns or raises and checks
the frozen arguments it was called with. The expected texts are literals copied from outcome.py. A full
success closes the window: the click is made inside d.allow_app_close(), so the close is counted as the
application's and not taken for the user's. Every dialog is answered by the scenario (ui.answer_dialog)."""
import functools
import os

import registry
import stubs
import ui
from scenarios_a import APPLY_NEEDS_SYMBOL, APPLY_ONE, RESET_ONE

scenario = functools.partial(registry.scenario, in_session_run=False)
REFRESH_HINT = "Files may need a refresh (F5) to show the new icon."
INJECTED = "injected by the GUI harness"
UNEXPECTED_LINE = f"RuntimeError: {INJECTED}"
NO_SPACE = "[Errno 28] No space left on device"
DENIED = "gio: Operation not permitted"
MISSING = "gio: No such file or directory"
OK_ONLY = {"ok": ("OK", "default")}
OK_AND_CLOSE = {"close": ("Close Window", "default"), "ok": ("OK", "default")}


def apply_tooltip(n):
    what = ("Set this symbol and accent on the selected folder." if n == 1
            else f"Set this symbol and accent on the {n} selected folders.")
    return f"{what}\n{REFRESH_HINT}"


def symbol(ctx):
    return ctx.symbol("folder-music", "audio-x-generic", "star")


def folders(ctx, *names):
    paths = [ctx.folder(n) for n in names]
    ctx.paths = paths
    return paths


def choose_symbol(d, name):
    ui.click_cell(d, name)
    ui.wait_quietly(d, lambda: d.selected_name() == name, f"{name} to be selected")
    d.require(d.selected_name() == name, f"{name} was not selected")


def relaunch(d, paths, what):
    opens = len(d.opens)
    launch = d.launch(paths, what)
    d.check(f"second launch ({what}) exit status", launch.status, 0)
    d.check(f"second launch ({what}) stderr", launch.err, "")
    d.wait_until(lambda: len(d.opens) > opens, f"the Open of the second launch ({what})")


def apply_call(paths, sym, accent, system_accent=None, dark=False):
    """The frozen call record of apply_folders as gui/window.py makes it."""
    return ((tuple(paths), sym, accent),
            (("dark", dark), ("symbols_dir", os.environ["YARU_SYMBOLS_DIR"]), ("system_accent", system_accent)))


def apply_and_close(d):
    """Click Apply when it must succeed for every folder: the application closes its window."""
    with d.allow_app_close():
        ui.click(d, "apply-button")
        ui.wait_quietly(d, lambda: not d.app.get_windows(), "the window to close after a full success")
    d.check("windows after a full success", len(d.app.get_windows()), 0)
    d.check("windows closed by the application", d.app_closes, 1)
    d.check("dialogs presented", d.dialogs, [])


def tilde(d, path):
    return "~/" + os.path.relpath(path, os.environ["HOME"])


# ------------------------------------------------------------- E1
def prepare_e1(ctx):
    ctx.sym = symbol(ctx)
    ctx.videos = ctx.folder("Videos")
    return folders(ctx, "Music")


@scenario("E1", "Apply is insensitive without a symbol and says why; with one, the two-line tooltip",
          prepare=prepare_e1, steps=("window shown", "no symbol", "symbol chosen", "two folders, no symbol",
                                     "two folders, symbol chosen"))
def e1(d):
    sym = d.ctx.sym
    d.step("window shown")
    d.wait_window()
    d.info("E1: 'No folder selected' is not reachable in the window: the panel exists only once the window has "
           "folders, and update_selection ignores an empty selection (A1 and A7 check both)")
    d.step("no symbol")
    d.check("Apply (sensitive, tooltip)", ui.buttons_state(d)["apply"], (False, APPLY_NEEDS_SYMBOL))
    d.step("symbol chosen")
    choose_symbol(d, sym)
    d.check("Apply (sensitive, tooltip)", ui.buttons_state(d)["apply"], (True, apply_tooltip(1)))
    d.check("the one-folder tooltip is APPLY_ONE", apply_tooltip(1), APPLY_ONE)
    d.step("two folders, no symbol")
    relaunch(d, [d.ctx.paths[0], d.ctx.videos], "Music and Videos")
    d.check("Apply (sensitive, tooltip)", ui.buttons_state(d)["apply"], (False, APPLY_NEEDS_SYMBOL))
    d.step("two folders, symbol chosen")
    choose_symbol(d, sym)
    d.check("Apply (sensitive, tooltip)", ui.buttons_state(d)["apply"], (True, apply_tooltip(2)))
    d.check("backend calls", d.backend.calls()["apply"], 0)


# ------------------------------------------------------------- E2
def prepare_e2(ctx):
    paths = folders(ctx, "Music")
    ctx.sym = symbol(ctx)
    ctx.record(paths[0], ctx.sym, "purple")
    return paths


@scenario("E2", "Apply calls the backend once with the frozen choice; a full success closes the window",
          prepare=prepare_e2, steps=("window shown", "apply", "call"))
def e2(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.backend.apply.returns = stubs.folder_results(ctx.paths)
    d.step("apply")
    apply_and_close(d)
    d.step("call")
    d.check("apply_folders calls", d.backend.apply.calls, [apply_call(ctx.paths, ctx.sym, "purple")])
    d.check("other backend calls", {k: v for k, v in d.backend.calls().items() if k != "apply"},
            {"reset": 0, "plan_cleanup": 0, "run_cleanup": 0})


# ------------------------------------------------------------- E3
def prepare_e3(ctx):
    ctx.sym = symbol(ctx)
    return folders(ctx, "Music", "Videos", "Pictures")


@scenario("E3", "a partial failure: the dialog, OK keeps the window, the count is recalculated, Close Window",
          prepare=prepare_e3, steps=("window shown", "apply", "partial dialog", "OK", "apply again", "Close Window"))
def e3(d):
    ctx = d.ctx
    music, videos, pictures = ctx.paths
    d.step("window shown")
    d.wait_window()
    choose_symbol(d, ctx.sym)
    d.check("Reset before (label, sensitive, tooltip)", ui.buttons_state(d)["reset"],
            ("Reset", False, "None of the selected folders has an icon from Folder Symbols"))
    d.backend.apply.returns = stubs.folder_results(ctx.paths, {videos: DENIED, pictures: MISSING})
    # what the real apply_folders does for the folder it set: record it in the manifest
    d.backend.apply.during = lambda *a, **k: ctx.record(music, ctx.sym, "system")
    d.step("apply")
    ui.click(d, "apply-button")
    d.step("partial dialog")
    ui.check_dialog(d, "Applied to 1 of 3, 2 failed", "The other folders have their new icon.",
                    f"{tilde(d, videos)}: {DENIED}\n{tilde(d, pictures)}: {MISSING}", OK_AND_CLOSE)
    d.step("OK")
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("windows after OK", len(d.app.get_windows()), 1)
    d.check("buttons after OK (recounted)", ui.buttons_state(d), {
        "apply": (True, apply_tooltip(3)),
        "reset": ("Reset 1 of 3", True, "Give the one folder with an icon from Folder Symbols its normal icon again"),
        "clean-up": True})
    d.step("apply again")
    ui.click(d, "apply-button")
    ui.visible_dialog(d, "the partial dialog again")
    d.step("Close Window")
    ui.answer_closing(d, "close")
    d.check("windows after Close Window", len(d.app.get_windows()), 0)
    d.check("windows closed by the application", d.app_closes, 1)
    d.check("apply_folders calls", len(d.backend.apply.calls), 2)


# ------------------------------------------------------------- E4
def prepare_e4(ctx):
    ctx.sym = symbol(ctx)
    return folders(ctx, "Music", "Videos")


@scenario("E4", "every folder failed: the dialog without Close Window (two folders, then one)", prepare=prepare_e4,
          steps=("window shown", "two folders failed", "one folder failed"))
def e4(d):
    ctx = d.ctx
    music, videos = ctx.paths
    d.step("window shown")
    d.wait_window()
    d.step("two folders failed")
    choose_symbol(d, ctx.sym)
    d.backend.apply.returns = stubs.folder_results(ctx.paths, {music: DENIED, videos: MISSING})
    ui.click(d, "apply-button")
    ui.check_dialog(d, "Could not apply to any of the 2 folders", "No folder was changed.",
                    f"{tilde(d, music)}: {DENIED}\n{tilde(d, videos)}: {MISSING}", OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("Apply after OK", ui.buttons_state(d)["apply"], (True, apply_tooltip(2)))
    d.step("one folder failed")
    relaunch(d, [music], "Music")
    choose_symbol(d, ctx.sym)
    d.backend.apply.returns = stubs.folder_results([music], {music: DENIED})
    ui.click(d, "apply-button")
    ui.check_dialog(d, "Could not apply to the folder", "No folder was changed.", f"{tilde(d, music)}: {DENIED}",
                    OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("Apply after OK", ui.buttons_state(d)["apply"], (True, apply_tooltip(1)))


# ------------------------------------------------------------- E5
def prepare_one(ctx):
    ctx.sym = symbol(ctx)
    return folders(ctx, "Music")


@scenario("E5", "ManifestError and ApplyError: Nothing was applied, with the error", prepare=prepare_one,
          steps=("window shown", "ManifestError", "ApplyError"))
def e5(d):
    from folder_symbols.apply import ApplyError
    from folder_symbols.store import ManifestError
    d.step("window shown")
    d.wait_window()
    choose_symbol(d, d.ctx.sym)
    for step, error in (("ManifestError", ManifestError(f"the manifest is damaged ({INJECTED})")),
                        ("ApplyError", ApplyError(f"symbol 'x' not found ({INJECTED})"))):
        d.step(step)
        d.backend.apply.raises = error
        ui.click(d, "apply-button")
        ui.check_dialog(d, "Nothing was applied", str(error), None, OK_ONLY)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, "after OK")
        d.check("Apply after OK", ui.buttons_state(d)["apply"], (True, apply_tooltip(1)))
    d.check("apply_folders calls", len(d.backend.apply.calls), 2)


# ------------------------------------------------------------- E6
@scenario("E6", "RecordError: Icons set, but not recorded", prepare=prepare_e4, steps=("window shown", "RecordError"))
def e6(d):
    from folder_symbols.apply import RecordError
    ctx = d.ctx
    music, videos = ctx.paths
    d.step("window shown")
    d.wait_window()
    choose_symbol(d, ctx.sym)
    d.step("RecordError")
    d.backend.apply.raises = RecordError(stubs.folder_results(ctx.paths, {videos: DENIED}),
                                         OSError(28, "No space left on device"))
    ui.click(d, "apply-button")
    ui.check_dialog(d, "Icons set, but not recorded",
                    f"The icon was set on 1 of 2 folders, but the manifest could not be saved: {NO_SPACE}. "
                    "'folder-symbols list' and 'reset --all' will not see them.",
                    f"{tilde(d, videos)}: {DENIED}", OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("Apply after OK", ui.buttons_state(d)["apply"], (True, apply_tooltip(2)))


# ------------------------------------------------------------- E7
@scenario("E7", "an unexpected error: Something went wrong, the traceback on stderr, the window works on",
          prepare=prepare_one, steps=("window shown", "unexpected error", "responsive again"),
          stderr_tracebacks=(UNEXPECTED_LINE,))
def e7(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    choose_symbol(d, ctx.sym)
    d.step("unexpected error")
    d.backend.apply.raises = RuntimeError(INJECTED)
    ui.click(d, "apply-button")
    ui.check_dialog(d, "Something went wrong",
                    f"{UNEXPECTED_LINE}. Some folders may already have their new icon; 'folder-symbols list' "
                    "shows them.", None, OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.step("responsive again")
    d.check("Apply after OK", ui.buttons_state(d)["apply"], (True, apply_tooltip(1)))
    d.backend.apply.raises = None
    d.backend.apply.returns = stubs.folder_results(ctx.paths, {ctx.paths[0]: DENIED})
    ui.click(d, "apply-button")
    ui.check_dialog(d, "Could not apply to the folder", "No folder was changed.",
                    f"{tilde(d, ctx.paths[0])}: {DENIED}", OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("apply_folders calls", len(d.backend.apply.calls), 2)


# ------------------------------------------------------------- E8
def prepare_e8(ctx):
    paths = folders(ctx, "Music")
    ctx.sym = symbol(ctx)
    ctx.record(paths[0], ctx.sym, "red")
    return paths


@scenario("E8", "while Apply runs: both buttons and Clean up blocked, a second click does nothing",
          prepare=prepare_e8, steps=("window shown", "apply", "while it runs", "after it returns"))
def e8(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.check("buttons before", ui.buttons_state(d), {"apply": (True, apply_tooltip(1)),
                                                    "reset": ("Reset", True, RESET_ONE), "clean-up": True})
    inside = {}

    def during(*_args, **_kwargs):
        if inside:
            return                       # a re-entrant call (the guard is broken): record nothing more
        inside.update(ui.buttons_state(d))
        # GTK delivers no click to an insensitive button; these test the window's own busy guard
        d.find_one("apply-button").emit("clicked")
        d.find_one("reset-button").emit("clicked")
        inside["calls during"] = dict(d.backend.calls())

    d.backend.apply.during = during
    d.backend.apply.returns = stubs.folder_results(ctx.paths, {ctx.paths[0]: DENIED})
    d.backend.reset.returns = stubs.folder_results(ctx.paths)
    d.step("apply")
    ui.click(d, "apply-button")
    d.step("while it runs")
    d.check("state inside apply_folders", inside, {
        "apply": (False, "Applying…"), "reset": ("Reset", False, "Working…"), "clean-up": False,
        "calls during": {"apply": 1, "reset": 0, "plan_cleanup": 0, "run_cleanup": 0}})
    d.step("after it returns")
    ui.check_dialog(d, "Could not apply to the folder", "No folder was changed.",
                    f"{tilde(d, ctx.paths[0])}: {DENIED}", OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("dialogs presented", [h for _s, h in d.dialogs], ["Could not apply to the folder"])
    d.check("backend calls", d.backend.calls(), {"apply": 1, "reset": 0, "plan_cleanup": 0, "run_cleanup": 0})
    d.check("buttons after", ui.buttons_state(d), {"apply": (True, apply_tooltip(1)),
                                                   "reset": ("Reset", True, RESET_ONE), "clean-up": True})


# ------------------------------------------------------------- E9
def prepare_e9(ctx):
    paths = folders(ctx, "Music", "Videos")
    ctx.sym = symbol(ctx)
    ctx.record(paths[0], ctx.sym, "red")
    ctx.record(paths[1], ctx.sym, "system")
    return paths


@scenario("E9", "one folder pinned, one following the system: one call, one recipe for all", prepare=prepare_e9,
          steps=("window shown", "mixed accents", "apply", "one recipe"))
def e9(d):
    ctx = d.ctx
    d.step("window shown")
    d.wait_window()
    d.step("mixed accents")
    d.check("gallery selection", d.selected_name(), ctx.sym)
    ui.check_accents(d, selected=["orange"], system=["orange"], switch=True)
    d.backend.apply.returns = stubs.folder_results(ctx.paths)
    d.step("apply")
    apply_and_close(d)
    d.step("one recipe")
    d.check("apply_folders calls", d.backend.apply.calls,
            [apply_call(ctx.paths, ctx.sym, "system", system_accent="orange")])
