"""CC Refiner - Joint Relocator tab (spheres, Kabsch fit, reposition / revert)."""
import importlib
import json
import math
import os
import re
import sys
import time
from .state import cmds
from .state import report as _report
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui
from .state import QtCore, QtGui, QtWidgets, wrapInstance
from . import state as _state
from .refiner_common import STYLE, _btn, _label, _maya_main_window, _row, _section, np, om
from . import finger_fix, views


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

    DEFAULT_SPHERE_JSON_NAME = "sphere_02.json"
    DEFAULT_SPHERE_JSON_DIRS = [
        "P:/rigging_team/Pipeline_share/RigUtils/FullBodyJntTransfer",
        "P:/rigging_team/Pipeline_share/RigUtils",
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

    def __init__(self, embed=False, mesh=None):
        self.embed = embed
        self.stored_data = {}
        self.mesh = mesh or self.DEFAULT_MESH
        self.joints = list(self.DEFAULT_JOINTS)
        self.joint_checkboxes = {}
        self.window_name = "HierarchicalJointSphereKabschWindow"
        self.create_ui()

    def create_ui(self):
        if self.embed:
            # lives inside another window: plain child widget, the host decides the size
            self.window = QtWidgets.QWidget()
            self.window.setObjectName(self.window_name + "Embedded")
            self.window.setStyleSheet(STYLE)
        else:
            maya_main = _maya_main_window()
            for w in QtWidgets.QApplication.topLevelWidgets():
                if w.objectName() == self.window_name:
                    w.close()
                    w.deleteLater()

            self.window = QtWidgets.QWidget(maya_main, QtCore.Qt.Window)
            self.window.setObjectName(self.window_name)
            self.window.setWindowTitle("CC Refiner")
            self.window.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.window.setWindowFlags(self.window.windowFlags() | QtCore.Qt.MSWindowsFixedSizeDialogHint)
            self.window.setStyleSheet(STYLE)
            self.window.setFixedWidth(300)

        outer = QtWidgets.QVBoxLayout(self.window)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs, 1)

        # ---------------- Tab 1: Joint Relocator ----------------
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarAsNeeded if self.embed else QtCore.Qt.ScrollBarAlwaysOff)
        page = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(page)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(20)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Joint Relocator")

        # 1. Setup
        lay = _section("Setup", root)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        self.txt_det_ns = QtWidgets.QLineEdit("FullBodyJntTransfer_01:")
        self.txt_det_ns.setToolTip("Namespace for detection hierarchy")
        # embedded in the marker tool there is no separate rig: the joints are duplicated into this namespace
        self.txt_tgt_ns = QtWidgets.QLineEdit(self.DUP_NS + ":" if self.embed else "")
        self.txt_tgt_ns.setToolTip("Namespace for target reposition hierarchy (leave empty if none)")
        self.txt_mesh = QtWidgets.QLineEdit(self.mesh)
        grid.addWidget(_label("Detect NS", True), 0, 0)
        grid.addWidget(self.txt_det_ns, 0, 1, 1, 2)
        grid.addWidget(_label("Repose NS", True), 1, 0)
        grid.addWidget(self.txt_tgt_ns, 1, 1, 1, 2)
        grid.addWidget(_label("Target Mesh", True), 2, 0)
        grid.addWidget(self.txt_mesh, 2, 1)
        grid.addWidget(_btn("Pick", "flat", self.load_mesh, "Load selected mesh", 22), 2, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # Joints
        lay = _section("Joints", root)
        head = QtWidgets.QHBoxLayout()
        self.lbl_joints_count = _label("", True)
        head.addWidget(self.lbl_joints_count, 1)
        head.addWidget(_btn("All", "flat", lambda *a: self._set_all_checked(True), None, 20))
        head.addWidget(_btn("None", "flat", lambda *a: self._set_all_checked(False), None, 20))
        head.addWidget(_btn("Load Sel.", "flat", self.load_joints,
                            "Load joints from the Maya selection", 20))
        lay.addLayout(head)

        self.txt_filter = QtWidgets.QLineEdit()
        self.txt_filter.setPlaceholderText("Filter joints...")
        self.txt_filter.setClearButtonEnabled(True)
        self.txt_filter.textChanged.connect(self._filter_joints)
        lay.addWidget(self.txt_filter)

        self.list_joints = QtWidgets.QListWidget()
        self.list_joints.setFixedHeight(150)
        self.list_joints.setToolTip("Check = active. Uncheck to keep a joint static. Click to select in Maya.")
        self.list_joints.itemClicked.connect(self._on_joint_clicked)
        lay.addWidget(self.list_joints)

        # Spheres
        lay = _section("Spheres", root)
        self.if_num_spheres = QtWidgets.QSpinBox()  # not shown; default 1 sphere per joint
        self.if_num_spheres.setRange(1, 10)
        self.if_num_spheres.setValue(1)
        self.btn_bs = _btn("BlendShape", "default", self.btn_create_blendshape,
                           "Select source mesh first, then target mesh. Topology check is off.")
        if self.embed:
            self.btn_bs.hide()   # the marker tool already provides the blendshape (wrapMarkerBlend)
        lay.addLayout(_row(
            _btn("Load Ref", "primary", self.btn_load_reference,
                 "Reference the rig and import the default sphere preset ({})".format(self.DEFAULT_SPHERE_JSON_NAME)),
            self.btn_bs,
        ))
        lay.addWidget(_btn("+ Extra Sphere", "default", self.add_extra_sphere,
                           "Add an extra sphere to the selected joint"))

        # 2. Process
        lay = _section("Calculate & Reposition", root)
        if self.embed:
            lay.addWidget(_btn("0. Duplicate Joints", "default", self.btn_duplicate_joints,
                               "Duplicate the detection joints into the Repose NS - those copies are the ones "
                               "that get repositioned (made automatically on Detect if missing)"))
        lay.addWidget(_btn("1. Detect Vertices", "primary", self.btn_calculate,
                           "Detect vertices inside the spheres and store reference frames", 30))
        lay.addWidget(_btn("2. Reposition Joints", "success", self.btn_reposition,
                           "Reposition target joints (skin-preserved)", 30))
        lay.addWidget(_btn("Revert", "default", self.btn_revert,
                           "Revert target joints & spheres to their state before reposition"))

        # 3. Presets
        lay = _section("JSON Presets", root)
        lay.addLayout(_row(
            _btn("Export", "default", self.export_json, "Export sphere transforms to JSON"),
            _btn("Import", "default", self.import_json, "Import sphere transforms from JSON"),
        ))

        # 4. Utilities
        lay = _section("Utilities", root)
        lay.addWidget(_btn("Delete All", "danger", self.delete_all_spheres, "Delete all spheres, remove the reference and clean up leftover nodes"))
        root.addStretch(1)

        # ---------------- Tab 2: Finger Fix ----------------
        try:
            self.finger_tool = finger_fix.HandRigMatchingUI()
            self.tabs.addTab(self.finger_tool.widget, "Finger Fix")
        except NameError:
            self.finger_tool = None
            self.tabs.addTab(_label("HandRigMatchingUI class not found.\nRun the full script file."), "Finger Fix")
            cmds.warning("HandRigMatchingUI class missing - Finger Fix tab disabled.")

        # ---------------- Status bar ----------------
        self.lbl_status = QtWidgets.QLabel("Loaded default preset joints & mesh.")
        self.lbl_status.setObjectName("status")
        self.lbl_status.setWordWrap(True)
        outer.addWidget(self.lbl_status)

        self.rebuild_joints_checkbox_ui()
        if self.embed:
            # no scrolling: tighten the spacing so every button fits, then report the height needed
            pages = [page]
            scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            if self.finger_tool is not None:
                self.finger_tool.widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
                pages.append(self.finger_tool.widget.widget())
            for pg in pages:
                pg.layout().setContentsMargins(10, 8, 10, 8)
                pg.layout().setSpacing(8)
                for lay in pg.findChildren(QtWidgets.QLayout):
                    if lay.spacing() >= 14:
                        lay.setSpacing(6)
            self.list_joints.setFixedHeight(110)
            page_h = max(pg.sizeHint().height() for pg in pages)
            need = (page_h + self.tabs.tabBar().sizeHint().height()
                    + self.lbl_status.sizeHint().height() + 6)
            self.window.setMinimumHeight(need)
            return
        self.window.show()
        # Lock the window to exactly fit the content so no button is ever hidden
        page_h = page.sizeHint().height()
        if self.finger_tool is not None:
            page_h = max(page_h, self.finger_tool.widget.widget().sizeHint().height())
        need = (page_h + self.tabs.tabBar().sizeHint().height()
                + self.lbl_status.sizeHint().height() + 12)
        self.window.setFixedSize(300, need)

    def set_status(self, text):
        text = str(text)
        if text.startswith("Status: "):
            text = text[len("Status: "):]
        self.lbl_status.setText(text)
        if self.embed and text.upper().startswith(("ERROR", "NO JOINTS", "TARGET MESH", "NOTHING")):
            _report("error", text)   # also in the red bar at the top of the window

    def _update_joint_count(self):
        self.lbl_joints_count.setText("{} joints".format(len(self.joints)))

    def _on_joint_clicked(self, item):
        self.select_joint_in_maya(item.text())

    def _set_all_checked(self, state):
        st = QtCore.Qt.Checked if state else QtCore.Qt.Unchecked
        for item in self.joint_checkboxes.values():
            item.setCheckState(st)

    def _filter_joints(self, text):
        text = text.strip().lower()
        for name, item in self.joint_checkboxes.items():
            item.setHidden(bool(text) and text not in name.lower())

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

        # the referenced body goes straight into viewport B of the marker tool
        if self.embed:
            self._show_reference_in_view_b()

        # Automatically import the default sphere preset after the reference is loaded
        self.import_default_json()

    def _show_reference_in_view_b(self):
        mesh = self.DEFAULT_MESH   # the referenced body (not the generated mesh)
        if not cmds.objExists(mesh):
            cmds.warning("Reference loaded, but {} was not found for view B.".format(self.DEFAULT_MESH))
            return
        try:
            views._assign_mesh("B", cmds.ls(mesh, long=True)[0])
        except Exception as e:
            cmds.warning("Could not load the reference mesh into view B: {}".format(e))

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
        # Enable the blendShape automatically: envelope on, source target weight = 1
        cmds.setAttr(bs_node + ".envelope", 1.0)
        cmds.blendShape(bs_node, edit=True, weight=[(0, 1.0)])
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
        return self.txt_det_ns.text()

    def get_target_namespace(self):
        return self.txt_tgt_ns.text()

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
            self._update_joint_count()
            cmds.inViewMessage(
                amg="Loaded {} joints from selection!".format(len(self.joints)),
                pos="topCenter",
                fade=True,
            )
        else:
            cmds.warning("Please select one or more Joints in the scene.")

    def rebuild_joints_checkbox_ui(self):
        self.list_joints.blockSignals(True)
        self.list_joints.clear()
        self.joint_checkboxes = {}

        for base_jnt in self.joints:
            item = QtWidgets.QListWidgetItem(base_jnt)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            checked = base_jnt not in self.DEFAULT_UNCHECKED_JOINTS
            item.setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            self.list_joints.addItem(item)
            self.joint_checkboxes[base_jnt] = item

        self.list_joints.blockSignals(False)
        self._update_joint_count()
        self._filter_joints(self.txt_filter.text())

    def get_active_joints(self):
        return [
            base_jnt
            for base_jnt in self.joints
            if base_jnt in self.joint_checkboxes
            and self.joint_checkboxes[base_jnt].checkState() == QtCore.Qt.Checked
        ]

    def load_mesh(self, *args):
        sel = cmds.ls(selection=True, transforms=True)
        if sel:
            self.mesh = sel[0]
            self.txt_mesh.setText(self.mesh)
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
        num_spheres = self.if_num_spheres.value()
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

    DUP_NS = "RepositionJnt"

    def _det_root(self, det_ns):
        """Top joint of the detection skeleton (CC_Base_BoneRoot, else the biggest joint tree)."""
        cand = self.format_joint_with_ns("CC_Base_BoneRoot", det_ns)
        if cmds.objExists(cand):
            return cmds.ls(cand, long=True)[0]
        pat = "{}:*".format(det_ns) if det_ns else "*"
        tops = [j for j in (cmds.ls(pat, type="joint", long=True) or [])
                if not cmds.listRelatives(j, parent=True, type="joint")]
        if not tops:
            return None
        return max(tops, key=lambda j: len(cmds.listRelatives(j, allDescendents=True, type="joint") or []))

    def btn_duplicate_joints(self, *args):
        """Duplicate the detection joints into a fresh namespace (same joint names) - the duplicates are the
        'target' joints that Reposition moves. The originals stay where they are."""
        det_ns = self.get_detection_namespace().strip().rstrip(":")
        root = self._det_root(det_ns)
        if not root:
            msg = "No joints found in '{}' - load the reference / check Detect NS.".format(det_ns)
            cmds.warning(msg)
            self.set_status(msg)
            return False
        tgt_ns = self.get_target_namespace().strip().rstrip(":")
        if not tgt_ns or tgt_ns == det_ns:
            tgt_ns = self.DUP_NS
        self.txt_tgt_ns.setText(tgt_ns + ":")
        cmds.undoInfo(openChunk=True, chunkName="DuplicateRepositionJoints")
        try:
            if cmds.namespace(exists=tgt_ns):
                old = sorted(cmds.ls(tgt_ns + ":*", type="joint", long=True) or [], key=lambda n: n.count("|"))
                for n in old:
                    if cmds.objExists(n):
                        cmds.delete(n)
            else:
                cmds.namespace(add=tgt_ns)
            dup_root = cmds.ls(cmds.duplicate(root, renameChildren=True)[0], long=True)[0]
            # keep joints only (the copy also carries any other children of the original)
            for n in reversed(cmds.listRelatives(dup_root, allDescendents=True, type="transform", fullPath=True) or []):
                if cmds.objExists(n) and cmds.nodeType(n) != "joint":
                    cmds.delete(n)
            if cmds.listRelatives(dup_root, parent=True):
                dup_root = cmds.parent(dup_root, world=True)[0]
                dup_root = cmds.ls(dup_root, long=True)[0]
            pairs = []

            def walk(o, d):
                pairs.append((o, d))
                oc = cmds.listRelatives(o, children=True, type="joint", fullPath=True) or []
                dc = cmds.listRelatives(d, children=True, type="joint", fullPath=True) or []
                for a, b in zip(oc, dc):
                    walk(a, b)

            walk(root, dup_root)
            items = [(cmds.ls(d, uuid=True)[0], o.split("|")[-1].split(":")[-1]) for o, d in pairs]
            for uid, base in items:
                node = cmds.ls(uid, long=True)[0]
                new = cmds.rename(node, "{}:{}".format(tgt_ns, base))
                try:
                    cmds.setAttr(new + ".overrideEnabled", 1)
                    cmds.setAttr(new + ".overrideColor", 17)
                except Exception:
                    pass
        finally:
            cmds.undoInfo(closeChunk=True)
        msg = "Duplicated {} joints into '{}:' - they are the joints Reposition will move.".format(
            len(items), tgt_ns)
        self.set_status(msg)
        cmds.inViewMessage(amg=msg, pos="topCenter", fade=True)
        return True

    def _ensure_target_joints(self):
        """Embedded: make sure the duplicate (target) joints exist before detecting."""
        det_ns = self.get_detection_namespace().strip().rstrip(":")
        tgt_ns = self.get_target_namespace().strip().rstrip(":")
        if tgt_ns and tgt_ns != det_ns and cmds.ls(tgt_ns + ":*", type="joint"):
            return True
        return self.btn_duplicate_joints()

    def _gen_blendshape(self):
        """The blendShape of the generated mesh (wrapMarkerBlend) when embedded in the marker tool."""
        if not self.embed:
            return None
        bs = _state.S["gen"]["bs"]
        if bs and cmds.objExists(bs):
            return bs
        return "wrapMarkerBlend" if cmds.objExists("wrapMarkerBlend") else None

    def btn_calculate(self, *args):
        """Detect always reads the FIRST pose: wrapMarkerBlend is put at 0 for the read, then restored."""
        if self.embed and not self._ensure_target_joints():
            return
        bs = self._gen_blendshape()
        old = None
        if bs:
            old = cmds.getAttr(bs + ".weight[0]")
            cmds.setAttr(bs + ".weight[0]", 0.0)
        try:
            self._calculate()
        finally:
            if bs and old is not None and cmds.objExists(bs):
                cmds.setAttr(bs + ".weight[0]", old)

    def _calculate(self):
        mesh_name = self.txt_mesh.text()
        active_base_joints = self.get_active_joints()
        det_ns = self.get_detection_namespace()
        tgt_ns = self.get_target_namespace()

        if not active_base_joints:
            cmds.error("No active (checked) joints loaded.")
            return
        if not mesh_name or not cmds.objExists(mesh_name):
            # embedded in the marker tool: fall back to the generated blendshape mesh
            gen = _state.S["gen"]["base"] if self.embed else None
            if gen and cmds.objExists(gen):
                mesh_name = gen
                self.txt_mesh.setText(gen.split("|")[-1])
            else:
                msg = ("Target mesh '{}' not found. Create the blendshape mesh first (Create Mesh), "
                       "or pick a mesh.".format(mesh_name))
                cmds.warning(msg)
                self.set_status(msg)
                return

        invalid_entries = []
        invalid_joints = set()
        outside_joints = set()   # embedded: spheres that do not touch the (partial) mesh at all
        best = {}                # joint -> most vertices found in one of its spheres

        for base_jnt in active_base_joints:
            det_jnt = self.format_joint_with_ns(base_jnt, det_ns)
            if not cmds.objExists(det_jnt):
                continue

            spheres = self.get_spheres_for_joint(base_jnt)
            if not spheres:
                continue

            per = []
            for s_name in spheres:
                vtx_in_single = self.get_vertices_in_spheres(
                    mesh_name, [s_name]
                )
                count = len(vtx_in_single)
                per.append(count)
                if count < 5 and not (self.embed and count == 0):
                    entry = "{} | {} -> {} vtx".format(
                        det_jnt, s_name, count
                    )
                    invalid_entries.append(entry)
                    invalid_joints.add(base_jnt)
            best[base_jnt] = max(per)
            if self.embed and sum(per) == 0:
                outside_joints.add(base_jnt)

        if invalid_entries:
            cmds.warning(
                "{} sphere(s) with < 5 vertices (see Script Editor).".format(
                    len(invalid_entries)
                )
            )
            for entry in invalid_entries:
                print("Invalid sphere: " + entry)

        self.stored_data.clear()
        processed_count = 0

        for base_jnt in active_base_joints:
            if base_jnt in invalid_joints or base_jnt in outside_joints:
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

        try:
            nvtx = cmds.polyEvaluate(mesh_name, vertex=True)
            bb = cmds.exactWorldBoundingBox(mesh_name)
        except Exception:
            nvtx, bb = "?", None
        top = sorted(best.items(), key=lambda kv: -kv[1])[:8]
        print("CC Refiner detect: mesh '{}' - {} vertices, bbox {}".format(
            mesh_name, nvtx, [round(v, 1) for v in bb] if bb else None))
        print("  spheres outside the mesh: {} joints; < 5 vertices: {} joints".format(
            len(outside_joints), len(invalid_joints)))
        print("  stored (will move): " + ", ".join(self.stored_data.keys()))
        print("  most vertices per joint: " + ", ".join("{}={}".format(k, v) for k, v in top))

        if processed_count > 0:
            status_msg = "Status: Stored {} joints on {} ({} vtx).".format(
                processed_count, mesh_name.split("|")[-1], nvtx)
            if invalid_joints:
                status_msg += " {} skipped (<5 vtx).".format(len(invalid_joints))
            if outside_joints:
                status_msg += " {} outside the mesh.".format(len(outside_joints))
        else:
            status_msg = ("ERROR: no joint has 5+ vertices of {} ({} vtx) in its spheres. "
                          "{} joints are outside the mesh. Best: {}. The mesh only covers part of the body - "
                          "move/enlarge the spheres onto it, or extend the mesh.").format(
                mesh_name.split("|")[-1], nvtx, len(outside_joints),
                ", ".join("{}={}".format(k, v) for k, v in top[:3]) or "none")

        self.set_status(status_msg)
        cmds.inViewMessage(
            amg="Captured frame data for {} active joints!".format(
                processed_count
            ),
            pos="topCenter",
            fade=True,
        )

    def _unlock_joint_attrs(self, joints):
        """Make translate/rotate/scale/jointOrient (compound + axis plugs) editable on the given joints:
        unlock locked plugs and disconnect incoming connections (constraints, anim curves, drivers),
        since a connected attribute cannot be set either."""
        attrs = []
        for base in ("translate", "rotate", "scale", "jointOrient"):
            attrs.append(base)
            attrs.extend(base + ax for ax in ("X", "Y", "Z"))
        fixed_joints = 0
        failed = []
        for jnt in joints:
            if not cmds.objExists(jnt):
                continue
            touched = False
            for attr in attrs:
                plug = "{}.{}".format(jnt, attr)
                if not cmds.objExists(plug):
                    continue
                try:
                    if cmds.getAttr(plug, lock=True):
                        cmds.setAttr(plug, lock=False)
                        touched = True
                except Exception as e:
                    failed.append("{} (unlock: {})".format(plug, e))
                try:
                    sources = cmds.listConnections(
                        plug, source=True, destination=False, plugs=True
                    ) or []
                    for src in sources:
                        cmds.disconnectAttr(src, plug)
                        print("Disconnected {} -> {}".format(src, plug))
                        touched = True
                except Exception as e:
                    failed.append("{} (disconnect: {})".format(plug, e))
            if touched:
                fixed_joints += 1
        if fixed_joints:
            print("Unlocked/disconnected transform attributes on {} joint(s) before processing.".format(fixed_joints))
        for f in failed:
            cmds.warning("Could not free attribute: " + f)
        return fixed_joints

    def btn_reposition(self, *args):
        if not self.stored_data:
            cmds.warning("Please press button 1 to store initial frames first.")
            return
        bs = self._gen_blendshape()
        if bs and cmds.getAttr(bs + ".weight[0]") < 0.001:
            msg = "wrapMarkerBlend is still at 0 - move the Offset slider (0 to 1) first."
            cmds.warning(msg)
            self.set_status(msg)
            return

        active_base_joints = set(self.get_active_joints())
        tgt_ns = self.get_target_namespace()
        
        facial_bone = self.format_joint_with_ns("CC_Base_FacialBone", tgt_ns)
        head_bone = self.format_joint_with_ns("CC_Base_Head", tgt_ns)

        detachment_map = self._get_detachment_map(active_base_joints, tgt_ns)
        target_world_data = {}
        missing_tgt = []

        for base_jnt, data in self.stored_data.items():
            if base_jnt not in active_base_joints:
                continue

            tgt_jnt = self.format_joint_with_ns(base_jnt, tgt_ns)
            if not cmds.objExists(tgt_jnt):
                missing_tgt.append(tgt_jnt)
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

        if not target_world_data:
            msg = "No joints moved: {} target joint(s) not found (Repose NS = '{}'), e.g. {}".format(
                len(missing_tgt), tgt_ns, missing_tgt[0] if missing_tgt else "-")
            cmds.warning(msg)
            self.set_status(msg)
            return

        sorted_target_joints = sorted(
            target_world_data.keys(), key=self.get_dag_depth
        )

        cmds.undoInfo(
            openChunk=True, chunkName="HierarchicalJointOrientRelocate"
        )
        try:
            # --- 0. UNLOCK any locked transform/orient attributes on joints being repositioned ---
            unlocked_count = self._unlock_joint_attrs(sorted_target_joints)

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

            self.set_status("Status: Posed {} active joints while isolating facial bones!".format(
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
            self._resnap_markers()   # this just deformed the mesh(es) - pull any placed markers back onto the surface
        finally:
            cmds.undoInfo(closeChunk=True)

    def _resnap_markers(self):
        """Re-snap every placed marker onto the (now possibly deformed) mesh surface, when embedded."""
        if not self.embed:
            return
        try:
            from . import markers
            markers.snap_markers(force=True)
            markers._update_overlays()
        except Exception as e:
            print("wrapMarker: could not re-snap markers after reposition: %s" % e)

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

            self._unlock_joint_attrs([t for t, _ in sorted_revert_items])

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

            self.set_status("Status: Reverted {} active joints.".format(reverted_count),
            )
            cmds.inViewMessage(
                amg="Reverted {} active joints and spheres!".format(reverted_count),
                pos="topCenter",
                fade=True,
            )
            self._resnap_markers()
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
        self._load_sphere_json(file_path[0])

    def _find_default_json(self):
        dirs = []
        try:
            dirs.append(os.path.dirname(os.path.abspath(__file__)))
        except NameError:
            pass
        dirs.extend(self.DEFAULT_SPHERE_JSON_DIRS)
        for d in dirs:
            candidate = os.path.join(d, self.DEFAULT_SPHERE_JSON_NAME)
            if os.path.isfile(candidate):
                return candidate
        return None

    def use_existing_reference(self):
        """If the reference is already in the scene when the tool opens: put its body in view B and,
        when there are no spheres yet, load the default sphere preset - same as pressing Load Ref."""
        if not cmds.objExists(self.DEFAULT_MESH):
            return False
        self._show_reference_in_view_b()
        extra = ""
        if not cmds.ls("*_bounding_sphere*", transforms=True) and self._find_default_json():
            try:
                self._load_sphere_json(self._find_default_json(), keep_mesh_if_missing=True)
                extra = " and loaded the sphere preset"
            except Exception as e:
                cmds.warning("Could not load the sphere preset: {}".format(e))
        self.set_status("Found the reference '{}' already in the scene: put it in view B{}.".format(
            self.REFERENCE_NAMESPACE, extra))
        return True

    def import_default_json(self, *args):
        path = self._find_default_json()
        if not path:
            cmds.warning(
                "{} not found next to the script or in the RigUtils share - pick it manually.".format(
                    self.DEFAULT_SPHERE_JSON_NAME
                )
            )
            self.import_json()
            return
        self._load_sphere_json(path, keep_mesh_if_missing=True)

    def _load_sphere_json(self, path, keep_mesh_if_missing=False):
        with open(path, "r") as f:
            data = json.load(f)

        # embedded: Target Mesh stays the generated mesh (the preset's mesh is the reference body)
        if "mesh" in data and data["mesh"] and not self.embed:
            if not keep_mesh_if_missing or cmds.objExists(data["mesh"]):
                self.mesh = data["mesh"]
                if self.txt_mesh:
                    self.txt_mesh.setText(self.mesh)

        if "joints" in data and data["joints"]:
            base_joints = [j.split("|")[-1].split(":")[-1] for j in data["joints"]]
            self.joints = list(dict.fromkeys(base_joints))
            self.rebuild_joints_checkbox_ui()
            self._update_joint_count()

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

        self.set_status("Status: Imported {} spheres from {}".format(
                restored_count, os.path.basename(path)
            ),
        )
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

    def show_all_spheres(self, *args):
        all_spheres = cmds.ls("*_bounding_sphere*", transforms=True) or []
        count = self.set_spheres_visibility(all_spheres, visible=True)
        cmds.inViewMessage(
            amg="Shown ALL {} spheres in scene!".format(count),
            pos="topCenter",
            fade=True,
        )

    def _remove_reference_quiet(self):
        """Remove the FullBodyJntTransfer reference if it is loaded. Returns True if removed."""
        uni = self._get_uniutils()
        if not uni:
            return False
        ref_nodes = [
            r for r in (cmds.ls(type="reference") or [])
            if r.startswith(self.REFERENCE_NAMESPACE)
        ]
        if not ref_nodes:
            try:
                cmds.referenceQuery(self.REFERENCE_FILE_PATH, referenceNode=True)
            except Exception:
                return False
        try:
            uni.remove_reference(self.REFERENCE_FILE_PATH)
            return True
        except Exception as e:
            cmds.warning("Could not remove reference: {}".format(e))
            return False

    _DEFAULT_CAMS = {"persp", "top", "front", "side", "|persp", "|top", "|front", "|side"}

    def _all_world_transforms(self):
        return set(cmds.ls(assemblies=True, long=True) or [])

    def _is_empty_transform(self, node):
        if not cmds.objExists(node) or cmds.nodeType(node) != "transform":
            return False
        return not (cmds.listRelatives(node, shapes=True) or cmds.listRelatives(node, children=True))

    def _delete_reference_leftovers(self, before=None):
        """Delete junk left behind by deleting spheres / removing the reference:
        - the <ns>RNfosterParent* node
        - empty transforms named transform, transform1, transform2, ... (any number)
        - any empty top-level transform that appeared during this clean-up (`before` = earlier snapshot)
        Non-empty transforms are never touched."""
        deleted = []
        candidates = list(cmds.ls("{}RNfosterParent*".format(self.REFERENCE_NAMESPACE), long=True) or [])

        for node in (cmds.ls("transform*", long=True) or []):
            short = node.split("|")[-1]
            if re.match(r"^transform\d*$", short):
                candidates.append(node)

        if before is not None:
            for node in self._all_world_transforms() - set(before):
                short = node.split("|")[-1]
                if short in self._DEFAULT_CAMS:
                    continue
                if self._is_empty_transform(node):
                    candidates.append(node)

        seen = set()
        for node in candidates:
            if node in seen or not cmds.objExists(node):
                continue
            seen.add(node)
            short = node.split("|")[-1]
            is_foster = "RNfosterParent" in short
            if not is_foster and not self._is_empty_transform(node):
                cmds.warning("'{}' has children/shapes - left untouched.".format(short))
                continue
            try:
                cmds.delete(node)
                deleted.append(short)
            except Exception as e:
                cmds.warning("Could not delete {}: {}".format(short, e))
        return deleted

    def delete_all_spheres(self, *args):
        """Delete ALL spheres, remove the reference, and clean up leftover nodes."""
        cmds.select(clear=True)
        before = self._all_world_transforms()

        spheres = cmds.ls("*_bounding_sphere*", transforms=True) or []
        sphere_count = len(spheres)
        if spheres:
            cmds.delete(spheres)

        ref_removed = self._remove_reference_quiet()
        leftovers = self._delete_reference_leftovers(before)
        cmds.select(clear=True)

        parts = ["{} spheres deleted".format(sphere_count)]
        if ref_removed:
            parts.append("reference removed")
        if leftovers:
            parts.append("cleaned: " + ", ".join(leftovers))
        msg = "; ".join(parts)
        self.set_status(msg)
        cmds.inViewMessage(amg=msg, pos="topCenter", fade=True)

        # Second pass once Maya is idle: catches nodes created after the commands above finish
        def _late_cleanup():
            try:
                late = self._delete_reference_leftovers(before)
                if late:
                    self.set_status(msg + "; late cleanup: " + ", ".join(late))
            except RuntimeError:
                pass   # the window was already closed / rebuilt
        cmds.evalDeferred(_late_cleanup)

    def delete_duplicate_joints(self):
        """Delete the duplicated (target) joints and their namespace. Returns how many joints were removed."""
        det_ns = self.get_detection_namespace().strip().rstrip(":")
        ns = self.get_target_namespace().strip().rstrip(":")
        if not ns or ns == det_ns:
            ns = self.DUP_NS
        if not cmds.namespace(exists=ns):
            return 0
        jnts = sorted(cmds.ls(ns + ":*", type="joint", long=True) or [], key=lambda n: n.count("|"))
        removed = 0
        for n in jnts:
            if cmds.objExists(n):
                removed += 1 + len(cmds.listRelatives(n, allDescendents=True, type="joint") or [])
                cmds.delete(n)
        try:
            cmds.namespace(removeNamespace=ns, deleteNamespaceContent=True)
        except Exception:
            pass
        return removed

    def reset_everything(self):
        """Spheres, reference + leftovers, duplicated joints and all stored detection data."""
        self.delete_all_spheres()
        self.delete_duplicate_joints()
        self.stored_data.clear()



# Run UI with global instance persistence


def embed(mesh=None):
    """Build the CC Refiner as a child widget of this window."""
    return HierarchicalJointSphereKabschUI(embed=True, mesh=mesh)
