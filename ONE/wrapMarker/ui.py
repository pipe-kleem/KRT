"""The Wrap Marker window, styling, cleanup and show()."""
import importlib
import json
import math
import os
import re
import sys
import time
from .state import cmds
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui
from .state import QtCore, QtGui, QtWidgets, wrapInstance
from . import state
from .state import CTX, REFINER_W, S, WINDOW, _FN, guard
from . import deform, genmesh, joint_relocator, markers, views, wrapdef


QSS = """
#%(w)s { background-color: #262729; }
QLabel { color: #c9cdd1; }
QLabel#badgeA, QLabel#badgeB { color: white; font-weight: bold; border-radius: 4px; }
QLabel#badgeA { background-color: #d94f4f; }
QLabel#badgeB { background-color: #2aa8d8; }
QLabel#valueLabel { color: #e8eaed; font-family: Consolas, monospace; }
QLabel#sectionLabel { color: #9aa0a6; }
QLabel#statusbar { background-color: #1b1c1e; color: #9aa0a6; padding-left: 8px;
                   border-top: 1px solid #343638; }
QLineEdit { background-color: #1d1e20; color: #e8eaed; border: 1px solid #3a3d40;
            border-radius: 4px; padding: 2px 6px; selection-background-color: #3d7fd9; }
QLineEdit:focus { border: 1px solid #5b9cf0; }
QPushButton { background-color: #3a3d40; color: #e1e4e8; border: 1px solid #4a4e52;
              border-radius: 4px; padding: 3px 12px; }
QPushButton:hover { background-color: #474b4f; border-color: #6a7075; }
QPushButton:pressed { background-color: #2d2f31; }
QPushButton[active="true"] { background-color: #2f8f4e; border-color: #43b869; color: white;
                             font-weight: bold; }
QPushButton[active="true"]:hover { background-color: #36a158; }
QSlider::groove:horizontal { height: 4px; background: #3a3d40; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5b9cf0; border-radius: 2px; }
QSlider::handle:horizontal { background: #eceff1; width: 12px; margin: -5px 0; border-radius: 6px; }
"""



def _ok(key):
    """The control stored under S['ui'][key] if it still exists, else None."""
    c = S["ui"].get(key)
    try:
        return c if c and cmds.control(c, exists=True) else None
    except Exception:
        return None



# set directly on the widget itself, so a plain selector is right (an id selector would need
# setObjectName, which breaks Maya's own control lookup - see _grab)
GREY_QSS = (
    "QPushButton { background-color: #3a3d40; border: 1px solid #4a4e52; border-radius: 4px;"
    " color: #e1e4e8; font-weight: bold; padding: 3px 12px; }"
    "QPushButton:hover { background-color: #474b4f; border-color: #6a7075; }"
    "QPushButton:pressed { background-color: #2d2f31; }"
)

ACTIVE_QSS = (
    "QPushButton { background-color: #2f8f4e; border: 1px solid #43b869; border-radius: 4px;"
    " color: white; font-weight: bold; padding: 3px 12px; }"
    "QPushButton:hover { background-color: #36a158; }"
)



def _qt(ctrl):
    if not ctrl:
        return None
    ptr = omui.MQtUtil.findControl(ctrl)
    if not ptr:
        try:
            ptr = omui.MQtUtil.findControl(cmds.control(ctrl, q=True, fullPathName=True))
        except Exception:
            ptr = None
    if not ptr:
        try:                                    # windows are found with findWindow, not findControl
            ptr = omui.MQtUtil.findWindow(ctrl)
        except Exception:
            ptr = None
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def _tool_window():
    """The tool's top-level Qt window."""
    w = _qt(WINDOW)
    if w is not None:
        return w
    for t in QtWidgets.QApplication.topLevelWidgets():
        try:
            if t.windowTitle() == "Wrap Marker Tool":
                return t
        except RuntimeError:
            pass
    return None



def _name(ctrl, object_name):
    """Give a control's widget an id so the window stylesheet can target it.

    WARNING: this breaks MQtUtil.findControl() for that control from here on (Maya matches
    control paths against objectName). Only ever use it on labels we never look up again -
    never on a button whose look we restyle later. Buttons go through _set_active instead.
    """
    w = _qt(ctrl)
    if w:
        S.setdefault("named", {})[object_name] = w     # keep the handle, the lookup is gone after this
        w.setObjectName(object_name)



STALE_QSS = (
    "QPushButton { background-color: #8a6420; border: 1px solid #d8a23a; border-radius: 4px;"
    " color: #ffffff; font-weight: bold; padding: 3px 12px; }"
    "QPushButton:hover { background-color: #9e7426; }"
)


