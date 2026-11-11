"""UniUtils - the studio's universal rig helpers, shipped inside KRT (Stage 68).

Copied from P:/rigging_team/Pipeline_share/RigUtils/UniUtils.py. Every
function below is unchanged; only this import header differs:
  - Fan / stretchy / Tweaker / capture_viewport_api come from this folder
    (KRT/rigutils/) instead of the P: share on sys.path,
  - breathing is KRT's own utils/breathing.py (the newest Breathing setup,
    from kva_a), which has the same main(Body_Mesh, mesh_list, use_001_scaling),
  - the two MEL procs are sourced from this folder.
At the bottom, everything from rig_lib (the generic half of the old
per-rig scripts/utils.py) is pulled in too, so UniUtils.replace_and_rename_mesh
and plain replace_and_rename_mesh both work.
"""
import maya.cmds as cmds
import maya.mel as mel
import os
import sys
import importlib

from . import capture_viewport_api, Fan, stretchy, Tweaker
from ..utils import breathing

_HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
for _mel_file in ("extraSliders.mel", "teethCtrlAdded.mel"):
    try:
        mel.eval('source "{}/{}";'.format(_HERE, _mel_file))
    except RuntimeError as _e:
        cmds.warning("[KRT rigutils] could not source {}: {}".format(_mel_file, _e))


def run_stretchy():
    # Replace 'main()' with the actual function name inside stretchy.py that starts the tool
    stretchy.stretchy()

def run_Fan():
    # Replace 'main()' with the actual function name inside Fan.py that starts the tool
    Fan.Fan()

def run_breathing(Body_Mesh, mesh_list, use_001_scaling):
    # Replace 'main()' with the actual function name inside run_breathing.py that starts the tool
    breathing.main(Body_Mesh, mesh_list, use_001_scaling)

    """
    run_breathing(Body_Mesh = "geo_vasu_cc_base_body_lod_0" , mesh_list = ["geo_vasu_rudra_big_mala_lod_0", "geo_vasu_rudra_small_mala_lod_0"], use_001_scaling=False,)

    """


def TweakerMain(vtx_names, ad_meshes, src_msh, bind_scale, use_bind_scale, influenceRadius, fullWeightWadius, fallOff):
    # Replace 'main()' with the actual function name inside Tweaker.py that starts the tool
    Tweaker.main(vtx_names, ad_meshes, src_msh, bind_scale, use_bind_scale, influenceRadius, fullWeightWadius, fallOff)
        
    """
    TweakerMain(vtx_names =["geo_ravana_cc_base_body_lod_0.vtx[1607]","geo_ravana_cc_base_body_lod_0.vtx[3961]","geo_ravana_cc_base_body_lod_0.vtx[80969]","geo_ravana_cc_base_body_lod_0.vtx[89339]","geo_ravana_cc_base_body_lod_0.vtx[18408]","geo_ravana_cc_base_body_lod_0.vtx[19381]","geo_ravana_cc_base_body_lod_0.vtx[194120]","geo_ravana_cc_base_body_lod_0.vtx[202527]","geo_ravana_cc_base_body_lod_0.vtx[81072]","geo_ravana_cc_base_body_lod_0.vtx[89440]","geo_ravana_cc_base_body_lod_0.vtx[138281]","geo_ravana_cc_base_body_lod_0.vtx[146648]","geo_ravana_cc_base_body_lod_0.vtx[158181]","geo_ravana_cc_base_body_lod_0.vtx[162710]","geo_ravana_cc_base_body_lod_0.vtx[1721]","geo_ravana_cc_base_body_lod_0.vtx[4066]","geo_ravana_cc_base_body_lod_0.vtx[18807]","geo_ravana_cc_base_body_lod_0.vtx[19780]","geo_ravana_cc_base_body_lod_0.vtx[176153]","geo_ravana_cc_base_body_lod_0.vtx[184470]"], ad_meshes = ["geo_ravana_rudra_neck_lod_0","geo_ravana_janeu_lod_0","geo_ravana_rudra_bicep_lod_0","geo_ravana_belt_lod_0","geo_ravana_cloth_lod_0","geo_ravana_body_hair_lod_0","geo_ravana_arm_hair_lod_0"],src_msh =  "geo_ravana_cc_base_body_lod_0", bind_scale = 0.01, use_bind_scale = True, influenceRadius=0.08, fullWeightWadius=0.0001, fallOff=2.0)
    """




def snap_joint(source_joint, target_joint, preserve_skin=True, preserve_children=True):
    """
    Snaps the source_joint to the target_joint's world position.
    
    :param source_joint: The joint to move.
    :param target_joint: The joint to snap to.
    :param preserve_skin: If True, the skinned mesh will not deform (Move Skinned Joints Tool).
    :param preserve_children: If True, child joints will not move (Mimics the 'd' key).
    """
    
    # 1. Acquire target joint's world space translation coordinates
    target_pos = cmds.xform(target_joint, query=True, worldSpace=True, translation=True)
    
    # 2. Locate all skinClusters attached to the source joint
    skin_clusters = list(set(cmds.listConnections(source_joint, type="skinCluster") or []))
    
    # 3. Enable 'Move Skinned Joints' mode to detach influence temporarily
    if preserve_skin:
        for skin in skin_clusters:
            cmds.skinCluster(skin, edit=True, moveJointsMode=True)
            
    # 4. Execute the move command
    # The preserveChildPosition flag locks the child hierarchy in world space
    cmds.move(target_pos[0], target_pos[1], target_pos[2], source_joint, 
              absolute=True, worldSpace=True, preserveChildPosition=preserve_children)
              
    # 5. Disable 'Move Skinned Joints' mode to restore influence
    if preserve_skin:
        for skin in skin_clusters:
            cmds.skinCluster(skin, edit=True, moveJointsMode=False)

# --- Execution Example ---
# snap_joint("L_Wrist_Jnt", "Loc_Target", preserve_skin=True, preserve_children=True)

#=======================================================================================

def reference_file(file_path, namespace_name="ref_ns"):
    """References a Maya file into the current scene."""
    try:
        cmds.file(file_path, reference=True, namespace=namespace_name)
        print(f"Success: Referenced '{file_path}' with namespace '{namespace_name}'.")
    except RuntimeError as e:
        print(f"Error: Could not reference file. {e}")

def remove_reference(file_path):
    """Completely removes a referenced file and its associated nodes."""
    try:
        # Verify the file is referenced by attempting to query its reference node
        cmds.file(file_path, query=True, referenceNode=True)
        
        # If no error is thrown, the file is a valid reference and can be removed
        cmds.file(file_path, removeReference=True)
        print(f"Success: Completely removed reference for '{file_path}'.")
    except RuntimeError:
        print(f"Warning: '{file_path}' is not recognized as an active referenced file.")

