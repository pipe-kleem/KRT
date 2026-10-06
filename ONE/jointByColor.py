import sys
import re
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

# PySide2 / PySide6 Compatibility Layer
try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui


class SkinWeightColorRampQt(QtWidgets.QDialog):
    # Palette for Left/Right mirror joint pair badges
    SIDE_COLOR_PALETTE = [
        "#3498db", "#e67e22", "#9b59b6", "#2ecc71", 
        "#e74c3c", "#1abc9c", "#f39c12", "#d35400", 
        "#8e44ad", "#16a085", "#c0392b", "#27ae60"
    ]

    def __init__(self, parent=None):
        super(SkinWeightColorRampQt, self).__init__(parent or self.get_maya_main_window())
        self.setWindowTitle("Skin Weight Tool (4 Decimal Precision + Side Tags)")
        self.setObjectName("SkinWeightColorRampQtWindow")
        self.resize(600, 720)
        
        # Explicitly add Minimize & Maximize window control buttons
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowMinMaxButtonsHint
            | QtCore.Qt.WindowCloseButtonHint
        )

        # API 2.0 Handles
        self.dag_path = None
        self.component = None
        self.skin_fn = None
        self.inf_indices = om.MIntArray()

        # Mappings & Data Caches
        self.verts = []
        self.skin_cluster = None
        self.num_inf = 0
        self.num_verts = 0
        self.inf_idx_to_name = {}
        self.inf_name_to_idx = {}
        self.cached_weights = []
        self.initial_weights_snapshot = None

        # Lock System & UI State
        self.joint_locks = {}
        self.joint_widgets = {}  
        self.is_updating_ui = False
        self.is_chunk_open = False

        # Scale & Palette Settings
        self.base_font_size = 11  
        self.current_scale = 1.0
        self.current_preset = "Default (Red to White)"
        self.custom_min_color = (1.0, 1.0, 1.0)
        self.custom_max_color = (1.0, 0.0, 0.0)

        self.build_ui()

    @staticmethod
    def get_maya_main_window():
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.objectName() == "MayaWindow":
                return widget
        return None

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Load Button
        self.load_btn = QtWidgets.QPushButton("Load Selected Vertices")
        self.load_btn.setStyleSheet("background-color: #3b4d5e; font-weight: bold; padding: 6px;")
        self.load_btn.clicked.connect(self.load_vertices)
        main_layout.addWidget(self.load_btn)

        # 2. UI Scale Group
        scale_box = QtWidgets.QGroupBox("UI Scale & Text Zoom")
        scale_layout = QtWidgets.QVBoxLayout(scale_box)
        
        slider_row = QtWidgets.QHBoxLayout()
        self.scale_label = QtWidgets.QLabel("UI Zoom Factor:")
        self.scale_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.scale_slider.setRange(70, 200)
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(self.on_scale_changed)
        self.scale_val_lbl = QtWidgets.QLabel("100%")
        slider_row.addWidget(self.scale_label)
        slider_row.addWidget(self.scale_slider)
        slider_row.addWidget(self.scale_val_lbl)
        scale_layout.addLayout(slider_row)

        btn_row = QtWidgets.QHBoxLayout()
        zoom_out_btn = QtWidgets.QPushButton("Zoom Out (-)")
        zoom_in_btn = QtWidgets.QPushButton("Zoom In (+)")
        reset_btn = QtWidgets.QPushButton("Reset (100%)")
        zoom_out_btn.clicked.connect(lambda: self.scale_slider.setValue(self.scale_slider.value() - 10))
        zoom_in_btn.clicked.connect(lambda: self.scale_slider.setValue(self.scale_slider.value() + 10))
        reset_btn.clicked.connect(lambda: self.scale_slider.setValue(100))
        btn_row.addWidget(zoom_out_btn)
        btn_row.addWidget(zoom_in_btn)
        btn_row.addWidget(reset_btn)
        scale_layout.addLayout(btn_row)

        main_layout.addWidget(scale_box)

        # 3. Ramp Preset Controls
        ramp_box = QtWidgets.QGroupBox("Color Ramp Controls")
        ramp_layout = QtWidgets.QVBoxLayout(ramp_box)
        
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(["Default (Red to White)", "Heatmap (Rainbow)", "Grayscale", "Custom Palette"])
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_row.addWidget(self.preset_combo)
        ramp_layout.addLayout(preset_row)

        flip_btn = QtWidgets.QPushButton("Flip Ramp Colors ⇄")
        flip_btn.clicked.connect(self.flip_color_ramp)
        ramp_layout.addWidget(flip_btn)

        main_layout.addWidget(ramp_box)

        # 4. Global Lock & Selection Controls
        control_box = QtWidgets.QGroupBox("Global Joint Actions")
        control_layout = QtWidgets.QVBoxLayout(control_box)

        lock_row = QtWidgets.QHBoxLayout()
        lock_all_btn = QtWidgets.QPushButton("Lock All Joints")
        unlock_all_btn = QtWidgets.QPushButton("Unlock All Joints")
        lock_all_btn.clicked.connect(lambda: self.set_all_locks(True))
        unlock_all_btn.clicked.connect(lambda: self.set_all_locks(False))
        lock_row.addWidget(lock_all_btn)
        lock_row.addWidget(unlock_all_btn)

        sel_row = QtWidgets.QHBoxLayout()
        sel_all_btn = QtWidgets.QPushButton("Select All Influences")
        sel_unlocked_btn = QtWidgets.QPushButton("Select Unlocked Joints")
        sel_all_btn.clicked.connect(self.select_all_joints)
        sel_unlocked_btn.clicked.connect(self.select_unlocked_joints)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(sel_unlocked_btn)

        control_layout.addLayout(lock_row)
        control_layout.addLayout(sel_row)
        main_layout.addWidget(control_box)

        # 5. Scroll Area for Joints
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QtWidgets.QWidget()
        self.joints_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.joints_layout.setAlignment(QtCore.Qt.AlignTop)
        self.joints_layout.setSpacing(4)
        self.scroll_area.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll_area)

        self.apply_font_scale()

    def parse_side_info(self, joint_name):
        """Parses joint name to extract side (L/R) and base name."""
        patterns = [
            (r'^(.*)_([LRlr])_(.*)$', lambda m: (m.group(2).upper(), f"{m.group(1)}_{m.group(3)}")),
            (r'^(.*)_([LRlr])$', lambda m: (m.group(2).upper(), m.group(1))),
            (r'^([LRlr])_(.*)$', lambda m: (m.group(1).upper(), m.group(2))),
        ]
        
        for pattern, extractor in patterns:
            match = re.match(pattern, joint_name)
            if match:
                side, base = extractor(match)
                return side, base
                
        return None, joint_name

    def compute_joint_tag_colors(self, joint_names):
        """Computes matching color tags for corresponding L/R joint pairs."""
        base_groups = {}
        for name in joint_names:
            side, base = self.parse_side_info(name)
            if base not in base_groups:
                base_groups[base] = []
            base_groups[base].append((name, side))

        tag_info = {}
        color_idx = 0

        for base, items in base_groups.items():
            sides = [s for _, s in items if s in ["L", "R"]]
            has_pair = ("L" in sides and "R" in sides)

            if has_pair:
                color = self.SIDE_COLOR_PALETTE[color_idx % len(self.SIDE_COLOR_PALETTE)]
                color_idx += 1
                for name, side in items:
                    tag_info[name] = {"side": side or "?", "color": color, "is_paired": True}
            else:
                for name, side in items:
                    if side in ["L", "R"]:
                        tag_info[name] = {"side": side, "color": "#7f8c8d", "is_paired": False}
                    else:
                        tag_info[name] = {"side": "S", "color": "#546e7a", "is_paired": False}

        return tag_info

    def on_scale_changed(self, value):
        self.current_scale = value / 100.0
        self.scale_val_lbl.setText(f"{value}%")
        self.apply_font_scale()

    def apply_font_scale(self):
        font_size = int(self.base_font_size * self.current_scale)
        btn_height = int(24 * self.current_scale)
        padding = int(3 * self.current_scale)

        style_sheet = f"""
            QWidget {{
                font-size: {font_size}pt;
            }}
            QPushButton {{
                min-height: {btn_height}px;
                padding: {padding}px;
            }}
            QSpinBox, QDoubleSpinBox {{
                min-height: {btn_height}px;
            }}
        """
        self.setStyleSheet(style_sheet)

    def get_color_for_value(self, value):
        val = max(0.0, min(1.0, float(value)))

        if self.current_preset == "Default (Red to White)":
            r, g, b = 1.0, 1.0 - val, 1.0 - val
        elif self.current_preset == "Heatmap (Rainbow)":
            if val <= 0.25:
                t = val / 0.25
                r, g, b = 0.0, t, 0.4 + 0.6 * t
            elif val <= 0.5:
                t = (val - 0.25) / 0.25
                r, g, b = 0.0, 1.0, 1.0 - t
            elif val <= 0.75:
                t = (val - 0.5) / 0.25
                r, g, b = t, 1.0, 0.0
            else:
                t = (val - 0.75) / 0.25
                r, g, b = 1.0, 1.0 - t, 0.0
        elif self.current_preset == "Grayscale":
            v = 0.1 + 0.9 * val
            r, g, b = v, v, v
        else:
            r = self.custom_min_color[0] + (self.custom_max_color[0] - self.custom_min_color[0]) * val
            g = self.custom_min_color[1] + (self.custom_max_color[1] - self.custom_min_color[1]) * val
            b = self.custom_min_color[2] + (self.custom_max_color[2] - self.custom_min_color[2]) * val

        return int(r * 255), int(g * 255), int(b * 255)

    def on_preset_changed(self, text):
        self.current_preset = text
        if self.cached_weights:
            self.sync_ui_from_weights_array(self.cached_weights)

    def flip_color_ramp(self):
        self.custom_min_color, self.custom_max_color = self.custom_max_color, self.custom_min_color
        if self.cached_weights:
            self.sync_ui_from_weights_array(self.cached_weights)

    def toggle_joint_lock(self, j_name):
        is_locked = not self.joint_locks.get(j_name, True)
        self.joint_locks[j_name] = is_locked
        self.update_lock_button_ui(j_name)

    def set_all_locks(self, state):
        for j_name in self.joint_locks:
            self.joint_locks[j_name] = state
            self.update_lock_button_ui(j_name)

    def select_single_joint(self, j_name):
        """Selects a specific joint in Maya scene."""
        if cmds.objExists(j_name):
            cmds.select(j_name, replace=True)

    def select_all_joints(self):
        """Selects all active loaded influences in Maya scene."""
        active_joints = [j for j in self.joint_widgets.keys() if cmds.objExists(j)]
        if active_joints:
            cmds.select(active_joints, replace=True)

    def select_unlocked_joints(self):
        """Selects all currently unlocked joints in Maya scene."""
        unlocked = [
            j for j, is_locked in self.joint_locks.items() 
            if not is_locked and cmds.objExists(j)
        ]
        if unlocked:
            cmds.select(unlocked, replace=True)

    def update_lock_button_ui(self, j_name):
        if j_name in self.joint_widgets:
            btn = self.joint_widgets[j_name]["btn"]
            slider = self.joint_widgets[j_name]["slider"]
            spin = self.joint_widgets[j_name]["spin"]
            is_locked = self.joint_locks.get(j_name, True)

            btn.setText("Locked" if is_locked else "Unlocked")
            btn.setStyleSheet("background-color: #8c3b3b;" if is_locked else "background-color: #3b8c4c;")
            slider.setEnabled(not is_locked)
            spin.setEnabled(not is_locked)

    def load_vertices(self):
        sel = cmds.ls(sl=True, flatten=True)
        self.verts = [v for v in sel if ".vtx[" in v]

        if not self.verts:
            cmds.warning("Please select at least one vertex.")
            self.clear_ui()
            return

        mesh = self.verts[0].split('.')[0]
        shapes = cmds.listRelatives(mesh, shapes=True)
        if not shapes:
            return

        history = cmds.listHistory(shapes[0])
        skin_clusters = cmds.ls(history, type="skinCluster")

        if not skin_clusters:
            cmds.warning("No skin cluster found.")
            self.clear_ui()
            return

        self.skin_cluster = skin_clusters[0]

        sel_list = om.MSelectionList()
        for v in self.verts:
            sel_list.add(v)
        self.dag_path, self.component = sel_list.getComponent(0)

        sc_list = om.MSelectionList()
        sc_list.add(self.skin_cluster)
        sc_mobj = sc_list.getDependNode(0)
        self.skin_fn = oma.MFnSkinCluster(sc_mobj)

        inf_paths = self.skin_fn.influenceObjects()
        self.num_inf = len(inf_paths)
        self.inf_indices = om.MIntArray(range(self.num_inf))

        self.inf_name_to_idx = {}
        self.inf_idx_to_name = {}
        for idx, path in enumerate(inf_paths):
            j_name = path.partialPathName()
            self.inf_name_to_idx[j_name] = idx
            self.inf_idx_to_name[idx] = j_name

        self.build_ui_sliders()

    def clear_ui(self):
        while self.joints_layout.count():
            child = self.joints_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.joint_widgets = {}

    def get_vertex_avg_weights_api(self):
        if not self.skin_fn or not self.dag_path or not self.component:
            return {}, []

        weights, _ = self.skin_fn.getWeights(self.dag_path, self.component)
        weights_list = list(weights)
        self.num_verts = len(weights_list) // self.num_inf

        avg_weights = {}
        for j_idx in range(self.num_inf):
            j_name = self.inf_idx_to_name[j_idx]
            tot = sum(weights_list[v * self.num_inf + j_idx] for v in range(self.num_verts))
            avg_weights[j_name] = tot / float(self.num_verts)

        return avg_weights, weights_list

    def build_ui_sliders(self):
        self.clear_ui()
        avg_weights, self.cached_weights = self.get_vertex_avg_weights_api()
        active_joints = {j: w for j, w in avg_weights.items() if w > 0.00001}

        self.joint_locks = {j_name: True for j_name in active_joints.keys()}
        tag_info_map = self.compute_joint_tag_colors(active_joints.keys())

        for j_name, avg in sorted(active_joints.items(), key=lambda x: x[1], reverse=True):
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(6)

            lock_btn = QtWidgets.QPushButton("Locked")
            lock_btn.setFixedWidth(70)
            lock_btn.clicked.connect(lambda *args, j=j_name: self.toggle_joint_lock(j))

            # SELECT JOINT BUTTON FOR SPECIFIC ROW
            sel_btn = QtWidgets.QPushButton("Sel")
            sel_btn.setFixedWidth(38)
            sel_btn.setStyleSheet("background-color: #2c3e50; font-weight: bold;")
            sel_btn.setToolTip(f"Select '{j_name}' in Maya viewport")
            sel_btn.clicked.connect(lambda *args, j=j_name: self.select_single_joint(j))

            # CIRCULAR SIDE TAG BADGE
            info = tag_info_map.get(j_name, {"side": "S", "color": "#546e7a", "is_paired": False})
            side_tag = QtWidgets.QLabel(info["side"])
            side_tag.setAlignment(QtCore.Qt.AlignCenter)
            side_tag.setFixedSize(22, 22)
            
            tag_style = f"""
                QLabel {{
                    background-color: {info['color']};
                    color: white;
                    font-weight: bold;
                    border-radius: 11px;
                    font-size: 10pt;
                }}
            """
            side_tag.setStyleSheet(tag_style)
            side_tag.setToolTip(f"Side Pair Match: {j_name}")

            label = QtWidgets.QLabel(j_name)
            label.setMinimumWidth(100)

            # DOUBLE SPINBOX configured for 4 decimal places (0.0000)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0.0000, 1.0000)
            spin.setDecimals(4)
            spin.setSingleStep(0.0001)
            spin.setValue(avg)
            spin.setEnabled(False)

            # HIGH RESOLUTION SLIDER (0 to 10,000 mapping to 0.0000 to 1.0000)
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(0, 10000)
            slider.setValue(int(avg * 10000))
            slider.setEnabled(False)

            slider.sliderMoved.connect(lambda val, s=spin: s.setValue(val / 10000.0))
            slider.sliderPressed.connect(lambda *args, j=j_name: self.on_slider_pressed(j))
            slider.sliderMoved.connect(lambda val, j=j_name: self.on_slider_drag(j, val / 10000.0))
            slider.sliderReleased.connect(lambda *args, j=j_name, s=spin: self.on_slider_release(j, s.value()))

            row_layout.addWidget(lock_btn)
            row_layout.addWidget(sel_btn)
            row_layout.addWidget(side_tag)
            row_layout.addWidget(label)
            row_layout.addWidget(spin)
            row_layout.addWidget(slider)

            self.joints_layout.addWidget(row_widget)
            self.joint_widgets[j_name] = {
                "btn": lock_btn, 
                "sel_btn": sel_btn,
                "tag": side_tag, 
                "slider": slider, 
                "spin": spin, 
                "label": label, 
                "container": row_widget
            }

            self.update_lock_button_ui(j_name)

        self.sync_ui_from_weights_array(self.cached_weights)
        self.apply_font_scale()

    def on_slider_pressed(self, j_name):
        if self.initial_weights_snapshot is None:
            _, self.initial_weights_snapshot = self.get_vertex_avg_weights_api()
            cmds.undoInfo(openChunk=True, chunkName="SkinWeightDragQt")
            self.is_chunk_open = True

    def on_slider_drag(self, joint_name, requested_val):
        if self.is_updating_ui or not self.skin_fn:
            return

        target_idx = self.inf_name_to_idx[joint_name]
        
        unlocked_indices = [
            self.inf_name_to_idx[j] for j, is_locked in self.joint_locks.items() 
            if not is_locked and j != joint_name and j in self.inf_name_to_idx
        ]

        if not unlocked_indices:
            self.sync_ui_from_weights_array(self.cached_weights)
            return

        weights = list(self.cached_weights)
        num_inf, num_verts = self.num_inf, self.num_verts

        for v in range(num_verts):
            offset = v * num_inf
            t_idx = offset + target_idx
            curr_target_weight = weights[t_idx]

            unlocked_available = sum(weights[offset + idx] for idx in unlocked_indices)

            max_available_val = curr_target_weight + unlocked_available
            target_val = min(requested_val, max_available_val)

            delta = target_val - curr_target_weight

            if delta > 0:  
                if unlocked_available > 0.00001:
                    for idx in unlocked_indices:
                        ratio = weights[offset + idx] / unlocked_available
                        weights[offset + idx] = max(0.0, weights[offset + idx] - (delta * ratio))
                weights[t_idx] = target_val

            elif delta < 0:  
                abs_delta = abs(delta)
                if unlocked_available > 0.00001:
                    for idx in unlocked_indices:
                        ratio = weights[offset + idx] / unlocked_available
                        weights[offset + idx] += abs_delta * ratio
                else:
                    share = abs_delta / float(len(unlocked_indices))
                    for idx in unlocked_indices:
                        weights[offset + idx] += share

                weights[t_idx] = target_val

        self.skin_fn.setWeights(self.dag_path, self.component, self.inf_indices, om.MDoubleArray(weights), normalize=False)
        self.sync_ui_from_weights_array(weights)

    def on_slider_release(self, joint_name, val):
        if self.is_updating_ui or not self.verts:
            return

        try:
            if self.initial_weights_snapshot is not None:
                self.skin_fn.setWeights(self.dag_path, self.component, self.inf_indices, om.MDoubleArray(self.initial_weights_snapshot), normalize=False)
            cmds.skinPercent(self.skin_cluster, self.verts, transformValue=[(joint_name, val)])
        finally:
            if self.is_chunk_open:
                cmds.undoInfo(closeChunk=True)
                self.is_chunk_open = False
            self.initial_weights_snapshot = None

        _, self.cached_weights = self.get_vertex_avg_weights_api()
        self.sync_ui_from_weights_array(self.cached_weights)

    def sync_ui_from_weights_array(self, weights_list):
        if self.is_updating_ui or not weights_list:
            return

        self.is_updating_ui = True
        try:
            num_verts = len(weights_list) // self.num_inf
            for j_name, widgets in self.joint_widgets.items():
                j_idx = self.inf_name_to_idx[j_name]
                tot = sum(weights_list[v * self.num_inf + j_idx] for v in range(num_verts))
                avg_val = tot / float(num_verts)

                widgets["spin"].setValue(avg_val)
                widgets["slider"].setValue(int(avg_val * 10000))

                r, g, b = self.get_color_for_value(avg_val)
                widgets["container"].setStyleSheet(f"background-color: rgb({r}, {g}, {b}); color: black;")
        finally:
            self.is_updating_ui = False


# Launch Tool Window safely inside Maya
try:
    skin_tool_dialog.close()
    skin_tool_dialog.deleteLater()
except NameError:
    pass

skin_tool_dialog = SkinWeightColorRampQt()
skin_tool_dialog.show()