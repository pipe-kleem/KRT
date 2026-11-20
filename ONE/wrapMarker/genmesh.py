"""Generated blendshape mesh: triangulation, blendShape, smooth / revert, marker data."""
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
from .state import DATA_ATTR, S
from . import markers, ui, views


# ---------------------------------------------------- generated blendshape mesh
def _delaunay(pts):
    """2D Delaunay (Bowyer-Watson). pts: [(x, y)] -> [(i, j, k)] counter-clockwise."""
    n = len(pts)
    if n < 3:
        return []
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    d = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    mx, my = (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0
    P = [(x + 1e-4 * i, y + 0.7e-4 * i) for i, (x, y) in enumerate(pts)]  # break exact ties
    P += [(mx - 20 * d, my - d), (mx, my + 20 * d), (mx + 20 * d, my - d)]

    def circ(t):
        (ax, ay), (bx, by), (cx, cy) = P[t[0]], P[t[1]], P[t[2]]
        dd = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(dd) < 1e-12:
            return None
        a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
        ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / dd
        uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / dd
        return ux, uy, (ax - ux) ** 2 + (ay - uy) ** 2

    tris = [(n, n + 1, n + 2)]
    cache = {tris[0]: circ(tris[0])}
    for i in range(n):
        px, py = P[i]
        bad = set()
        for t in tris:
            c = cache[t]
            if c and (px - c[0]) ** 2 + (py - c[1]) ** 2 < c[2]:
                bad.add(t)
        edges = {}
        for t in bad:
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                k = tuple(sorted(e))
                edges[k] = (edges.get(k, (0, e))[0] + 1, e)
        tris = [t for t in tris if t not in bad]
        for cnt, e in edges.values():
            if cnt == 1:
                t = (e[0], e[1], i)
                cache[t] = circ(t)
                tris.append(t)
    out = []
    for a, b, c in tris:
        if max(a, b, c) >= n:
            continue
        cross = (P[b][0] - P[a][0]) * (P[c][1] - P[a][1]) - (P[b][1] - P[a][1]) * (P[c][0] - P[a][0])
        if abs(cross) < 1e-9:
            continue
        out.append((a, b, c) if cross > 0 else (a, c, b))
    return out



def _make_poly_raw(name, points, counts, conns):
    pts = om2.MPointArray([om2.MPoint(*p) for p in points])
    obj = om2.MFnMesh().create(pts, list(counts), list(conns))
    path = om2.MFnDagNode(obj).fullPathName()
    if cmds.nodeType(path) == "mesh":
        path = cmds.listRelatives(path, parent=True, fullPath=True)[0]
    path = cmds.rename(path, name)
    cmds.sets(cmds.listRelatives(path, shapes=True, fullPath=True),
              e=True, forceElement="initialShadingGroup")
    return path



def _make_poly(name, points, tris):
    return _make_poly_raw(name, points, [3] * len(tris), [i for t in tris for i in t])



def _snapshot(node):
    """World-space points + topology of a mesh, so it can be rebuilt exactly."""
    shape = views._mesh_shapes(node)[0]
    sl = om2.MSelectionList()
    sl.add(shape)
    fn = om2.MFnMesh(sl.getDagPath(0))
    pts = [(q.x, q.y, q.z) for q in fn.getPoints(om2.MSpace.kWorld)]
    counts, conns = fn.getVertices()
    return pts, list(counts), list(conns)



def _store_data(base):
    """Write every marker onto the generated mesh as a JSON string attribute."""
    A, B = S["markers"]["A"], S["markers"]["B"]
    n = min(len(A), len(B))
    short = lambda x: x.split("|")[-1] if x else None
    data = {
        "meshA": short(S["mesh"]["A"]), "meshB": short(S["mesh"]["B"]),
        "note": "pair id N = marker N on A and marker N on B; mesh vertex N-1 = marker N",
        "pairs": [{"id": i + 1,
                   "A": {"pos": list(A[i]["pos"]), "face": A[i]["face"], "shape": short(A[i]["shape"])},
                   "B": {"pos": list(B[i]["pos"]), "face": B[i]["face"], "shape": short(B[i]["shape"])}}
                  for i in range(n)],
        "unpairedA": [{"id": i + 1, "pos": list(m["pos"]), "face": m["face"], "shape": short(m["shape"])}
                      for i, m in enumerate(A) if i >= n],
        "unpairedB": [{"id": i + 1, "pos": list(m["pos"]), "face": m["face"], "shape": short(m["shape"])}
                      for i, m in enumerate(B) if i >= n],
    }
    try:
        if not cmds.attributeQuery(DATA_ATTR, node=base, exists=True):
            cmds.addAttr(base, longName=DATA_ATTR, dataType="string")
        cmds.setAttr(base + "." + DATA_ATTR, json.dumps(data), type="string")
    except Exception as e:
        cmds.warning("Could not store marker data on %s: %s" % (base, e))



def read_markers(mesh):
    """Read the marker data back from a mesh made by this tool."""
    return json.loads(cmds.getAttr(mesh + "." + DATA_ATTR))



def _xray_a(on):
    try:
        ed = cmds.modelPanel(S["panel"]["A"], q=True, modelEditor=True)
        cmds.modelEditor(ed, e=True, xray=on)
    except Exception:
        pass



def _marker_sig():
    """Fingerprint of the marker pairs a generated mesh is built from."""
    A, B = S["markers"]["A"], S["markers"]["B"]
    n = min(len(A), len(B))
    r = lambda p: (round(p[0], 4), round(p[1], 4), round(p[2], 4))
    return (n, tuple(r(m["pos"]) for m in A[:n]), tuple(r(m["pos"]) for m in B[:n]))


def gen_is_stale():
    """True when a generated mesh exists but the markers have changed since it was built
    (new markers added, markers moved, markers imported) - so it needs rebuilding, not deleting."""
    g = S["gen"]
    if not (g["base"] and cmds.objExists(g["base"])):
        return False
    return g.get("sig") != _marker_sig()


def _delete_gen_mesh():
    g = S["gen"]
    try:                       # the wrap drives mesh B off this mesh - never leave it dangling
        from . import wrapdef
        wrapdef.delete_wrap(quiet=True)
    except Exception as e:
        cmds.warning("Could not remove the wrap: %s" % e)
    for n in (g["base"], g["bs"]):
        if n and cmds.objExists(n):
            cmds.delete(n)
    g["base"] = g["bs"] = None
    g["sig"] = None
    g["undo"] = []
    _xray_a(False)
    ui._sync_mesh_btn()



def _create_gen_mesh():
    markers.snap_markers(force=True)   # every marker on the CURRENT surface before triangulating
    A, B = S["markers"]["A"], S["markers"]["B"]
    n = min(len(A), len(B))
    if n < 3:
        cmds.warning("Place at least 3 marker pairs (same numbers on A and B) first.")
        return
    pa = [m["pos"] for m in A[:n]]
    pb = [m["pos"] for m in B[:n]]

    # triangulate in view A's screen space so the faces follow what you see
    view = omui.M3dView()
    omui.M3dView.getM3dViewFromModelPanel(S["panel"]["A"], view)
    xu, yu = om1.MScriptUtil(), om1.MScriptUtil()
    xp, yp = xu.asShortPtr(), yu.asShortPtr()
    scr = []
    for p in pa:
        view.worldToView(om1.MPoint(p[0], p[1], p[2]), xp, yp)
        scr.append((float(xu.getShort(xp)), float(yu.getShort(yp))))
    tris = _delaunay(scr)
    if not tris:
        cmds.warning("Could not build faces from these markers (points in a line?).")
        return

    prev = cmds.ls(sl=True, long=True)
    base = _make_poly("wrapMarkerMesh", pa, tris)
    S["gen"]["base"] = base  # known to the isolation guard from the start
    target = _make_poly("wrapMarkerTarget", pb, tris)
    bs = cmds.blendShape(target, base, name="wrapMarkerBlend")[0]
    cmds.delete(target)
    cmds.blendShape(bs, e=True, weight=[(0, S["blend"])])
    _store_data(base)

    # show as yellow wire, in view A only; x-ray A so the wire is visible on the surface
    for a, v in (("overrideEnabled", 1), ("overrideShading", 0), ("overrideColor", 17)):
        cmds.setAttr(base + "." + a, v)
    S["gen"]["base"], S["gen"]["bs"] = base, bs
    S["gen"]["sig"] = _marker_sig()      # so we can tell later whether the markers moved on
    S["gen"]["undo"] = []
    _restore_selection(prev)
    views._show_in_a(base)
    _xray_a(True)
    views._enforce_now()  # make sure each view shows only its own mesh (A also shows the new one)
    ui._sync_mesh_btn()



def _restore_selection(prev):
    """Re-select what was selected before - minus anything (e.g. faces of a deleted mesh) that is gone."""
    keep = [p for p in (prev or []) if cmds.objExists(p)]
    if keep:
        cmds.select(keep, r=True)
    else:
        cmds.select(clear=True)


def _install_gen(a, b, old_base, old_bs, delta):
    """Blend b into a, swap them in for the old generated mesh, keep display/data/weight."""
    g, w = S["gen"], S["blend"]
    old_json = None
    if cmds.attributeQuery(DATA_ATTR, node=old_base, exists=True):
        old_json = cmds.getAttr(old_base + "." + DATA_ATTR)
    prev = cmds.ls(sl=True, long=True)
    new_bs = cmds.blendShape(b, a, name="wrapMarkerBlendNew")[0]
    cmds.delete(b)
    if cmds.objExists(old_base):
        cmds.delete(old_base)
    if old_bs and cmds.objExists(old_bs):
        cmds.delete(old_bs)
    a = cmds.ls(cmds.rename(a, "wrapMarkerMesh"), long=True)[0]
    new_bs = cmds.rename(new_bs, "wrapMarkerBlend")
    cmds.blendShape(new_bs, e=True, weight=[(0, w)])
    for attr, val in (("overrideEnabled", 1), ("overrideShading", 0), ("overrideColor", 17)):
        cmds.setAttr(a + "." + attr, val)
    if old_json:
        try:
            d = json.loads(old_json)
            d["smoothLevels"] = max(0, d.get("smoothLevels", 0) + delta)
            d["note"] = ("pair id N = marker N on A and marker N on B; vertex N-1 is marker N "
                         "(original vertices come first, also after smoothing)")
            old_json = json.dumps(d)
        except Exception:
            pass
        if not cmds.attributeQuery(DATA_ATTR, node=a, exists=True):
            cmds.addAttr(a, longName=DATA_ATTR, dataType="string")
        cmds.setAttr(a + "." + DATA_ATTR, old_json, type="string")
    g["base"], g["bs"] = a, new_bs
    _restore_selection(prev)
    views._show_in_a(a)
    views._enforce_now()
    ui._sync_mesh_btn()



def _smooth_levels():
    c = ui._ok("smoothlvl")
    return max(1, min(4, cmds.intField(c, q=True, value=True))) if c else 1



def _smooth_gen_mesh(*_):
    """Subdivide the generated mesh by the chosen number of levels (no smoothing: the shape is not changed)
    and rebuild its blendshape: the A shape and the B shape get the identical subdivision."""
    g = S["gen"]
    base, bs = g["base"], g["bs"]
    if not (base and cmds.objExists(base) and bs and cmds.objExists(bs)):
        markers._notify("Create the mesh first, then subdivide it.")
        return
    lvl, w = _smooth_levels(), S["blend"]
    cmds.undoInfo(openChunk=True)
    try:
        cmds.blendShape(bs, e=True, weight=[(0, 0.0)])
        a = cmds.duplicate(base, name="wrapSmoothA")[0]    # current A shape
        cmds.blendShape(bs, e=True, weight=[(0, 1.0)])
        b = cmds.duplicate(base, name="wrapSmoothB")[0]    # current B shape
        cmds.blendShape(bs, e=True, weight=[(0, w)])
        g["undo"].append({"a": _snapshot(a), "b": _snapshot(b), "levels": lvl})  # for Revert
        for m in (a, b):
            # pure subdivision: new vertices are placed on the existing surface, the old ones do not move,
            # so the shape / deformation stays exactly as it is (polySmooth would round it off)
            for _ in range(lvl):
                cmds.polySubdivideFacet(m, divisions=1, mode=1)   # same op on A and B -> same topology
            cmds.delete(m, constructionHistory=True)
        _install_gen(a, b, base, bs, lvl)
    finally:
        cmds.undoInfo(closeChunk=True)
    markers._notify("Subdivided x%d - shape unchanged, blendshape reconnected (%d vertices)." %
            (lvl, cmds.polyEvaluate(S["gen"]["base"], vertex=True)))



def _revert_smooth(*_):
    """Step back to the mesh as it was before the last Smooth (blendshape rebuilt again)."""
    g = S["gen"]
    base, bs = g["base"], g["bs"]
    if not (base and cmds.objExists(base)):
        markers._notify("There is no generated mesh.")
        return
    if not g["undo"]:
        markers._notify("Nothing to revert - the mesh has not been subdivided.")
        return
    snap = g["undo"].pop()
    cmds.undoInfo(openChunk=True)
    try:
        a = _make_poly_raw("wrapSmoothA", *snap["a"])
        b = _make_poly_raw("wrapSmoothB", *snap["b"])
        _install_gen(a, b, base, bs, -snap["levels"])
    finally:
        cmds.undoInfo(closeChunk=True)
    markers._notify("Reverted subdivide (%d vertices)." % cmds.polyEvaluate(S["gen"]["base"], vertex=True))



def _toggle_gen_mesh(*_):
    g = S["gen"]
    if g["base"] and cmds.objExists(g["base"]):
        if gen_is_stale():               # markers added / moved / imported since: rebuild with all of them
            lvl = len(g.get("undo") or [])
            _delete_gen_mesh()
            _create_gen_mesh()
            if lvl:
                markers._notify("Mesh rebuilt from all %d marker pairs - press Subdivide again if needed."
                                % min(len(S["markers"]["A"]), len(S["markers"]["B"])))
            return
        _delete_gen_mesh()
    else:
        if not (S["mesh"]["A"] and S["mesh"]["B"]):
            cmds.warning("Load a mesh for both A and B first.")
            return
        _create_gen_mesh()
