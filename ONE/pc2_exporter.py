# -*- coding: utf-8 -*-
"""
PC2 Exporter - Referenced Rig Picker for Maya
----------------------------------------------
Exports Point Cache (.pc2) for meshes in referenced rigs (_geo & _lod_0 filtered)
or from direct Viewport selection.

Usage:
    Run in Maya's Script Editor (Python tab).
"""

# ============================================================================
#  Imports
# ============================================================================

import os
import shutil
import struct
import uuid

import maya.cmds as cmds
from maya import mel

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui


# ============================================================================
#  Constants
# ============================================================================

DEBUG_KEEP_TMP = False

_FPS_MAP = {
    "game": 15.0,  "film": 24.0,  "pal": 25.0,   "ntsc": 30.0,
    "show": 48.0,  "palf": 50.0,  "ntscf": 60.0,
    "2fps": 2.0,   "3fps": 3.0,   "4fps": 4.0,   "5fps": 5.0,
    "6fps": 6.0,   "8fps": 8.0,   "10fps": 10.0, "12fps": 12.0,
    "16fps": 16.0, "20fps": 20.0, "40fps": 40.0, "75fps": 75.0,
    "80fps": 80.0, "100fps": 100.0, "120fps": 120.0,
}


# ============================================================================
#  Logic Layer
# ============================================================================

def get_reference_nodes():
    """Return info dicts for every loaded reference, filtering by _geo and _lod_0."""
    refs = []
    for ref_node in cmds.ls(type="reference") or []:
        if ref_node == "sharedReferenceNode":
            continue
            
        try:
            filename = cmds.referenceQuery(ref_node, filename=True)
            namespace = cmds.referenceQuery(ref_node, namespace=True).lstrip(":")
        except Exception:
            continue

        # Get all nodes tied to this specific reference
        try:
            ref_nodes = cmds.referenceQuery(ref_node, nodes=True, dagPath=True) or []
        except Exception:
            continue
            
        ref_transforms = cmds.ls(ref_nodes, type="transform", long=True) or []
        
        # 1. Isolate groups containing "_geo"
        geo_groups = [t for t in ref_transforms if "_geo" in t.split("|")[-1].lower()]
        meshes_to_export = []

        for geo in geo_groups:
            descendants = cmds.listRelatives(geo, allDescendents=True, type="transform", fullPath=True) or []
            
            # 2. Check if there are any _lod_0 groups under this _geo
            lod0_groups = [d for d in descendants if "_lod_0" in d.split("|")[-1].lower()]

            if lod0_groups:
                # Export ONLY _lod_0 meshes
                for lod0 in lod0_groups:
                    lod_meshes = cmds.listRelatives(lod0, allDescendents=True, type="mesh", fullPath=True, noIntermediate=True) or []
                    for m in lod_meshes:
                        parent = cmds.listRelatives(m, parent=True, fullPath=True)[0]
                        if parent not in meshes_to_export:
                            meshes_to_export.append(parent)
            else:
                # 3. No _lod_0 found, grab all meshes under _geo
                geo_meshes = cmds.listRelatives(geo, allDescendents=True, type="mesh", fullPath=True, noIntermediate=True) or []
                for m in geo_meshes:
                    parent = cmds.listRelatives(m, parent=True, fullPath=True)[0]
                    if parent not in meshes_to_export:
                        meshes_to_export.append(parent)

        # Only add to list if we actually found matching meshes
        meshes = list(set(meshes_to_export))
        if meshes:
            refs.append({
                "refNode":   ref_node,
                "namespace": namespace,
                "filename":  filename,
                "meshes":    meshes,
            })
            
    return refs


def sanitize_name(node_name):
    short = node_name.split("|")[-1]
    return short.split(":")[-1] if ":" in short else short


def get_scene_fps():
    return _FPS_MAP.get(cmds.currentUnit(query=True, time=True), 24.0)


def _restore_maya_state(original_time, original_sel):
    cmds.currentTime(original_time, edit=True, update=True)
    if original_sel:
        cmds.select(original_sel, replace=True)
    else:
        cmds.select(clear=True)