# ==========================================
# Execution Examples
# ==========================================
# target_file_path = "C:/path/to/your/model.ma"
# reference_file(target_file_path, "character_01")
# remove_reference(target_file_path)

#=======================================================================================
# add epic arm guides in scene with biped module then run this
def updateEpicSpine():
    
    cmds.parentConstraint("body_C0_root|spine_C0_root", "guide1|spine_C0_root", mo = 0)
    cmds.scaleConstraint("body_C0_root|spine_C0_root", "guide1|spine_C0_root", mo = 0)

    cmds.delete("spine_C0_root_parentConstraint1", "spine_C0_root_scaleConstraint1")

    cmds.parent('body_C0_root|spine_C0_root', w=True)
    cmds.parent('guide1|spine_C0_root', 'body_C0_root')


    cmds.pointConstraint("CC_Base_Waist", "spine_C0_spineBase",  mo = 0)
    cmds.delete("spine_C0_spineBase_pointConstraint1")
    cmds.pointConstraint("CC_Base_Spine01", "spine_C0_tan0",  mo = 0)
    cmds.delete("spine_C0_tan0_pointConstraint1")
    cmds.pointConstraint("CC_Base_Spine02", "spine_C0_spineTop",  mo = 0)
    cmds.delete("spine_C0_spineTop_pointConstraint1")
    cmds.pointConstraint("CC_Base_Spine01", "spine_C0_tan1",  mo = 0)
    cmds.delete("spine_C0_tan1_pointConstraint1")

    cmds.setAttr("spine_C0_chest.translateZ", 0)
    cmds.setAttr("spine_C0_chest.translateY", 0)
    cmds.setAttr("spine_C0_tan1.translateY", -0.108)
    cmds.setAttr("spine_C0_tan1.translateX", -0.861)
    cmds.setAttr("spine_C0_tan1.rotateZ", 4.706)
    cmds.setAttr("spine_C0_tan0.translateX", 0.691)
    cmds.setAttr("spine_C0_tan0.translateY", 0.012)
    cmds.setAttr("spine_C0_tan0.translateZ", -0.001)
    cmds.setAttr("spine_C0_tan0.rotateZ", 5.862)

    cmds.parent('shoulder_R0_root', 'neck_C0_root', 'shoulder_L0_root', 'spine_C0_chest')
    cmds.parent('leg_L0_root', 'leg_R0_root', 'body_C0_root|spine_C0_root')
    cmds.delete("|spine_C0_root", "guide1")

    #setting
    cmds.setAttr("spine_C0_root.ui_host", "spineUI_C0_root", type="string")
    cmds.setAttr("leg_L0_root.extraTweak", 1)
    cmds.setAttr("arm_L0_root.ikTR", 0)
    cmds.setAttr("arm_L0_root.mirrorIK", 1)
    cmds.setAttr("arm_L0_root.extraTweak", 1)
    cmds.setAttr("leg_R0_root.extraTweak", 1)
    cmds.setAttr("arm_R0_root.ikTR", 0)
    cmds.setAttr("arm_R0_root.mirrorIK", 1)
    cmds.setAttr("arm_R0_root.extraTweak", 1)


#=======================================================================================

def space_switch(target, drivers, attr_name="spaceSwitch", include_local=True):
    # 1. Get current parent of target control to preserve hierarchy
    orig_parent = cmds.listRelatives(target, parent=True)
    orig_parent = orig_parent[0] if orig_parent else None

    # 2. Always create a new dedicated offset group for space switching
    space_grp = cmds.group(em=True, name=f"{target}_space_grp")
    cmds.matchTransform(space_grp, target)

    # Insert the new group above target in the hierarchy
    if orig_parent:
        cmds.parent(space_grp, orig_parent)
    cmds.parent(target, space_grp)

    # 3. Setup spaces list including default 'Local' option
    spaces = (["Local"] if include_local else []) + drivers

    # 4. Add Enum attribute to target control
    if not cmds.attributeQuery(attr_name, node=target, exists=True):
        cmds.addAttr(target, ln=attr_name, at="enum", en=":".join(spaces), k=True)

    # 5. Create parent constraint ON THE NEW SPACE GROUP
    constraint = cmds.orientConstraint(drivers, space_grp, mo=True)[0]
    weights = cmds.orientConstraint(constraint, q=True, wal=True)

    # 6. Connect Enum to constraint weights via Set Driven Keys
    for i, driver in enumerate(drivers):
        weight_attr = f"{constraint}.{weights[i]}"
        active_idx = i + 1 if include_local else i
        
        for idx in range(len(spaces)):
            cmds.setAttr(f"{target}.{attr_name}", idx)
            cmds.setAttr(weight_attr, 1.0 if idx == active_idx else 0.0)
            cmds.setDrivenKeyframe(weight_attr, cd=f"{target}.{attr_name}")

    cmds.setAttr(f"{target}.{attr_name}", 0)


#==============================================================================================================

