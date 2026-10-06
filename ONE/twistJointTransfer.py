"""
transferJointWeights.py
-----------------------
Move skin weights from SOURCE joints to TARGET joints, on every skinned
mesh each source joint influences (auto-detected), for the Left side and,
optionally, the mirrored Right side. Supports any number of source/target
pairs at once via the "+" button in the UI.

Default pairs
  1) Source (weight FROM): CC_Base_L_ForearmTwist01   Target (weight TO): arm_L0_4_jnt
  2) Source (weight FROM): CC_Base_L_CalfTwist01       Target (weight TO): leg_L0_4_jnt
  Right side : ON for both  (L names mirrored to R automatically)

One click does everything, per pair, per mesh:
  1. Finds the skinCluster on the mesh (meshes are auto-detected from the
     source joint - no need to pick a mesh).
  2. If the target (or source) joint is not an influence of that
     skinCluster yet, it is added automatically: every existing influence
     is locked first, then the joint is added with 0 weight, locked. The
     add is verified. No existing weights are touched by this step.
  3. All influences are locked; only that pair's source and target are
     unlocked.
  4. On every vertex where the source has weight, that weight is added to
     the target and the source is set to 0. The vertex total stays the
     same, so no other influence is touched.
  5. The whole run (every pair, every mesh, both sides) is one undo step.

Usage (Script Editor, Python tab):
    import transferJointWeights as tjw
    tjw.show_ui()

    # or without the UI:
    tjw.run_transfer()                                              # both defaults, L + R
    tjw.run_multi_transfer([
        ("CC_Base_L_ForearmTwist01", "arm_L0_4_jnt"),
        ("CC_Base_L_CalfTwist01", "leg_L0_4_jnt"),
    ], do_right=True)
"""

import re

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

WINDOW = "transferJointWeightsWin"
VERSION = "4.0"

DEFAULT_PAIRS = [
    ("CC_Base_L_ForearmTwist01", "arm_L0_4_jnt"),
    ("CC_Base_L_CalfTwist01", "leg_L0_4_jnt"),
]


# --------------------------------------------------------------------------
# Name / scene helpers
# --------------------------------------------------------------------------
def mirror_name(name):
    """
    Left -> Right name. Swaps an 'L' that sits after '_' (or at the start)
    and is followed by '_' or a digit:
        arm_L0_4_jnt             -> arm_R0_4_jnt
        CC_Base_L_ForearmTwist01 -> CC_Base_R_ForearmTwist01
    """
    return re.sub(r"(?:(?<=_)|(?<=^)|(?<=:))L(?=[_0-9])", "R", name)


def _same_node(a, b):
    return cmds.ls(a, long=True)[0] == cmds.ls(b, long=True)[0]


def _in_influences(joint, influences):
    return any(_same_node(joint, inf) for inf in influences)


