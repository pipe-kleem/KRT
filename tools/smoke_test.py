r"""Import smoke test - runs OUTSIDE Maya with fake maya/PySide2/ayon_api stubs.

It only proves the package IMPORTS (no circular imports, no missing names at
module level, mixin MROs resolve). It does not run any Maya logic.

Usage (from C:\pipeline\KRT_02):   python tools\smoke_test.py
"""
import importlib.util, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1) Static undefined-name check FIRST. Importing a module only executes its
# top level, so a name missing inside a method body (the classic fallout of
# splitting a file) imports fine and blows up later in Maya. This catches it.
print("--- undefined-name check ---")
rc = subprocess.call([sys.executable, os.path.join(ROOT, "tools", "check_names.py"), ROOT])
print("--- import check ---")
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke_stubs"))
# Hide any real PySide6/shiboken6 in this Python so compat.py falls back to the PySide2 stubs.
for _name in ("PySide6", "shiboken6"):
    sys.modules[_name] = None

# Load the folder as package "KRT" no matter what the folder is called.
spec = importlib.util.spec_from_file_location("KRT", os.path.join(ROOT, "__init__.py"),
                                              submodule_search_locations=[ROOT])
pkg = importlib.util.module_from_spec(spec); sys.modules["KRT"] = pkg; spec.loader.exec_module(pkg)

import importlib
for m in ["compat", "session", "utils", "dialogs", "widgets", "graph", "workspace", "main", "menu"]:
    importlib.import_module("KRT." + m); print("  ok  KRT." + m)
from KRT.workspace import SessionWorkspace
from KRT.graph import ModuleGraphWidget
print("SessionWorkspace MRO :", [c.__name__ for c in SessionWorkspace.__mro__ if c.__name__.endswith("Mixin")])
print("ModuleGraphWidget MRO:", [c.__name__ for c in ModuleGraphWidget.__mro__ if c.__name__.endswith("Mixin")])
print("IMPORT OK")
print("\nRun the undefined-name section above: 'files with holes: 0' is what you want.")
