#!/usr/bin/env python3
"""GUI harness for Folder Symbols: starts the real window (FolderSymbolsApplication) with stub backends, drives
it and checks states and texts. Local only: not part of `make check`, not run in CI.

  python3 tools/gui_check [-k ID[,ID...]] [--display xvfb|session] [--symbols auto|yaru|fixture]
                          [--self-test] [--list] [--out DIR] [--keep] [--scan-leftovers]
  make gui-check GUI_CHECK_ARGS="-k A5"

Each scenario runs in its own process (child.py) with an environment built from an allowlist:
  - a fresh HOME and XDG directories under the run directory, and a manifest fixture;
  - a private dbus-daemon of its own (no service directories, socket under the run directory; required);
  - a random test application id;
  - stub `gio` and `gsettings` commands;
  - the harness's own Xvfb (--display xvfb, the default) or your screen (--display session: a warning,
    a notification and a 5 s wait before each window).
Every process the harness starts dies with its parent (pdeath_exec.py). After each scenario and at the end,
/proc is scanned for processes left behind.

Exit status: 0 every scenario PASS; 1 any FAIL, INCOMPLETE or NOT RUN (or a failed run-level check); 2 the
harness cannot run (setup); 3 at least one NOT VERIFIED and no FAIL, INCOMPLETE or NOT RUN. With --self-test:
0 when every self-test gave its expected verdict, else 1."""
import argparse
import atexit
import json
import os
import random
import re
import select
import shlex
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT]

import fixtures                                                     # noqa: E402
import registry                                                     # noqa: E402
from registry import FAIL, INCOMPLETE, NOT_VERIFIED, PASS           # noqa: E402

REAL_APP_ID = "io.github.VladyslavChernyshov.FolderSymbols"        # the child checks it against application.APP_ID
PDEATH = os.path.join(HERE, "pdeath_exec.py")
CHILD = os.path.join(HERE, "child.py")
MARKER = "GUI_CHECK_RUN"
NOT_RUN = "NOT RUN"
WARNING = "Opening the window for a visual check in 5 seconds, please do not touch the keyboard or mouse"
SOCKET_MAX = 107                     # sun_path holds 108 bytes with the final NUL
STARTUP_TIMEOUT = 10                 # seconds for Xvfb and dbus-daemon to report their address
GSETTINGS_ALLOWED = "gsettings get org.gnome.desktop.interface icon-theme"
STDERR_BAD = ("Traceback", "-CRITICAL", "-WARNING", "-ERROR")
# The application's own diagnostics: "folder-symbols: ..." (for example gui/preview.py) and
# "folder-symbols-gui: ..." (the launcher's selection_error).
STDERR_BAD_PREFIXES = ("folder-symbols:", "folder-symbols-gui:")
TOOLS_PATH = "/usr/bin:/bin"         # PATH of the processes the harness starts, and where it looks for them
SAFE_PATH = re.compile(r"[A-Za-z0-9_./-]+")   # the run directory goes unescaped into a D-Bus address and bus.conf
NO_ADDRESS = "no D-Bus session bus address in the environment"
STDERR_TAIL = 5                      # stderr lines shown for a process that ended without a result
USER_CLOSED = "WINDOW CLOSED BY THE USER"
END_PATHS = ("start", "run")         # driver.py: Driver.start's own check, or run() after app.run() returned


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_str(v):
    return isinstance(v, str)


def _is_bool(v):
    return isinstance(v, bool)


def _str_or_none(v):
    return v is None or isinstance(v, str)


# Every event the child sends (registry.Recorder, child.py, driver.py): its required keys and their checks,
# and its optional keys. A line that does not match is a malformed event line.
EVENT_KEYS = {
    "step": ({"n": _is_int, "of": _is_int, "name": _is_str}, {}),
    "check": ({"step": _is_int, "label": _is_str, "ok": _is_bool, "expected": _is_str, "actual": _is_str}, {}),
    "info": ({"text": _is_str}, {}),
    "log": ({"text": _is_str}, {}),
    "preflight": ({"ok": _is_bool, "text": _is_str}, {}),
    "ready": ({"app_id": _is_str, "bus_id": _str_or_none}, {}),
    "end": ({"verdict": lambda v: v in (PASS, FAIL, INCOMPLETE, NOT_VERIFIED), "reason": _str_or_none,
             "differences": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
             "steps_ran": _is_int, "steps": _is_int},
            {"path": lambda v: v in END_PATHS}),
}


def valid_event(event):
    """True when event is a dict whose type is in EVENT_KEYS, with every required key of the right type and
    no optional key of the wrong type (other keys are ignored)."""
    if not isinstance(event, dict) or not isinstance(event.get("t"), str) or event["t"] not in EVENT_KEYS:
        return False
    required, optional = EVENT_KEYS[event["t"]]
    return (all(k in event and check(event[k]) for k, check in required.items())
            and all(check(event[k]) for k, check in optional.items() if k in event))
