import maya.cmds as cmds
from mgear.shifter import guide_manager
import mgear.shifter as shifter

class MultiRigBuilder(object):
    def __init__(self):
        self.window_name = "mGear_Multi_Grid_Builder"
        self.generated_guides = []
        self.show_ui()

    def show_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        cmds.window(self.window_name, title="Grid Rig Builder", widthHeight=(280, 360))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=('both', 10))
        
        cmds.text(label="Grid Settings", font="boldLabelFont", height=20)
        self.rows_fld = cmds.intFieldGrp(numberOfFields=1, label='Rows:', value1=2, columnWidth2=[80, 80])
        self.cols_fld = cmds.intFieldGrp(numberOfFields=1, label='Columns:', value1=2, columnWidth2=[80, 80])
        self.spc_x_fld = cmds.floatFieldGrp(numberOfFields=1, label='Spacing X:', value1=15.0, columnWidth2=[80, 80])
        self.spc_z_fld = cmds.floatFieldGrp(numberOfFields=1, label='Spacing Z:', value1=15.0, columnWidth2=[80, 80])
        
        cmds.separator(h=5, style='in')
        
        cmds.button(label="1. Create Ref Joints (Grid)", command=self.create_ref_joints, height=30)
        cmds.button(label="2. Draw & Snap Guides (Selection)", command=self.draw_and_snap_guide, height=30)
        cmds.button(label="3. Build Unified Rig", command=self.build_rigs, height=30)
        
        cmds.separator(h=5, style='in')
        
        # Updated Feature: Combined Button for 2 and 3
        cmds.button(label="🌟 Auto Snap & Build (2 + 3)", command=self.auto_snap_and_build, height=35, backgroundColor=(0.2, 0.4, 0.3))
        
        cmds.separator(h=5, style='in')
        
        cmds.button(label="🗑️ Smart Delete Rig (Auto-Detect)", command=self.delete_selected_rig, height=35, backgroundColor=(0.5, 0.2, 0.2))
        
        cmds.showWindow(self.window_name)

    def get_grid_params(self):
        rows = cmds.intFieldGrp(self.rows_fld, q=True, value1=True)
        cols = cmds.intFieldGrp(self.cols_fld, q=True, value1=True)
        spc_x = cmds.floatFieldGrp(self.spc_x_fld, q=True, value1=True)
        spc_z = cmds.floatFieldGrp(self.spc_z_fld, q=True, value1=True)
        return rows, cols, spc_x, spc_z

    def create_ref_joints(self, *args):
        rows, cols, spc_x, spc_z = self.get_grid_params()
        cmds.select(clear=True)
        
        if not cmds.objExists("ref_joints_grp"):
            cmds.group(em=True, n="ref_joints_grp")

        index = 0
        for r in range(rows):
            for c in range(cols):
                offset_x = c * spc_x
                offset_z = r * spc_z
                
                root_jnt = "arm_C{}_root_jnt".format(index)
                if not cmds.objExists(root_jnt):
                    cmds.select(clear=True)
                    cmds.joint(n=root_jnt, p=(2 + offset_x, 15, 0 + offset_z))
                    cmds.joint(n="arm_C{}_elbow_jnt".format(index), p=(7 + offset_x, 15, -1 + offset_z))
                    cmds.joint(n="arm_C{}_wrist_jnt".format(index), p=(12 + offset_x, 15, 0 + offset_z))
                    cmds.joint(n="arm_C{}_eff_jnt".format(index), p=(14 + offset_x, 15, 0 + offset_z))
                    
                    cmds.parent(root_jnt, "ref_joints_grp")
                else:
                    cmds.warning("{} already exists! Skipping creation.".format(root_jnt))
                    
                index += 1
        print("Generated {} reference joint chains.".format(index))

    def draw_and_snap_guide(self, *args):
        selection = cmds.ls(selection=True, type="joint")
        if not selection:
            cmds.warning("Please select the root joint(s) of the reference chains (e.g., arm_C0_root_jnt).")
            return

        self.generated_guides = []
        
        main_guide_group = None
        existing_guides = cmds.ls("guide", type="transform")
        if existing_guides:
            main_guide_group = existing_guides[0]
        
        success_count = 0
        
        for ref_root in selection:
            parts = ref_root.split('_')
            if len(parts) < 4 or not ref_root.endswith("_root_jnt"):
                cmds.warning("Skipping '{}': Naming format must be like 'arm_C0_root_jnt'.".format(ref_root))
                continue
                
            comp_name = parts[0]
            side_index = parts[1]
            comp_side = side_index[0]
            try:
                comp_index = int(side_index[1:])
            except ValueError:
                comp_index = 0
                
            new_base = "{}_{}{}_".format(comp_name, comp_side, comp_index)
            expected_new_root = new_base + "root"

            if cmds.objExists(expected_new_root):
                cmds.warning("Guide '{}' already exists. Skipping spawn to prevent clashes.".format(expected_new_root))
                continue

            ref_chain = [ref_root]
            children = cmds.listRelatives(ref_root, allDescendents=True, type="joint") or []
            children.reverse() 
            ref_chain.extend(children)
            
            if len(ref_chain) < 4:
                cmds.warning("Skipping '{}': Not enough child joints in chain.".format(ref_root))
                continue
            
            roots_before = set(cmds.ls("*_root", type="transform"))
            cmds.select(clear=True) 
            
            guide_manager.draw_comp("EPIC_arm_02", parent=None, showUI=False)
            
            roots_after = set(cmds.ls("*_root", type="transform"))
            new_roots = list(roots_after - roots_before)
            
            if not new_roots:
                cmds.warning("Failed to detect new guide for {}. Skipping.".format(ref_root))
                continue
                
            spawned_root = new_roots[0]
            spawned_root_short = spawned_root.split('|')[-1]
            old_base = spawned_root_short.replace("root", "")
            
            nodes_to_rename = [spawned_root] + (cmds.listRelatives(spawned_root, ad=True, type="transform") or [])
            nodes_to_rename.sort(key=lambda x: len(cmds.ls(x, long=True)[0].split('|')), reverse=True) 
            
            for node in nodes_to_rename:
                short_name = node.split('|')[-1]
                if old_base in short_name:
                    new_name = short_name.replace(old_base, new_base)
                    cmds.rename(node, new_name)
                    
            if cmds.objExists(expected_new_root):
                cmds.setAttr(expected_new_root + ".comp_name", comp_name, type="string")
                cmds.setAttr(expected_new_root + ".comp_side", comp_side, type="string")
                cmds.setAttr(expected_new_root + ".comp_index", comp_index)
                
                guide_chain = [
                    expected_new_root,
                    new_base + "elbow",
                    new_base + "wrist",
                    new_base + "eff"
                ]
                
                for ref_jnt, guide_node in zip(ref_chain[:4], guide_chain):
                    if cmds.objExists(ref_jnt) and cmds.objExists(guide_node):
                        pc = cmds.pointConstraint(ref_jnt, guide_node, offset=[0,0,0], weight=1)[0]
                        cmds.delete(pc)
                        oc = cmds.orientConstraint(ref_jnt, guide_node, offset=[0,0,0], weight=1)[0]
                        cmds.delete(oc)
                    else:
                        cmds.warning("Missing node during snap: {} or {}".format(ref_jnt, guide_node))
                        
                current_parent = cmds.listRelatives(expected_new_root, parent=True)
                if not main_guide_group:
                    if current_parent:
                        main_guide_group = current_parent[0]
                    else:
                        main_guide_group = cmds.group(em=True, n="guide")
                        cmds.parent(expected_new_root, main_guide_group)
                else:
                    if current_parent:
                        if current_parent[0] != main_guide_group:
                            cmds.parent(expected_new_root, main_guide_group)
                            # Force delete the redundant guide group entirely, including its controllers_org
                            cmds.delete(current_parent[0])
                    else:
                        cmds.parent(expected_new_root, main_guide_group)
                        
                self.generated_guides.append(expected_new_root)
                success_count += 1
            else:
                cmds.warning("Renaming failed to resolve expected root name: {}".format(expected_new_root))
        
        # Extra garbage collection: sweep for any stray, empty/useless guide groups spawned by mGear
        all_guides = cmds.ls("guide*", type="transform")
        for g in all_guides:
            if g != main_guide_group and cmds.objExists(g):
                children = cmds.listRelatives(g, children=True, type="transform") or []
                if len(children) == 0 or (len(children) == 1 and children[0].endswith("controllers_org")):
                    cmds.delete(g)
                    
        print("Successfully processed {} guides into '{}' group.".format(success_count, main_guide_group))
        cmds.select(selection, r=True)

    def auto_snap_and_build(self, *args):
        # Executes Step 2 based on selection
        self.draw_and_snap_guide()
        
        # Executes Step 3 if guides were generated
        if self.generated_guides:
            self.build_rigs()
        else:
            cmds.warning("No guides were generated. Rig build aborted.")

    def build_rigs(self, *args):
        existing_guides = cmds.ls("guide", type="transform")
        if not existing_guides:
            cmds.warning("No 'guide' group found. Run 'Draw & Snap Guides' first.")
            return
            
        cmds.select(existing_guides[0], r=True)
        try:
            shifter.Rig().buildFromSelection()
            print("Successfully built Unified mGear Rig!")
        except Exception as e:
            cmds.error("Failed to build rig: {}".format(e))

    def delete_selected_rig(self, *args):
        selection = cmds.ls(selection=True, long=True)
        if not selection:
            cmds.warning("Please select a part of the Rig, Guide, or Ref Joints to delete.")
            return

        nodes_to_delete = set()
        default_cameras = ["|persp", "|top", "|front", "|side"]

        for sel in selection:
            current = sel
            root_found = None

            while current:
                if cmds.objExists(current + ".is_rig"):
                    root_found = current
                elif cmds.objExists(current + ".ismodel"):
                    root_found = current
                elif current.endswith("|ref_joints_grp") or current == "ref_joints_grp":
                    root_found = current

                parent = cmds.listRelatives(current, parent=True, fullPath=True)
                if parent:
                    current = parent[0]
                else:
                    break

            if not root_found:
                current = sel
                while current:
                    if current.split("|")[-1].endswith("_root_jnt"):
                        root_found = current
                    parent = cmds.listRelatives(current, parent=True, fullPath=True)
                    if parent:
                        current = parent[0]
                    else:
                        break

            if not root_found:
                top_node = sel
                parent = cmds.listRelatives(top_node, parent=True, fullPath=True)
                while parent:
                    top_node = parent[0]
                    parent = cmds.listRelatives(top_node, parent=True, fullPath=True)
                root_found = top_node

            if root_found and root_found not in default_cameras:
                nodes_to_delete.add(root_found)

        if nodes_to_delete:
            for node in nodes_to_delete:
                if cmds.objExists(node):
                    cmds.delete(node)
                    print("🧹 Successfully completely deleted hierarchy: {}".format(node))
        else:
            cmds.warning("Could not detect a valid hierarchy to delete.")

MultiRigBuilder()