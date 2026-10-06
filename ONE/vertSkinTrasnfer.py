"""
KRT Skin Tools
==============

A fast, single-file skinCluster toolkit for Maya (PySide2 / PySide6).

Features
--------
1.  Joint Weight Export / Import
      * pick joint(s), nothing else - mesh and affected vertices are
        auto-detected from each joint's own skinCluster connections
      * export writes only that joint's weights, only where it has any
      * import auto-matches the mesh, adds the joint as an influence if it
        is missing, and renormalizes the rest of the skin around it
      * sparse JSON (optionally gzipped) - small files, quick to parse

2.  Mirror Weights (fast)
      * in-place (one mesh) or mesh -> mesh, anywhere in the scene
      * position matching with a spatial hash (no scipy / numpy required)
      * identical-topology (vertex index) mode when the meshes match 1:1
      * optional bind / orig-shape sampling so a posed rig still mirrors right
      * editable left/right token pairs, auto-adds the mirrored influences

3.  Copy Skin - one source to many targets
      * rebinds targets with the source influence set, then copySkinWeights
      * full control over surface / influence association

Everything that touches weights goes through MFnSkinCluster.getWeights /
setWeights, so a whole mesh is read and written in a single API call instead of
per-vertex skinPercent commands.

Usage
-----
    import krt_skin_tools
    krt_skin_tools.show()

Author: generated for the KRT pipeline.
"""

import os
import sys
import json
import gzip
import math
import time
import traceback

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
    IS_PYSIDE6 = True
except ImportError:                                     # Maya 2022 - 2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
    IS_PYSIDE6 = False


# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #

TOOL_NAME = "KRT Skin Tools"
TOOL_VERSION = "1.0.0"
WINDOW_OBJECT = "KRT_SkinTools_Window"

FILE_FORMAT = "krtSkin"
FILE_VERSION = 2
FILE_FORMAT_JOINTS = "krtJointSkin"
FILE_VERSION_JOINTS = 1
WEIGHT_EPS = 1.0e-6

OPTVAR_DIR = "krtSkinTools_lastDir"

# Checked top to bottom, first match wins, so the specific tokens come first.
# Token shape decides where it may match:
#   "_L_"   both ends underscored -> anywhere in the name
#   "L_"    trailing underscore   -> only as a prefix
#   "_L"    leading underscore    -> only as a suffix
#   "Left"  bare word             -> anywhere
DEFAULT_MIRROR_PAIRS = [
    ("Left", "Right"),
    ("left", "right"),
    ("lf_", "rt_"),
    ("_L_", "_R_"),
    ("_l_", "_r_"),
    ("L_", "R_"),
    ("l_", "r_"),
    ("_L", "_R"),
    ("_l", "_r"),
]

SURFACE_ASSOC = ["closestPoint", "rayCast", "closestComponent"]
INFLUENCE_ASSOC = ["closestJoint", "closestBone", "label", "name", "oneToOne"]
SKIN_METHODS = ["Classic linear", "Dual quaternion", "Weight blended"]


class SkinError(RuntimeError):
    """Raised for any recoverable problem so the UI can report it cleanly."""


# --------------------------------------------------------------------------- #
#  Small name / DAG helpers
# --------------------------------------------------------------------------- #

def short_name(name):
    """'ns:grp|ns:joint1' -> 'joint1'."""
    return name.split("|")[-1].split(":")[-1]


def get_shape(node):
    """Return the long name of the first non-intermediate shape under *node*."""
    if not node or not cmds.objExists(node):
        return None
    if cmds.objectType(node, isAType="shape"):
        return cmds.ls(node, long=True)[0]
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
    if not shapes:
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                    fullPath=True) or []
    return shapes[0] if shapes else None


def find_skin_cluster(node):
    """Return the skinCluster deforming *node*, or None. Replaces the MEL
    findRelatedSkinCluster with a pure-Python history walk."""
    shape = get_shape(node) or node
    if not shape or not cmds.objExists(shape):
        return None
    history = cmds.listHistory(shape, pruneDagObjects=True, interestLevel=2) or []
    clusters = cmds.ls(history, type="skinCluster") or []
    return clusters[0] if clusters else None


def skin_clusters_for_joint(joint):
    """Every skinCluster in the scene that uses *joint* as an influence."""
    if not joint or not cmds.objExists(joint):
        return []
    conns = cmds.listConnections(joint, type="skinCluster",
                                 source=False, destination=True) or []
    return sorted(set(conns))


def meshes_for_joint(joint):
    """Mesh transforms deformed by any skinCluster that *joint* influences."""
    meshes = []
    for skin in skin_clusters_for_joint(joint):
        for geo in cmds.skinCluster(skin, query=True, geometry=True) or []:
            xform = (cmds.listRelatives(geo, parent=True, fullPath=True)
                     or [geo])[0]
            if xform not in meshes:
                meshes.append(xform)
    return meshes


def group_joints_by_mesh(joints):
    """Sort *joints* by the mesh(es) they actually influence.

    Returns (groups, unresolved) where groups is {mesh: [joint, ...]} and
    unresolved is the joints that are not an influence anywhere yet."""
    groups = {}
    unresolved = []
    for jnt in joints:
        meshes = meshes_for_joint(jnt)
        if not meshes:
            unresolved.append(jnt)
            continue
        for m in meshes:
            groups.setdefault(m, []).append(jnt)
    return groups, unresolved


def dag_path(name):
    """MDagPath for *name*, extended to its shape."""
    sel = om.MSelectionList()
    sel.add(name)
    path = sel.getDagPath(0)
    if path.apiType() == om.MFn.kTransform:
        path.extendToShape()
    return path


