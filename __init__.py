"""KRT (Kleem Rigging Tool).

__version__ is stamped into the window title and printed by the installer,
so it is always obvious WHICH copy of KRT is actually running. Bump it
whenever a change is delivered, and add the matching entry at the TOP of
changelog.py (the Changelog window in the UI reads it).
"""
__version__ = "46.44"
__build__ = "2026-11-18 12:00"


# KRT is a PACKAGE: its PARENT folder must be on sys.path, never the KRT folder itself.
# If the KRT folder is on sys.path, plain 'import widgets' / 'import utils' / 'import graph' in OTHER
# tools (e.g. Reallusion Auto Setup) pick up KRT's sub-packages and fail with
# "attempted relative import beyond top-level package". Drop it (and any stale copies of those modules).
import sys as _sys
import os as _os
try:
    _here = _os.path.normcase(_os.path.abspath(_os.path.dirname(__file__)))
    _bad = [p for p in _sys.path if p and _os.path.normcase(_os.path.abspath(p)) == _here]
    if _bad:
        _sys.path[:] = [p for p in _sys.path if p not in _bad]
        for _n in ("widgets", "utils", "graph", "dialogs", "workspace", "compat"):
            _m = _sys.modules.get(_n)
            if _m is not None and _os.path.normcase(_os.path.abspath(getattr(_m, "__file__", "") or "")).startswith(_here):
                _sys.modules.pop(_n, None)
        print("[KRT] Removed the KRT folder itself from sys.path (%s). Put its PARENT folder on the path instead "
              "(check Maya.env PYTHONPATH / userSetup / shelf)." % _bad[0])
except Exception:
    pass