def switchFix():

    # --- Left Arm ---
    cmds.parent("armUI_L0_root", "arm_L0_wrist")
    cmds.setAttr("armUI_L0_root.rotateZ", 0)
    cmds.setAttr("armUI_L0_root.translateX", 0)
    cmds.setAttr("armUI_L0_root.translateY", 0)
    cmds.setAttr("armUI_L0_root.translateZ", 0)
    cmds.setAttr("armUI_L0_root.rotateX", 0)
    cmds.setAttr("armUI_L0_root.rotateY", 0)
    cmds.setAttr("armUI_L0_root.translateY", 1.5)

    # --- Right Arm ---
    cmds.parent("armUI_R0_root", "arm_R0_wrist")
    cmds.setAttr("armUI_R0_root.rotateZ", 0)
    cmds.setAttr("armUI_R0_root.translateX", 0)
    cmds.setAttr("armUI_R0_root.translateY", 0)
    cmds.setAttr("armUI_R0_root.translateZ", 0)
    cmds.setAttr("armUI_R0_root.rotateX", 0)
    cmds.setAttr("armUI_R0_root.rotateY", 0)
    cmds.setAttr("armUI_R0_root.translateY", 1.5)

    # --- Left Leg ---
    cmds.parent("legUI_L0_root", "leg_L0_eff")
    cmds.setAttr("legUI_L0_root.rotateZ", 0)
    cmds.setAttr("legUI_L0_root.translateX", 0)
    cmds.setAttr("legUI_L0_root.translateY", 0)
    cmds.setAttr("legUI_L0_root.translateZ", 0)
    cmds.setAttr("legUI_L0_root.rotateX", 0)
    cmds.setAttr("legUI_L0_root.rotateY", 0)
    cmds.setAttr("legUI_L0_root.translateZ", -1.5)
    cmds.setAttr("legUI_L0_root.translateX", -2.133)
    # --- Right Leg ---
    cmds.parent("legUI_R0_root", "leg_R0_eff")
    cmds.setAttr("legUI_R0_root.rotateZ", 0)
    cmds.setAttr("legUI_R0_root.translateX", 0)
    cmds.setAttr("legUI_R0_root.translateY", 0)
    cmds.setAttr("legUI_R0_root.translateZ", 0)
    cmds.setAttr("legUI_R0_root.rotateX", 0)
    cmds.setAttr("legUI_R0_root.rotateY", 0)
    cmds.setAttr("legUI_R0_root.translateZ", -1.5)
    cmds.setAttr("legUI_R0_root.translateX", -2.133)

    # --- Spine ---
    cmds.parent("spineUI_C0_root", "body_C0_root")
    cmds.setAttr("spineUI_C0_root.rotateZ", 0)
    cmds.setAttr("spineUI_C0_root.translateX", 0)
    cmds.setAttr("spineUI_C0_root.translateY", 0)
    cmds.setAttr("spineUI_C0_root.translateZ", 0)
    cmds.setAttr("spineUI_C0_root.rotateX", 0)
    cmds.setAttr("spineUI_C0_root.rotateY", 0)
    cmds.setAttr("spineUI_C0_root.translateZ", -2)

    # --- Face ---
    cmds.parent("faceUI_C0_root", "neck_C0_eff")
    cmds.setAttr("faceUI_C0_root.rotateZ", 0)
    cmds.setAttr("faceUI_C0_root.translateX", 0)
    cmds.setAttr("faceUI_C0_root.translateY", 0)
    cmds.setAttr("faceUI_C0_root.translateZ", 0)
    cmds.setAttr("faceUI_C0_root.rotateX", 0)
    cmds.setAttr("faceUI_C0_root.rotateY", 0)
    cmds.setAttr("faceUI_C0_root.translateY", 3)

    # --- Eyes Look ---
    cmds.setAttr("eyeslook_C0_root.translateX", -4.959)
    cmds.setAttr("eyeslook_C0_root.translateY", 1.329)

    # --- Neck ---
    cmds.setAttr("neck_C0_root.translateZ", 0)
