import maya.cmds as cmds

# --------------------------------------------------------
# 1. CREATION FUNCTION
# --------------------------------------------------------
def create_auto_muscle_setup(driver_attr, new_joint_name, joint_radius=None, locator_size=None, snap_vertex=None, constraint_target=None):
    driver_node = driver_attr.split('.')[0]
    
    if not cmds.objExists(driver_node):
        cmds.warning(f"Driver object does not exist: {driver_node}")
        return

    # Determine final constraint target
    if constraint_target and not cmds.objExists(constraint_target):
        cmds.warning(f"Constraint target '{constraint_target}' not found. Falling back to driver node '{driver_node}'.")
        target_node = driver_node
    else:
        target_node = constraint_target if constraint_target else driver_node

    # Create Zero Group and Driven Joint
    cmds.select(clear=True)
    driven_joint = cmds.joint(name=new_joint_name)
    cmds.matchTransform(driven_joint, driver_node, pos=True, rot=True)
    
    zero_grp = cmds.group(empty=True, name=f"{new_joint_name}_zeroGrp")
    cmds.matchTransform(zero_grp, driver_node, pos=True, rot=True)
    cmds.parent(driven_joint, zero_grp)
    
    # Create Guide Locators
    default_loc = cmds.spaceLocator(name=f"{new_joint_name}_defaultLoc")[0]
    stretch_loc = cmds.spaceLocator(name=f"{new_joint_name}_stretchLoc")[0]
    
    for loc, color in [(default_loc, 17), (stretch_loc, 18)]: # 17 = Yellow, 18 = Sky Blue
        cmds.matchTransform(loc, driver_node, pos=True, rot=True)
        cmds.parent(loc, zero_grp)
        loc_shape = cmds.listRelatives(loc, shapes=True)[0]
        cmds.setAttr(f"{loc_shape}.overrideEnabled", 1)
        cmds.setAttr(f"{loc_shape}.overrideColor", color)
        
    # --------------------------------------------------------
    # Vertex Snap Logic (Moves the group BEFORE constraining)
    # --------------------------------------------------------
    if snap_vertex:
        if cmds.objExists(snap_vertex):
            vtx_pos = cmds.xform(snap_vertex, query=True, worldSpace=True, translation=True)
            cmds.xform(zero_grp, worldSpace=True, translation=vtx_pos)
        else:
            cmds.warning(f"Vertex {snap_vertex} not found. Snapping to driver joint instead.")

    # Constrain the zero group to the target node
    cmds.parentConstraint(target_node, zero_grp, maintainOffset=True)
    cmds.scaleConstraint(target_node, zero_grp, maintainOffset=True)
    
    # Radii/Scale
    driver_rad = cmds.getAttr(f"{driver_node}.radius") if cmds.attributeQuery('radius', node=driver_node, exists=True) else 1.0
    final_jnt_rad = joint_radius if joint_radius is not None else (driver_rad * 3.0)
    final_loc_size = locator_size if locator_size is not None else (final_jnt_rad * 1.2)
        
    cmds.setAttr(f"{driven_joint}.radius", final_jnt_rad)
    cmds.setAttr(f"{driven_joint}.overrideEnabled", 1)
    cmds.setAttr(f"{driven_joint}.overrideColor", 13)
    
    for loc in [default_loc, stretch_loc]:
        loc_shape = cmds.listRelatives(loc, shapes=True)[0]
        cmds.setAttr(f"{loc_shape}.localScaleX", final_loc_size)
        cmds.setAttr(f"{loc_shape}.localScaleY", final_loc_size)
        cmds.setAttr(f"{loc_shape}.localScaleZ", final_loc_size)

    # UI Attributes
    cmds.addAttr(driven_joint, ln='Muscle_Settings', at='enum', en='-------:')
    cmds.setAttr(f"{driven_joint}.Muscle_Settings", cb=True)
    
    cmds.addAttr(driven_joint, ln='activation_dir', at='enum', en='Positive:Negative:Both', k=True)
    cmds.setAttr(f"{driven_joint}.activation_dir", 0)
    
    cmds.addAttr(driven_joint, ln='show_locators', at='bool', k=True)
    cmds.setAttr(f"{driven_joint}.show_locators", 1)
    cmds.connectAttr(f"{driven_joint}.show_locators", f"{default_loc}.visibility")
    cmds.connectAttr(f"{driven_joint}.show_locators", f"{stretch_loc}.visibility")

    for limit_attr in ['driver_min', 'driver_max']:
        cmds.addAttr(driven_joint, ln=limit_attr, at='float', k=True)
    cmds.setAttr(f"{driven_joint}.driver_min", 0.0)
    cmds.setAttr(f"{driven_joint}.driver_max", 90.0)

    # Direction Logic Network
    node_prefix = f"{driven_joint}_dirLogic"
    
    md_neg = cmds.createNode('multiplyDivide', name=f"{node_prefix}_neg_MD")
    cmds.setAttr(f"{md_neg}.input2X", -1)
    cmds.connectAttr(driver_attr, f"{md_neg}.input1X", force=True)
    
    cond_abs = cmds.createNode('condition', name=f"{node_prefix}_abs_COND")
    cmds.setAttr(f"{cond_abs}.operation", 4)
    cmds.setAttr(f"{cond_abs}.secondTerm", 0)
    cmds.connectAttr(driver_attr, f"{cond_abs}.firstTerm", force=True)
    cmds.connectAttr(driver_attr, f"{cond_abs}.colorIfFalseR", force=True)
    cmds.connectAttr(f"{md_neg}.outputX", f"{cond_abs}.colorIfTrueR", force=True)
    
    choice_dir = cmds.createNode('choice', name=f"{node_prefix}_CHOICE")
    cmds.connectAttr(f"{driven_joint}.activation_dir", f"{choice_dir}.selector", force=True)
    cmds.connectAttr(driver_attr, f"{choice_dir}.input[0]", force=True)
    cmds.connectAttr(f"{md_neg}.outputX", f"{choice_dir}.input[1]", force=True)
    cmds.connectAttr(f"{cond_abs}.outColorR", f"{choice_dir}.input[2]", force=True)

    # Remap Network
    attributes = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']
    full_attrs = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ', 'scaleX', 'scaleY', 'scaleZ']
    
    for i in range(9):
        short_a = attributes[i]
        full_a = full_attrs[i]
        
        cmds.addAttr(driven_joint, ln=f"default_{full_a}", at='float', k=True)
        cmds.addAttr(driven_joint, ln=f"stretch_{full_a}", at='float', k=True)
        
        cmds.connectAttr(f"{default_loc}.{short_a}", f"{driven_joint}.default_{full_a}", force=True)
        cmds.connectAttr(f"{stretch_loc}.{short_a}", f"{driven_joint}.stretch_{full_a}", force=True)

        remap_node = cmds.createNode('remapValue', name=f"{driven_joint}_{full_a}_muscleRemap")
        
        cmds.connectAttr(f"{choice_dir}.output", f"{remap_node}.inputValue", force=True)
        cmds.connectAttr(f"{driven_joint}.driver_min", f"{remap_node}.inputMin", force=True)
        cmds.connectAttr(f"{driven_joint}.driver_max", f"{remap_node}.inputMax", force=True)
        cmds.connectAttr(f"{driven_joint}.default_{full_a}", f"{remap_node}.outputMin", force=True)
        cmds.connectAttr(f"{driven_joint}.stretch_{full_a}", f"{remap_node}.outputMax", force=True)
        cmds.connectAttr(f"{remap_node}.outValue", f"{driven_joint}.{full_a}", force=True)

    print(f"Success: Dynamic muscle '{driven_joint}' created.")

