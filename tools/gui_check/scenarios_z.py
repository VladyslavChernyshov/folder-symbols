"""Self-tests of the GUI harness (--self-test): each one must give the verdict in its expect field. They show
that the harness can report NOT VERIFIED, a watchdog timeout, a window closed by someone else, a blocked
main loop killed by the parent, that wait_until counts real main-loop iterations, a wait's own timeout,
that the real application id on the private bus leaves the real session bus alone, a crash or a non-zero
exit after the end event, application diagnostics on stderr, a window closed before the scenario started
(through each of the driver's two checks, Z12 and Z15), a malformed event line, an end event of the wrong
type, and a process that exits without a result. Z5 needs a person and runs only when asked for by its exact
id. Z8 expects NOT VERIFIED instead of PASS when the harness has no real session bus."""
import os
import signal
import sys

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
