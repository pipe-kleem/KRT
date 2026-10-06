# -*- coding: utf-8 -*-
"""
Cache Exporter - Referenced Rig Picker for Maya
------------------------------------------------
Exports geometry caches (PC2 or Alembic) for all meshes in referenced rigs.
Includes automated Wrinkle Map (JSON) extraction for PC2 formats.

Usage:
    Run in Maya's Script Editor (Python tab).
"""

import os
import re
import shutil
import uuid
import fnmatch
import json
from collections import Counter

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

FORMAT_PC2     = "PC2"
FORMAT_ALEMBIC = "Alembic"
FORMATS        = [FORMAT_PC2, FORMAT_ALEMBIC]

# ============================================================================
#  Logic Layer
# ============================================================================

def get_reference_nodes():
    raw = []
    for ref_node in cmds.ls(type="reference") or []:
        if ref_node == "sharedReferenceNode":
            continue
        try:
            filename = cmds.referenceQuery(ref_node, filename=True)
        except Exception:
            continue

        try:
            ns = cmds.referenceQuery(ref_node, namespace=True) or ""
            ns = ns.strip().lstrip(":")
        except Exception:
            ns = ""
        if not ns:
            ns = os.path.splitext(os.path.basename(filename))[0]

        meshes = []
        for mesh in cmds.ls(type="mesh", long=True) or []:
            try:
                if cmds.referenceQuery(mesh, referenceNode=True) != ref_node:
                    continue
                parents = cmds.listRelatives(mesh, parent=True, fullPath=True)
                if parents and parents[0] not in meshes:
                    meshes.append(parents[0])
            except Exception:
                continue

        raw.append({
            "refNode":   ref_node,
            "namespace": ns,
            "filename":  filename,
            "meshes":    meshes,
        })

    name_count = Counter(r["namespace"] for r in raw)
    name_seen  = {}
    for ref in raw:
        ns = ref["namespace"]
        if name_count[ns] > 1:
            name_seen[ns] = name_seen.get(ns, 0) + 1
            ref["namespace"] = "{}_{}".format(ns, str(name_seen[ns]).zfill(2))

    return raw

def sanitize_name(node_name):
    short = node_name.split("|")[-1]
    return short.split(":")[-1] if ":" in short else short

def get_scene_fps():
    return _FPS_MAP.get(cmds.currentUnit(query=True, time=True), 24.0)

def _lod_folder(mesh_name):
    m = re.search(r'_[Ll][Oo][Dd]_?(\d+)$', mesh_name)
    return ("lod{}".format(m.group(1)), mesh_name) if m else ("", mesh_name)

def _restore_maya_state(original_time, original_sel):
    cmds.currentTime(original_time, edit=True, update=True)
    if original_sel:
        cmds.select(original_sel, replace=True)
    else:
        cmds.select(clear=True)

# ----------------------------------------------------------------------------
#  Wrinkle Map Export (JSON)
# ----------------------------------------------------------------------------

def export_wrinkle_for_ref(ref_info, meshes, output_dir, start_frame, end_frame):
    exported = []
    errors = []
    target_pattern = "Morpher_CC_Base_Body*"
    
    bs_mesh_mapping = {}
    found_blendshapes = []
    
    for transform in meshes:
        history = cmds.listHistory(transform) or []
        blendshapes = cmds.ls(history, type='blendShape')
        
        for bs in blendshapes:
            base_name = bs.split('|')[-1]
            name_without_namespace = base_name.split(':')[-1]
            
            if fnmatch.fnmatch(name_without_namespace, target_pattern):
                if bs not in found_blendshapes:
                    short_mesh_name = transform.split('|')[-1]
                    clean_mesh_name = short_mesh_name.split(':')[-1]
                    
                    bs_mesh_mapping[bs] = clean_mesh_name
                    found_blendshapes.append(bs)

    if not found_blendshapes:
        errors.append(("Wrinkle Map", "No matching blendshapes ({}) found in this selection.".format(target_pattern)))
        return exported, errors

    for node in found_blendshapes:
        if not cmds.objExists(node):
            continue
            
        aliases = cmds.aliasAttr(node, query=True)
        if not aliases:
            continue
            
        bs_names = aliases[0::2]
        anim_data = {"frames": {}}

        for frame in range(int(start_frame), int(end_frame) + 1):
            frame_data = {}
            for name in bs_names:
                attr_path = "{}.{}".format(node, name)
                try:
                    val = cmds.getAttr(attr_path, time=frame)
                    if val is not None and abs(val) > 0.0001: 
                        frame_data[name] = round(val, 4)
                except Exception:
                    pass
            
            if frame_data:
                anim_data["frames"][str(frame)] = frame_data

        mesh_name = bs_mesh_mapping.get(node, "UnknownMesh")
        node_file_path = os.path.join(output_dir, "{}_wrinkle.json".format(mesh_name)).replace("\\", "/")

        try:
            with open(node_file_path, 'w') as f:
                json.dump(anim_data, f, indent=4)
            exported.append(node_file_path)
        except Exception as exc:
            errors.append((mesh_name, "Failed to write JSON: {}".format(exc)))

    return exported, errors

