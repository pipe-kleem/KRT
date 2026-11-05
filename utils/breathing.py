"""Breathing setup (Stage 66) - Breathing_Setup_Fixed.py from the kva_a rig,
as a KRT module for the BREATHING panel. Unchanged except the RUN block at
the bottom was removed: the panel calls

    run_breathing(Body_Mesh, mesh_list, use_001_scaling)

with the main mesh / extra meshes typed into the panel.
"""
import math
import maya.cmds as cmds

# ============================================================
# SETTINGS
# ============================================================

SKELETON_ROOT = "CC_Base_BoneRoot"
SNAP_JOINT = "CC_Base_Spine02"

CTRL = "Chest_M_Ctrl"
CTRL_ZERO = CTRL + "_zero"
BREATH_ATTR = "Breath"

CTRL_SIZE = 1.5
CTRL_COLOR = 13

# Multiplier to scale translateY movement into full breathing response
BREATH_MULTIPLIER = 50.0

BREATH_MESH = "CC_Base_Body_Breathing"
BREATH_GRP = BREATH_MESH + "_GRP"
BREATH_SKIN = BREATH_MESH + "_skinCluster"

SETUP_GROUP = "Breathing_Setup_GRP"
EXPRESSION_NAME = "breath_bidirectional_expr"

BLENDSHAPE_NODE = "Morpher_CC_Base_Body"

# ============================================================
# REFERENCE BR ZERO POSITIONS / DISTANCES
# These are the correct world-space values supplied by you.
# IMPORTANT:
# Do NOT multiply these values by get_global_scale().
# They are already final Maya world-space values.
# ============================================================

REF_SPINE_BR_ZERO_POS = (
    0.00014918032591972622,
    1.6578205612762194,
    -0.02472299379184477,
)

REF_MID_BR_ZERO_POS = (
    -0.0002037,
    1.7496575,
    0.1554548,
)

REF_CHEST_BR_ZERO_POS = (
    0.000244547451828755,
    2.097762240054318,
    -0.04875186855525583,
)

REF_SPINE_TO_MID = 0.20223299734310526
REF_MID_TO_CHEST = 0.4035808152730981
REF_SPINE_TO_CHEST = 0.4405974088023853

BR_DISTANCE_TOLERANCE = 0.000001


# ============================================================
# GENERAL HELPERS
# ============================================================

def get_global_scale(node):
    """Calculates global scale factor from the world matrix of a node."""
    if not cmds.objExists(node):
        return 1.0
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return math.sqrt(matrix[0] ** 2 + matrix[1] ** 2 + matrix[2] ** 2)


def short_name(node):
    return node.split("|")[-1].split(":")[-1]


def safe_delete(node):
    if not cmds.objExists(node):
        return

    try:
        cmds.delete(node)
    except RuntimeError:
        cmds.warning("Could not delete: {}".format(node))


def find_descendant(root, name):
    nodes = [root] + (
        cmds.listRelatives(
            root, allDescendents=True, fullPath=True
        )
        or []
    )

    for node in nodes:
        if short_name(node) == name:
            return node

    cmds.error("Missing joint: " + name)


def unlock_transforms(node):
    """Unlocks standard transform and visibility attributes on a node."""
    if not cmds.objExists(node):
        return
    attrs = ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"]
    for attr in attrs:
        plug = "{}.{}".format(node, attr)
        if cmds.objExists(plug):
            try:
                cmds.setAttr(plug, lock=False)
            except RuntimeError:
                pass


def freeze(nodes):
    if isinstance(nodes, str):
        nodes = [nodes]

    nodes = [node for node in nodes if cmds.objExists(node)]

    if not nodes:
        return

    for node in nodes:
        unlock_transforms(node)

    cmds.makeIdentity(
        nodes,
        apply=True,
        translate=True,
        rotate=True,
        scale=True,
        normal=False,
        preserveNormals=True,
    )


def unparent_to_world(node):
    if not cmds.objExists(node):
        return node

    parent = (
        cmds.listRelatives(node, parent=True, fullPath=True) or []
    )

    if parent:
        node = cmds.parent(node, world=True)[0]

    return node


def disconnect_and_unlock(plug):
    if not cmds.objExists(plug):
        return

    incoming = (
        cmds.listConnections(
            plug, source=True, destination=False, plugs=True
        )
        or []
    )

    for source_plug in incoming:
        try:
            cmds.disconnectAttr(source_plug, plug)
        except RuntimeError:
            pass

    try:
        if cmds.getAttr(plug, lock=True):
            cmds.setAttr(plug, lock=False)
    except RuntimeError:
        pass


# ============================================================
# CLEAN PREVIOUS SETUP
# ============================================================

def delete_previous_setup():
    safe_delete(EXPRESSION_NAME)

    if cmds.objExists(CTRL_ZERO):
        constraints = (
            cmds.listConnections(
                CTRL_ZERO,
                source=True,
                destination=False,
                type="constraint",
            )
            or []
        )

        for constraint in set(constraints):
            safe_delete(constraint)

    safe_delete(SETUP_GROUP)

    generated_nodes = [
        BREATH_SKIN,
        BREATH_MESH,
        BREATH_GRP,
        "Chest_BR_zero",
        "Mid_BR_zero",
        "Spine_BR_zero",
        "Chest_BR",
        "Mid_BR",
        "Spine_BR",
        "Root",
        "BreathSkeleton_TEMP",
    ]

    for node in generated_nodes:
        safe_delete(node)


