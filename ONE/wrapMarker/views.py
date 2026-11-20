"""Viewports: shared temp camera, per-view isolation, mesh locking and loading."""
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
from .state import S, _ENF, _FN
from . import genmesh, markers, persist, ui


# ----------------------------------------------------------------- camera
def _source_camera_transform():
    panel = cmds.getPanel(withFocus=True)
    if not panel or cmds.getPanel(typeOf=panel) != "modelPanel":
        panels = cmds.getPanel(type="modelPanel") or []
        panel = panels[0] if panels else None
    if not panel:
        return None
    cam = cmds.modelPanel(panel, q=True, camera=True)
    if not cmds.objExists(cam):
        return None
    if cmds.nodeType(cam) == "transform":
        return cam
    return cmds.listRelatives(cam, parent=True)[0]



def _make_cam():
    cam = cmds.camera(name="wrapMarkerCam")[0]
    src = _source_camera_transform()
    if src:
        cmds.xform(cam, ws=True, matrix=cmds.xform(src, q=True, ws=True, matrix=True))
        src_shape = cmds.listRelatives(src, shapes=True)[0]
        shape = cmds.listRelatives(cam, shapes=True)[0]
        cmds.setAttr(shape + ".focalLength", cmds.getAttr(src_shape + ".focalLength"))
    else:
        cmds.xform(cam, ws=True, t=(28, 21, 28), ro=(-27.938, 45, 0))
    return cam



def _frame(side):
    cam, mesh = S["cam"][side], S["mesh"][side]
    if cam and mesh and cmds.objExists(mesh):
        cmds.viewFit(cam, mesh, fitFactor=0.9)



# ----------------------------------------------------------------- viewport
def _mesh_shapes(node):
    """All non-intermediate mesh shapes at/below node."""
    if not node or not cmds.objExists(node):
        return []
    if cmds.nodeType(node) == "mesh":
        return [cmds.ls(node, long=True)[0]]
    return cmds.listRelatives(node, allDescendents=True, type="mesh",
                              noIntermediate=True, fullPath=True) or []



def _clean_panel(panel):
    """Plain viewport: default shader, no HUD, no grid, no toolbar, no clutter."""
    ed = cmds.modelPanel(panel, q=True, modelEditor=True)
    flags = dict(
        displayAppearance="smoothShaded", displayTextures=False, useDefaultMaterial=True,
        displayLights="default", wireframeOnShaded=S["wire"], shadows=False,
        headsUpDisplay=False, grid=False, manipulators=False,
        selectionHiliteDisplay=False,
        viewAxis=False, displayAxis=False,
        cameras=False, lights=False, imagePlane=False, joints=False, ikHandles=False,
        deformers=False, handles=False, pivots=False, nurbsCurves=False,
        nurbsSurfaces=False, subdivSurfaces=False, planes=False, fluids=False,
        hairSystems=False, dynamics=False, strokes=False, textures=False,
        polymeshes=True, locators=False, dimensions=False,
    )
    for k in ["allObjects"] + list(flags):
        try:
            cmds.modelEditor(ed, e=True, **{k: flags.get(k, True)})
        except Exception:
            pass
    try:
        bar = cmds.modelPanel(panel, q=True, barLayout=True)
        cmds.layout(bar, e=True, manage=False)
    except Exception:
        pass



def _isolate_empty(panel):
    """Show nothing in this panel until a mesh is loaded for it."""
    prev = cmds.ls(sl=True, long=True)
    cmds.select(clear=True)
    cmds.isolateSelect(panel, state=0)
    cmds.isolateSelect(panel, loadSelected=True)  # empty selection -> empty view
    cmds.isolateSelect(panel, state=1)
    if prev:
        cmds.select(prev, r=True)



def _show_in_a(node):
    """Add a node to view A's isolate set directly (and only A's), then refresh the view."""
    panel = S["panel"]["A"]
    vs = cmds.isolateSelect(panel, q=True, viewObjects=True)
    if vs and cmds.objExists(vs):
        cmds.sets(node, e=True, add=vs)
    else:
        cmds.isolateSelect(panel, addDagObject=node)
    cmds.isolateSelect(panel, update=True)



def _enforce_now():
    _ENF[0] = 0.0
    _enforce_isolation()



def _enforce_isolation(*_):
    """Safety net: if a view ever shows something other than its own mesh (e.g. after a
    selection change in the main viewport), put its isolate set back. Throttled."""
    now = time.time()
    if now - _ENF[0] < 0.25:
        return
    _ENF[0] = now
    for side in ("A", "B"):
        panel = S["panel"][side]
        try:
            if not panel or not cmds.modelPanel(panel, exists=True):
                continue
            if not cmds.isolateSelect(panel, q=True, state=True):
                _isolate(side) if S["mesh"][side] else _isolate_empty(panel)
                continue
            vs = cmds.isolateSelect(panel, q=True, viewObjects=True)
            if not vs or not cmds.objExists(vs):
                continue
            want = set()
            for n in (S["mesh"][side], S["gen"]["base"] if side == "A" else None):
                if n and cmds.objExists(n):
                    want.add(cmds.ls(n, long=True)[0])
            have = set()
            for x in cmds.sets(vs, q=True) or []:
                x = cmds.ls(x, long=True)[0]
                if cmds.nodeType(x) != "transform":
                    x = (cmds.listRelatives(x, parent=True, fullPath=True) or [x])[0]
                have.add(x)
            if have != want:
                cmds.sets(vs, e=True, clear=True)
                if want:
                    cmds.sets(sorted(want), e=True, add=vs)
                cmds.isolateSelect(panel, update=True)
        except Exception:
            pass