# ----------------------------------------------------------------------------
#  PC2 Export
# ----------------------------------------------------------------------------

def export_pc2_for_ref(ref_info, output_dir, start_frame, end_frame,
                       frame_step, world_space):
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

    meshes_sorted  = sorted(meshes)
    shape_nodes    = []
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

    log("  [PC2] Running cacheFile for {} mesh(es)...\n".format(len(shape_nodes)))
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

    def _mcx_name(idx):
        return cache_name + ("" if idx == 0 else str(idx)) + ".mcx"

    mcx_to_mesh = {}
    for idx, transform in enumerate(mesh_per_shape):
        fname = _mcx_name(idx)
        if os.path.exists(os.path.join(tmp_dir, fname)):
            mcx_to_mesh[fname[:-4]] = transform
        else:
            errors.append((sanitize_name(transform),
                           "MCX not written by Maya (index {})".format(idx)))

    log("  [PC2] Mapped {} .mcx file(s) to meshes.\n".format(len(mcx_to_mesh)))

    for mcx_base, transform in mcx_to_mesh.items():
        mesh_name  = sanitize_name(transform)
        lod_sub, _ = _lod_folder(mesh_name)
        save_dir   = os.path.join(output_dir, lod_sub) if lod_sub else output_dir
        os.makedirs(save_dir, exist_ok=True)

        pc2_tmp = safe_dir + mcx_base + ".pc2"
        pc2_dst = os.path.join(save_dir, mesh_name + ".pc2")

        try:
            mel.eval('cacheFile -pc2 0 -pcf "{}" -f "{}" -dir "{}"'.format(
                pc2_tmp, mcx_base, safe_dir))
        except Exception as exc:
            errors.append((mesh_name, "cacheFile -pc2 failed: {}".format(exc)))
            continue

        try:
            shutil.copy2(pc2_tmp, pc2_dst)
            exported.append(pc2_dst)
            log("  Saved: {}\n".format(
                os.path.join(lod_sub, mesh_name + ".pc2") if lod_sub else mesh_name + ".pc2"))
        except Exception as exc:
            errors.append((mesh_name, "copy failed: {}".format(exc)))

    if not DEBUG_KEEP_TMP:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    log("  Temp files cleaned up.\n")

    return exported, errors

# ----------------------------------------------------------------------------
#  Alembic Export
# ----------------------------------------------------------------------------

