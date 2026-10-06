"""
transferJointWeights.py
-----------------------
Move skin weights from a SOURCE joint to a TARGET joint on a skinned mesh.

How it works
  1. Finds the skinCluster on the mesh.
  2. If the source or target joint is not an influence yet, it is added
     with 0 weight and locked, so no existing weights change.
  3. All influences are locked; only the source and target are unlocked.
  4. For every vertex where the source has weight, that weight is added
     to the target and the source is set to 0. The vertex total stays
     the same, so no other influence is touched.
  5. Everything runs in a single undo chunk, so Ctrl+Z undoes all of it.

Usage (Script Editor, Python tab):
    import transferJointWeights as tjw
    tjw.show_ui()

    # or without the UI:
    tjw.transfer_weights("L_arm_jnt", "L_shoulder_jnt", "body_geo")
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

WINDOW = "transferJointWeightsWin"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get_skin_cluster(mesh):
    """Return the skinCluster driving the mesh (transform or shape)."""
    history = cmds.listHistory(mesh, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster")
    return skins[0] if skins else None


def _get_mobject(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDependNode(0)


def _get_dag(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDagPath(0)


def _influence_names(skin):
    return cmds.skinCluster(skin, q=True, influence=True) or []


def _same_node(a, b):
    return cmds.ls(a, long=True)[0] == cmds.ls(b, long=True)[0]


def _in_influences(joint, influences):
    return any(_same_node(joint, inf) for inf in influences)


def _selected_vertex_ids(mesh):
    """Vertex ids of the current component selection on this mesh (faces/edges converted)."""
    sel = cmds.ls(sl=True, flatten=False) or []
    comps = [s for s in sel if "." in s]
    if not comps:
        return None
    verts = cmds.polyListComponentConversion(comps, toVertex=True) or []
    verts = cmds.ls(verts, flatten=True) or []
    mesh_long = cmds.ls(mesh, long=True)[0]
    ids = []
    for v in verts:
        node = v.split(".")[0]
        # component can be on the transform or on the shape
        node_long = cmds.ls(node, long=True)[0]
        parent = (cmds.listRelatives(node_long, parent=True, fullPath=True) or [None])[0]
        if node_long == mesh_long or parent == mesh_long:
            ids.append(int(v.split("[")[-1].rstrip("]")))
    return sorted(set(ids)) or None


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
def transfer_weights(source, target, mesh, selected_only=False, restore_locks=False):
    """
    Move all weights from `source` joint to `target` joint on `mesh`.

    selected_only : only process currently selected vertices of the mesh.
    restore_locks : put every influence's lock state back afterwards
                    (default False = leave everything locked except src/tgt).
    Returns the number of vertices changed.
    """
    # ---- validation -------------------------------------------------------
    for node, label in ((source, "Source joint"), (target, "Target joint"), (mesh, "Mesh")):
        if not node or not cmds.objExists(node):
            cmds.error("{} '{}' does not exist.".format(label, node))
    if _same_node(source, target):
        cmds.error("Source and target are the same joint.")

    skin = get_skin_cluster(mesh)
    if not skin:
        cmds.error("No skinCluster found on '{}'.".format(mesh))

    vert_ids = None
    if selected_only:
        vert_ids = _selected_vertex_ids(mesh)
        if not vert_ids:
            cmds.error("'Selected vertices only' is on, but no vertices of '{}' are selected.".format(mesh))

    cmds.undoInfo(openChunk=True, chunkName="transferJointWeights")
    try:
        influences = _influence_names(skin)
        original_locks = {inf: cmds.skinCluster(skin, q=True, influence=inf, lockWeights=True)
                          for inf in influences}

        # ---- add missing influences (0 weight, locked -> nothing changes) --
        for jnt in (source, target):
            if not _in_influences(jnt, influences):
                cmds.skinCluster(skin, e=True, addInfluence=jnt, weight=0.0, lockWeights=True)
                print("[transferJointWeights] Added '{}' to {} (locked, 0 weight).".format(jnt, skin))

        # ---- lock everything, unlock only source + target -----------------
        influences = _influence_names(skin)
        for inf in influences:
            cmds.skinCluster(skin, e=True, influence=inf, lockWeights=True)
        for jnt in (source, target):
            cmds.skinCluster(skin, e=True, influence=jnt, lockWeights=False)

        # ---- read weights of the two influences (fast, via API) -----------
        fn_skin = oma.MFnSkinCluster(_get_mobject(skin))
        out_geo = fn_skin.getOutputGeometry()
        if len(out_geo) == 0:
            cmds.error("skinCluster '{}' has no output geometry.".format(skin))
        shape_path = om.MDagPath.getAPathTo(out_geo[0])

        inf_paths = fn_skin.influenceObjects()
        src_path, tgt_path = _get_dag(source), _get_dag(target)
        src_phys = tgt_phys = None
        for i, p in enumerate(inf_paths):
            if p == src_path:
                src_phys = i
            elif p == tgt_path:
                tgt_phys = i
        if src_phys is None or tgt_phys is None:
            cmds.error("Could not resolve influence indices on '{}'.".format(skin))

        # logical indices = the index used in weightList[v].weights[idx]
        src_log = fn_skin.indexForInfluenceObject(src_path)
        tgt_log = fn_skin.indexForInfluenceObject(tgt_path)

        comp_fn = om.MFnSingleIndexedComponent()
        comp = comp_fn.create(om.MFn.kMeshVertComponent)
        if vert_ids:
            comp_fn.addElements(vert_ids)
        else:
            num_verts = om.MFnMesh(shape_path).numVertices
            comp_fn.setCompleteData(num_verts)
            vert_ids = list(range(num_verts))

        weights = fn_skin.getWeights(shape_path, comp, om.MIntArray([src_phys, tgt_phys]))

        # ---- move source -> target (undoable setAttr, only affected verts) --
        changed = 0
        for n, vid in enumerate(vert_ids):
            src_w = weights[n * 2]
            if src_w <= 1e-7:
                continue
            tgt_w = weights[n * 2 + 1]
            cmds.setAttr("{}.weightList[{}].weights[{}]".format(skin, vid, tgt_log), tgt_w + src_w)
            cmds.setAttr("{}.weightList[{}].weights[{}]".format(skin, vid, src_log), 0.0)
            changed += 1

        # ---- optional: restore original lock states -----------------------
        if restore_locks:
            for inf in _influence_names(skin):
                state = original_locks.get(inf, True)  # newly added ones stay locked
                cmds.skinCluster(skin, e=True, influence=inf, lockWeights=state)

    finally:
        cmds.undoInfo(closeChunk=True)

    msg = "Moved weights on {} vertices: {} -> {}  ({})".format(changed, source, target, skin)
    print("[transferJointWeights] " + msg)
    cmds.inViewMessage(amg="<hl>{}</hl>".format(msg), pos="midCenter", fade=True)
    return changed


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
def _load_selected(field, want_mesh=False):
    sel = cmds.ls(sl=True, objectsOnly=True) or []
    if not sel:
        cmds.warning("Nothing selected.")
        return
    node = sel[0]
    if want_mesh and cmds.nodeType(node) == "mesh":
        node = cmds.listRelatives(node, parent=True)[0]
    cmds.textFieldButtonGrp(field, e=True, text=node)


def _run(*_):
    transfer_weights(
        cmds.textFieldButtonGrp("tjw_src", q=True, text=True).strip(),
        cmds.textFieldButtonGrp("tjw_tgt", q=True, text=True).strip(),
        cmds.textFieldButtonGrp("tjw_mesh", q=True, text=True).strip(),
        selected_only=cmds.checkBox("tjw_selOnly", q=True, value=True),
        restore_locks=cmds.checkBox("tjw_restore", q=True, value=True),
    )


def show_ui():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="Transfer Joint Weights", widthHeight=(420, 200), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))
    cmds.separator(height=6, style="none")

    cmds.textFieldButtonGrp("tjw_src", label="Source Joint", buttonLabel="<< Sel",
                            columnWidth3=(90, 260, 50), adjustableColumn=2,
                            buttonCommand=lambda: _load_selected("tjw_src"))
    cmds.textFieldButtonGrp("tjw_tgt", label="Target Joint", buttonLabel="<< Sel",
                            columnWidth3=(90, 260, 50), adjustableColumn=2,
                            buttonCommand=lambda: _load_selected("tjw_tgt"))
    cmds.textFieldButtonGrp("tjw_mesh", label="Mesh", buttonLabel="<< Sel",
                            columnWidth3=(90, 260, 50), adjustableColumn=2,
                            buttonCommand=lambda: _load_selected("tjw_mesh", want_mesh=True))

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 200), columnAttach2=("left", "left"),
                   columnOffset2=(95, 0))
    cmds.checkBox("tjw_selOnly", label="Selected vertices only", value=False)
    cmds.checkBox("tjw_restore", label="Restore lock states after", value=False)
    cmds.setParent("..")

    cmds.button(label="Transfer Weights  (Source  ->  Target)", height=34,
                backgroundColor=(0.35, 0.55, 0.35), command=_run)
    cmds.separator(height=4, style="none")
    cmds.showWindow(WINDOW)


if __name__ == "__main__":
    show_ui()