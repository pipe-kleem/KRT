import maya.cmds as cmds

def show_honeybee_rig_ui():
    win_name = "honeybee_rig_builder_ui"
    
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)
        
    win = cmds.window(win_name, title="Honeybee Auto-Rigger Pro", widthHeight=(350, 420), sizeable=True)
    
    cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 5))
    
    cmds.separator(height=10, style='none')
    cmds.text(label="HONEYBEE RIG BUILDER", font="boldLabelFont", height=25)
    cmds.text(label="Automated Skeleton Setup Tool", font="smallObliqueLabelFont", height=15)
    cmds.separator(height=15, style='in')
    
    cmds.frameLayout(label=" Control Scale Parameters ", marginWidth=15, marginHeight=15, collapsable=False)
    
    cmds.rowColumnLayout(numberOfColumns=2, 
                         columnWidth=[(1, 140), (2, 140)], 
                         columnSpacing=[(2, 10)], 
                         rowSpacing=[(1, 10), (2, 10), (3, 10), (4, 10), (5, 10), (6, 10), (7, 10)])
    
    cmds.text(label="Global Scale:", align="right", font="boldLabelFont")
    cmds.floatField("scale_global_fld", value=0.0900, precision=4, step=0.001)

    # Renamed Offset to Subcontrol
    cmds.text(label="Subcontrol Scale:", align="right", font="boldLabelFont")
    cmds.floatField("scale_subcontrol_fld", value=0.0800, precision=4, step=0.001)

    cmds.text(label="Body Scale:", align="right", font="boldLabelFont")
    cmds.floatField("scale_body_fld", value=0.0200, precision=4, step=0.001)

    cmds.text(label="Legs Scale:", align="right", font="plainLabelFont")
    cmds.floatField("scale_legs_fld", value=0.0030, precision=4, step=0.001)
    
    cmds.text(label="Abdomen Scale:", align="right", font="plainLabelFont")
    cmds.floatField("scale_abdomen_fld", value=0.0150, precision=4, step=0.001)
    
    cmds.text(label="Antennae Scale:", align="right", font="plainLabelFont")
    cmds.floatField("scale_antennae_fld", value=0.0030, precision=4, step=0.001)
    
    cmds.text(label="Others Scale:", align="right", font="plainLabelFont")
    cmds.floatField("scale_others_fld", value=0.0030, precision=4, step=0.001)
    
    cmds.setParent('..') 
    cmds.setParent('..') 
    
    cmds.separator(height=15, style='none')
    cmds.button(label="BUILD RIG", height=45, backgroundColor=(0.2, 0.6, 0.8), 
                command=lambda x: execute_rig_build())
    cmds.separator(height=10, style='none')
    
    cmds.showWindow(win)

def execute_rig_build():
    s_glb = cmds.floatField("scale_global_fld", query=True, value=True)
    s_sub = cmds.floatField("scale_subcontrol_fld", query=True, value=True)
    s_bdy = cmds.floatField("scale_body_fld", query=True, value=True)
    s_legs = cmds.floatField("scale_legs_fld", query=True, value=True)
    s_ab = cmds.floatField("scale_abdomen_fld", query=True, value=True)
    s_ant = cmds.floatField("scale_antennae_fld", query=True, value=True)
    s_oth = cmds.floatField("scale_others_fld", query=True, value=True)
        
    build_honeybee_rig(scale_legs=s_legs, scale_abdomen=s_ab, scale_antennae=s_ant, scale_others=s_oth, scale_global=s_glb, scale_subcontrol=s_sub, scale_body=s_bdy)

