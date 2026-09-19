"""Report names a module USES but never binds - the class of bug that shows up
at runtime as NameError. Conservative: over-counts bindings, so anything it
reports is a real hole."""
import ast, os, sys, builtins

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "__version__", "__build__"}

def bound_names(tree):
    out = set()
    for x in ast.walk(tree):
        if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
            out.add(x.id)
        elif isinstance(x, (ast.Import, ast.ImportFrom)):
            for a in x.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(x.name)
            a = getattr(x, "args", None)
            if a:
                for q in list(a.args) + list(a.kwonlyargs) + list(getattr(a, "posonlyargs", [])):
                    out.add(q.arg)
                if a.vararg: out.add(a.vararg.arg)
                if a.kwarg: out.add(a.kwarg.arg)
        elif isinstance(x, ast.Lambda):
            a = x.args
            for q in list(a.args) + list(a.kwonlyargs) + list(getattr(a, "posonlyargs", [])):
                out.add(q.arg)
            if a.vararg: out.add(a.vararg.arg)
            if a.kwarg: out.add(a.kwarg.arg)
        elif isinstance(x, ast.ExceptHandler) and x.name:
            out.add(x.name)
        elif isinstance(x, (ast.Global, ast.Nonlocal)):
            out |= set(x.names)
        elif isinstance(x, ast.arg):
            out.add(x.arg)
    return out

def used_names(tree):
    return {x.id for x in ast.walk(tree) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}

def star_exports(path):
    if not os.path.isfile(path): return set()
    tree = ast.parse(open(path, encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in n.targets):
            try: return set(ast.literal_eval(n.value))
            except Exception: return set()
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names: out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)): out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name): out.add(x.id)
    return out

root = sys.argv[1] if len(sys.argv) > 1 else "."
problems = {}
for pkg in sorted(os.listdir(root)):
    pdir = os.path.join(root, pkg)
    if not os.path.isdir(pdir) or pkg in (".git", "tools", "archive", "__pycache__", "PanelScripts", "templates"):
        continue
    shared = star_exports(os.path.join(pdir, "_shared.py"))
    defines = {}
    for f in os.listdir(pdir):
        if not f.endswith(".py"): continue
        t = ast.parse(open(os.path.join(pdir, f), encoding="utf-8").read())
        names = set()
        for n in t.body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)): names.add(n.name)
            elif isinstance(n, ast.Assign):
                for tg in n.targets:
                    for x in ast.walk(tg):
                        if isinstance(x, ast.Name): names.add(x.id)
        defines[f[:-3]] = names
    for f in sorted(os.listdir(pdir)):
        if not f.endswith(".py") or f in ("_shared.py", "__init__.py"): continue
        tree = ast.parse(open(os.path.join(pdir, f), encoding="utf-8").read())
        free = used_names(tree) - bound_names(tree) - BUILTINS - shared
        if free:
            problems[f"{pkg}/{f}"] = {n: [m for m, ns in defines.items() if n in ns and m != f[:-3]] for n in sorted(free)}
for k, v in problems.items():
    print(k)
    for n, owners in v.items():
        print(f"    {n:<28} -> {owners if owners else 'NOT FOUND IN PACKAGE'}")
print("\nfiles with holes:", len(problems))


# ---------------------------------------------------------------------------
# Relative-import check.
#
# After the 2026-09 restructure a file that used to sit at the package root
# (KRT/workspace.py) lives one level deeper (KRT/workspace/executors.py), so
# every "from .utils import x" inside it now means KRT.workspace.utils, which
# does not exist. Imports written INSIDE a function body are not executed at
# import time, so neither py_compile nor the import smoke test sees them -
# they only fail when a rigger clicks the button that runs that code.
# ---------------------------------------------------------------------------
def module_exports(path):
    """Top-level names a module file provides (defs, classes, assignments,
    imports, and - for a package __init__ - whatever it re-exports)."""
    out = set()
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return out
    def walk_body(body):
        # NOTE: recurse into module-level try/if/with - compat.py binds
        # QtWidgets & friends inside a try/except (PySide6 else PySide2),
        # which is still a module-level name.
        for n in body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    if a.name == "*":
                        if isinstance(n, ast.ImportFrom) and n.module:
                            sib = os.path.join(os.path.dirname(path), n.module.split(".")[-1] + ".py")
                            out.update(star_exports(sib))
                    else:
                        out.add((a.asname or a.name).split(".")[0])
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(n.name)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            out.add(x.id)
            elif isinstance(n, ast.Try):
                walk_body(n.body); walk_body(n.orelse); walk_body(n.finalbody)
                for h in n.handlers:
                    walk_body(h.body)
            elif isinstance(n, (ast.If, ast.With)):
                walk_body(n.body)
                walk_body(getattr(n, "orelse", []))
    walk_body(tree.body)
    return out


def check_relative_imports(root):
    issues = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "tools", "archive", "__pycache__", "PanelScripts", "templates")]
        for f in sorted(filenames):
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except Exception:
                continue
            for n in ast.walk(tree):
                if not isinstance(n, ast.ImportFrom) or not n.level:
                    continue
                base = dirpath
                for _ in range(n.level - 1):
                    base = os.path.dirname(base)
                parts = (n.module or "").split(".") if n.module else []
                target_mod = os.path.join(base, *parts) + ".py" if parts else None
                target_pkg = os.path.join(base, *parts, "__init__.py") if parts else os.path.join(base, "__init__.py")
                tpath = target_mod if target_mod and os.path.isfile(target_mod) else (
                        target_pkg if os.path.isfile(target_pkg) else None)
                rel = os.path.relpath(path, root)
                if tpath is None:
                    issues.append(f"{rel}:{n.lineno}  {ast.unparse(n)}   -> MODULE NOT FOUND")
                    continue
                exports = module_exports(tpath)
                missing = [a.name for a in n.names
                           if a.name != "*" and a.name not in exports
                           and not os.path.isfile(os.path.join(os.path.dirname(tpath), a.name + ".py"))
                           and not os.path.isdir(os.path.join(os.path.dirname(tpath), a.name))]
                if missing:
                    issues.append(f"{rel}:{n.lineno}  {ast.unparse(n)}   -> NAME(S) NOT EXPORTED: {missing}")
    return issues


print("\n--- relative-import check ---")
_issues = check_relative_imports(root)
for i in _issues:
    print("  " + i)
print("broken relative imports:", len(_issues))

