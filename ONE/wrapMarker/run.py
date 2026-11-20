# Maya launcher - paste this one line in the Script Editor / on a shelf button (Python):
#
#     exec(open(r"C:/Pipeline/wrapMarker/run.py").read())
#
# Every run closes the previous window, forgets all wrapMarker modules and imports them fresh from disk,
# so edits to the files are picked up each time the tool opens.
import os
import sys

import maya.cmds as cmds

_PKG = "wrapMarker"
_ROOT = r"C:/Pipeline"          # the folder that CONTAINS the wrapMarker folder (used when run with a bare exec)
if "__file__" in globals():     # started from the drag-and-drop file / shelf button: use the folder it really sits in
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")

# 1. close the previous instance cleanly (camera, isolate sets, callbacks, overlays, window)
_old = sys.modules.get(_PKG + ".ui")
if _old is not None:
    try:
        _old._cleanup()
    except Exception as _e:
        print("wrapMarker: cleanup of the previous run failed: %s" % _e)
if cmds.window("wrapMarkerWin", exists=True):
    cmds.deleteUI("wrapMarkerWin")

# 1b. close EVERY leftover Qt window of the tool (an old instance can survive deleteUI and sit in front)
try:
    try:
        from PySide6 import QtWidgets as _QW
    except ImportError:
        from PySide2 import QtWidgets as _QW
    _n = 0
    for _w in list(_QW.QApplication.topLevelWidgets()):
        try:
            if _w.objectName() == "wrapMarkerWin" or _w.windowTitle() == "Wrap Marker Tool":
                _w.close()
                _w.setParent(None)
                _w.deleteLater()
                _n += 1
        except RuntimeError:
            pass
    _QW.QApplication.processEvents()
    print("wrapMarker: closed %d old window(s)" % _n)
except Exception as _e:
    print("wrapMarker: could not scan for old windows: %s" % _e)

# 2. drop every wrapMarker module so the files are read again
for _m in [m for m in sys.modules if m == _PKG or m.startswith(_PKG + ".")]:
    del sys.modules[_m]

# 3. import fresh and open
while _ROOT in sys.path:                 # always put OUR folder first, so no other wrapMarker copy can win
    sys.path.remove(_ROOT)
sys.path.insert(0, _ROOT)
sys.dont_write_bytecode = True           # never use stale .pyc files
import importlib
importlib.invalidate_caches()
import wrapMarker
import wrapMarker.ui as _ui
print("wrapMarker: loaded from %s" % os.path.dirname(os.path.abspath(wrapMarker.__file__)))
print("wrapMarker: ui.py modified %s" % __import__("time").ctime(os.path.getmtime(_ui.__file__)))
wrapMarker.show()
