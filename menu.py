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


def launch(*args):
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
    cmds.menuItem(parent=MENU_NAME, label="Launch / Reload KRT", command=launch)
    cmds.menuItem(parent=MENU_NAME, divider=True)
    cmds.menuItem(parent=MENU_NAME, label="About KRT",
                  command=lambda *a: cmds.confirmDialog(
                      title="KRT", message="KRT — Procedural Rig Builder", button=["OK"]))
    return MENU_NAME