DISPLAY_MODES = ("xvfb", "session")
EXIT_OK, EXIT_FAIL, EXIT_SETUP, EXIT_NOT_VERIFIED = 0, 1, 2, 3
BUS_CONF = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<!-- The GUI harness's private session bus: no service directories (nothing can be autostarted), a socket
     under the run directory, and everything allowed between the processes of one scenario. -->
<busconfig>
  <type>session</type>
  <listen>unix:path={socket}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""
GIO_STUB = """#!/bin/sh
printf '%s\\n' "gio $*" >> {log}
echo "gio is disabled by the GUI harness" >&2
exit 99
"""
GSETTINGS_STUB = """#!/bin/sh
printf '%s\\n' "gsettings $*" >> {log}
if [ "$*" = "get org.gnome.desktop.interface icon-theme" ]; then echo "'Yaru'"; exit 0; fi
echo "gsettings: only 'get org.gnome.desktop.interface icon-theme' is allowed by the GUI harness" >&2
exit 99
"""
KEYFILE = "[org/gnome/desktop/interface]\ncolor-scheme='default'\n"


class SetupError(Exception):
    """The harness cannot run (exit 2)."""


def say(text=""):
    print(text, flush=True)


def signal_name(number):
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"


def random_suffix(n=10):
    first = random.choice(string.ascii_letters)
    return first + "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n - 1))


def scan_processes(marker_value=None, exclude=()):
    """[(pid, command line)] of this user's processes whose environment has GUI_CHECK_RUN (=marker_value
    if given), read from /proc/*/environ."""
    wanted = f"{MARKER}={marker_value}".encode() if marker_value else f"{MARKER}=".encode()
    found, uid = [], os.getuid()
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in exclude or int(entry) == os.getpid():
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid != uid:
                continue
            with open(f"/proc/{entry}/environ", "rb") as f:
                env = f.read().split(b"\0")
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        if any(e == wanted if marker_value else e.startswith(wanted) for e in env):
            found.append((int(entry), cmdline))
    return found


class RealBus:
    """Read-only queries on your real session bus (Gio, no GTK); None values when it cannot be reached.
    why_none says why there is no connection."""

    def __init__(self):
        self.connection = None
        if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return
        try:
            from gi.repository import Gio
            self.Gio = Gio
            self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:                     # no bus, or no PyGObject
            self.error = str(e)

    @property
    def why_none(self):
        if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return NO_ADDRESS
        return f"the real session bus is not reachable: {getattr(self, 'error', 'unknown error')}"

    def _call(self, method, args=None, reply="(s)"):
        from gi.repository import GLib
        return self.connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                         method, args, GLib.VariantType.new(reply),
                                         self.Gio.DBusCallFlags.NONE, 2000, None).unpack()

    def bus_id(self):
        return self._call("GetId")[0] if self.connection else None

    def names(self):
        return self._call("ListNames", None, "(as)")[0] if self.connection else []

    def owner_pid(self, name):
        """The process id of the owner of name, or None when nobody owns it."""
        from gi.repository import GLib
        if not self.connection:
            return None
        try:
            owner = self._call("GetNameOwner", GLib.Variant("(s)", (name,)))[0]
            return self._call("GetConnectionUnixProcessID", GLib.Variant("(s)", (owner,)), "(u)")[0]
        except GLib.Error:
            return None


class Result:
    def __init__(self, scenario):
        self.scenario = scenario
        self.verdict, self.reason = None, None
        self.details = []                # lines printed under the scenario's line
        self.events = []
        self.bad_events = []             # raw text of event lines that are not valid events
        self.seconds = 0.0
        self.allowed_seen = []           # allowlisted stderr lines that appeared
        self.user_closed = False         # the events show a window closed by the user


def stops_further_windows(res):
    """True when no further window may open after this result: a real scenario (not a self-test) that ended
    INCOMPLETE, or whose events show a window closed by the user, whatever its final verdict (the process
    may have crashed or hung in shutdown after the close)."""
    return not res.scenario.selftest and (res.verdict == INCOMPLETE or res.user_closed)