def _button_width(label, pad=28, per_char=7.6, smallest=64):
    """Room for the label plus padding, so a button is never clipped by a fixed column width."""
    return max(smallest, int(len(label) * per_char) + pad)


def _set_active(ctrl, on, widget=None, qss=None):
    """Toggle the green 'on' look of a button: green while on, back to the normal grey when off."""
    try:
        cmds.button(ctrl, e=True, enableBackground=True,
                    backgroundColor=(0.18, 0.56, 0.31) if on else (0.23, 0.24, 0.25))
    except Exception:
        pass
    w = _qt(ctrl) or _live(widget)
    if w is None:
        cmds.warning("wrapMarker: could not style button %s" % ctrl)
        return
    w.setProperty("active", bool(on))
    w.setStyleSheet(qss or (ACTIVE_QSS if on else GREY_QSS))   # always explicit, so nothing else can win
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()
    w.repaint()



def _style_window():
    ptr = omui.MQtUtil.findWindow(WINDOW)
    if ptr:
        wrapInstance(int(ptr), QtWidgets.QWidget).setStyleSheet(QSS % {"w": WINDOW})



def _update_statusbar():
    sb = _ok("statusbar")
    if not sb:
        return

    def part(side):
        m = S["mesh"][side]
        if not m:
            return "%s: no mesh" % side
        return "%s: %s  |  %s verts  |  %d markers" % (
            side, m.split("|")[-1].split(":")[-1], format(S["info"][side], ","),
            len(S["markers"][side]))

    pairs = min(len(S["markers"]["A"]), len(S["markers"]["B"]))
    mode = "MARKING ON - click a mesh to place a marker" if S["marking"] else "Marking off"
    txt = "%s        %s        %s        pairs: %d        ||        Ctrl+Z undo   Shift+Z redo   Shift+drag move   Ctrl+click delete   F frame   Alt+drag orbit" % (
        mode, part("A"), part("B"), pairs)
    cmds.text(sb, e=True, label=txt)



def message(text):
    """A neutral note for the user: status bar now, Script Editor for the record."""
    print("wrapMarker: %s" % text)
    sb = _ok("statusbar")
    if sb:
        try:
            cmds.text(sb, e=True, label="  " + text)
        except Exception:
            pass


def _sync_morph_btn():
    btn = _ok("morphbtn")
    if not btn:
        return
    try:
        on = deform.has_morph()
    except Exception:
        on = False
    try:
        stale = on and deform.morph_is_stale()
    except Exception:
        stale = False
    cmds.button(btn, e=True, label="Update Morph" if stale else ("Un-morph B" if on else "Morph B"))
    cmds.button(btn, e=True, annotation=(
        "Markers changed since this morph was solved - rebuild it" if stale else
        ("Remove the morph from mesh B" if on else
         "Morph mesh B onto mesh A through the marker pairs (smooth spline, not a wrap)")))
    _set_active(btn, on and not stale, qss=STALE_QSS if stale else None)


def _sync_action_btns():
    """Keep both 'is this still in step with the markers?' buttons honest."""
    _sync_mesh_btn()
    _sync_morph_btn()


_sync_wrap_btn = _sync_morph_btn      # old name, kept so nothing stale breaks


def _sync_mesh_btn():
    btn = _ok("genbtn")
    if not btn:
        return
    on = bool(S["gen"]["base"] and cmds.objExists(S["gen"]["base"]))
    try:
        stale = on and genmesh.gen_is_stale()
    except Exception:
        stale = False
    cmds.button(btn, e=True, label="Update Mesh" if stale else ("Delete Mesh" if on else "Create Mesh"))
    cmds.button(btn, e=True, annotation=(
        "Markers changed since this mesh was built - rebuild it from all marker pairs"
        if stale else "Build a blendshape mesh from the marker pairs (click again to delete)"))
    _set_active(btn, on and not stale, qss=STALE_QSS if stale else None)



# --------------------------------------------------------------------- UI
def _refresh_all(*_):
    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    markers._update_overlays()



def _install_jobs(win):
    cam = S["cam"]["A"]
    shape = cmds.listRelatives(cam, shapes=True)[0]
    for a in ("translate", "rotate", "scale"):
        cmds.scriptJob(attributeChange=[cam + "." + a, _refresh_all], parent=win)
    cmds.scriptJob(attributeChange=[shape + ".focalLength", _refresh_all], parent=win)



def _set_blend(v):
    S["blend"] = float(v)
    bs = S["gen"]["bs"]
    if bs and cmds.objExists(bs):
        cmds.blendShape(bs, e=True, weight=[(0, S["blend"])])
    deform.set_weight(S["blend"])
    if _ok("blendval"):
        cmds.text(S["ui"]["blendval"], e=True, label="%.2f" % S["blend"])
    markers._update_overlays()



