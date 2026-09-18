"""Auto-split from graph.py."""
from ._shared import *
from .catalog import _find_guide_root


class CustomStepListEditor(QtWidgets.QWidget):
    """Editor for one of mGear's pre/post Custom Step script lists.

    Serializes to the same "name | path" comma-separated legacy string
    format Shifter's own CustomStepListWidget falls back to reading (see
    mgear.shifter.custom_step_widget.CustomStepData / _parseLegacyFormat),
    so steps added here run correctly in a normal Shifter build and remain
    readable if the guide is later opened in mGear's own Custom Steps tab.
    A '*' prefix on a stored name marks a step disabled; that maps to the
    checkbox state here.
    """

    def __init__(self, parent=None):
        super(CustomStepListEditor, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet("background:#1e1e1e; border:1px solid #333;")
        self.list_widget.setFixedHeight(110)
        self.list_widget.itemChanged.connect(lambda _item: self._notify())
        layout.addWidget(self.list_widget)

        btn_row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("+ Add Script")
        btn_add.clicked.connect(self.add_script)
        btn_remove = QtWidgets.QPushButton("Remove")
        btn_remove.clicked.connect(self.remove_selected)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_remove)
        layout.addLayout(btn_row)

        # Set by the owning panel; called whenever the list content changes
        # so it can be written straight back onto the guide root's attr.
        self.on_change = None

    def add_script(self):
        res = cmds.fileDialog2(fm=4, ff="Python (*.py)")  # fm=4: multiple existing files
        if not res:
            return
        for path in res:
            name = os.path.splitext(os.path.basename(path))[0]
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            item.setData(QtCore.Qt.UserRole, path)
            item.setToolTip(path)
            self.list_widget.addItem(item)
        self._notify()

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._notify()

    def _notify(self):
        if callable(self.on_change):
            self.on_change()

    def to_legacy_string(self):
        parts = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(QtCore.Qt.UserRole) or ""
            prefix = "" if item.checkState() == QtCore.Qt.Checked else "*"
            parts.append(f"{prefix}{item.text()} | {path}")
        return ", ".join(parts)

    def load_from_string(self, data_string):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        stripped = (data_string or "").strip()
        if stripped.startswith("{"):
            # A v2 JSON blob written by Shifter's own Custom Steps tab
            # (groups, templates, ...) - too rich to round-trip here safely.
            # Leave it untouched rather than risk mangling it.
            item = QtWidgets.QListWidgetItem("<advanced step list - edit via mGear's own Custom Steps tab>")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.list_widget.addItem(item)
        else:
            for entry in stripped.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                active = True
                if entry.startswith("*"):
                    active = False
                    entry = entry[1:]
                name, _, path = entry.partition("|")
                item = QtWidgets.QListWidgetItem(name.strip())
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked if active else QtCore.Qt.Unchecked)
                item.setData(QtCore.Qt.UserRole, path.strip())
                item.setToolTip(path.strip())
                self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)


