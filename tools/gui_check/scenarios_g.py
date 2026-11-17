"""Scenarios G1-G6: Clean up (gui/window.py _on_cleanup, _cleanup and _busy_call; outcome.py cleanup_dialog,
cleanup_notes and cleanup_outcome). The menu item is the action win.clean-up; it is activated as the menu
does. The expected texts are literals copied from outcome.py."""
import functools

import registry
import stubs
import ui
from scenarios_e import INJECTED, OK_ONLY, UNEXPECTED_LINE, relaunch, tilde

scenario = functools.partial(registry.scenario, in_session_run=False)
NOTHING = "Nothing to clean up"
REMOVE_BODY = "The entries are only forgotten: no icon files are deleted and no folder's icon is changed."
REMOVE_RESPONSES = {"cancel": ("Cancel", "default"), "remove": ("Remove", "destructive")}
NOTHING_REMOVED_BODY = ("When checked again, none of the folders was surely missing (a drive may have been mounted "
                        "meanwhile), so every entry was kept.")
WARNINGS = ("entry 2 has no path", "entry 5 is not an object", "entry 7 has no recipe")


def clean_up(d):
    """The "Clean up…" menu item."""
    win = ui.window(d)
    d.require(win.lookup_action("clean-up").get_enabled(), "win.clean-up is disabled: the menu item is insensitive")
    win.activate_action("win.clean-up", None)


def music(ctx, record=False):
    ctx.music = ctx.folder("Music")
    if record:
        ctx.sym = ctx.symbol("folder-music", "audio-x-generic", "star")
        ctx.record(ctx.music, ctx.sym, "red")
    return [ctx.music]


def gone(ctx, n):
    return [ctx.path(f"gone-{i:02d}") for i in range(1, n + 1)]


# ------------------------------------------------------------- G1
def prepare_g1(ctx):
    music(ctx)
    return []


@scenario("G1", "the Clean up menu item works on the welcome page and the main page, blocked while it runs",
          prepare=prepare_g1, steps=("welcome page", "main page"))
def g1(d):
    win = d.wait_window()
    inside = []
    d.backend.plan_cleanup.returns = stubs.cleanup_plan(total=0)
    d.backend.plan_cleanup.during = lambda: inside.append(win.lookup_action("clean-up").get_enabled())
    for step, page in (("welcome page", "empty"), ("main page", "main")):
        d.step(step)
        if page == "main":
            relaunch(d, [d.ctx.music], "Music")
        d.check("page", win.page, page)
        d.check("win.clean-up enabled before", win.lookup_action("clean-up").get_enabled(), True)
        clean_up(d)
        ui.check_dialog(d, NOTHING, "No folders are recorded.", None, OK_ONLY)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, "after OK")
        d.check("win.clean-up enabled while plan_cleanup runs", inside[-1:], [False])
        d.check("win.clean-up enabled after", win.lookup_action("clean-up").get_enabled(), True)
    d.check("plan_cleanup calls", d.backend.plan_cleanup.calls, [((), ())] * 2)
    d.check("run_cleanup calls", len(d.backend.run_cleanup.calls), 0)


# ------------------------------------------------------------- G2
@scenario("G2", "nothing to clean up: every text variant", prepare=music,
          steps=("window shown", "nothing recorded", "all exist", "one outside home", "two outside home",
                 "one unknown", "two unknown", "outside home and unknown"))
def g2(d):
    ctx = d.ctx
    checked = "Every checked folder still exists."
    variants = (
        ("nothing recorded", stubs.cleanup_plan(total=0), "No folders are recorded."),
        ("all exist", stubs.cleanup_plan(total=3), "Every recorded folder still exists."),
        ("one outside home", stubs.cleanup_plan(skipped=1, total=3),
         f"{checked}\n\n1 folder outside your home was not checked."),
        ("two outside home", stubs.cleanup_plan(skipped=2, total=3),
         f"{checked}\n\n2 folders outside your home were not checked."),
        ("one unknown", stubs.cleanup_plan(unknown=[ctx.path("locked-1")], total=3),
         f"{checked}\n\n1 entry was kept because its folder could not be checked."),
        ("two unknown", stubs.cleanup_plan(unknown=[ctx.path("locked-1"), ctx.path("locked-2")], total=3),
         f"{checked}\n\n2 entries were kept because their folders could not be checked."),
        ("outside home and unknown", stubs.cleanup_plan(unknown=[ctx.path("locked-1")], skipped=1, total=3),
         f"{checked}\n\n1 folder outside your home was not checked.\n\n"
         "1 entry was kept because its folder could not be checked."),
    )
    d.step("window shown")
    d.wait_window()
    for step, plan, body in variants:
        d.step(step)
        d.backend.plan_cleanup.returns = plan
        clean_up(d)
        ui.check_dialog(d, NOTHING, body, None, OK_ONLY)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, f"after {step}")
    d.check("run_cleanup calls", len(d.backend.run_cleanup.calls), 0)


