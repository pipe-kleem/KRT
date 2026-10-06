"""
fastSkinMirror.py  -  Fast skin-weight mirror for SELECTED vertices (Maya 2022+, Python 3)

Why it's fast
-------------
* Only the selected vertices (and their mirror partners) are read / written - no full-mesh
  weight read, no per-vertex skinPercent calls.
* Mirror-vertex lookup uses OpenMaya's MMeshIntersector (C++ octree) instead of a Python
  loop over every vertex - no scipy needed.
* One getWeights call + one setWeights call per mesh (OpenMaya 2.0).
* Influence remap is a precomputed permutation applied with operator.itemgetter (C speed).
* Fully undoable as ONE undo step: the same file registers itself as a tiny plugin command.

Install
-------
1. Save this file as   fastSkinMirror.py   into your Maya scripts folder
   (e.g. Documents/maya/<version>/scripts).
2. In the Script Editor (Python tab):

       import fastSkinMirror
       fastSkinMirror.show()

   Or headless / from a shelf button without UI:

       import fastSkinMirror
       fastSkinMirror.mirror_selected(plane="YZ", direction="+", match="position")

Usage
-----
Select vertices on either side (or faces/edges/whole meshes - converted to vertices),
choose the mirror plane (XY / YZ / XZ, default YZ) and direction
(+ to - default, or - to +), press Mirror.
  * Selected verts on the SOURCE side   -> push their weights to the opposite side.
  * Selected verts on the TARGET side   -> pull weights from their mirror partner.
  * Selected verts on the CENTER line   -> symmetrised (L/R influence weights averaged).
Joint match "Position" (default) pairs joints by their mirrored bind-pose position;
"Name / Label" pairs them by Maya joint labels (side/type) then L_/R_, _l/_r,
Left/Right ... name tokens. Unpaired influences keep their own weight.
If a mirror joint exists in the scene but is not yet in the skinCluster, it is added
automatically (weight 0) so the mirrored weight lands on it.
"""

import os
import sys
import time
import types
import operator

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


def maya_useNewAPI():
    """Tells Maya this plugin uses the Python API 2.0."""
    pass


TOOL_NAME = "fastSkinMirror"
PLUGIN_CMD = "fastSkinMirrorApply"
WINDOW = "fastSkinMirrorWin"
_STASH_NAME = "_fastSkinMirror_stash"
_AXES = {"x": 0, "y": 1, "z": 2}
DEFAULT_PAIRS = "L:R, l:r, Left:Right, left:right, lf:rt, Lf:Rt, LF:RT, Lft:Rgt"


# --------------------------------------------------------------------------------------
# Shared stash (the module imported by the user and the module loaded as a plugin are
# two different module objects, so data is handed over through sys.modules)
# --------------------------------------------------------------------------------------
def _stash():
    mod = sys.modules.get(_STASH_NAME)
    if mod is None:
        mod = types.ModuleType(_STASH_NAME)
        mod.pending = None
        sys.modules[_STASH_NAME] = mod
    return mod


class _WeightOp(object):
    """One setWeights operation on one skinned mesh, able to apply and revert itself."""

    def __init__(self, skin_obj, shape_path, comp, n_inf, new_w, new_blend=None):
        self.skin_obj = skin_obj
        self.shape_path = shape_path
        self.comp = comp
        self.inf_idx = om.MIntArray(list(range(n_inf)))
        self.new_w = om.MDoubleArray(new_w)
        self.new_blend = om.MDoubleArray(new_blend) if new_blend is not None else None
        self.old_w = None
        self.old_blend = None

    def apply(self):
        fn = oma.MFnSkinCluster(self.skin_obj)
        if self.old_w is None:
            self.old_w = fn.getWeights(self.shape_path, self.comp, self.inf_idx)
            if self.new_blend is not None:
                self.old_blend = fn.getBlendWeights(self.shape_path, self.comp)
        fn.setWeights(self.shape_path, self.comp, self.inf_idx, self.new_w, False)
        if self.new_blend is not None:
            fn.setBlendWeights(self.shape_path, self.comp, self.new_blend)

    def revert(self):
        if self.old_w is None:
            return
        fn = oma.MFnSkinCluster(self.skin_obj)
        fn.setWeights(self.shape_path, self.comp, self.inf_idx, self.old_w, False)
        if self.old_blend is not None:
            fn.setBlendWeights(self.shape_path, self.comp, self.old_blend)