def _toggle_wire(*_):
    S["wire"] = not S["wire"]
    for side in ("A", "B"):
        try:
            ed = cmds.modelPanel(S["panel"][side], q=True, modelEditor=True)
            cmds.modelEditor(ed, e=True, wireframeOnShaded=S["wire"])
        except Exception:
            pass
    if _ok("wirebtn"):
        _set_active(S["ui"]["wirebtn"], S["wire"])



def _toggle_markers(*_):
    """Show / hide the marker numbers in both views (the markers themselves are untouched)."""
    S["hidden"] = not S.get("hidden")
    if _ok("hidebtn"):
        _set_active(S["ui"]["hidebtn"], S["hidden"])
    markers._update_overlays()
    markers._notify("Markers hidden - they are still there, just not drawn."
                    if S["hidden"] else "Markers visible again.")


def _toggle_symmetry(*_):
    S["symmetry"] = not S["symmetry"]
    if _ok("symbtn"):
        _set_active(S["ui"]["symbtn"], S["symmetry"])
    _notify = markers._notify
    _notify("Symmetry ON - each click also places the mirrored marker on the same mesh."
            if S["symmetry"] else "Symmetry OFF.")



def _host_layout(ctrl):
    """Qt widget + layout of a Maya layout control we created as a host for our own widgets."""
    if not ctrl:
        return None
    try:
        ptr = omui.MQtUtil.findLayout(ctrl) or omui.MQtUtil.findControl(ctrl)
    except Exception:
        ptr = None
    if not ptr:
        return None
    w = wrapInstance(int(ptr), QtWidgets.QWidget)
    lay = w.layout()
    if lay is None:
        lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    return lay


def _grab(key, ctrl, label):
    """Cache the Qt widget of a Maya control as soon as it is created.

    NEVER call setObjectName() on a Maya-made control: Maya resolves a control path
    ("win|layout|button7") by matching each step against the widgets' objectName, so renaming
    one makes every later MQtUtil.findControl() for it return nothing. That is exactly why the
    Start Marking button stopped restyling while Wireframe/Symmetry (never renamed) kept working.
    """
    w = _qt(ctrl)
    S[key] = w
    print("wrapMarker: %s widget %s" % (label, "ok" if w is not None else "NOT FOUND"))
    return w


def _live(w):
    try:
        w.isVisible()
        return w
    except Exception:
        return None


def _sync_btn(*_, **kw):
    """Make the button show the real state: green + 'Stop Marking' while marking, grey + 'Start Marking' off.
    The real fix: _set_active sets an explicit per-widget stylesheet, which beats the window-wide
    one. A bare native backgroundColor, or just a dynamic property + polish, both lost that fight -
    that's why Wireframe/Symmetry (which go through _set_active) worked and this never did."""
    on = bool(S["marking"])
    btn = _ok("start")
    if not btn:
        print("wrapMarker: Start Marking button not found (cannot restyle it)")
        return
    try:
        cmds.button(btn, e=True, label="Stop Marking" if on else "Start Marking")
    except Exception as e:
        print("wrapMarker: could not relabel the Start button: %s" % e)
    _set_active(btn, on, widget=S.get("btnqt"))
    # belt-and-braces: tint the status bar too, independent of the button
    w = _live((S.get("named") or {}).get("statusbar"))
    if w is not None:
        try:
            w.setStyleSheet("QLabel { background-color: %s; color: #e8eaed; padding-left: 8px;"
                            " border-top: 1px solid #343638; }"
                            % ("#2f8f4e" if on else "#1b1c1e"))
        except Exception:
            pass


def _tool_changed(*_):
    """The user switched to another Maya tool: marking is no longer on."""
    if S["marking"] and time.time() - S["toggle_t"] > 0.7 and cmds.currentCtx() != CTX:
        print("wrapMarker: marking turned OFF - Maya switched to the tool '%s'" % cmds.currentCtx())
        S["marking"] = False
        _sync_btn()



def _toggle_marking(*_):
    """First click: marking ON (button green, 'Stop Marking'). Second click: OFF (grey, 'Start Marking')."""
    now = time.time()
    if now - S.get("click_t", 0.0) < 0.25:      # one physical click must only toggle once
        return
    S["click_t"] = now
    S["toggle_t"] = now
    try:
        S["marking"] = not S["marking"]
        _sync_btn()                              # colour + name first, whatever Maya does next
        print("wrapMarker: marking %s" % ("ON" if S["marking"] else "OFF"))
        if S["marking"]:
            cmds.setToolTo(CTX)
            missing = [sd for sd in ("A", "B") if not S["mesh"][sd]]
            if missing:
                markers._notify("Marking is ON, but mesh %s is not loaded yet." % " and ".join(missing))
        else:
            cmds.setToolTo("selectSuperContext")
    except Exception:
        import traceback
        traceback.print_exc()
        _sync_btn()