#   cmds.setAttr("spine_C0_eff|neck_C0_root.translateZ", 0)  # old swithc setup for defualt Mgear spine

    cmds.setAttr("neck_C0_neck.translateZ", 0)
    cmds.setAttr("neck_C0_tan0.translateZ", 0)
    cmds.setAttr("neck_C0_neck_crv.translateZ", 0)
    cmds.setAttr("neck_C0_head.translateZ", 0)
    cmds.setAttr("neck_C0_tan1.translateZ", 0)
    cmds.setAttr("neck_C0_head_crv.translateZ", 0)
    cmds.setAttr("neck_C0_tan0.translateZ", 0)
    cmds.setAttr("neck_C0_head.translateZ", 0)
    cmds.setAttr("neck_C0_eff.translateZ", 0)
    cmds.setAttr("neck_C0_head|mouth_C0_root.translateZ", 0)



    # Select the objects
    cmds.select([
        'foot_R0_outpivot', 
        'foot_R0_heel', 
        'foot_R0_inpivot', 
        'foot_L0_inpivot', 
        'foot_L0_heel', 
        'foot_L0_outpivot'
    ], replace=True)

    # Move the selection
    cmds.move(0, 0.0767615, 0, relative=True, objectSpace=True, worldSpaceDistance=True)
    cmds.select(d=1)





    #L-------------------------------------------------------

    cmds.parent("finger_L3_root", w = True)
    cmds.parent("finger_L2_root", w = True)
    cmds.parent("finger_L1_root", w = True)
    cmds.parent("finger_L0_root", w = True)
    cmds.parent("thumbRoll_L0_root", w = True)

    cmds.parentConstraint("meta_L0_root1", "meta_L0_root", mo=False)
    cmds.parentConstraint("meta_L0_0_loc1", "meta_L0_0_loc", mo=False)
    cmds.parentConstraint("meta_L0_1_loc1", "meta_L0_1_loc", mo=False)
    cmds.parentConstraint("meta_L0_2_loc1", "meta_L0_2_loc", mo=False)

    cmds.delete("meta_L0_root_parentConstraint1")
    cmds.delete("meta_L0_0_loc_parentConstraint1")
    cmds.delete("meta_L0_1_loc_parentConstraint1")
    cmds.delete("meta_L0_2_loc_parentConstraint1")

    cmds.parent("finger_L3_root", "meta_L0_2_loc")
    cmds.parent("finger_L2_root", "meta_L0_1_loc")
    cmds.parent("finger_L1_root", "meta_L0_0_loc")
    cmds.parent("finger_L0_root", "meta_L0_root")
    cmds.parent("thumb_L0_root", "meta_L0_root")
    cmds.delete("thumbRoll_L0_root")


    cmds.setAttr("meta_L0_root.metaCtl", 1 )


    #R-------------------------------------------------------

    cmds.parent("finger_R3_root", w = True)
    cmds.parent("finger_R2_root", w = True)
    cmds.parent("finger_R1_root", w = True)
    cmds.parent("finger_R0_root", w = True)
    cmds.parent("thumbRoll_R0_root", w = True)

    cmds.parentConstraint("meta_R0_root1", "meta_R0_root", mo=False)
    cmds.parentConstraint("meta_R0_0_loc1", "meta_R0_0_loc", mo=False)
    cmds.parentConstraint("meta_R0_1_loc1", "meta_R0_1_loc", mo=False)
    cmds.parentConstraint("meta_R0_2_loc1", "meta_R0_2_loc", mo=False)

    cmds.delete("meta_R0_root_parentConstraint1")
    cmds.delete("meta_R0_0_loc_parentConstraint1")
    cmds.delete("meta_R0_1_loc_parentConstraint1")
    cmds.delete("meta_R0_2_loc_parentConstraint1")

    cmds.parent("finger_R3_root", "meta_R0_2_loc")
    cmds.parent("finger_R2_root", "meta_R0_1_loc")
    cmds.parent("finger_R1_root", "meta_R0_0_loc")
    cmds.parent("finger_R0_root", "meta_R0_root")
    cmds.parent("thumb_R0_root", "meta_R0_root")
    cmds.delete("thumbRoll_R0_root")

    cmds.setAttr("meta_R0_root.metaCtl", 1 )


    #-----------------------------------------------------L_foot_guide_fix

    cmds.parent("arm_L0_eff", "armUI_L0_root", w=True)
    cmds.orientConstraint("CC_Base_L_Hand", "arm_L0_wrist", skip=["x", "z"], maintainOffset=False, weight=1)
    cmds.delete("arm_L0_wrist_orientConstraint1")
    cmds.parent("arm_L0_eff", "armUI_L0_root", "arm_L0_wrist")


    cmds.parent("arm_R0_eff", "armUI_R0_root", w=True)
    cmds.orientConstraint("CC_Base_R_Hand", "arm_R0_wrist", skip=["x", "z"], maintainOffset=False, weight=1)
    cmds.delete("arm_R0_wrist_orientConstraint1")
    cmds.parent("arm_R0_eff", "armUI_R0_root", "arm_R0_wrist")


    def snap(obj, axis='Y'):
        a = 'XYZ'.index(axis.upper())
        p = cmds.xform(obj, q=True, ws=True, t=True)
        p[a] = round(p[a])
        cmds.xform(obj, ws=True, t=p)

    snap('foot_L0_heel', 'Y')
    snap('foot_L0_inpivot', 'Y')
    snap('foot_L0_outpivot', 'Y')

    cmds.setAttr("foot_L0_0_loc.rotateZ", 0)
    cmds.setAttr("foot_L0_0_loc.rotateX", 0)
    cmds.setAttr("foot_L0_0_loc.rotateY", 0)

    cmds.setAttr("foot_L0_1_loc.rotateZ", 0)
    cmds.setAttr("foot_L0_1_loc.rotateX", 0)
    cmds.setAttr("foot_L0_1_loc.rotateY", 0)
    cmds.setAttr("foot_L0_1_loc.translateZ", 0)
    cmds.setAttr("foot_L0_1_loc.translateY", 0)

    cmds.setAttr("foot_L0_2_loc.translateZ", 0)
    cmds.setAttr("foot_L0_2_loc.translateY", 0)
    cmds.setAttr("foot_L0_2_loc.rotateZ", 0)
    cmds.setAttr("foot_L0_2_loc.rotateX", 0)

    cmds.setAttr("foot_L0_1_loc.translateX", 0)


    cmds.select("foot_L0_2_loc", r=True)
    cmds.move(0, 0, 0.0818673, r=True, os=True, wd=True)
    #mel.eval("SnapToPointRelease;")
    #mel.eval("dR_enterForSnap;")

    cmds.parent("foot_L0_2_loc", w = True)
    cmds.setAttr("foot_L0_1_loc.translateX", 0.02)
    cmds.parent("foot_L0_2_loc", "foot_L0_1_loc")

    cmds.select(clear=True)


    cmds.parent("meta_L0_root" , w =True)
    cmds.setAttr("arm_L0_eff.rotateZ", 0)
    cmds.setAttr("arm_L0_eff.rotateX", 0)
    cmds.setAttr("arm_L0_eff.rotateY", 0)
    cmds.setAttr("arm_L0_eff.translateZ", 0)
    cmds.parent("meta_L0_root","arm_L0_eff")




    #-----------------------------------------------------R_foot_guide_fix

    snap('foot_R0_heel', 'Y')
    snap('foot_R0_inpivot', 'Y')
    snap('foot_R0_outpivot', 'Y')

    cmds.setAttr("foot_R0_0_loc.rotateZ", 0)
    cmds.setAttr("foot_R0_0_loc.rotateX", 0)
    cmds.setAttr("foot_R0_0_loc.rotateY", 0)

    cmds.setAttr("foot_R0_1_loc.rotateZ", 0)
    cmds.setAttr("foot_R0_1_loc.rotateX", 0)
    cmds.setAttr("foot_R0_1_loc.rotateY", 0)
    cmds.setAttr("foot_R0_1_loc.translateZ", 0)
    cmds.setAttr("foot_R0_1_loc.translateY", 0)

    cmds.setAttr("foot_R0_2_loc.translateZ", 0)
    cmds.setAttr("foot_R0_2_loc.translateY", 0)
    cmds.setAttr("foot_R0_2_loc.rotateZ", 0)
    cmds.setAttr("foot_R0_2_loc.rotateX", 0)

    cmds.setAttr("foot_R0_1_loc.translateX", 0)

    cmds.select("foot_R0_2_loc", r=True)
    cmds.move(0, 0, 0.0818673, r=True, os=True, wd=True)
    mel.eval("SnapToPointRelease;")
    mel.eval("dR_enterForSnap;")


    cmds.parent("foot_R0_2_loc", w = True)
    cmds.setAttr("foot_R0_1_loc.translateX", 0.02)
    cmds.parent("foot_R0_2_loc", "foot_R0_1_loc")


    cmds.select(clear=True)


    cmds.parent("meta_R0_root" , w =True)
    cmds.setAttr("arm_R0_eff.rotateZ", 0)
    cmds.setAttr("arm_R0_eff.rotateX", 0)
    cmds.setAttr("arm_R0_eff.rotateY", 0)
    cmds.setAttr("arm_R0_eff.translateZ", 0)
    cmds.parent("meta_R0_root","arm_R0_eff")
    



    #   SPACE_SWITCH
    cmds.setAttr("shoulder_L0_tip|arm_L0_root.ikrefarray", "shoulder_L0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("shoulder_L0_tip|arm_L0_root.upvrefarray", "shoulder_L0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("shoulder_L0_tip|arm_L0_root.pinrefarray", "shoulder_L0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|shoulder_L0_root.refArray", "shoulder_L0_root,spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.headrefarray", "spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.ikrefarray", "spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.ui_host", "neck_C0_eff|faceUI_C0_root", type="string")
    cmds.setAttr("faceUI_C0_root.ikrefarray", "local_C0_root,spine_C0_chest,body_C0_root,spine_C0_root,global_C0_root,spine_C0_eff", type="string")

    cmds.setAttr("shoulder_R0_tip|arm_R0_root.ikrefarray", "shoulder_R0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("shoulder_R0_tip|arm_R0_root.upvrefarray", "shoulder_R0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("shoulder_R0_tip|arm_R0_root.pinrefarray", "shoulder_R0_tip,spine_C0_chest,spine_C0_root,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|shoulder_R0_root.refArray", "shoulder_R0_root,spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.headrefarray", "spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.ikrefarray", "spine_C0_chest,body_C0_root,local_C0_root,global_C0_root", type="string")
    cmds.setAttr("spine_C0_chest|neck_C0_root.ui_host", "neck_C0_eff|faceUI_C0_root", type="string")
    cmds.setAttr("faceUI_C0_root.ikrefarray", "local_C0_root,spine_C0_chest,body_C0_root,spine_C0_root,global_C0_root,spine_C0_eff", type="string")

    cmds.setAttr("foot_L0_root.rollAngle", -30)
    cmds.setAttr("foot_L0_root.rollAngle", -30)



    def align_and_offset_finger_guides(sides=('L', 'R')):
        """
        Aligns mGear guide locators to Character Creator (CC3/CC4) finger joints.
        Works for both Left and Right hands using a single parentConstraint method.
        
        :param sides: Tuple or list of sides to process, e.g., ('L', 'R') or ('L',)
        """
        cmds.undoInfo(openChunk=True)
        
        try:
            for side in sides:
                print(f"\n================ Processing Side: {side} ================")
                
                # Direct 1:1 mapping using CC4 joint positions
                guide_targets = [
                    # --- Index Finger (L0/R0) ---
                    (f"CC_Base_{side}_Index1", f"finger_{side}0_root"),
                    (f"CC_Base_{side}_Index2", f"finger_{side}0_0_loc"),
                    (f"CC_Base_{side}_Index3", f"finger_{side}0_1_loc"),
                    (f"CC_Base_{side}_Index4", f"finger_{side}0_2_loc"),
                    
                    # --- Middle Finger (L1/R1) ---
                    (f"CC_Base_{side}_Mid1",   f"finger_{side}1_root"),
                    (f"CC_Base_{side}_Mid2",   f"finger_{side}1_0_loc"),
                    (f"CC_Base_{side}_Mid3",   f"finger_{side}1_1_loc"),
                    (f"CC_Base_{side}_Mid4",   f"finger_{side}1_2_loc"),
                    
                    # --- Ring Finger (L2/R2) ---
                    (f"CC_Base_{side}_Ring1",  f"finger_{side}2_root"),
                    (f"CC_Base_{side}_Ring2",  f"finger_{side}2_0_loc"),
                    (f"CC_Base_{side}_Ring3",  f"finger_{side}2_1_loc"),
                    (f"CC_Base_{side}_Ring4",  f"finger_{side}2_2_loc"),
                    
                    # --- Pinky Finger (L3/R3) ---
                    (f"CC_Base_{side}_Pinky1", f"finger_{side}3_root"),
                    (f"CC_Base_{side}_Pinky2", f"finger_{side}3_0_loc"),
                    (f"CC_Base_{side}_Pinky3", f"finger_{side}3_1_loc"),
                    (f"CC_Base_{side}_Pinky4", f"finger_{side}3_2_loc"),

                    # --- Thumb (L0/R0) ---
                    (f"CC_Base_{side}_Thumb1", f"thumb_{side}0_root"),
                    (f"CC_Base_{side}_Thumb2", f"thumb_{side}0_0_loc"),
                    (f"CC_Base_{side}_Thumb3", f"thumb_{side}0_1_loc"),
                    (f"CC_Base_{side}_Thumb4", f"thumb_{side}0_2_loc"),
                ]

                # ---------------------------------------------------------
                # Single-Step Alignment via Temporary Parent Constraints
                # ---------------------------------------------------------
                print(f"--- [{side}] Starting Orientation & Position Constraints ---")
                aligned_count = 0
                
                for target, guide in guide_targets:
                    if cmds.objExists(target) and cmds.objExists(guide):
                        constraint = cmds.parentConstraint(target, guide, maintainOffset=False, weight=1)[0]
                        cmds.delete(constraint)
                        aligned_count += 1
                        print(f"Aligned and cleaned: {target} -> {guide}")
                    else:
                        cmds.warning(f"Skipped: Could not find '{target}' or '{guide}' in scene.")

                print(f"--- [{side}] Successfully aligned {aligned_count}/{len(guide_targets)} guides ---")

            print("\nFinger guide alignment complete for all requested sides!")

        finally:
            cmds.undoInfo(closeChunk=True)


    # Execute
    align_and_offset_finger_guides(sides=('L', 'R'))




    cmds.setAttr("finger_L0_root.mode", 2)
    cmds.setAttr("finger_L1_root.mode", 2)
    cmds.setAttr("finger_L2_root.mode", 2)
    cmds.setAttr("finger_L3_root.mode", 2)
    cmds.setAttr("thumb_L0_root.mode", 2)

    cmds.setAttr("finger_R0_root.mode", 2)
    cmds.setAttr("finger_R1_root.mode", 2)
    cmds.setAttr("finger_R2_root.mode", 2)
    cmds.setAttr("finger_R3_root.mode", 2)
    cmds.setAttr("thumb_R0_root.mode", 2)

    cmds.setAttr('finger_L0_root.ui_host', 'armUI_L0_root', type='string')
    cmds.setAttr('finger_L1_root.ui_host', 'armUI_L0_root', type='string')
    cmds.setAttr('finger_L2_root.ui_host', 'armUI_L0_root', type='string')
    cmds.setAttr('finger_L3_root.ui_host', 'armUI_L0_root', type='string')
    cmds.setAttr('thumb_L0_root.ui_host', 'armUI_L0_root', type='string')

    cmds.setAttr('finger_R0_root.ui_host', 'armUI_R0_root', type='string')
    cmds.setAttr('finger_R1_root.ui_host', 'armUI_R0_root', type='string')
    cmds.setAttr('finger_R2_root.ui_host', 'armUI_R0_root', type='string')
    cmds.setAttr('finger_R3_root.ui_host', 'armUI_R0_root', type='string')
    cmds.setAttr('thumb_R0_root.ui_host', 'armUI_R0_root', type='string')


    cmds.setAttr('thumb_R0_blade.bladeRollOffset', 180)
    cmds.setAttr('finger_R0_blade.bladeRollOffset', 180)
    cmds.setAttr('finger_R1_blade.bladeRollOffset', 180)
    cmds.setAttr('finger_R2_blade.bladeRollOffset', 180)
    cmds.setAttr('finger_R3_blade.bladeRollOffset', 180)


#------------------------------------------match fingers

    # Base mapping for Left Side: Target (CC Joint) -> Driven (Control)
    base_map_L = {
        # Index
        "CC_Base_L_Index1": "finger_L0_root",
        "CC_Base_L_Index2": "finger_L0_0_loc",
        "CC_Base_L_Index3": "finger_L0_1_loc",
        "CC_Base_L_Index4": "finger_L0_2_loc",
        # Middle
        "CC_Base_L_Mid1": "finger_L1_root",
        "CC_Base_L_Mid2": "finger_L1_0_loc",
        "CC_Base_L_Mid3": "finger_L1_1_loc",
        "CC_Base_L_Mid4": "finger_L1_2_loc",
        # Ring
        "CC_Base_L_Ring1": "finger_L2_root",
        "CC_Base_L_Ring2": "finger_L2_0_loc",
        "CC_Base_L_Ring3": "finger_L2_1_loc",
        "CC_Base_L_Ring4": "finger_L2_2_loc",
        # Pinky
        "CC_Base_L_Pinky1": "finger_L3_root",
        "CC_Base_L_Pinky2": "finger_L3_0_loc",
        "CC_Base_L_Pinky3": "finger_L3_1_loc",
        "CC_Base_L_Pinky4": "finger_L3_2_loc",
        # Thumb
        "CC_Base_L_Thumb1": "thumb_L0_root",
        "CC_Base_L_Thumb2": "thumb_L0_0_loc",
        "CC_Base_L_Thumb3": "thumb_L0_1_loc",
        "CC_Base_L_Thumb4": "thumb_L0_2_loc",
    }


    def get_side_mapping(base_dict, side="L"):
        """Generates joint map for given side ('L' or 'R')."""
        if side.upper() == "L":
            return base_dict

        r_dict = {}
        for target, driven in base_dict.items():
            # Replace CC side syntax (_L_) and loc side syntax (_L)
            r_target = target.replace("_L_", "_R_")
            r_driven = driven.replace("_L", "_R")
            r_dict[r_target] = r_driven

        return r_dict


    def match_controls_to_joints(side="BOTH"):
        """Snaps controls to CC joints and deletes parent constraints.

        side: 'L', 'R', or 'BOTH'
        """
        mappings_to_process = []

        if side.upper() in ["L", "BOTH"]:
            mappings_to_process.append(get_side_mapping(base_map_L, "L"))
        if side.upper() in ["R", "BOTH"]:
            mappings_to_process.append(get_side_mapping(base_map_L, "R"))

        matched_count = 0
        total_pairs = 0

        for mapping in mappings_to_process:
            total_pairs += len(mapping)
            for target, driven in mapping.items():
                if cmds.objExists(target) and cmds.objExists(driven):
                    constraint = cmds.parentConstraint(
                        target, driven, maintainOffset=False
                    )
                    cmds.delete(constraint)
                    matched_count += 1
                else:
                    missing = []
                    if not cmds.objExists(target):
                        missing.append(target)
                    if not cmds.objExists(driven):
                        missing.append(driven)
                    cmds.warning(
                        "Skipping pair. Missing object(s): {}".format(
                            ", ".join(missing)
                        )
                    )

        print(
            "Successfully snap-matched and cleared constraints for {}/{} pairs.".format(
                matched_count, total_pairs
            )
        )


    # --- EXECUTIONS ---
    # Process Left Side only:   match_controls_to_joints("L")
    # Process Right Side only:  match_controls_to_joints("R")
    # Process Both Sides:       match_controls_to_joints("BOTH")

    match_controls_to_joints("BOTH")








    #Tongue_Fix ----------------------------------------------------------------

    cmds.setAttr("tongue_C0_root.rotateX", -90)
    cmds.setAttr("tongue_C0_root.rotateY", -62.3)
    cmds.setAttr("tongue_C0_root.rotateZ", 90)



    def snap(source, target):
        cmds.xform(source, ws=True, matrix=cmds.xform(target, q=True, ws=True, matrix=True))

    # Usage:
    snap("tongue_C0_1_loc", "CC_Base_Tongue02")
    snap("tongue_C0_2_loc", "CC_Base_Tongue03")
    snap("tongue_C0_3_loc", "CC_Base_Tongue03")

    val = cmds.getAttr("tongue_C0_2_loc.translateX")

    cmds.setAttr("tongue_C0_3_loc.translateX",val )



    #FootGuides_snap_to_grid ----------------------------------------------------------------



    def snap_to_grid(node, axis='Y', grid_size=1.0):
        axis = axis.upper()
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis, 1)
        
        # Get current world space translation
        pos = cmds.xform(node, query=True, worldSpace=True, translation=True)
        
        # Snap specified axis to the nearest grid line
        pos[axis_idx] = round(pos[axis_idx] / grid_size) * grid_size
        
        # Apply updated position back to node
        cmds.xform(node, worldSpace=True, translation=pos)

    # Usage examples:         # Snaps Y axis by default
    snap_to_grid("foot_L0_heel", axis='Y')
    snap_to_grid("foot_R0_heel", axis='Y')

    snap_to_grid("foot_L0_outpivot", axis='Y')
    snap_to_grid("foot_R0_outpivot", axis='Y')

    snap_to_grid("foot_L0_inpivot", axis='Y')
    snap_to_grid("foot_R0_inpivot", axis='Y')

    snap_to_grid("foot_L0_2_loc", axis='Y')
    snap_to_grid("foot_R0_2_loc", axis='Y')




#==============================================================================

def EpicSpineConstraint():

    # Define pairing: ( [List of Drivers], "Driven Object" )
    constraint_pairs = [
        (["spine_C0_pelvis_jnt"], "CC_Base_Pelvis"),
        (["spine_C0_pelvis_jnt"], "CC_Base_Hip"),
        (["spine_C0_spine_03_jnt", "spine_C0_spine_02_jnt"], "CC_Base_Spine01"), # Two drivers
        (["spine_C0_spine_01_jnt"], "CC_Base_Waist"),
        (["spine_C0_spine_04_jnt"], "CC_Base_Spine02"),
        (["spine_C0_spine_04_jnt"], "CC_Base_L_RibsTwist"),
        (["spine_C0_spine_04_jnt"], "CC_Base_L_Breast"),
        (["spine_C0_spine_04_jnt"], "CC_Base_R_RibsTwist"),
        (["spine_C0_spine_04_jnt"], "CC_Base_R_Breast")
    ]

    # Apply reverse parent constraints
    for drivers, driven in constraint_pairs:
        # Validate existence of ALL drivers and the driven object
        if all(cmds.objExists(driver) for driver in drivers) and cmds.objExists(driven):
            # The * operator unpacks the driver list so multiple drivers can be passed
            cmds.parentConstraint(*drivers, driven, maintainOffset=True)
            print(f"Success: {drivers} -> {driven}")
        else:
            print(f"Warning: Missing objects for {driven}. Skipping constraint.")
    
#==============================================================================

def auto_skincluster_top_all_meshes():
    meshes = cmds.ls(type="mesh", long=True, noIntermediate=True) or []
    
    # Define the hierarchical evaluation order
    priority = ["skinCluster", "deltaMush", "blendShape"]

    # Helper function to assign a priority index based on node type
    def get_priority(node):
        n_type = cmds.nodeType(node)
        return priority.index(n_type) if n_type in priority else len(priority)

    for shape in meshes:
        hist = cmds.listHistory(shape, pruneDagObjects=True) or []

        skins = [
            n for n in hist
            if cmds.nodeType(n) == "skinCluster" and n.startswith("skinCluster")
        ]

        raw_deformers = [
            n for n in hist
            if cmds.nodeType(n) in [
                "skinCluster", "blendShape", "cluster", "ffd",
                "wire", "wrap", "deltaMush", "tension", "proximityWrap"
            ]
        ]

        if not raw_deformers:
            continue

        # Sort the collected deformers based on the defined priority list
        sorted_deformers = sorted(raw_deformers, key=get_priority)

        # Sequentially enforce the order using the original try/except core logic
        for i in range(len(sorted_deformers) - 1):
            for j in range(i + 1, len(sorted_deformers)):
                try:
                    cmds.reorderDeformers(sorted_deformers[i], sorted_deformers[j], shape)
                except:
                    pass

        if skins:
            print("Ordered to:", [cmds.nodeType(d) for d in sorted_deformers], "on", shape)

    print("Done. All deformers ordered by custom hierarchy.")

# auto_skincluster_top_all_meshes()

#  ==========================================================



def apply_delta_mush(meshes=None, iterations=10, step=0.5):
    """
    Applies a Delta Mush deformer to geometry and sets its smoothing values.
    """
    # Default to current selection if no meshes are provided
    if not meshes:
        meshes = cmds.ls(selection=True)
        
    if not meshes:
        cmds.warning("No meshes provided or selected.")
        return []

    deformers = []
    
    for mesh in meshes:
        # Apply the deformer
        mush_node = cmds.deltaMush(mesh, name=f"{mesh}_deltaMush")[0]
        
        # Set the editable attributes
        cmds.setAttr(f"{mush_node}.smoothingIterations", iterations)
        cmds.setAttr(f"{mush_node}.smoothingStep", step)
        
        deformers.append(mush_node)
        
    return deformers

# Execution Example 1: Apply to currently selected objects
# apply_delta_mush(iterations=20, step=0.75)

# Execution Example 2: Apply to specifically named objects
# apply_delta_mush(meshes=['geo_avadhoot_beard_lod_1'], iterations=20, step=0.5)

#==============================================================================================================


def rebindTweakFix():
    def rg_re_skin(meshes, exclude_meshes=None):
        """
        Re-skins specified meshes while keeping history, with an option to exclude specific meshes.
        Processes only valid mesh geometry that has an existing skin cluster.
        
        Args:
            meshes (str or list): The target mesh(es) or wildcards (e.g., "geo_*") to process.
            exclude_meshes (str or list, optional): Mesh(es) or wildcards to ignore.
        """
        # 1. Input formatting
        if isinstance(meshes, str):
            meshes = [meshes]
            
        if isinstance(exclude_meshes, str):
            exclude_meshes = [exclude_meshes]
        elif exclude_meshes is None:
            exclude_meshes = []

        # 2. Safely expand exclusion list to long names to avoid matching issues
        expanded_exclusions = []
        if exclude_meshes:
            expanded_exclusions = cmds.ls(exclude_meshes, long=True) or []

        # 3. Expand wildcards for target objects
        actual_nodes = cmds.ls(meshes, long=True) or []
        
        # Remove duplicates while preserving order
        actual_nodes = list(dict.fromkeys(actual_nodes))
        
        if not actual_nodes:
            cmds.error("No valid objects found matching the input.")
            return

        for node in actual_nodes:
            # Check exclusion list
            if node in expanded_exclusions:
                cmds.warning('Skipping "{}": Node is explicitly excluded.'.format(node))
                continue

            # 4. Verify that the node is (or contains) a polygon MESH
            mesh_shapes = cmds.ls(node, dag=True, type="mesh", noIntermediate=True, long=True)
            if not mesh_shapes:
                cmds.warning('Skipping "{}": Object is not a valid polygon mesh.'.format(node))
                continue
            
            # Take the primary mesh shape
            shape = mesh_shapes[0]

            # 5. Check if the mesh has an active skin cluster
            skin_cluster = mel.eval('findRelatedSkinCluster("{}")'.format(shape))
            if not skin_cluster:
                cmds.warning('Skipping "{}": Mesh has no skin cluster attached.'.format(node))
                continue

            # 6. Re-skin process
            joints = cmds.skinCluster(skin_cluster, query=True, influence=True)
            
            # Unbind skin while keeping geometry history intact
            cmds.skinCluster(shape, edit=True, unbindKeepHistory=True)
            
            # Clean up bind pose nodes associated with the unbind
            bind_poses = cmds.ls(type="dagPose") or []
            for pose in bind_poses:
                if cmds.attributeQuery("bindPose", node=pose, exists=True):
                    try:
                        cmds.delete(pose)
                    except Exception:
                        pass

            # Re-bind the skin using the gathered influence joints
            cmds.skinCluster(joints, shape)
            print('Successfully re-skinned "{}"'.format(node))
    
    # --- Usage Examples ---
    
    # Example 1: Exclude a single specific mesh
    
    cmds.setAttr( "world_ctl.scaleZ", 100)
    cmds.setAttr( "world_ctl.scaleX", 100)
    cmds.setAttr( "world_ctl.scaleY", 100)
    rg_re_skin("geo_*_cc_*_body_lod_*")
    
    cmds.setAttr( "world_ctl.scaleZ", 1)
    cmds.setAttr( "world_ctl.scaleX", 1)
    cmds.setAttr( "world_ctl.scaleY", 1)
    rg_re_skin("geo_*", exclude_meshes="*cc*")

#==============================================================================================================

def finalize_grouping_N_parent():
    
    cmds.setAttr("shoulder_R0_orbit_ctlShape.visibility", 0)
    cmds.setAttr("shoulder_L0_orbit_ctlShape.visibility", 0)
    
    #cmds.parent("*_lod_*Bas*", "others")
    cmds.parent( "cc_rig_grp", "rig", "rigging")


    cmds.setAttr("mouth_C0_liplow_npo.visibility", lock=False)
    cmds.setAttr("mouth_C0_liplow_npo.visibility", 0)

    cmds.setAttr("mouth_C0_lipup_npo.visibility", lock=False)
    cmds.setAttr("mouth_C0_lipup_npo.visibility", 0)

    cmds.disconnectAttr("foot_L0_root.blend", "foot_L0_bk1_ctlShape.visibility")
    cmds.setAttr("foot_L0_bk1_ctlShape.visibility", 0)

    cmds.disconnectAttr("foot_R0_root.blend", "foot_R0_bk1_ctlShape.visibility")
    cmds.setAttr("foot_R0_bk1_ctlShape.visibility", 0)

    cmds.disconnectAttr("foot_L0_root.blend", "foot_L0_bk1_ctlShape1.visibility")
    cmds.setAttr("foot_L0_bk1_ctlShape1.visibility", 0)

    cmds.disconnectAttr("foot_R0_root.blend", "foot_R0_bk1_ctlShape1.visibility")
    cmds.setAttr("foot_R0_bk1_ctlShape1.visibility", 0)

    cmds.setAttr("mouth_C0_jaw_ctl.visibility", lock=False)
    cmds.setAttr("mouth_C0_jaw_ctl.visibility", 0)

    cmds.setAttr("eye_R0_Over_ctl.visibility", lock=False)
    cmds.setAttr("eye_R0_Over_ctl.visibility", 0)

    cmds.setAttr("eye_R0_fk_ctl.visibility", lock=False)
    cmds.setAttr("eye_R0_fk_ctl.visibility", 0)

    cmds.setAttr("eye_L0_Over_ctl.visibility", lock=False)
    cmds.setAttr("eye_L0_Over_ctl.visibility", 0)

    cmds.setAttr("eye_L0_fk_ctl.visibility", lock=False)
    cmds.setAttr("eye_L0_fk_ctl.visibility", 0)

    cmds.setAttr("eyeslook_C0_ctl.visibility", lock=False)
    cmds.setAttr("eyeslook_C0_ctl.visibility", 0)

    cmds.setAttr("mouth_C0_teethup_ctl.visibility", lock=False)
    cmds.setAttr("mouth_C0_teethup_ctl.visibility", 0)

    cmds.setAttr("mouth_C0_teethlow_ctl.visibility", lock=False)
    cmds.setAttr("mouth_C0_teethlow_ctl.visibility", 0)

    cmds.setAttr("foot_L0_fk1_ctl.visibility", lock=False)
    cmds.setAttr("foot_L0_fk1_ctl.visibility", 0)

    cmds.setAttr("foot_R0_fk1_ctl.visibility", lock=False)
    cmds.setAttr("foot_R0_fk1_ctl.visibility", 0)

    cmds.scaleConstraint("neck_C0_head_jnt","GRP_faceGUI", mo = 1)
    
    cmds.setAttr("CTRL_faceGUIfollowHead.translateY", 1)

    #cmds.parent("spine_C0_tan1_npo", "spine_C0_ik1autoRot_lvl")
    cmds.setAttr("CC_Base_Spine01_parentConstraint1.spine_C0_spine_03_jntW0", 0.6)
    cmds.setAttr("CC_Base_Spine01_parentConstraint1.spine_C0_spine_02_jntW1", 0.4)

    #cmds.setAttr("teeth_bs.visibility", 0)
    cmds.setAttr("teeth_bs.v", lock=True)
    cmds.parent("teeth_bs", "others")
    cmds.parent("upper_teeth_jnt_grp", "lower_teeth_jnt_grp", "rig")
    
    rebindTweakFix()
    cmds.delete("rig_sets_grp", "rig_componentsRoots_grp", "rig_controllers_grp", "rig_deformers_grp", "rig_geo_grp")

    cmds.setAttr("armUI_L0_ctl.chain_blend", 0)
    cmds.setAttr("armUI_R0_ctl.chain_blend", 0)

    for ctl in cmds.ls('*ctl', '*CTL', type='transform'):
        ro = f"{ctl}.rotateOrder"
        if cmds.objExists(ro) and (cmds.getAttr(ro, k=True) or cmds.getAttr(ro, cb=True)):
            cmds.setAttr(ro, k=False, cb=True)


    def remove_unused_influences_all_meshes():
        """Finds all skinClusters in the scene and removes influences with zero weight."""
        skin_clusters = cmds.ls(type="skinCluster")

        if not skin_clusters:
            print("No skinClusters found in the scene.")
            return

        total_removed = 0

        for sc in skin_clusters:
            # Get all bound influences and influences with actual non-zero weight
            all_influences = cmds.skinCluster(sc, query=True, influence=True) or []
            weighted_influences = (
                cmds.skinCluster(sc, query=True, weightedInfluence=True) or []
            )

            # Identify unused influences
            unused_influences = [
                inf for inf in all_influences if inf not in weighted_influences
            ]

            if unused_influences:
                # Remove unused influences from the skinCluster
                cmds.skinCluster(sc, edit=True, removeInfluence=unused_influences)
                total_removed += len(unused_influences)
                print(
                    f"Removed {len(unused_influences)} unused influence(s) from '{sc}'."
                )

        print(f"Completed: Removed {total_removed} total unused influence(s).")


    # Execute script
    #remove_unused_influences_all_meshes()



    cmds.setAttr("local_C0_ctl.sx", lock=True)
    cmds.setAttr("global_C0_ctl.sx", lock=True)
    cmds.setAttr("world_ctl.sx", lock=True)
    cmds.setAttr("local_C0_ctl.sy", lock=True)
    cmds.setAttr("global_C0_ctl.sy", lock=True)
    cmds.setAttr("world_ctl.sy", lock=True)
    cmds.setAttr("local_C0_ctl.sz", lock=True)
    cmds.setAttr("global_C0_ctl.sz", lock=True)
    cmds.setAttr("world_ctl.sz", lock=True)
    cmds.setAttr("local_C0_ctl.sx", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("global_C0_ctl.sx", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("world_ctl.sx", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("local_C0_ctl.sy", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("global_C0_ctl.sy", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("world_ctl.sy", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("local_C0_ctl.sz", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("global_C0_ctl.sz", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("world_ctl.sz", lock=True, keyable=False, channelBox=False)
    cmds.setAttr("armUI_L0_ctl.arm_ikref", 5)
    cmds.setAttr("armUI_R0_ctl.arm_ikref", 5)

    


    cmds.setAttr("shoulder_R0_orbit_ctlShape.visibility", 0)
    cmds.setAttr("shoulder_L0_orbit_ctlShape.visibility", 0)

#==============================================================================================================


# ── the generic half of the old per-rig utils.py (KRT/rigutils/rig_lib.py) ──
from .rig_lib import *   # noqa: F401,F403