# --------------------------------------------------------------------------------------
# Undoable plugin command
# --------------------------------------------------------------------------------------
class FastSkinMirrorApplyCmd(om.MPxCommand):
    def __init__(self):
        super(FastSkinMirrorApplyCmd, self).__init__()
        self._ops = []

    @staticmethod
    def creator():
        return FastSkinMirrorApplyCmd()

    def isUndoable(self):
        return True

    def doIt(self, args):
        st = _stash()
        ops, st.pending = st.pending, None
        if not ops:
            raise RuntimeError("%s: nothing to apply (call fastSkinMirror.mirror_selected())."
                               % PLUGIN_CMD)
        self._ops = ops
        self.redoIt()

    def redoIt(self):
        for op in self._ops:
            op.apply()

    def undoIt(self):
        for op in reversed(self._ops):
            op.revert()


def initializePlugin(obj):
    plugin = om.MFnPlugin(obj, TOOL_NAME, "1.0", "Any")
    plugin.registerCommand(PLUGIN_CMD, FastSkinMirrorApplyCmd.creator)


def uninitializePlugin(obj):
    om.MFnPlugin(obj).deregisterCommand(PLUGIN_CMD)


def _ensure_plugin():
    if hasattr(cmds, PLUGIN_CMD):
        return True
    try:
        path = os.path.abspath(__file__)
        if path.endswith(".pyc"):
            path = path[:-1]
        cmds.loadPlugin(path, quiet=True)
        return hasattr(cmds, PLUGIN_CMD)
    except Exception as exc:  # pragma: no cover
        om.MGlobal.displayWarning("%s: could not load undo plugin (%s). Changes will NOT "
                                  "be undoable." % (TOOL_NAME, exc))
        return False


# --------------------------------------------------------------------------------------
# Scene helpers
# --------------------------------------------------------------------------------------
def _mesh_shape(dag):
    """Return the non-intermediate mesh shape dagPath for a transform/shape dagPath."""
    if dag.hasFn(om.MFn.kMesh) and dag.apiType() == om.MFn.kMesh:
        if not om.MFnDagNode(dag).isIntermediateObject:
            return dag
        return None
    for i in range(dag.childCount()):
        child = dag.child(i)
        if child.apiType() != om.MFn.kMesh:
            continue
        if om.MFnDagNode(child).isIntermediateObject:
            continue
        p = om.MDagPath(dag)
        p.push(child)
        return p
    return None


def _gather_selection():
    """{shapeFullPath: (shapeDagPath, sorted vertex indices)} from current selection."""
    sel = cmds.ls(sl=True, fl=False) or []
    if not sel:
        return {}
    conv = cmds.polyListComponentConversion(sel, toVertex=True) or []
    msel = om.MSelectionList()
    for item in conv:
        try:
            msel.add(item)
        except Exception:
            pass

    result = {}
    for i in range(msel.length()):
        try:
            dag, comp = msel.getComponent(i)
        except Exception:
            continue
        shape = _mesh_shape(dag)
        if shape is None:
            continue
        key = shape.fullPathName()
        if key not in result:
            result[key] = (shape, set())
        if comp.isNull():
            result[key][1].update(range(om.MFnMesh(shape).numVertices))
        else:
            result[key][1].update(om.MFnSingleIndexedComponent(comp).getElements())
    return {k: (v[0], sorted(v[1])) for k, v in result.items()}


