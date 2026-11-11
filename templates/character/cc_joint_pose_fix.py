# CC JOINT POSE FIX - put the elbow/knee chain joints back on the straight
# line between shoulder->hand and hip->foot, sliding each joint along its own
# local X only. Children stay where they are and the skin does not move
# (bindPreMatrix is updated). Uses create_curve_on_joints() from utils.py.
import maya.cmds as cmds
import maya.api.OpenMaya as om


def set_joint_on_curve_preserve_mesh(joints, curve, axis="x"):
    """
    Snaps one or multiple skinned joints along a specified LOCAL axis to the closest
    point on a target curve, preserving child joint transforms and keeping the bound skin mesh static.

    :param joints: Single joint name (str) OR a list/tuple of joint names.
    :param curve: Name of the target curve node or transform.
    :param axis: Local axis to move along ('x', 'y', or 'z'). Case-insensitive.
    """
    if isinstance(joints, str):
        joints = [joints]

    axis = axis.lower()
    axis_indices = {'x': 0, 'y': 1, 'z': 2}
    if axis not in axis_indices:
        cmds.warning(f"Invalid axis '{axis}'. Choose 'x', 'y', or 'z'.")
        return

    if not cmds.objExists(curve):
        cmds.warning(f"Curve '{curve}' does not exist.")
        return

    curve_shapes = cmds.listRelatives(curve, shapes=True, type="nurbsCurve") or [curve]
    selection_list = om.MSelectionList()
    selection_list.add(curve_shapes[0])
    try:
        mfn_curve = om.MFnNurbsCurve(selection_list.getDagPath(0))
    except TypeError:
        cmds.warning(f"Object '{curve}' is not a valid NURBS curve.")
        return

    target_attr = {'x': 'translateX', 'y': 'translateY', 'z': 'translateZ'}[axis]

    for joint in joints:
        if not cmds.objExists(joint):
            cmds.warning(f"Joint '{joint}' does not exist. Skipping.")
            continue

        # A. remember where the direct children are in world space
        children = cmds.listRelatives(joint, children=True, type="transform") or []
        child_world_matrices = {
            child: cmds.xform(child, query=True, worldSpace=True, matrix=True)
            for child in children
        }

        # B. how far along its own local axis the joint must slide to reach the curve
        joint_pos = om.MPoint(cmds.xform(joint, query=True, worldSpace=True, translation=True))
        joint_wm = om.MMatrix(cmds.getAttr(f"{joint}.worldMatrix[0]"))
        i = axis_indices[axis]
        axis_vector = om.MVector(joint_wm[i * 4], joint_wm[i * 4 + 1], joint_wm[i * 4 + 2]).normalize()
        closest_point, _ = mfn_curve.closestPoint(joint_pos, space=om.MSpace.kWorld)
        distance_shift = (closest_point - joint_pos) * axis_vector

        # C. slide it
        cmds.setAttr(f"{joint}.{target_attr}", cmds.getAttr(f"{joint}.{target_attr}") + distance_shift)

        # D. put the children back
        for child, original_matrix in child_world_matrices.items():
            cmds.xform(child, worldSpace=True, matrix=original_matrix)

        # E. new bind pose for every skinCluster this joint drives -> mesh stays still
        connections = cmds.listConnections(
            f"{joint}.worldMatrix[0]", type="skinCluster", connections=True, plugs=True) or []
        for k in range(0, len(connections), 2):
            dst_plug = connections[k + 1]
            if ".matrix[" in dst_plug:
                skin_node, attr_name = dst_plug.split(".")
                index = attr_name.split("[")[1].split("]")[0]
                cmds.setAttr(f"{skin_node}.bindPreMatrix[{index}]",
                             cmds.getAttr(f"{joint}.worldInverseMatrix[0]"), type="matrix")


# (start joint, end joint, joints to slide onto the start->end line)
LIMBS = [
    ("CC_Base_L_Upperarm", "CC_Base_L_Hand",
     ["CC_Base_L_Forearm", "CC_Base_L_ForearmTwist01", "CC_Base_L_ElbowShareBone",
      "CC_Base_L_UpperarmTwist02", "CC_Base_L_ForearmTwist02"]),
    ("CC_Base_R_Upperarm", "CC_Base_R_Hand",
     ["CC_Base_R_Forearm", "CC_Base_R_ForearmTwist01", "CC_Base_R_ElbowShareBone",
      "CC_Base_R_UpperarmTwist02", "CC_Base_R_ForearmTwist02"]),
    ("CC_Base_L_Thigh", "CC_Base_L_Foot",
     ["CC_Base_L_Calf", "CC_Base_L_CalfTwist01", "CC_Base_L_KneeShareBone"]),
    ("CC_Base_R_Thigh", "CC_Base_R_Foot",
     ["CC_Base_R_Calf", "CC_Base_R_CalfTwist01", "CC_Base_R_KneeShareBone"]),
]

for start, end, joints_list in LIMBS:
    # use the name the curve really got - 'jnt_connection_crv1' is only
    # right when no other curve of that name already exists
    my_curve = create_curve_on_joints(start, end)
    if not my_curve:
        continue
    set_joint_on_curve_preserve_mesh(joints_list, my_curve, axis="x")
    cmds.delete(my_curve)
