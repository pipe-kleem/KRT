import maya.cmds as cmds

def create_pro_ribbon(side="L", part="upperArm", start_snap=None, end_snap=None, 
                      surface_width=5.0, rig_scale=1.0, global_size=1.5, main_size=1.0, tweak_size=0.75):
    
    # Generate the prefix for naming conventions
    prefix = f"{side}_{part}"
    
    # Auto-color controls based on Side (L = Blue, R = Red, C = Yellow)
    if side.upper() == "L":
        ctrl_color = (0.2, 0.6, 1.0)
    elif side.upper() == "R":
        ctrl_color = (1.0, 0.2, 0.2)
    else:
        ctrl_color = (1.0, 1.0, 0.2)

    # --- 0. APPLY MASTER RIG SCALE ---
    # Multiply all base sizes by the default scale so the rig is physically built to size,
    # keeping the global control perfectly clean at scale [1, 1, 1]
    surface_width *= rig_scale
    global_size *= rig_scale
    main_size *= rig_scale
    tweak_size *= rig_scale

    # --- 1. Create NURBS Surface ---
    length_ratio = 0.1
    patches_u = 5  
    
    plane_nodes = cmds.nurbsPlane(
        width=surface_width, lengthRatio=length_ratio, patchesU=patches_u, 
        patchesV=1, axis=(0, 1, 0), degree=3, constructionHistory=False, name=f"{prefix}_ribbon_surface"
    )
    
    ribbon_transform = plane_nodes[0]
    ribbon_shape = cmds.listRelatives(ribbon_transform, shapes=True)[0]
    
    # LOCK AND TEMPLATE THE RIBBON SURFACE
    cmds.setAttr(f"{ribbon_transform}.visibility", 1) # Keep visible
    cmds.setAttr(f"{ribbon_transform}.overrideEnabled", 1) 
    cmds.setAttr(f"{ribbon_transform}.overrideDisplayType", 1) # 1 = Template, 2 = Reference
    
    for attr in ['tx','ty','tz','rx','ry','rz','sx','sy','sz']:
        cmds.setAttr(f"{ribbon_transform}.{attr}", lock=True, keyable=False)
    
    rig_grp = cmds.group(empty=True, name=f"{prefix}_rig_grp")
    
    # --- 2. GLOBAL CONTROL SETUP ---
    global_offset = cmds.group(empty=True, name=f"{prefix}_ribbon_global_ctl_offset", parent=rig_grp)
    
    # Diamond shape for master control
    global_ctl = cmds.circle(name=f"{prefix}_ribbon_global_ctl", normal=(1, 0, 0), radius=global_size, degree=1, sections=4, constructionHistory=False)[0]
    cmds.parent(global_ctl, global_offset)
    cmds.setAttr(f"{global_ctl}.overrideEnabled", 1)
    cmds.setAttr(f"{global_ctl}.overrideRGBColors", 1)
    cmds.setAttr(f"{global_ctl}.overrideColorRGB", 1.0, 1.0, 0.0) # Yellow for Master Control
    
    # Apply user-defined default rig scale
    if rig_scale != 1.0:
        cmds.setAttr(f"{global_ctl}.scaleX", rig_scale)
        cmds.setAttr(f"{global_ctl}.scaleY", rig_scale)
        cmds.setAttr(f"{global_ctl}.scaleZ", rig_scale)
    
    # Setup Group (Divorced from hierarchy scale to prevent double transforms)
    setup_grp = cmds.group(empty=True, name=f"{prefix}_setup_grp", parent=rig_grp)
    cmds.setAttr(f"{setup_grp}.inheritsTransform", 0) 
    
    cmds.parent(ribbon_transform, setup_grp)
    follicle_grp = cmds.group(empty=True, name=f"{prefix}_follicles_grp", parent=setup_grp)
    
    # --- 3. Create 5 Follicles, Tweak Controls, and Bind Joints ---
    bind_joints = []
    for i in range(patches_u):
        u_val = (i + 0.5) / float(patches_u)
        
        # Follicle Setup
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
        
        # TWEAK CONTROL SETUP (Square shape, rotated on Z)
        tweak_name = f"{prefix}_ribbon_tweak_{i+1:02d}"
        tweak_ctl = cmds.circle(name=f"{tweak_name}_ctl", normal=(0, 1, 0), radius=tweak_size, degree=1, sections=4, constructionHistory=False)[0]
        
        # Rotate shape on Z and freeze transforms so the channel box stays perfectly clean at 0
        cmds.setAttr(f"{tweak_ctl}.rotateZ", 90)
        cmds.makeIdentity(tweak_ctl, apply=True, t=1, r=1, s=1, n=0)
        
        cmds.setAttr(f"{tweak_ctl}.overrideEnabled", 1)
        cmds.setAttr(f"{tweak_ctl}.overrideRGBColors", 1)
        cmds.setAttr(f"{tweak_ctl}.overrideColorRGB", ctrl_color[0], ctrl_color[1], ctrl_color[2])
        
        tweak_offset = cmds.group(empty=True, name=f"{tweak_name}_ctl_offset_grp")
        cmds.parent(tweak_ctl, tweak_offset)
        cmds.parent(tweak_offset, follicle_transform, relative=True)
        
        # Bind Joint Setup (Parented under Tweak Control)
        cmds.select(clear=True) 
        bind_jnt = cmds.joint(radius=tweak_size*0.8, name=f"{prefix}_bind_jnt_{i+1:02d}")
        cmds.parent(bind_jnt, tweak_ctl, relative=True)
        bind_joints.append(bind_jnt)
        
        # Prevent joints from scaling weirdly
        cmds.setAttr(f"{bind_jnt}.segmentScaleCompensate", 0)
        
        # HIDE BIND JOINTS
        cmds.setAttr(f"{bind_jnt}.drawStyle", 2) # None
        cmds.setAttr(f"{bind_jnt}.visibility", 0) 
        
        # Connect Global Control scale to the tweak offset
        cmds.connectAttr(f"{global_ctl}.scale", f"{tweak_offset}.scale")

    # --- 4. Create 3 Custom Controllers ---
    ctl_main_grp = cmds.group(empty=True, name=f"{prefix}_ribbon_ctls_grp", parent=global_ctl)
    
    num_ctrl_joints = 3
    start_x = -surface_width / 2.0 
    step_x = surface_width / (num_ctrl_joints - 1) 
    
    ctrl_joints = []
    
    for j in range(num_ctrl_joints):
        pos_x = start_x + (j * step_x)
        ctl_name = f"{prefix}_ribbon_{j+1:02d}_ctl"
        
        ctl_curve = cmds.circle(normal=(1, 0, 0), radius=main_size, name=ctl_name, constructionHistory=False)[0]
        cmds.setAttr(f"{ctl_curve}.overrideEnabled", 1)
        cmds.setAttr(f"{ctl_curve}.overrideRGBColors", 1)
        cmds.setAttr(f"{ctl_curve}.overrideColorRGB", ctrl_color[0], ctrl_color[1], ctrl_color[2]) 
        
        # Cycle-Free Hierarchy
        ctl_offset = cmds.group(empty=True, name=f"{ctl_name}_offset_grp")
        ctl_auto_trans = cmds.group(empty=True, name=f"{ctl_name}_auto_trans_grp", parent=ctl_offset)
        ctl_aim_target = cmds.group(empty=True, name=f"{ctl_name}_aim_target", parent=ctl_auto_trans)
        
        # Dual proxies ONLY for the middle control
        if j == 1:
            cmds.group(empty=True, name=f"{ctl_name}_aim_left_proxy", parent=ctl_auto_trans)
            cmds.group(empty=True, name=f"{ctl_name}_aim_right_proxy", parent=ctl_auto_trans)

        ctl_aim_grp = cmds.group(empty=True, name=f"{ctl_name}_aim_grp", parent=ctl_auto_trans)
        ctl_auto_rot = cmds.group(empty=True, name=f"{ctl_name}_auto_rot_grp", parent=ctl_aim_grp)
        
        cmds.parent(ctl_curve, ctl_auto_rot)
        cmds.connectAttr(f"{ctl_curve}.translate", f"{ctl_aim_target}.translate")
        
        cmds.xform(ctl_offset, translation=[pos_x, 0, 0], worldSpace=True)
        cmds.parent(ctl_offset, ctl_main_grp)
        
        cmds.select(clear=True)
        # Joints retain _jnt, so no conflict with ctl
        ctl_jnt = cmds.joint(radius=main_size*0.5, name=f"{prefix}_ribbon_{j+1:02d}_jnt", position=[pos_x, 0, 0])
        cmds.parent(ctl_jnt, ctl_curve)
        
        cmds.setAttr(f"{ctl_jnt}.segmentScaleCompensate", 0)
        ctrl_joints.append(ctl_jnt)

    # --- 5. Bind the 3 control joints to the surface with EXACT Skin Weights ---
    skin_cluster = cmds.skinCluster(
        ctrl_joints, ribbon_transform, toSelectedBones=True, bindMethod=0,            
        normalizeWeights=1, maximumInfluences=3, dropoffRate=4.0, name=f"{prefix}_skinCluster"
    )[0]

    exact_weights = [
        [0.999, 0.001, 0.0], [1.000, 0.000, 0.0], [1.000, 0.000, 0.0], [0.999, 0.001, 0.0],
        [0.700, 0.300, 0.0], [0.999, 0.001, 0.0], [0.999, 0.001, 0.0], [0.700, 0.300, 0.0],
        [0.374, 0.614, 0.012], [0.382, 0.606, 0.012], [0.382, 0.606, 0.012], [0.374, 0.614, 0.012],
        [0.030, 0.969, 0.001], [0.029, 0.971, 0.000], [0.029, 0.971, 0.000], [0.030, 0.969, 0.001],
        [0.001, 0.993, 0.006], [0.001, 0.995, 0.004], [0.001, 0.995, 0.004], [0.001, 0.993, 0.006],
        [0.000, 0.700, 0.300], [0.000, 0.691, 0.309], [0.000, 0.691, 0.309], [0.000, 0.700, 0.300],
        [0.0, 0.300, 0.700], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.300, 0.700],
        [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]
    ]

    cvs = cmds.ls(f"{ribbon_transform}.cv[*][*]", flatten=True)
    for idx, cv in enumerate(cvs):
        w = exact_weights[idx]
        cmds.skinPercent(skin_cluster, cv, transformValue=[
            (ctrl_joints[0], w[0]), (ctrl_joints[1], w[1]), (ctrl_joints[2], w[2])
        ])

    # --- 6. AIM LOGIC (Dual Proxy Center Tangent) ---
    cmds.aimConstraint(f"{prefix}_ribbon_01_ctl_aim_target", f"{prefix}_ribbon_02_ctl_aim_left_proxy", 
                       aimVector=(-1,0,0), upVector=(0,1,0), worldUpType="scene", maintainOffset=False, skip=["x"])
    
    cmds.aimConstraint(f"{prefix}_ribbon_03_ctl_aim_target", f"{prefix}_ribbon_02_ctl_aim_right_proxy", 
                       aimVector=(1,0,0), upVector=(0,1,0), worldUpType="scene", maintainOffset=False, skip=["x"])
    
    cmds.orientConstraint(f"{prefix}_ribbon_02_ctl_aim_left_proxy", f"{prefix}_ribbon_02_ctl_aim_right_proxy", f"{prefix}_ribbon_02_ctl_aim_grp", 
                          maintainOffset=False, skip=["x"])

    # --- 7. TRANSLATION AUTOMATION (01 and 03 push 02) ---
    for i in [1, 3]:
        mult_node = cmds.createNode("multiplyDivide", name=f"{prefix}_mult_trans_ctl{i:02d}")
        cmds.connectAttr(f"{prefix}_ribbon_{i:02d}_ctl.translate", f"{mult_node}.input1")
        cmds.setAttr(f"{mult_node}.input2", 0.5, 0.5, 0.5)

    plus_trans_02 = cmds.createNode("plusMinusAverage", name=f"{prefix}_plus_trans_ctl02")
    cmds.connectAttr(f"{prefix}_mult_trans_ctl01.output", f"{plus_trans_02}.input3D[0]")
    cmds.connectAttr(f"{prefix}_mult_trans_ctl03.output", f"{plus_trans_02}.input3D[1]")
    cmds.connectAttr(f"{plus_trans_02}.output3D", f"{prefix}_ribbon_02_ctl_auto_trans_grp.translate")

    # --- 8. ROTATION AUTOMATION (X-Axis Twist) ---
    for i in [1, 3]:
        mult_rot = cmds.createNode("multiplyDivide", name=f"{prefix}_mult_rot_ctl{i:02d}")
        cmds.connectAttr(f"{prefix}_ribbon_{i:02d}_ctl.rotateX", f"{mult_rot}.input1X")
        cmds.setAttr(f"{mult_rot}.input2X", 0.5) 

    plus_rot_02 = cmds.createNode("plusMinusAverage", name=f"{prefix}_plus_rot_ctl02")
    cmds.connectAttr(f"{prefix}_mult_rot_ctl01.outputX", f"{plus_rot_02}.input1D[0]")
    cmds.connectAttr(f"{prefix}_mult_rot_ctl03.outputX", f"{plus_rot_02}.input1D[1]")
    cmds.connectAttr(f"{plus_rot_02}.output1D", f"{prefix}_ribbon_02_ctl_auto_rot_grp.rotateX")

    # --- 9. SNAPPING LOGIC ---
    if start_snap and end_snap and cmds.objExists(start_snap) and cmds.objExists(end_snap):
        cmds.delete(cmds.pointConstraint(start_snap, end_snap, global_offset, maintainOffset=False))
        cmds.delete(cmds.orientConstraint(start_snap, end_snap, global_offset, maintainOffset=False))
        
        cmds.matchTransform(f"{prefix}_ribbon_01_ctl_offset_grp", start_snap, pos=True, rot=True)
        cmds.matchTransform(f"{prefix}_ribbon_03_ctl_offset_grp", end_snap, pos=True, rot=True)
        
        cmds.delete(cmds.pointConstraint(start_snap, end_snap, f"{prefix}_ribbon_02_ctl_offset_grp", maintainOffset=False))
        cmds.delete(cmds.orientConstraint(start_snap, end_snap, f"{prefix}_ribbon_02_ctl_offset_grp", maintainOffset=False))
        
        # FIX FOR MAYA SCALE BAKING BUG
        for attr in ['scaleX', 'scaleY', 'scaleZ']:
            cmds.setAttr(f"{global_offset}.{attr}", 1)
            cmds.setAttr(f"{prefix}_ribbon_02_ctl_offset_grp.{attr}", 1)
        
    elif start_snap and cmds.objExists(start_snap):
        cmds.matchTransform(global_offset, start_snap, pos=True, rot=False)
        cmds.matchTransform(f"{prefix}_ribbon_01_ctl_offset_grp", start_snap, pos=True, rot=True)
        
    elif end_snap and cmds.objExists(end_snap):
        cmds.matchTransform(global_offset, end_snap, pos=True, rot=False)
        cmds.matchTransform(f"{prefix}_ribbon_03_ctl_offset_grp", end_snap, pos=True, rot=True)

    # --- 10. LOCK ROOT GROUP ---
    for attr in ['tx','ty','tz','rx','ry','rz','sx','sy','sz']:
        cmds.setAttr(f"{rig_grp}.{attr}", lock=True, keyable=False)

    cmds.select(global_ctl)
    print(f"[{prefix}] Scalable Ribbon Rig successfully generated!")