def _find_skin(shape_path):
    hist = cmds.listHistory(shape_path.fullPathName(), pruneDagObjects=True) or []
    shape_obj = shape_path.node()
    for skin in cmds.ls(hist, type="skinCluster") or []:
        obj = om.MSelectionList().add(skin).getDependNode(0)
        fn = oma.MFnSkinCluster(obj)
        try:
            fn.indexForOutputShape(shape_obj)
            return obj, skin
        except Exception:
            continue
    return None, None


def _orig_shape(shape_path):
    """Return dagPath of the undeformed (bind pose) intermediate shape, or None."""
    shape = shape_path.fullPathName()
    parent = (cmds.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
    if not parent:
        return None
    n_verts = om.MFnMesh(shape_path).numVertices
    for s in cmds.listRelatives(parent, shapes=True, fullPath=True) or []:
        if cmds.nodeType(s) != "mesh" or not cmds.getAttr(s + ".intermediateObject"):
            continue
        if cmds.listConnections(s + ".inMesh", source=True, destination=False):
            continue
        p = om.MSelectionList().add(s).getDagPath(0)
        if om.MFnMesh(p).numVertices == n_verts:
            return p
    return None


def _make_comp(indices):
    fn = om.MFnSingleIndexedComponent()
    comp = fn.create(om.MFn.kMeshVertComponent)
    fn.addElements(om.MIntArray(list(indices)))
    return comp, list(fn.getElements())


# --------------------------------------------------------------------------------------
# Mirror lookup
# --------------------------------------------------------------------------------------
class _MirrorLookup(object):
    """Finds mirror vertices with MMeshIntersector - cost scales with the selection only."""

    def __init__(self, lookup_path, axis, world_space, tolerance, snap):
        self.ax = axis
        self.tol = tolerance
        self.snap = snap
        self.fn_mesh = om.MFnMesh(lookup_path)
        space = om.MSpace.kWorld if world_space else om.MSpace.kObject
        self.pts = self.fn_mesh.getPoints(space)
        mtx = lookup_path.inclusiveMatrix() if world_space else om.MMatrix()
        self.inter = om.MMeshIntersector()
        self.inter.create(lookup_path.node(), mtx)
        s = [1.0, 1.0, 1.0]
        s[axis] = -1.0
        self.scale = s

    def coord(self, v):
        return self.pts[v][self.ax]

    def mirror(self, v):
        p = self.pts[v]
        s = self.scale
        q = om.MPoint(p.x * s[0], p.y * s[1], p.z * s[2])
        try:
            face = self.inter.getClosestPoint(q).face
        except Exception:
            return -1
        best, best_d = -1, 1e30
        for vi in self.fn_mesh.getPolygonVertices(face):
            d = self.pts[vi].distanceTo(q)
            if d < best_d:
                best, best_d = vi, d
        if best_d <= self.tol or self.snap:
            return best
        return -1


# --------------------------------------------------------------------------------------
# Influence mirror map
# --------------------------------------------------------------------------------------
def _parse_pairs(text):
    pairs = []
    for chunk in (text or "").split(","):
        if ":" in chunk:
            a, b = [c.strip() for c in chunk.split(":", 1)]
            if a and b:
                pairs.append((a, b))
    return pairs


def _swap_name(base, pairs):
    """Swap side tokens in a name. Underscore tokens first, then CamelCase prefixes."""
    tokens = base.split("_")
    for a, b in pairs:
        for x, y in ((a, b), (b, a)):
            if x in tokens:
                return "_".join(y if t == x else t for t in tokens)
    for a, b in pairs:
        for x, y in ((a, b), (b, a)):
            if len(x) > 1 and base.startswith(x) and len(base) > len(x):
                nxt = base[len(x)]
                if nxt.isupper() or nxt.isdigit():
                    return y + base[len(x):]
    return None


# Maya joint label ("Draw Label" attrs): side 0=Center 1=Left 2=Right 3=None, type 18=Other
def _joint_label(node):
    try:
        side = cmds.getAttr(node + ".side")
        typ = cmds.getAttr(node + ".type")
    except Exception:
        return None
    if side not in (1, 2) or typ == 0:
        return None
    other = cmds.getAttr(node + ".otherType") if typ == 18 else ""
    return (side, typ, other)


def _mirror_label(label):
    return (3 - label[0], label[1], label[2]) if label else None


def _mirror_point(p, axis):
    return om.MPoint(*[(-p[k] if k == axis else p[k]) for k in range(3)])


class _Joint(object):
    __slots__ = ("node", "short", "base", "ns", "pos", "label")

    def __init__(self, node, pos):
        self.node = node
        self.short = node.split("|")[-1]
        ns, _, self.base = self.short.rpartition(":")
        self.ns = ns + ":" if ns else ""
        self.pos = pos
        self.label = _joint_label(node)


def _influence_joints(skin_name, fn_skin):
    """Influences with their BIND-POSE world positions (from bindPreMatrix), so the
    match does not depend on the current pose."""
    infs = fn_skin.influenceObjects()
    out = []
    ident = om.MMatrix()
    for i in range(len(infs)):
        dag = infs[i]
        mm = None
        try:
            li = fn_skin.indexForInfluenceObject(dag)
            vals = cmds.getAttr("%s.bindPreMatrix[%d]" % (skin_name, li))
            m = om.MMatrix(vals)
            if not m.isEquivalent(ident):
                mm = m.inverse()
        except Exception:
            pass
        if mm is None:
            mm = dag.inclusiveMatrix()
        out.append(_Joint(dag.fullPathName(), om.MPoint(mm[12], mm[13], mm[14])))
    return out


def _tolerance_for(joints):
    if not joints:
        return 0.001
    bb = om.MBoundingBox()
    for j in joints:
        bb.expand(j.pos)
    return max(0.001, (bb.max - bb.min).length() * 0.002)


def _pick(src, cands, axis, tol, pairs):
    """Best mirror partner for src among cands. Returns index into cands or -1."""
    q = _mirror_point(src.pos, axis)
    dists = [c.pos.distanceTo(q) for c in cands]
    if not dists:
        return -1
    best_d = min(dists)
    if best_d > tol:
        return -1
    tied = [k for k, d in enumerate(dists) if d <= best_d + tol * 0.25]
    if len(tied) == 1:
        return tied[0]
    # several joints at the same spot (twist / helper joints): break the tie by name/label
    swapped = _swap_name(src.base, pairs)
    for k in tied:
        if swapped and cands[k].base == swapped:
            return k
    want = _mirror_label(src.label)
    for k in tied:
        if want and cands[k].label == want:
            return k
    return min(tied, key=lambda k: dists[k])


def _match_by_name(src, cands, axis, pairs):
    """Name/label partner: joint label first (nearest mirrored among same label), then
    side tokens in the name. Returns index into cands or -1."""
    want = _mirror_label(src.label)
    if want:
        hits = [k for k, c in enumerate(cands) if c.label == want]
        if hits:
            q = _mirror_point(src.pos, axis)
            return min(hits, key=lambda k: cands[k].pos.distanceTo(q))
    swapped = _swap_name(src.base, pairs)
    if swapped:
        target = src.ns + swapped
        for k, c in enumerate(cands):
            if c.short == target:
                return k
    return -1


def _scene_candidates(influences):
    """Joints in the same skeleton(s) that are NOT yet influences (positions = current)."""
    roots = set()
    for j in influences:
        parts = j.node.split("|")
        for d in range(2, len(parts) + 1):
            path = "|".join(parts[:d])
            if path and cmds.objExists(path) and cmds.nodeType(path) == "joint":
                roots.add(path)
                break
    if not roots:
        return []
    allj = set(cmds.listRelatives(list(roots), allDescendents=True, type="joint",
                                  fullPath=True) or [])
    allj.update(roots)
    have = set(j.node for j in influences)
    out = []
    for n in sorted(allj - have):
        p = cmds.xform(n, q=True, ws=True, t=True)
        out.append(_Joint(n, om.MPoint(p[0], p[1], p[2])))
    return out


def _influence_mirror_map(skin_name, skin_obj, pairs, axis, match="position"):
    """Return list: influence index -> mirror influence index.
    match = "position" (default) : mirrored bind-pose joint position.
    match = "name"               : joint label (side/type), then L/R name tokens.
    Mirror joints found in the skeleton but missing from the skinCluster are added."""
    for attempt in range(2):
        fn_skin = oma.MFnSkinCluster(skin_obj)
        joints = _influence_joints(skin_name, fn_skin)
        n = len(joints)
        tol = _tolerance_for(joints)
        mirror = [-1] * n
        for i, j in enumerate(joints):
            if match == "position":
                if abs(j.pos[axis]) <= tol:
                    mirror[i] = i
                else:
                    mirror[i] = _pick(j, joints, axis, tol, pairs)
            else:
                mirror[i] = _match_by_name(j, joints, axis, pairs)

        missing = [i for i in range(n) if mirror[i] < 0]
        if missing and attempt == 0:
            cands = _scene_candidates(joints)
            add = []
            for i in missing:
                if match == "position":
                    if abs(joints[i].pos[axis]) <= tol:
                        continue
                    k = _pick(joints[i], cands, axis, tol, pairs)
                else:
                    k = _match_by_name(joints[i], cands, axis, pairs)
                if k >= 0 and cands[k].node not in add:
                    add.append(cands[k].node)
            if add:
                for node in add:
                    cmds.skinCluster(skin_name, e=True, addInfluence=node, weight=0.0,
                                     lockWeights=False)
                    cmds.setAttr(node + ".liw", 0)
                om.MGlobal.displayInfo("%s: added missing mirror joints to %s: %s" % (
                    TOOL_NAME, skin_name, ", ".join(a.split("|")[-1] for a in add)))
                continue          # rebuild the map with the new influences
        break

    unmatched = [joints[i].short for i in range(n) if mirror[i] < 0]
    if unmatched:
        om.MGlobal.displayWarning("%s: no mirror joint found for %s - weights kept on the "
                                  "same joint." % (TOOL_NAME, ", ".join(unmatched)))
    return [m if m >= 0 else i for i, m in enumerate(mirror)]


def _build_remapper(mirror):
    """Return f(row) -> mirrored row (influence weights swapped L<->R)."""
    n = len(mirror)
    if n == 1:
        return lambda row: list(row)
    if sorted(mirror) == list(range(n)):          # true permutation -> C-speed gather
        inv = [0] * n
        for i, j in enumerate(mirror):
            inv[j] = i
        getter = operator.itemgetter(*inv)
        return lambda row: getter(row)

    def remap(row):                               # non-bijective map -> accumulate
        out = [0.0] * n
        for i, w in enumerate(row):
            if w:
                out[mirror[i]] += w
        return out
    return remap


# --------------------------------------------------------------------------------------
# Main entry points
# --------------------------------------------------------------------------------------
def _build_pairs_for_mesh(shape_path, indices, axis, direction, world_space,
                          use_bind_pose, tolerance, snap):
    lookup_path = shape_path
    if use_bind_pose:
        lookup_path = _orig_shape(shape_path) or shape_path
    look = _MirrorLookup(lookup_path, axis, world_space, tolerance, snap)
    sign = 1.0 if direction == "+" else -1.0

    pair = {}          # target vertex -> source vertex
    center = set()
    misses = 0
    for v in indices:
        a = look.coord(v) * sign
        if abs(a) <= tolerance:
            center.add(v)
            pair.setdefault(v, v)
            continue
        m = look.mirror(v)
        if m < 0:
            misses += 1
            continue
        if a > 0:      # on source side -> push to mirror
            pair[m] = v
        else:          # on target side -> pull from mirror
            pair[v] = m
    return pair, center, misses


_PLANES = {"YZ": "x", "XZ": "y", "XY": "z"}


def mirror_selected(plane="YZ", direction="+", match="position", axis=None,
                    world_space=False, use_bind_pose=True, tolerance=0.001, snap=True,
                    mirror_blend=True, pairs=DEFAULT_PAIRS):
    """Mirror skin weights of the selected vertices.

    plane         : "YZ" (default, mirrors across X), "XZ" (across Y) or "XY" (across Z).
    direction     : "+" (default) copies the positive side onto the negative side, "-" the opposite.
    match         : "position" (default) pairs joints by mirrored bind-pose position,
                    "name" pairs them by joint label (side/type) then L/R name tokens.
    axis          : optional override "x"/"y"/"z" instead of plane.
    direction     : "+" copies +axis side onto -axis side, "-" the opposite.
    world_space   : mirror plane through world origin (else the mesh's own origin).
    use_bind_pose : find mirror verts on the orig/intermediate shape (recommended).
    tolerance     : max distance for a vertex to count as the mirror partner.
    snap          : if no vertex within tolerance, use the closest one anyway.
    mirror_blend  : also mirror dual-quaternion blend weights (if skinningMethod is Weighted).
    pairs         : "L:R, Left:Right, ..." side-token pairs used to pair influences.
    """
    t0 = time.perf_counter()
    if axis is None:
        axis = _PLANES[plane.upper()]
    ax = _AXES[axis.lower()] if isinstance(axis, str) else int(axis)
    pair_list = _parse_pairs(pairs) if isinstance(pairs, str) else list(pairs)

    meshes = _gather_selection()
    if not meshes:
        om.MGlobal.displayWarning("%s: select vertices (or faces/edges/meshes) on a skinned "
                                  "mesh." % TOOL_NAME)
        return 0

    cmds.undoInfo(openChunk=True, chunkName="fastSkinMirror")
    try:
        return _mirror_meshes(meshes, t0, ax, direction, world_space, use_bind_pose,
                              tolerance, snap, mirror_blend, pair_list, match)
    finally:
        cmds.undoInfo(closeChunk=True)


def _mirror_meshes(meshes, t0, ax, direction, world_space, use_bind_pose, tolerance, snap,
                   mirror_blend, pair_list, match):
    ops = []
    total_set, total_miss = 0, 0
    for key, (shape_path, indices) in meshes.items():
        skin_obj, skin_name = _find_skin(shape_path)
        if skin_obj is None:
            om.MGlobal.displayWarning("%s: no skinCluster on %s - skipped." % (TOOL_NAME, key))
            continue
        fn_skin = oma.MFnSkinCluster(skin_obj)

        pair, center, misses = _build_pairs_for_mesh(
            shape_path, indices, ax, direction, world_space, use_bind_pose, tolerance, snap)
        total_miss += misses
        if not pair:
            continue

        mirror = _influence_mirror_map(skin_name, skin_obj, pair_list, ax, match)
        fn_skin = oma.MFnSkinCluster(skin_obj)       # refresh (influences may be added)
        remap = _build_remapper(mirror)
        n_inf = len(mirror)

        # --- one read for all sources --------------------------------------------------
        src_comp, src_elems = _make_comp(sorted(set(pair.values())))
        weights, n = fn_skin.getWeights(shape_path, src_comp)
        if n != n_inf:
            om.MGlobal.displayWarning("%s: influence count mismatch on %s - skipped."
                                      % (TOOL_NAME, skin_name))
            continue
        wl = list(weights)
        row_of = {v: r for r, v in enumerate(src_elems)}

        # --- build target weights -----------------------------------------------------
        tgt_comp, tgt_elems = _make_comp(sorted(pair.keys()))
        new_w = []
        extend = new_w.extend
        for t in tgt_elems:
            r = row_of[pair[t]] * n
            row = wl[r:r + n]
            mrow = remap(row)
            if t in center:
                extend([(a + b) * 0.5 for a, b in zip(row, mrow)])
            else:
                extend(mrow)

        new_blend = None
        if mirror_blend and cmds.getAttr(skin_name + ".skinningMethod") == 2:
            bw = list(fn_skin.getBlendWeights(shape_path, src_comp))
            new_blend = [bw[row_of[pair[t]]] for t in tgt_elems]

        ops.append(_WeightOp(skin_obj, shape_path, tgt_comp, n_inf, new_w, new_blend))
        total_set += len(tgt_elems)

    if not ops:
        om.MGlobal.displayWarning("%s: nothing mirrored (%d vertices had no mirror partner "
                                  "within tolerance)." % (TOOL_NAME, total_miss))
        return 0

    if _ensure_plugin():
        _stash().pending = ops
        getattr(cmds, PLUGIN_CMD)()
    else:
        for op in ops:
            op.apply()

    dt = (time.perf_counter() - t0) * 1000.0
    msg = "%s: mirrored %d vertices in %.1f ms" % (TOOL_NAME, total_set, dt)
    if total_miss:
        msg += "  (%d had no partner - raise tolerance or enable Snap)" % total_miss
    om.MGlobal.displayInfo(msg)
    _set_status(msg)
    return total_set


def select_mirror(axis="x", world_space=False, use_bind_pose=True, tolerance=0.001,
                  snap=False, add=False):
    """Select the mirror partners of the selected vertices."""
    ax = _AXES[axis.lower()] if isinstance(axis, str) else int(axis)
    out = []
    for key, (shape_path, indices) in _gather_selection().items():
        lookup_path = (_orig_shape(shape_path) if use_bind_pose else None) or shape_path
        look = _MirrorLookup(lookup_path, ax, world_space, tolerance, snap)
        verts = sorted({m for m in (look.mirror(v) for v in indices) if m >= 0})
        out.extend("%s.vtx[%d]" % (key, v) for v in verts)
    if out:
        cmds.select(out, add=add)
    return out


# --------------------------------------------------------------------------------------
# UI  -  mirror plane (XY / YZ / XZ), direction (+ to - / - to +), one Mirror button
# --------------------------------------------------------------------------------------
_UI = {}
_PLANE_ORDER = ["XY", "YZ", "XZ"]


def _set_status(msg):
    ctl = _UI.get("status")
    if ctl and cmds.text(ctl, exists=True):
        cmds.text(ctl, e=True, label=msg)


def _on_mirror(*_):
    plane = _PLANE_ORDER[cmds.radioButtonGrp(_UI["plane"], q=True, select=True) - 1]
    direction = "+" if cmds.radioButtonGrp(_UI["dir"], q=True, select=True) == 1 else "-"
    match = "position" if cmds.radioButtonGrp(_UI["match"], q=True, select=True) == 1 else "name"
    cmds.waitCursor(state=True)
    try:
        mirror_selected(plane=plane, direction=direction, match=match)
    finally:
        cmds.waitCursor(state=False)


def show():
    """Open the Fast Skin Mirror window."""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="Fast Skin Mirror", sizeable=False, widthHeight=(300, 155))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))
    cmds.separator(style="none", height=4)
    _UI["plane"] = cmds.radioButtonGrp(label="Mirror across", labelArray3=_PLANE_ORDER,
                                       numberOfRadioButtons=3, select=2,      # YZ default
                                       columnWidth4=(90, 55, 55, 55))
    _UI["dir"] = cmds.radioButtonGrp(label="Direction", labelArray2=["+ to -", "- to +"],
                                     numberOfRadioButtons=2, select=1,       # + to - default
                                     columnWidth3=(90, 80, 80))
    _UI["match"] = cmds.radioButtonGrp(label="Joint match", labelArray2=["Position", "Name / Label"],
                                       numberOfRadioButtons=2, select=1,     # Position default
                                       columnWidth3=(90, 80, 100))
    cmds.separator(height=6)
    cmds.button(label="Mirror", height=36, command=_on_mirror,
                backgroundColor=(0.32, 0.52, 0.42))
    _UI["status"] = cmds.text(label="Select vertices and press Mirror.", align="left")
    cmds.separator(style="none", height=4)
    cmds.showWindow(WINDOW)


if __name__ == "__main__":
    show()