def export_pc2_for_ref(ref_info, output_dir, start_frame, end_frame, frame_step, world_space):
    """Write MCX via Maya, map to meshes, then convert to PC2."""
    exported = []
    errors   = []
    meshes   = ref_info["meshes"]

    if not meshes:
        return exported, errors

    os.makedirs(output_dir, exist_ok=True)

    original_sel  = cmds.ls(selection=True, long=True) or []
    original_time = cmds.currentTime(query=True)
    cache_name    = "pc2cache_{}".format(ref_info["namespace"])
    tmp_dir       = os.path.join(output_dir, "_tmp_mcx_{}".format(uuid.uuid4().hex[:8]))
    safe_dir      = tmp_dir.replace("\\", "/").rstrip("/") + "/"
    os.makedirs(tmp_dir)

    meshes_sorted = sorted(meshes)
    shape_nodes   = []
    mesh_per_shape = [] 

    for transform in meshes_sorted:
        shapes = cmds.listRelatives(
            transform, shapes=True, type="mesh",
            fullPath=True, noIntermediate=True) or []
        for s in shapes:
            shape_nodes.append(s)
            mesh_per_shape.append(transform)

    if not shape_nodes:
        errors.append(("cacheFile", "No shape nodes found under selected transforms."))
        if not DEBUG_KEEP_TMP:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return exported, errors

    log("  Running cacheFile for {} mesh(es)...\n".format(len(shape_nodes)))
    try:
        cmds.cacheFile(
            format           = "OneFile",
            directory        = safe_dir,
            fileName         = cache_name,
            startTime        = int(start_frame),
            endTime          = int(end_frame),
            sampleMultiplier = int(frame_step),
            worldSpace       = 1 if world_space else 0,
            points           = shape_nodes,
        )
    except Exception as exc:
        errors.append(("cacheFile", str(exc)))
        _restore_maya_state(original_time, original_sel)
        if not DEBUG_KEEP_TMP:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return exported, errors

    _restore_maya_state(original_time, original_sel)

    def mcx_filename(idx):
        suffix = "" if idx == 0 else str(idx)
        return cache_name + suffix + ".mcx"

    mcx_to_mesh = {} 
    for idx, transform in enumerate(mesh_per_shape):
        fname = mcx_filename(idx)
        fpath = os.path.join(tmp_dir, fname)
        if os.path.exists(fpath):
            mcx_to_mesh[fname[:-4]] = transform
        else:
            errors.append((sanitize_name(transform),
                           "MCX not written by Maya (index {})".format(idx)))

    for mcx_base, transform in mcx_to_mesh.items():
        mesh_name = sanitize_name(transform)
        pc2_tmp   = safe_dir + mcx_base + ".pc2"
        pc2_dst   = os.path.join(output_dir, mesh_name + ".pc2")

        try:
            mel.eval('cacheFile -pc2 0 -pcf "{}" -f "{}" -dir "{}"'.format(
                pc2_tmp, mcx_base, safe_dir))
        except Exception as exc:
            errors.append((mesh_name, "cacheFile -pc2 failed: {}".format(exc)))
            continue

        try:
            shutil.copy2(pc2_tmp, pc2_dst)
            exported.append(pc2_dst)
            log("  Saved: {}.pc2\n".format(mesh_name))
        except Exception as exc:
            errors.append((mesh_name, "copy failed: {}".format(exc)))

    if not DEBUG_KEEP_TMP:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return exported, errors


# ============================================================================
#  UI Layer
# ============================================================================

