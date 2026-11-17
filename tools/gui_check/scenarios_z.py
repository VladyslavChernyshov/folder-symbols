"""Self-tests of the GUI harness (--self-test): each one must give the verdict in its expect field. They show
that the harness can report NOT VERIFIED, a watchdog timeout, a window closed by someone else, a blocked
main loop killed by the parent, that wait_until counts real main-loop iterations, a wait's own timeout,
that the real application id on the private bus leaves the real session bus alone, a crash or a non-zero
exit after the end event, application diagnostics on stderr, a window closed before the scenario started
(through each of the driver's two checks, Z12 and Z15), a malformed event line, an end event of the wrong
type, and a process that exits without a result. Z17-Z22 cover the helpers added for the B, C and D scenarios:
the warning wording and the session-mode selection (Z17), the exact stderr lines a scenario must print
(Z18-Z20), the gsettings stub's icon theme file (Z21) and restore_permissions (Z22). Z23-Z32 cover those added
for E, F, G and H: a dialog left open (Z23), the dialog helpers (Z24), a window the application closes inside
allow_app_close (Z25) and a close after such a block, which is the user's again (Z26), not_verified (Z27, Z28),
the declared tracebacks (Z29-Z31) and Stub.during with the result builders (Z32). Z5 needs a person and runs
only when asked for by its exact id. Z8 expects NOT VERIFIED instead of PASS when the harness has no real
session bus."""
import argparse
import importlib.util
import os
import signal
import stat
import subprocess
import sys

import registry
from registry import FAIL, INCOMPLETE, NOT_VERIFIED, PASS, scenario


@scenario("Z1", "a scenario that needs Yaru, evaluated without it", selftest=True, needs_yaru=True,
          force_symbols="fixture", steps=("window shown",), expect=(NOT_VERIFIED, "no real Yaru symbols"))
def z1(d):
    d.step("window shown")
    d.wait_window()


@scenario("Z2", "a condition that never holds: the watchdog ends it", selftest=True, watchdog=3,
          steps=("window shown", "wait forever"), expect=(FAIL, "TIMEOUT at step 2: waiting for a condition"))
def z2(d):
    d.step("window shown")
    d.wait_window()
    d.step("wait forever")
    d.wait_until(lambda: False, "a condition that never holds", timeout=60)


@scenario("Z3", "the window is closed from outside the driver: INCOMPLETE", selftest=True,
          steps=("window shown", "close from outside", "after the close"),
          expect=(INCOMPLETE, "WINDOW CLOSED BY THE USER at step 2 of 3"))
