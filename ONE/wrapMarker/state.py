"""Shared state and constants (leaf module: imports nothing from this package)."""
import inspect
import traceback

import maya.cmds as _maya_cmds
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
except ImportError:  # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance

WINDOW = "wrapMarkerWin"
CTX = "wrapMarkerCtx"
DOT_RGB = {"A": (255, 70, 70), "B": (40, 200, 255)}
NUM_SIZE = 13  # marker number size in pixels
S = {
    "cam": {"A": None, "B": None},
    "panel": {"A": None, "B": None},
    "mesh": {"A": None, "B": None},
    "markers": {"A": [], "B": []},
    "loaded": {"A": [], "B": []},
    "overlay": {"A": None, "B": None},
    "callbacks": [],
    "blend": 0.0,
    "gen": {"base": None, "bs": None, "undo": []},
    "history": [],   # chronological marker actions: (side, marker dict)
    "redo": [],
    "wire": False,
    "marking": False,   # our own flag: is the marking tool on?
    "toggle_t": 0.0,
    "info": {"A": 0, "B": 0},  # vertex counts for the status bar
    "locked": {"A": {}, "B": {}},
    "shortcuts": [],
    "ui": {},
    "refiner": None,   # embedded CC Refiner (built in below)
}
_FN = {}          # shape -> (MFnMesh, accel params)
_ACC_KW = [None]  # which keyword name the accelerator argument uses
_ENF = [0.0]
DATA_ATTR = "wrapMarkerData"
REFINER_W = 320


# ---------------------------------------------------------------- error reporting
REPORT = [None]   # set by ui.show(): function(level, message) that fills the red bar in the window


def report(level, msg):
    """Send a warning / error to the window's message bar (never raises)."""
    f = REPORT[0]
    if f is None:
        return
    try:
        f(level, msg)
    except Exception:
        pass


class _Cmds(object):
    """maya.cmds, except that cmds.warning / cmds.error are also shown in the message bar."""

    def __getattr__(self, name):
        return getattr(_maya_cmds, name)

    def warning(self, *args, **kwargs):
        if args:
            report("warning", args[0])
        return _maya_cmds.warning(*args, **kwargs)

    def error(self, *args, **kwargs):
        if args:
            report("error", args[0])
        return _maya_cmds.error(*args, **kwargs)


cmds = _Cmds()


def guard(fn):
    """Wrap a button callback: an exception is printed AND shown in the message bar instead of vanishing."""
    try:
        params = list(inspect.signature(fn).parameters.values())
        varargs = any(p.kind == p.VAR_POSITIONAL for p in params)
        npos = len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
    except (TypeError, ValueError):
        varargs, npos = True, 0

    def wrapper(*args, **kwargs):
        try:
            return fn(*(args if varargs else args[:npos]), **kwargs)
        except Exception as e:
            traceback.print_exc()
            report("error", "%s: %s" % (getattr(fn, "__name__", "command"), e))
    wrapper.__name__ = getattr(fn, "__name__", "guarded")
    return wrapper
