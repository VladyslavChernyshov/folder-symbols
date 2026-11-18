"""The window's real backend (folder_symbols/gui/window.py: Backend), checked without GTK: window.py is only
read as text with ast, never imported. The GUI harness always injects stubs that accept any arguments, so these
tests are what pins that Backend's defaults are the real functions and that the window's calls still fit them."""
import ast, importlib, inspect, os

from folder_symbols import apply, store

WINDOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "folder_symbols", "gui", "window.py")
REAL = {"apply_func": apply.apply_folders, "reset_func": apply.reset_folders,
        "plan_cleanup_func": store.plan_cleanup, "run_cleanup_func": store.run_cleanup}


def _tree():
    with open(WINDOW, encoding="utf-8") as f:
        return ast.parse(f.read())


def _is_self_attr(node, attr):
    return (isinstance(node, ast.Attribute) and node.attr == attr and isinstance(node.value, ast.Name)
            and node.value.id == "self")


def _backend_field(node):
    """The field name of a `self._backend.<field>` expression, else None."""
    if isinstance(node, ast.Attribute) and _is_self_attr(node.value, "_backend"):
        return node.attr
    return None


def test_backend_defaults_are_the_real_functions():
    tree = _tree()
    imported = {alias.asname or alias.name: (node.module, alias.name)
                for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
    [cls] = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Backend"]
    defaults = {}
    for field in cls.body:
        if isinstance(field, ast.AnnAssign):
            assert isinstance(field.value, ast.Name), ast.unparse(field)
            module, name = imported[field.value.id]           # only GTK-free modules are imported here
            assert module.startswith("folder_symbols.") and not module.startswith("folder_symbols.gui")
            defaults[field.target.id] = getattr(importlib.import_module(module), name)
    assert defaults == REAL


def test_the_windows_backend_calls_bind_to_the_real_signatures():
    tree = _tree()
    calls, passed = {}, set()               # passed: ids of uncalled references given to self._busy_call
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        field = _backend_field(node.func)
        if field is not None:
            assert not any(isinstance(a, ast.Starred) for a in node.args), ast.unparse(node)
            assert all(k.arg is not None for k in node.keywords), ast.unparse(node)
            calls.setdefault(field, []).append((len(node.args), [k.arg for k in node.keywords]))
        elif _is_self_attr(node.func, "_busy_call") and node.args and _backend_field(node.args[0]):
            passed.add(id(node.args[0]))
            calls.setdefault(_backend_field(node.args[0]), []).append((0, []))   # _busy_call runs call()
    called_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        if _backend_field(node) is not None:
            assert id(node) in called_funcs or id(node) in passed, f"unchecked use: {ast.unparse(node)}"
    assert set(calls) == set(REAL)
    for field, shapes in calls.items():
        sig = inspect.signature(REAL[field])
        for n_args, keywords in shapes:
            sig.bind(*[None] * n_args, **dict.fromkeys(keywords))    # TypeError: the call does not fit