def depend_node(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDependNode(0)


def vertex_component(indices):
    """MObject component holding the given vertex ids."""
    fn = om.MFnSingleIndexedComponent()
    comp = fn.create(om.MFn.kMeshVertComponent)
    fn.addElements(om.MIntArray(list(indices)))
    return comp


def selected_vertex_ids(mesh=None):
    """Vertex ids currently selected. If *mesh* is given, only ids on it."""
    sel = cmds.ls(selection=True, flatten=True, long=True) or []
    wanted = None
    if mesh:
        wanted = short_name(get_shape(mesh) or mesh)
    ids = []
    for item in sel:
        if ".vtx[" not in item:
            continue
        node = item.split(".")[0]
        if wanted:
            node_short = short_name(get_shape(node) or node)
            if node_short != wanted:
                continue
        ids.append(int(item.split("[")[-1].split("]")[0]))
    return sorted(set(ids))


def selected_mesh():
    """First mesh in the selection (accepts components)."""
    sel = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    for node in sel:
        if get_shape(node):
            return node
    return None


def _swap_token(name, token, other):
    """Replace *token* with *other* honouring the token's position rule.
    Returns None when it does not apply."""
    if not token:
        return None
    lead = token.startswith("_")
    trail = token.endswith("_")
    if trail and not lead:                       # prefix token, e.g. "L_"
        if name.startswith(token):
            return other + name[len(token):]
        return None
    if lead and not trail:                       # suffix token, e.g. "_L"
        if name.endswith(token):
            return name[:-len(token)] + other
        return None
    if token in name:                            # infix or bare word
        return name.replace(token, other, 1)
    return None


def mirror_name(name, pairs):
    """Swap the first matching L/R token. Centre joints come back unchanged so
    they mirror onto themselves."""
    for left, right in pairs:
        swapped = _swap_token(name, left, right)
        if swapped is not None:
            return swapped
        swapped = _swap_token(name, right, left)
        if swapped is not None:
            return swapped
    return name


# --------------------------------------------------------------------------- #
#  Revert stack (OpenMaya setWeights is not part of Maya's undo queue)
# --------------------------------------------------------------------------- #

_REVERT_STACK = []
_REVERT_LIMIT = 12


def _push_revert(skin_name, shape, indices, logical, old_weights):
    _REVERT_STACK.append({
        "skin": skin_name,
        "shape": shape,
        "indices": list(indices),
        "logical": om.MIntArray(list(logical)),
        "weights": om.MDoubleArray(list(old_weights)),
        "time": time.time(),
    })
    while len(_REVERT_STACK) > _REVERT_LIMIT:
        _REVERT_STACK.pop(0)


def revert_last():
    """Restore the weights captured before the most recent operation."""
    if not _REVERT_STACK:
        raise SkinError("Nothing to revert.")
    entry = _REVERT_STACK.pop()
    if not cmds.objExists(entry["skin"]) or not cmds.objExists(entry["shape"]):
        raise SkinError("The node this operation touched no longer exists.")
    sel = om.MSelectionList()
    sel.add(entry["skin"])
    fn = oma.MFnSkinCluster(sel.getDependNode(0))
    path = dag_path(entry["shape"])
    comp = vertex_component(entry["indices"])
    fn.setWeights(path, comp, entry["logical"], entry["weights"], False)
    return "%s  (%d verts)" % (short_name(entry["shape"]), len(entry["indices"]))


def revert_depth():
    return len(_REVERT_STACK)


# --------------------------------------------------------------------------- #
#  SkinIO - the fast weight engine
# --------------------------------------------------------------------------- #

class SkinIO(object):
    """One mesh + its skinCluster, with bulk weight access.

    ``inf_short``  short influence names, in the order weights are laid out.
    ``logical``    matrix-plug indices for those influences (setWeights wants
                   logical indices, getWeights hands back physical order - the
                   two match on most rigs but not all, so both are kept).
    """

    def __init__(self, mesh):
        shape = get_shape(mesh)
        if not shape:
            raise SkinError("'%s' has no deformable shape." % mesh)
        skin = find_skin_cluster(shape)
        if not skin:
            raise SkinError("No skinCluster found on '%s'." % short_name(mesh))

        self.shape = shape
        self.skin = skin
        self.transform = (cmds.listRelatives(shape, parent=True, fullPath=True)
                          or [shape])[0]
        self.name = short_name(self.transform)
        self.dag = dag_path(shape)
        self.fn = oma.MFnSkinCluster(depend_node(skin))
        self.mesh_fn = om.MFnMesh(self.dag)
        self.vtx_count = self.mesh_fn.numVertices
        self.refresh_influences()

    # -- influences -------------------------------------------------------- #

    def refresh_influences(self):
        self.inf_paths = self.fn.influenceObjects()
        self.num_inf = len(self.inf_paths)
        self.inf_long = [p.fullPathName() for p in self.inf_paths]
        self.inf_short = [short_name(p.partialPathName()) for p in self.inf_paths]
        self.logical = om.MIntArray(
            [self.fn.indexForInfluenceObject(p) for p in self.inf_paths])
        self.by_short = {}
        for i, s in enumerate(self.inf_short):
            self.by_short.setdefault(s, i)

    def column(self, joint):
        """Physical weight-array column for a joint name (short or long)."""
        return self.by_short.get(short_name(joint))

    def add_influences(self, joints):
        """Add joints to the skinCluster with zero weight. Returns (added, missing)."""
        added, missing = [], []
        for jnt in joints:
            if self.column(jnt) is not None:
                continue
            node = jnt if cmds.objExists(jnt) else None
            if node is None:
                matches = cmds.ls(short_name(jnt), long=True) or []
                matches = [m for m in matches
                           if cmds.objectType(m, isAType="transform")]
                node = matches[0] if matches else None
            if not node:
                missing.append(short_name(jnt))
                continue
            cmds.skinCluster(self.skin, edit=True, addInfluence=node,
                             weight=0.0, lockWeights=True)
            try:
                cmds.setAttr("%s.liw" % node, False)
            except Exception:
                pass
            added.append(short_name(node))
        if added:
            self.refresh_influences()
        return added, missing

    # -- geometry ---------------------------------------------------------- #

    def points(self, world=False, use_orig=False):
        """Vertex positions as a list of (x, y, z) tuples."""
        if use_orig:
            pts = self._orig_points()
            if pts is not None:
                return pts
        space = om.MSpace.kWorld if world else om.MSpace.kObject
        return [(p.x, p.y, p.z) for p in self.mesh_fn.getPoints(space)]

    def _orig_points(self):
        """Positions from the skinCluster input (bind) geometry, object space."""
        try:
            filter_fn = oma.MFnGeometryFilter(depend_node(self.skin))
            index = filter_fn.indexForOutputShape(self.dag.node())
            sel = om.MSelectionList()
            sel.add("%s.input[%d].inputGeometry" % (self.skin, index))
            data = sel.getPlug(0).asMObject()
            fn = om.MFnMesh(data)
            return [(p.x, p.y, p.z) for p in fn.getPoints(om.MSpace.kObject)]
        except Exception:
            return None

    def bounding_diagonal(self, points):
        if not points:
            return 1.0
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        d = math.sqrt((max(xs) - min(xs)) ** 2 +
                      (max(ys) - min(ys)) ** 2 +
                      (max(zs) - min(zs)) ** 2)
        return d if d > 1e-6 else 1.0

    # -- weights ----------------------------------------------------------- #

    def get_weights(self, indices=None, columns=None):
        """Flat weight list. Row stride is ``len(columns)`` if given, else
        ``num_inf``. One API call regardless of vertex count."""
        indices = range(self.vtx_count) if indices is None else indices
        comp = vertex_component(indices)
        if columns is None:
            values, _ = self.fn.getWeights(self.dag, comp)
        else:
            logical = om.MIntArray([int(self.logical[c]) for c in columns])
            values = self.fn.getWeights(self.dag, comp, logical)
        return list(values)

    def set_weights(self, indices, values, normalize=True, record=True):
        """Write a full-width weight block (stride == num_inf) in one call."""
        indices = list(indices)
        comp = vertex_component(indices)
        arr = om.MDoubleArray(values)
        old = self.fn.setWeights(self.dag, comp, self.logical, arr,
                                 normalize, True)
        if record:
            _push_revert(self.skin, self.shape, indices, self.logical, old)
        return old

    # -- misc -------------------------------------------------------------- #

    def unlock_influences(self):
        for path in self.inf_paths:
            try:
                cmds.setAttr("%s.liw" % path.fullPathName(), False)
            except Exception:
                pass

    def info(self):
        return "%s  |  %s  |  %d verts  |  %d influences" % (
            self.name, self.skin, self.vtx_count, self.num_inf)


# --------------------------------------------------------------------------- #
#  Spatial hash - nearest point lookup without numpy / scipy
# --------------------------------------------------------------------------- #

class PointHash(object):
    def __init__(self, points, ids, cell):
        self.points = points
        self.cell = max(float(cell), 1e-6)
        self.inv = 1.0 / self.cell
        self.grid = {}
        inv = self.inv
        floor = math.floor
        grid = self.grid
        for i in ids:
            x, y, z = points[i]
            key = (int(floor(x * inv)), int(floor(y * inv)), int(floor(z * inv)))
            bucket = grid.get(key)
            if bucket is None:
                grid[key] = [i]
            else:
                bucket.append(i)

    def nearest(self, p, tol, expand=1):
        """Closest stored id to *p* within *tol*, else -1."""
        px, py, pz = p
        inv = self.inv
        floor = math.floor
        cx = int(floor(px * inv))
        cy = int(floor(py * inv))
        cz = int(floor(pz * inv))
        r = max(1, int(math.ceil(tol * inv))) * max(1, expand)
        best = -1
        best_d = tol * tol
        grid = self.grid
        pts = self.points
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                for z in range(cz - r, cz + r + 1):
                    bucket = grid.get((x, y, z))
                    if not bucket:
                        continue
                    for i in bucket:
                        qx, qy, qz = pts[i]
                        dx = qx - px
                        dy = qy - py
                        dz = qz - pz
                        d = dx * dx + dy * dy + dz * dz
                        if d < best_d:
                            best_d = d
                            best = i
        return best


# --------------------------------------------------------------------------- #
#  Export / Import
# --------------------------------------------------------------------------- #

def _open_write(path):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "wt")
    return open(path, "w")


def _open_read(path):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path, "r")