def export_alembic_for_ref(ref_info, output_dir, start_frame, end_frame,
                           frame_step, world_space):
    exported = []
    errors   = []
    meshes   = ref_info["meshes"]

    if not meshes:
        return exported, errors

    if not cmds.pluginInfo("AbcExport", query=True, loaded=True):
        try:
            cmds.loadPlugin("AbcExport")
        except Exception as exc:
            errors.append(("AbcExport", "Plugin not available: {}".format(exc)))
            return exported, errors

    os.makedirs(output_dir, exist_ok=True)

    frame_step = max(1, int(frame_step))
    namespace  = ref_info["namespace"]
    abc_path   = os.path.join(output_dir, namespace + ".abc").replace("\\", "/")

    roots     = " ".join("-root {}".format(t) for t in meshes)
    ws_flag   = "-worldSpace" if world_space else ""
    step_flag = "-step {}".format(1.0 / frame_step) if frame_step > 1 else ""

    job = (
        "-frameRange {sf} {ef} "
        "{step} "
        "-dataFormat ogawa "
        "-stripNamespaces "
        "{ws} "
        "{roots} "
        "-file \"{abc}\""
    ).format(
        sf    = int(start_frame),
        ef    = int(end_frame),
        step  = step_flag,
        ws    = ws_flag,
        roots = roots,
        abc   = abc_path,
    ).strip()

    log("  [ABC] Exporting {} mesh(es) -> {}\n".format(len(meshes), namespace + ".abc"))

    try:
        cmds.AbcExport(j=job)
        exported.append(abc_path)
        log("  Saved: {}\n".format(namespace + ".abc"))
    except Exception as exc:
        errors.append((namespace, "AbcExport failed: {}".format(exc)))

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
    "QListWidget:focus { border: 1px solid #1e1e1e; outline: none; }"
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
    "QComboBox {"
    "  background-color: #2b2b2b; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; padding: 3px 6px; color: #cccccc;"
    "}"
    "QComboBox:focus { border-color: #4a7fbf; }"
    "QComboBox::drop-down { border: none; width: 20px; }"
    "QComboBox::down-arrow { width: 8px; height: 8px; }"
    "QComboBox QAbstractItemView {"
    "  background-color: #2b2b2b; border: 1px solid #1e1e1e;"
    "  selection-background-color: #4a7fbf; color: #cccccc;"
    "}"
    "QCheckBox { spacing: 6px; color: #cccccc; }"
    "QCheckBox::indicator {"
    "  width: 13px; height: 13px; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; background-color: #2b2b2b;"
    "}"
    "QCheckBox::indicator:checked { background-color: #4a7fbf; border-color: #4a7fbf; }"
    "QRadioButton { spacing: 6px; color: #cccccc; }"
    "QRadioButton::indicator {"
    "  width: 13px; height: 13px; border: 1px solid #1e1e1e;"
    "  border-radius: 7px; background-color: #2b2b2b;"
    "}"
    "QRadioButton::indicator:checked { background-color: #4a7fbf; border-color: #4a7fbf; }"
    "QPushButton {"
    "  background-color: #595959; border: 1px solid #1e1e1e;"
    "  border-radius: 2px; padding: 4px 10px; color: #cccccc;"
    "}"
    "QPushButton:hover   { background-color: #686868; }"
    "QPushButton:pressed { background-color: #3a3a3a; }"
    "QPushButton:disabled { color: #555555; background-color: #404040; }"
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
    "QScrollBar::add-line:vertical,   QScrollBar::sub-line:vertical   { height: 0; }"
    "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:  0; }"
    "QFrame#divider { background-color: #1e1e1e; max-height: 1px; }"
)

def _maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)

