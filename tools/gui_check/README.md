# GUI harness

`tools/gui_check/` starts the real Folder Symbols window (`FolderSymbolsApplication`) with stub backends, drives
it from a script and checks states, texts and dialogs. It is a local tool: it is **not** part of `make check`
and CI does not run it. Run it after changing anything under `folder_symbols/gui/`.

```bash
make gui-check                                   # every scenario, on the harness's own Xvfb
make gui-check GUI_CHECK_ARGS="-k A5"            # one scenario
python3 tools/gui_check --self-test              # the harness's own tests (Z1-Z32)
python3 tools/gui_check --list                   # scenarios and their flags
```

Needs `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1`, `xvfb` and `dbus-daemon` (`/usr/bin:/bin` is searched for both).

## What it is and what it is not

It checks what the window shows and does when the backend returns given results: texts, tooltips,
sensitivity, dialogs, selection, the preview file, stderr, exit status of second launches.

It does **not**:

- call the real `gio`, read or write a real manifest, or talk to a running Nautilus or a running window;
- check how the window looks (no screenshots, no pixels);
- exercise real pointer or keyboard input (see [Input emulation](#input-emulation));
- test the CLI or the rendering code (that is `make check`).

## Isolation

Each scenario runs in its own process (`child.py`) with an environment built from an allowlist:

- a fresh `HOME` and XDG directories under the run directory, with the manifest fixture written by the scenario;
- its own private `dbus-daemon` (no service directories, so nothing can be autostarted; socket under the run
  directory) and a random test application id, `...FolderSymbols.GuiCheck<random>`;
- `gio` and `gsettings` stubs first in `PATH`. The `gio` stub only logs the call and exits 99; any call is a
  run-level failure. The `gsettings` stub answers only `get org.gnome.desktop.interface icon-theme`; any other
  call is a run-level failure;
- `GSETTINGS_BACKEND=keyfile` with `color-scheme='default'`, so the style is light;
- software rendering (`GSK_RENDERER=cairo`, GL and Vulkan disabled), no accessibility bus.

Every process the harness starts dies with its parent (`pdeath_exec.py`). After each scenario and at the end,
`/proc/*/environ` is scanned for processes left behind (`--scan-leftovers` does the same for earlier runs).
Before a scenario starts, a preflight checks the display, the application id, that the private bus is not the
real one (when the harness has a real session bus to compare with), that the package, `HOME`, the manifest and `TMPDIR` are the harness's own, and that the style is
light; a failed check is a FAIL.

**Symbols.** With `--symbols auto` (default) the real Yaru symbols are used when `YARU_SYMBOLS_DIR` (or the
package default) has any; otherwise a small generated set is used. Scenarios with `needs_yaru` (D4, D6) are
NOT VERIFIED with the generated set. `--symbols yaru` fails setup without real symbols; `--symbols fixture`
always uses the generated set.

## Displays

- `--display xvfb` (default, or `$GUI_CHECK_DISPLAY`): the harness starts its own Xvfb (1280x1024, no window
  manager). Nothing appears on your screen; no warning, no notification, all scenarios run.
- `--display session`: windows open on **your** screen. Rules:
  - the run has the A scenarios only. B-H are left out unless their **exact id** is given with `-k`
    (`-k B1`, not `-k B`; `-k B` prints "not selected in session mode, use -k <exact id>");
  - `in_session_run=False` marks a scenario as left out of session runs (set for B-H);
  - **one** warning per run, before the first window: a line in the terminal and a `notify-send`
    notification ("Opening N windows for a visual check, about T seconds in total, ..."), then one wait of 5 s.
    No further warning or wait before later windows;
  - when the run ends, one "Visual check finished, you can use the keyboard and mouse again" line and
    notification (only if a warning was given);
  - if the window is closed by the user, the remaining scenarios are NOT RUN (see below) and no window opens
    again until you ask.

## Verdicts and exit codes

| Verdict | Meaning |
|---|---|
| PASS | every step ran, every check held, nothing was left unchecked |
| FAIL | a check failed, a step was missing or out of order, a timeout, an unexpected stderr line, a crash or a kill, a dialog left open, a malformed event |
| INCOMPLETE | the window was closed by someone other than the driver: not a bug in the code under test; it lists the steps that ran and did not |
| NOT VERIFIED | a part could not be checked here (no real Yaru, no real session bus, running as root for B5, `d.not_verified(...)`); never PASS |
| NOT RUN | not started because an earlier scenario was INCOMPLETE or its window was closed by the user |

Precedence inside one scenario: FAIL wins over NOT VERIFIED (a failed check is reported, the unverified part
only if everything else held). A process that ends without an end event is a FAIL, never "closed by the user";
a user close always shows up as the driver's own `WINDOW CLOSED BY THE USER at step N of M` and an INCOMPLETE
end event.

| Exit | When |
|---|---|
| 0 | every scenario PASS (the run directory is then deleted unless `--keep`) |
| 1 | any FAIL, INCOMPLETE or NOT RUN, or a run-level failure (leftover processes, a `gio` call, an unexpected `gsettings` call) |
| 2 | the harness cannot run (setup: no Xvfb, no `dbus-daemon`, unsafe path, no scenario matches) |
| 3 | at least one NOT VERIFIED and no FAIL, INCOMPLETE or NOT RUN |

With `--self-test`: 0 when every self-test gave its expected verdict, else 1. Ctrl-C and SIGTERM stop every
process of the run and exit 130 and 143.

## Scenario fields

A scenario is a function registered with `@scenario(id, title, steps=(...), **fields)` in `registry.py`. The
parent reads only the metadata; the function runs in the child inside the GLib main loop.

| Field | Meaning |
|---|---|
| `prepare(ctx)` | builds folders and manifest entries in the sandbox `HOME` (no GTK) and returns the launch paths |
| `steps` | step names in order; `d.step(name)` must be called in this order and all of them must run |
| `needs_display` | `False`: a process-level scenario with no window (`ProcessDriver`) |
| `needs_yaru` | NOT VERIFIED when only the generated symbols are available |
| `not_verified_if(symbols_dir, source)` | a reason text makes it NOT VERIFIED before any window opens |
| `needs_real_bus` | NOT VERIFIED when the harness has no real session bus to compare with |
| `force_symbols="fixture"` | always evaluated as if Yaru were absent |
| `symbols_dir` | `"missing"` or `"empty"`: `YARU_SYMBOLS_DIR` is such a directory |
| `app_id` | `"test"` (default) or `"real"` (the real id, private bus only) |
| `watchdog`, `kill_after` | GLib watchdog in seconds (default 30: "TIMEOUT at step N"), and seconds after it at which the parent kills the child (default 10) |
| `allowed_stderr` | exact stderr lines the scenario may print |
| `stderr_lines(home, symbols_dir)` | exact stderr lines it **must** print, each once and in this order; a missing, repeated or reordered line is a FAIL; allowed for this scenario only |
| `stderr_tracebacks` | final exception lines of tracebacks it must print, each block once and in this order (an unexpected error the window catches and prints) |
| `in_session_run` | `False`: left out of `--display session` runs unless its exact id is given |
| `manual` | needs a person; runs only when its exact id is given with `-k` (Z5) |
| `selftest`, `expect`, `expect_no_real_bus`, `on_start` | self-tests: the verdict and text they must give (`expect_no_real_bus` when there is no real session bus, Z8), and a hook before `app.run()` |

Stderr is checked for every scenario: a line that contains `Traceback`, `-CRITICAL`, `-WARNING`, `-ERROR` or
`warning` (any case), or starts with `folder-symbols:` or `folder-symbols-gui:`, is a FAIL unless the scenario
declared it with one of the three fields above.

`restore_permissions(top)` in `__main__.py` is **not** a scenario field but a harness function. After each
scenario (and at the end) it gives the owner read and write access (and search on directories) to everything
under the scenario directory that lacks it, so the run directory can always be read and removed. It is needed
by B5, whose `ctx.make_unreadable(path)` does `chmod 0` (B5 is NOT VERIFIED when running as root, where this
does not block reading).

**The icon theme stub.** The `gsettings` stub reports the content of the file `$GUI_CHECK_ICON_THEME_FILE`
(a file in the scenario directory) as the icon theme, or `Yaru` while the file does not exist.
`ctx.icon_theme(name)` writes it; `ui.set_system_theme(d, name)` writes it and then sets Gtk.Settings'
`gtk-icon-theme-name`, which is the notification the window reacts to (FAIL if it was not emitted).

## Input emulation

GTK 4 has no public way to inject real pointer or key events, so input is emulated at **signal level**
(`ui.py`):

- a click on a gallery cell: the grid's `list.select-item` action;
- a click on an accent swatch: the app's capture-phase `Gtk.GestureClick` gets `pressed` then `released`, then
  GTK's check-button rule is applied;
- a click on the "Follow system accent" row: the row's `Gtk.GestureClick` gets `pressed` and `released` at the
  centre of the label or the switch;
- the switch: `Gtk.Switch.activate()`; the category split button: `Adw.SplitButton.activate()`;
- buttons: the `clicked` signal on a sensitive button (an insensitive one is a FAIL: GTK delivers no click to it);
- arrow keys: the window's `move-focus` signal.

What this does **not** exercise: GTK's own gesture recognition and hit testing, real key bindings and
focus traversal by real keys, the switch's own click gesture, drag, hover, scrolling by wheel, and the real
timing of events. A scenario that passes says the app's handlers behave correctly when called; not that a user's
click reaches them.

## Dialogs and closing

- Every dialog presented on a window is recorded in `d.dialogs` as `(step, heading)` (from `notify::visible-dialog`).
  `ui.visible_dialog`, `check_dialog`, `answer_dialog`, `dismiss_dialog` and `no_dialog` find, check and close
  them. Answering is a `clicked` on the response's button, found by a widget-tree search.
- **A dialog still open when the scenario body ends is a FAIL** ("a dialog was left open", every scenario must
  answer or close the dialogs it opens).
- The driver's own closing of windows is not the user's. Any other `close-request` is a user close:
  INCOMPLETE. Where the application itself closes its window (after a full success, or "Close Window"), wrap the
  action in `with d.allow_app_close():`; the close is counted in `d.app_closes` and is not a user close. After the
  block, a close is the user's again (Z26).
- Every scenario has the GLib watchdog; a wait that expires gives "timeout waiting for ..." and the watchdog gives
  "TIMEOUT at step N: waiting for ...". The parent kills a child that outlives watchdog + `kill_after`.

## Helpers for scenario authors

- `Recorder` (the base of both drivers): `step`, `check(label, actual, expected)` (records, does not stop),
  `require(condition, label)` (stops with FAIL), `info(text)`, and `not_verified(reason)`, which marks a part
  that could not be checked: the verdict becomes NOT VERIFIED with the reason unless a check failed.
- `Stub` / `Backend` (`stubs.py`): the four backend callables (`apply`, `reset`, `plan_cleanup`, `run_cleanup`).
  Each records its calls as frozen copies, runs `Stub.during(*args, **kwargs)` (after the record, before the
  return: check the window's busy state, or change the manifest as the real call would), then returns
  `returns` or raises `raises`; a stub with neither fails the scenario on its first call.
  Result builders: `folder_results(dirs, failed)`, `cleanup_plan(stale, unknown, skipped, total, warnings)`,
  `cleanup_result(removed, kept)`.
- `ui.Toasts(d)` (used as `with ui.Toasts(d) as toasts:`): `Adw.ToastOverlay` has no getter for its toasts, so
  while the block runs `Adw.ToastOverlay.add_toast` is wrapped in the scenario process and records every title
  (`toasts.titles`). `toasts.dismiss_all()` dismisses them, because a new toast queues behind a shown one.
- `ui.wait_quietly`: a wait whose own timeout only returns, so a broken behaviour fails by a check, not by a
  stack of timeouts.

## FALLBACK lines

Some state has no public getter, and the harness reads it by a widget-tree search: the buttons of an
`Adw.AlertDialog` (`dialog_state`, `answer_dialog`), the Legal section of `Adw.AboutDialog` (H1), the toast
titles (`Toasts`). Where an action may be missing (`list.select-item`, the `move-focus` signal) a fallback
call is used. Each use is printed as an `info: FALLBACK: ...` line. These searches and fallbacks have only been
run on GTK 4.22 and libadwaita 1.9; on another version they may fail or find nothing, and that says something
about the harness, not necessarily about the app. The harness is written against the public API of GTK 4.14 and
libadwaita 1.5, but this has not been checked by running it on those versions or against their GIR files.

## Scenarios

| Id | What it pins |
|---|---|
| A1 | start without paths: the welcome page |
| A2, A2b | one folder, without and with a manifest entry |
| A3 | three folders and one file, one recorded |
| A4 | only bad paths: the error, exit 1, no window (process-level) |
| A5 | a second launch with another folder updates the same window (needs a query/category pair that narrows the symbols, else NOT VERIFIED) |
| A6 | a second launch with only bad paths leaves the open window alone |
| A7 | the welcome page gives way to the main layout at the first selection |
| B1 | a recorded symbol and pinned accent: selected, scrolled to, switch off |
| B2 | a recorded symbol that follows the system accent: switch on, system swatch |
| B3 | folders with different symbols, or one without a record: nothing selected, plain preview |
| B4, B4b, B5 | the recorded symbol is not in the gallery / the manifest is damaged / unreadable (NOT VERIFIED as root): as without a record, one stderr line |
| C1 | search filters, no match shows the placeholder, clearing restores the list |
| C2 | categories: the split button's reset, tooltip, All categories, menu height cap |
| C3 | a click selects and previews; a second click on the selected symbol keeps it |
| C4 | keyboard: focus starts on the selected cell; arrow keys switch the accent |
| C5, C5b | the symbols directory is missing / empty: the problem page and the install hint |
| C6 | the grid's column count does not decrease as the window grows |
| D1 | a click on any swatch turns the switch off, moves the ring, recolours the preview |
| D2 | see below |
| D3 | system icon theme not Yaru: the row is insensitive, with its tooltip |
| D4 | the 13th swatch (MATE) only when the recorded or system accent is mate (needs Yaru) |
| D5, D5b | the system accent changes while open: a following folder moves, a pinned one keeps its swatch |
| D6 | light/dark changes while open: preview and swatches follow (needs Yaru) |
| E1 | Apply insensitive without a symbol, with the reason; the two-line tooltip otherwise |
| E2 | Apply calls the backend once with the frozen choice; a full success closes the window |
| E3 | a partial failure: the dialog, OK keeps the window, recount, Close Window |
| E4 | every folder failed: the dialog without Close Window |
| E5, E6, E7 | ManifestError and ApplyError / RecordError / an unexpected error (traceback on stderr, window works on) |
| E8 | while Apply runs: both buttons and Clean up blocked, a second click does nothing |
| E9 | one folder pinned, one following the system: one call, one recipe for all |
| F1 | the Reset label and tooltip, insensitive without records |
| F2, F2b | Reset of one folder (no confirmation) / of two (confirmation, Cancel default, Reset destructive) |
| F3 | Reset outcomes: partial, all failed, ManifestError, RecordError, unexpected error |
| F4 | after an incomplete Reset: recount, selection and accent kept |
| F5 | at the minimum width, "Reset 2 of 3" and Apply fit side by side |
| G1 | the Clean up menu item on the welcome page and the main page, blocked while it runs |
| G2 | nothing to clean up: every text variant |
| G3 | entries to remove: the question, at most 10 listed, Cancel default, Remove destructive |
| G4 | Remove: the toasts, "Nothing was removed", the Reset count recalculated |
| G5 | Clean up errors, with the traceback |
| G6 | warnings about unusable manifest entries are printed once per window |
| H1 | About: name, version, developer, MIT, links, Legal section "Yaru artwork" |
| Z1-Z4, Z6-Z16 | the harness's own checks: NOT VERIFIED, watchdog, user close (also before the scenario starts, Z12, Z15), killed process, iteration counting, own timeout, real id on the private bus (Z8), kill or non-zero exit after the end event, application diagnostics on stderr, malformed events, exit without a result |
| Z17-Z22 | warning wording and session selection, `stderr_lines`, the icon theme file, `restore_permissions` |
| Z23-Z32 | dialog left open, dialog helpers, `allow_app_close`, `not_verified`, `stderr_tracebacks`, `Stub.during` and the builders |
| Z5 | manual: you close the window by hand (exact id only) |

### D2

D2 ("the switch selects the system swatch; a click on the label toggles it") ends with a click on the **centre
of the switch** through the row's click gesture. What it pins: the row's own handler
(`_on_row_click` in `gui/accents.py`) leaves a click that lands on the switch to the switch and does not
toggle it itself, so the switch stays on. What it does not pin: that a real click on the switch toggles it, since
the switch's own gesture is not emulated (see [Input emulation](#input-emulation)). A click on the label does
toggle it (steps "label click" and "label click again").

## Adding a scenario

1. Pick the module by area (`scenarios_a.py` ... `scenarios_h.py`; `scenarios_z.py` is for self-tests). B-H
   modules start with `scenario = functools.partial(registry.scenario, in_session_run=False)`.
2. Write `prepare(ctx)` if it needs folders or manifest entries (`ctx.folder`, `ctx.file`, `ctx.symbol`,
   `ctx.record`, `ctx.icon_theme`, `ctx.manifest_text`, `ctx.make_unreadable`); it returns the launch paths.
3. Decorate the body: `@scenario("X1", "title", prepare=..., steps=("window shown", ...))`. Texts expected from
   the app are written out as literals, so a changed text in the app shows up as a difference.
4. In the body call `d.step(...)` in order, `d.wait_window()`, then `ui.*` helpers and `d.check(label, actual,
   expected)`. Answer or close every dialog; use `d.allow_app_close()` where the app closes its window.
5. If it prints on stderr on purpose, declare it (`stderr_lines`, `stderr_tracebacks` or `allowed_stderr`).
6. Register the module in `registry.load()` if it is new, and run `python3 tools/gui_check -k X1`, then
   `make gui-check`. Prove that the scenario can fail by breaking the app's behaviour on a copy of the tree and
   running it there; do not break the working tree.
7. A scenario that tests a harness helper is a self-test (`selftest=True`, `expect=(verdict, text)`).