# --------------------------------------------------------
# 2. DELETION FUNCTION
# --------------------------------------------------------
def delete_all_muscle_setups():
    all_joints = cmds.ls(type='joint')
    for jnt in all_joints:
        if cmds.attributeQuery('Muscle_Settings', node=jnt, exists=True):
            connections = cmds.listConnections(jnt, type='remapValue')
            if connections:
                cmds.delete(list(set(connections)))
            dir_nodes = cmds.ls(f"{jnt}_dirLogic*")
            if dir_nodes:
                cmds.delete(dir_nodes)
            parent_grp = cmds.listRelatives(jnt, parent=True)
            if parent_grp and parent_grp[0].endswith('_zeroGrp'):
                cmds.delete(parent_grp[0])
            else:
                cmds.delete(jnt)

# --------------------------------------------------------
# 3. EXPORT FUNCTION
# --------------------------------------------------------
def print_muscle_poses():
    joints = cmds.ls(type='joint')
    print("\n# ==================================================")
    print("# PASTE THE FOLLOWING SCRIPT TO RESTORE MUSCLE POSES")
    print("# ==================================================")
    print("import maya.cmds as cmds\n")
    
    for jnt in joints:
        if cmds.attributeQuery('Muscle_Settings', node=jnt, exists=True):
            print(f"# Restoring Setup: {jnt}")
            for attr in ['activation_dir', 'driver_min', 'driver_max']:
                val = cmds.getAttr(f"{jnt}.{attr}")
                print(f"cmds.setAttr('{jnt}.{attr}', {val})")
            
            for loc_suffix in ['_defaultLoc', '_stretchLoc']:
                loc_name = f"{jnt}{loc_suffix}"
                if cmds.objExists(loc_name):
                    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']:
                        val = cmds.getAttr(f"{loc_name}.{attr}")
                        print(f"cmds.setAttr('{loc_name}.{attr}', {round(val, 4)})")
            print("")
    print("# ==================================================\n")