class CacheExporterWindow(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(CacheExporterWindow, self).__init__(parent or _maya_main_window())
        self.setWindowTitle("Cache Exporter")
        self.setMinimumSize(520, 680)
        self.setStyleSheet(QSS)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self._ref_data = []
        self._build_ui()
        self._refresh_rigs()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        root.addWidget(self._label("Cache Exporter", "heading"))
        root.addWidget(self._label("Export referenced rigs to PC2 or Alembic cache", "sub"))
        root.addWidget(self._divider())

        root.addWidget(self._label("Target Mode", "section"))
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(20)
        mode_row.setContentsMargins(0, 2, 0, 2)
        self._mode_ref = QtWidgets.QRadioButton("Reference List")
        self._mode_sel = QtWidgets.QRadioButton("Selected Objects")
        self._mode_ref.setChecked(True)
        self._mode_ref.setToolTip("Export all meshes from the rigs selected in the list below.")
        self._mode_sel.setToolTip(
            "Export only the meshes currently selected in the Maya viewport.\n"
            "The rig list resolves which reference each mesh belongs to.")
        self._mode_ref.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_ref)
        mode_row.addWidget(self._mode_sel)
        mode_row.addStretch()
        root.addLayout(mode_row)
        root.addWidget(self._divider())

        root.addWidget(self._label("Referenced Rigs", "section"))
        self._rig_list = QtWidgets.QListWidget()
        self._rig_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._rig_list.setFixedHeight(140)
        self._rig_list.itemSelectionChanged.connect(self._on_rig_selected)
        root.addWidget(self._rig_list)

        self._rig_btns = []
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)
        for label, slot in [("Select All",  self._select_all),
                             ("Select None", self._select_none),
                             ("Refresh",     self._refresh_rigs)]:
            b = QtWidgets.QPushButton(label)
            b.setFixedHeight(24)
            b.clicked.connect(slot)
            self._rig_btns.append(b)
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._info_label = self._readonly_field("Select a rig above to see details")
        root.addWidget(self._info_label)
        root.addWidget(self._divider())

        root.addWidget(self._label("Output Directory", "section"))
        dir_row = QtWidgets.QHBoxLayout()
        dir_row.setSpacing(6)
        self._out_dir = QtWidgets.QLineEdit("{scene_dir}/cache_exports")
        self._out_dir.setFixedHeight(24)
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.setFixedSize(72, 24)
        browse_btn.clicked.connect(self._browse)
        open_btn = QtWidgets.QPushButton()
        open_btn.setFixedSize(24, 24)
        open_btn.setToolTip("Open output folder in Explorer / Finder")
        open_btn.setIcon(QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_DirOpenIcon))
        open_btn.clicked.connect(self._open_output_folder)
        dir_row.addWidget(self._out_dir)
        dir_row.addWidget(browse_btn)
        dir_row.addWidget(open_btn)
        root.addLayout(dir_row)
        hint = self._label("Token: {scene_dir} = directory of the current Maya scene file", "sub")
        root.addWidget(hint)
        root.addWidget(self._divider())

        root.addWidget(self._label("Frame Range", "section"))
        self._start, self._end, self._step = self._build_frame_range(root)
        root.addWidget(self._divider())

        root.addWidget(self._label("Format & Options", "section"))

        fmt_row = QtWidgets.QHBoxLayout()
        fmt_row.setSpacing(8)
        fmt_lbl = QtWidgets.QLabel("Format:")
        fmt_lbl.setFixedWidth(60)
        self._fmt_combo = QtWidgets.QComboBox()
        self._fmt_combo.setFixedHeight(24)
        self._fmt_combo.setFixedWidth(120)
        for fmt in FORMATS:
            self._fmt_combo.addItem(fmt)
        self._fmt_combo.currentTextChanged.connect(self._on_format_changed)
        fmt_row.addWidget(fmt_lbl)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        root.addLayout(fmt_row)

        self._world_space = QtWidgets.QCheckBox("Export in World Space")
        self._world_space.setChecked(True)
        self._subfolders = QtWidgets.QCheckBox("Create sub-folder per rig")
        self._subfolders.setChecked(True)
        
        self._export_wrinkle = QtWidgets.QCheckBox("Export Wrinkle Maps (JSON)")
        self._export_wrinkle.setChecked(True)
        
        root.addWidget(self._world_space)
        root.addWidget(self._subfolders)
        root.addWidget(self._export_wrinkle)

        ignore_row = QtWidgets.QHBoxLayout()
        ignore_row.setSpacing(6)
        ignore_row.setContentsMargins(0, 2, 0, 0)
        ignore_lbl = QtWidgets.QLabel("Ignore prefixes:")
        ignore_lbl.setFixedWidth(100)
        self._ignore_prefixes = QtWidgets.QLineEdit("CTRL_, TEXT_, FRM_")
        self._ignore_prefixes.setFixedHeight(24)
        self._ignore_prefixes.setToolTip(
            "Comma-separated prefixes. Meshes whose short name starts with any of these "
            "will be skipped. Case-insensitive.  Example: CTRL_, TEXT_, FRM_")
        ignore_row.addWidget(ignore_lbl)
        ignore_row.addWidget(self._ignore_prefixes)
        root.addLayout(ignore_row)
        root.addWidget(self._divider())

        root.addWidget(self._label("Log", "section"))
        self._log = QtWidgets.QPlainTextEdit()
        self._log.setPlainText("Ready.")
        self._log.setReadOnly(True)
        self._log.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        root.addWidget(self._log, stretch=1)

        bot_row = QtWidgets.QHBoxLayout()
        bot_row.setSpacing(8)
        self._export_btn = QtWidgets.QPushButton("Export  [ PC2 ]")
        self._export_btn.setObjectName("exportBtn")
        self._export_btn.setFixedHeight(34)
        self._export_btn.clicked.connect(self._run_export)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setFixedSize(72, 34)
        close_btn.clicked.connect(self.close)
        bot_row.addWidget(self._export_btn)
        bot_row.addWidget(close_btn)
        root.addLayout(bot_row)

    def _build_frame_range(self, parent_layout):
        fr_row = QtWidgets.QHBoxLayout()
        fr_row.setSpacing(6)

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

    def _on_format_changed(self, fmt):
        self._export_btn.setText("Export  [ {} ]".format(fmt))
        if fmt == FORMAT_PC2:
            self._export_wrinkle.setEnabled(True)
        else:
            self._export_wrinkle.setEnabled(False)

    def _on_mode_changed(self):
        ref_mode = self._mode_ref.isChecked()
        self._rig_list.setEnabled(ref_mode)
        for b in self._rig_btns:
            b.setEnabled(ref_mode)

    def _refresh_rigs(self):
        self._ref_data = get_reference_nodes()
        self._rig_list.clear()
        self.log("Refreshed - found {} referenced rig(s).\n".format(len(self._ref_data)))
        if not self._ref_data:
            item = QtWidgets.QListWidgetItem("  (no referenced rigs found)")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self._rig_list.addItem(item)
            return
        for ref in self._ref_data:
            mc = len(ref["meshes"])
            self._rig_list.addItem("  {}   [{} mesh{}]".format(
                ref["namespace"], mc, "es" if mc != 1 else ""))

    def _on_rig_selected(self):
        items = self._rig_list.selectedItems()
        if not items or not self._ref_data:
            return
        ref = self._ref_data[self._rig_list.row(items[-1])]
        self._info_label.setText("{}   |   {} meshes   |   {}".format(
            ref["namespace"], len(ref["meshes"]), ref["filename"]))

    def _select_all(self):
        self._rig_list.selectAll()

    def _select_none(self):
        self._rig_list.clearSelection()
        self._info_label.setText("Select a rig above to see details")

    def _browse(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._resolve_output_dir())
        if path:
            self._out_dir.setText(path)

    def _open_output_folder(self):
        path = self._resolve_output_dir()
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(
                self, "Folder Not Found",
                "The output folder does not exist yet:\n{}".format(path))
            return
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(os.path.normpath(path)))

    def _resolve_output_dir(self):
        raw = self._out_dir.text().strip()
        scene_file = cmds.file(query=True, sceneName=True) or ""
        if scene_file:
            scene_dir = os.path.dirname(scene_file)
        else:
            scene_dir = os.path.expanduser("~")
            if "{scene_dir}" in raw:
                self.log("  [WARN] Scene not saved -- {{scene_dir}} resolved to: {}\n".format(
                    scene_dir))
        return raw.replace("{scene_dir}", scene_dir)

    def _get_ignore_prefixes(self):
        raw = self._ignore_prefixes.text()
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    def _run_export(self):
        output_dir  = self._resolve_output_dir()
        start_frame = self._start.value()
        end_frame   = self._end.value()
        frame_step  = self._step.value()
        world_space = self._world_space.isChecked()
        subfolders  = self._subfolders.isChecked()
        ignore_pfx  = self._get_ignore_prefixes()
        sel_mode    = self._mode_sel.isChecked()
        fmt         = self._fmt_combo.currentText()

        if not output_dir:
            QtWidgets.QMessageBox.warning(self, "No Output Directory",
                                          "Please specify an output directory.")
            return

        os.makedirs(output_dir, exist_ok=True)

        if sel_mode:
            jobs = self._resolve_selection_jobs()
            if jobs is None:
                return
        else:
            selected_rows = [self._rig_list.row(i)
                             for i in self._rig_list.selectedItems()]
            if not selected_rows:
                QtWidgets.QMessageBox.warning(self, "No Rigs Selected",
                                              "Please select at least one rig.")
                return
            jobs = [(self._ref_data[i], self._ref_data[i]["meshes"])
                    for i in selected_rows]

        self.log("\n-- Export started [{}] ({}) --------\n".format(
            fmt, "Selected Objects" if sel_mode else "Reference List"))
        self.log("Frames: {} -> {}  Step: {}  WorldSpace: {}\n".format(
            start_frame, end_frame, frame_step, world_space))

        total_ok = total_err = 0

        for ref, meshes in jobs:
            self.log("\nRig: {} ({} meshes)\n".format(ref["namespace"], len(meshes)))
            if not meshes:
                self.log("  [WARN] No meshes - skipping.\n")
                continue

            if ignore_pfx:
                kept    = [m for m in meshes
                           if not any(sanitize_name(m).lower().startswith(p)
                                      for p in ignore_pfx)]
                skipped = len(meshes) - len(kept)
                if skipped:
                    self.log("  [SKIP] {} mesh(es) matched ignore prefixes.\n".format(skipped))
            else:
                kept = meshes

            if not kept:
                self.log("  [WARN] All meshes ignored - skipping rig.\n")
                continue

            out_dir = os.path.join(output_dir, fmt.lower())
            if subfolders:
                out_dir = os.path.join(out_dir, ref["namespace"])

            if fmt == FORMAT_PC2:
                exported, errors = export_pc2_for_ref(
                    ref_info    = dict(ref, meshes=kept),
                    output_dir  = out_dir,
                    start_frame = start_frame,
                    end_frame   = end_frame,
                    frame_step  = frame_step,
                    world_space = world_space,
                )
                
                if self._export_wrinkle.isChecked():
                    self.log("  [JSON] Extracting Wrinkle Maps...\n")
                    w_exported, w_errors = export_wrinkle_for_ref(
                        ref_info    = ref,
                        meshes      = kept,
                        output_dir  = out_dir,
                        start_frame = start_frame,
                        end_frame   = end_frame
                    )
                    exported.extend(w_exported)
                    errors.extend(w_errors)
            else:
                exported, errors = export_alembic_for_ref(
                    ref_info    = dict(ref, meshes=kept),
                    output_dir  = out_dir,
                    start_frame = start_frame,
                    end_frame   = end_frame,
                    frame_step  = frame_step,
                    world_space = world_space,
                )

            for path in exported:
                self.log("  [OK]   {}\n".format(path))
            for mesh, err in errors:
                self.log("  [FAIL] {} - {}\n".format(mesh, err))

            total_ok  += len(exported)
            total_err += len(errors)

        self.log("\n-- Done: {} exported, {} failed ------------\n".format(
            total_ok, total_err))

    def _resolve_selection_jobs(self):
        sel = cmds.ls(selection=True, long=True) or []
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Nothing Selected", "Select one or more meshes in the Maya viewport first.")
            return None

        meshes = []
        for node in sel:
            if cmds.nodeType(node) == "transform":
                shapes = cmds.listRelatives(node, shapes=True, type="mesh", fullPath=True, noIntermediate=True) or []
                meshes.extend(shapes)
            elif cmds.nodeType(node) == "mesh":
                if not cmds.getAttr(node + ".intermediateObject"):
                    meshes.append(node)
                
        descendants = cmds.listRelatives(sel, allDescendents=True, type="mesh", fullPath=True, noIntermediate=True) or []
        meshes.extend(descendants)
        meshes = list(set(meshes))

        if not meshes:
            QtWidgets.QMessageBox.warning(self, "No Meshes", "No valid meshes found in the current selection.")
            return None

        ref_by_node = {r["refNode"]: r for r in self._ref_data}
        batches = {}
        local_meshes = set()

        # Route referenced nodes into batches, and un-referenced (imported) nodes into a generic local set
        for mesh_shape in meshes:
            parents = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
            transform = parents[0] if parents else mesh_shape
            
            try:
                ref_node = cmds.referenceQuery(transform, referenceNode=True)
                if ref_node in ref_by_node:
                    batches.setdefault(ref_node, set()).add(transform)
                else:
                    local_meshes.add(transform)
            except Exception:
                local_meshes.add(transform)

        jobs = [(ref_by_node[rn], list(ms)) for rn, ms in batches.items()]
        
        # Construct a dummy reference info dictionary for any non-referenced objects found
        if local_meshes:
            local_info = {
                "refNode": None,
                "namespace": "Local_Export",
                "filename": "Local Scene",
                "meshes": list(local_meshes)
            }
            jobs.append((local_info, list(local_meshes)))

        if not jobs:
            QtWidgets.QMessageBox.warning(self, "Export Failed", "Could not resolve selection into exportable jobs.")
            return None

        return jobs

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
    _window = CacheExporterWindow()
    _window.show()

def log(msg):
    if _window is not None:
        _window.log(msg)
    else:
        print(msg, end="")

show()