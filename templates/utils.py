"""scripts/utils.py - helpers for THIS rig only.

KRT already loads the studio rig library (KRT/rigutils) into every script
panel and into Maya's Script Editor, so none of this needs importing:

  UniUtils.*   run_Fan, run_stretchy, run_breathing, updateEpicSpine, switchFix,
               space_switch, EpicSpineConstraint, snap_joint, reference_file,
               auto_skincluster_top_all_meshes, finalize_grouping_N_parent, ...
  helpers      replace_and_rename_mesh, create_curve_on_joints, organize_and_convert_lod,
               set_all_joint_radii, create_lra_zero_groups, DisplayingNormalsFix,
               apply_mgear_to_cc3_constraints (JOINT_MAPPINGS, JOINTS_TO_SKIP,
               EXCLUDE_JOINTS), repath_textures, offset_joint, snap_joint_to_target,
               apply_custom_wrap, create_and_reorder_blendshape, add_prefix_to_objects, ...
  modules      UniUtils, wrapToBs, Fan, stretchy, Tweaker, breathing, capture_viewport_api

(The full list: KRT/rigutils/UniUtils.py and KRT/rigutils/rig_lib.py.)
Put functions that only this rig needs below. A function defined here with
the same name as a library one replaces it for this rig.
"""
import maya.cmds as cmds
import maya.mel as mel
