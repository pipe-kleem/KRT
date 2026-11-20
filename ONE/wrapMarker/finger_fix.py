"""CC Refiner - Finger Fix tab."""
import importlib
import json
import math
import os
import re
import sys
import time
from .state import cmds
import maya.api.OpenMaya as om2
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui
from .state import QtCore, QtGui, QtWidgets, wrapInstance
from .refiner_common import EXTRA_SLIDERS_MEL, TEETH_CTRL_MEL, _btn, _label, _section, mel


# ======================================================================
# Finger Fix Tool (defined here so it is always refreshed before launch)
# ======================================================================
class HandRigMatchingUI:
    """Finger Fix Tool. Exposes `self.widget` to embed in a tab."""

    def __init__(self):
        self.rig_path = "P:/rigging_team/Pipeline_share/RigUtils/HandSetup/Hand_Build_v01.ma"
        self.build_ui()

    def build_ui(self):
        self.widget = QtWidgets.QScrollArea()
        self.widget.setWidgetResizable(True)
        self.widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        page = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(page)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(20)
        self.widget.setWidget(page)

        # Configuration
        lay = _section("Configuration", root)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        self.namespace_field = QtWidgets.QLineEdit("Hand_Build_v01")
        grid.addWidget(_label("Rig NS", True), 0, 0)
        grid.addWidget(self.namespace_field, 0, 1)

        self.rb_both = QtWidgets.QRadioButton("Both")
        self.rb_left = QtWidgets.QRadioButton("Left")
        self.rb_right = QtWidgets.QRadioButton("Right")
        self.rb_both.setChecked(True)
        side_row = QtWidgets.QHBoxLayout()
        for rb in (self.rb_both, self.rb_left, self.rb_right):
            side_row.addWidget(rb)
        side_row.addStretch(1)
        grid.addWidget(_label("Side", True), 1, 0)
        grid.addLayout(side_row, 1, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # Workflow
        lay = _section("Workflow", root)
        lay.addWidget(_btn("1. Tip Joint && Reference", "primary", self.tip_joint_and_reference,
                           "Create finger tip joints, reference the hand rig, then snap the controls to the base joints"))
        lay.addWidget(_btn("2. Match Joints", "success", self.run_joint_matching, "Match joints to base (preserve mesh)"))
        mirror_row = QtWidgets.QHBoxLayout()
        mirror_row.setSpacing(14)
        mirror_row.addWidget(_btn("L \u2192 R", "primary", lambda *a: self.run_mirror("L", "R"),
                                  "Mirror the left controls' attribute values onto the right controls (YZ plane: X translate, Y/Z rotate flipped)"), 1)
        mirror_row.addWidget(_btn("R \u2192 L", "primary", lambda *a: self.run_mirror("R", "L"),
                                  "Mirror the right controls' attribute values onto the left controls (YZ plane: X translate, Y/Z rotate flipped)"), 1)
        lay.addLayout(mirror_row)
        lay.addWidget(_btn("3. Remove Ref", "danger", self.unreference_hand_rig, "Remove reference rig"))
        lay.addWidget(_btn("Teeth Ctrl", "default", self.run_teeth_ctrl,
                           "Build the teeth blendshape, joints and controls"))
        lay.addWidget(_btn("Extra Sliders", "default", self.run_extra_sliders,
                           "Build the extra viseme sliders (V_Open, V_Tight, ...)"))

        # Restore control values stored in the file (highlighted + green dot when data exists)
        restore_row = QtWidgets.QHBoxLayout()
        restore_row.setSpacing(10)
        self.btn_restore = _btn("4. Restore Ctrls", "dry", self.restore_ctrl_values)
        self.lbl_restore_dot = QtWidgets.QLabel("\u25CF")
        self.lbl_restore_dot.setFixedWidth(16)
        self.lbl_restore_dot.setAlignment(QtCore.Qt.AlignCenter)
        restore_row.addWidget(self.btn_restore, 1)
        restore_row.addWidget(self.lbl_restore_dot)
        lay.addLayout(restore_row)

        self._restore_timer = QtCore.QTimer(self.widget)
        self._restore_timer.setInterval(1500)
        self._restore_timer.timeout.connect(self._refresh_restore_state)
        self._restore_timer.start()
        self._refresh_restore_state()

        foot = _label(".../HandSetup/Hand_Build_v01.ma", True)
        foot.setAlignment(QtCore.Qt.AlignCenter)
        foot.setToolTip(self.rig_path)
        root.addWidget(foot)
        root.addStretch(1)

        # Fist test slider (very last): drives finger rotations directly, no keys, no connections
        lay = _section("Fist Test", root)
        lay.addWidget(_label("Make Fist"))
        self.fist_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.fist_slider.setRange(0, 1000)  # 0.00 - 10.00
        self.fist_slider.setValue(0)
        self.fist_slider.setFixedHeight(22)
        lay.addWidget(self.fist_slider)

        lay.addWidget(_label("Joint Radius"))
        self.radius_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.radius_slider.setRange(1, 100)  # radius 0.1 - 10.0
        self.radius_slider.setValue(10)
        self.radius_slider.setFixedHeight(22)
        lay.addWidget(self.radius_slider)
        self._radius_dragging = False
        self.radius_slider.sliderPressed.connect(self._radius_press)
        self.radius_slider.sliderReleased.connect(self._radius_release)
        self.radius_slider.valueChanged.connect(self._radius_changed)
        self._sync_radius_slider()

        self._fist_rest = {}
        self._fist_prev = 0
        self._fist_dragging = False
        self.fist_slider.sliderPressed.connect(self._fist_press)
        self.fist_slider.sliderReleased.connect(self._fist_release)
        self.fist_slider.valueChanged.connect(self._fist_changed)

    def get_selected_sides(self):
        if self.rb_left.isChecked():
            return ['L']
        if self.rb_right.isChecked():
            return ['R']
        return ['L', 'R']

    def get_namespace(self):
        return self.namespace_field.text().strip()

    # ------------------------------------------------------------------
    # Control value storage (kept on CC_Base_BoneRoot.handCtrlData in the scene file)
    # ------------------------------------------------------------------
    STORE_NODE = "CC_Base_BoneRoot"
    STORE_ATTR = "handCtrlData"
    CTRL_FINGERS = ["Pinky1", "Ring1", "Mid1", "Index1", "Thumb1"]
    TRS_ATTRS = [t + a for t in ("translate", "rotate", "scale") for a in ("X", "Y", "Z")]

    def _ns_prefix(self):
        ns = self.get_namespace()
        return "{}:".format(ns) if ns and not ns.endswith(":") else ns

    def _ctrl_names(self, side):
        names = []
        for f in self.CTRL_FINGERS:
            for kind in ("AIM", "TOP", "UP"):
                names.append("CC_Base_{}_{}_{}_CTRL".format(side, f, kind))
        names.append("main_{}_ctrl".format(side))
        return names

    def _read_store(self):
        node = self.STORE_NODE
        if not cmds.objExists(node):
            return None
        if not cmds.attributeQuery(self.STORE_ATTR, node=node, exists=True):
            return None
        raw = cmds.getAttr("{}.{}".format(node, self.STORE_ATTR))
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            cmds.warning("Stored control data on {} is not valid JSON.".format(node))
            return None
        return data if isinstance(data, dict) and data else None

    def _refresh_restore_state(self):
        """Highlight the Restore button + green dot when the scene holds stored data, else dry grey."""
        try:
            data = self._read_store()
        except Exception:
            data = None
        has = bool(data)
        kind = "highlight" if has else "dry"
        if self.btn_restore.property("kind") != kind:
            self.btn_restore.setProperty("kind", kind)
            self.btn_restore.style().unpolish(self.btn_restore)
            self.btn_restore.style().polish(self.btn_restore)
        self.lbl_restore_dot.setStyleSheet(
            "color: {}; font-size: 12pt; background: transparent;".format("#4cc27a" if has else "#55585d")
        )
        if has:
            tip = "Stored data found on {}.{} ({} controls). Click to restore.".format(
                self.STORE_NODE, self.STORE_ATTR, len(data))
        else:
            tip = "No stored control data in this file (saved automatically when you press Match Joints)."
        self.btn_restore.setToolTip(tip)
        self.lbl_restore_dot.setToolTip(tip)

    def _store_ctrl_values(self):
        """Save translate/rotate/scale of every UNLOCKED, unconnected hand control (both sides found
        in the scene) onto CC_Base_BoneRoot.handCtrlData as JSON. Merges with existing data so a side
        that is not currently in the scene keeps its old values."""
        node = self.STORE_NODE
        if not cmds.objExists(node):
            cmds.warning("'{}' not found - control values were not stored.".format(node))
            return 0

        data = self._read_store() or {}
        prefix = self._ns_prefix()
        stored = 0
        for side in ("L", "R"):
            for base in self._ctrl_names(side):
                full = prefix + base
                if not cmds.objExists(full):
                    continue
                attrs = {}
                for attr in self.TRS_ATTRS:
                    plug = "{}.{}".format(full, attr)
                    if not cmds.objExists(plug):
                        continue
                    if cmds.getAttr(plug, lock=True):
                        continue
                    if cmds.listConnections(plug, source=True, destination=False):
                        continue
                    attrs[attr] = cmds.getAttr(plug)
                if attrs:
                    data[base] = attrs
                    stored += 1

        if not stored:
            cmds.warning("No unlocked hand controls found in the scene - nothing stored.")
            return 0

        plug = "{}.{}".format(node, self.STORE_ATTR)
        if not cmds.attributeQuery(self.STORE_ATTR, node=node, exists=True):
            cmds.addAttr(node, longName=self.STORE_ATTR, niceName="Hand Ctrl Data", dataType="string")
        elif cmds.getAttr(plug, lock=True):
            cmds.setAttr(plug, lock=False)
        cmds.setAttr(plug, json.dumps(data, separators=(",", ":")), type="string")
        print("Stored values of {} hand controls on {}.".format(stored, plug))
        return stored

    def restore_ctrl_values(self, *args):
        data = self._read_store()
        if not data:
            cmds.warning("No stored control data found on {}.{}.".format(self.STORE_NODE, self.STORE_ATTR))
            self._refresh_restore_state()
            return

        prefix = self._ns_prefix()
        restored, missing, skipped = 0, [], 0
        cmds.undoInfo(openChunk=True, chunkName="RestoreHandCtrlValues")
        try:
            for side in self.get_selected_sides():
                for base in self._ctrl_names(side):
                    if base not in data:
                        continue
                    full = prefix + base
                    if not cmds.objExists(full):
                        missing.append(full)
                        continue
                    for attr, value in data[base].items():
                        plug = "{}.{}".format(full, attr)
                        if not cmds.objExists(plug):
                            continue
                        if cmds.listConnections(plug, source=True, destination=False):
                            skipped += 1
                            continue
                        was_locked = cmds.getAttr(plug, lock=True)
                        if was_locked:
                            cmds.setAttr(plug, lock=False)
                        try:
                            cmds.setAttr(plug, value)
                            restored += 1
                        except Exception as e:
                            skipped += 1
                            cmds.warning("Could not set {}: {}".format(plug, e))
                        finally:
                            if was_locked:
                                cmds.setAttr(plug, lock=True)
        finally:
            cmds.undoInfo(closeChunk=True)

        if missing:
            cmds.warning("Controls not found (is the rig referenced?): {}".format(", ".join(missing[:6])))
        msg = "Restored {} control values".format(restored)
        if skipped:
            msg += " ({} skipped: connected/failed)".format(skipped)
        print(msg)
        cmds.inViewMessage(amg=msg, pos="topCenter", fade=True)

    # ------------------------------------------------------------------
    # Fist test slider: 0 (rest) -> 10 (fist). Sets rotations directly - no keys, no connections.
    # ------------------------------------------------------------------
    FIST_ROTATIONS = {
        "Index1": (12.985, 2.382, -84.937), "Index2": (13.334, 6.303, -81.548), "Index3": (13.334, 6.303, -81.548),
        "Mid1": (11.851, 2.864, -85.109),   "Mid2": (12.263, 7.644, -81.508),   "Mid3": (12.263, 7.644, -81.508),
        "Ring1": (8.668, 2.965, -84.527),   "Ring2": (9.199, 8.452, -81.912),   "Ring3": (9.199, 8.452, -81.912),
        "Pinky1": (7.936, 3.095, -84.162),  "Pinky2": (8.287, 6.508, -82.343),  "Pinky3": (8.287, 6.508, -82.343),
        "Thumb1": (1.178, 0.424, -19.789),  "Thumb2": (0.0, 0.0, -30.854),      "Thumb3": (0.0, 0.0, -38.116),
    }

    def _fist_press(self):
        self._fist_dragging = True
        cmds.undoInfo(openChunk=True, chunkName="FistTestSlider")

    def _fist_release(self):
        self._fist_dragging = False
        cmds.undoInfo(closeChunk=True)

    def _fist_changed(self, raw):
        if self._fist_dragging:
            self._apply_fist(raw)
        else:
            cmds.undoInfo(openChunk=True, chunkName="FistTestSlider")
            try:
                self._apply_fist(raw)
            finally:
                cmds.undoInfo(closeChunk=True)

    def _set_plug_forced(self, plug, *values):
        """setAttr that temporarily unlocks a locked plug."""
        was_locked = cmds.getAttr(plug, lock=True)
        if was_locked:
            cmds.setAttr(plug, lock=False)
        try:
            cmds.setAttr(plug, *values)
        finally:
            if was_locked:
                cmds.setAttr(plug, lock=True)

    def _apply_fist(self, raw):
        prev, self._fist_prev = self._fist_prev, raw
        t = max(0.0, min(1.0, raw / 1000.0))
        sides = self.get_selected_sides()

        # leaving 0: remember the current (rest) pose of the fingers
        if prev == 0 and raw > 0:
            self._fist_rest = {}

        failed = []
        for side in sides:
            for name, fist in self.FIST_ROTATIONS.items():
                jnt = "CC_Base_{}_{}".format(side, name)
                if not cmds.objExists(jnt):
                    continue
                if jnt not in self._fist_rest:
                    self._fist_rest[jnt] = tuple(cmds.getAttr(jnt + ".rotate")[0])
                rest = self._fist_rest[jnt]
                if side == "R":
                    # right hand: mirrored fist values (YZ plane -> rotateY / rotateZ flip sign)
                    fist = tuple(fist[i] * self.MIRROR_SIGN.get(a, 1.0)
                                 for i, a in enumerate(("rotateX", "rotateY", "rotateZ")))
                rot = [rest[i] + (fist[i] - rest[i]) * t for i in range(3)]
                try:
                    self._set_plug_forced(jnt + ".rotate", *rot)
                except Exception:
                    failed.append(jnt)

        # main controls: hidden as soon as the slider leaves 0, shown again when it returns to 0
        ns_prefix = self._ns_prefix()
        for side in sides:
            ctrl = "{}main_{}_ctrl".format(ns_prefix, side)
            if cmds.objExists(ctrl):
                try:
                    self._set_plug_forced(ctrl + ".visibility", 0 if raw > 0 else 1)
                except Exception:
                    failed.append(ctrl)

        if raw == 0:
            self._fist_rest = {}
        if failed:
            cmds.warning("Fist test could not set (connected?): {}".format(", ".join(failed[:4])))

    # Joint radius slider: sets .radius on the fist-test joints only
    def _radius_joints(self):
        joints = []
        for side in self.get_selected_sides():
            for name in self.FIST_ROTATIONS:
                jnt = "CC_Base_{}_{}".format(side, name)
                if cmds.objExists(jnt) and cmds.objExists(jnt + ".radius"):
                    joints.append(jnt)
        return joints

    def _sync_radius_slider(self):
        """Start the slider at the current radius of the first animated joint found in the scene."""
        joints = self._radius_joints()
        if not joints:
            return
        try:
            val = int(round(cmds.getAttr(joints[0] + ".radius") * 10))
        except Exception:
            return
        self.radius_slider.blockSignals(True)
        self.radius_slider.setValue(max(1, min(100, val)))
        self.radius_slider.blockSignals(False)

    def _radius_press(self):
        self._radius_dragging = True
        cmds.undoInfo(openChunk=True, chunkName="JointRadiusSlider")

    def _radius_release(self):
        self._radius_dragging = False
        cmds.undoInfo(closeChunk=True)

    def _radius_changed(self, raw):
        if self._radius_dragging:
            self._apply_radius(raw)
        else:
            cmds.undoInfo(openChunk=True, chunkName="JointRadiusSlider")
            try:
                self._apply_radius(raw)
            finally:
                cmds.undoInfo(closeChunk=True)

    def _apply_radius(self, raw):
        radius = raw / 10.0
        failed = []
        for jnt in self._radius_joints():
            try:
                self._set_plug_forced(jnt + ".radius", radius)
            except Exception:
                failed.append(jnt)
        if failed:
            cmds.warning("Radius could not be set (connected?): {}".format(", ".join(failed[:4])))

    # Combined: tip joints -> reference rig -> snap controls
    def tip_joint_and_reference(self, *args):
        self.create_finger_tip_joints()
        self.reference_hand_rig()  # snaps the controls automatically after a successful reference

    # MEL-script buttons
    def _run_mel_proc(self, mel_src, proc_name, label):
        cmds.undoInfo(openChunk=True, chunkName=label.replace(" ", ""))
        try:
            mel.eval(mel_src)
            mel.eval("{}()".format(proc_name))
            print("{} finished.".format(label))
            cmds.inViewMessage(amg="{} done".format(label), pos="topCenter", fade=True)
        except Exception as e:
            cmds.warning("{} failed: {}".format(label, e))
        finally:
            cmds.undoInfo(closeChunk=True)

    def run_teeth_ctrl(self, *args):
        self._run_mel_proc(TEETH_CTRL_MEL, "teethCtrlAdded", "Teeth Ctrl")

    def run_extra_sliders(self, *args):
        self._run_mel_proc(EXTRA_SLIDERS_MEL, "extraSliders", "Extra Sliders")

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
        # skip fingers whose tip joint (…3 -> …4) already exists, so re-running never duplicates
        already = [c for c in controls if cmds.objExists(c[:-1] + "4")]
        controls = [c for c in controls if c not in already]
        if already:
            print("Tip joints already exist for {} finger(s) - not recreated.".format(len(already)))
        if not controls:
            if not already:
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
            return

        # Automatically snap the controls to the base joints after referencing
        self.run_ctrl_snapping()

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
        # Automatically save the control values to the file before matching
        try:
            self._store_ctrl_values()
        except Exception as e:
            cmds.warning("Could not store control values: {}".format(e))
        self._refresh_restore_state()

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

    # Action 3b: Mirror control attribute values from one side to the other (L -> R or R -> L)
    # YZ-plane mirror (world X flipped): translateX, rotateY and rotateZ change sign; the rest are copied.
    MIRROR_SIGN = {"translateX": -1.0, "rotateY": -1.0, "rotateZ": -1.0}

    def run_mirror(self, src_side, dst_side):
        prefix = self._ns_prefix()
        copied, missing, skipped = 0, [], 0
        cmds.undoInfo(openChunk=True, chunkName="MirrorHandCtrlValues")
        try:
            for src_base, dst_base in zip(self._ctrl_names(src_side), self._ctrl_names(dst_side)):
                src, dst = prefix + src_base, prefix + dst_base
                if not (cmds.objExists(src) and cmds.objExists(dst)):
                    missing.append("{} -> {}".format(src_base, dst_base))
                    continue
                for attr in self.TRS_ATTRS:
                    sp, dp = "{}.{}".format(src, attr), "{}.{}".format(dst, attr)
                    if not (cmds.objExists(sp) and cmds.objExists(dp)):
                        continue
                    # only channels the user can edit on the source side
                    if cmds.getAttr(sp, lock=True) or cmds.listConnections(sp, source=True, destination=False):
                        continue
                    if cmds.listConnections(dp, source=True, destination=False):
                        skipped += 1
                        continue
                    value = cmds.getAttr(sp) * self.MIRROR_SIGN.get(attr, 1.0)
                    was_locked = cmds.getAttr(dp, lock=True)
                    if was_locked:
                        cmds.setAttr(dp, lock=False)
                    try:
                        cmds.setAttr(dp, value)
                        copied += 1
                    except Exception as e:
                        skipped += 1
                        cmds.warning("Could not set {}: {}".format(dp, e))
                    finally:
                        if was_locked:
                            cmds.setAttr(dp, lock=True)
        finally:
            cmds.undoInfo(closeChunk=True)

        if missing:
            cmds.warning("Controls not found (is the rig referenced?): {}".format(", ".join(missing[:4])))
        msg = "Mirrored {} attribute values {} -> {}".format(copied, src_side, dst_side)
        if skipped:
            msg += " ({} skipped)".format(skipped)
        print(msg)
        cmds.inViewMessage(amg=msg, pos="topCenter", fade=True)

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
