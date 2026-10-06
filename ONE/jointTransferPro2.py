import os
import json
import numpy as np
import maya.api.OpenMaya as om
import maya.cmds as cmds


import re
import sys
import importlib

sys.path.append(r"P:/rigging_team/Pipeline_share/RigUtils")
import UniUtils
importlib.reload(UniUtils)

class HierarchicalJointSphereKabschUI:

    DEFAULT_MESH = "FullBodyJntTransfer_01:CC_Base_Body"

    REFERENCE_FILE_PATH = "P:/rigging_team/Pipeline_share/RigUtils/FullBodyJntTransfer/FullBodyJntTransfer_01.ma"
    REFERENCE_NAMESPACE = "FullBodyJntTransfer_01"

    DEFAULT_JOINTS = [
        "CC_Base_BoneRoot",
        "CC_Base_Hip",
        "CC_Base_Pelvis",
        "CC_Base_L_Thigh",
        "CC_Base_L_Calf",
        "CC_Base_L_Foot",
        "CC_Base_L_ToeBaseShareBone",
        "CC_Base_L_ToeBase",
        "CC_Base_L_PinkyToe1",
        "CC_Base_L_RingToe1",
        "CC_Base_L_MidToe1",
        "CC_Base_L_IndexToe1",
        "CC_Base_L_BigToe1",
        "CC_Base_L_CalfTwist01",
        "CC_Base_L_CalfTwist02",
        "CC_Base_L_KneeShareBone",
        "CC_Base_L_ThighTwist01",
        "CC_Base_L_ThighTwist02",
        "CC_Base_R_Thigh",
        "CC_Base_R_Calf",
        "CC_Base_R_KneeShareBone",
        "CC_Base_R_Foot",
        "CC_Base_R_ToeBase",
        "CC_Base_R_BigToe1",
        "CC_Base_R_PinkyToe1",
        "CC_Base_R_RingToe1",
        "CC_Base_R_IndexToe1",
        "CC_Base_R_MidToe1",
        "CC_Base_R_ToeBaseShareBone",
        "CC_Base_R_CalfTwist01",
        "CC_Base_R_CalfTwist02",
        "CC_Base_R_ThighTwist01",
        "CC_Base_R_ThighTwist02",
        "CC_Base_Waist",
        "CC_Base_Spine01",
        "CC_Base_Spine02",
        "CC_Base_NeckTwist01",
        "CC_Base_NeckTwist02",
        "CC_Base_Head",
        "CC_Base_FacialBone",
        "CC_Base_JawRoot",
        "CC_Base_Tongue01",
        "CC_Base_Tongue02",
        "CC_Base_Tongue03",
        "CC_Base_Teeth02",
        "CC_Base_R_Eye",
        "CC_Base_L_Eye",
        "CC_Base_UpperJaw",
        "CC_Base_Teeth01",
        "CC_Base_L_Clavicle",
        "CC_Base_L_Upperarm",
        "CC_Base_L_Forearm",
        "CC_Base_L_ForearmTwist01",
        "CC_Base_L_ForearmTwist02",
        "CC_Base_L_ElbowShareBone",
        "CC_Base_L_Hand",
        "CC_Base_L_Pinky1",
        "CC_Base_L_Pinky2",
        "CC_Base_L_Pinky3",
        "CC_Base_L_Ring1",
        "CC_Base_L_Ring2",
        "CC_Base_L_Ring3",
        "CC_Base_L_Mid1",
        "CC_Base_L_Mid2",
        "CC_Base_L_Mid3",
        "CC_Base_L_Index1",
        "CC_Base_L_Index2",
        "CC_Base_L_Index3",
        "CC_Base_L_Thumb1",
        "CC_Base_L_Thumb2",
        "CC_Base_L_Thumb3",
        "CC_Base_L_UpperarmTwist01",
        "CC_Base_L_UpperarmTwist02",
        "CC_Base_L_RibsTwist",
        "CC_Base_L_Breast",
        "CC_Base_R_RibsTwist",
        "CC_Base_R_Breast",
        "CC_Base_R_Clavicle",
        "CC_Base_R_Upperarm",
        "CC_Base_R_Forearm",
        "CC_Base_R_ElbowShareBone",
        "CC_Base_R_ForearmTwist01",
        "CC_Base_R_ForearmTwist02",
        "CC_Base_R_Hand",
        "CC_Base_R_Ring1",
        "CC_Base_R_Ring2",
        "CC_Base_R_Ring3",
        "CC_Base_R_Mid1",
        "CC_Base_R_Mid2",
        "CC_Base_R_Mid3",
        "CC_Base_R_Thumb1",
        "CC_Base_R_Thumb2",
        "CC_Base_R_Thumb3",
        "CC_Base_R_Index1",
        "CC_Base_R_Index2",
        "CC_Base_R_Index3",
        "CC_Base_R_Pinky1",
        "CC_Base_R_Pinky2",
        "CC_Base_R_Pinky3",
        "CC_Base_R_UpperarmTwist01",
        "CC_Base_R_UpperarmTwist02",
        "meta_L0_root1",
        "meta_L0_0_loc1",
        "meta_L0_1_loc1",
        "meta_L0_2_loc1",
        "meta_R0_root1",
        "meta_R0_0_loc1",
        "meta_R0_1_loc1",
        "meta_R0_2_loc1",
    ]

    DEFAULT_UNCHECKED_JOINTS = {
        "CC_Base_FacialBone",
        "CC_Base_JawRoot",
        "CC_Base_Tongue01",
        "CC_Base_Tongue02",
        "CC_Base_Tongue03",
        "CC_Base_Teeth02",
        "CC_Base_R_Eye",
        "CC_Base_L_Eye",
        "CC_Base_UpperJaw",
        "CC_Base_Teeth01",
    }

    def __init__(self):
        self.stored_data = {}
        self.mesh = self.DEFAULT_MESH
        self.joints = list(self.DEFAULT_JOINTS)
        self.joint_checkboxes = {}
        self.window_name = "HierarchicalJointSphereKabschWindow"
        self.create_ui()

    def create_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
        if cmds.windowPref(self.window_name, exists=True):
            cmds.windowPref(self.window_name, remove=True)

        self.window = cmds.window(
            self.window_name,
            title="Hierarchical Joint Relocator",
            widthHeight=(480, 890),
            sizeable=True,
        )

        # Tabs at the top to switch between tools
        self.tabs = cmds.tabLayout(innerMarginWidth=5, innerMarginHeight=5)

        self.main_scroll = cmds.scrollLayout(childResizable=True)

        cmds.columnLayout(
            adjustableColumn=True, rowSpacing=8, columnOffset=["both", 10]
        )

        # Section 0: Reference & Blendshape Utilities
        cmds.text(
            label="0. Reference & Blendshape",
            font="boldLabelFont",
            align="center",
        )

        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.button(
            label="Load Reference",
            height=30,
            backgroundColor=[0.25, 0.45, 0.35],
            annotation=self.REFERENCE_FILE_PATH,
            command=self.btn_load_reference,
        )
        cmds.button(
            label="Create BlendShape (Select 2 Meshes)",
            height=30,
            backgroundColor=[0.35, 0.35, 0.5],
            annotation="Select source mesh first, then target mesh. Topology check is off.",
            command=self.btn_create_blendshape,
        )
        cmds.button(
            label="Remove Reference",
            height=30,
            backgroundColor=[0.5, 0.3, 0.3],
            annotation=self.REFERENCE_FILE_PATH,
            command=self.btn_remove_reference,
        )
        cmds.setParent("..")

        cmds.separator(height=10, style="single")

        # Section 1: Setup Inputs & Namespaces
        cmds.text(
            label="1. Setup Joints, Mesh & Namespaces",
            font="boldLabelFont",
            align="center",
        )

        cmds.rowLayout(numberOfColumns=4, adjustableColumn=2)
        cmds.text(label="Detect NS: ")
        self.txt_det_ns = cmds.textField(
            text="FullBodyJntTransfer_01:",
            annotation="Namespace for detection hierarchy",
        )
        cmds.text(label="Repose NS: ")
        self.txt_tgt_ns = cmds.textField(
            text="",
            annotation="Namespace for target reposition hierarchy (leave empty if none)",
        )
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        self.lbl_joints_count = cmds.text(
            label="Target Joints Loaded: {}".format(len(self.joints)),
            align="left",
        )
        cmds.button(
            label="Load Selected Joints",
            command=self.load_joints,
            backgroundColor=[0.25, 0.25, 0.35],
        )
        cmds.setParent("..")

        cmds.text(
            label="Active Joints (Uncheck to keep static):",
            align="left",
            font="obliqueLabelFont",
        )
        self.joints_scroll_layout = cmds.scrollLayout(
            height=140, childResizable=True
        )
        cmds.columnLayout(adjustableColumn=True)
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.text(label="Target Mesh: ")
        self.txt_mesh = cmds.textField(text=self.mesh)
        cmds.button(label="Load Selected", command=self.load_mesh)
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.text(label="Spheres Per Joint: ", align="left")
        self.if_num_spheres = cmds.intField(value=1, minValue=1, maxValue=10)
        cmds.setParent("..")

        cmds.button(
            label="Create / Reset Spheres for Active Joints",
            height=30,
            backgroundColor=[0.3, 0.35, 0.45],
            command=self.create_bounding_spheres,
        )

        cmds.button(
            label="+ Add Extra Sphere to Selected Joint",
            height=25,
            backgroundColor=[0.35, 0.4, 0.5],
            command=self.add_extra_sphere,
        )

        cmds.separator(height=10, style="single")

        # Section 2: Calculate & Reposition
        cmds.text(
            label="2. Calculate & Batch Reposition",
            font="boldLabelFont",
            align="center",
        )

        cmds.button(
            label="1. Detect Vertices & Store Reference (Detection Joints)",
            height=35,
            backgroundColor=[0.2, 0.4, 0.5],
            command=self.btn_calculate,
        )

        cmds.button(
            label="2. Reposition Target Joints (Skin-Preserved)",
            height=35,
            backgroundColor=[0.3, 0.5, 0.3],
            command=self.btn_reposition,
        )

        cmds.text(
            label="Invalid Spheres (< 5 Vertices) - Click item to select sphere:",
            align="left",
            font="obliqueLabelFont",
        )
        self.tsl_invalid_spheres = cmds.textScrollList(
            height=80,
            allowMultiSelection=False,
            selectCommand=self.on_select_invalid_sphere,
        )

        cmds.separator(height=10, style="single")

        # Section 3: JSON Presets
        cmds.text(
            label="3. JSON Presets (Sphere Transforms)",
            font="boldLabelFont",
            align="center",
        )

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(
            label="Export Spheres to JSON",
            height=30,
            backgroundColor=[0.25, 0.45, 0.4],
            command=self.export_json,
        )
        cmds.button(
            label="Import Spheres from JSON",
            height=30,
            backgroundColor=[0.45, 0.4, 0.25],
            command=self.import_json,
        )
        cmds.setParent("..")

        cmds.separator(height=10, style="single")

        # Section 4: Visibility & Utilities
        cmds.text(
            label="4. Sphere Visibility & Utilities",
            font="boldLabelFont",
            align="center",
        )

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(
            label="Hide Active Spheres",
            command=self.hide_active_spheres,
            backgroundColor=[0.3, 0.35, 0.4],
        )
        cmds.button(
            label="Show Active Spheres",
            command=self.show_active_spheres,
            backgroundColor=[0.35, 0.4, 0.35],
        )
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(
            label="Hide ALL Spheres",
            command=self.hide_all_spheres,
            backgroundColor=[0.25, 0.3, 0.35],
        )
        cmds.button(
            label="Show ALL Spheres",
            command=self.show_all_spheres,
            backgroundColor=[0.3, 0.35, 0.3],
        )
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        cmds.button(
            label="Delete Active Spheres",
            command=self.delete_loaded_spheres,
            backgroundColor=[0.45, 0.3, 0.3],
        )
        cmds.button(
            label="Delete ALL Spheres",
            command=self.delete_all_spheres,
            backgroundColor=[0.55, 0.25, 0.25],
        )
        cmds.setParent("..")

        cmds.separator(height=10, style="none")

        cmds.button(
            label="Revert / Undo Target Joints & Spheres",
            height=30,
            backgroundColor=[0.5, 0.2, 0.2],
            command=self.btn_revert,
        )

        cmds.separator(height=10, style="none")
        self.lbl_status = cmds.text(
            label="Status: Loaded default preset joints & mesh.", align="left"
        )
        cmds.separator(height=10, style="none")

        cmds.setParent("..")
        cmds.setParent("..")

        # Tab 2: Finger Fix Tool
        cmds.setParent(self.tabs)
        self.finger_tab = cmds.scrollLayout(childResizable=True)
        try:
            self.finger_tool = HandRigMatchingUI(parent=self.finger_tab)
        except NameError:
            self.finger_tool = None
            cmds.columnLayout(adjustableColumn=True)
            cmds.text(label="HandRigMatchingUI class not found.\nRun the full script file.")
            cmds.setParent("..")
            cmds.warning("HandRigMatchingUI class missing - Finger Fix tab disabled.")

        cmds.tabLayout(
            self.tabs,
            edit=True,
            tabLabel=[
                (self.main_scroll, "Joint Relocator"),
                (self.finger_tab, "Finger Fix"),
            ],
        )

        self.rebuild_joints_checkbox_ui()
        cmds.showWindow(self.window)

    # ------------------------------------------------------------------
    # Reference & Blendshape utilities
    # ------------------------------------------------------------------
    def _get_uniutils(self):
        try:
            import UniUtils
            return UniUtils
        except ImportError:
            cmds.warning("Could not import UniUtils. Make sure it is on the Python path.")
            return None

    def btn_load_reference(self, *args):
        uni = self._get_uniutils()
        if not uni:
            return
        uni.reference_file(self.REFERENCE_FILE_PATH, self.REFERENCE_NAMESPACE)
        cmds.inViewMessage(
            amg="Referenced '{}'".format(self.REFERENCE_NAMESPACE),
            pos="topCenter",
            fade=True,
        )

    def btn_remove_reference(self, *args):
        uni = self._get_uniutils()
        if not uni:
            return
        uni.remove_reference(self.REFERENCE_FILE_PATH)
        cmds.inViewMessage(
            amg="Removed reference '{}'".format(self.REFERENCE_NAMESPACE),
            pos="topCenter",
            fade=True,
        )

    def btn_create_blendshape(self, *args):
        sel = cmds.ls(selection=True, transforms=True) or []
        meshes = [
            s for s in sel
            if cmds.listRelatives(s, shapes=True, type="mesh", noIntermediate=True)
        ]
        if len(meshes) != 2:
            cmds.warning("Please select exactly 2 meshes (source first, then target).")
            return

        source, target = meshes
        bs_node = cmds.blendShape(source, target, topologyCheck=False)[0]
        cmds.select(target, replace=True)
        cmds.inViewMessage(
            amg="Created blendShape '{}': {} -> {}".format(bs_node, source, target),
            pos="topCenter",
            fade=True,
        )

    def format_joint_with_ns(self, base_joint, ns):
        if not ns or not ns.strip():
            return base_joint
        clean_ns = ns.strip().rstrip(":")
        return "{}:{}".format(clean_ns, base_joint)

    def get_detection_namespace(self):
        return cmds.textField(self.txt_det_ns, query=True, text=True)

    def get_target_namespace(self):
        return cmds.textField(self.txt_tgt_ns, query=True, text=True)

    def select_joint_in_maya(self, base_joint_name):
        det_ns = self.get_detection_namespace()
        det_jnt = self.format_joint_with_ns(base_joint_name, det_ns)
        if cmds.objExists(det_jnt):
            cmds.select(det_jnt, replace=True)
            return

        tgt_ns = self.get_target_namespace()
        tgt_jnt = self.format_joint_with_ns(base_joint_name, tgt_ns)
        if cmds.objExists(tgt_jnt):
            cmds.select(tgt_jnt, replace=True)

    def load_joints(self, *args):
        sel = cmds.ls(selection=True, type="joint")
        if not sel:
            sel = [
                obj
                for obj in cmds.ls(selection=True)
                if cmds.nodeType(obj) == "joint"
            ]

        if sel:
            base_joints = [j.split("|")[-1].split(":")[-1] for j in sel]
            self.joints = list(dict.fromkeys(base_joints))
            self.rebuild_joints_checkbox_ui()
            cmds.text(
                self.lbl_joints_count,
                edit=True,
                label="Target Joints Loaded: {}".format(len(self.joints)),
            )
            cmds.inViewMessage(
                amg="Loaded {} joints from selection!".format(len(self.joints)),
                pos="topCenter",
                fade=True,
            )
        else:
            cmds.warning("Please select one or more Joints in the scene.")

    def rebuild_joints_checkbox_ui(self):
        children = (
            cmds.scrollLayout(
                self.joints_scroll_layout, query=True, childArray=True
            )
            or []
        )
        for child in children:
            cmds.deleteUI(child)

        cmds.setParent(self.joints_scroll_layout)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
        self.joint_checkboxes = {}

        for base_jnt in self.joints:
            default_state = base_jnt not in self.DEFAULT_UNCHECKED_JOINTS

            cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
            cb = cmds.checkBox(
                label=base_jnt,
                value=default_state,
                annotation="Uncheck to keep '{}' static during repose".format(base_jnt),
                changeCommand=lambda val, j=base_jnt: self.select_joint_in_maya(j),
            )
            cmds.button(
                label="Select",
                width=50,
                backgroundColor=[0.3, 0.3, 0.4],
                command=lambda x, j=base_jnt: self.select_joint_in_maya(j),
            )
            cmds.setParent("..")

            self.joint_checkboxes[base_jnt] = cb

        cmds.setParent("..")

    def get_active_joints(self):
        active_joints = []
        for base_jnt in self.joints:
            cb = self.joint_checkboxes.get(base_jnt)
            if cb and cmds.checkBox(cb, exists=True):
                if cmds.checkBox(cb, query=True, value=True):
                    active_joints.append(base_jnt)
        return active_joints

    def load_mesh(self, *args):
        sel = cmds.ls(selection=True, transforms=True)
        if sel:
            self.mesh = sel[0]
            cmds.textField(self.txt_mesh, edit=True, text=self.mesh)
            cmds.inViewMessage(
                amg="Loaded mesh '{}'!".format(self.mesh),
                pos="topCenter",
                fade=True,
            )
        else:
            cmds.warning("Please select a target Mesh transform.")

    def get_spheres_for_joint(self, base_joint_name):
        prefix = "{}_bounding_sphere".format(base_joint_name)
        spheres = cmds.ls("*{}*".format(prefix), transforms=True) or []
        valid_spheres = [
            s for s in spheres if s.split("|")[-1].startswith(prefix)
        ]
        return valid_spheres

    def get_dag_depth(self, obj_name):
        long_names = cmds.ls(obj_name, long=True)
        if long_names:
            return len(long_names[0].split("|"))
        return 0

    def _create_single_sphere(self, sphere_name, position):
        if cmds.objExists(sphere_name):
            cmds.delete(sphere_name)

        sphere_nodes = cmds.polySphere(
            name=sphere_name, radius=1.0, subdivisionsX=16, subdivisionsY=16
        )
        sphere_transform = sphere_nodes[0]
        cmds.xform(sphere_transform, worldSpace=True, translation=position)

        shapes = cmds.listRelatives(sphere_transform, shapes=True)
        if shapes:
            cmds.setAttr(shapes[0] + ".overrideEnabled", 1)
            cmds.setAttr(shapes[0] + ".overrideShading", 0)

        for attr in ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"]:
            cmds.setAttr("{}.{}".format(sphere_transform, attr), lock=False)

        return sphere_transform

    def create_bounding_spheres(self, *args):
        active_base_joints = self.get_active_joints()
        if not active_base_joints:
            cmds.error("No active/checked joints to process.")
            return

        det_ns = self.get_detection_namespace()
        num_spheres = cmds.intField(self.if_num_spheres, query=True, value=True)
        created_count = 0

        for base_jnt in active_base_joints:
            det_jnt = self.format_joint_with_ns(base_jnt, det_ns)
            if not cmds.objExists(det_jnt):
                continue

            existing = self.get_spheres_for_joint(base_jnt)
            if existing:
                cmds.delete(existing)

            joint_pos = cmds.xform(
                det_jnt, query=True, worldSpace=True, translation=True
            )

            for i in range(1, num_spheres + 1):
                sphere_name = "{}_bounding_sphere_{}".format(base_jnt, i)
                self._create_single_sphere(sphere_name, joint_pos)
                created_count += 1

        cmds.inViewMessage(
            amg="Created {} bounding spheres for active joints!".format(created_count),
            pos="topCenter",
            fade=True,
        )

    def add_extra_sphere(self, *args):
        det_ns = self.get_detection_namespace()
        active_base_joints = set(self.get_active_joints())
        
        sel = cmds.ls(selection=True, type="joint")
        if sel:
            sel_base_joints = [
                j.split("|")[-1].split(":")[-1]
                for j in sel
                if j.split("|")[-1].split(":")[-1] in active_base_joints
            ]
        else:
            sel_base_joints = list(active_base_joints)

        if not sel_base_joints:
            cmds.warning("No active (checked) joint selected.")
            return

        added_count = 0
        for base_jnt in sel_base_joints:
            det_jnt = self.format_joint_with_ns(base_jnt, det_ns)
            if not cmds.objExists(det_jnt):
                continue

            existing = self.get_spheres_for_joint(base_jnt)
            next_idx = len(existing) + 1
            sphere_name = "{}_bounding_sphere_{}".format(base_jnt, next_idx)

            joint_pos = cmds.xform(
                det_jnt, query=True, worldSpace=True, translation=True
            )
            self._create_single_sphere(sphere_name, joint_pos)
            added_count += 1

        cmds.inViewMessage(
            amg="Added {} extra sphere(s)!".format(added_count),
            pos="topCenter",
            fade=True,
        )

    def get_pos(self, name):
        return cmds.xform(name, query=True, worldSpace=True, translation=True)

    def get_vertices_in_spheres(self, mesh_name, sphere_list):
        sel_list = om.MSelectionList()
        sel_list.add(mesh_name)
        dag_path = sel_list.getDagPath(0)
        mfn_mesh = om.MFnMesh(dag_path)

        inv_matrices = []
        for sphere_name in sphere_list:
            m_sphere_world = om.MMatrix(
                cmds.xform(
                    sphere_name, query=True, worldSpace=True, matrix=True
                )
            )
            inv_matrices.append(m_sphere_world.inverse())

        points_world = mfn_mesh.getPoints(om.MSpace.kWorld)
        inside_vtx_names = set()

        for i, pt in enumerate(points_world):
            for m_sphere_inv in inv_matrices:
                pt_local = pt * m_sphere_inv
                dist = om.MVector(
                    pt_local.x, pt_local.y, pt_local.z
                ).length()
                if dist <= 1.0:
                    inside_vtx_names.add("{}.vtx[{}]".format(mesh_name, i))
                    break

        return sorted(list(inside_vtx_names))

    def update_skin_bind_pre_matrix(self, joint_name):
        if not cmds.objExists(joint_name):
            return

        connections = (
            cmds.listConnections(
                "{}.worldMatrix[0]".format(joint_name),
                type="skinCluster",
                connections=True,
                plugs=True,
            )
            or []
        )

        for i in range(0, len(connections), 2):
            dst_plug = connections[i + 1]
            if ".matrix[" in dst_plug:
                skin_node, attr_name = dst_plug.split(".")
                index = attr_name.split("[")[1].split("]")[0]
                world_inv_mat = cmds.getAttr(
                    "{}.worldInverseMatrix[0]".format(joint_name)
                )

                cmds.setAttr(
                    "{}.bindPreMatrix[{}]".format(skin_node, index),
                    world_inv_mat,
                    type="matrix",
                )

    def on_select_invalid_sphere(self):
        selected_items = cmds.textScrollList(
            self.tsl_invalid_spheres, query=True, selectItem=True
        )
        if not selected_items:
            return

        item_str = selected_items[0]
        if " | " in item_str and " -> " in item_str:
            sphere_name = item_str.split(" | ")[1].split(" -> ")[0]
            if cmds.objExists(sphere_name):
                cmds.select(sphere_name, replace=True)

    def _get_detachment_map(self, active_base_joints, tgt_ns):
        """
        Maps all unchecked (inactive) joints that are immediate children 
        of checked (active) joints so they can be temporarily unparented.
        """
        detachment_map = {}
        search_pattern = "{}*".format(tgt_ns) if tgt_ns else "*"
        all_jnts = cmds.ls(search_pattern, type="joint") or []

        for j in all_jnts:
            base_name = j.split("|")[-1].split(":")[-1]
            if base_name not in active_base_joints:
                parent_nodes = cmds.listRelatives(j, parent=True, fullPath=True)
                if parent_nodes:
                    parent_base = parent_nodes[0].split("|")[-1].split(":")[-1]
                    if parent_base in active_base_joints:
                        detachment_map[j] = parent_nodes[0]
                        
        return detachment_map

    def btn_calculate(self, *args):
        mesh_name = cmds.textField(self.txt_mesh, query=True, text=True)
        active_base_joints = self.get_active_joints()
        det_ns = self.get_detection_namespace()
        tgt_ns = self.get_target_namespace()

        if not active_base_joints:
            cmds.error("No active (checked) joints loaded.")
            return
        if not mesh_name or not cmds.objExists(mesh_name):
            cmds.error("Specified Mesh dynamic path does not exist in scene.")
            return

        cmds.textScrollList(self.tsl_invalid_spheres, edit=True, removeAll=True)
        invalid_entries = []
        invalid_joints = set()

        for base_jnt in active_base_joints:
            det_jnt = self.format_joint_with_ns(base_jnt, det_ns)
            if not cmds.objExists(det_jnt):
                continue

            spheres = self.get_spheres_for_joint(base_jnt)
            if not spheres:
                continue

            for s_name in spheres:
                vtx_in_single = self.get_vertices_in_spheres(
                    mesh_name, [s_name]
                )
                count = len(vtx_in_single)
                if count < 5:
                    entry = "{} | {} -> {} vtx".format(
                        det_jnt, s_name, count
                    )
                    invalid_entries.append(entry)
                    invalid_joints.add(base_jnt)

        if invalid_entries:
            for entry in invalid_entries:
                cmds.textScrollList(
                    self.tsl_invalid_spheres, edit=True, append=entry
                )

        self.stored_data.clear()
        processed_count = 0

        for base_jnt in active_base_joints:
            if base_jnt in invalid_joints:
                continue

            det_jnt = self.format_joint_with_ns(base_jnt, det_ns)
            tgt_jnt = self.format_joint_with_ns(base_jnt, tgt_ns)

            if not cmds.objExists(det_jnt):
                continue

            spheres = self.get_spheres_for_joint(base_jnt)
            if not spheres:
                continue

            vtx_inside = self.get_vertices_in_spheres(mesh_name, spheres)
            if len(vtx_inside) < 3:
                continue

            p_vtx_0 = np.array([self.get_pos(v) for v in vtx_inside])
            p_joint_0 = np.array(self.get_pos(det_jnt))
            c0 = np.mean(p_vtx_0, axis=0)
            N = len(vtx_inside)

            distances = np.linalg.norm(p_vtx_0 - p_joint_0, axis=1)
            weights = np.where(distances < 1e-4, 1e5, 1.0 / (distances**2))
            w_sum = np.sum(weights)
            if w_sum > 0:
                weights /= w_sum

            m_j_init = cmds.xform(
                det_jnt, query=True, worldSpace=True, matrix=True
            )

            init_channels = None
            if cmds.objExists(tgt_jnt):
                init_channels = {
                    "translate": cmds.getAttr(tgt_jnt + ".translate")[0],
                    "rotate": cmds.getAttr(tgt_jnt + ".rotate")[0],
                    "jointOrient": cmds.getAttr(tgt_jnt + ".jointOrient")[0],
                }

            R_j0 = np.array(
                [
                    [m_j_init[0], m_j_init[1], m_j_init[2]],
                    [m_j_init[4], m_j_init[5], m_j_init[6]],
                    [m_j_init[8], m_j_init[9], m_j_init[10]],
                ]
            )
            row_lengths_j = np.linalg.norm(R_j0, axis=1, keepdims=True)
            row_lengths_j = np.where(row_lengths_j < 1e-6, 1.0, row_lengths_j)
            R_j0_norm = R_j0 / row_lengths_j

            spheres_data = []
            for s_name in spheres:
                p_s0 = np.array(self.get_pos(s_name))
                m_s_init = cmds.xform(
                    s_name, query=True, worldSpace=True, matrix=True
                )
                R_s0 = np.array(
                    [
                        [m_s_init[0], m_s_init[1], m_s_init[2]],
                        [m_s_init[4], m_s_init[5], m_s_init[6]],
                        [m_s_init[8], m_s_init[9], m_s_init[10]],
                    ]
                )
                row_lengths_s = np.linalg.norm(R_s0, axis=1, keepdims=True)
                row_lengths_s = np.where(
                    row_lengths_s < 1e-6, 1.0, row_lengths_s
                )
                R_s0_norm = R_s0 / row_lengths_s

                spheres_data.append(
                    {
                        "sphere_name": s_name,
                        "p_sphere_0": p_s0,
                        "m_s_init": m_s_init,
                        "s0_rel": p_s0 - c0,
                        "R_s0_norm": R_s0_norm,
                        "row_lengths_s": row_lengths_s,
                    }
                )

            self.stored_data[base_jnt] = {
                "det_joint": det_jnt,
                "tgt_joint": tgt_jnt,
                "vertices": vtx_inside,
                "spheres": spheres_data,
                "p_vtx_0": p_vtx_0,
                "p_joint_0": p_joint_0,
                "m_j_init": m_j_init,
                "init_channels": init_channels,
                "c0": c0,
                "j0_rel": p_joint_0 - c0,
                "R_j0_norm": R_j0_norm,
                "row_lengths_j": row_lengths_j,
                "weights": weights,
                "N": N,
            }
            processed_count += 1

        if invalid_entries and processed_count > 0:
            status_msg = "Status: Stored frames for {} joints ({} skipped due to < 5 vtx).".format(
                processed_count, len(invalid_joints)
            )
        elif invalid_entries and processed_count == 0:
            status_msg = "ERROR: All spheres have < 5 vertices. Resize/move spheres!"
        else:
            status_msg = "Status: Stored frames for {}/{} active joints.".format(
                processed_count, len(active_base_joints)
            )

        cmds.text(self.lbl_status, edit=True, label=status_msg)
        cmds.inViewMessage(
            amg="Captured frame data for {} active joints!".format(
                processed_count
            ),
            pos="topCenter",
            fade=True,
        )

    def btn_reposition(self, *args):
        if not self.stored_data:
            cmds.warning("Please press button 1 to store initial frames first.")
            return

        active_base_joints = set(self.get_active_joints())
        tgt_ns = self.get_target_namespace()
        
        facial_bone = self.format_joint_with_ns("CC_Base_FacialBone", tgt_ns)
        head_bone = self.format_joint_with_ns("CC_Base_Head", tgt_ns)

        detachment_map = self._get_detachment_map(active_base_joints, tgt_ns)
        target_world_data = {}

        for base_jnt, data in self.stored_data.items():
            if base_jnt not in active_base_joints:
                continue

            tgt_jnt = self.format_joint_with_ns(base_jnt, tgt_ns)
            if not cmds.objExists(tgt_jnt):
                continue

            vertices = data["vertices"]
            p_vtx_0 = data["p_vtx_0"]
            c0 = data["c0"]
            j0_rel = data["j0_rel"]
            R_j0_norm = data["R_j0_norm"]
            row_lengths_j = data["row_lengths_j"]
            weights = data["weights"]

            p_vtx_t = np.array([self.get_pos(v) for v in vertices])
            ct = np.mean(p_vtx_t, axis=0)

            A = p_vtx_0 - c0
            B = p_vtx_t - ct

            H = np.dot(A.T, B)
            U, S, Vt = np.linalg.svd(H)
            R = np.dot(Vt.T, U.T)

            if np.linalg.det(R) < 0:
                Vt[2, :] *= -1
                R = np.dot(Vt.T, U.T)

            var_A = np.sum(A**2)
            scale = np.sum(S) / var_A if var_A > 1e-6 else 1.0

            rigid_j_rel = scale * np.dot(R, j0_rel)
            A_transformed = scale * np.dot(A, R.T)
            residuals = B - A_transformed
            local_deformation_delta = np.sum(
                residuals * weights[:, np.newaxis], axis=0
            )

            target_j_pos = ct + rigid_j_rel + local_deformation_delta

            R_jt_norm = np.dot(R_j0_norm, R.T)
            R_jt_scaled = R_jt_norm * row_lengths_j
            m44_j = [
                R_jt_scaled[0, 0], R_jt_scaled[0, 1], R_jt_scaled[0, 2], 0.0,
                R_jt_scaled[1, 0], R_jt_scaled[1, 1], R_jt_scaled[1, 2], 0.0,
                R_jt_scaled[2, 0], R_jt_scaled[2, 1], R_jt_scaled[2, 2], 0.0,
                target_j_pos[0], target_j_pos[1], target_j_pos[2], 1.0,
            ]

            spheres_target = []
            for s_info in data["spheres"]:
                s_name = s_info["sphere_name"]
                s0_rel = s_info["s0_rel"]
                R_s0_norm = s_info["R_s0_norm"]
                row_lengths_s = s_info["row_lengths_s"]

                rigid_s_rel = scale * np.dot(R, s0_rel)
                target_s_pos = ct + rigid_s_rel + local_deformation_delta

                R_st_norm = np.dot(R_s0_norm, R.T)
                R_st_scaled = R_st_norm * row_lengths_s
                m44_s = [
                    R_st_scaled[0, 0], R_st_scaled[0, 1], R_st_scaled[0, 2], 0.0,
                    R_st_scaled[1, 0], R_st_scaled[1, 1], R_st_scaled[1, 2], 0.0,
                    R_st_scaled[2, 0], R_st_scaled[2, 1], R_st_scaled[2, 2], 0.0,
                    target_s_pos[0], target_s_pos[1], target_s_pos[2], 1.0,
                ]
                spheres_target.append({"name": s_name, "matrix": m44_s})

            target_world_data[tgt_jnt] = {
                "W_j_target": om.MMatrix(m44_j),
                "spheres_target": spheres_target,
            }

        sorted_target_joints = sorted(
            target_world_data.keys(), key=self.get_dag_depth
        )

        cmds.undoInfo(
            openChunk=True, chunkName="HierarchicalJointOrientRelocate"
        )
        try:
            # --- 1. UNPARENT CC_Base_FacialBone TO WORLD ---
            # Python equivalent of: select -r CC_Base_FacialBone ; parent -w;
            has_facial = cmds.objExists(facial_bone)
            if has_facial:
                cmds.parent(facial_bone, world=True)

            # Unparent other inactive branches
            detached_nodes = []
            for child, parent_node in detachment_map.items():
                if cmds.objExists(child) and child != facial_bone:
                    try:
                        cmds.parent(child, world=True)
                        detached_nodes.append((child, parent_node))
                    except Exception as e:
                        cmds.warning("Could not detach child {}: {}".format(child, e))

            # --- 2. REPOSE ACTIVE JOINTS ---
            moved_count = 0
            for tgt_jnt in sorted_target_joints:
                t_data = target_world_data[tgt_jnt]
                W_j_target = t_data["W_j_target"]

                parents = cmds.listRelatives(
                    tgt_jnt, parent=True, type="joint"
                )
                if parents:
                    parent_joint = parents[0]
                    m_parent_world = om.MMatrix(
                        cmds.xform(
                            parent_joint,
                            query=True,
                            worldSpace=True,
                            matrix=True,
                        )
                    )
                    L_j_target = W_j_target * m_parent_world.inverse()
                else:
                    L_j_target = W_j_target

                transform_mat = om.MTransformationMatrix(L_j_target)
                trans = transform_mat.translation(om.MSpace.kTransform)

                rot_order = cmds.getAttr(tgt_jnt + ".rotateOrder")
                euler_rot = transform_mat.rotation(asQuaternion=False)
                euler_rot.reorderIt(rot_order)

                cmds.setAttr(
                    tgt_jnt + ".translate", trans.x, trans.y, trans.z
                )
                cmds.setAttr(
                    tgt_jnt + ".jointOrient",
                    np.degrees(euler_rot.x),
                    np.degrees(euler_rot.y),
                    np.degrees(euler_rot.z),
                )
                cmds.setAttr(tgt_jnt + ".rotate", 0.0, 0.0, 0.0)

                self.update_skin_bind_pre_matrix(tgt_jnt)

                for s_target in t_data["spheres_target"]:
                    s_name = s_target["name"]
                    if cmds.objExists(s_name):
                        cmds.xform(
                            s_name, worldSpace=True, matrix=s_target["matrix"]
                        )

                moved_count += 1

            # --- 3. REPARENT CC_Base_FacialBone TO CC_Base_Head ---
            # Python equivalent of: select -r CC_Base_FacialBone ; select -add CC_Base_Head ; parent;
            if has_facial and cmds.objExists(head_bone):
                cmds.parent(facial_bone, head_bone)

            # Re-attach other inactive branches
            for child, parent_node in detached_nodes:
                if cmds.objExists(child) and cmds.objExists(parent_node):
                    try:
                        cmds.parent(child, parent_node)
                    except Exception as e:
                        cmds.warning("Could not re-attach child {}: {}".format(child, e))

            cmds.text(
                self.lbl_status,
                edit=True,
                label="Status: Posed {} active joints while isolating facial bones!".format(
                    moved_count
                ),
            )
            cmds.inViewMessage(
                amg="Baked position & jointOrient for {} active joints!".format(
                    moved_count
                ),
                pos="topCenter",
                fade=True,
            )
        finally:
            cmds.undoInfo(closeChunk=True)

    def btn_revert(self, *args):
        if not self.stored_data:
            cmds.warning("No stored reference state to revert to.")
            return

        active_base_joints = set(self.get_active_joints())
        tgt_ns = self.get_target_namespace()

        facial_bone = self.format_joint_with_ns("CC_Base_FacialBone", tgt_ns)
        head_bone = self.format_joint_with_ns("CC_Base_Head", tgt_ns)
        detachment_map = self._get_detachment_map(active_base_joints, tgt_ns)

        revert_items = []
        for base_jnt, data in self.stored_data.items():
            if base_jnt not in active_base_joints:
                continue
            tgt_jnt = self.format_joint_with_ns(base_jnt, tgt_ns)
            revert_items.append((tgt_jnt, data))

        sorted_revert_items = sorted(
            revert_items, key=lambda item: self.get_dag_depth(item[0])
        )

        cmds.undoInfo(openChunk=True, chunkName="BatchRevertHierarchicalJoints")
        try:
            # --- 1. UNPARENT FACIAL BONE ---
            has_facial = cmds.objExists(facial_bone)
            if has_facial:
                cmds.parent(facial_bone, world=True)

            detached_nodes = []
            for child, parent_node in detachment_map.items():
                if cmds.objExists(child) and child != facial_bone:
                    try:
                        cmds.parent(child, world=True)
                        detached_nodes.append((child, parent_node))
                    except Exception as e:
                        cmds.warning("Could not detach child {}: {}".format(child, e))

            # --- 2. REVERT ACTIVE JOINTS ---
            reverted_count = 0
            for tgt_jnt, data in sorted_revert_items:
                init_ch = data["init_channels"]

                if cmds.objExists(tgt_jnt) and init_ch:
                    cmds.setAttr(
                        tgt_jnt + ".translate",
                        init_ch["translate"][0],
                        init_ch["translate"][1],
                        init_ch["translate"][2],
                    )
                    cmds.setAttr(
                        tgt_jnt + ".rotate",
                        init_ch["rotate"][0],
                        init_ch["rotate"][1],
                        init_ch["rotate"][2],
                    )
                    cmds.setAttr(
                        tgt_jnt + ".jointOrient",
                        init_ch["jointOrient"][0],
                        init_ch["jointOrient"][1],
                        init_ch["jointOrient"][2],
                    )
                    self.update_skin_bind_pre_matrix(tgt_jnt)

                for s_info in data["spheres"]:
                    s_name = s_info["sphere_name"]
                    m_s_init = s_info["m_s_init"]
                    if cmds.objExists(s_name):
                        cmds.xform(s_name, worldSpace=True, matrix=m_s_init)

                reverted_count += 1

            # --- 3. REPARENT FACIAL BONE ---
            if has_facial and cmds.objExists(head_bone):
                cmds.parent(facial_bone, head_bone)

            for child, parent_node in detached_nodes:
                if cmds.objExists(child) and cmds.objExists(parent_node):
                    try:
                        cmds.parent(child, parent_node)
                    except Exception as e:
                        cmds.warning("Could not re-attach child {}: {}".format(child, e))

            cmds.text(
                self.lbl_status,
                edit=True,
                label="Status: Reverted {} active joints.".format(reverted_count),
            )
            cmds.inViewMessage(
                amg="Reverted {} active joints and spheres!".format(reverted_count),
                pos="topCenter",
                fade=True,
            )
        finally:
            cmds.undoInfo(closeChunk=True)

    def export_json(self, *args):
        file_path = cmds.fileDialog2(
            fileFilter="JSON Files (*.json)",
            dialogStyle=2,
            fileMode=0,
            caption="Export Sphere Transforms JSON",
        )
        if not file_path:
            return

        spheres_data = {}
        all_spheres = cmds.ls("*_bounding_sphere*", transforms=True) or []

        for sphere in all_spheres:
            spheres_data[sphere] = {
                "matrix": cmds.xform(
                    sphere, query=True, worldSpace=True, matrix=True
                ),
                "translation": cmds.xform(
                    sphere, query=True, worldSpace=True, translation=True
                ),
                "rotation": cmds.xform(
                    sphere, query=True, worldSpace=True, rotation=True
                ),
                "scale": cmds.xform(sphere, query=True, relative=True, scale=True),
            }

        payload = {
            "mesh": self.mesh,
            "joints": self.joints,
            "spheres": spheres_data,
        }

        with open(file_path[0], "w") as f:
            json.dump(payload, f, indent=4)

        cmds.inViewMessage(
            amg="Exported {} sphere transforms to JSON!".format(
                len(spheres_data)
            ),
            pos="topCenter",
            fade=True,
        )

    def import_json(self, *args):
        file_path = cmds.fileDialog2(
            fileFilter="JSON Files (*.json)",
            dialogStyle=2,
            fileMode=1,
            caption="Import Sphere Transforms JSON",
        )
        if not file_path:
            return

        with open(file_path[0], "r") as f:
            data = json.load(f)

        if "mesh" in data and data["mesh"]:
            self.mesh = data["mesh"]
            if cmds.objExists(self.txt_mesh):
                cmds.textField(self.txt_mesh, edit=True, text=self.mesh)

        if "joints" in data and data["joints"]:
            base_joints = [j.split("|")[-1].split(":")[-1] for j in data["joints"]]
            self.joints = list(dict.fromkeys(base_joints))
            self.rebuild_joints_checkbox_ui()
            cmds.text(
                self.lbl_joints_count,
                edit=True,
                label="Target Joints Loaded: {}".format(len(self.joints)),
            )

        spheres_dict = data.get("spheres", {})
        restored_count = 0

        for sphere_name, t_data in spheres_dict.items():
            if not cmds.objExists(sphere_name):
                self._create_single_sphere(sphere_name, [0, 0, 0])

            if "matrix" in t_data:
                cmds.xform(sphere_name, worldSpace=True, matrix=t_data["matrix"])
            else:
                if "translation" in t_data:
                    cmds.xform(
                        sphere_name,
                        worldSpace=True,
                        translation=t_data["translation"],
                    )
                if "rotation" in t_data:
                    cmds.xform(
                        sphere_name, worldSpace=True, rotation=t_data["rotation"]
                    )
                if "scale" in t_data:
                    cmds.xform(sphere_name, relative=True, scale=t_data["scale"])

            restored_count += 1

        cmds.inViewMessage(
            amg="Imported {} sphere transforms from JSON!".format(restored_count),
            pos="topCenter",
            fade=True,
        )

    def set_spheres_visibility(self, sphere_list, visible=True):
        count = 0
        for sphere in sphere_list:
            if cmds.objExists(sphere):
                cmds.setAttr(sphere + ".visibility", 1 if visible else 0)
                count += 1
        return count

    def hide_active_spheres(self, *args):
        active_base_joints = self.get_active_joints()
        spheres = []
        for base_jnt in active_base_joints:
            spheres.extend(self.get_spheres_for_joint(base_jnt))

        count = self.set_spheres_visibility(spheres, visible=False)
        cmds.inViewMessage(
            amg="Hidden {} active spheres!".format(count),
            pos="topCenter",
            fade=True,
        )

    def show_active_spheres(self, *args):
        active_base_joints = self.get_active_joints()
        spheres = []
        for base_jnt in active_base_joints:
            spheres.extend(self.get_spheres_for_joint(base_jnt))

        count = self.set_spheres_visibility(spheres, visible=True)
        cmds.inViewMessage(
            amg="Shown {} active spheres!".format(count),
            pos="topCenter",
            fade=True,
        )

    def hide_all_spheres(self, *args):
        all_spheres = cmds.ls("*_bounding_sphere*", transforms=True) or []
        count = self.set_spheres_visibility(all_spheres, visible=False)
        cmds.inViewMessage(
            amg="Hidden ALL {} spheres in scene!".format(count),
            pos="topCenter",
            fade=True,
        )

    def show_all_spheres(self, *args):
        all_spheres = cmds.ls("*_bounding_sphere*", transforms=True) or []
        count = self.set_spheres_visibility(all_spheres, visible=True)
        cmds.inViewMessage(
            amg="Shown ALL {} spheres in scene!".format(count),
            pos="topCenter",
            fade=True,
        )

    def delete_loaded_spheres(self, *args):
        active_base_joints = self.get_active_joints()
        if not active_base_joints:
            cmds.warning("No active joints loaded/checked.")
            return

        deleted_count = 0
        for base_jnt in active_base_joints:
            spheres = self.get_spheres_for_joint(base_jnt)
            if spheres:
                cmds.delete(spheres)
                deleted_count += len(spheres)

        cmds.inViewMessage(
            amg="Deleted {} spheres for active joints!".format(deleted_count),
            pos="topCenter",
            fade=True,
        )

    def delete_all_spheres(self, *args):
        spheres = cmds.ls("*_bounding_sphere*", transforms=True)
        if spheres:
            count = len(spheres)
            cmds.delete(spheres)
            cmds.inViewMessage(
                amg="Deleted {} bounding spheres from scene!".format(count),
                pos="topCenter",
                fade=True,
            )
        else:
            cmds.warning("No bounding spheres found in scene.")