# ==========================================
# 4. EXECUTION EXAMPLES
# ==========================================


def stretchy():

    delete_all_muscle_setups()

    # Example 1: Full features (Custom sizes, Snap to Vertex, Custom Constraint Target)
    create_auto_muscle_setup( driver_attr="CC_Base_L_Clavicle.rotateX", new_joint_name="trapeziusMuscle_L_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[18808]", constraint_target="CC_Base_L_Clavicle")

    create_auto_muscle_setup( driver_attr="CC_Base_L_Upperarm.rotateZ", new_joint_name="deltoidMuscle_L_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[40874]", constraint_target="CC_Base_L_Upperarm")

    create_auto_muscle_setup( driver_attr="CC_Base_L_Forearm.rotateX", new_joint_name="bicepsMuscle_L_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[20663]", constraint_target="CC_Base_L_Upperarm")

    create_auto_muscle_setup( driver_attr="CC_Base_L_Forearm.rotateX", new_joint_name="tricepsMuscle_L_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[40881]", constraint_target="CC_Base_L_Upperarm")


    create_auto_muscle_setup( driver_attr="CC_Base_R_Clavicle.rotateX", new_joint_name="trapeziusMuscle_R_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[19781]", constraint_target="CC_Base_R_Clavicle")

    create_auto_muscle_setup( driver_attr="CC_Base_R_Upperarm.rotateZ", new_joint_name="deltoidMuscle_R_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[45077]", constraint_target="CC_Base_R_Upperarm")

    create_auto_muscle_setup( driver_attr="CC_Base_R_Forearm.rotateX", new_joint_name="bicepsMuscle_R_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[22755]", constraint_target="CC_Base_R_Upperarm")

    create_auto_muscle_setup( driver_attr="CC_Base_R_Forearm.rotateX", new_joint_name="tricepsMuscle_R_JNT", joint_radius=25.0, locator_size=25.0, snap_vertex="CC_Base_Body.vtx[45082]", constraint_target="CC_Base_R_Upperarm")


# stretchy()