# ============================================================
# ZERO GROUP
# ============================================================

def zero_group(node):
    group_name = node + "_zero"

    safe_delete(group_name)

    world_matrix = cmds.xform(
        node, query=True, worldSpace=True, matrix=True
    )

    old_parent = (
        cmds.listRelatives(node, parent=True, fullPath=True) or []
    )

    group = cmds.group(empty=True, name=group_name)

    if old_parent:
        group = cmds.parent(group, old_parent[0])[0]

    cmds.xform(group, worldSpace=True, matrix=world_matrix)

    cmds.parent(node, group)

    cmds.setAttr(node + ".translate", 0, 0, 0)
    cmds.setAttr(node + ".rotate", 0, 0, 0)
    cmds.setAttr(node + ".scale", 1, 1, 1)

    if cmds.attributeQuery("jointOrient", node=node, exists=True):
        cmds.setAttr(node + ".jointOrient", 0, 0, 0)

    if cmds.attributeQuery("rotateAxis", node=node, exists=True):
        cmds.setAttr(node + ".rotateAxis", 0, 0, 0)

    return group


# ============================================================
# ACCURATE BR ZERO WORLD-SPACE POSITION / DISTANCE HELPERS
# ============================================================

def _get_world_position(node):
    """Return transform origin in Maya world space."""
    if not cmds.objExists(node):
        cmds.error("Node not found: " + node)

    return cmds.xform(
        node,
        query=True,
        worldSpace=True,
        translation=True,
    )


def _distance(point_a, point_b):
    dx = point_b[0] - point_a[0]
    dy = point_b[1] - point_a[1]
    dz = point_b[2] - point_a[2]
    return math.sqrt((dx * dx) + (dy * dy) + (dz * dz))


def _vec_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _vec_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _vec_mul(v, scalar):
    return [v[0] * scalar, v[1] * scalar, v[2] * scalar]


def _vec_dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _vec_length(v):
    return math.sqrt(_vec_dot(v, v))


def _vec_normalize(v):
    length = _vec_length(v)
    if length < 1e-12:
        return None
    return [v[0] / length, v[1] / length, v[2] / length]


def _project_perpendicular(vector, axis):
    along = _vec_mul(axis, _vec_dot(vector, axis))
    return _vec_sub(vector, along)


def solve_mid_from_two_distances(
    spine_pos,
    chest_pos,
    guide_pos,
    spine_to_mid,
    mid_to_chest,
):
    """
    Solve Mid_BR_zero from exact distances to Spine_BR_zero and Chest_BR_zero.

    There are multiple mathematical solutions around the Spine->Chest axis.
    guide_pos chooses the intended anatomical/forward side.
    """
    spine_to_chest_vec = _vec_sub(chest_pos, spine_pos)
    spine_to_chest = _vec_length(spine_to_chest_vec)

    if spine_to_chest < 1e-12:
        cmds.error(
            "Spine_BR_zero and Chest_BR_zero are at the same position."
        )

    max_distance = spine_to_mid + mid_to_chest
    min_distance = abs(spine_to_mid - mid_to_chest)

    if spine_to_chest > max_distance + BR_DISTANCE_TOLERANCE:
        cmds.error(
            "Reference Mid distances are impossible because "
            "Spine_BR_zero <-> Chest_BR_zero is too long. "
            "Current: {:.12f}, max allowed: {:.12f}".format(
                spine_to_chest,
                max_distance,
            )
        )

    if spine_to_chest < min_distance - BR_DISTANCE_TOLERANCE:
        cmds.error(
            "Reference Mid distances are impossible because "
            "Spine_BR_zero <-> Chest_BR_zero is too short. "
            "Current: {:.12f}, min allowed: {:.12f}".format(
                spine_to_chest,
                min_distance,
            )
        )

    axis = _vec_normalize(spine_to_chest_vec)

    # Position of the circle center measured from Spine along Spine->Chest.
    a = (
        (spine_to_mid * spine_to_mid)
        - (mid_to_chest * mid_to_chest)
        + (spine_to_chest * spine_to_chest)
    ) / (2.0 * spine_to_chest)

    h_sq = (spine_to_mid * spine_to_mid) - (a * a)

    if h_sq < 0.0 and abs(h_sq) <= BR_DISTANCE_TOLERANCE:
        h_sq = 0.0

    if h_sq < 0.0:
        cmds.error(
            "Unable to solve Mid_BR_zero. Invalid h^2: {}".format(h_sq)
        )

    h = math.sqrt(h_sq)

    circle_center = _vec_add(
        spine_pos,
        _vec_mul(axis, a),
    )

    # Choose correct side using the known-good Mid position.
    guide_vector = _vec_sub(guide_pos, circle_center)
    perpendicular = _project_perpendicular(guide_vector, axis)
    perpendicular = _vec_normalize(perpendicular)

    # Fallback directions if needed.
    if perpendicular is None:
        perpendicular = _vec_normalize(
            _project_perpendicular([0.0, 0.0, 1.0], axis)
        )

    if perpendicular is None:
        perpendicular = _vec_normalize(
            _project_perpendicular([1.0, 0.0, 0.0], axis)
        )

    if perpendicular is None:
        cmds.error("Unable to determine Mid_BR_zero direction.")

    return _vec_add(
        circle_center,
        _vec_mul(perpendicular, h),
    )


