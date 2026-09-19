import maya.cmds as cmds
import re
import sys
import importlib
import os

sys.path.append(r"P:/rigging_team/Pipeline_share/RigUtils")
import UniUtils
importlib.reload(UniUtils)
import wrapToBs
importlib.reload(wrapToBs)

# Priority list for fallback texture extensions
EXT_PRIORITY = [
    ".exr", ".tx", ".rstex", ".png", ".tga", ".tif", ".tiff",
    ".jpg", ".jpeg", ".bmp", ".hdr"
]

def _normalise_path(path):
    """Ensure consistent forward slashes for Maya file paths."""
    return path.replace("//", "/")

def _lookup_in_dir(directory, filename):
    """Find the best matching file within a specific directory."""
    if not os.path.isdir(directory):
        return None
        
    orig_stem, orig_ext = os.path.splitext(filename.lower())
    try:
        entries = os.listdir(directory)
    except OSError:
        return None

    # 1. Exact match (case-insensitive)
    for entry in entries:
        if entry.lower() == filename.lower():
            return "{}/{}".format(directory, entry)

    # Filter entries sharing the same base name (stem)
    stem_matches = [e for e in entries if os.path.splitext(e)[0].lower() == orig_stem]
    if not stem_matches:
        return None

    # 2. Same extension, different case
    for entry in stem_matches:
        if os.path.splitext(entry)[1].lower() == orig_ext:
            return "{}/{}".format(directory, entry)

    # 3. Ranked by extension priority
    ranked = {}
    for entry in stem_matches:
        ext = os.path.splitext(entry)[1].lower()
        if ext in EXT_PRIORITY:
            ranked[EXT_PRIORITY.index(ext)] = entry
    if ranked:
        return "{}/{}".format(directory, ranked[min(ranked)])

    # 4. First available match
    return "{}/{}".format(directory, stem_matches[0])

def repath_textures(new_dir):
    """Scan all file nodes and recursively search new_dir for missing textures."""
    new_dir = _normalise_path(new_dir)
    if not os.path.isdir(new_dir):
        cmds.warning("Directory not found: {}".format(new_dir))
        return

    file_nodes = cmds.ls(type="file") or []
    if not file_nodes:
        cmds.warning("No file texture nodes in scene.")
        return

    updated_count = 0
    cmds.undoInfo(openChunk=True, chunkName="RepathTextures")
    try:
        for node in file_nodes:
            raw_path = cmds.getAttr("{}.fileTextureName".format(node)) or ""
            orig_name = os.path.basename(_normalise_path(raw_path))

            found_full = None
            
            # Recursively walk through the new directory
            for walk_root, _, _ in os.walk(new_dir):
                walk_root_n = _normalise_path(walk_root)
                found_full = _lookup_in_dir(walk_root_n, orig_name)
                if found_full:
                    break # Stop searching once found

            if found_full:
                cmds.setAttr("{}.fileTextureName".format(node), found_full, type="string")
                
                # Regenerate UDIM preview if applicable
                if cmds.attributeQuery("uvTilingMode", node=node, exists=True):
                    if cmds.getAttr("{}.uvTilingMode".format(node)) != 0:
                        if cmds.attributeQuery("uvTileProxyQuality", node=node, exists=True):
                            cmds.setAttr("{}.uvTileProxyQuality".format(node), 2)
                        cmds.ogs(regenerateUVTilePreview=node)
                
                updated_count += 1
                print("// Repathed: {} -> {}".format(node, found_full))
            else:
                print("// Missing: Could not locate '{}' for node '{}'".format(orig_name, node))
    finally:
        cmds.undoInfo(closeChunk=True)

    print("// Repath complete — {}/{} textures updated.".format(updated_count, len(file_nodes)))

# ======================================================================
# EXECUTION
# Replace the path below with your target directory and run the script.
# ======================================================================
# repath_textures("C:/path/to/your/new/texture/folder")

#==========================================================================================

def organize_and_convert_lod(asset_name="char_gurudattatreya_a", delete_ai_lod=False):
    # Part 1: Gather and ensure top-level groups
    meshes = cmds.ls(type="mesh")
    if not meshes:
        return cmds.warning("No polygon objects found in the scene.")

    transforms = list(set(cmds.listRelatives(meshes, p=True, f=True)))
    to_group = [t for t in transforms if t.split("|")[-1] != asset_name and f"|{asset_name}|" not in t]

    top_grp = cmds.ls(asset_name, long=True)[0] if cmds.objExists(asset_name) else cmds.group(em=True, n=asset_name)
    for obj in to_group:
        try: cmds.parent(obj, top_grp)
        except: pass
    
    geo_grp_name = f"{asset_name}_geo"
    geo_grp = next((c for c in (cmds.listRelatives(top_grp, c=True, f=True) or []) if c.split("|")[-1] == geo_grp_name), None)
    if not geo_grp:
        geo_grp = cmds.group(em=True, n=geo_grp_name, p=top_grp)

    # Part 2: Parse and Sort LODs
    deleted_count = 0
    for mesh in cmds.listRelatives(top_grp, c=True, type="transform", f=True) or []:
        short_name = mesh.split("|")[-1]
        if short_name == geo_grp_name or not cmds.objExists(mesh): 
            continue

        # Handle AI LOD deletion
        if re.search(r"ai_lod", short_name, re.I) and delete_ai_lod:
            cmds.delete(mesh)
            deleted_count += 1
            continue

        # Match prefix/suffix or fallback to AI LOD naming patterns
        match = re.search(r"(\d+)_lod|_lod_(\d+)", short_name, re.I)
        if match:
            idx = match.group(1) or match.group(2)
            lod_name = f"{asset_name}_lod_{idx}"
        elif re.search(r"ai_lod", short_name, re.I):
            lod_name = f"{asset_name}_ai_lod"
        else:
            continue

        # Fixed: Changed invalid 'f' flag to 'l' (long) for cmds.ls
        tgt_grp = cmds.ls(f"{geo_grp}|{lod_name}", l=True) or [cmds.group(em=True, n=lod_name, p=geo_grp)]
        try: cmds.parent(mesh, tgt_grp[0])
        except Exception as e: cmds.warning(f"Could not parent {short_name}: {e}")

    # UI Feedback
    msg = f"LOD hierarchy generated successfully! {'(Deleted ' + str(deleted_count) + ' AI objects)' if delete_ai_lod and deleted_count else ''}"
    cmds.inViewMessage(amg=f"<hl>{msg}</hl>", pos="midCenter", fade=True)



