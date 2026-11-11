"""Joint Transfer - fit the CC skeleton to the character's body.

Headless version of the "Joint Relocator" tab of jointTransferPro2.py.
Used by the JOINT TRANSFER panel (each step has its own button, so you can
stop, adjust spheres by hand, and carry on), or in one line from a script:

    from KRT.utils import joint_transfer; joint_transfer.run()

Steps (STEPS below - each key is a function in this module):
    1. load_reference      reference FullBodyJntTransfer_01.ma
    2. import_spheres      bounding spheres from the sphere JSON
    3. detect              per joint: rest positions of the reference-mesh
                           vertices inside ITS spheres (uses the spheres that
                           are in the scene NOW, so hand edits count)
    4. create_blendshape   CC_Base_Body -> FullBodyJntTransfer_01:CC_Base_Body, on
    5. reposition          Kabsch / SVD best fit per joint, skin preserved
                           (each skinCluster bindPreMatrix updated)
    6. delete_spheres
    7. remove_reference    blendShape + leftovers + the reference itself

Between steps the detected data is kept in _STATE (on `sys`, so a KRT
reload does not lose it while you are adjusting things).
"""
import os
import sys
import json

import numpy as np
import maya.cmds as cmds
import maya.api.OpenMaya as om

from . import rig_resources, rig_reference, step_runner

# Both files ship inside KRT (resources/rig_utils/); P: is only a fallback.
REFERENCE_FILE = rig_resources.resource(rig_resources.FULLBODY_REF)
NAMESPACE = "FullBodyJntTransfer_01"
REF_MESH = NAMESPACE + ":CC_Base_Body"        # detection mesh (in the reference)
SOURCE_MESH = "CC_Base_Body"                    # the character's body (blendShape source)
TARGET_NS = ""                                  # the character's joints have no namespace
SPHERE_JSON = rig_resources.resource(rig_resources.SPHERE_JSON)
BLENDSHAPE_NAME = "jointTransfer_BS"
SPHERE_TAG = "_bounding_sphere"
MIN_VERTS = 5                                   # spheres with fewer vertices are skipped

# Same "keep static" set as the UI tool's DEFAULT_UNCHECKED_JOINTS.
STATIC_JOINTS = {
    "CC_Base_FacialBone", "CC_Base_JawRoot", "CC_Base_Tongue01", "CC_Base_Tongue02",
    "CC_Base_Tongue03", "CC_Base_Teeth02", "CC_Base_R_Eye", "CC_Base_L_Eye",
    "CC_Base_UpperJaw", "CC_Base_Teeth01",
}

# (function name, label) in run order - the panel builds its rows from this.
STEPS = [
    ("load_reference",    "1. Load reference"),
    ("import_spheres",    "2. Import spheres (JSON)"),
    ("detect",            "3. Detect vertices"),
    ("create_blendshape", "4. Blendshape ON"),
    ("reposition",        "5. Reposition joints (skin kept)"),
    ("delete_spheres",    "6. Delete spheres"),
    ("remove_reference",  "7. Remove reference + cleanup"),
]

# Survives a KRT reload (module re-import) - same trick as hang_watch.
if not hasattr(sys, "_krt_joint_transfer_state"):
    sys._krt_joint_transfer_state = {}
_STATE = sys._krt_joint_transfer_state


def _log(msg):
    print("[KRT JointTransfer] " + msg)


def _base(name):
    return name.split("|")[-1].split(":")[-1]


def _ns(base, ns):
    ns = (ns or "").strip().rstrip(":")
    return "{}:{}".format(ns, base) if ns else base


def _xform_matrix(node):
    """World matrix as a 4x4 numpy array (Maya is row-vector: p_world = p_local @ M)."""
    return np.array(cmds.xform(node, query=True, worldSpace=True, matrix=True)).reshape(4, 4)


def _mesh_points(mesh):
    """All vertex world positions in one API call -> (N, 3) numpy array.
    DEFORMED positions: with the blendShape on, this is the shaped mesh."""
    sel = om.MSelectionList()
    sel.add(mesh)
    pts = om.MFnMesh(sel.getDagPath(0)).getPoints(om.MSpace.kWorld)
    return np.array([(p.x, p.y, p.z) for p in pts])


# ── 1. reference ─────────────────────────────────────────────────────────
def _find_reference(ns=NAMESPACE):
    return rig_reference.find(ns)


def load_reference(path=None, ns=NAMESPACE):
    return rig_reference.load(path or REFERENCE_FILE, ns, _STATE, log=_log)