QSS = (
    "QWidget {"
    "  background-color: #3f3f3f; color: #cccccc;"
    "  font-family: 'Segoe UI', sans-serif; font-size: 12px;"
    "}"
    "QDialog { background-color: #3f3f3f; }"
    "QLabel  { color: #cccccc; }"
    "QLabel#heading { font-size: 14px; font-weight: bold; color: #eeeeee; }"
    "QLabel#section {"
    "  font-size: 10px; font-weight: bold; color: #9a9a9a; letter-spacing: 1px;"
    "}"
    "QLabel#sub { color: #888888; font-size: 11px; }"
    "QListWidget {"
    "  background-color: #2b2b2b; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; color: #cccccc; outline: none;"
    "}"
    "QListWidget::item { padding: 5px 8px; }"
    "QListWidget::item:selected { background-color: #4a7fbf; color: #ffffff; }"
    "QListWidget::item:hover:!selected { background-color: #484848; }"
    "QLineEdit, QSpinBox {"
    "  background-color: #2b2b2b; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; padding: 3px 6px; color: #cccccc;"
    "}"
    "QLineEdit:focus, QSpinBox:focus { border-color: #4a7fbf; }"
    "QLineEdit[readOnly='true'] { color: #777777; background-color: #333333; }"
    "QSpinBox::up-button, QSpinBox::down-button {"
    "  background-color: #4a4a4a; border: none; width: 16px;"
    "}"
    "QCheckBox, QRadioButton { spacing: 6px; color: #cccccc; }"
    "QCheckBox::indicator {"
    "  width: 13px; height: 13px; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; background-color: #2b2b2b;"
    "}"
    "QRadioButton::indicator {"
    "  width: 13px; height: 13px; border: 1px solid #1e1e1e;"
    "  border-radius: 7px; background-color: #2b2b2b;"
    "}"
    "QCheckBox::indicator:checked, QRadioButton::indicator:checked {"
    "  background-color: #4a7fbf; border-color: #4a7fbf;"
    "}"
    "QPushButton {"
    "  background-color: #595959; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; padding: 4px 10px; color: #cccccc;"
    "}"
    "QPushButton:hover   { background-color: #686868; }"
    "QPushButton:pressed { background-color: #3a3a3a; }"
    "QPushButton#exportBtn {"
    "  background-color: #3d6e3d; border: 1px solid #2a5a2a;"
    "  color: #ffffff; font-weight: bold; font-size: 13px; padding: 7px 14px;"
    "}"
    "QPushButton#exportBtn:hover   { background-color: #4a7f4a; }"
    "QPushButton#exportBtn:pressed { background-color: #2a5a2a; }"
    "QPlainTextEdit {"
    "  background-color: #252525; border: 1px solid #1a1a1a;"
    "  border-radius: 2px; color: #b8b8b8;"
    "  font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; padding: 4px;"
    "}"
    "QScrollBar:vertical   { background: #2b2b2b; width: 8px;  margin: 0; }"
    "QScrollBar:horizontal { background: #2b2b2b; height: 8px; margin: 0; }"
    "QScrollBar::handle:vertical, QScrollBar::handle:horizontal {"
    "  background: #5a5a5a; border-radius: 4px; min-height: 20px; min-width: 20px;"
    "}"
    "QFrame#divider { background-color: #1e1e1e; max-height: 1px; }"
)


def _maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