class Run:
    def __init__(self, args):
        self.args = args
        self.run_id = random_suffix()
        self.test_app_id = f"{REAL_APP_ID}.GuiCheck{self.run_id}"
        self.procs = []                  # every Popen this run started (all under pdeath_exec)
        self.xvfb, self.display = None, None
        self.dir = None
        self.info = []                   # informational lines (not checks)
        self.run_failures = []           # run-level checks that failed
        self.real_bus = RealBus()
        self.preflight_shown = False
        self.windows_opened = 0
        self.tools = {}                  # name -> absolute path, looked up in TOOLS_PATH

    # ------------------------------------------------------------- processes
    def spawn(self, argv, env, **kwargs):
        """Start argv under pdeath_exec, in its own process group, with exactly this environment."""
        p = subprocess.Popen([sys.executable, PDEATH, str(os.getpid()), *argv], env=env,
                             start_new_session=True, **kwargs)
        p.pgid = p.pid                    # start_new_session: p leads its own group; None once stopped
        self.procs.append(p)
        return p

    @staticmethod
    def stop(p, grace=3):
        """Stop p's whole process group once: SIGTERM, then (after p exited or grace seconds) SIGKILL to
        sweep members that outlived the leader, then reap p. Both signals are sent while p is not yet
        reaped (an exited p stays a zombie, which keeps its pid, so the group id cannot have been reused).
        A process that was stopped before, or reaped anywhere (poll, wait, os.waitpid), is not signalled:
        once it is reaped, stop returns without any further signal."""
        pgid, p.pgid = getattr(p, "pgid", None), None
        if pgid is None or p.returncode is not None:
            return
        try:
            os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return                        # reaped elsewhere: its group id may belong to someone else now
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            try:
                if os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                    break                 # exited, not reaped
            except ChildProcessError:
                return                    # reaped meanwhile: no SIGKILL after reaping
            time.sleep(0.02)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            p.wait(grace)
        except subprocess.TimeoutExpired:
            pass

    def cleanup(self):
        for p in reversed(self.procs):
            self.stop(p)
        self.procs = []

    def base_env(self, extra=None):
        env = {"PATH": TOOLS_PATH, "HOME": os.path.join(self.dir, "home-tools"), "LANG": "C.UTF-8",
               "TMPDIR": os.path.join(self.dir, "tmp"), MARKER: self.run_id}
        env.update(extra or {})
        return env

    def read_line_from(self, fd, p, what, log):
        """The first line written to fd by process p within STARTUP_TIMEOUT seconds."""
        deadline, data = time.monotonic() + STARTUP_TIMEOUT, b""
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or p.poll() is not None:
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if ready:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                data += chunk
        os.close(fd)
        if b"\n" not in data:
            tail = "".join(open(log, encoding="utf-8", errors="replace").readlines()[-8:]) if os.path.exists(log) else ""
            state = "exited with status %s" % p.poll() if p.poll() is not None else "gave no answer"
            raise SetupError(f"{what} {state} within {STARTUP_TIMEOUT} s; the last lines of {log}:\n{tail}")
        return data.split(b"\n", 1)[0].decode().strip()

    # ------------------------------------------------------------- setup
    def scenario_dir(self, sc):
        return os.path.join(self.dir, f"s-{sc.id}")

    @staticmethod
    def socket_path(sdir):
        return os.path.join(sdir, "bus", "socket")

    def setup(self, chosen):
        args = self.args
        base = os.path.abspath(args.out or tempfile.gettempdir())     # Python < 3.12: mkdtemp keeps it relative
        self.check_safe_path(base)                                     # before anything is created or started
        os.makedirs(base, exist_ok=True)
        self.dir = os.path.abspath(tempfile.mkdtemp(prefix="gui-check-", dir=base))
        self.check_safe_path(self.dir)
        for sub in ("bin", "tmp", "cache", "home-tools"):
            os.makedirs(os.path.join(self.dir, sub))
        for sc in chosen:
            socket = self.socket_path(self.scenario_dir(sc))
            if len(socket.encode()) > SOCKET_MAX:
                raise SetupError(f"the D-Bus socket path of {sc.id}, {socket}, is longer than {SOCKET_MAX} bytes; "
                                 f"use --out with a shorter directory; left the run directory {self.dir} "
                                 "(nothing was started in it)")
        self.gio_log = os.path.join(self.dir, "gio.log")
        self.gsettings_log = os.path.join(self.dir, "gsettings.log")
        for name, text in (("gio", GIO_STUB.format(log=shlex.quote(self.gio_log))),
                           ("gsettings", GSETTINGS_STUB.format(log=shlex.quote(self.gsettings_log)))):
            path = os.path.join(self.dir, "bin", name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(path, 0o755)

        # symbols
        from folder_symbols.symbols import YARU_SYMBOLS
        yaru_dir = os.environ.get("YARU_SYMBOLS_DIR") or YARU_SYMBOLS
        has_yaru = fixtures.has_symbols(yaru_dir)
        if args.symbols == "yaru" and not has_yaru:
            raise SetupError(f"--symbols yaru: no *-symbolic.svg under {yaru_dir}")
        self.fixture_dir = fixtures.write_symbols(os.path.join(self.dir, "symbols"))
        self.yaru_dir = yaru_dir if has_yaru else None
        self.source = "yaru" if has_yaru and args.symbols != "fixture" else "fixture"
        count = fixtures.count_symbols(yaru_dir) if self.source == "yaru" else len(fixtures.fixture_names())
        self.info.append(f"symbols: {self.source} ({count} symbols) "
                         f"{yaru_dir if self.source == 'yaru' else self.fixture_dir}"
                         + ("" if has_yaru else f"; no real Yaru under {yaru_dir}"))

        # bus
        self.tools["dbus-daemon"] = shutil.which("dbus-daemon", path=TOOLS_PATH)
        if self.tools["dbus-daemon"] is None:
            raise SetupError(f"dbus-daemon not found in {TOOLS_PATH}: the harness needs a private session bus; "
                             "install it (Ubuntu: sudo apt install dbus-daemon)")
        self.real_bus_id, self.real_names_before, self.real_owner_before = None, [], None
        if self.real_bus.connection is not None:
            from gi.repository import GLib
            try:
                self.real_bus_id = self.real_bus.bus_id()
                self.real_names_before = sorted(n for n in self.real_bus.names() if "FolderSymbols" in n)
                self.real_owner_before = self.real_bus.owner_pid(REAL_APP_ID)
            except GLib.Error as e:
                self.real_bus.connection, self.real_bus.error = None, str(e)
                self.real_bus_id, self.real_names_before = None, []
        if self.real_bus.connection is not None:
            self.info.append(f"real session bus: id {self.real_bus_id}; names with FolderSymbols before the run: "
                             f"{self.real_names_before or 'none'} (informational)")
        else:
            self.info.append(f"real session bus: not used ({self.real_bus.why_none})"
                             + "; not checked: that the private bus id differs from the real one, that no GuiCheck "
                             "name appears on the real bus while a scenario runs, and the owner of the real id; "
                             "Z8 is NOT VERIFIED. The private-bus checks (socket, activatable names, name owner) "
                             "still run")
        self.info.append(f"test application id: {self.test_app_id}")

        # display
        if args.display == "xvfb":
            self.tools["Xvfb"] = shutil.which("Xvfb", path=TOOLS_PATH)
            if self.tools["Xvfb"] is None:
                raise SetupError(f"Xvfb not found in {TOOLS_PATH}: install Xvfb, or use --display session")
            self.start_xvfb()
        else:
            what = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")
            if not what:
                raise SetupError("--display session: neither WAYLAND_DISPLAY nor DISPLAY is set")
            self.info.append(f"display: session ({'WAYLAND_DISPLAY=' + os.environ['WAYLAND_DISPLAY'] if os.environ.get('WAYLAND_DISPLAY') else 'DISPLAY=' + os.environ['DISPLAY']})"
                             "; windows appear on your screen")
            self.tools["notify-send"] = shutil.which("notify-send", path=TOOLS_PATH)
            if self.tools["notify-send"] is None:
                self.info.append(f"notify-send not found in {TOOLS_PATH}: the warning before each window is "
                                 "printed only")

    @staticmethod
    def check_safe_path(path):
        if not SAFE_PATH.fullmatch(path):
            raise SetupError(f"the run directory {path!r} has characters other than A-Z a-z 0-9 _ . / -, which "
                             "would break the D-Bus address and bus.conf; use --out with a plain path")

    def start_xvfb(self):
        log = os.path.join(self.dir, "xvfb.log")
        r, w = os.pipe()
        with open(log, "w") as out:
            self.xvfb = self.spawn([self.tools["Xvfb"], "-displayfd", str(w), "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                                   self.base_env(), pass_fds=(w,), stdout=out, stderr=subprocess.STDOUT)
        os.close(w)
        number = self.read_line_from(r, self.xvfb, "Xvfb", log)
        if not number.isdigit():
            raise SetupError(f"Xvfb reported {number!r} as its display; see {log}")
        self.display = f":{number}"
        self.info.append(f"display: xvfb {self.display} (pid {self.xvfb.pid}, the harness's own; no window manager; "
                         "GSK_RENDERER=cairo)")

    # ------------------------------------------------------------- one scenario
    def start_bus(self, sdir):
        socket = self.socket_path(sdir)
        os.makedirs(os.path.dirname(socket), mode=0o700)
        conf = os.path.join(sdir, "bus.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(BUS_CONF.format(socket=socket))
        log = os.path.join(sdir, "dbus-daemon.log")
        r, w = os.pipe()
        with open(log, "w") as out:
            p = self.spawn([self.tools["dbus-daemon"], f"--config-file={conf}", "--nofork", f"--print-address={w}"],
                           self.base_env(), pass_fds=(w,), stdout=out, stderr=subprocess.STDOUT)
        os.close(w)
        return p, self.read_line_from(r, p, "dbus-daemon", log)

    def child_env(self, sc, sdir, bus_address, result_fd, control_fd):
        home = os.path.join(sdir, "home")
        config = os.path.join(home, ".config")
        os.makedirs(os.path.join(config, "glib-2.0", "settings"))
        with open(os.path.join(config, "glib-2.0", "settings", "keyfile"), "w", encoding="utf-8") as f:
            f.write(KEYFILE)
        os.makedirs(os.path.join(sdir, "tmp"))
        source = "fixture" if sc.force_symbols == "fixture" else self.source
        env = {
            "PATH": f"{os.path.join(self.dir, 'bin')}:{TOOLS_PATH}",
            "HOME": home,
            "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
            "XDG_CONFIG_HOME": config,
            "XDG_STATE_HOME": os.path.join(home, ".local", "state"),
            "XDG_CACHE_HOME": os.path.join(self.dir, "cache"),
            "TMPDIR": os.path.join(sdir, "tmp"),
            "LANG": "C.UTF-8",
            "GIO_USE_VFS": "local",
            "GTK_IM_MODULE": "gtk-im-context-simple",
            "GSETTINGS_BACKEND": "keyfile",
            "GSK_RENDERER": "cairo",
            "GDK_DISABLE": "gl,vulkan",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "GTK_A11Y": "none",
            "NO_AT_BRIDGE": "1",
            "ADW_DISABLE_PORTAL": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "YARU_SYMBOLS_DIR": self.yaru_dir if source == "yaru" else self.fixture_dir,
            MARKER: self.run_id,
            "GUI_CHECK_ROOT": ROOT,
            "GUI_CHECK_RUN_DIR": self.dir,
            "GUI_CHECK_DISPLAY_MODE": self.args.display,
            "GUI_CHECK_XVFB_DISPLAY": self.display or "",
            "GUI_CHECK_REAL_BUS_ID": self.real_bus_id or "",
            "GUI_CHECK_REAL_APP_ID": REAL_APP_ID,
            "GUI_CHECK_TEST_APP_ID": self.test_app_id,
            "GUI_CHECK_SYMBOLS_SOURCE": source,
            "GUI_CHECK_RESULT_FD": str(result_fd),
            "GUI_CHECK_CONTROL_FD": str(control_fd),
        }
        os.makedirs(env["XDG_DATA_HOME"])
        if sc.app_id == "test":
            env["FOLDER_SYMBOLS_APP_ID"] = self.test_app_id
        env["DBUS_SESSION_BUS_ADDRESS"] = bus_address
        if self.args.display == "xvfb":
            runtime = os.path.join(sdir, "runtime")
            os.makedirs(runtime, mode=0o700)
            env.update(DISPLAY=self.display, GDK_BACKEND="x11", XDG_RUNTIME_DIR=runtime)
        else:
            for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY"):
                if os.environ.get(key):
                    env[key] = os.environ[key]
        return env, source

    def warn_before_window(self):
        say(WARNING)
        if self.tools.get("notify-send"):
            try:
                subprocess.run([self.tools["notify-send"], "Folder Symbols GUI check", WARNING], timeout=5,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass
        time.sleep(5)                     # the required pause before a window appears on your screen

    def real_bus_reply(self, ready):
        """The real-bus check while a child is up: no *GuiCheck* name, the real id's owner unchanged."""
        if self.real_bus.connection is None:
            return {"guicheck": [], "real_owner_unchanged": None, "real_owner_pid": None, "skipped": True}
        from gi.repository import GLib
        try:
            names = self.real_bus.names()
            owner = self.real_bus.owner_pid(REAL_APP_ID)
        except GLib.Error as e:
            return {"guicheck": None, "real_owner_unchanged": None, "real_owner_pid": None, "skipped": False,
                    "error": str(e)}
        return {"guicheck": sorted(n for n in names if "GuiCheck" in n),
                "real_owner_unchanged": owner == self.real_owner_before, "real_owner_pid": owner,
                "skipped": False}

    def run_scenario(self, sc):
        res = Result(sc)
        source = "fixture" if sc.force_symbols == "fixture" else self.source
        if sc.needs_yaru and source != "yaru":
            res.verdict, res.reason = NOT_VERIFIED, "no real Yaru symbols (only the generated fixture)"
            return res
        if sc.needs_real_bus and self.real_bus.connection is None:
            res.verdict, res.reason = NOT_VERIFIED, f"not compared with the real session bus: {self.real_bus.why_none}"
            return res
        if sc.not_verified_if is not None:
            why = sc.not_verified_if(self.yaru_dir if source == "yaru" else self.fixture_dir, source)
            if why:
                res.verdict, res.reason = NOT_VERIFIED, why
                return res
        sdir = self.scenario_dir(sc)
        os.makedirs(sdir)
        bus = None
        try:
            bus, address = self.start_bus(sdir)
            r, w = os.pipe()
            cr, cw = os.pipe()
            env, _source = self.child_env(sc, sdir, address, w, cr)
            if sc.opens_window and self.args.display == "session":
                self.warn_before_window()
            if sc.opens_window:
                self.windows_opened += 1
            started = time.monotonic()
            with open(os.path.join(sdir, "stdout.txt"), "w") as out, open(os.path.join(sdir, "stderr.txt"), "w") as err:
                child = self.spawn([sys.executable, CHILD, sc.id], env, pass_fds=(w, cr), stdout=out, stderr=err,
                                   cwd=sdir)
            os.close(w)
            os.close(cr)
            killed = self.collect(sc, child, r, cw, res, started)
            res.seconds = time.monotonic() - started
            self.classify(sc, child, res, killed, sdir)
        finally:
            if bus is not None:
                self.stop(bus)
            for p in list(self.procs):
                if p is not self.xvfb and p.poll() is not None:
                    self.procs.remove(p)
        left = scan_processes(self.run_id, exclude={self.xvfb.pid} if self.xvfb else set())
        res.scan = ("leftover scan after the scenario (/proc/*/environ, Xvfb excluded): "
                    + (", ".join(f"{pid} {cmd}" for pid, cmd in left) if left else "none"))
        if left:
            self.fail(res, "processes left behind: " + "; ".join(f"{pid} {cmd}" for pid, cmd in left))
            for pid, _cmd in left:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        return res

    def collect(self, sc, child, r, cw, res, started):
        """Read the child's events until it closes the pipe; kill it watchdog + kill_after seconds after
        the start. Returns the number of seconds after which it was killed, or None."""
        limit = sc.watchdog + sc.kill_after
        buf, killed = b"", None
        with open(os.path.join(self.scenario_dir(sc), "events.jsonl"), "w") as log:
            while True:
                remaining = started + limit - time.monotonic()
                if remaining <= 0:
                    killed = limit
                    self.stop(child)
                    break
                ready, _, _ = select.select([r], [], [], remaining)
                if not ready:
                    continue
                chunk = os.read(r, 65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    text = raw.decode(errors="replace")
                    log.write(text + "\n")
                    log.flush()                  # readable while the scenario runs, and after a crash
                    try:
                        event = json.loads(raw)
                    except ValueError:           # not JSON, or not UTF-8
                        event = None
                    if not valid_event(event):   # an unknown type, a missing key or a wrong value type
                        res.bad_events.append(text)
                        continue
                    res.events.append(event)
                    if event["t"] == "ready":
                        reply = self.real_bus_reply(event)
                        res.real_bus = reply
                        try:
                            os.write(cw, (json.dumps(reply) + "\n").encode())
                        except OSError:
                            pass
        os.close(r)
        os.close(cw)
        try:
            child.wait(max(1, started + limit - time.monotonic()))
        except subprocess.TimeoutExpired:
            killed = limit
            self.stop(child)
        return killed

    @staticmethod
    def fail(res, line):
        if res.verdict in (PASS, NOT_VERIFIED, None):
            res.verdict, res.reason = FAIL, line
        res.details.append(line)

    def classify(self, sc, child, res, killed, sdir):
        end = next((e for e in reversed(res.events) if e["t"] == "end"), None)
        steps = [e for e in res.events if e["t"] == "step"]
        last = f"last step {steps[-1]['n']} of {steps[-1]['of']} ({steps[-1]['name']})" if steps else "no step started"
        with open(os.path.join(sdir, "stderr.txt"), encoding="utf-8", errors="replace") as f:
            stderr = f.read().splitlines()
        bad = []
        for line in stderr:
            if line in sc.allowed_stderr:
                res.allowed_seen.append(line)
            elif (any(b in line for b in STDERR_BAD) or "warning" in line.lower()
                  or line.startswith(STDERR_BAD_PREFIXES)):
                bad.append(line)
        for e in res.events:
            if e["t"] == "log":
                res.details.append(e["text"])
        # A user close always reaches the driver's close-request handler, which logs it and ends the scenario
        # with an end event INCOMPLETE (driver.py); a process that ends without an end event is never one.
        res.user_closed = any(e["t"] == "log" and e["text"].startswith(USER_CLOSED) for e in res.events) or (
            end is not None and end["verdict"] == INCOMPLETE)
        end_lines = []
        if end is not None:
            end_lines.append(f"the end event said {end['verdict']}" + (f": {end['reason']}" if end["reason"] else ""))
            end_lines.extend(end["differences"][:3])
            if len(end["differences"]) > 3:
                end_lines.append(f"... and {len(end['differences']) - 3} more differences (see events.jsonl)")
            if "path" in end:
                end_lines.append(f"end event path: {end['path']}")
        if killed is not None:
            res.verdict = FAIL
            res.reason = (f"killed by the parent after {killed} s: the process did not exit after its end event; {last}"
                          if end is not None else f"killed by the parent after {killed} s: no result by then; {last}")
            res.details.extend(end_lines)
        elif end is not None and child.returncode:     # the process must also end cleanly after its result
            res.verdict = FAIL
            res.reason = (f"killed by {signal_name(-child.returncode)} after the end event" if child.returncode < 0
                          else f"exited with code {child.returncode} after the end event")
            res.details.extend(end_lines)
        elif end is not None:
            res.verdict, res.reason = end["verdict"], end["reason"]
            res.details.extend(end_lines[1:])          # the verdict and reason are already the result's own
        elif child.returncode is not None and child.returncode < 0:
            res.verdict = FAIL
            res.reason = f"killed by {signal_name(-child.returncode)}; {last}"
        else:
            res.verdict = FAIL
            res.reason = f"the scenario process ended (status {child.returncode}) without a result; {last}"
            tail = [line for line in stderr if line.strip()][-STDERR_TAIL:]
            res.details.append("stderr (last lines): " + " | ".join(tail) if tail else "stderr: empty")
        for text in res.bad_events:
            self.fail(res, f"malformed event line from the child: {text!r}")
        for line in bad:
            self.fail(res, f"unexpected stderr line: {line}")
        reply = getattr(res, "real_bus", None)
        if reply and reply.get("error"):
            self.fail(res, f"real-bus check failed: {reply['error']}")
        elif reply and reply["skipped"]:
            res.details.append(f"info: real-bus names not checked ({self.real_bus.why_none})")
        elif reply and reply["guicheck"]:
            self.fail(res, f"names with GuiCheck on the real bus while the scenario ran: {reply['guicheck']}")
        if not self.preflight_shown and any(e["t"] == "preflight" for e in res.events):
            self.preflight_shown = True
            res.preflight = [f"{'ok  ' if e['ok'] else 'FAIL'} {e['text']}" for e in res.events if e["t"] == "preflight"]
        else:
            res.preflight = [f"FAIL {e['text']}" for e in res.events if e["t"] == "preflight" and not e["ok"]]
        res.infos = [e["text"] for e in res.events if e["t"] == "info"]

    # ------------------------------------------------------------- the whole run
    def finish_checks(self):
        self.cleanup()                   # Xvfb too, once: stop() never signals a group a second time
        left = scan_processes(self.run_id)
        self.info.append(f"processes left behind after the run (scan of /proc/*/environ for {MARKER}={self.run_id}): "
                         + (", ".join(f"{pid} {cmd}" for pid, cmd in left) if left else "none"))
        if left:
            self.run_failures.append(f"processes left behind: {left}")
        gio = open(self.gio_log).read().splitlines() if os.path.exists(self.gio_log) else []
        self.info.append(f"gio stub log (a tripwire): {len(gio)} lines")
        if gio:
            self.run_failures.append(f"the gio stub was called: {gio[:5]}")
        gs = open(self.gsettings_log).read().splitlines() if os.path.exists(self.gsettings_log) else []
        others = [l for l in gs if l != GSETTINGS_ALLOWED]
        self.info.append(f"gsettings stub log: {len(gs)} calls, all '{GSETTINGS_ALLOWED}'" if not others
                         else f"gsettings stub log: unexpected calls {others[:5]}")
        if others:
            self.run_failures.append(f"unexpected gsettings calls: {others[:5]}")
        if self.real_bus.connection is not None:
            from gi.repository import GLib
            try:
                after = sorted(n for n in self.real_bus.names() if "FolderSymbols" in n)
            except GLib.Error as e:
                self.info.append(f"real session bus: cannot list the names after the run: {e} (informational)")
            else:
                self.info.append(f"real session bus: names with FolderSymbols after the run: {after or 'none'} "
                                 "(informational; your own window may come and go)")


def select_scenarios(args, scenarios):
    pool = [s for s in scenarios.values() if s.selftest == args.self_test and not s.manual]
    if not args.k:
        return pool
    terms = [t.strip() for t in ",".join(args.k).split(",") if t.strip()]
    chosen = []
    for s in scenarios.values():
        exact = s.id in terms
        if exact or (s in pool and any(t in s.id for t in terms)):
            chosen.append(s)
    return chosen


def expectation(sc, has_real_bus):
    """The self-test's expectation in this environment (Z8 cannot PASS without a real session bus)."""
    if not has_real_bus and sc.expect_no_real_bus is not None:
        return sc.expect_no_real_bus
    return sc.expect


def print_result(res, selftest, has_real_bus):
    sc = res.scenario
    expected = ""
    expect = expectation(sc, has_real_bus)
    if selftest and expect:
        res.as_expected = expected_ok(res, expect)
        expected = f"  [expected {expect[0]}: {'as expected' if res.as_expected else 'NOT AS EXPECTED'}]"
    say(f"{sc.id:<4} {res.verdict:<14} {res.seconds:5.1f} s  {sc.title}{expected}")
    if res.verdict in (NOT_VERIFIED, NOT_RUN):
        say(f"       reason: {res.reason}")
    elif res.verdict != PASS and res.reason:
        for line in res.reason.splitlines():
            say(f"       reason: {line}" if line == res.reason.splitlines()[0] else f"               {line}")
    for line in getattr(res, "preflight", []):
        say(f"       preflight: {line}")
    for line in res.details:
        say(f"       {line}")
    for line in getattr(res, "infos", []):
        say(f"       info: {line}")
    if getattr(res, "scan", None):
        say(f"       info: {res.scan}")
    for line in res.allowed_seen:
        say(f"       allowed stderr line: {line}")


def expected_ok(res, expect):
    """expect: (verdict, text or tuple of texts that must all appear[, text that must not appear])."""
    verdict, contains, *rest = expect
    text = (res.reason or "") + "\n" + "\n".join(res.details)
    wanted = contains if isinstance(contains, tuple) else (contains,)
    return (res.verdict == verdict and all(w in text for w in wanted)
            and not (rest and rest[0] and rest[0] in text))


def main(argv=None):
    p = argparse.ArgumentParser(prog="gui_check", description=__doc__.split("\n\n")[0])
    p.add_argument("-k", action="append", help="scenario ids or parts of ids, comma-separated")
    p.add_argument("--display", choices=DISPLAY_MODES, default=os.environ.get("GUI_CHECK_DISPLAY", "xvfb"),
                   help="where the windows open (default: $GUI_CHECK_DISPLAY, else xvfb); session warns and waits "
                   "5 s before each window")
    p.add_argument("--symbols", choices=("auto", "yaru", "fixture"), default="auto")
    p.add_argument("--self-test", action="store_true", help="run the harness's own self-tests (Z)")
    p.add_argument("--list", action="store_true", help="list the scenarios and exit")
    p.add_argument("--out", help="directory for the run directory (default: the system temp directory)")
    p.add_argument("--keep", action="store_true", help="keep the run directory even when everything passed")
    p.add_argument("--scan-leftovers", action="store_true",
                   help="list processes of any earlier run that are still alive, and exit (1 if there are)")
    args = p.parse_args(argv)
    if args.display not in DISPLAY_MODES:        # argparse does not check a default against choices
        p.error(f"--display / GUI_CHECK_DISPLAY: {args.display!r} is not one of {', '.join(DISPLAY_MODES)}")

    if args.scan_leftovers:
        left = scan_processes()
        for pid, cmd in left:
            say(f"{pid} {cmd}")
        say(f"processes with {MARKER}= in their environment: {len(left)}")
        return EXIT_FAIL if left else EXIT_OK
    scenarios = registry.load()
    if args.list:
        for s in scenarios.values():
            flags = [f for f, on in (("self-test", s.selftest), ("manual", s.manual), ("no window", not s.needs_display),
                                     ("needs Yaru", s.needs_yaru), ("real id", s.app_id == "real")) if on]
            say(f"{s.id:<4} {s.title}" + (f"  ({', '.join(flags)})" if flags else ""))
        return EXIT_OK
    chosen = select_scenarios(args, scenarios)
    if not chosen:
        say("gui_check: no scenario matches")
        return EXIT_SETUP

    run = Run(args)
    atexit.register(run.cleanup)

    def on_signal(signum, _frame):
        run.cleanup()
        say(f"gui_check: stopped by {signal.Signals(signum).name}; every process of this run was stopped; "
            f"kept {run.dir}")
        os._exit(130 if signum == signal.SIGINT else 143)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    started = time.monotonic()
    try:
        run.setup(chosen)
    except SetupError as e:
        run.cleanup()
        say(f"gui_check: {e}")
        return EXIT_SETUP
    say(f"gui_check: run directory {run.dir}")
    for line in run.info:
        say(f"info: {line}")
    run.info = []

    results, stopped = [], None
    has_real_bus = run.real_bus.connection is not None
    for sc in chosen:
        if stopped:
            res = Result(sc)
            res.verdict, res.reason = NOT_RUN, f"not run: {stopped}; ask before running windows again"
            results.append(res)
            print_result(res, args.self_test, has_real_bus)
            continue
        try:
            res = run.run_scenario(sc)
        except SetupError as e:                  # the scenario's private bus did not start
            run.cleanup()
            say(f"gui_check: {sc.id}: {e}")
            say(f"gui_check: the harness cannot run; kept {run.dir}")
            return EXIT_SETUP
        results.append(res)
        print_result(res, args.self_test, has_real_bus)
        if stops_further_windows(res):
            stopped = (f"the window of {sc.id} was closed by the user ({res.verdict})" if res.user_closed
                       else f"{sc.id} {res.verdict}")
    run.finish_checks()
    for line in run.info:
        say(f"info: {line}")
    say(f"info: windows opened: {run.windows_opened} ({'on your screen' if args.display == 'session' else 'not visible'})")
    counts = {v: sum(1 for r in results if r.verdict == v) for v in (PASS, FAIL, INCOMPLETE, NOT_VERIFIED, NOT_RUN)}
    for line in run.run_failures:
        say(f"RUN FAIL: {line}")
    if args.self_test:
        good = sum(1 for r in results if getattr(r, "as_expected", False))
        code = EXIT_OK if good == len(results) and not run.run_failures else EXIT_FAIL
        say(f"summary: self-test {good} of {len(results)} as expected; "
            + ", ".join(f"{n} {v}" for v, n in counts.items() if n) + f"; {time.monotonic() - started:.1f} s; exit {code}")
    else:
        if counts[FAIL] or counts[INCOMPLETE] or counts[NOT_RUN] or run.run_failures:
            code = EXIT_FAIL
        elif counts[NOT_VERIFIED]:
            code = EXIT_NOT_VERIFIED
        else:
            code = EXIT_OK
        say("summary: " + ", ".join(f"{n} {v}" for v, n in counts.items() if n or v == PASS)
            + f"; {time.monotonic() - started:.1f} s; exit {code}")
    if code == EXIT_OK and not args.keep:
        shutil.rmtree(run.dir, ignore_errors=True)
    else:
        say(f"gui_check: kept {run.dir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