# ── 2. spheres ───────────────────────────────────────────────────────────
def _create_sphere(name):
    if cmds.objExists(name):
        cmds.delete(name)
    sphere = cmds.polySphere(name=name, radius=1.0, subdivisionsX=16,
                             subdivisionsY=16, constructionHistory=False)[0]
    shape = (cmds.listRelatives(sphere, shapes=True) or [None])[0]
    if shape:
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideShading", 0)      # wireframe look
    return sphere


def import_spheres(json_path=None):
    """Create every sphere from the JSON at its saved world matrix.
    Returns the joint list stored in the JSON (base names)."""
    json_path = json_path or SPHERE_JSON
    if not os.path.isfile(json_path):
        raise IOError("Sphere JSON not found: " + json_path)
    with open(json_path, "r") as f:
        data = json.load(f)
    count = 0
    for name, t in data.get("spheres", {}).items():
        sphere = _create_sphere(name)
        if "matrix" in t:
            cmds.xform(sphere, worldSpace=True, matrix=t["matrix"])
        else:
            cmds.xform(sphere, worldSpace=True, translation=t.get("translation", [0, 0, 0]))
            cmds.xform(sphere, worldSpace=True, rotation=t.get("rotation", [0, 0, 0]))
            cmds.xform(sphere, relative=True, scale=t.get("scale", [1, 1, 1]))
        count += 1
    joints = list(dict.fromkeys(_base(j) for j in data.get("joints", [])))
    _log("imported {} spheres, {} joints from {}".format(count, len(joints), json_path))
    return joints


def all_spheres():
    return cmds.ls("*" + SPHERE_TAG + "*", transforms=True) or []


def _spheres_for(base):
    prefix = base + SPHERE_TAG
    return [s for s in all_spheres() if _base(s).startswith(prefix)]


def joints_from_scene_spheres():
    """Joint base names that have at least one sphere in the scene now."""
    return sorted({_base(s).split(SPHERE_TAG)[0] for s in all_spheres()})


# ── 3. detect ────────────────────────────────────────────────────────────
def _inside(points_h, sphere):
    """Indices of vertices inside a (possibly scaled/rotated) unit sphere:
    move every point into the sphere's local space at once; inside = length <= 1."""
    local = points_h @ np.linalg.inv(_xform_matrix(sphere))
    return np.nonzero(np.linalg.norm(local[:, :3], axis=1) <= 1.0)[0]


def _rot_rows(m4):
    """Upper-left 3x3 split into normalised rows + their lengths (scale)."""
    R = m4[:3, :3].copy()
    lengths = np.linalg.norm(R, axis=1, keepdims=True)
    lengths = np.where(lengths < 1e-6, 1.0, lengths)
    return R / lengths, lengths


def _rest_points(mesh):
    """Mesh points with our blendShape switched OFF (envelope 0) for the
    read, so re-running Detect after step 4 still measures the REST shape."""
    env = BLENDSHAPE_NAME + ".envelope"
    old = None
    if cmds.objExists(BLENDSHAPE_NAME):
        old = cmds.getAttr(env)
        cmds.setAttr(env, 0.0)
    try:
        return _mesh_points(mesh)
    finally:
        if old is not None:
            cmds.setAttr(env, old)


def detect(joints=None, mesh=REF_MESH, det_ns=NAMESPACE):
    """Store, per joint, the rest positions of the vertices inside its spheres.
    joints=None -> every joint that has a sphere in the scene, minus STATIC_JOINTS."""
    if not cmds.objExists(mesh):
        raise RuntimeError("Detection mesh not found: {} (run step 1 first)".format(mesh))
    if joints is None:
        joints = [j for j in joints_from_scene_spheres() if j not in STATIC_JOINTS]
    if not joints:
        raise RuntimeError("No spheres in the scene (run step 2 first)")
    pts = _rest_points(mesh)
    pts_h = np.c_[pts, np.ones(len(pts))]           # homogeneous coords for the matrix test

    stored, skipped = {}, []
    for base in joints:
        det_jnt = _ns(base, det_ns)
        spheres = _spheres_for(base)
        if not cmds.objExists(det_jnt) or not spheres:
            continue
        per_sphere = [(_inside(pts_h, s), s) for s in spheres]
        thin = [s for idx, s in per_sphere if len(idx) < MIN_VERTS]
        if thin:
            skipped.append("{} ({})".format(base, ", ".join(thin)))
            continue
        idx = np.unique(np.concatenate([i for i, _ in per_sphere]))
        if len(idx) < 3:
            continue

        p0 = pts[idx]
        pj0 = np.array(cmds.xform(det_jnt, query=True, worldSpace=True, translation=True))
        c0 = p0.mean(axis=0)
        d = np.linalg.norm(p0 - pj0, axis=1)
        w = np.where(d < 1e-4, 1e5, 1.0 / (d ** 2))
        w /= w.sum()
        R_norm, lengths = _rot_rows(_xform_matrix(det_jnt))
        stored[base] = {"idx": idx, "p0": p0, "c0": c0, "j0_rel": pj0 - c0,
                        "R_j0_norm": R_norm, "row_lengths": lengths, "weights": w}

    _STATE["stored"] = stored
    _log("detected vertices for {} joints".format(len(stored)))
    for s in skipped:
        cmds.warning("[KRT JointTransfer] skipped (sphere has < {} vertices): {}".format(MIN_VERTS, s))
    return stored