class GuideSettingsPanel(QtWidgets.QWidget):
    """The full mGear Shifter "Guide Settings" dialog for the guide root,
    reproduced tab-for-tab (Guide Settings / Custom Steps / Naming Rules /
    Blueprint) so switching over to Shifter's own UI is never required.

    These are rig-wide options (they live as attributes on the single
    "guide" root transform), not per-component, so this panel always edits
    whichever guide root currently exists in the scene rather than the
    selected graph node.
    """

    _COLOR_ROWS = [
        ("L", "L_color_fk", "L_color_ik"),
        ("C", "C_color_fk", "C_color_ik"),
        ("R", "R_color_fk", "R_color_ik"),
    ]

    def __init__(self, graph_widget):
        super(GuideSettingsPanel, self).__init__()
        self.graph_widget = graph_widget

        self._fields = {}  # attr name -> widget
        self._updating = False
        # Stage 31, request #3: set whenever a field is edited while there is
        # no guide root in the scene to write it to. Those edits live only in
        # the panel until a guide exists, so push_pending_to_scene() (called
        # right after Build Guides) knows it must push them onto the new
        # guide root rather than letting refresh_from_scene() pull mGear's
        # freshly-built defaults back over the top of them.
        self._pending_scene_push = False

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        self.lbl_status = QtWidgets.QLabel(
            "No mGear guide in the scene yet - these settings are still editable.\n"
            "They're saved with the rig, and applied to the guide as soon as you Build Guides."
        )
        self.lbl_status.setStyleSheet("color: #ffcc66; padding: 4px;")
        self.lbl_status.setWordWrap(True)
        root_layout.addWidget(self.lbl_status)

        btn_refresh = QtWidgets.QPushButton("🔄 Refresh from Scene")
        btn_refresh.clicked.connect(self.refresh_from_scene)
        root_layout.addWidget(btn_refresh)

        self.inner_tabs = QtWidgets.QTabWidget()
        self.inner_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #333; } QTabBar::tab { padding: 4px 6px; font-size: 11px; }"
        )
        root_layout.addWidget(self.inner_tabs)

        self.inner_tabs.addTab(self._make_scroll_page(self._build_guide_settings_page), "Guide Settings")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_custom_steps_page), "Custom Steps")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_naming_rules_page), "Naming Rules")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_blueprint_page), "Blueprint")

        self.inner_tabs.setEnabled(False)

    # -- page / group scaffolding ------------------------------------------
    def _make_scroll_page(self, build_fn):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #252526; }")
        container = QtWidgets.QWidget()
        scroll.setWidget(container)
        page_layout = QtWidgets.QVBoxLayout(container)
        page_layout.setAlignment(QtCore.Qt.AlignTop)
        page_layout.setContentsMargins(4, 4, 4, 4)
        page_layout.setSpacing(10)
        build_fn(page_layout)
        return scroll

    def _group(self, target_layout, title):
        box = QtWidgets.QGroupBox(title)
        box.setStyleSheet(
            "QGroupBox { color: #2bb5a8; font-weight: bold; border: 1px solid #333; "
            "border-radius: 4px; margin-top: 8px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        layout = QtWidgets.QFormLayout(box)
        layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        target_layout.addWidget(box)
        return box, layout

    # -- field builders ------------------------------------------------------
    def _bool_field(self, layout, label, attr_name):
        chk = QtWidgets.QCheckBox()
        chk.toggled.connect(lambda v, a=attr_name: self._set_attr(a, v))
        layout.addRow(label, chk)
        self._fields[attr_name] = chk
        return chk

    def _string_field(self, layout, label, attr_name, with_browse=False):
        row = QtWidgets.QHBoxLayout()
        edit = QtWidgets.QLineEdit()
        edit.editingFinished.connect(lambda a=attr_name, e=edit: self._set_attr(a, e.text()))
        row.addWidget(edit)
        if with_browse:
            btn = QtWidgets.QPushButton("...")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _, a=attr_name, e=edit: self._browse_into(a, e))
            row.addWidget(btn)
        wrap = QtWidgets.QWidget(); wrap.setLayout(row)
        layout.addRow(label, wrap)
        self._fields[attr_name] = edit
        return edit

    def _enum_field(self, layout, label, attr_name, options):
        combo = QtWidgets.QComboBox()
        combo.addItems(options)
        combo.currentIndexChanged.connect(lambda idx, a=attr_name: self._set_attr(a, idx))
        layout.addRow(label, combo)
        self._fields[attr_name] = combo
        return combo

    def _int_field(self, layout, label, attr_name, minimum, maximum):
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.valueChanged.connect(lambda v, a=attr_name: self._set_attr(a, v))
        layout.addRow(label, spin)
        self._fields[attr_name] = spin
        return spin

    # -- Tab 1: Guide Settings ----------------------------------------------
    def _build_guide_settings_page(self, page_layout):
        self._build_rig_settings_group(page_layout)
        self._build_anim_channels_group(page_layout)
        self._build_base_rig_control_group(page_layout)
        self._build_skinning_group(page_layout)
        self._build_joint_settings_group(page_layout)
        self._build_data_collector_group(page_layout)
        self._build_color_settings_group(page_layout)

    def _build_rig_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Rig Settings")
        self._string_field(layout, "Rig Name", "rig_name")
        self._enum_field(layout, "Debug Mode", "mode", ["Final", "WIP"])
        self._enum_field(layout, "Guide Build Steps", "step",
                         ["All Steps", "Objects", "Properties", "Operators", "Connect", "Joints", "Finalize"])

    def _build_anim_channels_group(self, page_layout):
        box, layout = self._group(page_layout, "Animation Channels Settings")
        self._bool_field(layout, "Add Internal Proxy Channels", "proxyChannels")
        self._bool_field(layout, "Use Classic Channel Names", "classicChannelNames")
        self._bool_field(layout, "Use Component Instance Name for Attributes Prefix", "attrPrefixName")

    def _build_base_rig_control_group(self, page_layout):
        box, layout = self._group(page_layout, "Base Rig Control")
        self._bool_field(layout, "Use World Ctl or Custom Name", "worldCtl")
        self._string_field(layout, "Name", "world_ctl_name")

    def _build_skinning_group(self, page_layout):
        box, layout = self._group(page_layout, "Skinning Settings")
        self._bool_field(layout, "Import Skin", "importSkin")
        self._string_field(layout, "Skin Path", "skin", with_browse=True)

    def _build_joint_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Joint Settings")
        self._bool_field(layout, "Separated Joint Structure", "joint_rig")
        self._bool_field(layout, "Force World Oriented", "joint_worldOri")
        self._bool_field(layout, "Force uniform scaling in all joints", "force_uniScale")
        self._bool_field(layout, "Connect to existing joints", "connect_joints")
        self._bool_field(layout, "Force Segment Scale Compensate", "force_SSC")

    def _build_data_collector_group(self, page_layout):
        box, layout = self._group(page_layout, "Post Build Data Collector")
        self._bool_field(layout, "Collect Data on External File", "data_collector")
        self._string_field(layout, "Data Path", "data_collector_path", with_browse=True)
        self._bool_field(layout, "Collect Data Embedded on Root/Custom Joint", "data_collector_embedded")
        self._string_field(layout, "Custom Joint or Transform", "data_collector_embedded_custom_joint")

    def _build_color_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Color Settings")
        self._bool_field(layout, "Use RGB Colors", "Use_RGB_Color")
        for side_label, fk_attr, ik_attr in self._COLOR_ROWS:
            self._int_field(layout, f"{side_label}  FK", fk_attr, 0, 31)
            self._int_field(layout, f"{side_label}  IK", ik_attr, 0, 31)

    # -- Tab 2: Custom Steps --------------------------------------------------
    def _build_custom_steps_page(self, page_layout):
        box, form = self._group(page_layout, "Pre Custom Steps")
        self._bool_field(form, "Run Pre Custom Steps", "doPreCustomStep")
        self.pre_step_editor = CustomStepListEditor()
        self.pre_step_editor.on_change = lambda: self._set_attr("preCustomStep", self.pre_step_editor.to_legacy_string())
        form.addRow(self.pre_step_editor)

        box2, form2 = self._group(page_layout, "Post Custom Steps")
        self._bool_field(form2, "Run Post Custom Steps", "doPostCustomStep")
        self.post_step_editor = CustomStepListEditor()
        self.post_step_editor.on_change = lambda: self._set_attr("postCustomStep", self.post_step_editor.to_legacy_string())
        form2.addRow(self.post_step_editor)

        hint = QtWidgets.QLabel(
            "Scripts run top to bottom; uncheck to skip without removing.\n"
            "This is mGear's own rig-wide Custom Steps mechanism - separate from "
            "the per-module script on the Node tab, which only runs for one component."
        )
        hint.setStyleSheet("color:#888; font-size:10px;")
        hint.setWordWrap(True)
        page_layout.addWidget(hint)

    # -- Tab 3: Naming Rules --------------------------------------------------
    def _build_naming_rules_page(self, page_layout):
        box, layout = self._group(page_layout, "Naming Rules")
        self._string_field(layout, "Ctl Name Rule", "ctl_name_rule")
        self._string_field(layout, "Joint Name Rule", "joint_name_rule")
        self._string_field(layout, "Ctl Name Extension", "ctl_name_ext")
        self._string_field(layout, "Joint Name Extension", "joint_name_ext")
        self._enum_field(layout, "Ctl Description Case", "ctl_description_letter_case",
                         ["Default", "Upper Case", "Lower Case", "Capitalization"])
        self._enum_field(layout, "Joint Description Case", "joint_description_letter_case",
                         ["Default", "Upper Case", "Lower Case", "Capitalization"])
        self._int_field(layout, "Ctl Index Padding", "ctl_index_padding", 0, 99)
        self._int_field(layout, "Joint Index Padding", "joint_index_padding", 0, 99)

        box2, layout2 = self._group(page_layout, "Side Names (Controls)")
        self._string_field(layout2, "Left", "side_left_name")
        self._string_field(layout2, "Right", "side_right_name")
        self._string_field(layout2, "Center", "side_center_name")

        box3, layout3 = self._group(page_layout, "Side Names (Joints)")
        self._string_field(layout3, "Left", "side_joint_left_name")
        self._string_field(layout3, "Right", "side_joint_right_name")
        self._string_field(layout3, "Center", "side_joint_center_name")

    # -- Tab 4: Blueprint ------------------------------------------------------
    def _build_blueprint_page(self, page_layout):
        box, layout = self._group(page_layout, "Blueprint Guide")
        self._bool_field(layout, "Use Blueprint", "use_blueprint")
        self._string_field(layout, "Blueprint Path", "blueprint_path", with_browse=True)

        box2, layout2 = self._group(page_layout, "Override Sections (use local values instead of blueprint)")
        self._bool_field(layout2, "Rig Settings", "override_rig_settings")
        self._bool_field(layout2, "Animation Channels", "override_anim_channels")
        self._bool_field(layout2, "Base Rig Control", "override_base_rig_control")
        self._bool_field(layout2, "Skinning", "override_skinning")
        self._bool_field(layout2, "Joint Settings", "override_joint_settings")
        self._bool_field(layout2, "Data Collector", "override_data_collector")
        self._bool_field(layout2, "Color Settings", "override_color_settings")
        self._bool_field(layout2, "Naming Rules", "override_naming_rules")
        self._bool_field(layout2, "Pre Custom Steps", "override_pre_custom_steps")
        self._bool_field(layout2, "Post Custom Steps", "override_post_custom_steps")

    # -- scene <-> UI sync --------------------------------------------------
    def _browse_into(self, attr_name, line_edit):
        res = cmds.fileDialog2(fm=1, ff="All Files (*.*)")
        if res:
            line_edit.setText(res[0])
            self._set_attr(attr_name, res[0])

    def _set_attr(self, attr_name, value):
        if self._updating:
            return
        root = _find_guide_root()
        if not root:
            # Stage 31, request #3: no guide to write to yet - the edit still
            # counts, it just has to wait for one. Remember that so it gets
            # pushed at build time instead of being silently dropped.
            self._pending_scene_push = True
            return
        try:
            plug = f"{root}.{attr_name}"
            if isinstance(value, bool):
                cmds.setAttr(plug, value)
            elif isinstance(value, str):
                cmds.setAttr(plug, value, type="string")
            else:
                cmds.setAttr(plug, value)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Could not set guide option '{attr_name}' - see Script Editor.")

    def get_settings_dict(self):
        """Snapshot of every field this panel manages, as plain JSON-safe
        values - independent of whether a guide root currently exists in
        the scene. Used by the standalone Graph Config JSON export."""
        data = {}
        for attr_name, widget in self._fields.items():
            if isinstance(widget, QtWidgets.QCheckBox):
                data[attr_name] = widget.isChecked()
            elif isinstance(widget, QtWidgets.QLineEdit):
                data[attr_name] = widget.text()
            elif isinstance(widget, QtWidgets.QComboBox):
                data[attr_name] = widget.currentIndex()
            elif isinstance(widget, QtWidgets.QSpinBox):
                data[attr_name] = widget.value()
        data["preCustomStep"] = self.pre_step_editor.to_legacy_string()
        data["postCustomStep"] = self.post_step_editor.to_legacy_string()
        return data

    def apply_settings_dict(self, data):
        """Inverse of get_settings_dict(): loads values into the UI, then -
        if a guide root actually exists in the scene right now - pushes
        them onto its real Maya attributes too, same as editing each field
        by hand would. If no guide exists yet, the UI still reflects the
        loaded values so 'Refresh from Scene' (or reloading this JSON) can
        push them once a guide has been built."""
        if not isinstance(data, dict):
            return
        self._updating = True
        try:
            for attr_name, widget in self._fields.items():
                if attr_name not in data:
                    continue
                value = data[attr_name]
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(value or "")
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(int(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))
            if "preCustomStep" in data:
                self.pre_step_editor.load_from_string(data["preCustomStep"] or "")
            if "postCustomStep" in data:
                self.post_step_editor.load_from_string(data["postCustomStep"] or "")
        except Exception:
            traceback.print_exc()
        finally:
            self._updating = False

        root = _find_guide_root()
        if not root:
            cmds.warning("Guide Settings loaded into the panel, but no guide root exists in the "
                         "scene yet - build a guide, then reload this JSON (or edit a field by "
                         "hand) to push these values onto it.")
            return
        for attr_name, value in data.items():
            if attr_name in self._fields:
                self._set_attr(attr_name, value)
        if "preCustomStep" in data:
            self._set_attr("preCustomStep", data["preCustomStep"] or "")
        if "postCustomStep" in data:
            self._set_attr("postCustomStep", data["postCustomStep"] or "")

    def push_pending_to_scene(self):
        """Stage 31, request #3: push settings the user edited while no guide
        existed onto the guide that has just been built.

        Called right after Build Guides and BEFORE refresh_from_scene(),
        because refresh reads the scene into the panel - which, on a
        just-built guide, would replace the rigger's settings with mGear's
        defaults, quietly losing them. Returns True if anything was pushed."""
        if not self._pending_scene_push:
            return False
        root = _find_guide_root()
        if not root:
            return False
        data = self.get_settings_dict()
        for attr_name, value in data.items():
            self._set_attr(attr_name, value)
        self._pending_scene_push = False
        cmds.warning("[KRT] Applied your Guide Settings to the newly built guide.")
        return True

    def refresh_from_scene(self):
        try:
            root = _find_guide_root()
        except Exception:
            traceback.print_exc()
            self.lbl_status.setText("Could not check the scene for a guide - see Script Editor.")
            self.lbl_status.setStyleSheet("color: #ff6666; padding: 4px;")
            self.inner_tabs.setEnabled(False)
            return

        if not root:
            # Stage 31, request #3: "i am again not able to change these
            # setting". This used to disable the entire tab strip whenever
            # no guide existed in the scene, which made every Guide Setting
            # unreachable until after a build - even though these values are
            # a property of the RIG, are saved in the guides JSON and the KRT
            # session JSON, and are exactly the sort of thing a rigger sets
            # up BEFORE building anything. They stay editable now: edits are
            # held in the panel, and pushed onto the guide root the moment
            # one exists (see push_pending_to_scene(), called right after
            # Build Guides).
            self.lbl_status.setText(
                "No mGear guide in the scene yet - these settings are still editable.\n"
                "They're saved with the rig, and applied to the guide as soon as you Build Guides.")
            self.lbl_status.setStyleSheet("color: #ffcc66; padding: 4px;")
            self.inner_tabs.setEnabled(True)
            return

        self.lbl_status.setText(f"Editing guide root: {root.split('|')[-1]}")
        self.lbl_status.setStyleSheet("color: #2bb5a8; padding: 4px;")
        self.inner_tabs.setEnabled(True)

        self._updating = True
        try:
            for attr_name, widget in self._fields.items():
                if not cmds.attributeQuery(attr_name, node=root, exists=True):
                    continue
                value = cmds.getAttr(f"{root}.{attr_name}")
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(value or "")
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(int(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))

            if cmds.attributeQuery("preCustomStep", node=root, exists=True):
                self.pre_step_editor.load_from_string(cmds.getAttr(f"{root}.preCustomStep") or "")
            if cmds.attributeQuery("postCustomStep", node=root, exists=True):
                self.post_step_editor.load_from_string(cmds.getAttr(f"{root}.postCustomStep") or "")
        except Exception:
            traceback.print_exc()
            self.lbl_status.setText(f"Editing guide root: {root.split('|')[-1]}  (some fields failed to load - see Script Editor)")
            self.lbl_status.setStyleSheet("color: #ffaa33; padding: 4px;")
        finally:
            self._updating = False
