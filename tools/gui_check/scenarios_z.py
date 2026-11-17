"""Self-tests of the GUI harness (--self-test): each one must give the verdict in its expect field. They show
that the harness can report NOT VERIFIED, a watchdog timeout, a window closed by someone else, a blocked
main loop killed by the parent, a wait that needs no iteration, a wait's own timeout, and that the real
application id on the private bus leaves the real session bus alone. Z5 needs a person and runs only when
asked for by its exact id."""
import os

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


@scenario("Z6", "a condition that already holds needs no iteration", selftest=True,
          steps=("window shown", "condition already true"), expect=(PASS, ""))
def z6(d):
    d.step("window shown")
    d.wait_window()
    d.step("condition already true")
    d.check("iterations", d.wait_until(lambda: True, "a condition that holds"), 0)


@scenario("Z7", "a wait's own timeout, shorter than the watchdog", selftest=True,
          steps=("window shown", "short wait"),
          expect=(FAIL, "timeout waiting for a condition that never holds (1 s)", "TIMEOUT at step"))
def z7(d):
    d.step("window shown")
    d.wait_window()
    d.step("short wait")
    d.wait_until(lambda: False, "a condition that never holds", timeout=1)


@scenario("Z8", "the real application id on the private bus leaves the real session bus alone", selftest=True,
          app_id="real", needs_private_bus=True,
          steps=("window shown", "real id on the private bus", "parent's real-bus check"), expect=(PASS, ""))
def z8(d):
    d.step("window shown")
    d.wait_window()
    d.step("real id on the private bus")
    from folder_symbols.gui.application import APP_ID
    d.check("application id", d.app.get_application_id(), APP_ID)
    d.step("parent's real-bus check")
    reply = d.wait_parent()
    d.check("names with GuiCheck on the real bus", reply["guicheck"], [])
    d.check("owner of the real id on the real bus unchanged", reply["real_owner_unchanged"], True)
    d.check("the real id on the real bus is not owned by this process",
            reply["real_owner_pid"] != os.getpid(), True)
