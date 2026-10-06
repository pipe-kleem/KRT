import maya.cmds as cmds
import maya.mel as mel

def create_wrapped_follicle_rig():
    # 1. Get the current selection (Expecting exactly 2 items: 1 Joint, 1 Mesh)
    selection = cmds.ls(selection=True)
    
    if len(selection) != 2:
        cmds.warning("Please select exactly ONE root joint and ONE mesh!")
        return
        
    # Separate the joint from the mesh in the selection
    joints = cmds.ls(selection, type='joint')
    if not joints:
        cmds.warning("No joint found in your selection!")
        return
        
    root_joint = joints[0]
    
    # The mesh is whichever selected item is NOT the joint
    source_mesh = [item for item in selection if item != root_joint][0]
    
    # 2. Get all descendants
    descendants = cmds.listRelatives(root_joint, allDescendents=True, type='joint', fullPath=True)
    if not descendants:
        cmds.warning("No children found in the joint hierarchy!")
        return
        
    descendants.reverse()
    root_short_name = root_joint.split('|')[-1] 
    
    # 3. Create Master Groups
    planes_group = cmds.group(empty=True, world=True, name=root_short_name + "_PLANES_GRP")
    fols_group = cmds.group(empty=True, world=True, name=root_short_name + "_FOLLICLES_GRP")
    mesh_group = cmds.group(empty=True, world=True, name=root_short_name + "_DRIVER_MESH_GRP")
    
    # --- DUPLICATE THE MESH ---
    dup_mesh = cmds.duplicate(source_mesh, name=root_short_name + "_WrapDriver_GEO")[0]
    cmds.parent(dup_mesh, mesh_group)
    
    # List to store all planes so we can wrap them at the end
    all_planes = []
    
    # 4. Process each joint
    for jnt in descendants:
        short_name = jnt.split('|')[-1]
        
        # --- CREATE DUPLICATE JOINT ---
        dup_jnt = cmds.duplicate(jnt, parentOnly=True)[0]
        final_jnt_name = "LOCG_" + short_name
        cmds.rename(dup_jnt, final_jnt_name)
        cmds.setAttr(final_jnt_name + ".radius", 25)
        
        # --- CREATE PLANE ---
        plane_name = "PLANE_" + short_name
        plane = cmds.polyPlane(name=plane_name, width=0.1, height=0.1, subdivisionsX=1, subdivisionsY=1)[0]
        plane_shape = cmds.listRelatives(plane, shapes=True)[0]
        
        # Snap plane to original joint and parent it to the planes group
        cmds.matchTransform(plane, jnt, position=True, rotation=True)
        cmds.parent(plane, planes_group)
        
        # Add plane to our list for the Wrap Deformer later
        all_planes.append(plane)
        
        # --- CREATE FOLLICLE ---
        fol_shape = cmds.createNode('follicle')
        fol_transform = cmds.listRelatives(fol_shape, parent=True)[0]
        
        fol_name = "FOL_" + short_name
        fol_transform = cmds.rename(fol_transform, fol_name)
        fol_shape = cmds.listRelatives(fol_transform, shapes=True)[0] 
        
        cmds.connectAttr(plane_shape + ".outMesh", fol_shape + ".inputMesh", force=True)
        cmds.connectAttr(plane_shape + ".worldMatrix[0]", fol_shape + ".inputWorldMatrix", force=True)
        cmds.connectAttr(fol_shape + ".outTranslate", fol_transform + ".translate", force=True)
        cmds.connectAttr(fol_shape + ".outRotate", fol_transform + ".rotate", force=True)
        
        cmds.setAttr(fol_shape + ".parameterU", 0.5)
        cmds.setAttr(fol_shape + ".parameterV", 0.5)
        
        cmds.parent(fol_transform, fols_group)
        cmds.parent(final_jnt_name, fol_transform)
        
    # 5. --- APPLY WRAP DEFORMER ---
    # Maya's wrap deformer works best using the native MEL command.
    # We select all the planes first, then shift-select the driver mesh last.
    cmds.select(clear=True)
    cmds.select(all_planes, replace=True)
    cmds.select(dup_mesh, add=True)
    
    # Execute the wrap command
    mel.eval('CreateWrap;')
    
    # Clear selection so things look clean at the end
    cmds.select(clear=True)
    
    print(f"Success! {len(all_planes)} planes created, connected to follicles, and wrapped to '{dup_mesh}'.")

# Run the function
create_wrapped_follicle_rig()