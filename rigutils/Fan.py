import maya.cmds as cmds
import maya.api.OpenMaya as om


# ============================================================
# HELPERS
# ============================================================

def get_mesh_fn(mesh_name):
    """
    Return an OpenMaya MFnMesh from a mesh transform or shape.
    """

    if not cmds.objExists(mesh_name):
        raise RuntimeError(
            "Mesh does not exist: {}".format(mesh_name)
        )

    if cmds.nodeType(mesh_name) == "transform":
        shapes = cmds.listRelatives(
            mesh_name,
            shapes=True,
            noIntermediate=True,
            fullPath=True
        ) or []

        mesh_shapes = [
            shape for shape in shapes
            if cmds.nodeType(shape) == "mesh"
        ]

        if not mesh_shapes:
            raise RuntimeError(
                "No mesh shape found below: {}".format(mesh_name)
            )

        mesh_name = mesh_shapes[0]

    if cmds.nodeType(mesh_name) != "mesh":
        raise RuntimeError(
            "Object is not a mesh: {}".format(mesh_name)
        )

    selection_list = om.MSelectionList()
    selection_list.add(mesh_name)

    dag_path = selection_list.getDagPath(0)
    return om.MFnMesh(dag_path)


def add_keyable_double(
        node,
        attribute_name,
        default_value=0.0
):
    """
    Add a keyable double attribute if it does not already exist.
    """

    if not cmds.attributeQuery(
        attribute_name,
        node=node,
        exists=True
    ):
        cmds.addAttr(
            node,
            longName=attribute_name,
            attributeType="double",
            defaultValue=default_value
        )

    cmds.setAttr(
        "{}.{}".format(node, attribute_name),
        keyable=True
    )


def add_keyable_enum(
        node,
        attribute_name,
        enum_names,
        default_value=0
):
    """
    Add a keyable enum attribute if it does not already exist.
    """

    if not cmds.attributeQuery(
        attribute_name,
        node=node,
        exists=True
    ):
        cmds.addAttr(
            node,
            longName=attribute_name,
            attributeType="enum",
            enumName=enum_names,
            defaultValue=default_value
        )

    cmds.setAttr(
        "{}.{}".format(node, attribute_name),
        keyable=True
    )


def clean_node_name(name):
    """
    Convert a DAG or namespace name into a safe DG-node prefix.
    """

    return (
        name.split("|")[-1]
        .replace(":", "_")
        .replace(" ", "_")
    )


# ============================================================
# MAIN FUNCTION
# ============================================================

