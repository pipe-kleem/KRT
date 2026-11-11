# delete, parenting, correct naming
# Add one replace_and_rename_mesh line per extra mesh.
replace_and_rename_mesh(rigged_mesh="CC_Base_Body", unrigged_mesh="geo_{char}_cc_base_body_lod_0")
replace_and_rename_mesh(rigged_mesh="CC_Base_Tongue", unrigged_mesh="geo_{char}_cc_base_tongue_lod_0")
replace_and_rename_mesh(rigged_mesh="CC_Base_Teeth", unrigged_mesh="geo_{char}_cc_base_teeth_lod_0")
replace_and_rename_mesh(rigged_mesh="CC_Base_TearLine", unrigged_mesh="geo_{char}_cc_base_tearline_lod_0")

replace_and_rename_mesh(rigged_mesh="Eye_R", unrigged_mesh="geo_{char}_cornea_r_lod_0")
replace_and_rename_mesh(rigged_mesh="Cornea_R", unrigged_mesh="geo_{char}_eye_r_lod_0")
replace_and_rename_mesh(rigged_mesh="Eye_L", unrigged_mesh="geo_{char}_eye_l_lod_0")
replace_and_rename_mesh(rigged_mesh="Cornea_L", unrigged_mesh="geo_{char}_cornea_l_lod_0")

#----------------------------------------------------------------------------------------------------
#parenting

cmds.group(n="cc_rig_grp", em=True)
cmds.parent("{char}", "headRig_grp", "cc_rig_grp")
cmds.setAttr("cc_rig_grp.scaleZ", 0.01)
cmds.setAttr("cc_rig_grp.scaleX", 0.01)
cmds.setAttr("cc_rig_grp.scaleY", 0.01)
cmds.parent("CC_Base_Eye", "{rig}_lod_0")
cmds.parent("geo_{char}_cornea_r_lod_0", "geo_{char}_eye_r_lod_0", "geo_{char}_eye_l_lod_0", "geo_{char}_cornea_l_lod_0", "CC_Base_Eye")


#----------------------------------------------------------------------------------------------------
#delete
if cmds.objExists("transform1"):
    cmds.delete("transform1")

cmds.group(em=True, name="rigging")
cmds.parent("rigging", "{rig}")
cmds.group(em=True, name="others")
cmds.parent("others", "{rig}")