def print_br_zero_distance_report(title="BR ZERO GROUP DISTANCE CHECK"):
    required = [
        "Spine_BR_zero",
        "Mid_BR_zero",
        "Chest_BR_zero",
    ]

    missing = [node for node in required if not cmds.objExists(node)]
    if missing:
        cmds.warning(
            "Cannot print BR distance report. Missing: {}".format(
                ", ".join(missing)
            )
        )
        return None

    spine_pos = _get_world_position("Spine_BR_zero")
    mid_pos = _get_world_position("Mid_BR_zero")
    chest_pos = _get_world_position("Chest_BR_zero")

    spine_mid = _distance(spine_pos, mid_pos)
    mid_chest = _distance(mid_pos, chest_pos)
    spine_chest = _distance(spine_pos, chest_pos)

    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    print("\nWORLD POSITIONS:")
    print("Spine_BR_zero : {}".format(spine_pos))
    print("Mid_BR_zero   : {}".format(mid_pos))
    print("Chest_BR_zero : {}".format(chest_pos))

    print("\nDISTANCES:")
    print(
        "Spine_BR_zero <--> Mid_BR_zero   = {:.12f}".format(
            spine_mid
        )
    )
    print(
        "Mid_BR_zero   <--> Chest_BR_zero = {:.12f}".format(
            mid_chest
        )
    )
    print(
        "Spine_BR_zero <--> Chest_BR_zero = {:.12f}".format(
            spine_chest
        )
    )

    print("\nREFERENCE DISTANCES:")
    print(
        "Spine -> Mid   = {:.12f}".format(REF_SPINE_TO_MID)
    )
    print(
        "Mid -> Chest   = {:.12f}".format(REF_MID_TO_CHEST)
    )
    print(
        "Spine -> Chest = {:.12f}".format(REF_SPINE_TO_CHEST)
    )

    print("\nDISTANCE ERROR:")
    print(
        "Spine -> Mid   = {:.12f}".format(
            abs(spine_mid - REF_SPINE_TO_MID)
        )
    )
    print(
        "Mid -> Chest   = {:.12f}".format(
            abs(mid_chest - REF_MID_TO_CHEST)
        )
    )

    print("=" * 60 + "\n")

    return {
        "spine_position": spine_pos,
        "mid_position": mid_pos,
        "chest_position": chest_pos,
        "spine_mid": spine_mid,
        "mid_chest": mid_chest,
        "spine_chest": spine_chest,
    }


def update_mid_br_zero():
    """
    Correct Mid_BR_zero in WORLD SPACE.

    OLD BUG:
        Mid_BR_zero.translate = hard-coded values * scale_factor

    That is not reliable because:
      - translate is local-space
      - get_global_scale() can differ between Maya files
      - the same mesh topology does not guarantee identical parent transforms

    NEW METHOD:
      1. Put Mid at the exact world-space position supplied by you.
      2. Check its distances to Spine and Chest.
      3. If Spine/Chest differ slightly in another file, solve the Mid point
         mathematically so the two reference distances are maintained.
    """
    spine = "Spine_BR_zero"
    mid = "Mid_BR_zero"
    chest = "Chest_BR_zero"

    for node in (spine, mid, chest):
        if not cmds.objExists(node):
            cmds.error("Node not found: " + node)
        unlock_transforms(node)

    # Exact known-good world position. No scale_factor.
    cmds.xform(
        mid,
        worldSpace=True,
        translation=REF_MID_BR_ZERO_POS,
    )

    # Keep original intended zero-group rotation values.
    cmds.setAttr(mid + ".rotateX", 14.72042)
    cmds.setAttr(mid + ".rotateY", -0.0282)
    cmds.setAttr(mid + ".rotateZ", -0.08166)

    cmds.setAttr(mid + ".scaleX", 1)
    cmds.setAttr(mid + ".scaleY", 1)
    cmds.setAttr(mid + ".scaleZ", 1)
    cmds.setAttr(mid + ".visibility", 1)

    spine_pos = _get_world_position(spine)
    mid_pos = _get_world_position(mid)
    chest_pos = _get_world_position(chest)

    spine_mid = _distance(spine_pos, mid_pos)
    mid_chest = _distance(mid_pos, chest_pos)

    correct_spine_mid = (
        abs(spine_mid - REF_SPINE_TO_MID)
        <= BR_DISTANCE_TOLERANCE
    )
    correct_mid_chest = (
        abs(mid_chest - REF_MID_TO_CHEST)
        <= BR_DISTANCE_TOLERANCE
    )

    # If another file has different Spine/Chest transforms, solve Mid from
    # the distances instead of accepting the wrong position.
    if not (correct_spine_mid and correct_mid_chest):
        solved_mid = solve_mid_from_two_distances(
            spine_pos=spine_pos,
            chest_pos=chest_pos,
            guide_pos=REF_MID_BR_ZERO_POS,
            spine_to_mid=REF_SPINE_TO_MID,
            mid_to_chest=REF_MID_TO_CHEST,
        )

        cmds.xform(
            mid,
            worldSpace=True,
            translation=solved_mid,
        )

    # Final strict validation.
    final_mid = _get_world_position(mid)
    final_spine_mid = _distance(spine_pos, final_mid)
    final_mid_chest = _distance(final_mid, chest_pos)

    if (
        abs(final_spine_mid - REF_SPINE_TO_MID)
        > BR_DISTANCE_TOLERANCE
    ):
        cmds.error(
            "Mid_BR_zero Spine distance is still wrong. "
            "Expected {:.12f}, got {:.12f}".format(
                REF_SPINE_TO_MID,
                final_spine_mid,
            )
        )

    if (
        abs(final_mid_chest - REF_MID_TO_CHEST)
        > BR_DISTANCE_TOLERANCE
    ):
        cmds.error(
            "Mid_BR_zero Chest distance is still wrong. "
            "Expected {:.12f}, got {:.12f}".format(
                REF_MID_TO_CHEST,
                final_mid_chest,
            )
        )

    print(
        "Mid_BR_zero corrected accurately in WORLD SPACE: {}".format(
            final_mid
        )
    )

    print_br_zero_distance_report(
        title="BR ZERO GROUP DISTANCE CHECK - AFTER MID FIX"
    )

    return final_mid