def create_mesh_projected_fan_joints(
        target_joint,
        target_mesh,
        radius=1.0,
        max_search_distance=100.0,
        offset_rot=(0.0, 0.0, 0.0)
):
    """
    Create a mesh-projected four-joint fan setup.

    Base-joint source options:

        None
        Rot X
        Rot Y
        Rot Z
        Reverse Rot X
        Reverse Rot Y
        Reverse Rot Z

    Fan-joint source options:

        Rot X
        Rot Y
        Rot Z
        Reverse Rot X
        Reverse Rot Y
        Reverse Rot Z

    Base-joint speed attributes:

        rotationSpeedX
        rotationSpeedY
        rotationSpeedZ

    Speed examples:

        0.0 = no rotation
        0.5 = half rotation
        1.0 = normal rotation
        2.0 = double rotation
       -1.0 = additional direction reversal
    """

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not cmds.objExists(target_joint):
        cmds.warning(
            "Target joint does not exist: {}".format(target_joint)
        )
        return None

    if cmds.nodeType(target_joint) != "joint":
        cmds.warning(
            "Target object is not a joint: {}".format(target_joint)
        )
        return None

    if not cmds.objExists(target_mesh):
        cmds.warning(
            "Target mesh does not exist: {}".format(target_mesh)
        )
        return None

    try:
        mesh_fn = get_mesh_fn(target_mesh)

    except Exception as error:
        cmds.warning(str(error))
        return None

    target_short_name = target_joint.split("|")[-1]
    node_prefix = clean_node_name(target_joint)

    offset_fan_name = "{}_fan_offset_jnt".format(
        target_short_name
    )

    master_fan_name = "{}_fan_base_jnt".format(
        target_short_name
    )

    if (
        cmds.objExists(offset_fan_name) or
        cmds.objExists(master_fan_name)
    ):
        cmds.warning(
            "Fan setup already exists for: {}".format(target_joint)
        )
        return None

    # --------------------------------------------------------
    # 1. CREATE OFFSET JOINT
    # --------------------------------------------------------

    cmds.select(
        target_joint,
        replace=True
    )

    offset_jnt = cmds.joint(
        name=offset_fan_name
    )

    offset_jnt = cmds.ls(
        offset_jnt,
        long=True
    )[0]

    cmds.setAttr(
        "{}.radius".format(offset_jnt),
        radius * 2.5
    )

    cmds.setAttr(
        "{}.rotateX".format(offset_jnt),
        offset_rot[0]
    )

    cmds.setAttr(
        "{}.rotateY".format(offset_jnt),
        offset_rot[1]
    )

    cmds.setAttr(
        "{}.rotateZ".format(offset_jnt),
        offset_rot[2]
    )

    # --------------------------------------------------------
    # 2. CREATE MASTER FAN JOINT
    # --------------------------------------------------------

    cmds.select(
        offset_jnt,
        replace=True
    )

    master_jnt = cmds.joint(
        name=master_fan_name
    )

    master_jnt = cmds.ls(
        master_jnt,
        long=True
    )[0]

    cmds.setAttr(
        "{}.radius".format(master_jnt),
        radius * 2.0
    )

    cmds.setAttr(
        "{}.overrideEnabled".format(master_jnt),
        1
    )

    cmds.setAttr(
        "{}.overrideColor".format(master_jnt),
        16
    )

    for attribute in [
        "tx", "ty", "tz",
        "rx", "ry", "rz",
        "jox", "joy", "joz"
    ]:
        cmds.setAttr(
            "{}.{}".format(master_jnt, attribute),
            0
        )

    # --------------------------------------------------------
    # 3. MASTER-JOINT ATTRIBUTES
    # --------------------------------------------------------

    master_axis_enum = (
        "None:"
        "Rot X:"
        "Rot Y:"
        "Rot Z:"
        "Reverse Rot X:"
        "Reverse Rot Y:"
        "Reverse Rot Z"
    )

    default_master_sources = {
        "X": 1,
        "Y": 2,
        "Z": 3
    }

    for axis in ["X", "Y", "Z"]:
        source_attribute = "driveMaster{}_from".format(axis)
        speed_attribute = "rotationSpeed{}".format(axis)

        add_keyable_enum(
            master_jnt,
            source_attribute,
            master_axis_enum,
            default_master_sources[axis]
        )

        cmds.setAttr(
            "{}.{}".format(master_jnt, source_attribute),
            default_master_sources[axis]
        )

        add_keyable_double(
            master_jnt,
            speed_attribute,
            1.0
        )

        cmds.setAttr(
            "{}.{}".format(master_jnt, speed_attribute),
            1.0
        )

    # --------------------------------------------------------
    # 4. MASTER ROTATION NETWORK
    # --------------------------------------------------------
    #
    # Important:
    #
    # Reverse options do not pass through a separate rotation
    # inversion node.
    #
    # Instead:
    #
    #   selected rotation × selected sign × rotation speed
    #
    # This avoids Maya angle-unit conversion problems.
    # --------------------------------------------------------

    for driven_axis in ["X", "Y", "Z"]:

        source_choice = cmds.createNode(
            "choice",
            name="{}_master{}_source_choice".format(
                node_prefix,
                driven_axis
            )
        )

        sign_choice = cmds.createNode(
            "choice",
            name="{}_master{}_sign_choice".format(
                node_prefix,
                driven_axis
            )
        )

        signed_rotation_md = cmds.createNode(
            "multiplyDivide",
            name="{}_master{}_signedRotation_MD".format(
                node_prefix,
                driven_axis
            )
        )

        speed_md = cmds.createNode(
            "multiplyDivide",
            name="{}_master{}_rotationSpeed_MD".format(
                node_prefix,
                driven_axis
            )
        )

        cmds.setAttr(
            "{}.operation".format(signed_rotation_md),
            1
        )

        cmds.setAttr(
            "{}.operation".format(speed_md),
            1
        )

        selector_attribute = (
            "{}.driveMaster{}_from".format(
                master_jnt,
                driven_axis
            )
        )

        cmds.connectAttr(
            selector_attribute,
            "{}.selector".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            selector_attribute,
            "{}.selector".format(sign_choice),
            force=True
        )

        # Source choice:
        #
        # 0 = None
        # 1 = X
        # 2 = Y
        # 3 = Z
        # 4 = Reverse X, but source remains X
        # 5 = Reverse Y, but source remains Y
        # 6 = Reverse Z, but source remains Z

        cmds.setAttr(
            "{}.input[0]".format(source_choice),
            0.0
        )

        cmds.connectAttr(
            "{}.rotateX".format(target_joint),
            "{}.input[1]".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateY".format(target_joint),
            "{}.input[2]".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateZ".format(target_joint),
            "{}.input[3]".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateX".format(target_joint),
            "{}.input[4]".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateY".format(target_joint),
            "{}.input[5]".format(source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateZ".format(target_joint),
            "{}.input[6]".format(source_choice),
            force=True
        )

        # Sign choice:
        #
        # None      = 0
        # Normal    = 1
        # Reverse   = -1

        cmds.setAttr(
            "{}.input[0]".format(sign_choice),
            0.0
        )

        cmds.setAttr(
            "{}.input[1]".format(sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[2]".format(sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[3]".format(sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[4]".format(sign_choice),
            -1.0
        )

        cmds.setAttr(
            "{}.input[5]".format(sign_choice),
            -1.0
        )

        cmds.setAttr(
            "{}.input[6]".format(sign_choice),
            -1.0
        )

        # Selected rotation × normal/reverse sign

        cmds.connectAttr(
            "{}.output".format(source_choice),
            "{}.input1X".format(signed_rotation_md),
            force=True
        )

        cmds.connectAttr(
            "{}.output".format(sign_choice),
            "{}.input2X".format(signed_rotation_md),
            force=True
        )

        # Signed rotation × animator speed

        cmds.connectAttr(
            "{}.outputX".format(signed_rotation_md),
            "{}.input1X".format(speed_md),
            force=True
        )

        cmds.connectAttr(
            "{}.rotationSpeed{}".format(
                master_jnt,
                driven_axis
            ),
            "{}.input2X".format(speed_md),
            force=True
        )

        # Final master-joint rotation

        cmds.connectAttr(
            "{}.outputX".format(speed_md),
            "{}.rotate{}".format(
                master_jnt,
                driven_axis
            ),
            force=True
        )

    # --------------------------------------------------------
    # 5. RAYCAST SETUP
    # --------------------------------------------------------

    direction_map = {
        "_up": {
            "vector": om.MVector(-1.0, 0.0, 0.0),
            "translation_axis": "X",
            "invert_offset": True
        },

        "_down": {
            "vector": om.MVector(0.0, 0.0, -1.0),
            "translation_axis": "Z",
            "invert_offset": True
        },

        "_front": {
            "vector": om.MVector(1.0, 0.0, 0.0),
            "translation_axis": "X",
            "invert_offset": False
        },

        "_back": {
            "vector": om.MVector(0.0, 0.0, 1.0),
            "translation_axis": "Z",
            "invert_offset": False
        }
    }

    master_world_matrix_values = cmds.xform(
        master_jnt,
        query=True,
        matrix=True,
        worldSpace=True
    )

    master_world_matrix = om.MMatrix(
        master_world_matrix_values
    )

    ray_source = om.MFloatPoint(
        master_world_matrix_values[12],
        master_world_matrix_values[13],
        master_world_matrix_values[14]
    )

    fan_axis_enum = (
        "Rot X:"
        "Rot Y:"
        "Rot Z:"
        "Reverse Rot X:"
        "Reverse Rot Y:"
        "Reverse Rot Z"
    )

    created_fan_joints = []

    # --------------------------------------------------------
    # 6. CREATE FOUR FAN JOINTS
    # --------------------------------------------------------

    for suffix, direction_info in direction_map.items():

        fan_name = "{}_fan{}_jnt".format(
            target_short_name,
            suffix
        )

        fan_prefix = "{}_fan{}".format(
            node_prefix,
            suffix
        )

        if cmds.objExists(fan_name):
            cmds.warning(
                "Fan joint already exists, skipping: {}".format(
                    fan_name
                )
            )
            continue

        # ----------------------------------------------------
        # RAYCAST
        # ----------------------------------------------------

        local_vector = direction_info["vector"]
        world_vector = local_vector * master_world_matrix

        ray_direction = om.MFloatVector(
            world_vector.x,
            world_vector.y,
            world_vector.z
        )

        ray_direction.normalize()

        intersection_result = mesh_fn.allIntersections(
            ray_source,
            ray_direction,
            om.MSpace.kWorld,
            max_search_distance,
            False
        )

        offset_distance = 1.0

        if intersection_result:
            hit_ray_parameters = intersection_result[1]

            if hit_ray_parameters:
                offset_distance = hit_ray_parameters[0]

        if direction_info["invert_offset"]:
            offset_distance *= -1.0

        # ----------------------------------------------------
        # CREATE FAN JOINT
        # ----------------------------------------------------

        cmds.select(
            master_jnt,
            replace=True
        )

        fan_jnt = cmds.joint(
            name=fan_name
        )

        fan_jnt = cmds.ls(
            fan_jnt,
            long=True
        )[0]

        created_fan_joints.append(fan_jnt)

        cmds.setAttr(
            "{}.radius".format(fan_jnt),
            radius
        )

        for attribute in [
            "tx", "ty", "tz",
            "rx", "ry", "rz",
            "jox", "joy", "joz"
        ]:
            cmds.setAttr(
                "{}.{}".format(fan_jnt, attribute),
                0
            )

        # ----------------------------------------------------
        # FAN ATTRIBUTES
        # ----------------------------------------------------

        add_keyable_enum(
            fan_jnt,
            "drivenByAxis",
            fan_axis_enum,
            0
        )

        add_keyable_double(
            fan_jnt,
            "driverStart",
            0.0
        )

        add_keyable_double(
            fan_jnt,
            "driverEnd",
            90.0
        )

        cmds.setAttr(
            "{}.driverStart".format(fan_jnt),
            0.0
        )

        cmds.setAttr(
            "{}.driverEnd".format(fan_jnt),
            90.0
        )

        # ----------------------------------------------------
        # BASE MESH OFFSETS
        # ----------------------------------------------------

        base_offsets = {
            "X": 0.0,
            "Y": 0.0,
            "Z": 0.0
        }

        translation_axis = direction_info[
            "translation_axis"
        ]

        base_offsets[translation_axis] = offset_distance

        for axis in ["X", "Y", "Z"]:
            base_attribute = "baseMeshOffset{}".format(axis)
            forward_attribute = "targetOffsetFwd{}".format(axis)
            backward_attribute = "targetOffsetBwd{}".format(axis)

            add_keyable_double(
                fan_jnt,
                base_attribute,
                base_offsets[axis]
            )

            add_keyable_double(
                fan_jnt,
                forward_attribute,
                base_offsets[axis]
            )

            add_keyable_double(
                fan_jnt,
                backward_attribute,
                base_offsets[axis]
            )

            cmds.setAttr(
                "{}.{}".format(fan_jnt, base_attribute),
                base_offsets[axis]
            )

            cmds.setAttr(
                "{}.{}".format(fan_jnt, forward_attribute),
                base_offsets[axis]
            )

            cmds.setAttr(
                "{}.{}".format(fan_jnt, backward_attribute),
                base_offsets[axis]
            )

        # ----------------------------------------------------
        # FAN SOURCE AND REVERSE SIGN
        # ----------------------------------------------------

        fan_source_choice = cmds.createNode(
            "choice",
            name="{}_source_choice".format(fan_prefix)
        )

        fan_sign_choice = cmds.createNode(
            "choice",
            name="{}_sign_choice".format(fan_prefix)
        )

        fan_signed_driver_md = cmds.createNode(
            "multiplyDivide",
            name="{}_signedDriver_MD".format(fan_prefix)
        )

        cmds.setAttr(
            "{}.operation".format(fan_signed_driver_md),
            1
        )

        cmds.connectAttr(
            "{}.drivenByAxis".format(fan_jnt),
            "{}.selector".format(fan_source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.drivenByAxis".format(fan_jnt),
            "{}.selector".format(fan_sign_choice),
            force=True
        )

        # Normal sources

        cmds.connectAttr(
            "{}.rotateX".format(master_jnt),
            "{}.input[0]".format(fan_source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateY".format(master_jnt),
            "{}.input[1]".format(fan_source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateZ".format(master_jnt),
            "{}.input[2]".format(fan_source_choice),
            force=True
        )

        # Reverse options use the same source values.
        # The separate sign selector performs the reversal.

        cmds.connectAttr(
            "{}.rotateX".format(master_jnt),
            "{}.input[3]".format(fan_source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateY".format(master_jnt),
            "{}.input[4]".format(fan_source_choice),
            force=True
        )

        cmds.connectAttr(
            "{}.rotateZ".format(master_jnt),
            "{}.input[5]".format(fan_source_choice),
            force=True
        )

        # Signs:
        #
        # 0 = Rot X
        # 1 = Rot Y
        # 2 = Rot Z
        # 3 = Reverse Rot X
        # 4 = Reverse Rot Y
        # 5 = Reverse Rot Z

        cmds.setAttr(
            "{}.input[0]".format(fan_sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[1]".format(fan_sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[2]".format(fan_sign_choice),
            1.0
        )

        cmds.setAttr(
            "{}.input[3]".format(fan_sign_choice),
            -1.0
        )

        cmds.setAttr(
            "{}.input[4]".format(fan_sign_choice),
            -1.0
        )

        cmds.setAttr(
            "{}.input[5]".format(fan_sign_choice),
            -1.0
        )

        cmds.connectAttr(
            "{}.output".format(fan_source_choice),
            "{}.input1X".format(fan_signed_driver_md),
            force=True
        )

        cmds.connectAttr(
            "{}.output".format(fan_sign_choice),
            "{}.input2X".format(fan_signed_driver_md),
            force=True
        )

        # ----------------------------------------------------
        # CONVERT INTERNAL ANGLE VALUE TO VISIBLE DEGREES
        # ----------------------------------------------------
        #
        # The selected master-joint rotation reaches the
        # multiplyDivide as Maya's internal angle value.
        #
        # driverStart and driverEnd are intended to use visible
        # values such as 0 and 90 degrees.
        # ----------------------------------------------------

        radians_to_degrees_md = cmds.createNode(
            "multiplyDivide",
            name="{}_radiansToDegrees_MD".format(fan_prefix)
        )

        cmds.setAttr(
            "{}.operation".format(radians_to_degrees_md),
            1
        )

        cmds.connectAttr(
            "{}.outputX".format(fan_signed_driver_md),
            "{}.input1X".format(radians_to_degrees_md),
            force=True
        )

        cmds.setAttr(
            "{}.input2X".format(radians_to_degrees_md),
            57.29577951308232
        )

        # ----------------------------------------------------
        # ABSOLUTE DRIVER VALUE
        # ----------------------------------------------------

        invert_for_absolute_md = cmds.createNode(
            "multiplyDivide",
            name="{}_absoluteInvert_MD".format(fan_prefix)
        )

        cmds.setAttr(
            "{}.operation".format(invert_for_absolute_md),
            1
        )

        cmds.connectAttr(
            "{}.outputX".format(radians_to_degrees_md),
            "{}.input1X".format(invert_for_absolute_md),
            force=True
        )

        cmds.setAttr(
            "{}.input2X".format(invert_for_absolute_md),
            -1.0
        )

        absolute_condition = cmds.createNode(
            "condition",
            name="{}_absolute_COND".format(fan_prefix)
        )

        # Less Than
        cmds.setAttr(
            "{}.operation".format(absolute_condition),
            4
        )

        cmds.connectAttr(
            "{}.outputX".format(radians_to_degrees_md),
            "{}.firstTerm".format(absolute_condition),
            force=True
        )

        cmds.setAttr(
            "{}.secondTerm".format(absolute_condition),
            0.0
        )

        cmds.connectAttr(
            "{}.outputX".format(invert_for_absolute_md),
            "{}.colorIfTrueR".format(absolute_condition),
            force=True
        )

        cmds.connectAttr(
            "{}.outputX".format(radians_to_degrees_md),
            "{}.colorIfFalseR".format(absolute_condition),
            force=True
        )

        # ----------------------------------------------------
        # FORWARD/BACKWARD DIRECTION
        # ----------------------------------------------------

        direction_condition = cmds.createNode(
            "condition",
            name="{}_direction_COND".format(fan_prefix)
        )

        # Greater Than
        cmds.setAttr(
            "{}.operation".format(direction_condition),
            2
        )

        cmds.connectAttr(
            "{}.outputX".format(radians_to_degrees_md),
            "{}.firstTerm".format(direction_condition),
            force=True
        )

        cmds.setAttr(
            "{}.secondTerm".format(direction_condition),
            0.0
        )

        color_channels = {
            "X": "R",
            "Y": "G",
            "Z": "B"
        }

        # ----------------------------------------------------
        # TRANSLATION REMAP NETWORK
        # ----------------------------------------------------

        for axis in ["X", "Y", "Z"]:
            color_channel = color_channels[axis]

            cmds.connectAttr(
                "{}.targetOffsetFwd{}".format(
                    fan_jnt,
                    axis
                ),
                "{}.colorIfTrue{}".format(
                    direction_condition,
                    color_channel
                ),
                force=True
            )

            cmds.connectAttr(
                "{}.targetOffsetBwd{}".format(
                    fan_jnt,
                    axis
                ),
                "{}.colorIfFalse{}".format(
                    direction_condition,
                    color_channel
                ),
                force=True
            )

            remap_node = cmds.createNode(
                "remapValue",
                name="{}_translate{}_RV".format(
                    fan_prefix,
                    axis
                )
            )

            cmds.connectAttr(
                "{}.outColorR".format(absolute_condition),
                "{}.inputValue".format(remap_node),
                force=True
            )

            cmds.connectAttr(
                "{}.driverStart".format(fan_jnt),
                "{}.inputMin".format(remap_node),
                force=True
            )

            cmds.connectAttr(
                "{}.driverEnd".format(fan_jnt),
                "{}.inputMax".format(remap_node),
                force=True
            )

            cmds.connectAttr(
                "{}.baseMeshOffset{}".format(
                    fan_jnt,
                    axis
                ),
                "{}.outputMin".format(remap_node),
                force=True
            )

            cmds.connectAttr(
                "{}.outColor{}".format(
                    direction_condition,
                    color_channel
                ),
                "{}.outputMax".format(remap_node),
                force=True
            )

            cmds.connectAttr(
                "{}.outValue".format(remap_node),
                "{}.translate{}".format(
                    fan_jnt,
                    axis
                ),
                force=True
            )

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    cmds.select(
        master_jnt,
        replace=True
    )

    print("")
    print("Fan-joint setup created successfully.")
    print("Target joint: {}".format(target_joint))
    print("Target mesh: {}".format(target_mesh))
    print("Master joint: {}".format(master_jnt))
    print(
        "Fan joints created: {}".format(
            len(created_fan_joints)
        )
    )
    print("")
    print("Normal and reverse sources are active.")
    print("rotationSpeedX/Y/Z are live multipliers.")
    print("")

    return master_jnt

def delete_all_fan_joints_in_scene():
    objects_to_clear = cmds.ls("*_fan*", type=['joint', 'multiplyDivide', 'choice', 'plusMinusAverage', 'clamp', 'condition', 'remapValue']) or []
    
    if not objects_to_clear:
        print("No rigging elements found to clean up.")
        return
        
    deleted_count = 0
    for node in set(objects_to_clear):
        if cmds.objExists(node):
            try:
                cmds.lockNode(node, lock=False)
                cmds.delete(node)
                deleted_count += 1
            except Exception:
                pass
                
    print(f"Global cleanup complete! Safely cleared {deleted_count} rigging objects.")



def export_fan_joint_attributes():
    base_joints = cmds.ls("*_fan_base_jnt", type="joint") or []
    
    if not base_joints:
        print("# No fan joints found in the scene.")
        return

    print("\n# " + "="*40)
    print("# FAN JOINT ATTRIBUTE EXPORT")
    print("# " + "="*40)
    
    for base_jnt in base_joints:
        prefix = base_jnt.replace("_fan_base_jnt", "")
        nice_name = prefix.replace("_", " ")
        
        # 1. Base Joint Attributes
        print(f"\n# {nice_name} Base")
        base_attrs = [
            "driveMasterX_from", "driveMasterY_from", "driveMasterZ_from",
            "rotationSpeedX", "rotationSpeedY", "rotationSpeedZ"
        ]
        
        for attr in base_attrs:
            plug = f"{base_jnt}.{attr}"
            if cmds.objExists(plug):
                val = cmds.getAttr(plug)
                if isinstance(val, float): val = round(val, 3)
                print(f'cmds.setAttr("{plug}", {val})')
        
        # 2. Sub-Joint Attributes
        print(f"\n# {nice_name} Fan Directions")
        directions = ["_up", "_down", "_front", "_back"]
        sub_attrs = [
            "drivenByAxis", "driverStart", "driverEnd",
            "baseMeshOffsetX", "baseMeshOffsetY", "baseMeshOffsetZ",
            "targetOffsetFwdX", "targetOffsetFwdY", "targetOffsetFwdZ",
            "targetOffsetBwdX", "targetOffsetBwdY", "targetOffsetBwdZ"
        ]
        
        for suffix in directions:
            fan_jnt = f"{prefix}_fan{suffix}_jnt"
            if cmds.objExists(fan_jnt):
                for attr in sub_attrs:
                    plug = f"{fan_jnt}.{attr}"
                    if cmds.objExists(plug):
                        val = cmds.getAttr(plug)
                        if isinstance(val, float): val = round(val, 3)
                        print(f'cmds.setAttr("{plug}", {val})')

    print("\n# " + "="*40)
    print("# END EXPORT")
    print("# " + "="*40 + "\n")



def advanced_mirror_fan_setup(
    direction="L_to_R",
    suffix_map=None,          
    invert_fwd_bwd_on=(),     
    invert_delta_axes=("X", "Y", "Z") 
):
    source_str = "_L_" if direction == "L_to_R" else "_R_"
    target_str = "_R_" if direction == "L_to_R" else "_L_"

    # Default 1:1 mapping if no custom map is provided
    if suffix_map is None:
        suffix_map = {"_up": "_up", "_down": "_down", "_front": "_front", "_back": "_back"}

    base_joints = cmds.ls(f"*{source_str}*_fan_base_jnt", type="joint") or []

    if not base_joints:
        print(f"# No source fan joints found containing '{source_str}'.")
        return

    base_attrs = [
        "driveMasterX_from", "driveMasterY_from", "driveMasterZ_from",
        "rotationSpeedX", "rotationSpeedY", "rotationSpeedZ"
    ]

    sub_attrs_direct = ["drivenByAxis", "driverStart", "driverEnd"]
    axes = ["X", "Y", "Z"]

    print(f"\n# EXECUTING ADVANCED MIRROR: {direction}")

    for src_base in base_joints:
        tgt_base = src_base.replace(source_str, target_str)

        if not cmds.objExists(tgt_base):
            continue

        # 1. Base Attributes (Direct Copy)
        for attr in base_attrs:
            src_plug, tgt_plug = f"{src_base}.{attr}", f"{tgt_base}.{attr}"
            if cmds.objExists(src_plug) and cmds.objExists(tgt_plug):
                cmds.setAttr(tgt_plug, cmds.getAttr(src_plug))

        # 2. Sub-Joints (Mapped via suffix_map)
        prefix_src = src_base.replace("_fan_base_jnt", "")
        prefix_tgt = tgt_base.replace("_fan_base_jnt", "")

        for src_sfx, tgt_sfx in suffix_map.items():
            src_fan = f"{prefix_src}_fan{src_sfx}_jnt"
            tgt_fan = f"{prefix_tgt}_fan{tgt_sfx}_jnt"

            if not (cmds.objExists(src_fan) and cmds.objExists(tgt_fan)):
                continue

            # Copy standard attributes
            for attr in sub_attrs_direct:
                src_plug, tgt_plug = f"{src_fan}.{attr}", f"{tgt_fan}.{attr}"
                if cmds.objExists(src_plug) and cmds.objExists(tgt_plug):
                    cmds.setAttr(tgt_plug, cmds.getAttr(src_plug))

            # DELTA MATH FOR TARGETS
            swap_targets = tgt_sfx in invert_fwd_bwd_on

            for ax in axes:
                # Get Source Values
                src_base_val = cmds.getAttr(f"{src_fan}.baseMeshOffset{ax}")
                src_fwd_val = cmds.getAttr(f"{src_fan}.targetOffsetFwd{ax}")
                src_bwd_val = cmds.getAttr(f"{src_fan}.targetOffsetBwd{ax}")

                # Calculate Source Movement (Delta)
                delta_fwd = src_fwd_val - src_base_val
                delta_bwd = src_bwd_val - src_base_val

                # Flip sign for mirrored axes
                if ax in invert_delta_axes:
                    delta_fwd *= -1.0
                    delta_bwd *= -1.0

                # Get Target's Native Raycast Base
                tgt_base_val = cmds.getAttr(f"{tgt_fan}.baseMeshOffset{ax}")

                # Apply Delta to Target Base (handling Fwd/Bwd swaps)
                if swap_targets:
                    final_fwd = tgt_base_val + delta_bwd
                    final_bwd = tgt_base_val + delta_fwd
                else:
                    final_fwd = tgt_base_val + delta_fwd
                    final_bwd = tgt_base_val + delta_bwd

                # Apply final math
                cmds.setAttr(f"{tgt_fan}.targetOffsetFwd{ax}", final_fwd)
                cmds.setAttr(f"{tgt_fan}.targetOffsetBwd{ax}", final_bwd)

        print(f"Successfully processed: {src_base} -> {tgt_base}")











# --- RUN CODE ---
#export_fan_joint_attributes()


# Example 1: For the Thighs (Notice the suffix mapping swaps Up/Front and Down/Back)
'''advanced_mirror_fan_setup(
    direction="L_to_R",
    suffix_map={"_up": "_front", "_front": "_up", "_down": "_back", "_back": "_down"},
    invert_delta_axes=("X", "Y", "Z"),
    invert_fwd_bwd_on=() 
)'''

# Example 2: For the Arms (Standard 1:1 suffix mapping, but swapping Fwd/Bwd)
'''advanced_mirror_fan_setup(
    direction="L_to_R",
    suffix_map={"_up": "_up", "_down": "_down", "_front": "_front", "_back": "_back"},
    invert_delta_axes=("X", "Y", "Z"),
    invert_fwd_bwd_on=("_up", "_front") 
)'''



def L_FanValue():

    # ========================================
    # FAN JOINT ATTRIBUTE EXPORT
    # ========================================

    # CC Base FacialBone Base
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.driveMasterY_from", 2)
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.rotationSpeedX", 1.0)
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_FacialBone_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base FacialBone Fan Directions
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.baseMeshOffsetX", -12.2)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.baseMeshOffsetY", 7.4)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.baseMeshOffsetX", -4.5)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.baseMeshOffsetZ", -11.081)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetFwdZ", -11.081)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_down_jnt.targetOffsetBwdZ", -11.081)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.baseMeshOffsetX", -0.27)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.baseMeshOffsetY", -12.4)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetFwdX", 25.83)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetBwdX", 25.83)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.baseMeshOffsetX", -4.5)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.baseMeshOffsetZ", 11.056)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetFwdZ", 11.056)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_FacialBone_fan_back_jnt.targetOffsetBwdZ", 11.056)

    # CC Base L Calf Base
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.driveMasterZ_from", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.rotationSpeedX", -32.0)
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Calf_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base L Calf Fan Directions
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.baseMeshOffsetX", 7.193)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetFwdX", -8.007)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetBwdX", 7.193)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.baseMeshOffsetZ", -12.562)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetFwdZ", -100.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_down_jnt.targetOffsetBwdZ", -12.562)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.baseMeshOffsetX", -13.073)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetFwdX", 31.427)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.baseMeshOffsetZ", 7.175)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetFwdZ", 100.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Calf_fan_back_jnt.targetOffsetBwdZ", 7.175)

    # CC Base L Foot Base
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.driveMasterY_from", 2)
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.rotationSpeedX", 1.0)
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Foot_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base L Foot Fan Directions
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.baseMeshOffsetX", -4.592)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetFwdX", -4.592)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetBwdX", -4.592)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.baseMeshOffsetZ", -13.603)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetFwdZ", -13.603)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_down_jnt.targetOffsetBwdZ", -13.603)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.baseMeshOffsetX", 17.595)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetFwdX", 17.595)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetBwdX", 17.595)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.baseMeshOffsetZ", 13.313)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetFwdZ", 13.313)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Foot_fan_back_jnt.targetOffsetBwdZ", 13.313)

    # CC Base L Forearm Base
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.rotationSpeedX", -35.3)
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base L Forearm Fan Directions
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.baseMeshOffsetX", -5.089)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetFwdX", -5.089)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetBwdX", 15.311)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.baseMeshOffsetZ", -5.432)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetFwdZ", -5.432)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_down_jnt.targetOffsetBwdZ", -60.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.baseMeshOffsetX", 9.389)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetFwdX", 9.389)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetBwdX", -15.311)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.baseMeshOffsetZ", 12.42)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetFwdZ", 12.42)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetBwdY", -13.2)
    cmds.setAttr("CC_Base_L_Forearm_fan_back_jnt.targetOffsetBwdZ", 78.2)

    # CC Base L Hand Base
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.rotationSpeedX", -20.0)
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Hand_fan_base_jnt.rotationSpeedZ", -20.0)

    # CC Base L Hand Fan Directions
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.baseMeshOffsetX", -1.458)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetFwdX", -11.258)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetBwdX", -24.358)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.baseMeshOffsetY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetFwdY", 4.4)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetBwdY", 6)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.baseMeshOffsetZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetFwdZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_up_jnt.targetOffsetBwdZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.baseMeshOffsetZ", -5.048)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetFwdZ", -71.448)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetBwdZ", -5.048)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetBwdY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetFwdY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.baseMeshOffsetY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetBwdX", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.targetOffsetFwdX", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_down_jnt.baseMeshOffsetX", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.baseMeshOffsetX", 4.02)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetFwdX", 37.12)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetBwdX", 4.02)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.baseMeshOffsetY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetFwdY", 15)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetBwdY", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetFwdZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.baseMeshOffsetZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_front_jnt.targetOffsetBwdZ", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.baseMeshOffsetZ", 5.281)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetFwdZ", 5.281)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Hand_fan_back_jnt.targetOffsetBwdZ", 5.281)

    # CC Base L Thigh Base
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.rotationSpeedX", -30.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_base_jnt.rotationSpeedZ", -30.0)

    # CC Base L Thigh Fan Directions
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.baseMeshOffsetX", -14.524)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetFwdX", -14.524)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetBwdX", -53.524)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.baseMeshOffsetY", 20.2)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.baseMeshOffsetZ", -12.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetFwdZ", -63.073)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_down_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.baseMeshOffsetX", 10.186)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.baseMeshOffsetY", 14.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetFwdX", 38.286)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetBwdX", 38.286)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.baseMeshOffsetZ", 15.887)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetFwdZ", 15.887)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Thigh_fan_back_jnt.targetOffsetBwdZ", 15.887)

    # CC Base L Upperarm Base
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.rotationSpeedX", -30.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_base_jnt.rotationSpeedZ", -30.0)

    # CC Base L Upperarm Fan Directions
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.baseMeshOffsetX", -22.701)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetFwdX", -22.701)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetBwdX", -139.334)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.baseMeshOffsetZ", -11.9)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetFwdZ", -80.585)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_down_jnt.targetOffsetBwdZ", -11.9)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.baseMeshOffsetX", 22.701)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetFwdX", 22.701)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetBwdX", -25.866)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.baseMeshOffsetZ", 15.785)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetFwdZ", 15.785)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_L_Upperarm_fan_back_jnt.targetOffsetBwdZ", 80.0)

    # CC Base NeckTwist01 Base
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.driveMasterY_from", 2)
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.rotationSpeedX", 1.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base NeckTwist01 Fan Directions
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.baseMeshOffsetX", -10.906)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.baseMeshOffsetY", 8.4)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetFwdX", -45.841)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetBwdX", -45.841)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.baseMeshOffsetZ", -11.141)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetFwdZ", -11.141)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_down_jnt.targetOffsetBwdZ", -11.141)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.baseMeshOffsetX", 10.906)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.baseMeshOffsetY", 8.4)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetFwdX", 45.306)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetBwdX", 45.306)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.baseMeshOffsetY", 3.4)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.baseMeshOffsetZ", 14.191)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetFwdZ", 14.191)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist01_fan_back_jnt.targetOffsetBwdZ", 14.191)

    # CC Base NeckTwist02 Base
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.driveMasterY_from", 2)
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.rotationSpeedX", 1.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base NeckTwist02 Fan Directions
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.baseMeshOffsetX", -7.636)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.baseMeshOffsetZ", -8.4)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetFwdX", -10.724)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetBwdX", -10.724)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.baseMeshOffsetZ", -9.91)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetFwdZ", -9.91)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_down_jnt.targetOffsetBwdZ", -9.91)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.baseMeshOffsetX", 7.636)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.baseMeshOffsetY", 2.8)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.baseMeshOffsetZ", -8.4)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetFwdX", 10.636)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetBwdX", 10.636)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.baseMeshOffsetY", -2.3)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.baseMeshOffsetZ", 11.294)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetFwdZ", 11.294)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_NeckTwist02_fan_back_jnt.targetOffsetBwdZ", 11.294)