# ======================================================================
# Finger Fix Tool (defined here so it is always refreshed before launch)
# ======================================================================
class HandRigMatchingUI:
    """Finger Fix Tool. Builds into `parent` layout if given, else its own window."""

    def __init__(self, parent=None):
        self.window_name = "HandRigMatchingToolWin"
        self.rig_path = "P:/rigging_team/Pipeline_share/RigUtils/HandSetup/Hand_Build_v01.ma"
        self.parent = parent
        self.build_ui()

    def build_ui(self):
        if self.parent:
            cmds.setParent(self.parent)
        else:
            if cmds.window(self.window_name, exists=True):
                cmds.deleteUI(self.window_name, window=True)
            self.window = cmds.window(
                self.window_name,
                title="Hand Rig Workflow Tool",
                widthHeight=(380, 360),
                sizeable=False,
            )

        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=['both', 12])

        # Title Banner
        cmds.separator(height=8, style='none')
        cmds.text(label="HAND RIG MATCHING TOOL", font="boldLabelFont", align="center")
        cmds.separator(height=10, style='in')

        # Configuration Section
        cmds.frameLayout(label="Configuration", collapsable=False, marginWidth=10, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

        self.namespace_field = cmds.textFieldGrp(
            label="Rig Namespace:",
            text="Hand_Build_v01",
            columnWidth2=[100, 220]
        )

        self.side_radio = cmds.radioButtonGrp(
            label="Side Option:",
            labelArray3=['Both', 'Left Only', 'Right Only'],
            numberOfRadioButtons=3,
            select=1,
            columnWidth4=[100, 70, 80, 80]
        )
        cmds.setParent('..')
        cmds.setParent('..')

        # Actions Section
        cmds.frameLayout(label="Workflow Actions", collapsable=False, marginWidth=10, marginHeight=8)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8)

        cmds.button(
            label="0. Create Finger Tip Joints (Duplicate 3rd Joints)",
            height=32,
            backgroundColor=[0.40, 0.38, 0.25],
            command=self.create_finger_tip_joints
        )

        cmds.button(
            label="1. Reference Hand Setup Rig",
            height=32,
            backgroundColor=[0.25, 0.40, 0.50],
            command=self.reference_hand_rig
        )
        cmds.button(
            label="2. Snap Control Rig to Base Joints",
            height=32,
            backgroundColor=[0.28, 0.45, 0.55],
            command=self.run_ctrl_snapping
        )
        cmds.button(
            label="3. Match Joints to Base (Preserve Mesh)",
            height=32,
            backgroundColor=[0.35, 0.52, 0.38],
            command=self.run_joint_matching
        )
        cmds.button(
            label="4. Remove Reference Rig",
            height=32,
            backgroundColor=[0.55, 0.30, 0.30],
            command=self.unreference_hand_rig
        )

        cmds.setParent('..')
        cmds.setParent('..')

        # Footer
        cmds.separator(height=5, style='none')
        cmds.text(label="Path: P:/rigging_team/.../Hand_Build_v01.ma", align="center", enable=False)
        cmds.separator(height=5, style='none')

        cmds.setParent('..')

        if not self.parent:
            cmds.showWindow(self.window)

    def get_selected_sides(self):
        side_idx = cmds.radioButtonGrp(self.side_radio, query=True, select=True)
        if side_idx == 1:
            return ['L', 'R']
        elif side_idx == 2:
            return ['L']
        elif side_idx == 3:
            return ['R']

    def get_namespace(self):
        return cmds.textFieldGrp(self.namespace_field, query=True, text=True).strip()

    # Action 0: Duplicate 3rd finger joints as tip joints
    def create_finger_tip_joints(self, *args):
        controls = [
            "CC_Base_L_Pinky3",
            "CC_Base_L_Ring3",
            "CC_Base_L_Mid3",
            "CC_Base_L_Index3",
            "CC_Base_L_Thumb3",
            "CC_Base_R_Ring3",
            "CC_Base_R_Mid3",
            "CC_Base_R_Thumb3",
            "CC_Base_R_Index3",
            "CC_Base_R_Pinky3",
        ]

        missing = [c for c in controls if not cmds.objExists(c)]
        if missing:
            cmds.warning("Missing objects, skipped: {}".format(", ".join(missing)))
        controls = [c for c in controls if cmds.objExists(c)]
        if not controls:
            cmds.warning("None of the finger joints exist in the scene.")
            return

        cmds.undoInfo(openChunk=True, chunkName="CreateFingerTipJoints")
        try:
            # Select and duplicate controls
            cmds.select(controls, replace=True)
            duplicates = cmds.duplicate(returnRootsOnly=True)

            # Apply relative transformations
            cmds.move(1.72445e-07, 4.099654, 4.25303e-07, relative=True, objectSpace=True, worldSpaceDistance=True)
            cmds.move(-0.593984, 3.39368e-08, 9.1113e-10, relative=True, objectSpace=True, worldSpaceDistance=True)

            # Parent each duplicate to its original control
            for original, duplicate in zip(controls, duplicates):
                cmds.parent(duplicate, original)

            print("Created {} finger tip joints.".format(len(duplicates)))
        finally:
            cmds.undoInfo(closeChunk=True)

    # Action 1: Reference Hand Rig
    def reference_hand_rig(self, *args):
        ns = self.get_namespace()
        file_path = os.path.normpath(self.rig_path)

        if not os.path.exists(file_path):
            cmds.error(f"File does not exist at path: {file_path}")
            return

        try:
            cmds.file(file_path, reference=True, namespace=ns)
            print(f"Successfully referenced '{file_path}' under namespace '{ns}'.")
        except Exception as e:
            cmds.warning(f"Failed to reference file: {e}")

    # Action 2: Snap Controls to Base
    def run_ctrl_snapping(self, *args):
        ns = self.get_namespace()
        ns_prefix = f"{ns}:" if ns and not ns.endswith(":") else ns
        sides = self.get_selected_sides()

        pairs_template = [
            ("CC_Base_{SIDE}_Hand",   "{NS}main_{SIDE}_ctrl"),
            ("CC_Base_{SIDE}_Thumb1", "{NS}CC_Base_{SIDE}_Thumb1_TOP_CTRL"),
            ("CC_Base_{SIDE}_Thumb4", "{NS}CC_Base_{SIDE}_Thumb1_AIM_CTRL"),
            ("CC_Base_{SIDE}_Index1", "{NS}CC_Base_{SIDE}_Index1_TOP_CTRL"),
            ("CC_Base_{SIDE}_Index4", "{NS}CC_Base_{SIDE}_Index1_AIM_CTRL"),
            ("CC_Base_{SIDE}_Mid1",   "{NS}CC_Base_{SIDE}_Mid1_TOP_CTRL"),
            ("CC_Base_{SIDE}_Mid4",   "{NS}CC_Base_{SIDE}_Mid1_AIM_CTRL"),
            ("CC_Base_{SIDE}_Ring1",  "{NS}CC_Base_{SIDE}_Ring1_TOP_CTRL"),
            ("CC_Base_{SIDE}_Ring4",  "{NS}CC_Base_{SIDE}_Ring1_AIM_CTRL"),
            ("CC_Base_{SIDE}_Pinky1", "{NS}CC_Base_{SIDE}_Pinky1_TOP_CTRL"),
            ("CC_Base_{SIDE}_Pinky4", "{NS}CC_Base_{SIDE}_Pinky1_AIM_CTRL"),
        ]

        snapped_count = 0
        for side in sides:
            for target_fmt, snap_fmt in pairs_template:
                target = target_fmt.format(SIDE=side)
                snap_obj = snap_fmt.format(SIDE=side, NS=ns_prefix)

                if cmds.objExists(target) and cmds.objExists(snap_obj):
                    constraint = cmds.parentConstraint(target, snap_obj, maintainOffset=False)
                    cmds.delete(constraint)
                    snapped_count += 1
                else:
                    cmds.warning(f"Skipped missing pair: '{target}' -> '{snap_obj}'")

        print(f"Successfully snapped {snapped_count} controls!")

    # Action 3: Matrix Joint Match (Preserve Skin Mesh)
    def run_joint_matching(self, *args):
        ns = self.get_namespace()
        ns_prefix = f"{ns}:" if ns and not ns.endswith(":") else ns
        sides = self.get_selected_sides()

        joint_names = [
            "Thumb1", "Thumb2", "Thumb3", "Thumb4",
            "Index1", "Index2", "Index3", "Index4",
            "Mid1",   "Mid2",   "Mid3",   "Mid4",
            "Ring1",  "Ring2",  "Ring3",  "Ring4",
            "Pinky1", "Pinky2", "Pinky3", "Pinky4"
        ]

        matched_count = 0
        for side in sides:
            for jnt_name in joint_names:
                base_jnt = f"CC_Base_{side}_{jnt_name}"
                source_jnt = f"{ns_prefix}{base_jnt}"

                if cmds.objExists(source_jnt) and cmds.objExists(base_jnt):
                    self.snap_matrix_preserve_mesh(source_jnt, base_jnt)
                    matched_count += 1
                else:
                    cmds.warning(f"Skipped missing joint pair: '{source_jnt}' or '{base_jnt}'")

        print(f"Successfully matched matrices for {matched_count} joints!")

    def snap_matrix_preserve_mesh(self, source_jnt, target_jnt):
        children = cmds.listRelatives(target_jnt, children=True, type="transform") or []
        child_matrices = {c: cmds.xform(c, query=True, worldSpace=True, matrix=True) for c in children}

        if cmds.objExists(f"{source_jnt}.rotateOrder") and cmds.objExists(f"{target_jnt}.rotateOrder"):
            cmds.setAttr(f"{target_jnt}.rotateOrder", cmds.getAttr(f"{source_jnt}.rotateOrder"))

        if cmds.objExists(f"{source_jnt}.jointOrient") and cmds.objExists(f"{target_jnt}.jointOrient"):
            j_orient = cmds.getAttr(f"{source_jnt}.jointOrient")[0]
            cmds.setAttr(f"{target_jnt}.jointOrient", *j_orient)

        source_wm = cmds.xform(source_jnt, query=True, worldSpace=True, matrix=True)
        cmds.xform(target_jnt, worldSpace=True, matrix=source_wm)

        for child, matrix in child_matrices.items():
            cmds.xform(child, worldSpace=True, matrix=matrix)

        connections = cmds.listConnections(f"{target_jnt}.worldMatrix[0]", type="skinCluster", connections=True, plugs=True) or []
        for i in range(0, len(connections), 2):
            dst_plug = connections[i + 1]
            if ".matrix[" in dst_plug:
                skin_node, attr_name = dst_plug.split(".")
                index = attr_name.split("[")[1].split("]")[0]
                world_inv_mat = cmds.getAttr(f"{target_jnt}.worldInverseMatrix[0]")
                cmds.setAttr(f"{skin_node}.bindPreMatrix[{index}]", world_inv_mat, type="matrix")

    # Action 4: Unreference Hand Rig
    def unreference_hand_rig(self, *args):
        ns = self.get_namespace()
        file_path = os.path.normpath(self.rig_path)

        try:
            cmds.referenceQuery(file_path, referenceNode=True)
            cmds.file(file_path, removeReference=True)
            print(f"Successfully removed reference for file: {file_path}")
            return
        except Exception:
            pass

        ref_nodes = cmds.ls(type="reference")
        for ref in ref_nodes:
            if ns in ref:
                try:
                    ref_file = cmds.referenceQuery(ref, filename=True)
                    cmds.file(ref_file, removeReference=True)
                    print(f"Successfully removed reference node: {ref}")
                    return
                except Exception as e:
                    cmds.warning(f"Failed to remove reference '{ref}': {e}")
                    return

        cmds.warning(f"No active reference found matching path '{file_path}' or namespace '{ns}'.")


# Run UI with global instance persistence
global hj_sphere_ui
hj_sphere_ui = HierarchicalJointSphereKabschUI()