# ------------------------------------------------------------- G3
@scenario("G3", "entries to remove: the question, at most 10 listed, Cancel default, Remove destructive",
          prepare=music, steps=("window shown", "twelve entries", "Cancel", "one entry and a note", "Escape"))
def g3(d):
    ctx = d.ctx
    twelve = gone(ctx, 12)
    d.step("window shown")
    d.wait_window()
    d.backend.run_cleanup.returns = stubs.cleanup_result()   # only reached if a Cancel ran the cleanup
    d.step("twelve entries")
    d.backend.plan_cleanup.returns = stubs.cleanup_plan(stale=twelve)
    clean_up(d)
    ui.check_dialog(d, "Remove 12 entries for folders that no longer exist?", REMOVE_BODY,
                    "\n".join([tilde(d, p) for p in twelve[:10]] + ["... and 2 more"]),
                    REMOVE_RESPONSES, default="cancel", close="cancel")
    d.step("Cancel")
    ui.answer_dialog(d, "cancel")
    ui.no_dialog(d, "after Cancel")
    d.check("run_cleanup calls after Cancel", len(d.backend.run_cleanup.calls), 0)
    d.step("one entry and a note")
    d.backend.plan_cleanup.returns = stubs.cleanup_plan(stale=twelve[:1], skipped=1)
    clean_up(d)
    ui.check_dialog(d, "Remove 1 entry for a folder that no longer exists?",
                    f"{REMOVE_BODY}\n\n1 folder outside your home was not checked.", tilde(d, twelve[0]),
                    REMOVE_RESPONSES, default="cancel", close="cancel")
    d.step("Escape")
    ui.dismiss_dialog(d)
    ui.no_dialog(d, "after Escape")
    d.check("run_cleanup calls after Escape", len(d.backend.run_cleanup.calls), 0)
    d.check("win.clean-up enabled after", ui.window(d).lookup_action("clean-up").get_enabled(), True)


# ------------------------------------------------------------- G4
@scenario("G4", "Remove: the toasts, Nothing was removed, and the Reset count recalculated",
          prepare=lambda ctx: music(ctx, record=True),
          steps=("window shown", "all removed", "some removed", "one removed", "none removed"))
def g4(d):
    ctx = d.ctx
    three = gone(ctx, 3)
    d.step("window shown")
    d.wait_window()
    d.check("Reset before", ui.buttons_state(d)["reset"], ("Reset", True, "Give the folder its normal icon again"))
    rounds = (
        ("all removed", three, stubs.cleanup_result(removed=three), "Removed 3 entries"),
        ("some removed", three, stubs.cleanup_result(removed=three[:2], kept=three[2:]), "Removed 2 of 3 entries"),
        ("one removed", three[:1], stubs.cleanup_result(removed=three[:1]), "Removed 1 entry"),
    )
    with ui.Toasts(d) as toasts:
        for step, stale, result, toast in rounds:
            d.step(step)
            d.backend.plan_cleanup.returns = stubs.cleanup_plan(stale=stale)
            d.backend.run_cleanup.returns = result
            if step == "all removed":         # the manifest changes under the window: the count must follow
                d.backend.run_cleanup.during = lambda *_a: ctx.forget(ctx.music)
            else:
                d.backend.run_cleanup.during = None
            before = len(toasts.titles)
            clean_up(d)
            ui.visible_dialog(d, "the Remove question")
            ui.answer_dialog(d, "remove")
            ui.wait_quietly(d, lambda: len(toasts.titles) > before, f"the toast {toast!r}")
            d.check("toast title", toasts.titles[before:], [toast])
            ui.wait_quietly(d, lambda: ui.toast_label_shown(d, toast), f"the toast {toast!r} to be drawn")
            d.check(f"toast {toast!r} drawn in the window", ui.toast_label_shown(d, toast), True)
            toasts.dismiss_all()
            ui.no_dialog(d, f"after {step}")
            d.check("run_cleanup call", d.backend.run_cleanup.calls[-1], ((tuple(stale),), ()))
            if step == "all removed":
                d.check("Reset after (recounted)", ui.buttons_state(d)["reset"],
                        ("Reset", False, "This folder has no icon from Folder Symbols"))
    d.step("none removed")
    d.backend.plan_cleanup.returns = stubs.cleanup_plan(stale=three)
    d.backend.run_cleanup.returns = stubs.cleanup_result(kept=three)
    clean_up(d)
    ui.visible_dialog(d, "the Remove question")
    ui.answer_dialog(d, "remove")
    ui.check_dialog(d, "Nothing was removed", NOTHING_REMOVED_BODY, None, OK_ONLY)
    ui.answer_dialog(d, "ok")
    ui.no_dialog(d, "after OK")
    d.check("toasts", toasts.titles, ["Removed 3 entries", "Removed 2 of 3 entries", "Removed 1 entry"])
    d.check("run_cleanup calls", len(d.backend.run_cleanup.calls), 4)