IDLE_QSS = ("QLabel { background-color: #2b2d30; color: #6f747a; border: 1px solid #3a3d40;"
            " border-radius: 4px; padding: 0 8px; }")
ERR_STYLES = {
    "error": "QLabel { background-color: #a14646; color: #ffffff; border: 1px solid #c25a5a;"
             " border-radius: 4px; padding: 0 8px; font-weight: bold; }",
    "warning": "QLabel { background-color: #8a6420; color: #ffffff; border: 1px solid #d8a23a;"
               " border-radius: 4px; padding: 0 8px; }",
}


def _error_widget():
    return _live(S.get("errqt"))


def _clear_error(token=None):
    w = _error_widget()
    if w is None or (token is not None and token != S.get("err_t")):
        return
    w.setText("No errors")
    w.setToolTip("")
    w.setStyleSheet(IDLE_QSS)


def _show_message(level, msg):
    """Show an error / warning in the red bar at the top of the window (clears itself after a while)."""
    w = _error_widget()
    if w is None:
        return
    text = " ".join(str(msg).replace("wrap_marker_tool:", "").split())
    if not text:
        return
    w.setText(("ERROR:  " if level == "error" else "") + text)
    w.setToolTip(text + "\n(click to dismiss)")
    w.setStyleSheet(ERR_STYLES.get(level, ERR_STYLES["warning"]))
    token = S["err_t"] = time.time()
    QtCore.QTimer.singleShot(20000, lambda t=token: _clear_error(t))


def _use_existing_reference():
    """The reference was already in the scene before the tool opened: take it automatically."""
    ref = S.get("refiner")
    if ref is None:
        return
    try:
        ref.use_existing_reference()
    except Exception as e:
        cmds.warning("wrapMarker: could not use the existing reference: %s" % e)


def _startup():
    """After the window is up: take the reference, then the markers that are already in the scene."""
    _use_existing_reference()
    try:
        from . import persist
        persist.restore_from_scene()
    except Exception as e:
        cmds.warning("wrapMarker: could not restore the markers from the scene: %s" % e)


def _clear_markers(*_):
    """Delete every marker on both views. The generated mesh (if any) is kept."""
    n = len(S["markers"]["A"]) + len(S["markers"]["B"])
    if n and cmds.confirmDialog(title="Clear Markers", message="Delete all %d markers on A and B?" % n,
                                button=["Delete", "Cancel"], defaultButton="Cancel",
                                cancelButton="Cancel", dismissString="Cancel") != "Delete":
        return
    S["markers"] = {"A": [], "B": []}
    S["history"], S["redo"] = [], []
    try:
        deform.delete_morph(quiet=True)       # it was solved from the markers that just went
    except Exception as e:
        cmds.warning("Could not remove the morph: %s" % e)
    markers._update_overlays()
    from . import persist
    persist.save_to_scene()
    _update_statusbar()
    sb = _ok("statusbar")
    if sb and n:
        cmds.text(sb, e=True, label="  Cleared %d markers." % n)