#organize_and_convert_lod("char_gurudattatreya_a", delete_ai_lod=True)

#------------------------------------------------------------------------------




def organize_gurudattatreya_hierarchy():
    # Define the operations as tuples: (search_wildcard, new_group_name, parent_target)
    operations = [
        # Right Side
        (
            "geo_gurudattatreya_r*",
            "geo_gurudattatreya_r_grp",
            "char_gurudsattatreya_a_lod_2",
        ),
        (
            "geo_gurudattatreya_cc_r*",
            "geo_gurudattatreya_cc_r_grp",
            "geo_gurudattatreya_r_grp",
        ),
        # Front Side
        (
            "geo_gurudattatreya_front*",
            "geo_gurudattatreya_front_grp",
            "char_gurudsattatreya_a_lod_2",
        ),
        (
            "geo_gurudattatreya_cc_front*",
            "geo_gurudattatreya_cc_front_grp",
            "geo_gurudattatreya_front_grp",
        ),  # Parented under 'r_grp' per instructions
        # Left Side
        (
            "geo_gurudattatreya_l*",
            "geo_gurudattatreya_l_grp",
            "char_gurudsattatreya_a_lod_2",
        ),
        (
            "geo_gurudattatreya_cc_l*",
            "geo_gurudattatreya_cc_l_grp",
            "geo_gurudattatreya_l_grp",
        ),
    ]

    for wildcard, grp_name, parent_node in operations:
        # Find matching objects in the scene
        matching_objects = cmds.ls(wildcard, type="transform")

        if not matching_objects:
            print(f"Warning: No objects found matching {wildcard}. Skipping...")
            continue

        # Check if the group already exists; if not, create it with the matching objects
        if not cmds.objExists(grp_name):
            grp_name = cmds.group(matching_objects, name=grp_name)
        else:
            # If the group exists, just add the matching objects into it
            cmds.parent(matching_objects, grp_name)

        # Parent the group under the target node if the target exists
        if cmds.objExists(parent_node):
            # Check if it's already a child to prevent redundant parenting warnings
            current_parent = cmds.listRelatives(grp_name, parent=True)
            if not current_parent or current_parent[0] != parent_node:
                cmds.parent(grp_name, parent_node)
        else:
            print(
                f"Warning: Target parent '{parent_node}' does not exist. Group '{grp_name}' left in root."
            )

    print("Hierarchy organization complete!")


# Run the script
#organize_gurudattatreya_hierarchy()






#=======================================================================================================================


import maya.cmds as cmds

def cleanup_scene_nodes():
    """
    1. Pre-Execution Scene Cleanup
    Deletes specific unwanted nodes from the scene before running the layout logic.
    """
    target_node = "textureDeformerHandle1"
    if cmds.objExists(target_node):
        cmds.delete(target_node)
        print(f"[Cleanup] Successfully deleted: {target_node}")


def create_zero_group(name, parent_node=None):
    """
    2. Zero Group Creator
    Creates an empty group explicitly positioned with its pivot at world 0,0,0
    and parents it under a parent group if specified.
    """
    grp = cmds.group(empty=True, name=name)
    cmds.xform(grp, worldSpace=True, scalePivot=(0, 0, 0), rotatePivot=(0, 0, 0))
    
    if parent_node and cmds.objExists(parent_node):
        cmds.parent(grp, parent_node)
        
    return grp


def apply_transform_dict(target_node, transform_dict):
    """
    Helper function to safely apply a dictionary of attributes to a node.
    """
    if not cmds.objExists(target_node):
        print(f"[Warning] Targeted node does not exist for values: {target_node}")
        return
        
    for attr, value in transform_dict.items():
        try:
            cmds.setAttr(f"{target_node}.{attr}", value)
        except Exception as e:
            print(f"[Warning] Could not set attribute {attr} on {target_node}: {e}")


def process_rig_hierarchy(input_objects, group_name, dup_name_1, dup_name_2, transforms_config, visibility_targets):
    """
    3. Core Hierarchy Processing Engine
    Handles object processing, mesh isolation, strict grouping exclusion rules,
    hierarchy duplications, and customized attribute assignments.
    """
    valid_objects = [obj for obj in input_objects if cmds.objExists(obj)]
    if not valid_objects:
        cmds.error("None of the specified target objects exist in the scene.")
        return

    # Create primary main group container at origin
    main_group = create_zero_group(group_name)
    print(f"[Main Group] Created at origin: {main_group}")
    
    # Isolate all mesh shapes under the very first object in the list
    first_obj = valid_objects[0]
    mesh_shapes = cmds.listRelatives(first_obj, allDescendents=True, type="mesh", fullPath=True)
    
    mesh_sub_group = None
    mesh_sub_group_long = None
    
    if mesh_shapes:
        mesh_transforms = list(set(cmds.listRelatives(mesh_shapes, parent=True, fullPath=True)))
        mesh_group_name = f"{first_obj}_geo_grp"
        
        mesh_sub_group = create_zero_group(mesh_group_name, parent_node=main_group)
        cmds.parent(mesh_transforms, mesh_sub_group)
        mesh_sub_group_long = cmds.ls(mesh_sub_group, long=True)[0]
        print(f"[Mesh Isolation] Grouped geometry under: {mesh_sub_group}")
    else:
        print(f"[Mesh Isolation] No meshes found under '{first_obj}'. Skipping geometry sub-group step.")

    # Parent remaining high-level input elements into main_group safely
    for obj in valid_objects:
        if cmds.objExists(obj):
            current_parent = cmds.listRelatives(obj, parent=True, fullPath=True)
            if not current_parent or main_group not in current_parent[0]:
                obj_long = cmds.ls(obj, long=True)[0]
                if mesh_sub_group_long and obj_long.startswith(mesh_sub_group_long):
                    continue
                cmds.parent(obj, main_group)

    # Gather remaining contents to group them separately (Strictly Excluding the Geometry Group)
    all_children = cmds.listRelatives(main_group, children=True, fullPath=True) or []
    other_nodes = []
    
    for child in all_children:
        child_long = cmds.ls(child, long=True)[0]
        if mesh_sub_group_long and child_long == mesh_sub_group_long:
            continue
        other_nodes.append(child)
    
    # Group remaining items together
    rig_sub_group_name = f"{group_name}_rig_contents_grp"
    if len(other_nodes) >= 2:
        rig_sub_group = create_zero_group(rig_sub_group_name, parent_node=main_group)
        cmds.parent(other_nodes, rig_sub_group)
        print(f"[Rig Contents] Grouped secondary elements into: {rig_sub_group}")
    else:
        rig_sub_group = rig_sub_group_name

    # Apply scaling values to the primary rig contents group from config
    apply_transform_dict(rig_sub_group, transforms_config.get(rig_sub_group_name, {}))

    # -------------------------------------------------------------------------
    # DUPLICATION & DIRECT ATTRIBUTE SETTING
    # -------------------------------------------------------------------------
    
    # First Duplicate Execution
    dup1 = cmds.duplicate(main_group, renameChildren=True, upstreamNodes=True)
    dup1_renamed = cmds.rename(dup1[0], dup_name_1)
    cmds.xform(dup1_renamed, worldSpace=True, scalePivot=(0, 0, 0), rotatePivot=(0, 0, 0))
    print(f"[Duplicate Special] First copy completed: {dup1_renamed}")
    
    # Match the explicit name string generated by Maya's automatic rename process
    target_dup1_contents = f"{rig_sub_group_name}1"
    apply_transform_dict(target_dup1_contents, transforms_config.get(target_dup1_contents, {}))

    # Second Duplicate Execution
    dup2 = cmds.duplicate(main_group, renameChildren=True, upstreamNodes=True)
    dup2_renamed = cmds.rename(dup2[0], dup_name_2)
    cmds.xform(dup2_renamed, worldSpace=True, scalePivot=(0, 0, 0), rotatePivot=(0, 0, 0))
    print(f"[Duplicate Special] Second copy completed: {dup2_renamed}")
    
    # Match the explicit name string generated by Maya's automatic rename process
    target_dup2_contents = f"{rig_sub_group_name}2"
    apply_transform_dict(target_dup2_contents, transforms_config.get(target_dup2_contents, {}))

    # -------------------------------------------------------------------------
    # SCENE MESH VISIBILITY OPERATIONS
    # -------------------------------------------------------------------------
    for mesh in visibility_targets:
        if cmds.objExists(mesh):
            cmds.setAttr(f"{mesh}.visibility", False)
            print(f"[Visibility] Turned off visibility for: {mesh}")


