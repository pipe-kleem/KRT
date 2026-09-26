"""
KRT — persistent menu + launcher helpers.

Kept as a lightweight, always-importable module so the shelf button, the Maya
top-menu, and the startup hook can all share ONE launch/rebuild entry point.
"""

import maya.cmds as cmds
import maya.mel as mel

MENU_NAME = "KRT_MainMenu"
MENU_LABEL = "KRT"

# Submodules to flush on reload (everything except this file, so the bound
# menu/shelf callbacks stay valid across reloads).
_KEEP = {"KRT", "KRT.menu"}


def _existing_window():
    """The open KRT window, or None. Found by objectName among Qt's
    top-level widgets, so it works even after the KRT modules were reloaded."""
    try:
        from KRT.compat import QtWidgets
    except Exception:
        return None
    for w in QtWidgets.QApplication.topLevelWidgets():
        try:
            if w.objectName() == "KRT_Window" and w.isVisible():
                return w
        except RuntimeError:        # C++ object already deleted
            continue
    return None


def bring_to_front(win):
    """Un-minimize, show, raise and focus an existing window."""
    from KRT.compat import QtCore
    if win.isMinimized():
        win.showNormal()
    # Clear only the minimized bit, keep maximized/fullscreen as they were.
    win.setWindowState(win.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
    win.show()
    win.raise_()
    win.activateWindow()


def launch(*args):
    """Stage 54: if KRT is already open, just bring it to the front - no
    reload, so open tabs and unsaved work are kept. Use force_reload() (menu
    item "Reload KRT (close + reopen)") to pick up code changes."""
    win = _existing_window()
    if win is not None:
        bring_to_front(win)
        return
    force_reload()


def force_reload(*args):
    """Reload KRT's code and (re)open the tool window."""
    import sys
    for m in [x for x in sys.modules if (x == "KRT" or x.startswith("KRT.")) and x not in _KEEP]:
        del sys.modules[m]
    import KRT.main as krt
    krt.run_tool()


def build_menu(*args):
    """Create (or rebuild) the 'KRT' menu in Maya's main menu bar."""
    g_main = mel.eval('$tmp = $gMainWindow')
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME)
    cmds.menu(MENU_NAME, parent=g_main, label=MENU_LABEL, tearOff=True)
    cmds.menuItem(parent=MENU_NAME, label="Launch KRT", command=launch,
                  annotation="Open KRT, or bring the open window to the front.")
    cmds.menuItem(parent=MENU_NAME, label="Reload KRT (close + reopen)", command=force_reload,
                  annotation="Reload KRT's code - closes the window, unsaved tabs are lost.")
    cmds.menuItem(parent=MENU_NAME, divider=True)
    cmds.menuItem(parent=MENU_NAME, label="About KRT",
                  command=lambda *a: cmds.confirmDialog(
                      title="KRT", message="KRT — Procedural Rig Builder", button=["OK"]))
    return MENU_NAME