def z3(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("close from outside")
    d.GLib.timeout_add(200, lambda: win.close() or False)    # not through the driver, like a person would
    d.wait_until(lambda: False, "the window to be closed from outside", timeout=10)
    d.step("after the close")


@scenario("Z4", "a blocked main loop: the parent kills the process", selftest=True, watchdog=3, kill_after=3,
          steps=("window shown", "block the main loop"),
          expect=(FAIL, "killed by the parent after 6 s: no result by then; last step 2 of 2 (block the main loop)"))
def z4(d):
    d.step("window shown")
    d.wait_window()
    d.step("block the main loop")
    read_end, _write_end = os.pipe()
    os.read(read_end, 1)          # nobody writes: blocks the main thread, so no GLib timeout can fire


@scenario("Z5", "manual: you close the window by hand", selftest=True, manual=True, watchdog=45,
          steps=("window shown", "wait for you to close the window"),
          expect=(INCOMPLETE, "WINDOW CLOSED BY THE USER at step 2 of 2"))
def z5(d):
    d.step("window shown")
    d.wait_window()
    d.step("wait for you to close the window")
    d.wait_until(lambda: False, "you to close the window", timeout=30)


@scenario("Z6", "wait_until counts real main-loop iterations (none when the condition already holds)",
          selftest=True, steps=("window shown", "condition already true", "condition true after three iterations"),
          expect=(PASS, ""))
def z6(d):
    d.step("window shown")
    d.wait_window()
    # An idle source that is always ready at a priority above everything else is dispatched exactly once
    # per main-context iteration: an independent count of the iterations.
    ticks = [0]

    def tick():
        ticks[0] += 1
        return d.GLib.SOURCE_CONTINUE

    source = d.GLib.idle_add(tick, priority=d.GLib.PRIORITY_HIGH)
    try:
        d.step("condition already true")
        start = ticks[0]
        d.check("iterations returned", d.wait_until(lambda: True, "a condition that holds"), 0)
        d.check("main-loop iterations counted", ticks[0] - start, 0)
        d.step("condition true after three iterations")
        start = ticks[0]
        d.check("iterations returned", d.wait_until(lambda: ticks[0] >= start + 3, "three iterations"), 3)
        d.check("main-loop iterations counted", ticks[0] - start, 3)
        d.check("last_iterations", d.last_iterations, 3)
    finally:
        d.GLib.source_remove(source)


@scenario("Z7", "a wait's own timeout, shorter than the watchdog", selftest=True,
          steps=("window shown", "short wait"),
          expect=(FAIL, "timeout waiting for a condition that never holds (1 s)", "TIMEOUT at step"))
def z7(d):
    d.step("window shown")
    d.wait_window()
    d.step("short wait")
    d.wait_until(lambda: False, "a condition that never holds", timeout=1)


@scenario("Z8", "the real application id on the private bus leaves the real session bus alone", selftest=True,
          app_id="real", needs_real_bus=True,
          steps=("window shown", "real id on the private bus", "parent's real-bus check"), expect=(PASS, ""),
          expect_no_real_bus=(NOT_VERIFIED, "not compared with the real session bus"))
def z8(d):
    d.step("window shown")
    d.wait_window()
    d.step("real id on the private bus")
    from folder_symbols.gui.application import APP_ID
    d.check("application id", d.app.get_application_id(), APP_ID)
    d.step("parent's real-bus check")
    reply = d.wait_parent()
    # No "*GuiCheck*" check here: this scenario runs the real id, which has no GuiCheck in it, so it could
    # never find one (the parent still checks it, as for every scenario).
    d.check("owner of the real id on the real bus unchanged", reply["real_owner_unchanged"], True)
    d.check("the real id on the real bus is not owned by this process",
            reply["real_owner_pid"] != os.getpid(), True)


@scenario("Z9", "killed by a signal during shutdown, after the end event: FAIL", selftest=True,
          steps=("window shown",), expect=(FAIL, "killed by SIGKILL after the end event"))
def z9(d):
    d.step("window shown")
    d.wait_window()
    # SIGKILL, not SIGSEGV or SIGABRT: no core file and no crash report
    d.app.connect("shutdown", lambda _app: os.kill(os.getpid(), signal.SIGKILL))


@scenario("Z10", "a non-zero exit during shutdown, after the end event: FAIL", selftest=True,
          steps=("window shown",), expect=(FAIL, "exited with code 3 after the end event"))
def z10(d):
    d.step("window shown")
    d.wait_window()
    d.app.connect("shutdown", lambda _app: os._exit(3))


@scenario("Z11", "application diagnostics (folder-symbols: ..., folder-symbols-gui: ...) on stderr: FAIL",
          selftest=True, needs_display=False, steps=("print two diagnostics",),
          expect=(FAIL, ("unexpected stderr line: folder-symbols: injected by the self-test",
                         "unexpected stderr line: folder-symbols-gui: injected by the self-test")))
def z11(d):
    d.step("print two diagnostics")
    print("folder-symbols: injected by the self-test", file=sys.stderr, flush=True)
    print("folder-symbols-gui: injected by the self-test", file=sys.stderr, flush=True)


def close_before_start(d):
    """Close the window from outside the driver before the driver's idle callback (DEFAULT_IDLE) runs."""
    def added(_app, window):
        d.GLib.idle_add(lambda: window.close() or False, priority=d.GLib.PRIORITY_HIGH_IDLE)
    d.app.connect("window-added", added)


# The app keeps running after this close, so Driver.start runs and finds the close itself: path "start"
# (20 of 20 runs on Ubuntu 26.04).
@scenario("Z12", "the window is closed before the scenario starts: INCOMPLETE (Driver.start's check)",
          selftest=True, on_start=close_before_start, steps=("window shown",),
          expect=(INCOMPLETE, ("WINDOW CLOSED BY THE USER before the scenario started (step 0 of 1)",
                               "end event path: start")))
def z12(d):
    d.step("window shown")
    d.wait_window()


def close_and_quit_before_start(d):
    """Close the window and quit the application in one callback that runs before the driver's idle callback
    (PRIORITY_HIGH_IDLE ahead of DEFAULT_IDLE): app.run() returns after that main-context iteration, so
    Driver.start never runs."""
    def added(_app, window):
        d.GLib.idle_add(lambda: window.close() or d.app.quit() or False, priority=d.GLib.PRIORITY_HIGH_IDLE)
    d.app.connect("window-added", added)


@scenario("Z15", "the window is closed and the app quits before the scenario starts: INCOMPLETE (run()'s check)",
          selftest=True, on_start=close_and_quit_before_start, steps=("window shown",),
          expect=(INCOMPLETE, ("WINDOW CLOSED BY THE USER before the scenario started (step 0 of 1)",
                               "end event path: run")))
def z15(d):
    d.step("window shown")
    d.wait_window()


@scenario("Z13", "a malformed event line from the scenario process: FAIL", selftest=True, needs_display=False,
          steps=("write a malformed line",), expect=(FAIL, "malformed event line from the child: 'not json {'"))
def z13(d):
    d.step("write a malformed line")
    os.write(int(os.environ["GUI_CHECK_RESULT_FD"]), b"not json {\n")


@scenario("Z14", "an end event with a null verdict (valid JSON, wrong type): FAIL", selftest=True,
          needs_display=False, steps=("write an end event with a null verdict",),
          expect=(FAIL, """malformed event line from the child: '{"t": "end", "verdict": null}'"""))
def z14(d):
    d.step("write an end event with a null verdict")
    os.write(int(os.environ["GUI_CHECK_RESULT_FD"]), b'{"t": "end", "verdict": null}\n')


@scenario("Z16", "the process exits with status 3, no end event and an empty stderr: FAIL", selftest=True,
          steps=("window shown", "exit"),
          expect=(FAIL, ("the scenario process ended (status 3) without a result; last step 2 of 2 (exit)",
                         "stderr: empty")))
def z16(d):
    d.step("window shown")
    d.wait_window()
    d.step("exit")
    os._exit(3)               # no end event, nothing on stderr: once taken for a user close in session mode


# ------------------------------------------------------------- Z17-Z22: the helpers added for B, C and D
def load_main():
    """The harness's __main__.py as a module (its main() runs only under its own __name__ guard)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__main__.py")
    spec = importlib.util.spec_from_file_location("gui_check_main", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WARNING_TAIL = " for a visual check, about {t} seconds in total, please do not touch the keyboard or mouse until " \
               "the finished message"
A_IDS = ["A1", "A2", "A2b", "A3", "A4", "A5", "A6", "A7"]
B_IDS = ["B1", "B2", "B3", "B4", "B4b", "B5"]


@scenario("Z17", "the warning wording (1 window, N windows) and the session-mode selection of B, C and D",
          selftest=True, needs_display=False, expect=(PASS, ""),
          steps=("wording", "default runs", "session -k B1", "session -k B"))
def z17(d):
    main = load_main()
    d.step("wording")
    d.check("warning for 1 window", main.warning_text(1), "Opening 1 window" + WARNING_TAIL.format(t=10))
    d.check("warning for 7 windows", main.warning_text(7), "Opening 7 windows" + WARNING_TAIL.format(t=30))
    scenarios = registry.load()
    args = lambda display, k=None: argparse.Namespace(display=display, self_test=False, k=k)
    d.step("default runs")
    chosen, left_out = main.select_scenarios(args("session"), scenarios)
    d.check("session run: scenarios", [s.id for s in chosen], A_IDS)
    d.check("session run: windows", sum(1 for s in chosen if s.opens_window), 7)
    d.check("session run: left out", left_out, [])
    chosen, _left_out = main.select_scenarios(args("xvfb"), scenarios)
    ids = [s.id for s in chosen]
    d.check("xvfb run: B1, C1 and D6 included", all(i in ids for i in ("B1", "C1", "D6")), True)
    d.step("session -k B1")
    chosen, left_out = main.select_scenarios(args("session", ["B1"]), scenarios)
    d.check("session -k B1: scenarios", [s.id for s in chosen], ["B1"])
    d.check("session -k B1: left out", left_out, [])
    n = sum(1 for s in chosen if s.opens_window)
    d.check("session -k B1: N windows", n, 1)
    d.check("session -k B1: T seconds", main.warning_seconds(n), 10)
    d.step("session -k B")
    chosen, left_out = main.select_scenarios(args("session", ["B"]), scenarios)
    d.check("session -k B: scenarios", [s.id for s in chosen], [])
    d.check("session -k B: left out", left_out, B_IDS)
    done = subprocess.run([sys.executable, os.path.join(d.root, "tools", "gui_check"), "--display", "session",
                           "-k", "B"], capture_output=True, text=True, timeout=30)
    d.check("session -k B: exit status", done.returncode, 2)
    d.check("session -k B: output", done.stdout,
            f"gui_check: {', '.join(B_IDS)} not selected in session mode, use -k <exact id>\n")


def z_line(home, _symbols_dir):
    return (f"folder-symbols: the self-test's expected line for {home}",)


def print_z_line(times):
    for _ in range(times):
        print(z_line(os.environ["HOME"], None)[0], file=sys.stderr, flush=True)


@scenario("Z18", "an expected stderr line (stderr_lines) printed once: allowed, PASS", selftest=True,
          needs_display=False, stderr_lines=z_line, steps=("print it once",), expect=(PASS, ""))
def z18(d):
    d.step("print it once")
    print_z_line(1)


@scenario("Z19", "an expected stderr line printed twice: FAIL", selftest=True, needs_display=False,
          stderr_lines=z_line, steps=("print it twice",),
          expect=(FAIL, "stderr: expected exactly", "unexpected stderr line"))
def z19(d):
    d.step("print it twice")
    print_z_line(2)


@scenario("Z20", "an expected stderr line not printed: FAIL", selftest=True, needs_display=False,
          stderr_lines=z_line, steps=("print nothing",), expect=(FAIL, ("stderr: expected exactly", "got []")))
def z20(d):
    d.step("print nothing")


@scenario("Z21", "the gsettings stub reports the scenario's icon theme file, else 'Yaru'", selftest=True,
          needs_display=False, steps=("without the file", "with the file"), expect=(PASS, ""))
def z21(d):
    path = os.environ["GUI_CHECK_ICON_THEME_FILE"]
    run_dir = os.path.realpath(os.environ["GUI_CHECK_RUN_DIR"]) + os.sep
    get = lambda: subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
                                 capture_output=True, text=True, timeout=10)
    d.step("without the file")
    d.check("theme file under the run directory", os.path.realpath(path).startswith(run_dir), True)
    d.check("theme file exists", os.path.exists(path), False)
    done = get()
    d.check("reply without the file", (done.returncode, done.stdout, done.stderr), (0, "'Yaru'\n", ""))
    d.step("with the file")
    d.ctx.icon_theme("Yaru-blue")
    done = get()
    d.check("reply with the file", (done.returncode, done.stdout, done.stderr), (0, "'Yaru-blue'\n", ""))


@scenario("Z22", "restore_permissions makes a mode-0 file and directory readable again, links untouched",
          selftest=True, needs_display=False, steps=("mode 0", "restored"), expect=(PASS, ""))
def z22(d):
    main = load_main()
    top = os.path.join(os.environ["TMPDIR"], "z22")
    inner = os.path.join(top, "inner")
    os.makedirs(inner)
    f = os.path.join(inner, "manifest.json")
    open(f, "w").close()
    link = os.path.join(top, "broken")
    os.symlink(os.path.join(top, "no-such-target"), link)
    d.step("mode 0")
    os.chmod(f, 0)
    os.chmod(inner, 0)
    d.check("modes before", (stat.S_IMODE(os.lstat(inner).st_mode), ), (0,))
    d.step("restored")
    main.restore_permissions(top)
    d.check("directory mode has rwx for the owner", stat.S_IMODE(os.lstat(inner).st_mode) & 0o700, 0o700)
    d.check("file mode has rw for the owner", stat.S_IMODE(os.lstat(f).st_mode) & 0o600, 0o600)
    d.check("broken link still a link", os.path.islink(link), True)


# ------------------------------------------------------------- Z23-Z32: the helpers added for E, F, G and H
def present_dialog(d, heading, responses=(("ok", "OK"),), default=None, close=None, extra=None):
    """An Adw.AlertDialog made here (not by the application) on the window; returns (dialog, responses got)."""
    Adw = d.Adw
    dialog = Adw.AlertDialog(heading=heading, body=f"{heading} body")
    if extra is not None:
        dialog.set_extra_child(d.Gtk.ScrolledWindow(child=d.Gtk.Label(label=extra)))
    for rid, label in responses:
        dialog.add_response(rid, label)
    if default:
        dialog.set_default_response(default)
    if close:
        dialog.set_close_response(close)
    got = []
    dialog.connect("response", lambda _d, r: got.append(r))
    dialog.present(d.window)
    d.wait_until(lambda: d.window.get_visible_dialog() is dialog, f"the dialog {heading!r} to be shown")
    return dialog, got


@scenario("Z23", "a dialog left open at the end of the scenario: FAIL", selftest=True,
          steps=("window shown", "present and leave"), expect=(FAIL, "a dialog was left open: 'Z23 left open'"))
def z23(d):
    d.step("window shown")
    d.wait_window()
    d.step("present and leave")
    present_dialog(d, "Z23 left open")


@scenario("Z24", "check_dialog and answer_dialog on a dialog: its texts, responses and the clicked response",
          selftest=True, steps=("window shown", "check", "answer"), expect=(PASS, ""))
def z24(d):
    import ui
    d.step("window shown")
    d.wait_window()
    d.step("check")
    dialog, got = present_dialog(d, "Z24 question", (("cancel", "Cancel"), ("remove", "Remove")), "cancel",
                                 "cancel", extra="~/a\n~/b")
    dialog.set_response_appearance("remove", d.Adw.ResponseAppearance.DESTRUCTIVE)
    ui.check_dialog(d, "Z24 question", "Z24 question body", "~/a\n~/b",
                    {"cancel": ("Cancel", "default"), "remove": ("Remove", "destructive")}, "cancel", "cancel")
    d.step("answer")
    ui.answer_dialog(d, "remove")
    d.check("responses emitted", got, ["remove"])
    d.check("visible dialog", d.window.get_visible_dialog(), None)
    d.check("dialogs recorded", d.dialogs, [(2, "Z24 question")])


@scenario("Z25", "the application closes its window inside allow_app_close: PASS, counted", selftest=True,
          steps=("window shown", "app closes"), expect=(PASS, ""))
def z25(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("app closes")
    with d.allow_app_close():
        d.GLib.idle_add(lambda: win.close() or False)
        d.wait_until(lambda: not d.app.get_windows(), "the window to close")
    d.check("windows closed by the application", d.app_closes, 1)
    d.check("closing reset after the block", (d.closing, d.expect_close), (False, False))


@scenario("Z26", "after an allow_app_close block, a close is the user's again: INCOMPLETE", selftest=True,
          steps=("window shown", "empty allow block", "close from outside", "after the close"),
          expect=(INCOMPLETE, "WINDOW CLOSED BY THE USER at step 3 of 4"))
def z26(d):
    d.step("window shown")
    win = d.wait_window()
    d.step("empty allow block")
    with d.allow_app_close():
        pass
    d.step("close from outside")
    d.GLib.timeout_add(200, lambda: win.close() or False)
    d.wait_until(lambda: False, "the window to be closed from outside", timeout=10)
    d.step("after the close")


@scenario("Z27", "a part the scenario cannot check (not_verified): NOT VERIFIED with the reason", selftest=True,
          needs_display=False, steps=("not verified",), expect=(NOT_VERIFIED, "the part Z27 cannot check"))
def z27(d):
    d.step("not verified")
    d.not_verified("the part Z27 cannot check")


@scenario("Z28", "not_verified and a failed check: FAIL wins", selftest=True, needs_display=False,
          steps=("both",), expect=(FAIL, "1 difference(s)"))
def z28(d):
    d.step("both")
    d.not_verified("the part Z28 cannot check")
    d.check("a check that fails", 1, 2)


def print_traceback(message):
    import traceback
    try:
        raise RuntimeError(message)
    except RuntimeError:
        traceback.print_exc()
    sys.stderr.flush()


Z_TRACEBACK = "RuntimeError: injected by the self-test"


@scenario("Z29", "a declared traceback (stderr_tracebacks) printed once: allowed, PASS", selftest=True,
          needs_display=False, steps=("print it",), stderr_tracebacks=(Z_TRACEBACK,), expect=(PASS, ""))
def z29(d):
    d.step("print it")
    print_traceback("injected by the self-test")


@scenario("Z30", "a declared traceback printed twice: FAIL", selftest=True, needs_display=False,
          steps=("print it twice",), stderr_tracebacks=(Z_TRACEBACK,),
          expect=(FAIL, "stderr: expected exactly the tracebacks ending"))
def z30(d):
    d.step("print it twice")
    print_traceback("injected by the self-test")
    print_traceback("injected by the self-test")


@scenario("Z31", "a traceback with another exception than the declared one: FAIL", selftest=True,
          needs_display=False, steps=("print another",), stderr_tracebacks=(Z_TRACEBACK,),
          expect=(FAIL, ("stderr: expected exactly the tracebacks ending",
                         "unexpected stderr line: Traceback (most recent call last):")))
def z31(d):
    d.step("print another")
    print_traceback("something else")


@scenario("Z32", "Stub.during runs inside the call with the arguments; records are frozen; the result builders",
          selftest=True, needs_display=False, steps=("during and freeze", "builders"), expect=(PASS, ""))
def z32(d):
    import stubs
    from folder_symbols import apply, store
    d.step("during and freeze")
    stub, seen = stubs.Stub("z32"), []
    stub.returns = "result"
    stub.during = lambda *a, **k: seen.append((list(a[0]), dict(k), len(stub.calls)))
    dirs = ["/a", "/b"]
    d.check("returns", stub(dirs, "sym", dark=False), "result")
    dirs.append("/c")                     # a change after the call must not alter the record
    d.check("record", stub.calls, [((("/a", "/b"), "sym"), (("dark", False),))])
    d.check("during saw the arguments, after the record", seen, [(["/a", "/b"], {"dark": False}, 1)])
    stub.raises = ValueError("z32")
    try:
        stub([])
        raised = None
    except ValueError as e:
        raised = str(e)
    d.check("raises after during", (raised, len(seen)), ("z32", 2))
    d.step("builders")
    results = stubs.folder_results(["/a", "/b"], {"/b": "denied"})
    d.check("folder_results", results, [apply.FolderResult("/a", True, "icon set"),
                                        apply.FolderResult("/b", False, "denied")])
    plan = stubs.cleanup_plan(stale=["/x"], unknown=["/y"], skipped=2, warnings=("w",))
    d.check("cleanup_plan", (type(plan).__name__, [e.folder for e in plan.stale], [e.folder for e, _ in plan.unknown],
                             plan.skipped, plan.total, plan.warnings),
            ("CleanupPlan", ["/x"], ["/y"], 2, 4, ("w",)))
    d.check("cleanup_result", stubs.cleanup_result(["/x"], ["/y"]), store.CleanupResult(("/x",), ("/y",)))