def R_FanValue():
    
    # CC Base R Calf Base
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.driveMasterZ_from", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.rotationSpeedX", -32.0)
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Calf_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base R Calf Fan Directions
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.baseMeshOffsetX", -7.193)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetFwdX", 8.007)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetBwdX", -7.193)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.baseMeshOffsetZ", -7.184)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetFwdZ", -100.009)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_down_jnt.targetOffsetBwdZ", -7.184)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.baseMeshOffsetX", 13.073)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetFwdX", -31.427)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.baseMeshOffsetZ", 12.548)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetFwdZ", 99.986)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Calf_fan_back_jnt.targetOffsetBwdZ", 12.548)

    # CC Base R Foot Base
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.driveMasterY_from", 2)
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.rotationSpeedX", 1.0)
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Foot_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base R Foot Fan Directions
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.baseMeshOffsetX", -5.499)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetFwdX", -5.499)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetBwdX", -5.499)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.baseMeshOffsetZ", -13.337)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetFwdZ", -13.337)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_down_jnt.targetOffsetBwdZ", -13.337)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.baseMeshOffsetX", 4.596)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetFwdX", 4.596)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetBwdX", 4.596)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.baseMeshOffsetZ", 13.627)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetFwdZ", 13.627)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Foot_fan_back_jnt.targetOffsetBwdZ", 13.627)

    # CC Base R Forearm Base
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.rotationSpeedX", -35.3)
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_base_jnt.rotationSpeedZ", 1.0)

    # CC Base R Forearm Fan Directions
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.baseMeshOffsetX", -9.356)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetFwdX", -9.356)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetBwdX", 15.344)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.baseMeshOffsetZ", -5.444)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetFwdZ", -5.444)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_down_jnt.targetOffsetBwdZ", -53.024)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.baseMeshOffsetX", 5.131)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetFwdX", 5.131)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetBwdX", -15.269)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.baseMeshOffsetZ", 12.409)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetFwdZ", 12.409)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Forearm_fan_back_jnt.targetOffsetBwdZ", 66.977)

    # CC Base R Hand Base
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.rotationSpeedX", -20.0)
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Hand_fan_base_jnt.rotationSpeedZ", -20.0)

    # CC Base R Hand Fan Directions
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.baseMeshOffsetX", -3.959)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetFwdX", -3.959)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetBwdX", -3.959)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.baseMeshOffsetZ", -5.083)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetFwdZ", -5.083)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_down_jnt.targetOffsetBwdZ", -5.083)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.baseMeshOffsetX", 3.417)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetFwdX", 24.417)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetFwdY", -4.4)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetBwdX", 24.417)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetBwdY", -13.3)
    cmds.setAttr("CC_Base_R_Hand_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.baseMeshOffsetZ", 5.294)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetFwdZ", 5.294)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Hand_fan_back_jnt.targetOffsetBwdZ", 5.294)

    # CC Base R Thigh Base
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.driveMasterZ_from", 3)
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.rotationSpeedX", -30.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_base_jnt.rotationSpeedZ", -30.0)

    # CC Base R Thigh Fan Directions
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.baseMeshOffsetX", -10.186)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.baseMeshOffsetY", -14.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetFwdX", -38.286)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetBwdX", -38.286)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.baseMeshOffsetZ", -16.174)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetFwdZ", -16.174)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_down_jnt.targetOffsetBwdZ", -16.174)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.drivenByAxis", 2)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.baseMeshOffsetX", 14.524)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetFwdX", 14.524)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetBwdX", 53.524)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.baseMeshOffsetY", -20.2)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.baseMeshOffsetZ", 12.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetFwdZ", 63.073)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Thigh_fan_back_jnt.targetOffsetBwdZ", 0.0)

    # CC Base R Upperarm Base
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.driveMasterX_from", 1)
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.driveMasterY_from", 0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.driveMasterZ_from", 6)
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.rotationSpeedX", -30.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.rotationSpeedY", 1.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_base_jnt.rotationSpeedZ", 30.0)

    # CC Base R Upperarm Fan Directions
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.drivenByAxis", 5)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.baseMeshOffsetX", -22.701)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetFwdX", -22.701)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetBwdX", 25.866)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_up_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.baseMeshOffsetZ", -11.9)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetFwdZ", -80.585)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_down_jnt.targetOffsetBwdZ", -11.9)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.drivenByAxis", 5)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.baseMeshOffsetX", 22.701)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.baseMeshOffsetZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetFwdX", 22.701)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetFwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetBwdX", 139.334)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_front_jnt.targetOffsetBwdZ", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.drivenByAxis", 0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.driverStart", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.driverEnd", 90.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.baseMeshOffsetX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.baseMeshOffsetY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.baseMeshOffsetZ", 15.785)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetFwdX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetFwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetFwdZ", 15.785)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetBwdX", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetBwdY", 0.0)
    cmds.setAttr("CC_Base_R_Upperarm_fan_back_jnt.targetOffsetBwdZ", 80.0)

    # ========================================
    # END EXPORT
    # ========================================


