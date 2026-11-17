"""Stubs for the four backend callables of FolderSymbolsApplication (no GTK). Each records its calls with
frozen copies of the arguments, runs its `during` hook (what a scenario checks or changes while the call
runs: the window's busy state, or the manifest as the real call would change it), then returns a preset
result or raises a preset exception; a stub that was given neither fails the scenario on its first call.
The builders make the results of the real functions (apply.FolderResult, store.CleanupPlan,
store.CleanupResult); the package is imported only when they are called."""
import copy

_UNSET = object()


def freeze(value):
    """A deep, immutable copy: lists and tuples become tuples, dicts sorted tuples of pairs, sets
    frozensets; anything else is deep-copied, so a later change by the caller cannot alter the record."""
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, freeze(v)) for k, v in value.items()))
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(v) for v in value)
    return copy.deepcopy(value)


class Stub:
    def __init__(self, name):
        self.name = name
        self.calls = []                   # (args, kwargs), frozen
        self.returns = _UNSET
        self.raises = None
        self.during = None                # during(*args, **kwargs), after the record, before return/raise

    def __call__(self, *args, **kwargs):
        self.calls.append((freeze(args), freeze(kwargs)))
        if self.during is not None:
            self.during(*args, **kwargs)
        if self.raises is not None:
            raise self.raises
        if self.returns is _UNSET:
            raise AssertionError(f"gui_check: unexpected call of the {self.name} stub")
        return self.returns


class Backend:
    """apply, reset, plan_cleanup, run_cleanup; kwargs() gives FolderSymbolsApplication's arguments."""
    NAMES = ("apply", "reset", "plan_cleanup", "run_cleanup")

    def __init__(self):
        for name in self.NAMES:
            setattr(self, name, Stub(name))

    def kwargs(self):
        return {"apply_func": self.apply, "reset_func": self.reset,
                "plan_cleanup_func": self.plan_cleanup, "run_cleanup_func": self.run_cleanup}

    def calls(self):
        """{name: number of calls} of every stub."""
        return {name: len(getattr(self, name).calls) for name in self.NAMES}


# ------------------------------------------------------------- results of the real functions
def folder_results(dirs, failed=None):
    """[apply.FolderResult] for dirs in this order: the folders in failed ({path: reason}) failed with that
    message, the others got "icon set"."""
    from folder_symbols.apply import FolderResult
    failed = failed or {}
    return [FolderResult(d, False, failed[d]) if d in failed else FolderResult(d, True, "icon set") for d in dirs]


def cleanup_plan(stale=(), unknown=(), skipped=0, total=None, warnings=()):
    """A store.CleanupPlan: stale and unknown are folder paths (unknown ones with a PermissionError), total
    defaults to the number of entries they make."""
    from folder_symbols import store
    entry = lambda path: store.Entry(path, store.Recipe("star", "red"))
    return store.CleanupPlan(tuple(entry(p) for p in stale),
                             tuple((entry(p), PermissionError(13, "Permission denied", p)) for p in unknown),
                             skipped, len(stale) + len(unknown) + skipped if total is None else total,
                             tuple(warnings))


def cleanup_result(removed=(), kept=()):
    from folder_symbols import store
    return store.CleanupResult(tuple(removed), tuple(kept))