def _relaunch():
    """Re-run run.py: closes this window, forgets the modules and opens a fresh tool from disk."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
    with open(path, "r") as f:
        code = f.read()
    exec(compile(code, path, "exec"), {"__name__": "__main__", "__file__": path})


def _reset_tool(*_):
    """Delete everything this tool created in the scene and restart it."""
    if cmds.confirmDialog(
            title="Reset Tool",
            message="Delete all markers, the generated mesh, the duplicated joints (RepositionJnt), "
                    "the bounding spheres and the joint reference, then restart the tool?",
            button=["Reset", "Cancel"], defaultButton="Cancel", cancelButton="Cancel",
            dismissString="Cancel") != "Reset":
        return
    S["markers"] = {"A": [], "B": []}
    S["history"], S["redo"] = [], []
    from . import persist
    persist.delete_store()
    for label, fn in (("morph", deform.delete_morph), ("wrap", wrapdef.delete_wrap)):
        try:
            fn(quiet=True)
        except Exception as e:
            cmds.warning("Reset: %s: %s" % (label, e))
    try:
        genmesh._delete_gen_mesh()
    except Exception as e:
        cmds.warning("Reset: generated mesh: %s" % e)
    for n in (cmds.ls("wrapMarkerMesh*", "wrapMarkerBlend*", "wrapSmoothA*", "wrapSmoothB*") or []):
        try:
            if cmds.objExists(n):
                cmds.delete(n)
        except Exception:
            pass
    for side in ("A", "B"):
        try:
            views._unlock(side)
        except Exception:
            pass
    ref = S.get("refiner")
    if ref is not None:
        try:
            ref.reset_everything()
        except Exception as e:
            cmds.warning("Reset: joint tool: %s" % e)
    try:
        _remove_isolate_sets()
        _purge_view_sets()
    except Exception:
        pass
    cmds.evalDeferred(_relaunch)


def _force_delete(node):
    """Plain delete only (no API tricks: deleting Maya's isolate sets that way can crash Maya).
    Returns True when the node is gone."""
    if not cmds.objExists(node):
        return True
    try:
        cmds.delete(node)
    except Exception:
        pass
    return not cmds.objExists(node)


def _purge_view_sets():
    """Delete modelPanelNViewSelectedSet nodes whose panel no longer exists. Maya creates one per isolated
    view and never removes it when the panel is closed, so they pile up in the outliner / scene.
    Sets of panels that are still alive (e.g. the user's own isolate) are left alone."""
    failed = []
    for st in cmds.ls("modelPanel*ViewSelectedSet", type="objectSet") or []:
        panel = st[:-len("ViewSelectedSet")]
        try:
            alive = bool(cmds.modelPanel(panel, exists=True))
        except Exception:
            alive = False
        if alive:
            continue   # never touch the set of a viewport that still exists
        if not _force_delete(st):
            failed.append(st)
    if failed:
        print("wrapMarker: Maya refuses to delete %d old isolate set(s) (marked non-deletable)." % len(failed))


def _remove_isolate_sets():
    """Turn isolate off and delete the isolate sets the panels created."""
    for side in ("A", "B"):
        panel = S["panel"][side]
        if not panel:
            continue
        sets = None
        try:
            sets = cmds.isolateSelect(panel, q=True, viewObjects=True)
            cmds.isolateSelect(panel, state=0)
        except Exception:
            pass
        for st in {sets, panel + "ViewSelectedSet"}:   # by query and by name
            if st:
                _force_delete(st)



def _release_gen_mesh():
    """Keep the generated blendshape mesh, but make it an ordinary mesh again."""
    g = S["gen"]
    base = g["base"]
    if base and cmds.objExists(base):
        genmesh._store_data(base)  # final snapshot, including markers added after creation
        for a, v in (("overrideEnabled", 0), ("overrideShading", 1), ("overrideColor", 0)):
            try:
                cmds.setAttr(base + "." + a, v)
            except Exception:
                pass
    g["base"] = g["bs"] = None
    g["undo"] = []



def _delete_loaded_meshes():
    """Delete meshes this tool imported from files (and their empty namespaces)."""
    for side in ("A", "B"):
        for n in S["loaded"][side]:
            if cmds.objExists(n):
                try:
                    cmds.delete(n)
                except Exception:
                    pass
        S["loaded"][side] = []
    for ns in cmds.namespaceInfo(listOnlyNamespaces=True) or []:
        if ns.startswith(("viewAMesh", "viewBMesh")):
            try:
                cmds.namespace(removeNamespace=ns)
            except Exception:
                pass



def _cleanup(*_):
    state.REPORT[0] = None
    S["errqt"] = None
    try:
        cmds.setToolTo("selectSuperContext")
    except Exception:
        pass
    ref = S.get("refiner")
    if ref is not None:
        try:
            ref.window.deleteLater()
        except RuntimeError:
            pass
        S["refiner"] = None
    _remove_isolate_sets()
    _release_gen_mesh()
    for side in ("A", "B"):
        try:
            views._unlock(side)
        except Exception:
            pass
    _delete_loaded_meshes()
    for sc in S["shortcuts"]:
        try:
            sc.setEnabled(False)
            sc.deleteLater()
        except RuntimeError:
            pass
    S["shortcuts"] = []
    for cid in S["callbacks"]:
        try:
            om1.MMessage.removeCallback(cid)
        except Exception:
            pass
    S["callbacks"] = []
    for side in ("A", "B"):
        ov = S["overlay"][side]
        if ov is not None:
            try:
                ov.deleteLater()
            except RuntimeError:
                pass
        S["overlay"][side] = None
    if cmds.draggerContext(CTX, exists=True):
        cmds.deleteUI(CTX)
    cam = S["cam"]["A"]
    if cam and cmds.objExists(cam):
        cmds.delete(cam)
    S["cam"] = {"A": None, "B": None}
    S["panel"] = {"A": None, "B": None}
    _FN.clear()
    # the panels are destroyed once the window has closed: sweep their leftover view sets afterwards
    try:
        cmds.evalDeferred(_purge_view_sets, lowestPriority=True)
    except Exception:
        pass



def _purge_leftovers():
    """Remove what an earlier run left behind (e.g. after reloading the script, when the
    old session's state is gone): temp cameras, imported-mesh namespaces, old window.
    The generated blendshape mesh (wrapMarkerMesh) is never touched."""
    try:
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        if cmds.draggerContext(CTX, exists=True):
            cmds.setToolTo("selectSuperContext")
            cmds.deleteUI(CTX)
        for cam in cmds.ls("wrapMarkerCam*", type="transform") or []:
            if cmds.objExists(cam) and cmds.listRelatives(cam, shapes=True, type="camera"):
                cmds.delete(cam)
        for ns in cmds.namespaceInfo(listOnlyNamespaces=True) or []:
            if ns.startswith(("viewAMesh", "viewBMesh")):
                cmds.namespace(removeNamespace=ns, deleteNamespaceContent=True)
    except Exception as e:
        cmds.warning("wrap_marker_tool: cleanup of earlier run incomplete: %s" % e)
    _purge_view_sets()   # separate from the above so an error there can never skip it



def _embed_refiner(col):
    """Put the CC Refiner (joint_relocator module) into the right-hand column."""
    try:
        rf = joint_relocator.embed(mesh="wrapMarkerMesh")
    except Exception as e:
        import traceback
        traceback.print_exc()
        markers._notify("Could not build the CC Refiner: %s" % e)
        return
    ptr = omui.MQtUtil.findLayout(col) or omui.MQtUtil.findControl(col)
    host = wrapInstance(int(ptr), QtWidgets.QWidget)
    lay = host.layout()
    if lay is None:
        lay = QtWidgets.QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    rf.window.setMinimumWidth(REFINER_W - 10)
    lay.addWidget(rf.window)
    S["refiner"] = rf
    # make sure the window is tall enough that nothing in the refiner needs scrolling
    try:
        top = wrapInstance(int(omui.MQtUtil.findWindow(WINDOW)), QtWidgets.QWidget)
        need = rf.window.minimumHeight() + 150   # + marker rows, status bar, title bar
        top.setMinimumHeight(need)
        if top.height() < need:
            top.resize(top.width(), need)
    except Exception:
        pass



def show():
    _purge_leftovers()
    _cleanup()
    S["markers"] = {"A": [], "B": []}
    S["blend"] = 0.0
    S["wire"] = False
    S["hidden"] = False
    S["symmetry"] = True
    S["marking"] = False
    S["history"], S["redo"] = [], []
    S["mesh"] = {"A": None, "B": None}
    S["info"] = {"A": 0, "B": 0}
    S["loaded"] = {"A": [], "B": []}
    S["ui"] = {}
    S["btnqt"] = None
    S["errqt"] = None
    S["named"] = {}
    S["click_t"] = 0.0
    S["refiner"] = None

    cmds.draggerContext(CTX, pressCommand=markers._on_press, dragCommand=markers._on_drag,
                        releaseCommand=markers._on_release, cursor="crossHair")

    # one shared temp camera: orbiting either panel moves both
    S["cam"]["A"] = views._make_cam()
    S["cam"]["B"] = S["cam"]["A"]

    print("wrapMarker: build %s" % time.strftime("%Y-%m-%d %H:%M",
          time.localtime(os.path.getmtime(os.path.abspath(__file__)))))
    try:
        cmds.windowPref(WINDOW, remove=True)      # forget any saved size / arrangement of an older run
    except Exception:
        pass
    win = cmds.window(WINDOW, title="Wrap Marker Tool", widthHeight=(1520, 820),
                      closeCommand=_cleanup)
    root = cmds.formLayout()
    H = 28

    # row 1: mesh A | mesh B | start marking
    bar = cmds.rowLayout(numberOfColumns=9, adjustableColumn=8,
                         columnWidth=[(1, 28), (2, 220), (3, 62), (4, 18), (5, 28),
                                      (6, 220), (7, 62), (9, 200)],
                         columnAttach=[(i, "both", 3) for i in range(1, 10)])
    badges, fields = {}, {}
    for side in ("A", "B"):
        cb = guard(lambda *_, sd=side: views._load(sd))
        badges[side] = cmds.text(label=side, align="center", height=H)
        try:
            fld = cmds.textField(placeholderText="Mesh %s  -  file path or scene name, Enter to load"
                                 % side, enterCommand=cb, height=H)
        except TypeError:
            fld = cmds.textField(enterCommand=cb, height=H)
        S["ui"]["mesh" + side] = fields[side] = fld
        cmds.button(label="Load", command=cb, height=H,
                    annotation="Load a file path or scene object into view %s" % side)
        if side == "A":
            cmds.text(label="")
    S["ui"]["errbar"] = cmds.text(label="", align="left", height=H)
    _grab("errqt", S["ui"]["errbar"], "errorBar")
    if S.get("errqt") is not None:
        try:
            S["errqt"].setCursor(QtCore.Qt.PointingHandCursor)
            S["errqt"].mousePressEvent = lambda e: _clear_error()     # click the bar to dismiss it
        except Exception:
            pass
    S["ui"]["start"] = cmds.button(label="Start Marking", command=guard(_toggle_marking), height=H,
                                   annotation="Click on a mesh in either view to place numbered markers")
    _grab("btnqt", S["ui"]["start"], "startBtn")
    cmds.setParent(root)

    # row 2: offset slider, generated mesh, wireframe
    from . import persist

    # Row 2 is built from a spec list: every button is sized from its own longest label, so
    # nothing is ever clipped and adding a button later needs no column bookkeeping.
    buttons = [
        ("genbtn",    "Create Mesh", "Update Mesh",
         guard(genmesh._toggle_gen_mesh),
         "Build the mesh from the marker pairs; rebuilds it when the markers have changed"),
        ("smoothbtn", "Subdivide", None,
         guard(genmesh._smooth_gen_mesh),
         "Add subdivision levels without changing the shape; the blendshape is rebuilt to match"),
        ("revertbtn", "Revert", None,
         guard(genmesh._revert_smooth),
         "Undo the last subdivide (blendshape rebuilt)"),
        ("tweenbtn",  "In-betweens", None,
         guard(deform.add_inbetweens),
         "Add a marker pair halfway along each edge of the marker layout, placed on both "
         "surfaces - denser correspondences make the morph follow mesh A more closely"),
        ("morphbtn",  "Morph B", "Update Morph",
         guard(deform.toggle_morph),
         "Morph mesh B onto mesh A through the marker pairs (smooth spline, not a wrap)"),
        ("symbtn",    "Symmetry", None,
         guard(_toggle_symmetry),
         "Each click also places the mirrored marker (X) on the same mesh"),
        ("wirebtn",   "Wireframe", None,
         guard(_toggle_wire),
         "Wireframe on shaded in both views"),
        ("hidebtn",   "Hide Markers", "Show Markers",
         guard(_toggle_markers),
         "Stop drawing the marker numbers - the markers themselves are kept"),
        ("clearbtn",  "Clear Markers", None,
         guard(_clear_markers),
         "Delete all markers on both views (the generated mesh is kept)"),
        ("savebtn",   "Save Markers", None,
         guard(persist.save_file),
         "Save all markers to a .json file"),
        ("loadbtn",   "Load Markers", None,
         guard(persist.load_file),
         "Load markers from a .json file (mesh A / B are taken from the scene by name)"),
        ("resetbtn",  "Reset Tool", None,
         guard(_reset_tool),
         "Delete markers, generated mesh, duplicated joints, spheres and the reference, "
         "then restart the tool"),
    ]

    SEP = 14                      # gap between groups
    widths = [96, 206, 46, SEP]   # label, slider, value, gap
    for key, label, alt, _cmd, _tip in buttons:
        widths.append(_button_width(max([label, alt or ""], key=len)))
        if key in ("smoothbtn", "tweenbtn"):   # each has a number field right after it
            widths.append(48)
        elif key == "revertbtn":  # a little air after the mesh-building group
            widths.append(SEP)

    bar2 = cmds.rowLayout(numberOfColumns=len(widths) + 1,
                          adjustableColumn=len(widths) + 1,
                          columnWidth=[(i + 1, w) for i, w in enumerate(widths)],
                          columnAttach=[(i, "both", 2) for i in range(1, len(widths) + 2)])
    sec = cmds.text(label="Offset  A > B", align="right", height=H)
    S["ui"]["blend"] = cmds.floatSlider(min=0.0, max=1.0, value=0.0, step=0.01, width=200,
                                        dragCommand=_set_blend, changeCommand=_set_blend,
                                        annotation="Slide each A marker toward its matching B marker")
    S["ui"]["blendval"] = cmds.text(label="0.00", align="center", height=H)
    cmds.text(label="")
    for key, label, _alt, cmd, tip in buttons:
        S["ui"][key] = cmds.button(label=label, command=cmd, height=H, annotation=tip)
        if key == "smoothbtn":
            S["ui"]["smoothlvl"] = cmds.intField(minValue=1, maxValue=4, value=1, step=1, height=H,
                                                 annotation="Subdivision levels per press (1-4)")
        if key == "tweenbtn":
            S["ui"]["tweenlvl"] = cmds.intField(minValue=1, maxValue=10, value=1, step=1, height=H,
                                                annotation="How many in-betweens to add along each "
                                                           "edge (1-10); 1 puts one at the midpoint")
        if key == "revertbtn":
            cmds.text(label="")
    try:
        _qt(S["ui"]["resetbtn"]).setStyleSheet(
            "QPushButton { background: #a14646; border: 1px solid #c25a5a; color: #ffffff;"
            " border-radius: 4px; padding: 3px 12px; }"
            "QPushButton:hover { background: #b95555; }")
    except Exception:
        pass
    cmds.text(label="")
    cmds.setParent(root)

    # right-hand side: the CC Refiner joint tool (built in below), embedded
    S["ui"]["refcol"] = cmds.columnLayout(adjustableColumn=True, width=REFINER_W)
    cmds.setParent(root)

    # the two views, left and right. A plain formLayout with a 50/50 split: paneLayout kept
    # coming back stacked because Maya restores its own saved pane arrangement.
    pane = cmds.formLayout()
    ctl = {}
    for side in ("A", "B"):
        cmds.setParent(pane)
        pn = cmds.modelPanel(menuBarVisible=False, label="")
        cmds.modelPanel(pn, e=True, camera=S["cam"]["A"])
        S["panel"][side] = pn
        try:
            ctl[side] = cmds.modelPanel(pn, q=True, control=True) or pn
        except Exception:
            ctl[side] = pn
        views._clean_panel(pn)
        views._isolate_empty(pn)
    pa, pb = ctl["A"], ctl["B"]
    try:
        cmds.formLayout(pane, e=True,
                        attachForm=[(pa, "top", 0), (pa, "left", 0), (pa, "bottom", 0),
                                    (pb, "top", 0), (pb, "right", 0), (pb, "bottom", 0)],
                        attachPosition=[(pa, "right", 2, 50), (pb, "left", 2, 50)])
        print("wrapMarker: views side by side  A=%s  B=%s" % (pa.split("|")[-1], pb.split("|")[-1]))
    except Exception as e:                      # last resort: let Maya arrange them
        print("wrapMarker: side-by-side attach failed (%s) - using panes" % e)
    cmds.setParent(root)

    S["ui"]["statusbar"] = cmds.text(label="", align="left", height=24)

    cmds.formLayout(root, e=True,
                    attachForm=[(bar, "top", 6), (bar, "left", 6), (bar, "right", 6),
                                (bar2, "left", 6), (bar2, "right", 6),
                                (S["ui"]["refcol"], "right", 6),
                                (pane, "left", 6),
                                (S["ui"]["statusbar"], "left", 0), (S["ui"]["statusbar"], "right", 0),
                                (S["ui"]["statusbar"], "bottom", 0)],
                    attachControl=[(bar2, "top", 4, bar), (pane, "top", 6, bar2),
                                   (S["ui"]["refcol"], "top", 6, bar2), (S["ui"]["refcol"], "bottom", 4, S["ui"]["statusbar"]),
                                   (pane, "right", 6, S["ui"]["refcol"]),
                                   (pane, "bottom", 4, S["ui"]["statusbar"])])
    _install_jobs(win)
    cmds.scriptJob(event=["ToolChanged", _tool_changed], parent=win)
    cmds.scriptJob(event=["SelectionChanged", views._enforce_isolation], parent=win)
    cmds.showWindow(win)

    for what, fn in (("badge A", lambda: _name(badges["A"], "badgeA")),
                     ("badge B", lambda: _name(badges["B"], "badgeB")),
                     ("error bar", _clear_error),
                     ("value label", lambda: _name(S["ui"]["blendval"], "valueLabel")),
                     ("section label", lambda: _name(sec, "sectionLabel")),
                     ("status bar", lambda: _name(S["ui"]["statusbar"], "statusbar")),
                     ("window style", _style_window),
                     ("start button", _sync_btn),
                     ("symmetry button", lambda: _set_active(S["ui"]["symbtn"], S["symmetry"])),
                     ("hide button", lambda: _set_active(S["ui"]["hidebtn"], S.get("hidden"))),
                     ("morph button", _sync_action_btns),
                     ("mesh button", _sync_mesh_btn),
                     ("status text", _update_statusbar),
                     ("joint tool", lambda: _embed_refiner(S["ui"]["refcol"]))):
        try:
            fn()
        except Exception as e:                  # never let one step kill the rest of the window
            import traceback
            traceback.print_exc()
            print("wrapMarker: setup step '%s' failed: %s" % (what, e))
    state.REPORT[0] = _show_message
    cmds.evalDeferred(markers._make_overlays)
    cmds.evalDeferred(_startup)