def run_rig_setup_pipeline(input_objects=None, group_name="main_GRP", dup_name_1="dup_01_GRP", dup_name_2="dup_02_GRP", transforms_config=None, visibility_targets=None):
    """
    ===========================================================================
    4. MASTER PIPELINE FUNCTION
    ===========================================================================
    """
    print("--- STARTING RIG PIPELINE ---")
    
    cleanup_scene_nodes()
    
    if not input_objects:
        input_objects = cmds.ls(selection=True)
        if not input_objects:
            cmds.error("Pipeline Aborted: No target object inputs provided and nothing is selected.")
            return
    elif isinstance(input_objects, str):
        input_objects = [input_objects]

    if transforms_config is None: transforms_config = {}
    if visibility_targets is None: visibility_targets = []

    process_rig_hierarchy(
        input_objects=input_objects, 
        group_name=group_name, 
        dup_name_1=dup_name_1, 
        dup_name_2=dup_name_2,
        transforms_config=transforms_config,
        visibility_targets=visibility_targets
    )
    
    print("--- PIPELINE EXECUTION SUCCESSFUL ---")


# =============================================================================
# CHANGEABLE CONFIGURATION BLOCK (Matches your exact layout queries!)
# =============================================================================



#========================================================================================================



def replace_and_rename_mesh(rigged_mesh, unrigged_mesh):
    """
    Renames a rigged mesh using the name of an unrigged mesh,
    moves the rigged mesh into the unrigged mesh's exact hierarchy,
    and deletes the unrigged mesh.
    
    :param rigged_mesh: str, The current rigged mesh (Target)
    :param unrigged_mesh: str, The unrigged mesh with the correct name (Source)
    """
    # 1. Verify both meshes exist
    if not cmds.objExists(rigged_mesh):
        cmds.error("Rigged mesh '{0}' does not exist.".format(rigged_mesh))
        return
    if not cmds.objExists(unrigged_mesh):
        cmds.error("Unrigged mesh '{0}' does not exist.".format(unrigged_mesh))
        return

    # 2. Get the long path names to avoid issues with duplicate names in the scene
    rigged_long = cmds.ls(rigged_mesh, long=True)[0]
    unrigged_long = cmds.ls(unrigged_mesh, long=True)[0]

    # 3. Find the parent of the unrigged mesh to know its hierarchy
    unrigged_parent = cmds.listRelatives(unrigged_long, parent=True, fullPath=True)

    # 4. Extract the short target name from the unrigged mesh
    target_name = unrigged_long.split("|")[-1]

    # 5. Delete the unrigged mesh first to free up the name in that namespace/hierarchy
    cmds.delete(unrigged_long)

    # 6. Rename the rigged mesh to the target name
    # Note: Maya might append a '1' if the name is still conflicting globally, 
    # but freeing it above usually prevents this.
    renamed_rigged = cmds.rename(rigged_long, target_name)

    # 7. Match the hierarchy if the unrigged mesh had a parent
    if unrigged_parent:
        cmds.parent(renamed_rigged, unrigged_parent[0])
        print("Successfully renamed and moved '{0}' to hierarchy under '{1}'".format(target_name, unrigged_parent[0]))
    else:
        # If it was at the world level, bring it to the world level
        current_parent = cmds.listRelatives(renamed_rigged, parent=True)
        if current_parent:
            cmds.parent(renamed_rigged, world=True)
        print("Successfully renamed '{0}' and placed it at world level.".format(target_name))

# --- HOW TO USE ---
# Replace these strings with your actual object names
SOURCE_CORRECT_NAME = "pSphere_CorrectName"  # The unrigged mesh
TARGET_RIGGED_MESH = "pSphere_Rigged_WrongName"  # The rigged mesh



#===========================================================================================================

