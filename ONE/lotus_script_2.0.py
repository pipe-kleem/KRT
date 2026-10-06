import maya.cmds as cmds
import random

def get_obj_size(obj):
    """Calculates the max dimension of an object's bounding box."""
    bbox = cmds.exactWorldBoundingBox(obj)
    width = bbox[3] - bbox[0]
    height = bbox[4] - bbox[1]
    depth = bbox[5] - bbox[2]
    return max(width, height, depth)

def fix_deformation_order(geo_name):
    """Ensures all bend deformers are calculated before the skinCluster."""
    # Find all deformers in the history
    history = cmds.listHistory(geo_name, pruneDagObjects=True)
    skin = cmds.ls(history, type='skinCluster')
    bends = cmds.ls(history, type='nonLinear')
    
    if skin and bends:
        for b in bends:
            # Reorder: place the bend node before the skinCluster in the stack
            try:
                cmds.reorderDeformers(b, skin[0], geo_name)
            except:
                pass

def run_lotus_rig_v6(multiplier, offsets, total_petals=50, edge_idx=361, vtx_idx=1):
    # 1. Master Hierarchy Setup
    master_grp = "grp_flower_MASTER"
    if not cmds.objExists(master_grp):
        master_grp = cmds.group(em=True, name=master_grp)
    
    joints_grp = "grp_joints"
    if not cmds.objExists(joints_grp):
        joints_grp = cmds.group(em=True, name=joints_grp, parent=master_grp)
        
    deform_grp = "grp_bendy_handles"
    if not cmds.objExists(deform_grp):
        deform_grp = cmds.group(em=True, name=deform_grp, parent=master_grp)
        
    # Global Control Name: Lotus_Main_ctl
    global_ctrl = "Lotus_Main_ctl"
    global_ofs = "grp_global_OFS"
    if not cmds.objExists(global_ctrl):
        temp_circ = cmds.circle(nr=(0, 1, 0), r=10, name=global_ctrl)[0]
        global_ofs = cmds.group(temp_circ, name=global_ofs, parent=master_grp)
        cmds.setAttr(f"{global_ctrl}.overrideEnabled", 1)
        cmds.setAttr(f"{global_ctrl}.overrideColor", 17) # Yellow
    
    controls_grp = "grp_petal_controls"
    if not cmds.objExists(controls_grp):
        controls_grp = cmds.group(em=True, name=controls_grp, parent=global_ctrl)

    # Scale constraints from Global Control
    if not cmds.listConnections(f"{deform_grp}.scale"):
        cmds.scaleConstraint(global_ctrl, deform_grp, mo=True)
    if not cmds.listConnections(f"{joints_grp}.scale"):
        cmds.scaleConstraint(global_ctrl, joints_grp, mo=True)

    bright_colors = [6, 9, 13, 14, 15, 17, 18, 19, 20, 22, 23, 25, 26, 28, 29, 30]

    for i in range(1, total_petals + 1):
        geo_padded = f"geo_petal_{i:02d}_geo_lod_2"
        geo_unpadded = f"geo_petal_{i}_geo_lod_2"
        geo_name = geo_padded if cmds.objExists(geo_padded) else (geo_unpadded if cmds.objExists(geo_unpadded) else None)
        if not geo_name: continue

        # --- MATH & SIZING ---
        leaf_size = get_obj_size(geo_name)
        calc_radius = (leaf_size * 0.5) * multiplier
        edge_name = f"{geo_name}.e[{edge_idx}]"
        vtx_name = f"{geo_name}.vtx[{vtx_idx}]"
        
        verts = cmds.polyInfo(edge_name, ev=True)[0].split(':')[-1].split()
        v1_pos = cmds.xform(f"{geo_name}.vtx[{verts[0]}]", q=True, t=True, ws=True)
        v2_pos = cmds.xform(f"{geo_name}.vtx[{verts[1]}]", q=True, t=True, ws=True)
        jnt_pos = [(v1_pos[0]+v2_pos[0])/2, (v1_pos[1]+v2_pos[1])/2, (v1_pos[2]+v2_pos[2])/2]
        target_vtx_pos = cmds.xform(vtx_name, q=True, t=True, ws=True)

        # --- JOINT ---
        cmds.select(cl=True)
        jnt = cmds.joint(p=jnt_pos, name=f"jnt_petal_{i:02d}", rad=0.2)
        cmds.parent(jnt, joints_grp)
        
        norm_con = cmds.normalConstraint(geo_name, jnt, aimVector=(1, 0, 0), upVector=(0, 1, 0), worldUpType="scene")
        cmds.delete(norm_con)
        cmds.rotate(offsets[0], offsets[1], offsets[2], jnt, relative=True, os=True)
        
        rot = cmds.getAttr(f"{jnt}.r")[0]
        cmds.setAttr(f"{jnt}.jo", rot[0], rot[1], rot[2])
        cmds.setAttr(f"{jnt}.r", 0, 0, 0)
        
        # --- BENDY 1 ---
        bend1_nodes = cmds.nonLinear(geo_name, type='bend', lowBound=0, highBound=2)
        bend1_node, bend1_handle = bend1_nodes[0], bend1_nodes[1]
        cmds.rename(bend1_handle, f"bendMain_petal_{i:02d}")
        bend1_handle = f"bendMain_petal_{i:02d}"
        cmds.matchTransform(bend1_handle, jnt, pos=True, rot=True)
        cmds.rotate(0, 0, 45, bend1_handle, relative=True, os=True)
        cmds.parent(bend1_handle, deform_grp)

        # --- BENDY 2 ---
        bend2_nodes = cmds.nonLinear(geo_name, type='bend', lowBound=0, highBound=2)
        bend2_node, bend2_handle = bend2_nodes[0], bend2_nodes[1]
        cmds.rename(bend2_handle, f"bendSide_petal_{i:02d}")
        bend2_handle = f"bendSide_petal_{i:02d}"
        cmds.matchTransform(bend2_handle, jnt, pos=True, rot=True)
        cmds.rotate(0, 0, 45, bend2_handle, relative=True, os=True)
        cmds.rotate(0, 90, 0, bend2_handle, relative=True, os=True)
        cmds.parent(bend2_handle, deform_grp)

        # --- CONTROL ---
        ctrl = cmds.circle(nr=(0, 1, 0), r=calc_radius, name=f"ct_petal_{i:02d}")[0]
        ctrl_ofs = cmds.group(ctrl, name=f"grp_petal_{i:02d}_OFS")
        cmds.parent(ctrl_ofs, controls_grp)
        cmds.matchTransform(ctrl_ofs, jnt, pos=True, rot=True)
        
        cmds.rotate(0, 0, 90, f"{ctrl}.cv[*]", relative=True, os=True)
        offset_vec = [target_vtx_pos[0]-jnt_pos[0], target_vtx_pos[1]-jnt_pos[1], target_vtx_pos[2]-jnt_pos[2]]
        cmds.move(offset_vec[0], offset_vec[1], offset_vec[2], f"{ctrl}.cv[*]", r=True, ws=True)

        cmds.addAttr(ctrl, ln="curvature", at="double", dv=0, k=True)
        cmds.addAttr(ctrl, ln="sideTilt", at="double", dv=0, k=True)
        cmds.connectAttr(f"{ctrl}.curvature", f"{bend1_node}.curvature")
        cmds.connectAttr(f"{ctrl}.sideTilt", f"{bend2_node}.curvature")

        # Constraints
        cmds.parentConstraint(ctrl, bend1_handle, mo=True)
        cmds.parentConstraint(ctrl, bend2_handle, mo=True)
        cmds.parentConstraint(ctrl, jnt, mo=True)

        cmds.setAttr(f"{ctrl}.overrideEnabled", 1)
        cmds.setAttr(f"{ctrl}.overrideColor", random.choice(bright_colors))
        
        # --- BINDING & INPUT ORDER ---
        existing_skin = cmds.ls(cmds.listHistory(geo_name), type='skinCluster')
        if not existing_skin:
            cmds.skinCluster(jnt, geo_name, tsb=True, mi=1, dr=4)
        else:
            cmds.skinCluster(existing_skin[0], edit=True, ai=jnt, lw=True, wt=0)
            
        # FINAL STEP: Ensure Bendy -> SkinCluster order
        fix_deformation_order(geo_name)

# --- UI ---
def create_ui():
    win_id = "LotusRig_Master_V6"
    if cmds.window(win_id, exists=True): cmds.deleteUI(win_id)
    cmds.window(win_id, title="Lotus Rig TD - V6", widthHeight=(350, 240))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=['both', 10])
    
    cmds.text(label="Lotus Production Rig V6", fn="boldLabelFont", height=30)
    multiplier_field = cmds.floatField(value=0.7, pre=2)
    offset_fields = cmds.floatFieldGrp(numberOfFields=3, value1=0, value2=0, value3=0)
    
    def on_execute(*args):
        offs = [cmds.floatFieldGrp(offset_fields, q=True, v1=True),
                cmds.floatFieldGrp(offset_fields, q=True, v2=True),
                cmds.floatFieldGrp(offset_fields, q=True, v3=True)]
        mult = cmds.floatField(multiplier_field, q=True, v=True)
        run_lotus_rig_v6(mult, offs)
        print("# Success: Lotus Rig V6 built. Input order: Bendy -> SkinCluster.")

    cmds.button(label="Generate Lotus Rig", command=on_execute, bgc=(0.3, 0.4, 0.2), height=50)
    cmds.showWindow(win_id)

create_ui()