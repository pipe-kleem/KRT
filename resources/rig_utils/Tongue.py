import maya.cmds as cmds
import maya.api.OpenMaya as om

    
def clusterCreate():
    group_1_str = """
    CC_Base_Tongue.vtx[44:46] CC_Base_Tongue.vtx[72] CC_Base_Tongue.vtx[102:105] CC_Base_Tongue.vtx[111] CC_Base_Tongue.vtx[119] CC_Base_Tongue.vtx[127] CC_Base_Tongue.vtx[142] CC_Base_Tongue.vtx[156] CC_Base_Tongue.vtx[211:213] CC_Base_Tongue.vtx[245:247] CC_Base_Tongue.vtx[253] CC_Base_Tongue.vtx[261] CC_Base_Tongue.vtx[269] CC_Base_Tongue.vtx[284] CC_Base_Tongue.vtx[298] CC_Base_Tongue.vtx[732] CC_Base_Tongue.vtx[737] CC_Base_Tongue.vtx[740] CC_Base_Tongue.vtx[743] CC_Base_Tongue.vtx[746] CC_Base_Tongue.vtx[749] CC_Base_Tongue.vtx[752] CC_Base_Tongue.vtx[756] CC_Base_Tongue.vtx[822] CC_Base_Tongue.vtx[824] CC_Base_Tongue.vtx[865] CC_Base_Tongue.vtx[870] CC_Base_Tongue.vtx[1047] CC_Base_Tongue.vtx[1049] CC_Base_Tongue.vtx[1052] CC_Base_Tongue.vtx[1056] CC_Base_Tongue.vtx[1059] CC_Base_Tongue.vtx[1062] CC_Base_Tongue.vtx[1066] CC_Base_Tongue.vtx[1068] CC_Base_Tongue.vtx[1131] CC_Base_Tongue.vtx[1134] CC_Base_Tongue.vtx[1171:1172] CC_Base_Tongue.vtx[3831:3832] CC_Base_Tongue.vtx[3841:3842] CC_Base_Tongue.vtx[3847:3848] CC_Base_Tongue.vtx[3853:3854] CC_Base_Tongue.vtx[3859:3860] CC_Base_Tongue.vtx[3865:3866] CC_Base_Tongue.vtx[3871:3872] CC_Base_Tongue.vtx[3879:3880] CC_Base_Tongue.vtx[4011:4012] CC_Base_Tongue.vtx[4015:4016] CC_Base_Tongue.vtx[4097:4098] CC_Base_Tongue.vtx[4107:4108] CC_Base_Tongue.vtx[4461:4462] CC_Base_Tongue.vtx[4465:4466] CC_Base_Tongue.vtx[4471:4472] CC_Base_Tongue.vtx[4479:4480] CC_Base_Tongue.vtx[4485:4486] CC_Base_Tongue.vtx[4491:4492] CC_Base_Tongue.vtx[4499:4500] CC_Base_Tongue.vtx[4503:4504] CC_Base_Tongue.vtx[4629:4630] CC_Base_Tongue.vtx[4635:4636] CC_Base_Tongue.vtx[4709:4712]
    """
    
    group_2_str = """
    CC_Base_Tongue.vtx[30] CC_Base_Tongue.vtx[33:35] CC_Base_Tongue.vtx[57] CC_Base_Tongue.vtx[68] CC_Base_Tongue.vtx[76] CC_Base_Tongue.vtx[106] CC_Base_Tongue.vtx[115] CC_Base_Tongue.vtx[123] CC_Base_Tongue.vtx[139] CC_Base_Tongue.vtx[197] CC_Base_Tongue.vtx[200:202] CC_Base_Tongue.vtx[224] CC_Base_Tongue.vtx[235] CC_Base_Tongue.vtx[248] CC_Base_Tongue.vtx[257] CC_Base_Tongue.vtx[265] CC_Base_Tongue.vtx[281] CC_Base_Tongue.vtx[694] CC_Base_Tongue.vtx[700] CC_Base_Tongue.vtx[704] CC_Base_Tongue.vtx[710] CC_Base_Tongue.vtx[714] CC_Base_Tongue.vtx[717] CC_Base_Tongue.vtx[723] CC_Base_Tongue.vtx[725] CC_Base_Tongue.vtx[816:817] CC_Base_Tongue.vtx[1008] CC_Base_Tongue.vtx[1013] CC_Base_Tongue.vtx[1017] CC_Base_Tongue.vtx[1021] CC_Base_Tongue.vtx[1028] CC_Base_Tongue.vtx[1031] CC_Base_Tongue.vtx[1036] CC_Base_Tongue.vtx[1039] CC_Base_Tongue.vtx[1124] CC_Base_Tongue.vtx[1126] CC_Base_Tongue.vtx[1167] CC_Base_Tongue.vtx[1357] CC_Base_Tongue.vtx[1360] CC_Base_Tongue.vtx[1365] CC_Base_Tongue.vtx[1368] CC_Base_Tongue.vtx[1373:1374] CC_Base_Tongue.vtx[1377] CC_Base_Tongue.vtx[1380] CC_Base_Tongue.vtx[1385:1386] CC_Base_Tongue.vtx[1389:1390] CC_Base_Tongue.vtx[1409] CC_Base_Tongue.vtx[1412:1413] CC_Base_Tongue.vtx[1416] CC_Base_Tongue.vtx[1577:1578] CC_Base_Tongue.vtx[1581:1582] CC_Base_Tongue.vtx[1949:1950] CC_Base_Tongue.vtx[1957:1958] CC_Base_Tongue.vtx[1965] CC_Base_Tongue.vtx[1968:1970] CC_Base_Tongue.vtx[1977] CC_Base_Tongue.vtx[1980:1981] CC_Base_Tongue.vtx[1984] CC_Base_Tongue.vtx[2001:2002] CC_Base_Tongue.vtx[2005:2006] CC_Base_Tongue.vtx[2169] CC_Base_Tongue.vtx[2172:2173] CC_Base_Tongue.vtx[2176] CC_Base_Tongue.vtx[2544] CC_Base_Tongue.vtx[2552] CC_Base_Tongue.vtx[2557] CC_Base_Tongue.vtx[2564] CC_Base_Tongue.vtx[2569] CC_Base_Tongue.vtx[2573] CC_Base_Tongue.vtx[2596] CC_Base_Tongue.vtx[2600] CC_Base_Tongue.vtx[2761] CC_Base_Tongue.vtx[2765] CC_Base_Tongue.vtx[3133] CC_Base_Tongue.vtx[3141] CC_Base_Tongue.vtx[3152:3153] CC_Base_Tongue.vtx[3164] CC_Base_Tongue.vtx[3168] CC_Base_Tongue.vtx[3185] CC_Base_Tongue.vtx[3189] CC_Base_Tongue.vtx[3356] CC_Base_Tongue.vtx[3360] CC_Base_Tongue.vtx[3755:3756] CC_Base_Tongue.vtx[3759] CC_Base_Tongue.vtx[3767:3769] CC_Base_Tongue.vtx[3775:3777] CC_Base_Tongue.vtx[3781] CC_Base_Tongue.vtx[3786:3788] CC_Base_Tongue.vtx[3795:3796] CC_Base_Tongue.vtx[3800:3802] CC_Base_Tongue.vtx[3806] CC_Base_Tongue.vtx[3813:3814] CC_Base_Tongue.vtx[3817:3818] CC_Base_Tongue.vtx[3826] CC_Base_Tongue.vtx[3830] CC_Base_Tongue.vtx[3999:4003] CC_Base_Tongue.vtx[4093] CC_Base_Tongue.vtx[4383:4384] CC_Base_Tongue.vtx[4392:4394] CC_Base_Tongue.vtx[4400:4402] CC_Base_Tongue.vtx[4408:4411] CC_Base_Tongue.vtx[4419] CC_Base_Tongue.vtx[4423:4425] CC_Base_Tongue.vtx[4429:4430] CC_Base_Tongue.vtx[4439:4440] CC_Base_Tongue.vtx[4445:4447] CC_Base_Tongue.vtx[4451] CC_Base_Tongue.vtx[4615:4616] CC_Base_Tongue.vtx[4619:4620] CC_Base_Tongue.vtx[4624] CC_Base_Tongue.vtx[4702]
    """
    
    group_3_str = """
    CC_Base_Tongue.vtx[19] CC_Base_Tongue.vtx[21] CC_Base_Tongue.vtx[186] CC_Base_Tongue.vtx[188] CC_Base_Tongue.vtx[340] CC_Base_Tongue.vtx[488] CC_Base_Tongue.vtx[681] CC_Base_Tongue.vtx[685:686] CC_Base_Tongue.vtx[995:996] CC_Base_Tongue.vtx[999:1000] CC_Base_Tongue.vtx[1326] CC_Base_Tongue.vtx[1333:1334] CC_Base_Tongue.vtx[1341] CC_Base_Tongue.vtx[1920] CC_Base_Tongue.vtx[1925:1928] CC_Base_Tongue.vtx[1933:1934] CC_Base_Tongue.vtx[2517:2518] CC_Base_Tongue.vtx[2520] CC_Base_Tongue.vtx[2528] CC_Base_Tongue.vtx[3103] CC_Base_Tongue.vtx[3109:3112] CC_Base_Tongue.vtx[3117] CC_Base_Tongue.vtx[3728:3729] CC_Base_Tongue.vtx[3737:3739] CC_Base_Tongue.vtx[3743] CC_Base_Tongue.vtx[4357:4359] CC_Base_Tongue.vtx[4365:4368]
    """
    
    # Each element of this list is ONE vertex group = ONE cluster.
    vertex_groups = [
        group_1_str.split(),
        group_2_str.split(),
        group_3_str.split(),
    ]
    
    # ---------------------------------------------------------------------------
    # 2. Create one cluster per group.
    # ---------------------------------------------------------------------------
    
    def create_clusters_from_groups(groups, base_name="tongue_cluster"):
        """
        Creates exactly one cluster (clusterNode + clusterHandle) for each
        vertex list found in `groups`.
    
        Args:
            groups (list[list[str]]): list of vertex-component lists.
            base_name (str): naming prefix for the resulting clusters.
    
        Returns:
            list[tuple(str, str)]: list of (clusterNode, clusterHandle) pairs.
        """
        created = []
    
        for index, vtx_list in enumerate(groups, start=1):
            if not vtx_list:
                cmds.warning("Group {0} is empty, skipping.".format(index))
                continue
    
            # Make sure the components actually exist before selecting them.
            missing = [v for v in vtx_list if not cmds.objExists(v)]
            if missing:
                cmds.warning(
                    "Group {0}: {1} component(s) not found, e.g. {2}".format(
                        index, len(missing), missing[0]
                    )
                )
                vtx_list = [v for v in vtx_list if v not in missing]
                if not vtx_list:
                    continue
    
            cmds.select(vtx_list, replace=True)
    
            cluster_name = "{0}_{1}".format(base_name, index)
            cluster_node, cluster_handle = cmds.cluster(name=cluster_name)
    
            # cmds.cluster names the handle automatically based on the
            # 'name' flag but with a "Handle" suffix pattern in some Maya
            # versions, so force-rename it to something predictable.
            cluster_handle = cmds.rename(cluster_handle, cluster_name + "Handle")
    
            created.append((cluster_node, cluster_handle))
            print("Created cluster '{0}' -> handle '{1}' ({2} components)".format(
                cluster_node, cluster_handle, len(vtx_list)
            ))
    
        cmds.select(clear=True)
        return created
    
    
    if __name__ == "__main__":
        result = create_clusters_from_groups(vertex_groups)
        print("Done. Created {0} cluster(s): {1}".format(
            len(result), [c[0] for c in result]
        ))






