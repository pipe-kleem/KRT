"""Import smoke test - runs OUTSIDE Maya with fake maya/PySide2/ayon_api stubs.

It only proves the package IMPORTS (no circular imports, no missing names at
module level, mixin MROs resolve). It does not run any Maya logic.

Usage (from C:\pipeline\KRT_02):   python tools\smoke_test.py
"""
import importlib.util, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke_stubs"))

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