def _get_mobject(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDependNode(0)


def _get_dag(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDagPath(0)


def get_skin_cluster(mesh):
    history = cmds.listHistory(mesh, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster")
    return skins[0] if skins else None


def detect_meshes(joint):
    """All mesh transforms whose skinCluster has `joint` as an influence."""
    if not joint or not cmds.objExists(joint):
        return []
    skins = set(cmds.listConnections(joint, type="skinCluster") or [])
    meshes = []
    for sc in skins:
        for geo in cmds.skinCluster(sc, q=True, geometry=True) or []:
            if cmds.nodeType(geo) != "mesh":
                continue
            xform = cmds.listRelatives(geo, parent=True, fullPath=False)[0]
            if xform not in meshes:
                meshes.append(xform)
    return sorted(meshes)


def _selected_vertex_ids(mesh):
    """Vertex ids of the current component selection on this mesh."""
    comps = [s for s in (cmds.ls(sl=True) or []) if "." in s]
    if not comps:
        return None
    verts = cmds.ls(cmds.polyListComponentConversion(comps, toVertex=True) or [], flatten=True)
    mesh_long = cmds.ls(mesh, long=True)[0]
    ids = set()
    for v in verts:
        node_long = cmds.ls(v.split(".")[0], long=True)[0]
        parent = (cmds.listRelatives(node_long, parent=True, fullPath=True) or [None])[0]
        if mesh_long in (node_long, parent):
            ids.add(int(v.split("[")[-1].rstrip("]")))
    return sorted(ids) or None


# --------------------------------------------------------------------------
# Add influence safely
# --------------------------------------------------------------------------
def ensure_influence(skin, joint):
    """
    Make sure `joint` is an influence of `skin`.
    If missing: lock every existing influence first (so no weights move),
    add the joint with 0 weight and locked, then verify it is really there.
    Returns True if it was added, False if it was already an influence.
    """
    influences = cmds.skinCluster(skin, q=True, influence=True) or []
    if _in_influences(joint, influences):
        return False

    for inf in influences:
        cmds.skinCluster(skin, e=True, influence=inf, lockWeights=True)

    cmds.skinCluster(skin, e=True, addInfluence=joint, weight=0.0, lockWeights=True)

    if not _in_influences(joint, cmds.skinCluster(skin, q=True, influence=True) or []):
        raise RuntimeError("Failed to add '{}' to {}.".format(joint, skin))
    print("[transferJointWeights] Added '{}' to {} (locked, 0 weight).".format(joint, skin))
    return True


def _side_pairs(source, target, do_right):
    pairs = [("Left", source, target)]
    if do_right:
        r_src, r_tgt = mirror_name(source), mirror_name(target)
        if (r_src, r_tgt) == (source, target):
            cmds.warning("Could not build Right-side names from '{}' / '{}'.".format(source, target))
        else:
            pairs.append(("Right", r_src, r_tgt))
    return pairs


# --------------------------------------------------------------------------
# Core: one mesh
# --------------------------------------------------------------------------
def transfer_on_mesh(source, target, mesh, vert_ids=None, restore_locks=False):
    """Move weights source -> target on one mesh. Returns vertices changed."""
    skin = get_skin_cluster(mesh)
    if not skin:
        raise RuntimeError("No skinCluster on '{}'.".format(mesh))

    influences = cmds.skinCluster(skin, q=True, influence=True) or []
    original_locks = {inf: cmds.skinCluster(skin, q=True, influence=inf, lockWeights=True)
                      for inf in influences}

    # add missing influences (0 weight + locked -> nothing changes)
    for jnt in (source, target):
        ensure_influence(skin, jnt)

    # lock all, unlock only source + target
    influences = cmds.skinCluster(skin, q=True, influence=True) or []
    for inf in influences:
        cmds.skinCluster(skin, e=True, influence=inf, lockWeights=True)
    for jnt in (source, target):
        cmds.skinCluster(skin, e=True, influence=jnt, lockWeights=False)

    # read the two influences' weights via API
    fn_skin = oma.MFnSkinCluster(_get_mobject(skin))
    out_geo = fn_skin.getOutputGeometry()
    if len(out_geo) == 0:
        raise RuntimeError("skinCluster '{}' has no output geometry.".format(skin))
    shape_path = om.MDagPath.getAPathTo(out_geo[0])

    src_path, tgt_path = _get_dag(source), _get_dag(target)
    src_phys = tgt_phys = None
    for i, p in enumerate(fn_skin.influenceObjects()):
        if p == src_path:
            src_phys = i
        elif p == tgt_path:
            tgt_phys = i
    if src_phys is None or tgt_phys is None:
        raise RuntimeError("Could not resolve influence indices on '{}'.".format(skin))
    src_log = fn_skin.indexForInfluenceObject(src_path)
    tgt_log = fn_skin.indexForInfluenceObject(tgt_path)

    comp_fn = om.MFnSingleIndexedComponent()
    comp = comp_fn.create(om.MFn.kMeshVertComponent)
    if vert_ids:
        comp_fn.addElements(vert_ids)
    else:
        num_verts = om.MFnMesh(shape_path).numVertices
        comp_fn.setCompleteData(num_verts)
        vert_ids = range(num_verts)

    weights = fn_skin.getWeights(shape_path, comp, om.MIntArray([src_phys, tgt_phys]))

    # write with setAttr (undoable), only on vertices the source affects
    changed = 0
    for n, vid in enumerate(vert_ids):
        src_w = weights[n * 2]
        if src_w <= 1e-7:
            continue
        tgt_w = weights[n * 2 + 1]
        cmds.setAttr("{}.weightList[{}].weights[{}]".format(skin, vid, tgt_log), tgt_w + src_w)
        cmds.setAttr("{}.weightList[{}].weights[{}]".format(skin, vid, src_log), 0.0)
        changed += 1

    if restore_locks:
        for inf in cmds.skinCluster(skin, q=True, influence=True) or []:
            cmds.skinCluster(skin, e=True, influence=inf,
                             lockWeights=original_locks.get(inf, True))
    return changed


# --------------------------------------------------------------------------
# Core: many source/target pairs, every mesh, one or both sides
# --------------------------------------------------------------------------
def run_multi_transfer(pairs, do_right=True, selected_only=False, restore_locks=False):
    """
    pairs : list of (source, target) tuples, e.g.
            [("CC_Base_L_ForearmTwist01", "arm_L0_4_jnt"),
             ("CC_Base_L_CalfTwist01", "leg_L0_4_jnt")]
    For each pair, and its mirrored Right-side pair when do_right is True,
    weights are transferred on every mesh the source joint influences
    (auto-detected). Missing target/source joints are added to the
    skinCluster automatically. The whole call is one undo step.
    """
    if not pairs:
        cmds.warning("No source/target pairs given.")
        return []

    all_side_pairs = []
    for source, target in pairs:
        source, target = (source or "").strip(), (target or "").strip()
        if not source or not target:
            cmds.warning("Skipped an empty pair.")
            continue
        all_side_pairs.extend(_side_pairs(source, target, do_right))

    report = []
    total = 0
    cmds.undoInfo(openChunk=True, chunkName="transferJointWeights")
    try:
        for side, src, tgt in all_side_pairs:
            missing = [j for j in (src, tgt) if not cmds.objExists(j)]
            if missing:
                cmds.warning("[{}] Skipped {} -> {}: joint not found: {}"
                             .format(side, src, tgt, ", ".join(missing)))
                continue
            if _same_node(src, tgt):
                cmds.warning("[{}] Skipped - source and target are the same ({}).".format(side, src))
                continue

            side_meshes = detect_meshes(src)
            if not side_meshes:
                cmds.warning("[{}] No skinned meshes found for '{}'.".format(side, src))
                continue

            for mesh in side_meshes:
                vert_ids = None
                if selected_only:
                    vert_ids = _selected_vertex_ids(mesh)
                    if not vert_ids:
                        continue  # nothing selected on this mesh
                try:
                    n = transfer_on_mesh(src, tgt, mesh, vert_ids, restore_locks)
                except RuntimeError as e:
                    cmds.warning("[{}] {}: {}".format(side, mesh, e))
                    continue
                total += n
                report.append("[{}] {}: {} verts  {} -> {}".format(side, mesh, n, src, tgt))
    finally:
        cmds.undoInfo(closeChunk=True)

    for line in report:
        print("[transferJointWeights] " + line)
    msg = "Transfer done: {} vertices across {} result(s)".format(total, len(report))
    print("[transferJointWeights] " + msg)
    cmds.inViewMessage(amg="<hl>{}</hl>".format(msg), pos="midCenter", fade=True)
    return report


def run_transfer(source, target, do_right=True, selected_only=False, restore_locks=False):
    """Single-pair convenience wrapper around run_multi_transfer."""
    return run_multi_transfer([(source, target)], do_right, selected_only, restore_locks)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
_rows = []          # list of dicts: {"frame": .., "src": .., "tgt": ..}
_row_counter = [0]


def _load_selected_joint(field):
    sel = cmds.ls(sl=True, type="transform") or []
    if not sel:
        cmds.warning("Select a joint.")
        return
    cmds.textFieldButtonGrp(field, e=True, text=sel[0])


def _renumber_rows():
    for i, r in enumerate(_rows):
        cmds.frameLayout(r["frame"], e=True, label="Pair {}".format(i + 1))


def _remove_row(frame):
    if len(_rows) <= 1:
        cmds.warning("At least one source/target pair is required.")
        return
    cmds.deleteUI(frame)
    _rows[:] = [r for r in _rows if r["frame"] != frame]
    _renumber_rows()


def _set_row_enabled(idx, src_field, tgt_field, enable_box):
    on = cmds.checkBox(enable_box, q=True, value=True)
    cmds.textFieldButtonGrp(src_field, e=True, enable=on)
    cmds.textFieldButtonGrp(tgt_field, e=True, enable=on)


def _add_row(src_default="", tgt_default="", enabled=True):
    idx = _row_counter[0]
    _row_counter[0] += 1
    frame = "tjw_rowFrame_{}".format(idx)
    src_field = "tjw_src_{}".format(idx)
    tgt_field = "tjw_tgt_{}".format(idx)
    enable_box = "tjw_enable_{}".format(idx)

    cmds.setParent("tjw_rowsColumn")
    cmds.frameLayout(frame, label="Pair {}".format(len(_rows) + 1), collapsable=False,
                     marginWidth=6, marginHeight=4, borderVisible=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.checkBox(enable_box, label="Enabled", value=enabled,
                 changeCommand=lambda *_a, i=idx, s=src_field, t=tgt_field, e=enable_box:
                 _set_row_enabled(i, s, t, e))
    cmds.textFieldButtonGrp(src_field, label="Source (FROM)", text=src_default, enable=enabled,
                            buttonLabel="<< Sel", columnWidth3=(100, 210, 50), adjustableColumn=2,
                            buttonCommand=lambda f=src_field: _load_selected_joint(f))
    cmds.textFieldButtonGrp(tgt_field, label="Target (TO)", text=tgt_default, enable=enabled,
                            buttonLabel="<< Sel", columnWidth3=(100, 210, 50), adjustableColumn=2,
                            buttonCommand=lambda f=tgt_field: _load_selected_joint(f))
    cmds.button(label="Remove this pair", height=18,
               command=lambda *_a, fr=frame: _remove_row(fr))
    cmds.setParent("..")
    cmds.setParent("..")

    _rows.append({"frame": frame, "src": src_field, "tgt": tgt_field, "enable": enable_box})
    _renumber_rows()


def _collect_pairs():
    pairs = []
    for r in _rows:
        if not cmds.checkBox(r["enable"], q=True, value=True):
            continue
        src = cmds.textFieldButtonGrp(r["src"], q=True, text=True).strip()
        tgt = cmds.textFieldButtonGrp(r["tgt"], q=True, text=True).strip()
        if src or tgt:
            pairs.append((src, tgt))
    return pairs


def _run(*_):
    pairs = _collect_pairs()
    if not pairs:
        cmds.warning("No enabled pairs to transfer.")
        return
    run_multi_transfer(
        pairs,
        do_right=cmds.checkBox("tjw_right", q=True, value=True),
    )


def show_ui():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    _rows[:] = []
    _row_counter[0] = 0

    cmds.window(WINDOW, title="Transfer Joint Weights  v{}".format(VERSION),
               widthHeight=(460, 480), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))
    cmds.separator(height=6, style="none")

    cmds.checkBox("tjw_right", label="Also do Right side  (L -> R mirrored names)", value=True)
    cmds.separator(height=8)

    cmds.text(label="Source / Target pairs:", align="left")
    cmds.scrollLayout("tjw_rowsScroll", height=260, childResizable=True)
    cmds.columnLayout("tjw_rowsColumn", adjustableColumn=True, rowSpacing=8)
    cmds.setParent("..")  # leave tjw_rowsColumn
    cmds.setParent("..")  # leave scrollLayout, back to main column

    cmds.button(label="+  Add another Source / Target pair", height=26,
               command=lambda *_: _add_row())

    cmds.separator(height=8)
    cmds.button(label="Transfer Weights  (auto-adds Target joints if missing)", height=40,
               backgroundColor=(0.35, 0.55, 0.35), command=_run)
    cmds.separator(height=4, style="none")
    cmds.showWindow(WINDOW)

    for src, tgt in DEFAULT_PAIRS:
        _add_row(src, tgt)

    print("[transferJointWeights] v{} loaded from {}".format(VERSION, __file__))


if __name__ == "__main__":
    show_ui()