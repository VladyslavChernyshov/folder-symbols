"""Stubs for the four backend callables of FolderSymbolsApplication (no GTK). Each records its calls with
frozen copies of the arguments and returns a preset result or raises a preset exception; a stub that was
not given either fails the scenario on its first call."""
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

    def __call__(self, *args, **kwargs):
        self.calls.append((freeze(args), freeze(kwargs)))
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
