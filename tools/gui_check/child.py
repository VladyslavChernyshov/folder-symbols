"""child.py SCENARIO_ID: run one scenario of the GUI harness in this process and report it to the parent.

Started by the parent (__main__.py) under pdeath_exec.py, with an environment built from an allowlist
(sandbox HOME, private bus, the harness's display). Events go to the parent as JSON lines on the file
descriptor $GUI_CHECK_RESULT_FD, one per step and check, so a killed child keeps its partial result. The
parent's replies (the real-bus check) arrive on $GUI_CHECK_CONTROL_FD. GTK is imported only for scenarios
that open a window (driver.py)."""
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT]

import fixtures                        # noqa: E402
import registry                        # noqa: E402
from registry import FAIL, Fail, Recorder   # noqa: E402

PDEATH = os.path.join(HERE, "pdeath_exec.py")


def make_emit(fd):
    def emit(kind, **fields):
        os.write(fd, (json.dumps({"t": kind, **fields}) + "\n").encode())
    return emit


class ProcessDriver(Recorder):
    """For scenarios without a window: runs the real folder-symbols-gui as a process."""

    def __init__(self, scenario, emit, ctx):
        super().__init__(scenario, emit, ctx)
        self.root = os.environ["GUI_CHECK_ROOT"]

    def run_gui(self, args, env_changes, timeout=20):
        """(exit status, stdout, stderr) of folder-symbols-gui ARGS with this environment changed
        (a value None removes the variable)."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("GUI_CHECK_") or k == "GUI_CHECK_RUN"}
        for key, value in env_changes.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        wrapper = os.path.join(self.root, "folder-symbols-gui")
        done = subprocess.run([sys.executable, PDEATH, str(os.getpid()), sys.executable, wrapper, *args],
                              env=env, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr

    def preflight(self):
        problems = []
        run_dir = os.path.realpath(os.environ["GUI_CHECK_RUN_DIR"]) + os.sep
        import folder_symbols
        from folder_symbols import store
        package = os.path.dirname(os.path.realpath(folder_symbols.__file__))
        for ok, text in (
                (package == os.path.realpath(os.path.join(self.root, "folder_symbols")),
                 f"package: {package} (expected the harness's own tree {self.root})"),
                (os.path.realpath(os.path.expanduser("~")).startswith(run_dir),
                 f"HOME: {os.path.expanduser('~')} (under the run directory)"),
                (os.path.realpath(store.manifest_path()).startswith(run_dir),
                 f"manifest: {store.manifest_path()} (under the run directory)")):
            self.emit("preflight", ok=ok, text=text)
            if not ok:
                problems.append(text)
        if problems:
            raise Fail("preflight: " + "; ".join(problems))

    def run(self):
        try:
            self.preflight()
            self.scenario.body(self)
            verdict, reason = self.verdict_after_body()
        except Fail as e:
            verdict, reason = FAIL, str(e)
        except Exception:
            verdict, reason = FAIL, "exception in the scenario:\n" + traceback.format_exc()
        self.emit("end", verdict=verdict, reason=reason, differences=self.differences,
                  steps_ran=self.step_no, steps=self.total_steps)


def main(argv):
    emit = make_emit(int(os.environ["GUI_CHECK_RESULT_FD"]))
    control = os.environ.get("GUI_CHECK_CONTROL_FD")
    scenario = registry.load()[argv[1]]
    ctx = fixtures.Context(os.environ["HOME"], os.environ["YARU_SYMBOLS_DIR"],
                           os.environ["GUI_CHECK_SYMBOLS_SOURCE"])
    try:
        paths = scenario.prepare(ctx) if scenario.prepare else []
    except Exception:
        emit("end", verdict=FAIL, reason="exception in prepare:\n" + traceback.format_exc(),
             differences=[], steps_ran=0, steps=len(scenario.steps))
        return 0
    if not scenario.needs_display:
        ProcessDriver(scenario, emit, ctx).run()
        return 0
    import driver
    driver.run(scenario, emit, ctx, paths, int(control) if control else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
