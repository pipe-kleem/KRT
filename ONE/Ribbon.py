import maya.cmds as cmds

def create_pro_ribbon(side="L", part="upperArm", start_snap=None, end_snap=None):
    
    # Generate the prefix for naming conventions
    prefix = f"{side}_{part}"
    
    # Auto-color controls based on Side (L = Blue, R = Red, C = Yellow)
    if side.upper() == "L":
        ctrl_color = (0.2, 0.6, 1.0)
    elif side.upper() == "R":
        ctrl_color = (1.0, 0.2, 0.2)
    else:
        ctrl_color = (1.0, 1.0, 0.2)

    # --- 1. Create NURBS Surface ---
    surface_width = 20.0
    length_ratio = 0.1
    patches_u = 5  
    
    plane_nodes = cmds.nurbsPlane(
        width=surface_width, lengthRatio=length_ratio, patchesU=patches_u, 
        patchesV=1, axis=(0, 1, 0), degree=3, constructionHistory=False, name=f"{prefix}_ribbon_surface"
    )
    
    ribbon_transform = plane_nodes[0]
    ribbon_shape = cmds.listRelatives(ribbon_transform, shapes=True)[0]
    
    rig_grp = cmds.group(empty=True, name=f"{prefix}_rig_grp")
    cmds.parent(ribbon_transform, rig_grp)
    follicle_grp = cmds.group(empty=True, name=f"{prefix}_follicles_grp", parent=rig_grp)
    
    # --- 2 & 3. Create 5 Follicles and Bind Joints ---
    for i in range(patches_u):
        u_val = (i + 0.5) / float(patches_u)
        
        follicle_shape = cmds.createNode('follicle', name=f"{prefix}_follicleShape_{i+1:02d}")
        follicle_transform = cmds.listRelatives(follicle_shape, parent=True)[0]
        follicle_transform = cmds.rename(follicle_transform, f"{prefix}_follicle_{i+1:02d}")
        
        cmds.connectAttr(f"{ribbon_shape}.local", f"{follicle_shape}.inputSurface")
        cmds.connectAttr(f"{ribbon_shape}.worldMatrix[0]", f"{follicle_shape}.inputWorldMatrix")
        cmds.connectAttr(f"{follicle_shape}.outTranslate", f"{follicle_transform}.translate")
        cmds.connectAttr(f"{follicle_shape}.outRotate", f"{follicle_transform}.rotate")
        
        cmds.setAttr(f"{follicle_shape}.parameterU", u_val)
        cmds.setAttr(f"{follicle_shape}.parameterV", 0.5)
        cmds.setAttr(f"{follicle_shape}.visibility", 0)
        
        cmds.parent(follicle_transform, follicle_grp)
        
        cmds.select(clear=True) 
        bind_jnt = cmds.joint(radius=5, name=f"{prefix}_bind_jnt_{i+1:02d}")
        cmds.parent(bind_jnt, follicle_transform, relative=True)

    # --- 4. Create 3 Custom Controllers ---
    ctrl_main_grp = cmds.group(empty=True, name=f"{prefix}_controls_grp", parent=rig_grp)
    
    num_ctrl_joints = 3
    start_x = -surface_width / 2.0 
    step_x = surface_width / (num_ctrl_joints - 1) 
    
    ctrl_joints = []
    
    for j in range(num_ctrl_joints):
        pos_x = start_x + (j * step_x)
        ctrl_name = f"{prefix}_ctrl_{j+1:02d}"
        
        ctrl_curve = cmds.circle(normal=(1, 0, 0), radius=1.75, name=ctrl_name, constructionHistory=False)[0]
        cmds.setAttr(f"{ctrl_curve}.overrideEnabled", 1)
        cmds.setAttr(f"{ctrl_curve}.overrideRGBColors", 1)
        cmds.setAttr(f"{ctrl_curve}.overrideColorRGB", ctrl_color[0], ctrl_color[1], ctrl_color[2]) 
        
        # Cycle-Free Hierarchy
        ctrl_offset = cmds.group(empty=True, name=f"{ctrl_name}_offset_grp")
        ctrl_auto_trans = cmds.group(empty=True, name=f"{ctrl_name}_auto_trans_grp", parent=ctrl_offset)
        ctrl_aim_target = cmds.group(empty=True, name=f"{ctrl_name}_aim_target", parent=ctrl_auto_trans)
        
        # Dual proxies ONLY for the middle control (index 1 is ctrl_02)
        if j == 1:
            cmds.group(empty=True, name=f"{ctrl_name}_aim_left_proxy", parent=ctrl_auto_trans)
            cmds.group(empty=True, name=f"{ctrl_name}_aim_right_proxy", parent=ctrl_auto_trans)

        ctrl_aim_grp = cmds.group(empty=True, name=f"{ctrl_name}_aim_grp", parent=ctrl_auto_trans)
        ctrl_auto_rot = cmds.group(empty=True, name=f"{ctrl_name}_auto_rot_grp", parent=ctrl_aim_grp)
        
        cmds.parent(ctrl_curve, ctrl_auto_rot)
        
        cmds.connectAttr(f"{ctrl_curve}.translate", f"{ctrl_aim_target}.translate")
        
        cmds.xform(ctrl_offset, translation=[pos_x, 0, 0], worldSpace=True)
        cmds.parent(ctrl_offset, ctrl_main_grp)
        
        cmds.select(clear=True)
        ctrl_jnt = cmds.joint(radius=2, name=f"{ctrl_name}_jnt", position=[pos_x, 0, 0])
        cmds.parent(ctrl_jnt, ctrl_curve)
        
        ctrl_joints.append(ctrl_jnt)

    # --- 5. Bind the 3 control joints to the surface with EXACT Skin Weights ---
    skin_cluster = cmds.skinCluster(
        ctrl_joints, ribbon_transform, toSelectedBones=True, bindMethod=0,           
        normalizeWeights=1, maximumInfluences=3, dropoffRate=4.0, name=f"{prefix}_skinCluster"
    )[0]

    exact_weights = [
        [0.999, 0.001, 0.0], [1.000, 0.000, 0.0], [1.000, 0.000, 0.0], [0.999, 0.001, 0.0],
        [0.998, 0.002, 0.0], [0.999, 0.001, 0.0], [0.999, 0.001, 0.0], [0.998, 0.002, 0.0],
        [0.374, 0.614, 0.012], [0.382, 0.606, 0.012], [0.382, 0.606, 0.012], [0.374, 0.614, 0.012],
        [0.030, 0.969, 0.001], [0.029, 0.971, 0.000], [0.029, 0.971, 0.000], [0.030, 0.969, 0.001],
        [0.001, 0.993, 0.006], [0.001, 0.995, 0.004], [0.001, 0.995, 0.004], [0.001, 0.993, 0.006],
        [0.000, 0.700, 0.300], [0.000, 0.691, 0.309], [0.000, 0.691, 0.309], [0.000, 0.700, 0.300],
        [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]
    ]

    cvs = cmds.ls(f"{ribbon_transform}.cv[*][*]", flatten=True)
    for idx, cv in enumerate(cvs):
        w = exact_weights[idx]
        cmds.skinPercent(skin_cluster, cv, transformValue=[
            (ctrl_joints[0], w[0]), (ctrl_joints[1], w[1]), (ctrl_joints[2], w[2])
        ])

    # --- 6. AIM LOGIC (Dual Proxy Center Tangent) ---
    cmds.aimConstraint(f"{prefix}_ctrl_01_aim_target", f"{prefix}_ctrl_02_aim_left_proxy", 
                       aimVector=(-1,0,0), upVector=(0,1,0), worldUpType="scene", maintainOffset=False, skip=["x"])
    
    cmds.aimConstraint(f"{prefix}_ctrl_03_aim_target", f"{prefix}_ctrl_02_aim_right_proxy", 
                       aimVector=(1,0,0), upVector=(0,1,0), worldUpType="scene", maintainOffset=False, skip=["x"])
    
    cmds.orientConstraint(f"{prefix}_ctrl_02_aim_left_proxy", f"{prefix}_ctrl_02_aim_right_proxy", f"{prefix}_ctrl_02_aim_grp", 
                          maintainOffset=False, skip=["x"])

    # --- 7. TRANSLATION AUTOMATION (01 and 03 push 02) ---
    for i in [1, 3]:
        mult_node = cmds.createNode("multiplyDivide", name=f"{prefix}_mult_trans_ctrl{i:02d}")
        cmds.connectAttr(f"{prefix}_ctrl_{i:02d}.translate", f"{mult_node}.input1")
        cmds.setAttr(f"{mult_node}.input2", 0.5, 0.5, 0.5)

    plus_trans_02 = cmds.createNode("plusMinusAverage", name=f"{prefix}_plus_trans_ctrl02")
    cmds.connectAttr(f"{prefix}_mult_trans_ctrl01.output", f"{plus_trans_02}.input3D[0]")
    cmds.connectAttr(f"{prefix}_mult_trans_ctrl03.output", f"{plus_trans_02}.input3D[1]")
    cmds.connectAttr(f"{plus_trans_02}.output3D", f"{prefix}_ctrl_02_auto_trans_grp.translate")

    # --- 8. ROTATION AUTOMATION (X-Axis Twist) ---
    for i in [1, 3]:
        mult_rot = cmds.createNode("multiplyDivide", name=f"{prefix}_mult_rot_ctrl{i:02d}")
        cmds.connectAttr(f"{prefix}_ctrl_{i:02d}.rotateX", f"{mult_rot}.input1X")
        cmds.setAttr(f"{mult_rot}.input2X", 0.5) 

    plus_rot_02 = cmds.createNode("plusMinusAverage", name=f"{prefix}_plus_rot_ctrl02")
    cmds.connectAttr(f"{prefix}_mult_rot_ctrl01.outputX", f"{plus_rot_02}.input1D[0]")
    cmds.connectAttr(f"{prefix}_mult_rot_ctrl03.outputX", f"{plus_rot_02}.input1D[1]")
    cmds.connectAttr(f"{plus_rot_02}.output1D", f"{prefix}_ctrl_02_auto_rot_grp.rotateX")

    # --- 9. SNAPPING LOGIC ---
    if start_snap and cmds.objExists(start_snap):
        cmds.matchTransform(f"{prefix}_ctrl_01_offset_grp", start_snap, pos=True, rot=True)
        
    if end_snap and cmds.objExists(end_snap):
        cmds.matchTransform(f"{prefix}_ctrl_03_offset_grp", end_snap, pos=True, rot=True)
        
    # If both are provided, mathematically center the middle control
    if start_snap and end_snap and cmds.objExists(start_snap) and cmds.objExists(end_snap):
        pt_cns = cmds.pointConstraint(start_snap, end_snap, f"{prefix}_ctrl_02_offset_grp", maintainOffset=False)
        or_cns = cmds.orientConstraint(start_snap, end_snap, f"{prefix}_ctrl_02_offset_grp", maintainOffset=False)
        cmds.delete(pt_cns, or_cns) # Delete the constraints so it's free to animate

    print(f"[{prefix}] Ribbon Rig successfully generated and snapped!")

# ---------------------------------------------------------
# EXAMPLES OF HOW TO RUN THE SCRIPT
# ---------------------------------------------------------

# Example 1: Left Upper Arm (Snaps to existing joints named 'L_shoulder_jnt' and 'L_elbow_jnt')
create_pro_ribbon(side="L", part="upperArm", start_snap="L_shoulder_jnt", end_snap="L_elbow_jnt")
create_pro_ribbon(side="R", part="upperArm", start_snap="R_shoulder_jnt", end_snap="L_elbow_jnt")

# Example 2: Right Lower Arm (Snaps to 'R_elbow_jnt' and 'R_wrist_jnt')
create_pro_ribbon(side="L", part="lowerArm", start_snap="L_elbow_jnt", end_snap="R_wrist_jnt")
create_pro_ribbon(side="R", part="lowerArm", start_snap="R_elbow_jnt", end_snap="R_wrist_jnt")