def fix_skin_bind_matrix(jnt):
    """
    Finds any skinClusters attached to the joint and updates 
    the bindPreMatrix to match the joint's new worldInverseMatrix.
    This prevents the bound mesh from deforming.
    """
    connections = cmds.listConnections(
        f"{jnt}.worldMatrix[0]", 
        type="skinCluster", 
        connections=True, 
        plugs=True
    ) or []

    for i in range(0, len(connections), 2):
        dst_plug = connections[i + 1]  # e.g., 'skinCluster1.matrix[0]'

        if ".matrix[" in dst_plug:
            skin_node, attr_name = dst_plug.split(".")
            index = attr_name.split("[")[1].split("]")[0]

            # Query new inverse matrix for the moved joint
            world_inv_mat = cmds.getAttr(f"{jnt}.worldInverseMatrix[0]")

            # Sync skinCluster's bind pose matrix to prevent skin deformation
            cmds.setAttr(f"{skin_node}.bindPreMatrix[{index}]", world_inv_mat, type="matrix")

def zero_joint_orient_safe(jnt):
    """Zeroes out the joint orient on a tip joint while preserving child positions and skin."""
    children = cmds.listRelatives(jnt, children=True, fullPath=True, type=['transform', 'joint']) or []
    child_world_matrices = {c: cmds.xform(c, query=True, worldSpace=True, matrix=True) for c in children}
    
    cmds.joint(jnt, edit=True, orientJoint='none', zeroScaleOrient=True)
    cmds.setAttr(f"{jnt}.rotate", 0, 0, 0)
    
    # Restore children
    for child, original_matrix in child_world_matrices.items():
        cmds.xform(child, worldSpace=True, matrix=original_matrix)
        
    fix_skin_bind_matrix(jnt)