def _isolate(side):
    panel, mesh = S["panel"][side], S["mesh"][side]
    if not (panel and mesh):
        return
    prev = cmds.ls(sl=True, long=True)
    cmds.isolateSelect(panel, state=0)
    cmds.select(mesh, r=True)
    cmds.isolateSelect(panel, loadSelected=True)
    cmds.isolateSelect(panel, state=1)
    if prev:
        cmds.select(prev, r=True)
    else:
        cmds.select(clear=True)
    _clean_panel(panel)



# ------------------------------------------------------------------ locking
def _lock(side, node):
    """Make the mesh non-selectable (reference display type); restored on unlock.
    Covers the node, every shape/child under it, and any display layer driving them."""
    saved = []   # (plug, old value)
    nodes = [node] + (cmds.listRelatives(node, allDescendents=True, fullPath=True) or [])
    layers = set()
    cmds.undoInfo(stateWithoutFlush=False)  # keep this out of Maya's undo queue
    try:
        for n in nodes:
            if not cmds.attributeQuery("overrideDisplayType", node=n, exists=True):
                continue
            lyr = cmds.listConnections(n + ".drawOverride", source=True, destination=False,
                                       type="displayLayer")
            if lyr:
                layers.add(lyr[0])
                continue
            for attr, val in (("overrideEnabled", 1), ("overrideDisplayType", 2)):
                plug = n + "." + attr
                try:
                    saved.append((plug, cmds.getAttr(plug)))
                    cmds.setAttr(plug, val)
                except Exception:
                    saved.pop()
        for lyr in layers:
            try:
                plug = lyr + ".displayType"
                saved.append((plug, cmds.getAttr(plug)))
                cmds.setAttr(plug, 2)
            except Exception:
                saved.pop()
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
    if not saved:
        cmds.warning("Could not lock %s (its display settings are locked or driven)." % node)
    S["locked"][side] = {"node": node, "saved": saved}



def _unlock(side):
    d = S["locked"].get(side) or {}
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for plug, val in reversed(d.get("saved", [])):
            try:
                if cmds.objExists(plug.split(".")[0]):
                    cmds.setAttr(plug, val)
            except Exception:
                pass
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
    S["locked"][side] = {}



# ------------------------------------------------------------------ meshes
def _set_mesh(side):
    sel = cmds.ls(sl=True, long=True, transforms=True)
    if not sel:
        cmds.warning("Select a mesh transform first.")
        return
    _assign_mesh(side, sel[0])



def _assign_mesh(side, node):
    if not _mesh_shapes(node):
        cmds.warning("%s has no mesh shape." % node)
        return
    _unlock(side)
    S["mesh"][side] = node
    S["markers"][side] = []  # markers belong to the previous mesh
    S["history"], S["redo"] = [], []
    genmesh._delete_gen_mesh()
    _lock(side, node)
    try:
        S["info"][side] = sum(cmds.polyEvaluate(sh, vertex=True) for sh in _mesh_shapes(node))
    except Exception:
        S["info"][side] = 0
    _FN.clear()
    if ui._ok("mesh" + side):
        cmds.textField(S["ui"]["mesh" + side], e=True, text=node.split("|")[-1])
    _isolate(side)
    _frame(side)
    markers._update_overlays()
    persist.save_to_scene()



_LOADERS = {  # ext: (file type, plugin)
    "obj": ("OBJ", "objExport"),
    "fbx": ("FBX", "fbxmaya"),
    "abc": ("Alembic", "AbcImport"),
    "ma": ("mayaAscii", None),
    "mb": ("mayaBinary", None),
}



def _load(side):
    """Field holds a file path or a scene node name; empty = use selection."""
    txt = cmds.textField(S["ui"]["mesh" + side], q=True, text=True).strip().strip('"')
    w = ui._qt(S["ui"]["mesh" + side])
    if w:
        w.clearFocus()  # so F / Ctrl+F / Ctrl+Z work right after loading
    if not txt:
        _set_mesh(side)
    elif os.path.isfile(txt):
        _load_path(side, txt)
    elif cmds.objExists(txt):
        _assign_mesh(side, cmds.ls(txt, long=True)[0])
    else:
        cmds.warning("Not a file or scene object: %s" % txt)



def _load_path(side, path):
    """Import a mesh file (read-only on disk) and use it for this view."""
    ext = path.lower().rsplit(".", 1)[-1]
    if ext not in _LOADERS:
        cmds.warning("Unsupported file type: .%s" % ext)
        return
    ftype, plug = _LOADERS[ext]
    if plug and not cmds.pluginInfo(plug, q=True, loaded=True):
        cmds.loadPlugin(plug, quiet=True)
    for n in S["loaded"][side]:  # replace a mesh we imported earlier for this side
        if cmds.objExists(n):
            cmds.delete(n)
    new = cmds.file(path, i=True, type=ftype, returnNewNodes=True, ignoreVersion=True,
                    mergeNamespacesOnClash=False, namespace="view%sMesh" % side)
    shapes = cmds.ls(new, type="mesh", long=True, noIntermediate=True)
    xforms = []
    for sh in shapes:
        t = cmds.listRelatives(sh, parent=True, fullPath=True)[0]
        if t not in xforms:
            xforms.append(t)
    if not xforms:
        cmds.warning("No mesh found in %s" % path)
        return
    node = xforms[0] if len(xforms) == 1 else cmds.group(xforms, name="view%sMesh_grp" % side)
    node = cmds.ls(node, long=True)[0]
    S["loaded"][side] = [node]
    _assign_mesh(side, node)