def _build_export_data(mesh, vertex_indices=None, joints=None,
                       precision=6, log=print, progress=None, chunk=25000):
    """Read weights straight from the skinCluster and return a plain data
    dict, ready to be written to disk (or embedded in a multi-mesh file).
    Does not touch the filesystem.

    Reads happen in chunks of *chunk* vertices, each followed by a
    *progress* callback, instead of one single call across the whole mesh.
    A dense mesh (heavy jewelry, cloth, etc.) can otherwise mean one huge
    blocking OpenMaya call with no opportunity for Maya's UI thread to
    breathe, which is what a Windows 'not responding' / crash dialog
    usually means here - the fix is smaller, interruptible calls."""
    skin = SkinIO(mesh)

    if joints:
        columns, missing = [], []
        for jnt in joints:
            col = skin.column(jnt)
            if col is None:
                missing.append(short_name(jnt))
            elif col not in columns:
                columns.append(col)
        if missing:
            log("Not influences of %s, skipped: %s"
                % (skin.skin, ", ".join(missing)), "warn")
        if not columns:
            raise SkinError("None of the requested joints influence this mesh.")
    else:
        columns = list(range(skin.num_inf))

    if vertex_indices is None:
        indices = list(range(skin.vtx_count))
        scope = "mesh"
    else:
        indices = [i for i in sorted(set(vertex_indices))
                   if 0 <= i < skin.vtx_count]
        scope = "vertices"
        if not indices:
            raise SkinError("No valid vertices to export.")

    if len(indices) > 150000:
        log("%s: %d verts - this may take a while." % (skin.name, len(indices)),
            "warn")

    stride = len(columns)
    rows = []
    keep = []
    rnd = round
    total = len(indices)

    for start in range(0, total, chunk):
        block = indices[start:start + chunk]
        flat = skin.get_weights(block, columns)
        for n in range(len(block)):
            base = n * stride
            pairs = []
            for c in range(stride):
                w = flat[base + c]
                if w > WEIGHT_EPS:
                    pairs.append(c)
                    pairs.append(rnd(w, precision))
            if pairs:
                rows.append(pairs)
                keep.append(block[n])
        if progress:
            progress(min(1.0, float(start + chunk) / total),
                     "Reading %s..." % skin.name)

    data = {
        "format": FILE_FORMAT,
        "version": FILE_VERSION,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mayaVersion": cmds.about(version=True),
        "mesh": skin.name,
        "meshShape": short_name(skin.shape),
        "skinCluster": skin.skin,
        "vertexCount": skin.vtx_count,
        "scope": scope,
        "influenceScope": "filtered" if joints else "all",
        "influences": [skin.inf_short[c] for c in columns],
        "influencesLong": [skin.inf_long[c] for c in columns],
        "skinningMethod": cmds.getAttr("%s.skinningMethod" % skin.skin),
        "maxInfluences": cmds.getAttr("%s.maxInfluences" % skin.skin),
        "normalizeWeights": cmds.getAttr("%s.normalizeWeights" % skin.skin),
        "indices": keep,
        "weights": rows,
    }
    return data, stride