def fix_and_mirror_cc_fans(target_mesh="CC_Base_Body"):
    mirror_pairs = [
        ("CC_Base_L_Upperarm", "CC_Base_R_Upperarm"),
        ("CC_Base_L_Forearm",  "CC_Base_R_Forearm"),
        ("CC_Base_L_Hand",     "CC_Base_R_Hand"),
        ("CC_Base_L_Thigh",    "CC_Base_R_Thigh"),
        ("CC_Base_L_Calf",     "CC_Base_R_Calf"),
        ("CC_Base_L_Foot",     "CC_Base_R_Foot")
    ]
    
    for l_jnt, r_jnt in mirror_pairs:
        l_offset = f"{l_jnt}_fan_offset_jnt"
        l_base = f"{l_jnt}_fan_base_jnt"
        r_offset = f"{r_jnt}_fan_offset_jnt"
        r_base = f"{r_jnt}_fan_base_jnt"
        
        if not cmds.objExists(l_offset):
            continue
            
        # 1. Clean existing R-side to force fresh, accurate raycasts
        if cmds.objExists(r_offset):
            cmds.delete(r_offset)
            
        # 2. Regenerate R-side Base
        rad = cmds.getAttr(f"{l_offset}.radius") / 2.5 
        offset_rot = (
            cmds.getAttr(f"{l_offset}.rx"),
            cmds.getAttr(f"{l_offset}.ry"),
            cmds.getAttr(f"{l_offset}.rz") * -1.0 # Behavior mirror invert
        )
        create_mesh_projected_fan_joints(r_jnt, target_mesh, radius=rad, offset_rot=offset_rot)
        
        # 3. Mirror Driver Logic (Ignore Mesh Offsets)
        custom_base_attrs = cmds.listAttr(l_base, userDefined=True) or []
        for attr in custom_base_attrs:
            val = cmds.getAttr(f"{l_base}.{attr}")
            if "SpeedZ" in attr: 
                val *= -1.0 # Invert Z-speed for symmetry
            cmds.setAttr(f"{r_base}.{attr}", val)
            
        # 4. Sync Sub-Joint Rules & Swap Z-Conditions
        directions = ["_up", "_down", "_front", "_back"]
        for suffix in directions:
            l_fan = f"{l_jnt}_fan{suffix}_jnt"
            r_fan = f"{r_jnt}_fan{suffix}_jnt"
            
            if cmds.objExists(l_fan) and cmds.objExists(r_fan):
                # Only copy rule configurations, leaving R-side raycasts intact
                for attr in ["drivenByAxis", "driverStart", "driverEnd"]:
                    if cmds.objExists(f"{l_fan}.{attr}"):
                        cmds.setAttr(f"{r_fan}.{attr}", cmds.getAttr(f"{l_fan}.{attr}"))
                    
                # Swap the R-side's FWD and BWD Z-offsets to correct the inverted Condition node logic
                try:
                    r_fwd_z = cmds.getAttr(f"{r_fan}.targetOffsetFwdZ")
                    r_bwd_z = cmds.getAttr(f"{r_fan}.targetOffsetBwdZ")
                    
                    cmds.setAttr(f"{r_fan}.targetOffsetFwdZ", r_bwd_z)
                    cmds.setAttr(f"{r_fan}.targetOffsetBwdZ", r_fwd_z)
                except Exception:
                    pass

    print("\n# Mirrored fans: Preserved R-side raycasts and swapped Z-conditions to prevent flipping.")