def offset_joint(joint_name, offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """
    OPTION 1: Moves a joint by a specific amount in X, Y, or Z 
    without moving its children.
    """
    if not cmds.objExists(joint_name):
        cmds.error(f"'{joint_name}' does not exist.")
        return
        
    cmds.move(
        offset_x, offset_y, offset_z,
        joint_name, 
        relative=True, 
        worldSpace=True, 
        preserveChildPosition=True
    )
    print(f"Success: Offset '{joint_name}' by X: {offset_x}, Y: {offset_y}, Z: {offset_z}")


def snap_joint_to_target(joint_to_move, target_object):
    """
    OPTION 2: Snaps a joint to another object and prints the exact offset values.
    """
    if not cmds.objExists(joint_to_move):
        cmds.error(f"The joint '{joint_to_move}' does not exist.")
        return
    if not cmds.objExists(target_object):
        cmds.error(f"The target '{target_object}' does not exist.")
        return

    # 1. Get the starting position
    start_pos = cmds.xform(joint_to_move, query=True, worldSpace=True, translation=True)

    # 2. Get the target position to snap to
    target_pos = cmds.xform(target_object, query=True, worldSpace=True, translation=True)

    # 3. Calculate the exact offset needed to make this move
    moved_x = target_pos[0] - start_pos[0]
    moved_y = target_pos[1] - start_pos[1]
    moved_z = target_pos[2] - start_pos[2]

    # 4. Snap the joint while preserving children
    cmds.move(
        target_pos[0], target_pos[1], target_pos[2],
        joint_to_move, 
        absolute=True, 
        worldSpace=True, 
        preserveChildPosition=True
    )
    
    # 5. Print the results in a format that can be easily copied and reused
    print(f"\n--- Snapped '{joint_to_move}' to '{target_object}' ---")
    print(f"To repeat this exact move as an offset, copy and run this code:")
    print(f"offset_joint('{joint_to_move}', offset_x={moved_x:.3f}, offset_y={moved_y:.3f}, offset_z={moved_z:.3f})\n")



#==================================================================================================================================


def set_all_joint_radii(new_radius=1.0):
    """
    Selects all joints in the Maya scene and sets their radius.
    
    Args:
        new_radius (float): The target radius size for the joints.
    """
    # 1. Find all joints in the scene
    joints = cmds.ls(type='joint')
    
    # 2. Safety check: ensure there are joints to modify
    if not joints:
        cmds.warning("No joints found in the current scene.")
        return
        
    # 3. Loop through each joint and set the 'radius' attribute
    for jnt in joints:
        try:
            # Set the radius attribute
            cmds.setAttr(f"{jnt}.radius", new_radius)
        except RuntimeError as e:
            # Catch locked attributes or referenced nodes
            print(f"Skipped {jnt}: {e}")
            
    # 4. Select the joints as requested
    cmds.select(joints, replace=True)
    cmds.select(d=True)
    
    print(f"Success: Selected {len(joints)} joints and set their radius to {new_radius}.")



#===================================================================================================

def find_strict_cc3_joint(target_name):
    """Strictly matches the exact joint name while safely tolerating namespaces."""
    found_nodes = cmds.ls(f"*{target_name}", type="joint")
    for node in found_nodes:
        short_name = node.split(":")[-1]
        if short_name == target_name:
            return node
    return None

def apply_mgear_to_cc3_constraints(mapping_list, skip_list, exclude_enabled):
    """Iterates through the mapping and applies the specified constraints."""
    success_count = 0
    missing_drivers = []
    missing_driven = []
    skipped_joints = []

    for mgear_name, cc3_name, constraint_types in mapping_list:
        # Skip logic based on your original facial joints list
        if exclude_enabled and cc3_name in skip_list:
            skipped_joints.append(cc3_name)
            continue

        source_list = cmds.ls("*" + mgear_name, type=["joint", "transform"])
        target = find_strict_cc3_joint(cc3_name)

        if not source_list:
            missing_drivers.append(mgear_name)
        
        if not target:
            missing_driven.append(cc3_name)

        if source_list and target:
            source = source_list[0]
            try:
                if "parentConstraint" in constraint_types:
                    cmds.parentConstraint(source, target, maintainOffset=True, weight=1)
                if "orientConstraint" in constraint_types:
                    cmds.orientConstraint(source, target, maintainOffset=True, weight=1)
                if "scaleConstraint" in constraint_types:
                    cmds.scaleConstraint(source, target, maintainOffset=True, weight=1)
                success_count += 1
            except Exception as e:
                cmds.warning(f"Error binding {target} to {source}: {e}")

    # Print summary to the script editor
    print("\n--- CC3 to mGear Constraint Summary ---")
    print(f"Successfully connected: {success_count} joints.")
    if skipped_joints:
        print(f"Skipped {len(skipped_joints)} joints (Exclusion list).")
    if missing_drivers:
        cmds.warning(f"Missing mGear drivers: {', '.join(set(missing_drivers))}")
    if missing_driven:
        cmds.warning(f"Missing CC3 joints: {', '.join(set(missing_driven))}")
    print("---------------------------------------\n")


# =========================================================================================
# CONFIGURATION OPTIONS - EDIT JOINT NAMES & EXCLUSIONS HERE
# =========================================================================================

# Set to False if you want to constrain ALL joints, including facial ones
EXCLUDE_JOINTS = True 

JOINTS_TO_SKIP = [
    "CC_Base_JawRoot", "CC_Base_FacialBone", "CC_Base_Teeth02", 
    "CC_Base_Tongue02", "CC_Base_Teeth01", "CC_Base_Tongue01", 
    "CC_Base_UpperJaw", "CC_Base_L_Eye", "CC_Base_Tongue03", "CC_Base_R_Eye"
]

JOINT_MAPPINGS = [
    # Root & Pelvis
    ("local_C0_ctl", "CC_Base_BoneRoot", ["parentConstraint", "scaleConstraint"]),
    ("spine_C0_0_jnt", "CC_Base_Hip", ["parentConstraint"]),
    ("spine_C0_0_jnt", "CC_Base_Pelvis", ["parentConstraint"]),
    
    # Spine & Head
    ("spine_C0_1_jnt", "CC_Base_Waist", ["parentConstraint"]),
    ("spine_C0_2_jnt", "CC_Base_Spine01", ["parentConstraint"]),
    ("spine_C0_4_jnt", "CC_Base_Spine02", ["parentConstraint"]),
    ("neck_C0_0_jnt", "CC_Base_NeckTwist01", ["parentConstraint"]),
    ("neck_C0_1_jnt", "CC_Base_NeckTwist02", ["parentConstraint"]),
    ("neck_C0_head_jnt", "CC_Base_Head", ["parentConstraint"]),
    
    # Face / Mouth
    ("mouth_C0_jaw_jnt", "CC_Base_JawRoot", ["parentConstraint"]),
    ("tongue_C0_1_jnt", "CC_Base_Tongue01", ["parentConstraint"]),
    ("tongue_C0_2_jnt", "CC_Base_Tongue02", ["parentConstraint"]),
    ("tongue_C0_3_jnt", "CC_Base_Tongue03", ["parentConstraint"]),
    ("mouth_C0_teethup_jnt", "CC_Base_Teeth01", ["parentConstraint"]),
    ("mouth_C0_teethlow_jnt", "CC_Base_Teeth02", ["parentConstraint"]),
    ("eye_L0_eye_jnt", "CC_Base_L_Eye", ["parentConstraint"]),
    ("eye_R0_eye_jnt", "CC_Base_R_Eye", ["parentConstraint"]),
    ("neck_C0_head_jnt", "CC_Base_FacialBone", ["parentConstraint"]),
    ("mouth_C0_jaw_jnt", "CC_Base_UpperJaw", ["parentConstraint"]),

    # Left Leg & Twist
    ("leg_L0_0_jnt", "CC_Base_L_Thigh", ["parentConstraint"]),
    ("leg_L0_1_jnt", "CC_Base_L_ThighTwist01", ["parentConstraint"]),
    ("leg_L0_1_jnt", "CC_Base_L_ThighTwist02", ["parentConstraint"]),
    ("leg_L0_3_jnt", "CC_Base_L_KneeShareBone", ["parentConstraint"]),
    ("leg_L0_4_jnt", "CC_Base_L_Calf", ["parentConstraint"]),
    ("leg_L0_5_jnt", "CC_Base_L_CalfTwist01", ["parentConstraint"]),
    ("leg_L0_5_jnt", "CC_Base_L_CalfTwist02", ["parentConstraint"]),
    ("leg_L0_end_jnt", "CC_Base_L_Foot", ["parentConstraint"]),
    
    # Left Toes
    ("foot_L0_0_jnt", "CC_Base_L_ToeBaseShareBone", ["orientConstraint"]),
    ("foot_L0_0_jnt", "CC_Base_L_ToeBase", ["orientConstraint"]),
    ("foot_L0_1_jnt", "CC_Base_L_BigToe1", ["orientConstraint"]),
    ("foot_L0_1_jnt", "CC_Base_L_IndexToe1", ["orientConstraint"]),
    ("foot_L0_1_jnt", "CC_Base_L_MidToe1", ["orientConstraint"]),
    ("foot_L0_1_jnt", "CC_Base_L_RingToe1", ["orientConstraint"]),
    ("foot_L0_1_jnt", "CC_Base_L_PinkyToe1", ["orientConstraint"]),

    # Right Leg & Twist
    ("leg_R0_0_jnt", "CC_Base_R_Thigh", ["parentConstraint"]),
    ("leg_R0_1_jnt", "CC_Base_R_ThighTwist01", ["parentConstraint"]),
    ("leg_R0_1_jnt", "CC_Base_R_ThighTwist02", ["parentConstraint"]),
    ("leg_R0_3_jnt", "CC_Base_R_KneeShareBone", ["parentConstraint"]),
    ("leg_R0_4_jnt", "CC_Base_R_Calf", ["parentConstraint"]),
    ("leg_R0_5_jnt", "CC_Base_R_CalfTwist01", ["parentConstraint"]),
    ("leg_R0_5_jnt", "CC_Base_R_CalfTwist02", ["parentConstraint"]),
    ("leg_R0_end_jnt", "CC_Base_R_Foot", ["parentConstraint"]),
    
    # Right Toes
    ("foot_R0_0_jnt", "CC_Base_R_ToeBaseShareBone", ["orientConstraint"]),
    ("foot_R0_0_jnt", "CC_Base_R_ToeBase", ["orientConstraint"]),
    ("foot_R0_1_jnt", "CC_Base_R_BigToe1", ["orientConstraint"]),
    ("foot_R0_1_jnt", "CC_Base_R_IndexToe1", ["orientConstraint"]),
    ("foot_R0_1_jnt", "CC_Base_R_MidToe1", ["orientConstraint"]),
    ("foot_R0_1_jnt", "CC_Base_R_RingToe1", ["orientConstraint"]),
    ("foot_R0_1_jnt", "CC_Base_R_PinkyToe1", ["orientConstraint"]),

    # Left Arm & Specialty Twist
    ("shoulder_L0_shoulder_jnt", "CC_Base_L_Clavicle", ["parentConstraint"]),
    ("arm_L0_0_jnt", "CC_Base_L_Upperarm", ["parentConstraint"]),
    ("arm_L0_1_jnt", "CC_Base_L_UpperarmTwist01", ["parentConstraint"]),
    ("arm_L0_1_jnt", "CC_Base_L_UpperarmTwist02", ["parentConstraint"]),
    ("arm_L0_3_jnt", "CC_Base_L_ElbowShareBone", ["parentConstraint"]),
    ("arm_L0_4_jnt", "CC_Base_L_Forearm", ["parentConstraint"]),
    ("arm_L0_5_jnt", "CC_Base_L_ForearmTwist01", ["parentConstraint"]),
    ("arm_L0_5_jnt", "CC_Base_L_ForearmTwist02", ["parentConstraint"]),
    ("arm_L0_end_jnt", "CC_Base_L_Hand", ["parentConstraint"]),
    ("spine_C0_4_jnt", "CC_Base_L_RibsTwist", ["parentConstraint"]),
    ("spine_C0_4_jnt", "CC_Base_L_Breast", ["parentConstraint"]),

    # Left Fingers
    ("thumb_L0_0_jnt", "CC_Base_L_Thumb1", ["orientConstraint"]),
    ("thumb_L0_1_jnt", "CC_Base_L_Thumb2", ["orientConstraint"]),
    ("thumb_L0_2_jnt", "CC_Base_L_Thumb3", ["orientConstraint"]),
    ("finger_L0_0_jnt", "CC_Base_L_Index1", ["orientConstraint"]),
    ("finger_L0_1_jnt", "CC_Base_L_Index2", ["orientConstraint"]),
    ("finger_L0_2_jnt", "CC_Base_L_Index3", ["orientConstraint"]),
    ("finger_L1_0_jnt", "CC_Base_L_Mid1", ["orientConstraint"]),
    ("finger_L1_1_jnt", "CC_Base_L_Mid2", ["orientConstraint"]),
    ("finger_L1_2_jnt", "CC_Base_L_Mid3", ["orientConstraint"]),
    ("finger_L2_0_jnt", "CC_Base_L_Ring1", ["orientConstraint"]),
    ("finger_L2_1_jnt", "CC_Base_L_Ring2", ["orientConstraint"]),
    ("finger_L2_2_jnt", "CC_Base_L_Ring3", ["orientConstraint"]),
    ("finger_L3_0_jnt", "CC_Base_L_Pinky1", ["orientConstraint"]),
    ("finger_L3_1_jnt", "CC_Base_L_Pinky2", ["orientConstraint"]),
    ("finger_L3_2_jnt", "CC_Base_L_Pinky3", ["orientConstraint"]),

    # Right Arm & Specialty Twist
    ("shoulder_R0_shoulder_jnt", "CC_Base_R_Clavicle", ["parentConstraint"]),
    ("arm_R0_0_jnt", "CC_Base_R_Upperarm", ["parentConstraint"]),
    ("arm_R0_1_jnt", "CC_Base_R_UpperarmTwist01", ["parentConstraint"]),
    ("arm_R0_1_jnt", "CC_Base_R_UpperarmTwist02", ["parentConstraint"]),
    ("arm_R0_3_jnt", "CC_Base_R_ElbowShareBone", ["parentConstraint"]),
    ("arm_R0_4_jnt", "CC_Base_R_Forearm", ["parentConstraint"]),
    ("arm_R0_5_jnt", "CC_Base_R_ForearmTwist01", ["parentConstraint"]),
    ("arm_R0_5_jnt", "CC_Base_R_ForearmTwist02", ["parentConstraint"]),
    ("arm_R0_end_jnt", "CC_Base_R_Hand", ["parentConstraint"]),
    ("spine_C0_4_jnt", "CC_Base_R_RibsTwist", ["parentConstraint"]),
    ("spine_C0_4_jnt", "CC_Base_R_Breast", ["parentConstraint"]),

    # Right Fingers
    ("thumb_R0_0_jnt", "CC_Base_R_Thumb1", ["orientConstraint"]),
    ("thumb_R0_1_jnt", "CC_Base_R_Thumb2", ["orientConstraint"]),
    ("thumb_R0_2_jnt", "CC_Base_R_Thumb3", ["orientConstraint"]),
    ("finger_R0_0_jnt", "CC_Base_R_Index1", ["orientConstraint"]),
    ("finger_R0_1_jnt", "CC_Base_R_Index2", ["orientConstraint"]),
    ("finger_R0_2_jnt", "CC_Base_R_Index3", ["orientConstraint"]),
    ("finger_R1_0_jnt", "CC_Base_R_Mid1", ["orientConstraint"]),
    ("finger_R1_1_jnt", "CC_Base_R_Mid2", ["orientConstraint"]),
    ("finger_R1_2_jnt", "CC_Base_R_Mid3", ["orientConstraint"]),
    ("finger_R2_0_jnt", "CC_Base_R_Ring1", ["orientConstraint"]),
    ("finger_R2_1_jnt", "CC_Base_R_Ring2", ["orientConstraint"]),
    ("finger_R2_2_jnt", "CC_Base_R_Ring3", ["orientConstraint"]),
    ("finger_R3_0_jnt", "CC_Base_R_Pinky1", ["orientConstraint"]),
    ("finger_R3_1_jnt", "CC_Base_R_Pinky2", ["orientConstraint"]),
    ("finger_R3_2_jnt", "CC_Base_R_Pinky3", ["orientConstraint"]),
]





#==========================================================================================



import maya.cmds as cmds
import maya.mel as mel

def apply_custom_wrap(source_mesh, target_meshes):
    """
    Wraps a list of target meshes to a single source mesh.
    Actively searches for the newly created wrap node to set Exclusive Bind ON.
    """
    # Verify the source mesh exists before starting
    if not cmds.objExists(source_mesh):
        cmds.error('Source mesh "{}" does not exist in the scene.'.format(source_mesh))
        return

    for target in target_meshes:
        if not cmds.objExists(target):
            cmds.warning('Target mesh "{}" not found. Skipping...'.format(target))
            continue

        # 1. Select target first, source second
        cmds.select(target, replace=True)
        cmds.select(source_mesh, add=True)

        # 2. Call Maya's native wrap creation
        mel.eval('CreateWrap;')

        # 3. SEARCH for the wrap node that was just attached to the target
        # listHistory looks at everything connected to the target mesh
        history = cmds.listHistory(target)
        wrap_nodes = cmds.ls(history, type='wrap')

        if wrap_nodes:
            # The node directly affecting the mesh will be in this list
            # We grab the first one found in its history
            wrap_node = wrap_nodes[0]
            
            # 4. Force Exclusive Bind to 1 (ON)
            cmds.setAttr('{}.exclusiveBind'.format(wrap_node), 1)
            print('Success: Wrapped "{}" -> "{}" | Enabled exclusiveBind on: {}'.format(target, source_mesh, wrap_node))
            
        else:
            cmds.warning('Failed to locate wrap node in history for "{}". exclusiveBind may not be set.'.format(target))

    # Clear selection at the end
    cmds.select(clear=True)


#===================================================================================================================

import maya.cmds as cmds
import fnmatch

def create_and_reorder_blendshape(source_mesh, target_mesh):
    # 1. Validate that both meshes exist
    if not cmds.objExists(source_mesh):
        cmds.error(f"Source mesh '{source_mesh}' does not exist.")
        return
    if not cmds.objExists(target_mesh):
        cmds.error(f"Target mesh '{target_mesh}' does not exist.")
        return

    # 2. Find the target morpher FIRST 
    history = cmds.listHistory(target_mesh, pruneDagObjects=True) or []
    deformers = cmds.ls(history, type='geometryFilter')
    
    target_morpher = None
    for deformer in deformers:
        # Added a wildcard at the start to catch any namespaces
        if fnmatch.fnmatch(deformer, "*Morpher_CC_Base_Bod*"):
            target_morpher = deformer
            break

    # 3. Create the blendshape
    # FIX: frontOfChain=True forces the new node into the pre-deformation stack (below the SkinCluster).
    # Without this, Maya often refuses to reorder it below the CC Morpher.
    bs_node = cmds.blendShape(source_mesh, target_mesh, name=f"{source_mesh}_BS", frontOfChain=True)[0]
    cmds.blendShape(bs_node, edit=True, weight=[(0, 1.0)])
    print(f"Created Blendshape: {bs_node}")

    # 4. Reorder the deformer order
    if target_morpher:
        try:
            # reorderDeformers(A, B) forces node A to evaluate before node B 
            # (which pushes it visually BELOW node B in the Channel Box Inputs list)
            cmds.reorderDeformers(bs_node, target_morpher)
            print(f"Success: Reordered '{bs_node}' to come below '{target_morpher}'.")
        except Exception as e:
            cmds.warning(f"Failed to reorder deformers. Maya error: {e}")
    else:
        cmds.warning("Notice: No '*Morpher_CC_Base_Bod*' node found on the target mesh. Kept front-of-chain order.")

    return bs_node





    #===========================================================================================================


def enable_group_overrides(group_name):
    """
    Toggles drawing overrides (Reference Mode <-> Normal Mode) on the specified 
    group and every mesh/transform under its hierarchy.
    """
    if not cmds.objExists(group_name):
        return cmds.warning(f"The group or object '{group_name}' does not exist in the scene.")
        
    root_enabled_attr = f"{group_name}.overrideEnabled"
    
    # 1. Determine the target state based on the main group's current state
    if cmds.objExists(root_enabled_attr):
        # If currently 1 (Enabled), target is 0 (Disabled). Otherwise, target is 1.
        target_enable = 0 if cmds.getAttr(root_enabled_attr) == 1 else 1
    else:
        target_enable = 1  # Fallback default
        
    # 2. Get all descendants (children, grandchildren, shapes, etc.)
    descendants = cmds.listRelatives(group_name, allDescendents=True, fullPath=True) or []
    
    # Combine the main group and all descendants to process them all
    nodes_to_process = [group_name] + descendants
        
    # 3. Apply the toggled state to the hierarchy
    for node in nodes_to_process:
        attr_enabled = f"{node}.overrideEnabled"
        attr_display_type = f"{node}.overrideDisplayType"
        
        if cmds.objExists(attr_enabled):
            try:
                cmds.setAttr(attr_enabled, target_enable)
                
                if cmds.objExists(attr_display_type):
                    if target_enable == 1:
                        # 2 sets the display type to 'Reference'
                        cmds.setAttr(attr_display_type, 2) 
                    else:
                        # 0 resets the display type to 'Normal'
                        cmds.setAttr(attr_display_type, 0)
            except Exception as e:
                cmds.warning(f"Could not set attribute for '{node}': {e}")
                
    cmds.refresh()
    
    status_msg = "enabled (Reference mode)" if target_enable == 1 else "disabled (Normal mode)"
    print(f"Overrides have been {status_msg} for '{group_name}' and its hierarchy.")

def toggle_joints_visibility():
    """
    Toggles the draw style of all joints in the scene between 
    'Bone' (Visible) and 'None' (Hidden).
    """
    joints = cmds.ls(type="joint")
    if not joints:
        return cmds.warning("No joints found in the scene.")
        
    # 1. Check the first joint to determine the target state
    # 2 is 'None' (Hidden), 0 is 'Bone' (Default/Visible)
    first_joint_style = cmds.getAttr(f"{joints[0]}.drawStyle")
    target_style = 0 if first_joint_style == 2 else 2
    
    # 2. Apply the toggled style to all joints
    for j in joints:
        try:
            cmds.setAttr(f"{j}.drawStyle", target_style)
        except Exception as e:
            cmds.warning(f"Could not update drawStyle for '{j}': {e}")
            
    status_msg = "Bone (Visible)" if target_style == 0 else "None (Hidden)"
    print(f"All joints set to draw style: {status_msg}")
        

#============================================================================================================


import maya.cmds as cmds

def create_curve_on_joints(jnt1, jnt2):
    # 1. Verify that both objects actually exist in the Maya scene
    if not cmds.objExists(jnt1):
        cmds.warning(f"Object '{jnt1}' does not exist.")
        return None
    if not cmds.objExists(jnt2):
        cmds.warning(f"Object '{jnt2}' does not exist.")
        return None
        
    # 2. Get the world space coordinates of both joints
    pos1 = cmds.xform(jnt1, query=True, worldSpace=True, translation=True)
    pos2 = cmds.xform(jnt2, query=True, worldSpace=True, translation=True)
    
    # 3. Create the curve
    # Using degree=3 with 4 points (2 overlapping at each joint)
    curve_name = cmds.curve(
        degree=3, 
        point=[pos1, pos1, pos2, pos2], 
        name="jnt_connection_crv#"
    )
    
    print(f"Successfully created: {curve_name} between {jnt1} and {jnt2}")
    return curve_name

# --- EXAMPLE USAGE ---
# Replace "joint1" and "joint2" with the exact names of your joints in the Outliner



#===========================================================================================

# --- 1. Your Provided Function ---
def offset_joint(joint_name, offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """
    OPTION 1: Moves a joint by a specific amount in X, Y, or Z 
    without moving its children.
    """
    if not cmds.objExists(joint_name):
        cmds.warning(f"'{joint_name}' does not exist.")
        return
        
    cmds.move(
        offset_x, offset_y, offset_z,
        joint_name, 
        relative=True, 
        worldSpace=True, 
        preserveChildPosition=True
    )
    print(f"Success: Offset '{joint_name}' by X: {offset_x:.3f}, Y: {offset_y:.3f}, Z: {offset_z:.3f}")


# --- 2. New Snapping Function ---
def snap_joints_to_curve(curve_name, joints_to_snap):
    """
    Finds the nearest point on the curve for each joint, calculates the 
    relative offset, and uses offset_joint() to move them.
    """
    # Verify the curve exists
    if not cmds.objExists(curve_name):
        cmds.warning(f"Curve '{curve_name}' does not exist.")
        return
        
    # Get the curve shape node (needed for the nearest point calculation)
    if cmds.nodeType(curve_name) == "transform":
        curve_shapes = cmds.listRelatives(curve_name, shapes=True)
        if not curve_shapes:
            cmds.warning(f"'{curve_name}' has no shape node.")
            return
        curve_shape = curve_shapes[0]
    else:
        curve_shape = curve_name

    # Create a nearestPointOnCurve node to do the math
    npc_node = cmds.createNode("nearestPointOnCurve")
    cmds.connectAttr(f"{curve_shape}.worldSpace[0]", f"{npc_node}.inputCurve")
    
    # Loop through each joint in the list
    for jnt in joints_to_snap:
        if not cmds.objExists(jnt):
            cmds.warning(f"Joint '{jnt}' does not exist, skipping.")
            continue
            
        # 1. Get the current world-space position of the joint
        jnt_pos = cmds.xform(jnt, query=True, worldSpace=True, translation=True)
        
        # 2. Feed this position into the nearestPoint node
        cmds.setAttr(f"{npc_node}.inPosition", jnt_pos[0], jnt_pos[1], jnt_pos[2])
        
        # 3. Get the resulting nearest position on the curve
        nearest_x = cmds.getAttr(f"{npc_node}.positionX")
        nearest_y = cmds.getAttr(f"{npc_node}.positionY")
        nearest_z = cmds.getAttr(f"{npc_node}.positionZ")
        
        # 4. Calculate the relative offset (Target Position - Current Position)
        offset_x = nearest_x - jnt_pos[0]
        offset_y = nearest_y - jnt_pos[1]
        offset_z = nearest_z - jnt_pos[2]
        
        # 5. Snap the joint using your offset function
        offset_joint(jnt, offset_x, offset_y, offset_z)
        
    # Clean up the utility node to keep the scene clean
    cmds.delete(npc_node)
    print(f"\nFinished snapping {len(joints_to_snap)} joint(s) to '{curve_name}'.")








#============================================================================================================

def organize_cc_mesh():
    # delete, parenting, correct naming
    replace_and_rename_mesh(rigged_mesh="CC_Base_Body", unrigged_mesh="geo_kartavirya_cc_base_body_lod_1")
    replace_and_rename_mesh(rigged_mesh="CC_Base_Tongue", unrigged_mesh="geo_kartavirya_cc_base_tongue_lod_1")
    replace_and_rename_mesh(rigged_mesh="CC_Base_Teeth", unrigged_mesh="geo_kartavirya_cc_base_teeth_lod_1")
    replace_and_rename_mesh(rigged_mesh="CC_Base_TearLine", unrigged_mesh="geo_kartavirya_cc_base_tearline_lod_1")

    #----------------------------------------------------------------------------------------------------
    #parenting

    cmds.group(n = "cc_mesh_grp", em=True)
    cmds.parent("CC_Base_Body", "CC_Base_Eye", "KL_kartavirya_a_01|CC_Base_TearLine","CC_Base_Teeth", "CC_Base_Tongue" , "cc_mesh_grp" )

    cmds.group(n = "cc_rig_grp", em=True)
    cmds.parent("KL_kartavirya_a_01", "headRig_grp" , "cc_rig_grp" )

    cmds.setAttr ("cc_rig_grp.scaleZ", 0.01)
    cmds.setAttr ("cc_rig_grp.scaleX", 0.01)
    cmds.setAttr ("cc_rig_grp.scaleY", 0.01)

    cmds.parent("CC_Base_Eye", "kartavirya_a_lod_1")

    #----------------------------------------------------------------------------------------------------
    #delete
    cmds.delete("transform1", "cc_mesh_grp")

#==============================================================================================

def add_prefix_to_objects(obj_list, prefix):
    """
    Adds a specified prefix to a list of Maya objects.
    
    :param obj_list: list or str, A single object name or a list of object names.
    :param prefix: str, The prefix to add (e.g., "PRE").
    :return: list, A list of the newly renamed object names.
    """
    # Force single string inputs into a list so the loop doesn't break
    if isinstance(obj_list, str):
        obj_list = [obj_list]
        
    # Standardize the prefix format (adds an underscore if missing)
    if not prefix.endswith("_"):
        prefix = prefix + "_"
        
    renamed_objects = []

    for obj in obj_list:
        # Check if the object actually exists
        if not cmds.objExists(obj):
            cmds.warning(f"Object '{obj}' does not exist. Skipping.")
            continue
            
        # Optional: Check if the object already has the prefix to avoid duplicates
        short_name = obj.split("|")[-1]
        if short_name.startswith(prefix):
            cmds.warning(f"Object '{short_name}' already has the prefix '{prefix}'. Skipping.")
            renamed_objects.append(obj)
            continue
            
        # Combine prefix with the short name
        new_name = prefix + short_name
        
        # Rename and store the new name
        renamed_obj = cmds.rename(obj, new_name)
        renamed_objects.append(renamed_obj)
        print(f"Renamed: {obj} -> {renamed_obj}")
        
    return renamed_objects




def DisplayingNormalsFix():

    # Target objects from your selection
    objects = [
        "FRM_C_jaw_openExtremeShape", 
        "FRM_L_neck_stretchShape", 
        "FRM_C_neck_swallowShape"
    ]
    
    # Filter the list to only include objects that actually exist in your scene
    valid_objects = [obj for obj in objects if cmds.objExists(obj)]
    
    if valid_objects:
        # -relative(r), -facet(f), -displayNormal(dn) True
        cmds.polyOptions(valid_objects, relative=True, facet=True, displayNormal=True)
        print(f"Displaying vertex normals for: {valid_objects}")
    else:
        print("None of the specified objects were found in the scene.")


#-----------------------------------------------------------------------------


def create_lra_zero_groups(controls):
    for ctrl in controls:
        if not cmds.objExists(ctrl):
            cmds.warning("Control '" + ctrl + "' not found. Skipping.")
            continue
            
        # 1. Identify the original parent
        old_parent = cmds.listRelatives(ctrl, parent=True)
        
        # 2. Create the new zero group
        zero_grp = cmds.group(empty=True, name=ctrl + "_Zro_Grp")
        
        # 3. Temporarily parent the group TO the control
        cmds.parent(zero_grp, ctrl)
        
        # 4. Zero out local transforms to perfectly snap to the control's LRA
        cmds.setAttr(zero_grp + ".translate", 0, 0, 0)
        cmds.setAttr(zero_grp + ".rotate", 0, 0, 0)
        cmds.setAttr(zero_grp + ".scale", 1, 1, 1)
        
        # 5. Move the aligned group back to the original parent (or world)
        if old_parent:
            cmds.parent(zero_grp, old_parent[0])
        else:
            cmds.parent(zero_grp, world=True)
            
        # 6. Parent the control under the new group to completely zero it out
        cmds.parent(ctrl, zero_grp)