def align_lra_to_target(jnt, target_node):
    if getattr(jnt, "name", jnt) == getattr(target_node, "name", target_node):
        return

    target_uuid = cmds.ls(target_node, uuid=True)[0]
    
    # 1. Store original world matrices of direct children (including target)
    children = cmds.listRelatives(jnt, children=True, fullPath=True, type=['transform', 'joint']) or []
    child_world_matrices = {}
    for child in children:
        child_world_matrices[child] = cmds.xform(child, query=True, worldSpace=True, matrix=True)
        
    actual_target = cmds.ls(target_uuid)[0]
    
    # 2. Get current world matrix axes of the joint
    matrix = om.MMatrix(cmds.xform(jnt, query=True, matrix=True, worldSpace=True))
    local_axes = {
        'x': om.MVector(matrix[0], matrix[1], matrix[2]).normal(),
        'y': om.MVector(matrix[4], matrix[5], matrix[6]).normal(),
        'z': om.MVector(matrix[8], matrix[9], matrix[10]).normal()
    }
    
    # Calculate precise absolute vector to the actual chosen target
    pos_jnt = om.MVector(cmds.xform(jnt, query=True, rotatePivot=True, worldSpace=True))
    pos_target = om.MVector(cmds.xform(actual_target, query=True, rotatePivot=True, worldSpace=True))
    aim_vec = (pos_target - pos_jnt).normal()
    
    # Determine closest primary axis
    dots = { 'x': local_axes['x'] * aim_vec, 'y': local_axes['y'] * aim_vec, 'z': local_axes['z'] * aim_vec }
    abs_dots = {k: abs(v) for k, v in dots.items()}
    primary_axis = max(abs_dots, key=abs_dots.get)
    
    # Setup Vectors
    aim_dir = (1, 0, 0) if primary_axis == 'x' else ((0, 1, 0) if primary_axis == 'y' else (0, 0, 1))
    if dots[primary_axis] < 0:
        aim_dir = tuple(-v for v in aim_dir)
        
    up_axis = 'y' if primary_axis == 'x' else ('z' if primary_axis == 'y' else 'x')
    up_dir = (1, 0, 0) if up_axis == 'x' else ((0, 1, 0) if up_axis == 'y' else (0, 0, 1))
    world_up_vec = local_axes[up_axis]
    
    # 3. Create a dummy transform to calculate the perfect local orientation safely
    dummy = cmds.group(empty=True)
    cmds.xform(dummy, worldSpace=True, translation=[pos_jnt.x, pos_jnt.y, pos_jnt.z])
    parent = cmds.listRelatives(jnt, parent=True, fullPath=True)
    if parent:
        cmds.parent(dummy, parent[0])
        
    # Aim dummy at target
    cmds.aimConstraint(
        actual_target, dummy,
        aimVector=aim_dir,
        upVector=up_dir,
        worldUpType="vector",
        worldUpVector=(world_up_vec.x, world_up_vec.y, world_up_vec.z)
    )
    
    # Read calculated orientation
    new_joint_orient = cmds.getAttr(f"{dummy}.rotate")[0]
    cmds.delete(dummy)
    
    # 4. Safely apply orientation values directly to the joint
    cmds.setAttr(f"{jnt}.jointOrient", *new_joint_orient)
    cmds.setAttr(f"{jnt}.rotate", 0, 0, 0)
    
    # 5. Restore exact original positions of children (prevents them from shifting)
    for child, original_matrix in child_world_matrices.items():
        cmds.xform(child, worldSpace=True, matrix=original_matrix)
        
    # 6. Update Skin Cluster bindPreMatrix so the mesh stays static
    fix_skin_bind_matrix(jnt)


