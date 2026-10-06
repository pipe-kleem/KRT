
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