# =========================================================
# UI CLASS DEFINITION
# =========================================================

class RibbonRigUI:
    def __init__(self):
        self.window_name = "proRibbonRigWindow"
        
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.window = cmds.window(self.window_name, title="Pro Ribbon Builder", widthHeight=(360, 520), sizeable=True)
        self.scroll = cmds.scrollLayout(childResizable=True) 
        self.layout = cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 15), rowSpacing=8)
        
        cmds.separator(height=5, style="none")
        cmds.text(label="Scalable Ribbon Rig Generator", font="boldLabelFont", align="center")
        cmds.separator(height=10, style="in")
        
        # --- Basic Settings ---
        cmds.rowLayout(numberOfColumns=4, columnWidth4=(35, 60, 35, 120), adjustableColumn=4)
        cmds.text(label="Side:")
        self.side_menu = cmds.optionMenu()
        cmds.menuItem(label="L")
        cmds.menuItem(label="R")
        cmds.menuItem(label="C")
        
        cmds.text(label="Part:")
        self.part_input = cmds.textField(text="upperArm")
        cmds.setParent("..")
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(90, 100), adjustableColumn=2)
        cmds.text(label="Base Width:")
        self.width_input = cmds.floatField(value=5.0, precision=2, minValue=0.1)
        cmds.setParent("..")
        
        cmds.separator(height=10, style="in")
        
        # --- Snap Objects ---
        cmds.text(label="Start Snap Object (Optional):", align="left")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnWidth2=(220, 50))
        self.start_snap_input = cmds.textField(placeholderText="Select object & click >>")
        cmds.button(label="Get Sel", command=lambda x: self.populate_field(self.start_snap_input))
        cmds.setParent("..")
        
        cmds.text(label="End Snap Object (Optional):", align="left")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnWidth2=(220, 50))
        self.end_snap_input = cmds.textField(placeholderText="Select object & click >>")
        cmds.button(label="Get Sel", command=lambda x: self.populate_field(self.end_snap_input))
        cmds.setParent("..")
        
        cmds.separator(height=10, style="in")
        
        # --- Scales and Sizes ---
        cmds.text(label="Rig & Control Sizes:", font="boldLabelFont", align="left")
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(130, 100), adjustableColumn=2)
        cmds.text(label="Rig Default Scale:")
        self.rig_scale_input = cmds.floatField(value=1.0, precision=2, minValue=0.01)
        cmds.setParent("..")
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(130, 100), adjustableColumn=2)
        cmds.text(label="Global Ctrl Radius:")
        self.global_size_input = cmds.floatField(value=1.5, precision=2, minValue=0.1)
        cmds.setParent("..")
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(130, 100), adjustableColumn=2)
        cmds.text(label="Main Ctrl Radius:")
        self.main_size_input = cmds.floatField(value=1.0, precision=2, minValue=0.1)
        cmds.setParent("..")
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(130, 100), adjustableColumn=2)
        cmds.text(label="Tweak Ctrl Radius:")
        self.tweak_size_input = cmds.floatField(value=0.75, precision=2, minValue=0.05)
        cmds.setParent("..")
        
        cmds.separator(height=15, style="none")
        
        # --- Build Button ---
        cmds.button(
            label="Build Ribbon Rig", 
            height=40, 
            backgroundColor=(0.25, 0.65, 0.4), 
            command=self.execute_build
        )
        
        cmds.separator(height=15, style="none")
        cmds.showWindow(self.window)

    def populate_field(self, text_field):
        sel = cmds.ls(selection=True)
        if sel:
            cmds.textField(text_field, edit=True, text=sel[0])
        else:
            cmds.warning("Nothing selected! Please select an object in the viewport.")

    def execute_build(self, *args):
        # Fetch all UI variables
        side = cmds.optionMenu(self.side_menu, query=True, value=True)
        part = cmds.textField(self.part_input, query=True, text=True)
        width = cmds.floatField(self.width_input, query=True, value=True)
        
        rig_scale = cmds.floatField(self.rig_scale_input, query=True, value=True)
        g_size = cmds.floatField(self.global_size_input, query=True, value=True)
        m_size = cmds.floatField(self.main_size_input, query=True, value=True)
        t_size = cmds.floatField(self.tweak_size_input, query=True, value=True)
        
        start_snap = cmds.textField(self.start_snap_input, query=True, text=True)
        end_snap = cmds.textField(self.end_snap_input, query=True, text=True)
        
        if not start_snap.strip(): start_snap = None
        if not end_snap.strip(): end_snap = None
        
        create_pro_ribbon(
            side=side, part=part, start_snap=start_snap, end_snap=end_snap, 
            surface_width=width, rig_scale=rig_scale, 
            global_size=g_size, main_size=m_size, tweak_size=t_size
        )

# Run the UI
RibbonRigUI()