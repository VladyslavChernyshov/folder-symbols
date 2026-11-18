"""The GTK side of the GUI harness: runs one scenario inside the real FolderSymbolsApplication's main loop.

Only public GTK/libadwaita API of GTK 4.14 / libadwaita 1.5 is used. Waiting is event-driven: wait_until
iterates the GLib main context until a condition holds; nothing sleeps. A GLib watchdog ends a scenario
that waits too long ("TIMEOUT at step N"); a window closed by anyone but the driver ends it INCOMPLETE
("WINDOW CLOSED BY THE USER at step N of M")."""
import contextlib
import json
import os
import stat
import sys
import traceback

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from registry import FAIL, INCOMPLETE, Fail, Incomplete, Recorder
from stubs import Backend

HERE = os.path.dirname(os.path.abspath(__file__))
PDEATH = os.path.join(HERE, "pdeath_exec.py")
DEFAULT_WAIT = 10                    # seconds a single wait_until may take unless the scenario says otherwise


class Launch:
    """The result of a second launch of folder-symbols-gui."""
    def __init__(self, status, out, err):
        self.status, self.out, self.err = status, out, err

    def __repr__(self):
        return f"Launch(status={self.status!r}, out={self.out!r}, err={self.err!r})"


class Driver(Recorder):
    def __init__(self, scenario, emit, ctx, app, backend, control_fd):
        super().__init__(scenario, emit, ctx)
        self.Gtk, self.Adw, self.Gio, self.GLib = Gtk, Adw, Gio, GLib
        self.app, self.backend = app, backend
        self.root = os.environ["GUI_CHECK_ROOT"]
        self.opens, self.activates = [], 0       # paths of every "open" emission; "activate" emissions
        self.closing = False                     # True while the driver itself closes a window
        self.expect_close = False                # True inside allow_app_close(): the app may close its window
        self.app_closes = 0                      # windows the app closed inside allow_app_close()
        self.dialogs = []                        # (step, heading) of every dialog presented on a window
        self.closed_by_user = False
        self.watchdog_fired = False
        self.waiting_for = None
        self.last_iterations = None              # main-context iterations of the last wait_until
        self.parent_messages = []                # lines the parent sent on the control pipe
        self._watchdog = None
        self.result = None
        self.finishing = False
        app.connect("window-added", self._on_window_added)
        app.connect("open", self._on_open)
        app.connect("activate", self._on_activate)
        if control_fd is not None:
            channel = GLib.IOChannel.unix_new(control_fd)
            GLib.io_add_watch(channel, GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN | GLib.IOCondition.HUP,
                              self._on_control)

    # ------------------------------------------------------------- signals
    def _on_window_added(self, _app, window):
        window.connect("close-request", self._on_close_request)
        if hasattr(window, "get_visible_dialog"):            # Adw.ApplicationWindow, libadwaita 1.5
            window.connect("notify::visible-dialog", self._on_visible_dialog)

    def _on_visible_dialog(self, window, _pspec):
        dialog = window.get_visible_dialog()
        if dialog is not None:
            heading = dialog.get_heading() if hasattr(dialog, "get_heading") else type(dialog).__name__
            self.dialogs.append((self.step_no, heading))

    @contextlib.contextmanager
    def allow_app_close(self):
        """Inside this block the application may close its own window (after a full success, or "Close
        Window"): closing is set BEFORE the action, so the close is counted in app_closes and not taken for
        the user's. Outside it every close the driver did not make is the user's (INCOMPLETE), as before."""
        self.closing, self.expect_close = True, True
        try:
            yield
        finally:
            self.expect_close = False
            if not self.finishing:
                self.closing = False

    def open_dialogs(self):
        """[(window, dialog)] of the dialogs visible on the application's windows now."""
        return [(w, w.get_visible_dialog()) for w in self.app.get_windows()
                if hasattr(w, "get_visible_dialog") and w.get_visible_dialog() is not None]

    def _on_close_request(self, _window):
        if self.closing and self.expect_close:
            self.app_closes += 1
        if not self.closing:
            self.closed_by_user = True
            self.emit("log", text=f"WINDOW CLOSED BY THE USER at step {self.step_no} of {self.total_steps}")
        return False                              # let the window close

    def _on_open(self, _app, files, _n_files, _hint):
        self.opens.append([f.get_path() or f.get_uri() for f in files])

    def _on_activate(self, _app):
        self.activates += 1

    def _on_control(self, channel, condition):
        if condition & GLib.IOCondition.IN:
            status, line, _length, _term = channel.read_line()
            if line:
                self.parent_messages.append(line.rstrip("\n"))
                return True
        return False                              # HUP or EOF: the parent closed its end

    def _on_watchdog(self):
        self.watchdog_fired = True
        self._watchdog = None
        self.emit("log", text=f"TIMEOUT at step {self.step_no}: waiting for {self.waiting_for or 'nothing'}")
        self.app.quit()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------- waiting
    def wait_until(self, condition, what, timeout=DEFAULT_WAIT):
        """Iterate the main context until condition() is true. FAIL when timeout (seconds) passes or the
        watchdog fires, INCOMPLETE when the window was closed by the user. Returns the iterations needed
        (0 when the condition already held)."""
        if self.watchdog_fired:
            raise Fail(f"TIMEOUT at step {self.step_no}: waiting for {self.waiting_for}")
        if self.closed_by_user:
            raise Incomplete()
        self.last_iterations = 0
        if condition():
            return 0
        expired = []
        source = GLib.timeout_add(int(timeout * 1000), lambda: expired.append(True) or GLib.SOURCE_REMOVE)
        self.waiting_for = what
        context = GLib.MainContext.default()
        try:
            while True:
                context.iteration(True)
                self.last_iterations += 1
                if self.watchdog_fired:
                    raise Fail(f"TIMEOUT at step {self.step_no}: waiting for {what}")
                if self.closed_by_user:
                    raise Incomplete()
                if condition():
                    return self.last_iterations
                if expired:
                    raise Fail(f"step {self.step_no}: timeout waiting for {what} ({timeout} s)")
        finally:
            if not expired:
                GLib.source_remove(source)
            self.waiting_for = None

    def wait_window(self):
        """Wait for exactly one mapped window; return it."""
        self.wait_until(lambda: len(self.app.get_windows()) == 1 and self.app.get_windows()[0].get_mapped(),
                        "the window to be shown")
        return self.app.get_windows()[0]

    @property
    def window(self):
        windows = self.app.get_windows()
        self.require(len(windows) == 1, f"expected exactly one window, found {len(windows)}")
        return windows[0]

    # ------------------------------------------------------------- finding widgets
    @staticmethod
    def _walk(widget):
        yield widget
        child = widget.get_first_child()
        while child is not None:
            yield from Driver._walk(child)
            child = child.get_next_sibling()

    def find_all(self, name, scope=None, mapped=None):
        """Every widget named name under scope (default: every window), mapped or not unless asked."""
        roots = [scope] if scope is not None else list(self.app.get_windows())
        return [w for r in roots for w in self._walk(r)
                if w.get_name() == name and (mapped is None or w.get_mapped() == mapped)]

    def find_one(self, name, scope=None):
        """The one mapped widget named name under scope; FAIL unless there is exactly one."""
        mapped = self.find_all(name, scope, mapped=True)
        if len(mapped) != 1:
            unmapped = len(self.find_all(name, scope, mapped=False))
            raise Fail(f"step {self.step_no}: expected exactly one mapped {name!r}, found {len(mapped)} "
                       f"(and {unmapped} unmapped)")
        return mapped[0]

    # ------------------------------------------------------------- gallery helpers
    def grid_model(self):
        return self.find_one("gallery-grid").get_model()        # Gtk.SingleSelection

    def selected_name(self):
        """The name of the selected gallery symbol, or None."""
        item = self.grid_model().get_selected_item()
        return item.symbol.name if item is not None else None

    def preview_file(self):
        """The base name of the preview image's file icon, or a description of what it shows instead."""
        gicon = self.find_one("preview-image").get_gicon()
        if isinstance(gicon, Gio.FileIcon):
            return os.path.basename(gicon.get_file().get_path())
        return f"<not a file icon: {gicon!r}>"

    # ------------------------------------------------------------- second launch
    def launch(self, paths, what):
        """Start the real folder-symbols-gui with these paths, in this scenario's environment (same private
        bus, same test application id), and wait for it to exit. Event-driven (Gio.Subprocess)."""
        wrapper = os.path.join(self.root, "folder-symbols-gui")
        argv = [sys.executable, PDEATH, str(os.getpid()), sys.executable, wrapper, *paths]
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
        launcher.set_environ([f"{k}={v}" for k, v in os.environ.items()
                              if not k.startswith("GUI_CHECK_") or k in ("GUI_CHECK_RUN",)])
        process = launcher.spawnv(argv)
        result = {}

        def done(proc, res, _data):
            _ok, out, err = proc.communicate_utf8_finish(res)
            status = proc.get_exit_status() if proc.get_if_exited() else -proc.get_term_sig()
            result["launch"] = Launch(status, out or "", err or "")

        process.communicate_utf8_async(None, None, done, None)
        self.wait_until(lambda: "launch" in result, f"the second launch ({what}) to exit", timeout=20)
        launch = result["launch"]
        self.info(f"second launch ({what}): {' '.join(paths) or '(no paths)'} -> exit {launch.status}")
        return launch

    def wait_parent(self, timeout=DEFAULT_WAIT):
        """Wait for the parent's reply to the READY line (the real-bus check); returns it as a dict."""
        self.wait_until(lambda: self.parent_messages, "the parent's real-bus check", timeout=timeout)
        return json.loads(self.parent_messages[0])

    # ------------------------------------------------------------- preflight
    def preflight(self):
        """The isolation checks, one line each; any failure stops the scenario with FAIL."""
        problems = []

        def line(ok, text):
            self.emit("preflight", ok=ok, text=text)
            if not ok:
                problems.append(text)

        env = os.environ
        run_dir = env["GUI_CHECK_RUN_DIR"]
        under = lambda p: os.path.realpath(p).startswith(os.path.realpath(run_dir) + os.sep)
        self.emit("preflight", ok=True, text=f"versions: GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}."
                  f"{Gtk.get_micro_version()}, libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}."
                  f"{Adw.get_micro_version()}, PyGObject {gi.__version__}, Python {sys.version.split()[0]}")
        display = Gdk.Display.get_default()
        kind = GObject.type_name(display.__gtype__) if display is not None else None
        name = display.get_name() if display is not None else None
        if env["GUI_CHECK_DISPLAY_MODE"] == "xvfb":
            expected = env["GUI_CHECK_XVFB_DISPLAY"]
            line(kind == "GdkX11Display" and name == expected,
                 f"display: {kind} {name} (expected GdkX11Display {expected}, the harness's own Xvfb)")
        else:
            line(display is not None, f"display: {kind} {name} (session mode: your screen)")

        from folder_symbols.gui import application
        expected_id = env["GUI_CHECK_TEST_APP_ID"] if self.scenario.app_id == "test" else application.APP_ID
        app_id = self.app.get_application_id()
        line(app_id == expected_id, f"application id: {app_id} (expected {expected_id})")
        if self.scenario.app_id == "test":
            line(app_id != application.APP_ID, f"application id differs from the real {application.APP_ID}")
        line(application.APP_ID == env["GUI_CHECK_REAL_APP_ID"],
             f"the harness's real id {env['GUI_CHECK_REAL_APP_ID']} matches application.APP_ID")

        connection = self.app.get_dbus_connection()
        address = env.get("DBUS_SESSION_BUS_ADDRESS", "")
        bus_id = None
        if connection is None:
            line(False, "D-Bus: the application has no bus connection")
        else:
            call = lambda method, args, reply: connection.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", method, args,
                GLib.VariantType.new(reply), Gio.DBusCallFlags.NONE, -1, None).unpack()
            bus_id = call("GetId", None, "(s)")[0]
            socket = address[len("unix:path="):].split(",")[0] if address.startswith("unix:path=") else ""
            is_socket = bool(socket) and os.path.exists(socket) and stat.S_ISSOCK(os.stat(socket).st_mode)
            line(is_socket and under(socket), f"bus socket: {socket or address} (a socket under the run directory)")
            real_id = env.get("GUI_CHECK_REAL_BUS_ID", "")
            if real_id:
                line(bus_id != real_id, f"bus id: {bus_id}; the real session bus: {real_id} (must differ)")
            else:
                self.info(f"bus id: {bus_id}; not compared with the real session bus (the harness has none to "
                          "compare with)")
            activatable = call("ListActivatableNames", None, "(as)")[0]
            line(activatable == ["org.freedesktop.DBus"],
                 f"activatable names: {activatable} (expected only org.freedesktop.DBus: nothing can be autostarted)")
            owner = call("GetNameOwner", GLib.Variant("(s)", (app_id,)), "(s)")[0]
            line(owner == connection.get_unique_name(),
                 f"bus name {app_id} is owned by this process ({owner})")

        import folder_symbols
        package = os.path.dirname(os.path.realpath(folder_symbols.__file__))
        line(package == os.path.realpath(os.path.join(self.root, "folder_symbols")),
             f"package: {package} (expected the harness's own tree {self.root})")
        from folder_symbols import store
        line(under(os.path.expanduser("~")), f"HOME: {os.path.expanduser('~')} (under the run directory)")
        line(under(store.manifest_path()), f"manifest: {store.manifest_path()} (under the run directory)")
        import tempfile
        line(under(tempfile.gettempdir()), f"TMPDIR: {tempfile.gettempdir()} (under the run directory)")
        dark = Adw.StyleManager.get_default().get_dark()
        line(dark is False, f"style: dark={dark} (expected the light style pinned by the keyfile settings)")
        self.info(f"symbols: {env['GUI_CHECK_SYMBOLS_SOURCE']} {env['YARU_SYMBOLS_DIR']}")
        if problems:
            raise Fail("preflight: " + "; ".join(problems))
        self.emit("ready", app_id=app_id, bus_id=bus_id)

    # ------------------------------------------------------------- running
    def start(self):
        """The idle callback that runs the scenario inside app.run()."""
        self._watchdog = GLib.timeout_add_seconds(self.scenario.watchdog, self._on_watchdog)
        try:
            if self.closed_by_user:              # closed before this idle callback ran (the app may be gone)
                raise Incomplete()
            self.preflight()
            self.scenario.body(self)
            if self.closed_by_user:
                raise Incomplete()
            left = self.open_dialogs()
            if left:
                raise Fail(f"step {self.step_no}: a dialog was left open: "
                           + ", ".join(repr(d.get_heading() if hasattr(d, "get_heading") else type(d).__name__)
                                       for _w, d in left)
                           + " (every scenario must answer or close the dialogs it opens)")
            verdict, reason = self.verdict_after_body()
        except Incomplete:
            verdict, reason = INCOMPLETE, self.incomplete_reason()
        except Fail as e:
            verdict, reason = FAIL, str(e)
        except Exception:
            verdict, reason = FAIL, "exception in the scenario:\n" + traceback.format_exc()
        finally:
            if self._watchdog is not None:
                GLib.source_remove(self._watchdog)
                self._watchdog = None
            self.finish()
        self.result = (verdict, reason)
        self.emit("end", verdict=verdict, reason=reason, differences=self.differences,
                  steps_ran=self.step_no, steps=self.total_steps, path="start")
        return GLib.SOURCE_REMOVE

    def incomplete_reason(self):
        ran, not_run = self.steps_summary()
        where = (f"before the scenario started (step 0 of {self.total_steps})" if self.step_no == 0
                 else f"at step {self.step_no} of {self.total_steps}")
        return (f"WINDOW CLOSED BY THE USER {where}; ran: {', '.join(ran) or 'none'}; not run: "
                f"{', '.join(not_run) or 'none'}; the checks of the steps not run are unverified")

    def finish(self):
        """Close every window (the driver's own close, not the user's) and quit."""
        self.finishing = True
        self.closing = True
        for window in list(self.app.get_windows()):
            window.destroy()
        self.app.quit()


def run(scenario, emit, ctx, paths, control_fd):
    """Start the real application with stub backends and the scenario as an idle callback."""
    from folder_symbols.gui.application import FolderSymbolsApplication
    backend = Backend()
    app = FolderSymbolsApplication(**backend.kwargs())
    driver = Driver(scenario, emit, ctx, app, backend, control_fd)
    if scenario.on_start is not None:
        scenario.on_start(driver)
    GLib.idle_add(driver.start)
    status = app.run([os.path.join(driver.root, "folder-symbols-gui"), *paths])
    # path: "start" for the end event of Driver.start (including its own check of a close before the
    # scenario started), "run" for these two, when app.run() returned before Driver.start ran
    if driver.result is None and driver.closed_by_user:      # the idle callback never ran
        emit("end", verdict=INCOMPLETE, reason=driver.incomplete_reason(),
             differences=driver.differences, steps_ran=driver.step_no, steps=driver.total_steps, path="run")
    elif driver.result is None:
        emit("end", verdict=FAIL, reason=f"app.run() returned {status} before the scenario ended",
             differences=driver.differences, steps_ran=driver.step_no, steps=driver.total_steps, path="run")
    return status