def run_lra_fix():
    # orderedSelection=True forces Maya to respect exact 1-2 click sequence
    sel = cmds.ls(orderedSelection=True, long=True, type='joint')
    
    if not sel:
        cmds.warning("Select at least one joint to fix.")
        return

    # MANUAL MODE: If exactly 2 joints selected, aim first at second
    if len(sel) == 2:
        parent_jnt = sel[0]
        target_child = sel[1]
        
        descendants = cmds.listRelatives(parent_jnt, allDescendents=True, fullPath=True) or []
        if target_child in descendants:
            align_lra_to_target(parent_jnt, target_child)
            cmds.select(parent_jnt, replace=True)
            print(f"Successfully aimed LRA of '{parent_jnt.split('|')[-1]}' to '{target_child.split('|')[-1]}'.")
            return

    # AUTO MODE: Aim each selected joint to its first child
    for jnt in sel:
        children = cmds.listRelatives(jnt, children=True, fullPath=True, type=['transform', 'joint']) or []
        if children:
            align_lra_to_target(jnt, children[0])
        else:
            # Tip joint
            zero_joint_orient_safe(jnt)
            
    cmds.select(sel, replace=True)
    print("Auto LRA fix complete.")



def set_attr_preserve_mesh(joint, attribute, value, preserve_children=True):
    """Sets an attribute on a skinned joint while keeping the bound skin mesh static,

    with an optional toggle to preserve child joint positions.

    :param joint: Name of the target joint node.
    :param attribute: Attribute name (e.g., 'translateX', 'ry', 'rotate').
    :param value: Value to set (float/int, or tuple/list for 3D attributes).
    :param preserve_children: If True, child joints stay fixed in world space.
                              If False, child joints move with parent and update
                              their skin cluster bind matrices accordingly.
    """
    if not cmds.objExists(joint):
        cmds.warning(f"Joint '{joint}' does not exist.")
        return

    full_attr = f"{joint}.{attribute}"
    if not cmds.objExists(full_attr):
        cmds.warning(f"Attribute '{full_attr}' does not exist.")
        return

    # 1. Gather joints whose bindPreMatrix might need updating
    # Using `ad=True` (allDescendants) for maximum Maya compatibility
    if preserve_children:
        affected_joints = [joint]
    else:
        descendants = (
            cmds.listRelatives(joint, ad=True, type="joint") or []
        )
        affected_joints = [joint] + descendants

    # 2. Store original world matrices of direct child transform/joint nodes (if enabled)
    child_world_matrices = {}
    if preserve_children:
        children = (
            cmds.listRelatives(joint, children=True, type="transform") or []
        )
        for child in children:
            child_world_matrices[child] = cmds.xform(
                child, query=True, worldSpace=True, matrix=True
            )

    # 3. Execute the setAttr command
    if isinstance(value, (tuple, list)):
        cmds.setAttr(full_attr, *value)
    else:
        cmds.setAttr(full_attr, value)

    # 4. Restore direct child world matrices (if enabled)
    if preserve_children:
        for child, original_matrix in child_world_matrices.items():
            cmds.xform(child, worldSpace=True, matrix=original_matrix)

    # 5. Update skinCluster bindPreMatrix for ALL moved joints
    for jnt in affected_joints:
        connections = (
            cmds.listConnections(
                f"{jnt}.worldMatrix[0]",
                type="skinCluster",
                connections=True,
                plugs=True,
            )
            or []
        )

        for i in range(0, len(connections), 2):
            dst_plug = connections[i + 1]  # e.g., 'skinCluster1.matrix[0]'

            if ".matrix[" in dst_plug:
                skin_node, attr_name = dst_plug.split(".")
                index = attr_name.split("[")[1].split("]")[0]

                # Query new inverse matrix for the moved joint
                world_inv_mat = cmds.getAttr(f"{jnt}.worldInverseMatrix[0]")

                # Sync skinCluster's bind pose matrix to prevent skin deformation
                cmds.setAttr(
                    f"{skin_node}.bindPreMatrix[{index}]",
                    world_inv_mat,
                    type="matrix",
                )