# ============================================================
# PLUS CONTROL CURVE
# ============================================================

def plus_curve(name, size):
    a = 1.5 * size
    b = 0.5 * size

    points = [
        (0, a, b),
        (0, b, b),
        (0, b, a),
        (0, -b, a),
        (0, -b, b),
        (0, -a, b),
        (0, -a, -b),
        (0, -b, -b),
        (0, -b, -a),
        (0, b, -a),
        (0, b, -b),
        (0, a, -b),
        (0, a, b),
    ]

    return cmds.curve(
        degree=1,
        point=points,
        knot=list(range(len(points))),
        name=name,
    )


# ============================================================
# BUILD BREATHING JOINTS
# ============================================================

def build_breath_joints(scale_factor=1.0):
    root_copy = cmds.duplicate(
        SKELETON_ROOT,
        returnRootsOnly=True,
        name="BreathSkeleton_TEMP",
    )[0]

    hip = find_descendant(root_copy, "CC_Base_Hip")
    waist = find_descendant(root_copy, "CC_Base_Waist")
    mid = find_descendant(root_copy, "CC_Base_Spine01")
    chest = find_descendant(root_copy, "CC_Base_Spine02")

    chain = [
        (root_copy, hip),
        (hip, waist),
        (waist, mid),
        (mid, chest),
        (chest, None),
    ]

    for parent_node, keep_child in chain:
        children = (
            cmds.listRelatives(
                parent_node, children=True, fullPath=True
            )
            or []
        )

        for child in children:
            if keep_child is None or child != keep_child:
                cmds.delete(child)

    chest = cmds.rename(chest, "Chest_BR_TEMP")
    mid = cmds.rename(mid, "Mid_BR_TEMP")
    waist = cmds.rename(waist, "Spine_BR_TEMP")

    chest = unparent_to_world(chest)
    mid = unparent_to_world(mid)
    waist = unparent_to_world(waist)

    safe_delete(root_copy)

    freeze([waist, mid, chest])

    # --------------------------------------------------------
    # FIRST ADJUSTMENT
    # --------------------------------------------------------

    for joint in (waist, mid, chest):
        cmds.setAttr(joint + ".translateZ", 0)

    cmds.move(
        0,
        13.127102 * scale_factor,
        0,
        chest,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.move(
        0,
        -0.975258 * scale_factor,
        0,
        chest,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.move(
        0,
        8.846062 * scale_factor,
        0,
        mid,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.rotate(-19.402967, 0, 0, waist, relative=True, objectSpace=True)

    cmds.move(
        0,
        1.494302 * scale_factor,
        0,
        waist,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    freeze([waist, mid, chest])

    # --------------------------------------------------------
    # SECOND ADJUSTMENT
    # --------------------------------------------------------

    cmds.move(
        0,
        0,
        -2.350689 * scale_factor,
        mid,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.move(
        0,
        0.960077 * scale_factor,
        0,
        mid,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.rotate(10.663573, 0, 0, mid, relative=True, objectSpace=True)

    cmds.move(
        0,
        0,
        -0.0812005 * scale_factor,
        mid,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.move(
        0,
        -0.241635 * scale_factor,
        0,
        mid,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.move(
        0,
        0,
        -0.969579 * scale_factor,
        waist,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.rotate(0.541696, 0, 0, waist, relative=True, objectSpace=True)

    cmds.rotate(6.250125, 0, 0, chest, relative=True, objectSpace=True)

    cmds.move(
        0,
        0,
        -0.323544 * scale_factor,
        chest,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    freeze([waist, mid, chest])

    # --------------------------------------------------------
    # FINAL ROTATION
    # --------------------------------------------------------

    cmds.rotate(-18.500647, 0, 0, chest, relative=True, objectSpace=True)

    cmds.rotate(15.000583, 0, 0, mid, relative=True, objectSpace=True)

    cmds.rotate(0.326777, 0, 0, waist, relative=True, objectSpace=True)

    freeze([waist, mid, chest])

    waist = cmds.rename(waist, "Spine_BR")
    mid = cmds.rename(mid, "Mid_BR")
    chest = cmds.rename(chest, "Chest_BR")

    spine_zero = zero_group(waist)
    mid_zero = zero_group(mid)
    chest_zero = zero_group(chest)

    spine_zero = unparent_to_world(spine_zero)
    mid_zero = unparent_to_world(mid_zero)
    chest_zero = unparent_to_world(chest_zero)

    cmds.select(clear=True)

    root = cmds.joint(name="Root", position=(0, 0, 0))

    return [chest, mid, waist, root]


# ============================================================
# DUPLICATE AND SKIN BODY
# ============================================================

def duplicate_and_skin_body(BODY_MESH, influences, scale_factor=1.0):
    safe_delete(BREATH_SKIN)
    safe_delete(BREATH_GRP)
    safe_delete(BREATH_MESH)

    # 1. Turn off skinClusters on original mesh first
    skin_clusters = (
        cmds.ls(cmds.listHistory(BODY_MESH) or [], type="skinCluster")
        or []
    )
    saved_envelopes = {}

    for sc in skin_clusters:
        saved_envelopes[sc] = cmds.getAttr(sc + ".envelope")
        cmds.setAttr(sc + ".envelope", 0)

    # 2. Duplicate mesh
    mesh = cmds.duplicate(
        BODY_MESH, returnRootsOnly=True, name=BREATH_MESH
    )[0]

    # 3. Restore skinCluster envelope on original mesh
    for sc, env_val in saved_envelopes.items():
        cmds.setAttr(sc + ".envelope", env_val)

    # Clean construction history on duplicated mesh
    try:
        cmds.delete(mesh, constructionHistory=True)
    except RuntimeError:
        pass

    mesh = unparent_to_world(mesh)

    unlock_transforms(mesh)

    # NOT freezing mesh transforms to keep original values intact

    if short_name(mesh) != BREATH_MESH:
        mesh = cmds.rename(mesh, BREATH_MESH)

    # 4. Create upper group with location axes on origin grid (0,0,0)
    upper_grp = cmds.group(empty=True, name=BREATH_GRP)
    cmds.xform(
        upper_grp,
        worldSpace=True,
        matrix=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    )

    # 5. Put breathing mesh inside upper group FIRST
    cmds.parent(mesh, upper_grp)

    # 6. AFTER putting breathing mesh inside, set group scale to 0.01
    group_scale = 0.01
    cmds.setAttr(upper_grp + ".scaleX", group_scale)
    cmds.setAttr(upper_grp + ".scaleY", group_scale)
    cmds.setAttr(upper_grp + ".scaleZ", group_scale)

    # 7. Skin duplicate mesh to breathing joints
    skin_cluster = cmds.skinCluster(
        influences,
        mesh,
        toSelectedBones=True,
        bindMethod=0,
        skinMethod=0,
        normalizeWeights=1,
        maximumInfluences=5,
        obeyMaxInfluences=True,
        name=BREATH_SKIN,
    )[0]

    return mesh, skin_cluster, upper_grp


# ============================================================
# BUILD CONTROLLER
# ============================================================

def delete_control_constraints(zero):
    if not cmds.objExists(zero):
        return

    constraints = (
        cmds.listConnections(
            zero, source=True, destination=False, type="constraint"
        )
        or []
    )

    for constraint in set(constraints):
        if cmds.nodeType(constraint) in (
            "parentConstraint",
            "scaleConstraint",
        ):
            safe_delete(constraint)


def build_control(scale_factor=1.0):
    zero = CTRL_ZERO
    scaled_ctrl_size = CTRL_SIZE * scale_factor

    if cmds.objExists(CTRL):
        if cmds.nodeType(CTRL) != "transform":
            cmds.error(CTRL + " exists but is not a transform.")

        shapes = (
            cmds.listRelatives(
                CTRL, shapes=True, type="nurbsCurve", fullPath=True
            )
            or []
        )

        if shapes:
            cmds.delete(shapes)

        temp = plus_curve(CTRL + "_TEMP", scaled_ctrl_size)

        temp_shapes = (
            cmds.listRelatives(
                temp, shapes=True, type="nurbsCurve", fullPath=True
            )
            or []
        )

        if not temp_shapes:
            safe_delete(temp)
            cmds.error("Unable to create Chest controller shape.")

        parented_shape = cmds.parent(
            temp_shapes[0], CTRL, relative=True, shape=True
        )[0]

        safe_delete(temp)

        try:
            cmds.rename(parented_shape, CTRL + "Shape")
        except RuntimeError:
            pass

    else:
        plus_curve(CTRL, scaled_ctrl_size)

    if not cmds.objExists(zero):
        zero = cmds.group(CTRL, name=zero)
    else:
        current_parent = (
            cmds.listRelatives(CTRL, parent=True, fullPath=False) or []
        )

        if not current_parent or current_parent[0] != zero:
            cmds.parent(CTRL, zero)

    delete_control_constraints(zero)

    temporary_constraint = cmds.parentConstraint(
        SNAP_JOINT, zero, maintainOffset=False
    )[0]

    safe_delete(temporary_constraint)

    unlock_transforms(CTRL)
    cmds.setAttr(CTRL + ".translate", 0, 0, 0)
    cmds.setAttr(CTRL + ".rotate", 0, 0, 0)
    cmds.setAttr(CTRL + ".scale", 1, 1, 1)

    shapes = (
        cmds.listRelatives(
            CTRL, shapes=True, type="nurbsCurve", fullPath=True
        )
        or []
    )

    for shape in shapes:
        cmds.setAttr(shape + ".overrideEnabled", 1)
        cmds.setAttr(shape + ".overrideColor", CTRL_COLOR)

    plug = CTRL + "." + BREATH_ATTR

    if not cmds.attributeQuery(BREATH_ATTR, node=CTRL, exists=True):
        cmds.addAttr(
            CTRL,
            longName=BREATH_ATTR,
            attributeType="double",
            defaultValue=0,
            keyable=True,
        )

    else:
        disconnect_and_unlock(plug)

        try:
            cmds.addAttr(plug, edit=True, hasMinValue=False)
        except RuntimeError:
            pass

        try:
            cmds.addAttr(plug, edit=True, hasMaxValue=False)
        except RuntimeError:
            pass

    cmds.setAttr(plug, lock=False)
    cmds.setAttr(plug, keyable=True)

    freeze(zero)

    cmds.move(
        0,
        0,
        23.308912 * scale_factor,
        zero,
        relative=True,
        objectSpace=True,
        worldSpaceDistance=True,
    )

    cmds.setAttr(zero + ".rotateY", 90)

    cmds.rotate(7.321464, 0, 0, zero, relative=True, objectSpace=True)

    freeze(zero)

    parent_constraint = cmds.parentConstraint(
        SNAP_JOINT,
        zero,
        maintainOffset=True,
        name="Chest_M_Ctrl_parentConstraint",
    )[0]

    scale_constraint = cmds.scaleConstraint(
        SNAP_JOINT,
        zero,
        maintainOffset=True,
        name="Chest_M_Ctrl_scaleConstraint",
    )[0]

    cmds.select(CTRL, replace=True)

    return parent_constraint, scale_constraint


# ============================================================
# BIDIRECTIONAL BREATH EXPRESSION
# ============================================================

def install_breath_expression(scale_factor=1.0):
    driver = CTRL + "." + BREATH_ATTR

    params = {
        "Chest_BR": {
            "ty0": 0.0,
            "ty10": 0.995 * scale_factor,
            "tz0": 0.0,
            "tz10": 0.205 * scale_factor,
            "rx0": 0.0,
            "rx10": -3.096,
            "sf0": 1.0,
            "sf10": 1.139,
        },
        "Mid_BR": {
            "ty0": 0.0,
            "ty10": 0.910 * scale_factor,
            "tz0": 0.0,
            "tz10": -1.308 * scale_factor,
            "rx0": 0.0,
            "rx10": 0.0,
            "sf0": 1.0,
            "sf10": 1.01,
        },
        "Spine_BR": {
            "ty0": 0.0,
            "ty10": 0.097 * scale_factor,
            "tz0": 0.0,
            "tz10": 0.405 * scale_factor,
            "rx0": 0.0,
            "rx10": 0.0,
            "sf0": 1.0,
            "sf10": 1.005,
        },
    }

    if not cmds.objExists(driver):
        cmds.error("Breath driver not found: " + driver)

    lines = []

    for node, values in params.items():
        if not cmds.objExists(node):
            cmds.error("Breathing joint not found: " + node)

        for attribute, start_key, end_key in (
            ("translateY", "ty0", "ty10"),
            ("translateZ", "tz0", "tz10"),
            ("rotateX", "rx0", "rx10"),
            ("scaleX", "sf0", "sf10"),
        ):
            start = values[start_key]
            slope = ((values[end_key] - start) / 10.0) * BREATH_MULTIPLIER

            lines.append(
                "if ({driver} > 0) {{"
                " {node}.{attribute} = {start} + "
                "{driver} * {slope};"
                " }} else if ({driver} < 0) {{"
                " {node}.{attribute} = {start} - "
                "abs({driver}) * {slope};"
                " }} else {{"
                " {node}.{attribute} = {start};"
                " }}".format(
                    driver=driver,
                    node=node,
                    attribute=attribute,
                    start=start,
                    slope=slope,
                )
            )

        lines.append("{0}.scaleY = {0}.scaleX;".format(node))
        lines.append("{0}.scaleZ = {0}.scaleX;".format(node))

    safe_delete(EXPRESSION_NAME)

    expression_node = cmds.expression(
        name=EXPRESSION_NAME,
        string="\n".join(lines),
        alwaysEvaluate=True,
        unitConversion="all",
    )

    cmds.setAttr(driver, 0)

    return expression_node


# ============================================================
# GROUP SETUP AND ADD BLENDSHAPE
# ============================================================

def group_setup_and_add_blendshape(BODY_MESH):
    members = [
        BREATH_GRP,
        "Root",
        "Chest_BR_zero",
        "Mid_BR_zero",
        "Spine_BR_zero",
    ]

    missing = [node for node in members if not cmds.objExists(node)]

    if missing:
        cmds.error("Missing setup nodes: " + ", ".join(missing))

    if not cmds.objExists(BODY_MESH):
        cmds.error("Base mesh not found: " + BODY_MESH)

    if not cmds.objExists(BLENDSHAPE_NODE):
        cmds.error("BlendShape not found: " + BLENDSHAPE_NODE)

    cmds.setAttr(BLENDSHAPE_NODE + ".envelope", 1)

    target_index = None

    aliases = cmds.aliasAttr(BLENDSHAPE_NODE, query=True) or []

    for alias, plug in zip(aliases[0::2], aliases[1::2]):
        if alias == BREATH_MESH:
            target_index = int(plug.split("[")[-1].split("]")[0])
            break

    if target_index is None:
        used_indices = (
            cmds.getAttr(BLENDSHAPE_NODE + ".weight", multiIndices=True)
            or []
        )

        target_index = max(used_indices) + 1 if used_indices else 0

        cmds.blendShape(
            BLENDSHAPE_NODE,
            edit=True,
            topologyCheck=True,
            target=(BODY_MESH, target_index, BREATH_MESH, 1.0),
        )

    weight_plug = "{}.weight[{}]".format(BLENDSHAPE_NODE, target_index)

    disconnect_and_unlock(weight_plug)

    cmds.setAttr(weight_plug, 1.0)

    if not cmds.objExists(SETUP_GROUP):
        setup_group = cmds.group(empty=True, name=SETUP_GROUP)
    else:
        setup_group = SETUP_GROUP

    for node in members:
        current_parent = (
            cmds.listRelatives(node, parent=True, fullPath=True) or []
        )

        if (
            not current_parent
            or short_name(current_parent[0]) != setup_group
        ):
            cmds.parent(node, setup_group)

    cmds.setAttr(setup_group + ".visibility", 0)

    print(
        "{} added to {} at weight index {}.".format(
            BREATH_MESH, BLENDSHAPE_NODE, target_index
        )
    )

    return setup_group, target_index


# ============================================================
# DELETE TEMPORARY TRANSFORMS
# ============================================================

def delete_temp_transforms():
    for node in ("transform2", "transform3", "transform4"):
        if not cmds.objExists(node):
            continue

        shapes = (
            cmds.listRelatives(node, shapes=True, fullPath=True) or []
        )

        children = (
            cmds.listRelatives(node, children=True, fullPath=True)
            or []
        )

        if not shapes and not children:
            safe_delete(node)


def finalize():
    cmds.connectAttr(
        "Chest_M_Ctrl.translateY", "Chest_M_Ctrl.Breath", force=True
    )
    cmds.setAttr(
        "Chest_M_Ctrl.tx", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.tz", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.rx", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.ry", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.rz", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.sx", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.sy", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.sz", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.v", lock=True, keyable=False, channelBox=False
    )
    cmds.setAttr(
        "Chest_M_Ctrl.Breath",
        lock=True,
        keyable=False,
        channelBox=False,
    )


# ============================================================
# MAIN BUILD
# ============================================================

def build(BODY_MESH):
    cmds.undoInfo(openChunk=True, chunkName="Build Breathing Setup")

    try:
        if not cmds.objExists(SKELETON_ROOT):
            cmds.error("Skeleton root not found: " + SKELETON_ROOT)

        if not cmds.objExists(BODY_MESH):
            cmds.error("Body mesh not found: " + BODY_MESH)

        if not cmds.objExists(SNAP_JOINT):
            cmds.error("Snap joint not found: " + SNAP_JOINT)

        scale_factor = get_global_scale(SKELETON_ROOT)

        delete_previous_setup()

        influences = build_breath_joints(scale_factor)

        update_mid_br_zero()

        # FIX 1: Pass BODY_MESH as first argument
        breathing_mesh, skin_cluster, upper_grp = duplicate_and_skin_body(
            BODY_MESH, influences, scale_factor
        )

        parent_constraint, scale_constraint = build_control(scale_factor)

        expression_node = install_breath_expression(scale_factor)

        # FIX 2: Pass BODY_MESH argument
        setup_group, blendshape_index = group_setup_and_add_blendshape(BODY_MESH)

        delete_temp_transforms()

        finalize()

        # Confirm nothing changed after setup grouping/constraints.
        print_br_zero_distance_report(
            title="FINAL BR ZERO GROUP DISTANCE CHECK"
        )

        cmds.select(CTRL, replace=True)

        print(
            "\nFinal breathing setup created.\n"
            "Detected Global Scale Factor: {}\n"
            "Breath Multiplier (Speed): {}\n"
            "Breathing mesh upper group: {}\n"
            "Mid_BR_zero updated.\n"
            "Breathing mesh: {}\n"
            "SkinCluster: {}\n"
            "Controller: {}\n"
            "Expression: {}\n"
            "Setup group: {}\n"
            "BlendShape index: {}\n"
            "Parent constraint: {}\n"
            "Scale constraint: {}\n".format(
                scale_factor,
                BREATH_MULTIPLIER,
                upper_grp,
                breathing_mesh,
                skin_cluster,
                CTRL,
                expression_node,
                setup_group,
                blendshape_index,
                parent_constraint,
                scale_constraint,
            )
        )

    finally:
        cmds.undoInfo(closeChunk=True)


# ============================================================
# ADD EXTRA MESHES TO BREATHING SETUP
# ============================================================

def add_breathing_extra_meshes(mesh_list, blendshape_map=None, use_001_scaling=False):
    """
    Adds additional meshes to the breathing rig setup.
    
    Args:
        mesh_list (str or list): Name or list of names of base meshes to add.
        blendshape_map (dict, optional): Mapping of {mesh_name: blendshape_node_name}.
                                         If None, auto-detects or creates a blendShape node.
        use_001_scaling (bool): If True, creates an upper group with 0.01 scale.
                                If False, disables upper group scaling and parents 
                                mesh directly at standard scale (1.0).
    """
    if isinstance(mesh_list, str):
        mesh_list = [mesh_list]

    if blendshape_map is None:
        blendshape_map = {}

    influences = ["Chest_BR", "Mid_BR", "Spine_BR", "Root"]

    # --- Pre-Checks ---
    missing_joints = [j for j in influences if not cmds.objExists(j)]
    if missing_joints:
        cmds.error("Missing breathing joints: {}. Run build() first.".format(", ".join(missing_joints)))

    if not cmds.objExists(SETUP_GROUP):
        cmds.error("Setup group '{}' not found. Run build() first.".format(SETUP_GROUP))

    cmds.undoInfo(openChunk=True, chunkName="Add Extra Breathing Meshes")

    processed = []

    try:
        for mesh in mesh_list:
            if not cmds.objExists(mesh):
                cmds.warning("Mesh not found, skipping: {}".format(mesh))
                continue

            breath_mesh_name = mesh + "_Breathing"
            breath_grp_name = breath_mesh_name + "_GRP"
            breath_skin_name = breath_mesh_name + "_skinCluster"

            # Clean previous iteration if re-running
            safe_delete(breath_skin_name)
            safe_delete(breath_grp_name)
            safe_delete(breath_mesh_name)

            # 1. Turn off skinClusters on original mesh first for clean duplicate
            skin_clusters = (
                cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster") or []
            )
            saved_envelopes = {}
            for sc in skin_clusters:
                saved_envelopes[sc] = cmds.getAttr(sc + ".envelope")
                cmds.setAttr(sc + ".envelope", 0)

            # 2. Duplicate Mesh
            dup_mesh = cmds.duplicate(mesh, returnRootsOnly=True, name=breath_mesh_name)[0]

            # Restore skinCluster envelope on original mesh
            for sc, env_val in saved_envelopes.items():
                cmds.setAttr(sc + ".envelope", env_val)

            # Clean construction history & unparent
            try:
                cmds.delete(dup_mesh, constructionHistory=True)
            except RuntimeError:
                pass

            dup_mesh = unparent_to_world(dup_mesh)
            unlock_transforms(dup_mesh)

            if short_name(dup_mesh) != breath_mesh_name:
                dup_mesh = cmds.rename(dup_mesh, breath_mesh_name)

            # 3. Handle Scaling & Grouping Option
            if use_001_scaling:
                # Create upper group with scale 0.01
                upper_grp = cmds.group(empty=True, name=breath_grp_name)
                cmds.xform(
                    upper_grp,
                    worldSpace=True,
                    matrix=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                )

                # Put duplicate mesh inside upper group FIRST
                cmds.parent(dup_mesh, upper_grp)

                # Set upper group scale to 0.01
                group_scale = 0.01
                cmds.setAttr(upper_grp + ".scaleX", group_scale)
                cmds.setAttr(upper_grp + ".scaleY", group_scale)
                cmds.setAttr(upper_grp + ".scaleZ", group_scale)

                # Parent upper group to setup group
                cmds.parent(upper_grp, SETUP_GROUP)
            else:
                # NO upper group scaling — parent duplicate mesh directly into setup group
                cmds.parent(dup_mesh, SETUP_GROUP)

            # 4. Skin duplicate mesh to breathing joints
            skin_cluster = cmds.skinCluster(
                influences,
                dup_mesh,
                toSelectedBones=True,
                bindMethod=0,
                skinMethod=0,
                normalizeWeights=1,
                maximumInfluences=5,
                obeyMaxInfluences=True,
                name=breath_skin_name
            )[0]

            # 5. Find or Create BlendShape Node on original mesh
            bs_node = blendshape_map.get(mesh)

            if not bs_node:
                raw_history = cmds.listHistory(mesh) or []
                history = cmds.ls(raw_history, type="blendShape") or []

                if history:
                    bs_node = history[0]
                else:
                    bs_node = cmds.blendShape(mesh, name="bs_{}".format(short_name(mesh)))[0]

            if not cmds.objExists(bs_node):
                cmds.error("BlendShape node '{}' does not exist.".format(bs_node))

            cmds.setAttr(bs_node + ".envelope", 1)

            # 6. Connect Duplicate to BlendShape Target
            target_index = None
            aliases = cmds.aliasAttr(bs_node, query=True) or []

            for alias, plug in zip(aliases[0::2], aliases[1::2]):
                if alias == breath_mesh_name:
                    target_index = int(plug.split("[")[-1].split("]")[0])
                    break

            if target_index is None:
                used_indices = cmds.getAttr(bs_node + ".weight", multiIndices=True) or []
                target_index = max(used_indices) + 1 if used_indices else 0

                cmds.blendShape(
                    bs_node,
                    edit=True,
                    topologyCheck=True,
                    target=(mesh, target_index, dup_mesh, 1.0)
                )

            # Turn weight on fully
            weight_plug = "{}.weight[{}]".format(bs_node, target_index)
            disconnect_and_unlock(weight_plug)
            cmds.setAttr(weight_plug, 1.0)

            processed.append((mesh, dup_mesh, bs_node, target_index))

            print("Successfully added '{}' -> target '{}' on '{}' (0.01 Scale: {}).".format(
                mesh, dup_mesh, bs_node, use_001_scaling
            ))

    finally:
        cmds.undoInfo(closeChunk=True)

    return processed


# ==========================================
# 1. RUN PRIMARY BREATHING SETUP
# ==========================================
def main(Body_Mesh, mesh_list=None, use_001_scaling=False):
    if mesh_list is None:
        mesh_list = []

    build(
        BODY_MESH=Body_Mesh,
    )

    # ==========================================
    # 2. ADD ADDITIONAL MESHES (RUN AFTER)
    # ==========================================
    if mesh_list:
        add_breathing_extra_meshes(
            mesh_list=mesh_list,
            use_001_scaling=use_001_scaling,
        )


# Compatibility wrapper:
# The original pasted code called run_breathing(), but only main() existed.
def run_breathing(Body_Mesh, mesh_list=None, use_001_scaling=False):
    return main(
        Body_Mesh=Body_Mesh,
        mesh_list=mesh_list,
        use_001_scaling=use_001_scaling,
    )