# ── 4. blendShape ────────────────────────────────────────────────────────
def create_blendshape(source=SOURCE_MESH, target=REF_MESH, name=BLENDSHAPE_NAME):
    for m in (source, target):
        if not cmds.objExists(m):
            raise RuntimeError("Mesh not found: " + m)
    n_src = cmds.polyEvaluate(source, vertex=True)
    n_tgt = cmds.polyEvaluate(target, vertex=True)
    if n_src != n_tgt:
        raise RuntimeError("Vertex count differs: {} has {}, {} has {}".format(source, n_src, target, n_tgt))
    if cmds.objExists(name):
        cmds.delete(name)
    bs = cmds.blendShape(source, target, topologyCheck=False, name=name)[0]
    cmds.blendShape(bs, edit=True, weight=[(0, 1.0)])      # turn it on
    _log("blendShape {}: {} -> {} (weight 1)".format(bs, source, target))
    return bs


# ── 5. reposition ────────────────────────────────────────────────────────
def _dag_depth(node):
    longs = cmds.ls(node, long=True)
    return len(longs[0].split("|")) if longs else 0


def _update_bind_pre_matrix(joint):
    """Make every skinCluster treat the joint's NEW position as its bind
    position, so moving the joint does not deform the skin."""
    conns = cmds.listConnections(joint + ".worldMatrix[0]", type="skinCluster",
                                 connections=True, plugs=True) or []
    for i in range(0, len(conns), 2):
        dst = conns[i + 1]
        if ".matrix[" in dst:
            skin, attr = dst.split(".")
            index = attr.split("[")[1].split("]")[0]
            cmds.setAttr("{}.bindPreMatrix[{}]".format(skin, index),
                         cmds.getAttr(joint + ".worldInverseMatrix[0]"), type="matrix")


def _detachment_map(active, tgt_ns):
    """Static joints whose parent is an active joint: unparent them during the
    move so they stay exactly where they are."""
    result = {}
    for j in cmds.ls("{}*".format(tgt_ns) if tgt_ns else "*", type="joint") or []:
        if _base(j) in active:
            continue
        parent = cmds.listRelatives(j, parent=True, fullPath=True)
        if parent and _base(parent[0]) in active:
            result[j] = parent[0]
    return result