class PC2ExporterWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(PC2ExporterWindow, self).__init__(parent or _maya_main_window())
        self.setWindowTitle("PC2 Exporter")
        self.setMinimumSize(540, 720)
        self.setStyleSheet(QSS)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self._ref_data = []
        self._build_ui()
        self._refresh_rigs()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(self._label("PC2 Exporter", "heading"))
        root.addWidget(self._label("Export meshes to Point Cache (.pc2)", "sub"))
        root.addWidget(self._divider())

        # Target Source (New)
        root.addWidget(self._label("Target Mode", "section"))
        src_row = QtWidgets.QHBoxLayout()
        self._rb_rigs = QtWidgets.QRadioButton("Referenced Rigs (_geo / _lod_0 filtered)")
        self._rb_rigs.setChecked(True)
        self._rb_sel = QtWidgets.QRadioButton("Viewport Selection")
        self._rb_sel.setToolTip("Directly export whatever meshes you have selected.")
        src_row.addWidget(self._rb_rigs)
        src_row.addWidget(self._rb_sel)
        src_row.addStretch()
        root.addLayout(src_row)
        
        self._rb_rigs.toggled.connect(self._on_source_changed)
        root.addWidget(self._divider())

        # Rig list
        root.addWidget(self._label("Referenced Rigs", "section"))
        self._rig_list = QtWidgets.QListWidget()
        self._rig_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._rig_list.setMinimumHeight(120)
        self._rig_list.itemSelectionChanged.connect(self._on_rig_selected)
        root.addWidget(self._rig_list)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)
        for label, slot in [("Select All",  self._select_all),
                            ("Select None", self._select_none),
                            ("Refresh",     self._refresh_rigs)]:
            b = QtWidgets.QPushButton(label)
            b.setFixedHeight(24)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._info_label = self._readonly_field("Select a rig above to see details")
        self._file_label = self._readonly_field("")
        root.addWidget(self._info_label)
        root.addWidget(self._file_label)
        root.addWidget(self._divider())

        # Output directory
        root.addWidget(self._label("Output Directory", "section"))
        dir_row = QtWidgets.QHBoxLayout()
        self._out_dir = QtWidgets.QLineEdit("C:/temp/pc2_exports")
        self._out_dir.setFixedHeight(24)
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.setFixedSize(72, 24)
        browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(self._out_dir)
        dir_row.addWidget(browse_btn)
        root.addLayout(dir_row)
        root.addWidget(self._divider())

        # Frame range
        root.addWidget(self._label("Frame Range", "section"))
        self._start, self._end, self._step = self._build_frame_range(root)
        root.addWidget(self._divider())

        # Options
        root.addWidget(self._label("Options", "section"))
        self._world_space = QtWidgets.QCheckBox("Export in World Space")
        self._world_space.setChecked(True)
        self._subfolders = QtWidgets.QCheckBox("Create sub-folder per rig/selection")
        self._subfolders.setChecked(True)
        root.addWidget(self._world_space)
        root.addWidget(self._subfolders)
        root.addWidget(self._divider())

        # Log
        root.addWidget(self._label("Log", "section"))
        self._log = QtWidgets.QPlainTextEdit()
        self._log.setPlainText("Ready.")
        self._log.setReadOnly(True)
        root.addWidget(self._log, stretch=1)

        # Buttons
        bot_row = QtWidgets.QHBoxLayout()
        export_btn = QtWidgets.QPushButton("Run Export")
        export_btn.setObjectName("exportBtn")
        export_btn.setFixedHeight(34)
        export_btn.clicked.connect(self._run_export)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setFixedSize(72, 34)
        close_btn.clicked.connect(self.close)
        bot_row.addWidget(export_btn)
        bot_row.addWidget(close_btn)
        root.addLayout(bot_row)

    def _build_frame_range(self, parent_layout):
        fr_row = QtWidgets.QHBoxLayout()
        def spinbox(lo, hi, val):
            sb = QtWidgets.QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setFixedHeight(24)
            return sb

        start = spinbox(-99999, 99999, int(cmds.playbackOptions(q=True, minTime=True)))
        end   = spinbox(-99999, 99999, int(cmds.playbackOptions(q=True, maxTime=True)))
        step  = spinbox(1, 100, 1)

        for lbl, widget in [("Start", start), ("End", end), ("Step", step)]:
            fr_row.addWidget(QtWidgets.QLabel(lbl))
            fr_row.addWidget(widget)

        scene_btn = QtWidgets.QPushButton("Scene Range")
        scene_btn.setFixedSize(90, 24)
        scene_btn.clicked.connect(lambda: (
            start.setValue(int(cmds.playbackOptions(q=True, minTime=True))),
            end.setValue(int(cmds.playbackOptions(q=True, maxTime=True))),
        ))
        fr_row.addStretch()
        fr_row.addWidget(scene_btn)
        parent_layout.addLayout(fr_row)
        return start, end, step

    @staticmethod
    def _divider():
        f = QtWidgets.QFrame()
        f.setObjectName("divider")
        f.setFrameShape(QtWidgets.QFrame.HLine)
        f.setFixedHeight(1)
        return f

    @staticmethod
    def _label(text, obj_name):
        lbl = QtWidgets.QLabel(text.upper() if obj_name == "section" else text)
        lbl.setObjectName(obj_name)
        return lbl

    @staticmethod
    def _readonly_field(placeholder):
        field = QtWidgets.QLineEdit(placeholder)
        field.setReadOnly(True)
        field.setFixedHeight(24)
        return field

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_source_changed(self):
        is_rig = self._rb_rigs.isChecked()
        self._rig_list.setEnabled(is_rig)
        if not is_rig:
            self._info_label.setText("Mode: Viewport Selection Active")
            self._file_label.setText("Will export meshes currently selected in Maya viewport.")
        else:
            self._on_rig_selected()

    def _refresh_rigs(self):
        self._ref_data = get_reference_nodes()
        self._rig_list.clear()
        self.log("Refreshed - found {} valid rig(s) with _geo geometry.\n".format(len(self._ref_data)))
        if not self._ref_data:
            item = QtWidgets.QListWidgetItem("  (no rigs matching _geo found)")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self._rig_list.addItem(item)
            return
        for ref in self._ref_data:
            mc = len(ref["meshes"])
            self._rig_list.addItem("  {}   [{} valid mesh{}]".format(
                ref["namespace"], mc, "es" if mc != 1 else ""))

    def _on_rig_selected(self):
        if not self._rb_rigs.isChecked():
            return
        items = self._rig_list.selectedItems()
        if not items or not self._ref_data:
            return
        ref = self._ref_data[self._rig_list.row(items[-1])]
        self._info_label.setText("Namespace: {}   |   Meshes: {}".format(
            ref["namespace"], len(ref["meshes"])))
        self._file_label.setText("File: {}".format(ref["filename"]))

    def _select_all(self):
        self._rig_list.selectAll()

    def _select_none(self):
        self._rig_list.clearSelection()
        self._info_label.setText("Select a rig above to see details")
        self._file_label.setText("")

    def _browse(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._out_dir.text())
        if path:
            self._out_dir.setText(path)

    def _run_export(self):
        output_dir  = self._out_dir.text().strip()
        start_frame = self._start.value()
        end_frame   = self._end.value()
        frame_step  = self._step.value()
        world_space = self._world_space.isChecked()
        subfolders  = self._subfolders.isChecked()

        if not output_dir:
            QtWidgets.QMessageBox.warning(self, "No Directory", "Please specify an output directory.")
            return

        items_to_export = []

        # Route A: Viewport Selection
        if self._rb_sel.isChecked():
            sel = cmds.ls(selection=True, long=True) or []
            if not sel:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select meshes in the viewport.")
                return

            meshes = []
            for s in sel:
                # Add if selection is mesh transform/shape directly
                shapes = cmds.listRelatives(s, shapes=True, type="mesh", fullPath=True, noIntermediate=True) or []
                if shapes:
                    meshes.append(s)
                elif cmds.nodeType(s) == "mesh":
                    parent = cmds.listRelatives(s, parent=True, fullPath=True)[0]
                    meshes.append(parent)

                # Add descendant meshes 
                desc = cmds.listRelatives(s, allDescendents=True, type="mesh", fullPath=True, noIntermediate=True) or []
                for m in desc:
                    parent = cmds.listRelatives(m, parent=True, fullPath=True)[0]
                    meshes.append(parent)

            meshes = list(set(meshes))
            if not meshes:
                QtWidgets.QMessageBox.warning(self, "No Meshes", "No polygonal meshes found in selection.")
                return

            items_to_export.append({
                "namespace": "viewport_selection",
                "meshes": meshes
            })

        # Route B: Referenced Rigs
        else:
            selected_rows = [self._rig_list.row(i) for i in self._rig_list.selectedItems()]
            if not selected_rows:
                QtWidgets.QMessageBox.warning(self, "No Rigs Selected", "Please select at least one rig.")
                return
            for idx in selected_rows:
                items_to_export.append(self._ref_data[idx])

        os.makedirs(output_dir, exist_ok=True)
        self.log("\n-- Export started --------------------------\n")
        self.log("Frames: {} -> {}  Step: {}  WorldSpace: {}\n".format(
            start_frame, end_frame, frame_step, world_space))

        total_ok = total_err = 0

        for ref in items_to_export:
            self.log("\nTarget: {} ({} meshes)\n".format(ref["namespace"], len(ref["meshes"])))
            
            out_dir = os.path.join(output_dir, ref["namespace"]) if subfolders else output_dir
            exported, errors = export_pc2_for_ref(
                ref_info    = ref,
                output_dir  = out_dir,
                start_frame = start_frame,
                end_frame   = end_frame,
                frame_step  = frame_step,
                world_space = world_space,
            )

            for path in exported:
                self.log("  [OK]    {}\n".format(path))
            for mesh, err in errors:
                self.log("  [FAIL] {} - {}\n".format(mesh, err))

            total_ok  += len(exported)
            total_err += len(errors)

        self.log("\n-- Done: {} exported, {} failed ------------\n".format(total_ok, total_err))

    def log(self, msg):
        for line in msg.split("\n"):
            self._log.appendPlainText(line)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()


# ============================================================================
#  Entry Point
# ============================================================================

_window = None

def show():
    global _window
    try:
        _window.close()
        _window.deleteLater()
    except Exception:
        pass
    _window = PC2ExporterWindow()
    _window.show()

def log(msg):
    if _window is not None:
        _window.log(msg)
    else:
        print(msg, end="")

show()