# --- RUN SCRIPT ---

def Fan():
    delete_all_fan_joints_in_scene()

    create_mesh_projected_fan_joints("CC_Base_L_Upperarm", "CC_Base_Body", radius=5, offset_rot=(0, 0, 52.311))
    create_mesh_projected_fan_joints("CC_Base_L2_Upperarm", "CC_Base_Body", radius=5, offset_rot=(0, 0, 52.311))
    create_mesh_projected_fan_joints("CC_Base_L_Forearm", "CC_Base_Body", radius=5)
    create_mesh_projected_fan_joints("CC_Base_L_Hand", "CC_Base_Body", radius=5)



    create_mesh_projected_fan_joints("CC_Base_L_Thigh", "CC_Base_Body", radius=5)
    create_mesh_projected_fan_joints("CC_Base_L_Calf", "CC_Base_Body", radius=5)
    create_mesh_projected_fan_joints("CC_Base_L_Foot", "CC_Base_Body", radius=5)



    create_mesh_projected_fan_joints("CC_Base_NeckTwist01", "CC_Base_Body", radius=5)
    create_mesh_projected_fan_joints("CC_Base_NeckTwist02", "CC_Base_Body", radius=5)
    create_mesh_projected_fan_joints("CC_Base_FacialBone", "CC_Base_Body", radius=5)

    L_FanValue()
    fix_and_mirror_cc_fans("CC_Base_Body")
    R_FanValue()


#Fan()