def reposition(stored=None, mesh=REF_MESH, tgt_ns=TARGET_NS):
    stored = stored if stored is not None else _STATE.get("stored")
    if not stored:
        raise RuntimeError("Nothing detected yet (run step 3 first)")
    if not cmds.objExists(BLENDSHAPE_NAME):
        raise RuntimeError("blendShape {} not found (run step 4 first)".format(BLENDSHAPE_NAME))
    pts = _mesh_points(mesh)                         # shaped positions (blendShape on)
    active = set(stored)
    targets = {}
    for base, d in stored.items():
        tgt = _ns(base, tgt_ns)
        if not cmds.objExists(tgt):
            continue
        pt = pts[d["idx"]]
        ct = pt.mean(axis=0)
        A, B = d["p0"] - d["c0"], pt - ct
        U, S, Vt = np.linalg.svd(A.T @ B)            # Kabsch: best rotation A -> B
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:                     # reflection -> flip last axis
            Vt[2, :] *= -1
            R = Vt.T @ U.T
        var_A = np.sum(A ** 2)
        scale = np.sum(S) / var_A if var_A > 1e-6 else 1.0
        residual = B - scale * (A @ R.T)
        delta = np.sum(residual * d["weights"][:, None], axis=0)   # local, joint-weighted fix
        pos = ct + scale * (R @ d["j0_rel"]) + delta
        Rs = (d["R_j0_norm"] @ R.T) * d["row_lengths"]
        targets[tgt] = om.MMatrix([Rs[0, 0], Rs[0, 1], Rs[0, 2], 0.0,
                                   Rs[1, 0], Rs[1, 1], Rs[1, 2], 0.0,
                                   Rs[2, 0], Rs[2, 1], Rs[2, 2], 0.0,
                                   pos[0], pos[1], pos[2], 1.0])

    facial, head = _ns("CC_Base_FacialBone", tgt_ns), _ns("CC_Base_Head", tgt_ns)
    detach = _detachment_map(active, tgt_ns)
    moved = 0
    cmds.undoInfo(openChunk=True, chunkName="KRT_JointTransfer")
    try:
        has_facial = cmds.objExists(facial)
        if has_facial:
            cmds.parent(facial, world=True)
        detached = []
        for child, parent in detach.items():
            if cmds.objExists(child) and child != facial:
                try:
                    cmds.parent(child, world=True)
                    detached.append((child, parent))
                except Exception as e:
                    cmds.warning("[KRT JointTransfer] could not detach {}: {}".format(child, e))

        for tgt in sorted(targets, key=_dag_depth):   # parents before children
            W = targets[tgt]
            parents = cmds.listRelatives(tgt, parent=True, type="joint")
            L = W * om.MMatrix(cmds.xform(parents[0], query=True, worldSpace=True, matrix=True)).inverse() \
                if parents else W
            tm = om.MTransformationMatrix(L)
            t = tm.translation(om.MSpace.kTransform)
            e = tm.rotation(asQuaternion=False)
            e.reorderIt(cmds.getAttr(tgt + ".rotateOrder"))
            cmds.setAttr(tgt + ".translate", t.x, t.y, t.z)
            cmds.setAttr(tgt + ".jointOrient", *np.degrees([e.x, e.y, e.z]))
            cmds.setAttr(tgt + ".rotate", 0.0, 0.0, 0.0)
            _update_bind_pre_matrix(tgt)
            moved += 1

        if has_facial and cmds.objExists(head):
            cmds.parent(facial, head)
        for child, parent in detached:
            if cmds.objExists(child) and cmds.objExists(parent):
                try:
                    cmds.parent(child, parent)
                except Exception as e:
                    cmds.warning("[KRT JointTransfer] could not re-attach {}: {}".format(child, e))
    finally:
        cmds.undoInfo(closeChunk=True)
    _log("repositioned {} joints (skin preserved)".format(moved))
    return moved


# ── 6. delete spheres ────────────────────────────────────────────────────
def delete_spheres():
    spheres = all_spheres()
    if spheres:
        cmds.delete(spheres)
    _log("deleted {} spheres".format(len(spheres)))
    return len(spheres)


# ── 7. remove reference + leftovers ──────────────────────────────────────
def remove_reference(ns=NAMESPACE, blendshape=BLENDSHAPE_NAME):
    # the blendShape lives in THIS scene but deforms a referenced mesh -
    # delete it (and its set, if Maya made one) before the reference goes
    rig_reference.remove(ns, _STATE, delete_first=(blendshape, blendshape + "Set"), log=_log)
    _STATE.pop("stored", None)


def cleanup(ns=NAMESPACE, blendshape=BLENDSHAPE_NAME):
    """Steps 6 + 7 - tidy up after a failed or partial run."""
    delete_spheres()
    remove_reference(ns, blendshape)


# ── running steps ────────────────────────────────────────────────────────
def run_step(key, json_path=None, ref_path=None, **_ignored):
    if key == "load_reference":
        return load_reference(ref_path)
    if key == "import_spheres":
        return import_spheres(json_path)
    return globals()[key]()


def run_steps(keys=None, on_step=None, **opts):
    """Run the given step keys in STEPS order. opts: json_path, ref_path.
    Returns (success, error_text); on_step(key, 'running'|'ok'|'error')."""
    return step_runner.run_steps(STEPS, run_step, keys, on_step, opts, _log)


def run(json_path=None, ref_path=None):
    """All seven steps. On error the scene is left as it is; call cleanup()."""
    ok, err = run_steps(None, json_path=json_path, ref_path=ref_path)
    if not ok:
        raise RuntimeError(err)
