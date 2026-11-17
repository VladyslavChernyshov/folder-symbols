"""The scenario registry of the GUI harness (no GTK): what each scenario needs and, for the harness's own
self-tests, which verdict it must give. Scenario modules register their functions with @scenario; the
parent process reads only this metadata, the child process runs the functions."""
import dataclasses
from typing import Callable, Optional

PASS, FAIL, INCOMPLETE, NOT_VERIFIED = "PASS", "FAIL", "INCOMPLETE", "NOT VERIFIED"


@dataclasses.dataclass
class Scenario:
    id: str
    title: str
    steps: tuple                      # step names, in order (M = len(steps))
    body: Callable                    # body(d): run inside the GLib main loop (or with a ProcessDriver)
    prepare: Optional[Callable] = None    # prepare(ctx) -> launch paths; folders and manifest, no GTK
    needs_display: bool = True        # False: a process-level scenario, no window and no display
    needs_yaru: bool = False          # True: NOT VERIFIED when only the fixture symbols are available
    selftest: bool = False            # a check of the harness itself (--self-test)
    manual: bool = False              # needs a person (only run when its id is given exactly with -k)
    watchdog: int = 30                # seconds, the scenario's GLib watchdog
    kill_after: int = 10              # seconds after the watchdog at which the parent kills the child
    app_id: str = "test"              # "test": the random test id; "real": the real id (private bus only)
    needs_real_bus: bool = False      # NOT VERIFIED when the harness process has no session bus to compare with
    force_symbols: Optional[str] = None   # "fixture": always evaluated as if Yaru were absent
    allowed_stderr: tuple = ()        # exact full stderr lines this scenario may print (with reasons)
    # self-tests: (verdict, text or tuple of texts the reason and details must contain[, text they must not])
    expect: Optional[tuple] = None
    expect_no_real_bus: Optional[tuple] = None   # self-tests: expect when the harness has no real session bus
    on_start: Optional[Callable] = None   # self-tests: on_start(driver) before app.run(), ahead of the body
    # not_verified_if(symbols_dir, source) -> reason or None: evaluated by the parent before the scenario
    # starts; a reason makes it NOT VERIFIED without opening a window
    not_verified_if: Optional[Callable] = None
    # stderr_lines(home, symbols_dir) -> the exact stderr lines this scenario must print, each once and in this
    # order (computed by the parent from the scenario's HOME and symbols directory); allowed for this scenario
    # only, and a missing, repeated or reordered line is a FAIL
    stderr_lines: Optional[Callable] = None
    symbols_dir: Optional[str] = None     # "missing" or "empty": YARU_SYMBOLS_DIR is such a directory instead
    # False: left out of a --display session run unless its id is given exactly with -k (it still opens a
    # window and is counted in the warning then); always run on the harness's Xvfb
    in_session_run: bool = True
    # the final exception lines of the tracebacks this scenario must print to stderr, each block once and in
    # this order (an unexpected error that the window catches and prints); allowed for this scenario only
    stderr_tracebacks: tuple = ()

    @property
    def opens_window(self):
        return self.needs_display


SCENARIOS = {}


def scenario(id, title, steps, **kwargs):
    def register(body):
        if id in SCENARIOS:
            raise ValueError(f"duplicate scenario id {id}")
        SCENARIOS[id] = Scenario(id=id, title=title, steps=tuple(steps), body=body, **kwargs)
        return body
    return register


def load():
    """All scenarios, in registration order (importing the modules registers them)."""
    import scenarios_a, scenarios_b, scenarios_c, scenarios_d  # noqa: F401  (on sys.path)
    import scenarios_e, scenarios_f, scenarios_g, scenarios_h, scenarios_z  # noqa: F401
    return dict(SCENARIOS)


class Fail(Exception):
    """The scenario cannot go on: FAIL with this reason."""


class Incomplete(Exception):
    """The window was closed by someone other than the driver: INCOMPLETE."""


class Recorder:
    """Steps and checks of one scenario, sent to the parent as events. The base of both drivers (the GTK
    Driver and the ProcessDriver); no GTK here."""

    def __init__(self, scenario, emit, ctx):
        self.scenario, self.emit, self.ctx = scenario, emit, ctx
        self.step_no = 0
        self.differences = []
        self.unverified = []              # parts the scenario could not check (not_verified)

    @property
    def total_steps(self):
        return len(self.scenario.steps)

    def step(self, name):
        steps = self.scenario.steps
        expected = steps[self.step_no] if self.step_no < len(steps) else None
        if name != expected:
            raise Fail(f"step {name!r} out of order (expected {expected!r})")
        self.step_no += 1
        self.emit("step", n=self.step_no, of=len(steps), name=name)

    def check(self, label, actual, expected):
        """Compare and record; a difference does not stop the scenario. True when equal."""
        ok = actual == expected
        self.emit("check", step=self.step_no, label=label, ok=ok, expected=repr(expected), actual=repr(actual))
        if not ok:
            self.differences.append(f"step {self.step_no}: {label}: expected {expected!r}, got {actual!r}")
        return ok

    def require(self, condition, label):
        """Stop the scenario with FAIL unless condition holds."""
        if not condition:
            raise Fail(f"step {self.step_no}: {label}")

    def info(self, text):
        self.emit("info", text=text)

    def not_verified(self, reason):
        """A part of the scenario that cannot be checked here: the verdict is NOT VERIFIED with this reason
        unless a check failed (FAIL wins), never PASS."""
        self.unverified.append(reason)
        self.info(f"NOT VERIFIED: {reason}")

    def steps_summary(self):
        ran = list(self.scenario.steps[:self.step_no])
        return ran, list(self.scenario.steps[self.step_no:])

    def verdict_after_body(self):
        if self.step_no < self.total_steps:
            _ran, missing = self.steps_summary()
            raise Fail(f"only {self.step_no} of {self.total_steps} steps ran (missing: {', '.join(missing)})")
        if self.differences:
            return FAIL, f"{len(self.differences)} difference(s)"
        if self.unverified:
            return NOT_VERIFIED, "; ".join(self.unverified)
        return PASS, None