clusterCreate()

cmds.duplicate("tongue_cluster_1Handle", "tongue_cluster_2Handle","tongue_cluster_3Handle" )
cmds.delete("tongue_cluster_1Handle", "tongue_cluster_2Handle","tongue_cluster_3Handle" )


cmds.setAttr("tongue_cluster_1Handle1.rotateX", 180)
cmds.setAttr("tongue_cluster_1Handle1.rotateY", -90)

cmds.setAttr("tongue_cluster_2Handle1.rotateX", 180)
cmds.setAttr("tongue_cluster_2Handle1.rotateY", -90)

cmds.setAttr("tongue_cluster_3Handle1.rotateX", 180)
cmds.setAttr("tongue_cluster_3Handle1.rotateY", -90)

Con01 = cmds.parentConstraint("tongue_cluster_1Handle1", "CC_Base_Tongue01", mo= False)
cmds.delete(Con01[0])

Con02 = cmds.parentConstraint("tongue_cluster_2Handle1", "CC_Base_Tongue02", mo= False)
cmds.delete(Con02[0])

Con03 = cmds.parentConstraint("tongue_cluster_3Handle1", "CC_Base_Tongue03", mo= False)
cmds.delete(Con03[0])


cmds.select("CC_Base_Tongue01", "CC_Base_Tongue02","CC_Base_Tongue03" )
run_lra_fix()

cmds.select(cl =True)

cmds.delete("tongue_cluster_1Handle1", "tongue_cluster_2Handle1", "tongue_cluster_3Handle1")

set_attr_preserve_mesh('CC_Base_Tongue01', "tz", 0, preserve_children=False)


set_attr_preserve_mesh('CC_Base_Tongue01', "jointOrientX", 0, preserve_children=False) 
set_attr_preserve_mesh('CC_Base_Tongue01', "jointOrientY", 0, preserve_children=False)
set_attr_preserve_mesh('CC_Base_Tongue02', "jointOrientX", 0, preserve_children=False)
set_attr_preserve_mesh('CC_Base_Tongue02', "jointOrientY", 0, preserve_children=False)
set_attr_preserve_mesh('CC_Base_Tongue03', "jointOrientX", 0, preserve_children=False)
set_attr_preserve_mesh('CC_Base_Tongue03', "jointOrientY", 0, preserve_children=False)