def build_honeybee_rig(scale_legs=1.0, scale_abdomen=1.0, scale_antennae=1.0, scale_others=1.0, scale_global=1.0, scale_subcontrol=1.0, scale_body=1.0):
    
    # Custom scale detection
    def get_custom_scale(jnt_name):
        name = jnt_name.lower()
        if "leg" in name or "middle" in name:
            return scale_legs
        elif "abdomen" in name:
            return scale_abdomen
        elif "antenna" in name:
            return scale_antennae
        else:
            return scale_others

    # Custom color detection logic (L = Sky Blue, R = Red, Center = Yellow)
    def get_color_index(ctl_name):
        if ctl_name.startswith("l_") or ctl_name == "subcontrol":
            return 18 # Maya Sky Blue
        elif ctl_name.startswith("r_"):
            return 13 # Maya Red
        else:
            return 17 # Maya Yellow (Center / Mid)

    # --------------------------------------------------------
    # 1. MAIN GROUPING SETUP
    # --------------------------------------------------------
    rig_main = "rig_grp"
    ctrl_main = "controls_grp"
    jnt_main = "joints_grp"
    ik_main = "ik_grp"

    if not cmds.objExists(rig_main):
        cmds.group(em=True, name=rig_main)
    
    if not cmds.objExists(ctrl_main):
        cmds.group(em=True, name=ctrl_main)
        cmds.parent(ctrl_main, rig_main)
        
    if not cmds.objExists(jnt_main):
        cmds.group(em=True, name=jnt_main)
        cmds.parent(jnt_main, rig_main)
        cmds.setAttr(jnt_main + ".visibility", 0)

    if not cmds.objExists(ik_main):
        cmds.group(em=True, name=ik_main)
        cmds.parent(ik_main, rig_main)
        cmds.setAttr(ik_main + ".visibility", 0)

    if cmds.objExists("root_jnt") and cmds.listRelatives("root_jnt", parent=True) != [jnt_main]:
        try: cmds.parent("root_jnt", jnt_main)
        except Exception: pass

    # --------------------------------------------------------
    # CONTROL SHAPE GENERATORS
    # --------------------------------------------------------
    def create_circle_ctl(name, target_jnt, ctl_scale=1.0, normal=(1, 0, 0)):
        name = name.lower()
        color_idx = get_color_index(name)
        ctl = cmds.circle(n=name + "_ctl", nr=normal, r=2 * ctl_scale)[0]
        
        shapes = cmds.listRelatives(ctl, shapes=True)
        if shapes:
            cmds.setAttr(shapes[0] + ".overrideEnabled", 1)
            cmds.setAttr(shapes[0] + ".overrideColor", color_idx)
            
        cmds.setAttr(ctl + ".v", lock=True, keyable=False, channelBox=False)
            
        grp = cmds.group(ctl, n=name + "_ctl_grp")
        if target_jnt and cmds.objExists(target_jnt):
            cmds.matchTransform(grp, target_jnt)
        return ctl, grp

    def create_box_ctl(name, target_jnt, ctl_scale=1.0):
        name = name.lower()
        color_idx = get_color_index(name)
        s = ctl_scale * 2.5
        pts = [(-s, s, s), (s, s, s), (s, -s, s), (-s, -s, s), (-s, s, s), 
               (-s, s, -s), (s, s, -s), (s, -s, -s), (-s, -s, -s), (-s, s, -s), 
               (s, s, -s), (s, s, s), (s, -s, s), (s, -s, -s), (-s, -s, -s), (-s, -s, s)]
        
        ctl = cmds.curve(n=name + "_ctl", d=1, p=pts)
        
        shapes = cmds.listRelatives(ctl, shapes=True)
        if shapes:
            cmds.setAttr(shapes[0] + ".overrideEnabled", 1)
            cmds.setAttr(shapes[0] + ".overrideColor", color_idx)
            
        cmds.setAttr(ctl + ".v", lock=True, keyable=False, channelBox=False)
            
        grp = cmds.group(ctl, n=name + "_ctl_grp")
        if target_jnt and cmds.objExists(target_jnt):
            cmds.matchTransform(grp, target_jnt)
        return ctl, grp

    # --------------------------------------------------------
    # 1.5 GLOBAL, SUBCONTROL, AND BODY SETUP
    # --------------------------------------------------------
    global_ctl, global_grp = create_circle_ctl("global", "", ctl_scale=scale_global, normal=(0, 1, 0))
    cmds.parent(global_grp, ctrl_main)
    
    cmds.addAttr(global_ctl, longName="globalScale", attributeType='double', defaultValue=1.0, minValue=0.001, keyable=True)
    
    for axis in ['x', 'y', 'z']:
        cmds.setAttr(f"{global_ctl}.scale{axis.upper()}", lock=True, keyable=False, channelBox=False)
        cmds.connectAttr(f"{global_ctl}.globalScale", f"{jnt_main}.scale{axis.upper()}")
        cmds.connectAttr(f"{global_ctl}.globalScale", f"{global_grp}.scale{axis.upper()}")

    # Renamed Offset to Subcontrol (Color is automatically handled by the get_color_index function)
    subcontrol_ctl, subcontrol_grp = create_circle_ctl("subcontrol", "", ctl_scale=scale_subcontrol, normal=(0, 1, 0))
    cmds.parent(subcontrol_grp, global_ctl)
    
    if cmds.objExists("root_jnt"):
        try: cmds.parentConstraint(subcontrol_ctl, "root_jnt", mo=True)
        except RuntimeError: pass

    body_ctl, body_grp = create_circle_ctl("body", "body_jnt", ctl_scale=scale_body)
    cmds.parent(body_grp, subcontrol_ctl)
    
    if cmds.objExists("body_jnt"):
        try: cmds.parentConstraint(body_ctl, "body_jnt", mo=True)
        except RuntimeError: pass

    # --------------------------------------------------------
    # 2. IK CONTROL SETUP
    # --------------------------------------------------------
    ik_pairs = [
        ("l_foreleg_02_jnt", "l_foreleg_05_jnt"),
        ("l_middle_02_jnt", "l_middle_05_jnt"),
        ("l_hindleg_02_jnt", "l_hindleg_05_jnt"),
        ("r_foreleg_02_jnt", "r_foreleg_05_jnt"),
        ("r_middle_02_jnt", "r_middle_05_jnt"),
        ("r_hindleg_02_jnt", "r_hindleg_05_jnt")
    ]

    for start_jnt, end_jnt in ik_pairs:
        if cmds.objExists(start_jnt) and cmds.objExists(end_jnt):
            base_name = start_jnt.replace("_02_jnt", "_ik").lower()
            
            ik_name = base_name + "_ikh"
            if not cmds.objExists(ik_name):
                ik_nodes = cmds.ikHandle(sj=start_jnt, ee=end_jnt, sol='ikRPsolver', n=ik_name)
                ik_handle = ik_nodes[0]
            else:
                ik_handle = ik_name
            
            current_scale = get_custom_scale(end_jnt)
            
            ctl, grp = create_box_ctl(base_name, ctl_scale=current_scale, target_jnt=end_jnt)
            
            try:
                cmds.parentConstraint(ctl, ik_handle, mo=True)
                cmds.orientConstraint(ctl, end_jnt, mo=True)
            except RuntimeError: pass
            
            mid_jnt = start_jnt.replace("_02_jnt", "_03_jnt")
            pv_scale = current_scale * 0.5
            pv_ctl, pv_grp = create_circle_ctl(base_name + "_pv", target_jnt=mid_jnt, ctl_scale=pv_scale)
            
            try: cmds.poleVectorConstraint(pv_ctl, ik_handle)
            except RuntimeError: pass
            
            cmds.setAttr(ik_handle + ".visibility", 0)
            
            if cmds.listRelatives(ik_handle, parent=True) != [ik_main]:
                cmds.parent(ik_handle, ik_main) 
            
            if cmds.listRelatives(grp, parent=True) != [body_ctl]:
                cmds.parent(grp, body_ctl)
            if cmds.listRelatives(pv_grp, parent=True) != [body_ctl]:
                cmds.parent(pv_grp, body_ctl)

    # --------------------------------------------------------
    # 3. LOWER LEG FK SETUP
    # --------------------------------------------------------
    leg_prefixes = ["l_foreleg", "l_middle", "l_hindleg", "r_foreleg", "r_middle", "r_hindleg"]
    
    for prefix in leg_prefixes:
        foot_chain = [f"{prefix}_06_jnt", f"{prefix}_07_jnt", f"{prefix}_08_jnt", f"{prefix}_09_jnt"]
        
        parent_ctl = f"{prefix}_ik_ctl" 
        if not cmds.objExists(parent_ctl):
            parent_ctl = body_ctl 
            
        for jnt in foot_chain:
            if not cmds.objExists(jnt): continue
            
            base_name = jnt.replace("_jnt", "").lower()
            current_scale = get_custom_scale(jnt) * 0.7 
            
            ctl, grp = create_circle_ctl(base_name, target_jnt=jnt, ctl_scale=current_scale)
            
            try: cmds.parentConstraint(ctl, jnt, mo=True)
            except RuntimeError: pass
            
            if cmds.listRelatives(grp, parent=True) != [parent_ctl]:
                cmds.parent(grp, parent_ctl)
                
            parent_ctl = ctl

    # --------------------------------------------------------
    # 4. STANDARD FK CONTROL SETUP
    # --------------------------------------------------------
    fk_chains = [
        ["abdomen_root_jnt", "abdomen_01_jnt", "abdomen_02_jnt", "abdomen_03_jnt"],
        ["l_antenna_01_jnt", "l_antenna_02_jnt", "l_antenna_03_jnt", "l_antenna_04_jnt", "l_antenna_05_jnt"],
        ["r_antenna_01_jnt", "r_antenna_02_jnt", "r_antenna_03_jnt", "r_antenna_04_jnt", "r_antenna_05_jnt"],
        ["l_mandible_01_jnt", "l_mandible_02_jnt"],
        ["r_mandibre_01_jnt", "r_mandibre_02_jnt"] 
    ]
    
    for chain in fk_chains:
        parent_ctl = None
        for jnt in chain:
            if not cmds.objExists(jnt):
                alt_jnt = jnt.replace("mandibre", "mandible")
                if cmds.objExists(alt_jnt): jnt = alt_jnt
                else: continue
                
            base_name = jnt.replace("_jnt", "").lower()
            current_scale = get_custom_scale(jnt)
            
            ctl, grp = create_circle_ctl(base_name, target_jnt=jnt, ctl_scale=current_scale)
            
            try: cmds.parentConstraint(ctl, jnt, mo=True)
            except RuntimeError: pass
            
            if parent_ctl:
                cmds.parent(grp, parent_ctl)
            else:
                if cmds.listRelatives(grp, parent=True) != [body_ctl]:
                    cmds.parent(grp, body_ctl)
            
            parent_ctl = ctl

    fk_singles = [
        "l_wing_01_jnt", "r_wing_01_jnt",
        "l_foreleg_01_jnt", "l_middle_01_jnt", "l_hindleg_01_jnt",
        "r_foreleg_01_jnt", "r_middle_01_jnt", "r_hindleg_01_jnt",
        "head_jnt"
    ]

    for jnt in fk_singles:
        if cmds.objExists(jnt):
            base_name = jnt.replace("_jnt", "").lower()
            current_scale = get_custom_scale(jnt)
            
            ctl, grp = create_circle_ctl(base_name, target_jnt=jnt, ctl_scale=current_scale)
            
            try: cmds.parentConstraint(ctl, jnt, mo=True)
            except RuntimeError: pass
            
            if cmds.listRelatives(grp, parent=True) != [body_ctl]:
                cmds.parent(grp, body_ctl)
            
    print("Honeybee Rig Build Complete! Control Colors applied successfully.")

# Open the tool window:
show_honeybee_rig_ui()