def _write_json(file_path, data, pretty=False):
    folder = os.path.dirname(file_path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with _open_write(file_path) as fh:
        if pretty:
            json.dump(data, fh, indent=2)
        else:
            json.dump(data, fh, separators=(",", ":"))


def export_weights(mesh, file_path, vertex_indices=None, joints=None,
                   precision=6, pretty=False, log=print, progress=None):
    """Write a sparse weight file.

    mesh            transform or shape
    vertex_indices  None for the whole mesh, else a list of vertex ids
    joints          None for every influence, else the joints to record
    """
    data, stride = _build_export_data(mesh, vertex_indices=vertex_indices,
                                      joints=joints, precision=precision,
                                      log=log, progress=progress)
    _write_json(file_path, data, pretty=pretty)
    log("Exported %d verts x %d influences -> %s"
        % (len(data["indices"]), stride, file_path), "ok")
    return data


def export_joint_weights(joints, file_path, log=print, progress=None):
    """Export only the recorded weights of *joints*, auto-detecting each
    joint's mesh from its skinCluster connections. No vertex or influence
    scope to set: every joint is exported against only the mesh(es) it
    actually influences, and only the vertices it actually touches.

    One or more joints can land on different meshes; every affected mesh is
    bundled into the single output file. A mesh that fails to read (or
    turns out to have no matching data) is skipped with a warning rather
    than losing the rest of the export.
    """
    joints = sorted(set(short_name(j) for j in joints))
    if not joints:
        raise SkinError("No joints given.")

    groups, unresolved = group_joints_by_mesh(joints)
    if unresolved:
        log("Not an influence on anything yet, skipped: %s"
            % ", ".join(short_name(j) for j in unresolved), "warn")
    if not groups:
        raise SkinError(
            "None of the selected joints influence a skinned mesh.")

    mesh_list = list(groups.items())
    mesh_entries = []
    total_verts = 0
    all_joints = []
    failed = []

    for i, (mesh, mesh_joints) in enumerate(mesh_list):

        def mesh_progress(frac, msg, i=i, n=len(mesh_list)):
            if progress:
                progress((i + frac) / n, msg)

        try:
            data, stride = _build_export_data(
                mesh, vertex_indices=None, joints=mesh_joints, precision=6,
                log=log, progress=mesh_progress)
        except SkinError as exc:
            failed.append("%s (%s)" % (short_name(mesh), exc))
            log("Skipped %s: %s" % (short_name(mesh), exc), "error")
            continue
        mesh_entries.append(data)
        total_verts += len(data["indices"])
        all_joints.extend(data["influences"])
        log("%s: %d verts x %d joint(s)"
            % (data["mesh"], len(data["indices"]), stride))

    if not mesh_entries:
        raise SkinError("Nothing could be read from any mesh.")

    container = {
        "format": FILE_FORMAT_JOINTS,
        "version": FILE_VERSION_JOINTS,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mayaVersion": cmds.about(version=True),
        "joints": sorted(set(all_joints)),
        "meshes": mesh_entries,
    }
    _write_json(file_path, container, pretty=False)
    if failed:
        log("Skipped %d mesh(es): %s" % (len(failed), "; ".join(failed)),
            "warn")
    log("Exported %d joint(s) across %d mesh(es), %d vert writes -> %s"
        % (len(container["joints"]), len(mesh_entries), total_verts,
           file_path), "ok")
    return container


def read_weight_file(file_path):
    if not os.path.isfile(file_path):
        raise SkinError("File not found: %s" % file_path)
    try:
        with _open_read(file_path) as fh:
            data = json.load(fh)
    except Exception as exc:
        raise SkinError("Could not read '%s': %s" % (file_path, exc))
    if data.get("format") not in (FILE_FORMAT, FILE_FORMAT_JOINTS):
        # tolerate the older {"mesh_name":..., "weights": {...}} layout
        if "weights" in data and "mesh_name" in data:
            data = _upgrade_legacy(data)
        else:
            raise SkinError("'%s' is not a KRT skin file." % file_path)
    return data


def _upgrade_legacy(old):
    """Convert the previous per-vertex dict format to the sparse layout."""
    names = []
    lookup = {}
    indices, rows = [], []
    for vtx, weights in sorted(old.get("weights", {}).items(), key=lambda kv: int(kv[0])):
        pairs = []
        for jnt, val in weights.items():
            if jnt not in lookup:
                lookup[jnt] = len(names)
                names.append(jnt)
            pairs.append(lookup[jnt])
            pairs.append(float(val))
        if pairs:
            indices.append(int(vtx))
            rows.append(pairs)
    return {
        "format": FILE_FORMAT, "version": FILE_VERSION,
        "mesh": old.get("mesh_name", ""), "skinCluster": "",
        "vertexCount": 0, "scope": "vertices", "influenceScope": "filtered",
        "influences": names, "influencesLong": names,
        "indices": indices, "weights": rows,
    }


def _apply_mesh_entry(data, mesh=None, vertex_indices=None,
                      mode="renormalize", add_missing=True, log=print,
                      progress=None):
    """Apply one already-loaded mesh weight-data dict to the scene.

    mode
        'renormalize'  write the recorded joints, rescale everything else so
                       each vertex still sums to 1  (default)
        'zero_others'  only the recorded joints keep weight
        'raw'          write the recorded joints, leave the rest untouched
    """
    target = mesh or data.get("mesh")
    if not target or not cmds.objExists(target):
        matches = cmds.ls(short_name(target or ""), long=True) or []
        target = matches[0] if matches else None
    if not target:
        raise SkinError("Target mesh '%s' is not in the scene."
                        % (mesh or data.get("mesh")))

    skin = SkinIO(target)

    file_inf = data.get("influences", [])
    if add_missing:
        added, missing = skin.add_influences(file_inf)
        if added:
            log("Added %d influence(s): %s" % (len(added), ", ".join(added)), "ok")
        if missing:
            log("Not in the scene, their weights are dropped: %s"
                % ", ".join(missing), "warn")

    col_map = {}
    unresolved = []
    for i, jnt in enumerate(file_inf):
        col = skin.column(jnt)
        if col is None:
            unresolved.append(jnt)
        else:
            col_map[i] = col
    if not col_map:
        raise SkinError("None of the file's joints influence '%s'." % skin.name)
    if unresolved and not add_missing:
        log("Skipped %d joint(s) missing from the skinCluster: %s"
            % (len(unresolved), ", ".join(unresolved[:8])), "warn")

    file_indices = data.get("indices", [])
    rows = data.get("weights", [])

    wanted = None
    if vertex_indices is not None:
        wanted = set(vertex_indices)

    use_pos, use_rows = [], []
    for n, vtx in enumerate(file_indices):
        if vtx >= skin.vtx_count:
            continue
        if wanted is not None and vtx not in wanted:
            continue
        use_pos.append(vtx)
        use_rows.append(rows[n])

    if not use_pos:
        raise SkinError("No vertices from the file apply to this mesh.")

    if data.get("vertexCount") and data["vertexCount"] != skin.vtx_count:
        log("Vertex count differs (file %s, mesh %d) - matching by index."
            % (data["vertexCount"], skin.vtx_count), "warn")

    num_inf = skin.num_inf
    current = skin.get_weights(use_pos)
    touched = sorted(set(col_map.values()))
    touched_set = set(touched)
    others = [c for c in range(num_inf) if c not in touched_set]

    total = len(use_pos)
    step = max(1, total // 50)

    for n in range(total):
        base = n * num_inf
        pairs = use_rows[n]

        incoming = 0.0
        row_new = {}
        for k in range(0, len(pairs), 2):
            col = col_map.get(int(pairs[k]))
            if col is None:
                continue
            val = float(pairs[k + 1])
            row_new[col] = row_new.get(col, 0.0) + val
            incoming += val

        if mode == "zero_others":
            for c in range(num_inf):
                current[base + c] = 0.0
            scale = (1.0 / incoming) if incoming > WEIGHT_EPS else 0.0
            for col, val in row_new.items():
                current[base + col] = val * scale

        elif mode == "raw":
            for col, val in row_new.items():
                current[base + col] = val

        else:  # renormalize
            rest = 0.0
            for c in others:
                rest += current[base + c]
            remaining = 1.0 - incoming
            if remaining < 0.0:
                remaining = 0.0
            for col in touched:
                current[base + col] = row_new.get(col, 0.0)
            if rest > WEIGHT_EPS:
                scale = remaining / rest
                for c in others:
                    current[base + c] *= scale
            elif incoming > WEIGHT_EPS:
                scale = 1.0 / incoming
                for col, val in row_new.items():
                    current[base + col] = val * scale

        if progress and n % step == 0:
            progress(float(n) / total, "Importing weights...")

    skin.unlock_influences()
    skin.set_weights(use_pos, current, normalize=(mode != "raw"))

    log("Imported %d vertices onto '%s' (%s)."
        % (len(use_pos), skin.name, mode), "ok")
    return len(use_pos)


def import_weights(file_path, mesh=None, vertex_indices=None,
                   mode="renormalize", add_missing=True, log=print,
                   progress=None):
    """Read a weight file from disk and apply it (single-mesh krtSkin files,
    or the first mesh of a krtJointSkin container)."""
    data = read_weight_file(file_path)
    if data.get("format") == FILE_FORMAT_JOINTS:
        entries = data.get("meshes", [])
        if not entries:
            raise SkinError("File has no weight data.")
        data = entries[0]
    return _apply_mesh_entry(data, mesh=mesh, vertex_indices=vertex_indices,
                             mode=mode, add_missing=add_missing, log=log,
                             progress=progress)


def import_joint_weights(file_path, log=print, progress=None):
    """Apply every mesh block in a joint-skin file (written by
    export_joint_weights, or a plain single-mesh krtSkin file).

    Each mesh is auto-matched in the current scene by its stored name, any
    joint missing from that mesh's skinCluster is added automatically, and
    the recorded joints are renormalized against the mesh's other
    influences. Always applies to every vertex recorded in the file.
    """
    data = read_weight_file(file_path)
    entries = (data.get("meshes", [])
              if data.get("format") == FILE_FORMAT_JOINTS else [data])
    if not entries:
        raise SkinError("File has no weight data.")

    total_verts = 0
    joints_done = set()
    failed = []
    for i, entry in enumerate(entries):
        if progress:
            progress(float(i) / len(entries),
                     "Importing %s..." % entry.get("mesh", "?"))
        try:
            n = _apply_mesh_entry(entry, mesh=None, vertex_indices=None,
                                  mode="renormalize", add_missing=True,
                                  log=log)
        except SkinError as exc:
            failed.append("%s (%s)" % (entry.get("mesh", "?"), exc))
            continue
        except Exception as exc:
            failed.append("%s (%s)" % (entry.get("mesh", "?"), exc))
            sys.stderr.write(traceback.format_exc())
            continue
        total_verts += n
        joints_done.update(entry.get("influences", []))

    if failed:
        log("Failed on %d mesh(es): %s" % (len(failed), "; ".join(failed)),
            "error")
    log("Joint-skin import done: %d joint(s), %d vertex write(s) across "
        "%d mesh(es)." % (len(joints_done), total_verts,
                          len(entries) - len(failed)), "ok")
    return total_verts


# --------------------------------------------------------------------------- #
#  Mirror
# --------------------------------------------------------------------------- #

def mirror_weights(source_mesh, target_mesh=None, axis="x", direction="+ to -",
                   match="position", tolerance=0.01, center_tolerance=0.001,
                   include_center=True, world_space=False, use_orig=False,
                   pairs=None, add_missing=True, relaxed=True,
                   log=print, progress=None):
    """Mirror skin weights.

    source_mesh / target_mesh
        pass the same mesh (or leave target None) to mirror in place;
        pass two meshes to mirror across objects.
    direction
        '+ to -', '- to +' or 'flip' (swap both sides at once)
    match
        'position' (spatial hash, works on any topology) or
        'index' (1:1 vertex ids, only when the counts match)
    """
    pairs = pairs or DEFAULT_MIRROR_PAIRS
    t0 = time.time()

    src = SkinIO(source_mesh)
    same_mesh = (not target_mesh) or (get_shape(target_mesh) == src.shape)
    tgt = src if same_mesh else SkinIO(target_mesh)

    axis_id = {"x": 0, "y": 1, "z": 2}[axis.lower()]

    # ---- influence mapping ------------------------------------------------ #
    wanted = []
    for name in src.inf_short:
        m = mirror_name(name, pairs)
        if m != name:
            wanted.append(m)
    if add_missing and wanted:
        added, missing = tgt.add_influences(wanted)
        if added:
            log("Added %d mirrored influence(s): %s"
                % (len(added), ", ".join(added[:10])), "ok")
        if missing:
            log("Mirrored joints not in the scene: %s"
                % ", ".join(sorted(set(missing))[:10]), "warn")

    col_map = {}
    fallback = []
    for k, name in enumerate(src.inf_short):
        m = mirror_name(name, pairs)
        col = tgt.column(m)
        if col is None:
            col = tgt.column(name)
            if col is not None and m != name:
                fallback.append(name)
        if col is not None:
            col_map[k] = col
    if not col_map:
        raise SkinError("No source influence could be matched on the target.")
    if fallback:
        log("No mirrored joint for %d influence(s), kept on the original: %s"
            % (len(fallback), ", ".join(sorted(set(fallback))[:8])), "warn")

    # ---- vertex pairing --------------------------------------------------- #
    if progress:
        progress(0.05, "Sampling points...")

    src_pts = src.points(world=world_space, use_orig=use_orig)
    tgt_pts = src_pts if same_mesh else tgt.points(world=world_space,
                                                   use_orig=use_orig)

    ctol = float(center_tolerance)
    if same_mesh:
        if direction == "flip":
            tgt_ids = list(range(tgt.vtx_count))
        elif direction == "- to +":
            tgt_ids = [i for i, p in enumerate(tgt_pts) if p[axis_id] > ctol]
        else:
            tgt_ids = [i for i, p in enumerate(tgt_pts) if p[axis_id] < -ctol]
        if include_center and direction != "flip":
            tgt_ids += [i for i, p in enumerate(tgt_pts)
                        if abs(p[axis_id]) <= ctol]
            tgt_ids = sorted(set(tgt_ids))
    else:
        tgt_ids = list(range(tgt.vtx_count))

    if not tgt_ids:
        raise SkinError("No vertices on the receiving side - check the axis, "
                        "the direction or the centre tolerance.")

    pair_map = {}
    unmatched = []

    if match == "index":
        if src.vtx_count != tgt.vtx_count:
            raise SkinError("Index mirror needs identical vertex counts "
                            "(%d vs %d)." % (src.vtx_count, tgt.vtx_count))
        for i in tgt_ids:
            pair_map[i] = i
    else:
        if progress:
            progress(0.15, "Building point hash...")
        if same_mesh and direction != "flip":
            src_ids = [i for i in range(src.vtx_count)
                       if (src_pts[i][axis_id] > ctol if direction != "- to +"
                           else src_pts[i][axis_id] < -ctol)]
            if include_center:
                src_ids += [i for i in range(src.vtx_count)
                            if abs(src_pts[i][axis_id]) <= ctol]
        else:
            src_ids = list(range(src.vtx_count))

        diag = src.bounding_diagonal(src_pts)
        cell = max(tolerance * 2.0, diag / 64.0)
        grid = PointHash(src_pts, src_ids, cell)

        total = len(tgt_ids)
        step = max(1, total // 40)
        for n, i in enumerate(tgt_ids):
            p = list(tgt_pts[i])
            p[axis_id] = -p[axis_id]
            found = grid.nearest(p, tolerance)
            if found < 0 and relaxed:
                found = grid.nearest(p, tolerance * 20.0, expand=2)
            if found < 0:
                unmatched.append(i)
            else:
                pair_map[i] = found
            if progress and n % step == 0:
                progress(0.15 + 0.5 * (float(n) / total), "Matching vertices...")

    if not pair_map:
        raise SkinError("No vertex pairs found. Raise the tolerance or switch "
                        "to world space.")
    if unmatched:
        log("%d vertex(es) had no mirror within tolerance and were left alone."
            % len(unmatched), "warn")

    # ---- read the source rows we need (snapshot, so 'flip' is safe) ------- #
    if progress:
        progress(0.7, "Reading source weights...")

    needed = sorted(set(pair_map.values()))
    src_flat = src.get_weights(needed)
    src_row_of = {}
    n_src_inf = src.num_inf
    for pos, vtx in enumerate(needed):
        src_row_of[vtx] = pos * n_src_inf

    # ---- build and write the target block --------------------------------- #
    if progress:
        progress(0.8, "Writing weights...")

    write_ids = [i for i in tgt_ids if i in pair_map]
    n_tgt_inf = tgt.num_inf
    out = [0.0] * (len(write_ids) * n_tgt_inf)

    for n, vtx in enumerate(write_ids):
        base_out = n * n_tgt_inf
        base_src = src_row_of[pair_map[vtx]]
        total_w = 0.0
        for k, col in col_map.items():
            w = src_flat[base_src + k]
            if w > WEIGHT_EPS:
                out[base_out + col] += w
                total_w += w
        if total_w > WEIGHT_EPS and abs(total_w - 1.0) > 1e-5:
            scale = 1.0 / total_w
            for c in range(n_tgt_inf):
                out[base_out + c] *= scale

    tgt.unlock_influences()
    tgt.set_weights(write_ids, out, normalize=True)

    if progress:
        progress(1.0, "Done.")
    log("Mirrored %d vertices  %s -> %s  (%.2fs)"
        % (len(write_ids), src.name, tgt.name, time.time() - t0), "ok")
    return len(write_ids)


# --------------------------------------------------------------------------- #
#  Copy skin - one source to many targets
# --------------------------------------------------------------------------- #

def copy_skin(source, targets, rebind=True,
              surface_association="closestPoint",
              influence_association=("closestJoint", "oneToOne", "name"),
              normalize=True, skinning_method=None, max_influences=None,
              obey_max_influences=None, dropoff=4.0, log=print, progress=None):
    """Bind every target to the source's influence set and transfer weights."""
    src_skin = find_skin_cluster(source)
    if not src_skin:
        raise SkinError("Source '%s' has no skinCluster." % short_name(source))

    joints = cmds.skinCluster(src_skin, query=True, influence=True) or []
    if not joints:
        raise SkinError("Source skinCluster has no influences.")

    if skinning_method is None:
        skinning_method = cmds.getAttr("%s.skinningMethod" % src_skin)
    if max_influences is None:
        max_influences = cmds.getAttr("%s.maxInfluences" % src_skin)
    if obey_max_influences is None:
        obey_max_influences = bool(cmds.getAttr("%s.maintainMaxInfluences" % src_skin))

    inf_assoc = [a for a in influence_association if a]
    restore = cmds.ls(selection=True, long=True)
    done, failed = [], []

    cmds.undoInfo(openChunk=True, chunkName="KRT Copy Skin")
    try:
        total = max(1, len(targets))
        for n, target in enumerate(targets):
            if progress:
                progress(float(n) / total, "Copying to %s..." % short_name(target))
            try:
                shape = get_shape(target)
                if not shape:
                    failed.append("%s (no shape)" % short_name(target))
                    continue

                existing = find_skin_cluster(shape)
                if existing and rebind:
                    cmds.delete(existing)
                    existing = None

                if existing:
                    dst_skin = existing
                    have = set(short_name(j) for j in
                               (cmds.skinCluster(dst_skin, q=True, inf=True) or []))
                    for jnt in joints:
                        if short_name(jnt) not in have:
                            cmds.skinCluster(dst_skin, edit=True, addInfluence=jnt,
                                             weight=0.0)
                else:
                    dst_skin = cmds.skinCluster(
                        list(joints) + [target],
                        toSelectedBones=True,
                        bindMethod=0,
                        skinMethod=skinning_method,
                        maximumInfluences=max_influences,
                        obeyMaxInfluences=obey_max_influences,
                        dropoffRate=dropoff,
                        normalizeWeights=1,
                        name="%s_skinCluster" % short_name(target),
                    )[0]
                    cmds.refresh()

                cmds.copySkinWeights(
                    sourceSkin=src_skin,
                    destinationSkin=dst_skin,
                    noMirror=True,
                    surfaceAssociation=surface_association,
                    influenceAssociation=inf_assoc,
                    normalize=normalize,
                )
                done.append(short_name(target))
                log("  %s  ->  %s" % (short_name(target), dst_skin))
            except Exception as exc:
                failed.append("%s (%s)" % (short_name(target), exc))
    finally:
        cmds.undoInfo(closeChunk=True)
        if restore:
            try:
                cmds.select(restore, replace=True)
            except Exception:
                cmds.select(clear=True)

    if progress:
        progress(1.0, "Done.")
    log("Copied skin from '%s' to %d mesh(es)." % (short_name(source), len(done)),
        "ok")
    if failed:
        log("Failed: %s" % "; ".join(failed), "error")
    return done, failed


# --------------------------------------------------------------------------- #
#  UI
# --------------------------------------------------------------------------- #

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


STYLE = """
QGroupBox {
    border: 1px solid #3b3b3b; border-radius: 3px;
    margin-top: 9px; padding-top: 8px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton#accent {
    background-color: #4c7ea8; color: #f0f0f0;
    border: 1px solid #2f5570; border-radius: 3px; padding: 6px 10px;
    font-weight: bold;
}
QPushButton#accent:hover { background-color: #5a91be; }
QPushButton#accent:pressed { background-color: #3d6688; }
QPushButton#danger {
    background-color: #8a4b4b; color: #f0f0f0;
    border: 1px solid #5e3232; border-radius: 3px; padding: 5px 10px;
}
QPushButton#danger:hover { background-color: #a05858; }
QPlainTextEdit#log {
    background-color: #232323; border: 1px solid #3b3b3b;
    font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 11px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {
    border: 1px solid #3b3b3b; border-radius: 2px; padding: 2px 4px;
}
"""


class NodeField(QtWidgets.QWidget):
    """Line edit + '<' button that grabs the current selection."""

    changed = QtCore.Signal()

    def __init__(self, placeholder="", parent=None):
        super(NodeField, self).__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.btn = QtWidgets.QPushButton("<")
        self.btn.setFixedWidth(26)
        self.btn.setToolTip("Load the selected mesh")
        lay.addWidget(self.edit)
        lay.addWidget(self.btn)
        self.btn.clicked.connect(self._grab)
        self.edit.editingFinished.connect(self.changed.emit)

    def _grab(self):
        mesh = selected_mesh()
        if mesh:
            self.edit.setText(short_name(mesh))
            self.changed.emit()
        else:
            cmds.warning("Select a mesh first.")

    def text(self):
        return self.edit.text().strip()

    def setText(self, value):
        self.edit.setText(value)


class SkinToolsUI(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(SkinToolsUI, self).__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_OBJECT)
        self.setWindowTitle("%s  v%s" % (TOOL_NAME, TOOL_VERSION))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setMinimumWidth(470)
        self.resize(520, 780)
        self.setStyleSheet(STYLE)

        self._build()
        self._connect()
        self.log("Ready. %s v%s" % (TOOL_NAME, TOOL_VERSION))

    # ---------------------------------------------------------------- build #

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._tab_io(), "Export / Import")
        self.tabs.addTab(self._tab_mirror(), "Mirror")
        self.tabs.addTab(self._tab_copy(), "Copy Skin")
        root.addWidget(self.tabs)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(16)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setObjectName("log")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        root.addWidget(self.log_box)

        bottom = QtWidgets.QHBoxLayout()
        self.btn_revert = QtWidgets.QPushButton("Revert Last Weight Op")
        self.btn_revert.setObjectName("danger")
        self.btn_revert.setToolTip(
            "OpenMaya weight writes bypass Maya's undo queue.\n"
            "This restores the weights captured before the last operation.")
        self.btn_clear_log = QtWidgets.QPushButton("Clear Log")
        bottom.addWidget(self.btn_revert)
        bottom.addStretch()
        bottom.addWidget(self.btn_clear_log)
        root.addLayout(bottom)

    # -- tab 1 --------------------------------------------------------- #

    def _tab_io(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setSpacing(6)

        # joints - this list *is* the scope. Export reads only these
        # joints' own weights; the mesh and the affected vertices are
        # detected automatically from each joint's skinCluster.
        grp_j = QtWidgets.QGroupBox("Joints")
        v = QtWidgets.QVBoxLayout(grp_j)

        self.io_joints = QtWidgets.QListWidget()
        self.io_joints.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.io_joints.setMaximumHeight(140)
        v.addWidget(self.io_joints)

        jrow = QtWidgets.QHBoxLayout()
        self.btn_j_add = QtWidgets.QPushButton("Add Selected Joints")
        self.btn_j_del = QtWidgets.QPushButton("Remove")
        self.btn_j_clr = QtWidgets.QPushButton("Clear")
        for b in (self.btn_j_add, self.btn_j_del, self.btn_j_clr):
            jrow.addWidget(b)
        v.addLayout(jrow)

        self.io_info = QtWidgets.QLabel(
            "Select joint(s) in the scene, then Add Selected Joints.")
        self.io_info.setStyleSheet("color:#9a9a9a;")
        self.io_info.setWordWrap(True)
        v.addWidget(self.io_info)
        lay.addWidget(grp_j)

        # file
        grp_file = QtWidgets.QGroupBox("Weight File")
        fv = QtWidgets.QVBoxLayout(grp_file)
        frow = QtWidgets.QHBoxLayout()
        self.io_path = QtWidgets.QLineEdit()
        self.io_path.setPlaceholderText(r"C:\... \weights.json   (.gz also works)")
        self.btn_browse_save = QtWidgets.QPushButton("Save As...")
        self.btn_browse_open = QtWidgets.QPushButton("Open...")
        frow.addWidget(self.io_path)
        frow.addWidget(self.btn_browse_save)
        frow.addWidget(self.btn_browse_open)
        fv.addLayout(frow)
        lay.addWidget(grp_file)

        brow = QtWidgets.QHBoxLayout()
        self.btn_export = QtWidgets.QPushButton("Export Weights")
        self.btn_export.setObjectName("accent")
        self.btn_export.setToolTip(
            "Exports only the joints listed above: their own weights, on "
            "whichever mesh(es) they influence, for only the vertices they "
            "actually touch.")
        self.btn_import = QtWidgets.QPushButton("Import Weights")
        self.btn_import.setObjectName("accent")
        self.btn_import.setToolTip(
            "Applies every joint recorded in the file to its matching mesh "
            "in this scene, adding the joint as an influence if needed.")
        brow.addWidget(self.btn_export)
        brow.addWidget(self.btn_import)
        lay.addLayout(brow)

        lay.addStretch()
        return page

    # -- tab 2 --------------------------------------------------------- #

    def _tab_mirror(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setSpacing(6)

        grp = QtWidgets.QGroupBox("Meshes")
        f = QtWidgets.QFormLayout(grp)
        self.mir_mode = QtWidgets.QComboBox()
        self.mir_mode.addItems(["Mirror on one mesh", "Mesh to mesh"])
        f.addRow("Mode:", self.mir_mode)
        self.mir_src = NodeField("source mesh")
        self.mir_tgt = NodeField("target mesh")
        f.addRow("Source:", self.mir_src)
        f.addRow("Target:", self.mir_tgt)
        self.mir_tgt.setEnabled(False)
        lay.addWidget(grp)

        grp2 = QtWidgets.QGroupBox("Mirror Plane")
        g = QtWidgets.QGridLayout(grp2)
        g.addWidget(QtWidgets.QLabel("Axis:"), 0, 0)
        self.mir_axis = QtWidgets.QComboBox()
        self.mir_axis.addItems(["X", "Y", "Z"])
        g.addWidget(self.mir_axis, 0, 1)
        g.addWidget(QtWidgets.QLabel("Direction:"), 0, 2)
        self.mir_dir = QtWidgets.QComboBox()
        self.mir_dir.addItems(["+ to -", "- to +", "flip"])
        g.addWidget(self.mir_dir, 0, 3)

        g.addWidget(QtWidgets.QLabel("Match by:"), 1, 0)
        self.mir_match = QtWidgets.QComboBox()
        self.mir_match.addItems(["Position (any topology)",
                                 "Vertex index (identical topology)"])
        g.addWidget(self.mir_match, 1, 1, 1, 3)

        g.addWidget(QtWidgets.QLabel("Tolerance:"), 2, 0)
        self.mir_tol = QtWidgets.QDoubleSpinBox()
        self.mir_tol.setDecimals(4)
        self.mir_tol.setRange(0.0001, 1000.0)
        self.mir_tol.setValue(0.01)
        self.mir_tol.setSingleStep(0.01)
        g.addWidget(self.mir_tol, 2, 1)
        g.addWidget(QtWidgets.QLabel("Centre tol:"), 2, 2)
        self.mir_ctol = QtWidgets.QDoubleSpinBox()
        self.mir_ctol.setDecimals(4)
        self.mir_ctol.setRange(0.0, 1000.0)
        self.mir_ctol.setValue(0.001)
        self.mir_ctol.setSingleStep(0.001)
        g.addWidget(self.mir_ctol, 2, 3)

        self.mir_world = QtWidgets.QCheckBox("World space")
        self.mir_orig = QtWidgets.QCheckBox("Use bind (orig) shape positions")
        self.mir_orig.setChecked(True)
        self.mir_orig.setToolTip(
            "Sample the skinCluster's input geometry so a posed or deformed "
            "mesh still mirrors against its neutral shape.")
        self.mir_center = QtWidgets.QCheckBox("Include centre vertices")
        self.mir_center.setChecked(True)
        self.mir_relaxed = QtWidgets.QCheckBox("Fall back to nearest vertex")
        self.mir_relaxed.setChecked(True)
        g.addWidget(self.mir_world, 3, 0, 1, 2)
        g.addWidget(self.mir_orig, 3, 2, 1, 2)
        g.addWidget(self.mir_center, 4, 0, 1, 2)
        g.addWidget(self.mir_relaxed, 4, 2, 1, 2)
        lay.addWidget(grp2)

        grp3 = QtWidgets.QGroupBox("Left / Right Joint Tokens")
        v = QtWidgets.QVBoxLayout(grp3)
        self.mir_pairs = QtWidgets.QPlainTextEdit()
        self.mir_pairs.setMaximumHeight(110)
        self.mir_pairs.setToolTip(
            "One pair per line:  left token = right token\n"
            "Checked top to bottom, first match wins.\n\n"
            "Token shape controls where it may match:\n"
            "  _L_   underscored both ends  ->  anywhere in the name\n"
            "  L_    trailing underscore    ->  prefix only\n"
            "  _L    leading underscore     ->  suffix only\n"
            "  Left  bare word              ->  anywhere")
        self._reset_pairs()
        v.addWidget(self.mir_pairs)
        prow = QtWidgets.QHBoxLayout()
        self.btn_pairs_reset = QtWidgets.QPushButton("Reset Defaults")
        self.mir_addinf = QtWidgets.QCheckBox("Add missing mirrored influences")
        self.mir_addinf.setChecked(True)
        prow.addWidget(self.mir_addinf)
        prow.addStretch()
        prow.addWidget(self.btn_pairs_reset)
        v.addLayout(prow)
        lay.addWidget(grp3)

        self.btn_mirror = QtWidgets.QPushButton("Mirror Weights")
        self.btn_mirror.setObjectName("accent")
        lay.addWidget(self.btn_mirror)
        lay.addStretch()
        return page

    # -- tab 3 --------------------------------------------------------- #

    def _tab_copy(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setSpacing(6)

        grp = QtWidgets.QGroupBox("Source and Targets")
        v = QtWidgets.QVBoxLayout(grp)
        v.addWidget(QtWidgets.QLabel(
            "Select the skinned source first, then every target mesh."))
        srow = QtWidgets.QHBoxLayout()
        self.cp_source = QtWidgets.QLineEdit()
        self.cp_source.setPlaceholderText("source mesh")
        self.btn_cp_load = QtWidgets.QPushButton("Load Selection")
        srow.addWidget(QtWidgets.QLabel("Source:"))
        srow.addWidget(self.cp_source)
        srow.addWidget(self.btn_cp_load)
        v.addLayout(srow)
        self.cp_targets = QtWidgets.QListWidget()
        self.cp_targets.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.cp_targets.setMinimumHeight(140)
        v.addWidget(self.cp_targets)
        trow = QtWidgets.QHBoxLayout()
        self.btn_cp_add = QtWidgets.QPushButton("Add Selected as Targets")
        self.btn_cp_del = QtWidgets.QPushButton("Remove")
        self.btn_cp_clr = QtWidgets.QPushButton("Clear")
        trow.addWidget(self.btn_cp_add)
        trow.addWidget(self.btn_cp_del)
        trow.addWidget(self.btn_cp_clr)
        v.addLayout(trow)
        lay.addWidget(grp)

        grp2 = QtWidgets.QGroupBox("Transfer Options")
        f = QtWidgets.QFormLayout(grp2)
        self.cp_rebind = QtWidgets.QCheckBox(
            "Rebind targets (delete any existing skinCluster)")
        self.cp_rebind.setChecked(True)
        f.addRow("", self.cp_rebind)

        self.cp_surface = QtWidgets.QComboBox()
        self.cp_surface.addItems(SURFACE_ASSOC)
        f.addRow("Surface association:", self.cp_surface)

        self.cp_inf1 = QtWidgets.QComboBox()
        self.cp_inf1.addItems(INFLUENCE_ASSOC)
        self.cp_inf1.setCurrentText("closestJoint")
        self.cp_inf2 = QtWidgets.QComboBox()
        self.cp_inf2.addItems([""] + INFLUENCE_ASSOC)
        self.cp_inf2.setCurrentText("oneToOne")
        self.cp_inf3 = QtWidgets.QComboBox()
        self.cp_inf3.addItems([""] + INFLUENCE_ASSOC)
        self.cp_inf3.setCurrentText("name")
        irow = QtWidgets.QHBoxLayout()
        irow.addWidget(self.cp_inf1)
        irow.addWidget(self.cp_inf2)
        irow.addWidget(self.cp_inf3)
        f.addRow("Influence association:", irow)

        self.cp_method = QtWidgets.QComboBox()
        self.cp_method.addItems(["Match source"] + SKIN_METHODS)
        f.addRow("Skinning method:", self.cp_method)

        mrow = QtWidgets.QHBoxLayout()
        self.cp_maxinf = QtWidgets.QSpinBox()
        self.cp_maxinf.setRange(0, 32)
        self.cp_maxinf.setValue(0)
        self.cp_maxinf.setSpecialValueText("source")
        self.cp_dropoff = QtWidgets.QDoubleSpinBox()
        self.cp_dropoff.setRange(0.1, 20.0)
        self.cp_dropoff.setValue(4.0)
        self.cp_normalize = QtWidgets.QCheckBox("Normalize")
        self.cp_normalize.setChecked(True)
        mrow.addWidget(QtWidgets.QLabel("Max inf:"))
        mrow.addWidget(self.cp_maxinf)
        mrow.addWidget(QtWidgets.QLabel("Dropoff:"))
        mrow.addWidget(self.cp_dropoff)
        mrow.addWidget(self.cp_normalize)
        mrow.addStretch()
        f.addRow("", mrow)
        lay.addWidget(grp2)

        self.btn_copy = QtWidgets.QPushButton("Copy Skin to Targets")
        self.btn_copy.setObjectName("accent")
        lay.addWidget(self.btn_copy)
        lay.addStretch()
        return page

    # -------------------------------------------------------------- signals #

    def _connect(self):
        self.btn_j_add.clicked.connect(self._joints_add_selected)
        self.btn_j_del.clicked.connect(self._joints_remove_selected)
        self.btn_j_clr.clicked.connect(self._joints_clear)
        self.btn_browse_save.clicked.connect(lambda: self._browse(True))
        self.btn_browse_open.clicked.connect(lambda: self._browse(False))
        self.btn_export.clicked.connect(self._do_export)
        self.btn_import.clicked.connect(self._do_import)

        self.mir_mode.currentIndexChanged.connect(
            lambda i: self.mir_tgt.setEnabled(i == 1))
        self.btn_pairs_reset.clicked.connect(self._reset_pairs)
        self.btn_mirror.clicked.connect(self._do_mirror)

        self.btn_cp_load.clicked.connect(self._copy_load_selection)
        self.btn_cp_add.clicked.connect(self._copy_add_targets)
        self.btn_cp_del.clicked.connect(
            lambda: self._list_remove(self.cp_targets))
        self.btn_cp_clr.clicked.connect(self.cp_targets.clear)
        self.btn_copy.clicked.connect(self._do_copy)

        self.btn_revert.clicked.connect(self._do_revert)
        self.btn_clear_log.clicked.connect(self.log_box.clear)

    # ------------------------------------------------------------ utilities #

    def log(self, message, level="info"):
        colors = {"info": "#c8c8c8", "ok": "#7fc97f",
                  "warn": "#e0b050", "error": "#e07070"}
        color = colors.get(level, "#c8c8c8")
        stamp = time.strftime("%H:%M:%S")
        self.log_box.appendHtml(
            '<span style="color:#707070;">[%s]</span> '
            '<span style="color:%s;">%s</span>' % (stamp, color, message))
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()

    def set_progress(self, fraction, message=""):
        self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        if message:
            self.progress.setFormat("%s  %%p%%" % message)
        QtWidgets.QApplication.processEvents()

    def _guard(self, func, suspend=True):
        """Run *func* with a busy cursor, viewport off and errors trapped."""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        if suspend:
            cmds.refresh(suspend=True)
        try:
            func()
        except SkinError as exc:
            self.log(str(exc), "error")
        except Exception as exc:
            self.log("Unexpected error: %s" % exc, "error")
            sys.stderr.write(traceback.format_exc())
        finally:
            if suspend:
                cmds.refresh(suspend=False)
            try:
                cmds.refresh()
            except Exception:
                pass
            QtWidgets.QApplication.restoreOverrideCursor()
            self.set_progress(0, "")
            self.progress.setFormat("%p%")
            self.btn_revert.setText("Revert Last Weight Op (%d)" % revert_depth())

    @staticmethod
    def _list_remove(widget):
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    @staticmethod
    def _list_items(widget):
        return [widget.item(i).text() for i in range(widget.count())]

    def _last_dir(self):
        if cmds.optionVar(exists=OPTVAR_DIR):
            path = cmds.optionVar(query=OPTVAR_DIR)
            if os.path.isdir(path):
                return path
        return cmds.workspace(query=True, rootDirectory=True)

    def _remember_dir(self, path):
        folder = os.path.dirname(path)
        if folder:
            cmds.optionVar(stringValue=(OPTVAR_DIR, folder))

    # --------------------------------------------------------- tab 1 slots #

    def _joints_clear(self):
        self.io_joints.clear()
        self._update_joint_info()

    def _joints_remove_selected(self):
        self._list_remove(self.io_joints)
        self._update_joint_info()

    def _update_joint_info(self):
        """Show, for the joints currently in the list, which mesh each one
        is bound to right now (auto-detected - nothing to set by hand)."""
        names = self._list_items(self.io_joints)
        if not names:
            self.io_info.setText(
                "Select joint(s) in the scene, then Add Selected Joints.")
            return
        lines = []
        for s in names:
            matches = cmds.ls(s, long=True) or []
            joint = matches[0] if matches else None
            meshes = meshes_for_joint(joint) if joint else []
            if not joint:
                lines.append("%s - not found in this scene" % s)
            elif meshes:
                lines.append("%s -> %s" % (s, ", ".join(
                    short_name(m) for m in meshes)))
            else:
                lines.append("%s - not bound to any mesh here yet" % s)
        self.io_info.setText("\n".join(lines))

    def _joints_add_selected(self):
        joints = cmds.ls(selection=True, type="joint", long=True) or []
        existing = set(self._list_items(self.io_joints))
        added = 0
        for jnt in joints:
            s = short_name(jnt)
            if s not in existing:
                self.io_joints.addItem(s)
                existing.add(s)
                added += 1
        if not joints:
            self.log("Select one or more joints first.", "warn")
        else:
            self.log("Added %d joint(s)." % added)
        self._update_joint_info()

    def _browse(self, save):
        start = self.io_path.text() or self._last_dir()
        flt = "Skin weights (*.json *.json.gz);;All files (*.*)"
        if save:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Skin Weights", start, flt)
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Open Skin Weights", start, flt)
        if path:
            if save and not path.lower().endswith((".json", ".gz")):
                path += ".json"
            self.io_path.setText(path)
            self._remember_dir(path)
            if not save:
                self._preview_file_joints(path)

    def _preview_file_joints(self, path):
        """After picking a file to import, show which joint(s) it carries."""
        try:
            data = read_weight_file(path)
        except SkinError as exc:
            self.log(str(exc), "error")
            return
        entries = (data.get("meshes", [])
                  if data.get("format") == FILE_FORMAT_JOINTS else [data])
        self.io_joints.clear()
        joints = sorted(set(
            j for e in entries for j in e.get("influences", [])))
        for j in joints:
            self.io_joints.addItem(j)
        meshes = ", ".join(short_name(e.get("mesh", "?")) for e in entries)
        self.io_info.setText(
            "File carries %d joint(s) for: %s" % (len(joints), meshes))
        self.log("File has %d joint(s) across %d mesh(es)."
                 % (len(joints), len(entries)))

    def _do_export(self):
        def run():
            joints = self._list_items(self.io_joints)
            if not joints:
                joints = [short_name(j) for j in
                         (cmds.ls(selection=True, type="joint", long=True)
                          or [])]
                if not joints:
                    raise SkinError(
                        "Add joint(s) to the list, or select some first.")
            path = self.io_path.text().strip()
            if not path:
                raise SkinError("Set an output file.")

            self.set_progress(0.0, "Reading weights...")
            export_joint_weights(joints, path, log=self.log,
                                 progress=self.set_progress)
            self._remember_dir(path)
            self.set_progress(1.0, "Done.")
        self._guard(run)

    def _do_import(self):
        def run():
            path = self.io_path.text().strip()
            if not path:
                raise SkinError("Set a weight file.")

            import_joint_weights(path, log=self.log,
                                 progress=self.set_progress)
            self._update_joint_info()
        self._guard(run)

    # --------------------------------------------------------- tab 2 slots #

    def _reset_pairs(self):
        self.mir_pairs.setPlainText(
            "\n".join("%s = %s" % (a, b) for a, b in DEFAULT_MIRROR_PAIRS))

    def _parse_pairs(self):
        pairs = []
        for line in self.mir_pairs.toPlainText().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            left, right = line.split("=", 1)
            left, right = left.strip(), right.strip()
            if left and right:
                pairs.append((left, right))
        return pairs or DEFAULT_MIRROR_PAIRS

    def _do_mirror(self):
        def run():
            src = self.mir_src.text()
            if not src or not cmds.objExists(src):
                raise SkinError("Set a valid source mesh.")
            tgt = None
            if self.mir_mode.currentIndex() == 1:
                tgt = self.mir_tgt.text()
                if not tgt or not cmds.objExists(tgt):
                    raise SkinError("Set a valid target mesh.")

            mirror_weights(
                src, tgt,
                axis=self.mir_axis.currentText().lower(),
                direction=self.mir_dir.currentText(),
                match="index" if self.mir_match.currentIndex() == 1 else "position",
                tolerance=self.mir_tol.value(),
                center_tolerance=self.mir_ctol.value(),
                include_center=self.mir_center.isChecked(),
                world_space=self.mir_world.isChecked(),
                use_orig=self.mir_orig.isChecked(),
                pairs=self._parse_pairs(),
                add_missing=self.mir_addinf.isChecked(),
                relaxed=self.mir_relaxed.isChecked(),
                log=self.log, progress=self.set_progress)
        self._guard(run)

    # --------------------------------------------------------- tab 3 slots #

    def _copy_load_selection(self):
        sel = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        meshes = [n for n in sel if get_shape(n)]
        if len(meshes) < 2:
            self.log("Select the source first, then one or more targets.", "warn")
            if meshes:
                self.cp_source.setText(short_name(meshes[0]))
            return
        self.cp_source.setText(short_name(meshes[0]))
        self.cp_targets.clear()
        for m in meshes[1:]:
            self.cp_targets.addItem(short_name(m))
        self.log("Source '%s', %d target(s)."
                 % (short_name(meshes[0]), len(meshes) - 1))

    def _copy_add_targets(self):
        sel = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        existing = set(self._list_items(self.cp_targets))
        source = self.cp_source.text()
        added = 0
        for node in sel:
            if not get_shape(node):
                continue
            s = short_name(node)
            if s == source or s in existing:
                continue
            self.cp_targets.addItem(s)
            existing.add(s)
            added += 1
        self.log("Added %d target(s)." % added)

    def _do_copy(self):
        def run():
            source = self.cp_source.text().strip()
            if not source or not cmds.objExists(source):
                raise SkinError("Set a valid source mesh.")
            targets = [t for t in self._list_items(self.cp_targets)
                       if cmds.objExists(t)]
            if not targets:
                raise SkinError("Add at least one target mesh.")

            method = None
            if self.cp_method.currentIndex() > 0:
                method = self.cp_method.currentIndex() - 1
            max_inf = self.cp_maxinf.value() or None

            copy_skin(
                source, targets,
                rebind=self.cp_rebind.isChecked(),
                surface_association=self.cp_surface.currentText(),
                influence_association=(self.cp_inf1.currentText(),
                                       self.cp_inf2.currentText(),
                                       self.cp_inf3.currentText()),
                normalize=self.cp_normalize.isChecked(),
                skinning_method=method,
                max_influences=max_inf,
                dropoff=self.cp_dropoff.value(),
                log=self.log, progress=self.set_progress)
        # binding needs a live DG, so the viewport is left alone here
        self._guard(run, suspend=False)

    # ----------------------------------------------------------------- misc #

    def _do_revert(self):
        def run():
            self.log("Reverted: %s" % revert_last(), "ok")
        self._guard(run)


# --------------------------------------------------------------------------- #
#  Entry points
# --------------------------------------------------------------------------- #

_WINDOW = None


def show():
    """Open (or re-open) the tool."""
    global _WINDOW
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT:
            widget.close()
            widget.deleteLater()
    _WINDOW = SkinToolsUI()
    _WINDOW.show()
    return _WINDOW


# aliases so this drops straight into the KRT launcher conventions
run_tool = show
main = show


if __name__ == "__main__":
    show()