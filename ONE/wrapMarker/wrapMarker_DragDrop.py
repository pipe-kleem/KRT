"""Drag this file from Explorer into a Maya viewport.

It opens the Wrap Marker tool right away and puts a 'WrapMk' button on your current shelf, so
next time you only click the shelf button. The tool is always read fresh from the folder this file sits in.
"""
import os

import maya.cmds as cmds
import maya.mel as mel

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None


def _run_py(folder):
    return os.path.join(folder, "run.py").replace("\\", "/")


def _launch(run_py):
    with open(run_py, "r") as f:
        code = f.read()
    exec(compile(code, run_py, "exec"), {"__name__": "__main__", "__file__": run_py})


def _add_shelf_button(run_py, root):
    top = mel.eval("$tmp = $gShelfTopLevel")
    if not cmds.tabLayout(top, exists=True):
        return
    shelf = cmds.tabLayout(top, q=True, selectTab=True)
    for b in cmds.shelfLayout(shelf, q=True, childArray=True) or []:
        try:
            if cmds.shelfButton(b, q=True, label=True) == "WrapMk":
                cmds.deleteUI(b)
        except Exception:
            pass
    cmd = ("_p = r'%s'\n"
           "exec(compile(open(_p).read(), _p, 'exec'), {'__name__': '__main__', '__file__': _p})" % run_py)
    cmds.shelfButton(parent=shelf, label="WrapMk", annotation="Wrap Marker Tool",
                     image1="pythonFamily.png", sourceType="python", command=cmd,
                     imageOverlayLabel="WrapMk")


def onMayaDroppedPythonFile(obj=None):
    """Maya calls this when the file is dropped into the viewport."""
    here = os.path.dirname(os.path.abspath(obj)) if obj else _HERE
    if not here:
        cmds.warning("Wrap Marker: could not work out the tool folder.")
        return
    run_py = _run_py(here)
    if not os.path.isfile(run_py):
        cmds.warning("Wrap Marker: run.py not found next to this file (%s)." % here)
        return
    root = os.path.dirname(here).replace("\\", "/")
    try:
        _add_shelf_button(run_py, root)
    except Exception as e:
        print("Wrap Marker: shelf button not added: %s" % e)
    _launch(run_py)


if __name__ == "__main__" and _HERE:
    onMayaDroppedPythonFile(os.path.join(_HERE, "wrapMarker_DragDrop.py"))