# ------------------------------------------------------------- G5
@scenario("G5", "Clean up errors: Nothing was cleaned up, Something went wrong (with the traceback)", prepare=music,
          steps=("window shown", "plan: ManifestError", "plan: OSError", "run: OSError", "plan: unexpected error"),
          stderr_tracebacks=(UNEXPECTED_LINE,))
def g5(d):
    from folder_symbols.store import ManifestError
    ctx = d.ctx
    denied = PermissionError(13, "Permission denied", ctx.path(".local/share/folder-symbols/manifest.json"))
    d.step("window shown")
    win = d.wait_window()
    rounds = (
        ("plan: ManifestError", ManifestError(f"the manifest is damaged ({INJECTED})"), None,
         "Nothing was cleaned up", f"the manifest is damaged ({INJECTED})"),
        ("plan: OSError", denied, None, "Nothing was cleaned up",
         f"The manifest could not be saved: {denied}. Nothing was changed."),
        ("run: OSError", None, OSError(28, "No space left on device"), "Nothing was cleaned up",
         "The manifest could not be saved: [Errno 28] No space left on device. Nothing was changed."),
        ("plan: unexpected error", RuntimeError(INJECTED), None, "Something went wrong",
         f"{UNEXPECTED_LINE}. Nothing was changed."),
    )
    for step, plan_error, run_error, heading, body in rounds:
        d.step(step)
        d.backend.plan_cleanup.raises = plan_error
        d.backend.plan_cleanup.returns = stubs.cleanup_plan(stale=gone(ctx, 1))
        d.backend.run_cleanup.raises = run_error
        clean_up(d)
        if plan_error is None:
            ui.visible_dialog(d, "the Remove question")
            ui.answer_dialog(d, "remove")
        ui.check_dialog(d, heading, body, None, OK_ONLY)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, f"after {step}")
        d.check(f"win.clean-up enabled after {step}", win.lookup_action("clean-up").get_enabled(), True)
    d.check("backend calls", d.backend.calls(), {"apply": 0, "reset": 0, "plan_cleanup": 4, "run_cleanup": 1})


# ------------------------------------------------------------- G6
@scenario("G6", "warnings about unusable manifest entries are printed once per window", prepare=music,
          steps=("window shown", "two warnings", "the same and one more"),
          stderr_lines=lambda _home, _symbols: tuple(f"folder-symbols: {w}" for w in WARNINGS))
def g6(d):
    d.step("window shown")
    d.wait_window()
    for step, warnings in (("two warnings", WARNINGS[:2]), ("the same and one more", WARNINGS)):
        d.step(step)
        d.backend.plan_cleanup.returns = stubs.cleanup_plan(total=1, warnings=warnings)
        clean_up(d)
        ui.check_dialog(d, NOTHING, "Every recorded folder still exists.", None, OK_ONLY)
        ui.answer_dialog(d, "ok")
        ui.no_dialog(d, f"after {step}")
