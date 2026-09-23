"""Auto-split from widgets.py."""
from ._shared import *
from .collapse import CollapseMixin
from .cache_mixin import CacheMixin
from .dialogs import ErrorDialog
from .style import is_script_file_ref, panel_run_label, prompt_skincluster_naming_check, style_readonly_path_field, type_accent, type_bg_tint, type_icon
from .tweaker_group import TweakerVertexGroup, _NoteVerticalResizeHandle


class SortablePanel(CollapseMixin, CacheMixin, QtWidgets.QFrame):
    def __init__(self, title, p_type, default_val, workspace):
        super(SortablePanel, self).__init__()
        self.p_type = p_type
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint(p_type)
        self.accent = type_accent(p_type)
        self.uuid = uuid.uuid4().hex

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Toggle to include or exclude this panel from the main build")
        self.checkbox.toggled.connect(self.toggle_active)

        # Stage 17: a per-type icon, separate from the (renamable) title text
        # itself, so panel type reads at a glance even after a custom title.
        self.icon_label = QtWidgets.QLabel(type_icon(p_type))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip(p_type.replace("_", " ").title())

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox)
        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_edit)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        self.btn_del.setToolTip("Delete this panel completely")
        ctrl_layout.addWidget(self.btn_del)

        self.field = QtWidgets.QLineEdit(default_val)
        self.field.setToolTip("Path to the file, directory, or direct Python code")
        if p_type in READONLY_FIELD_TYPES:
            style_readonly_path_field(self.field, self.accent)
        elif p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ"):
            # Stage 19: this field locks itself the moment it holds a real
            # .py/.mel file path (same "set automatically, not typed by
            # hand" reasoning as the other read-only fields) but stays
            # editable for raw pasted code - see is_script_file_ref() and
            # _update_script_field_lock() below. INSTANCE_OBJ (Stage 40)
            # reuses this same field as its OPTIONAL custom transform
            # script - see the p_type == "INSTANCE_OBJ" block further down
            # for its own target_field/Delete All Instances UI.
            self.field.textChanged.connect(self._update_script_field_lock)
            self._update_script_field_lock()
        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.setToolTip("More Options, Adds, Copy & Paste")

        btn_txt = panel_run_label(p_type)
        self.btn_run = QtWidgets.QPushButton(btn_txt)
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")

        if p_type in ("NOTE", "DELETE_OBJ", "ZERO_OUT", "PARENT_OBJ"):
            # None of these types show the generic path/code field (see
            # below - it's hidden for all of them, they each have their
            # own dedicated name field instead), so Delete/More-Options go
            # up into the header row instead of sitting in a body row with
            # no field to anchor them - same top-right corner every other
            # card-style UI puts them in, and it's what keeps the cache/
            # RUN row below from looking lopsided with no field widget to
            # give it its usual shape.
            header_layout.addLayout(ctrl_layout)
            header_layout.addWidget(btn_dots)
        else:
            body_layout.addLayout(ctrl_layout)
            body_layout.addWidget(self.field)
            body_layout.addWidget(btn_dots)

        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ"):
            self.func_field = QtWidgets.QLineEdit()
            self.func_field.setPlaceholderText("Function (e.g. utils())")
            self.func_field.setFixedWidth(130)
            if self.p_type == "INSTANCE_OBJ":
                self.func_field.setToolTip(
                    "Optional - exec'd after the custom script above; leave "
                    "a 'transforms' list behind (same variable the script "
                    "itself can also set directly).")
            body_layout.addWidget(self.func_field)

            if self.p_type == "SCRIPT":
                # A SCRIPT panel runs inside KRT's own namespace, so anything
                # it defines/imports is invisible to Maya's Script Editor.
                # Tick this on a helper-library panel (utils.py) to copy the
                # names into Maya's global namespace after it runs.
                self.chk_share_global = QtWidgets.QCheckBox("🌐")
                self.chk_share_global.setToolTip(
                    "Share with Maya's global namespace.\n\n"
                    "A script panel normally runs in KRT's own namespace, so what it\n"
                    "defines or imports (UniUtils, helper functions...) cannot be seen\n"
                    "from Maya's Script Editor. Tick this on a helper-library panel and\n"
                    "everything it sets up becomes available there too, exactly as if\n"
                    "you had run the file in the Script Editor yourself.")
                body_layout.addWidget(self.chk_share_global)

        self._build_cache_controls(body_layout)
        body_layout.addWidget(self.btn_run)

        # Small reset button shown only when the panel is in the SHOW ERROR state.
        # Clicking it restores the run button to normal WITHOUT re-running.
        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        body_layout.addWidget(self.btn_reset_err)

        # Per-panel "Popup" tick: only JSON/Tweaker panels ever trigger the
        # SkinCluster-naming confirmation (prompt_skincluster_naming_check),
        # on both Save and Load - this lives right on the panel itself
        # (same row as the Cache tick) instead of a single workspace-wide
        # setting, so a rig with a lot of pre-existing mismatched names can
        # be silenced panel-by-panel without turning the popup off
        # everywhere. Unticking it does NOT skip the check itself - any
        # mismatch found is still renamed automatically, just without the
        # confirmation window (see naming_popup_enabled()).
        if p_type in ("JSON", "TWEAKER"):
            self.chk_naming_popup = QtWidgets.QCheckBox("Popup")
            self.chk_naming_popup.setChecked(True)
            self.chk_naming_popup.setToolTip(
                "When on, saving or loading a skin on this panel that finds "
                "skinCluster(s)\nnamed off KRT's '<mesh>_SkinCluster' convention pops up "
                "a confirmation\nbefore renaming them. Turn off to stop the popup on this "
                "panel - any\nmismatch found is still renamed automatically, just "
                "silently (logged to\nthe script editor instead).")
            self.chk_naming_popup.setStyleSheet("QCheckBox { color: #cccccc; font-size: 12px; margin-left: 6px; }")
            body_layout.addWidget(self.chk_naming_popup)

        self._build_cache_tick(body_layout)
        main_layout.addLayout(body_layout)

        if p_type == "JSON":
            skin_ext_layout = QtWidgets.QHBoxLayout()
            skin_ext_layout.setContentsMargins(25, 0, 0, 0)
            skin_ext_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText("Leave empty for selection...")
            btn_get_sel = QtWidgets.QPushButton("Get Selected")
            btn_get_sel.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes.clicked.connect(self.select_skin_meshes)
            skin_ext_layout.addWidget(self.mesh_field)
            skin_ext_layout.addWidget(btn_get_sel)
            skin_ext_layout.addWidget(btn_select_meshes)
            main_layout.addLayout(skin_ext_layout)

            joints_layout = QtWidgets.QHBoxLayout()
            joints_layout.setContentsMargins(25, 0, 0, 0)
            joints_layout.addWidget(QtWidgets.QLabel("Joints:"))
            self.joints_field = QtWidgets.QLineEdit()
            self.joints_field.setPlaceholderText("Influences for Bind All - auto-filled from the current skin on Save if left empty...")
            btn_get_sel_j = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_j.setToolTip("Store the currently selected joints into this field.")
            btn_get_sel_j.clicked.connect(self.get_selection_for_joints)
            btn_select_joints = QtWidgets.QPushButton("🎯 Select")
            btn_select_joints.setToolTip("Select the joints listed in this field in the viewport.")
            btn_select_joints.clicked.connect(self.select_skin_joints)
            joints_layout.addWidget(self.joints_field)
            joints_layout.addWidget(btn_get_sel_j)
            joints_layout.addWidget(btn_select_joints)
            main_layout.addLayout(joints_layout)

            # Stage 31 / 32 / 33: the studio's own re-skin (unbind keeping
            # weights, clear the stale bind pose, rebind to the same
            # influences - straight from the shipped RGreSkin MEL tool),
            # optionally performed with one or more controls temporarily
            # scaled up so the rebind's rest pose is computed at that scale.
            #
            # Stage 33: Scale Control(s) is now the gate for the whole
            # feature, not a separate checkbox - if it's empty, re-skin does
            # NOT run at all (Load Skin behaves exactly as before). Fill it
            # in (one or more controls, comma-separated) and re-skin runs
            # automatically after every successful load: every listed
            # control is scaled to Scale, the mesh(es) are re-bound, then
            # every control is restored - all with no button to press.
            reskin_row = QtWidgets.QHBoxLayout()
            reskin_row.setContentsMargins(25, 0, 0, 0)
            reskin_row.addWidget(QtWidgets.QLabel("Re-Skin after Load - Scale Control(s):"))
            self.reskin_ctl_field = QtWidgets.QLineEdit()
            self.reskin_ctl_field.setPlaceholderText(
                "Control(s) to scale during the rebind, comma-separated - leave empty to skip re-skin entirely...")
            self.reskin_ctl_field.setToolTip(
                "One or more controls (comma-separated) to temporarily scale while the "
                "mesh(es) are re-bound, then restore.\n\n"
                "This field is also the on/off switch for the whole Re-Skin feature: "
                "leave it EMPTY and Load Skin does nothing extra (no re-skin, no "
                "scaling) - fill in at least one control and re-skin runs automatically "
                "every time this panel loads its skin weights.")
            reskin_row.addWidget(self.reskin_ctl_field)
            btn_get_reskin_ctl = QtWidgets.QPushButton("Get Selected")
            btn_get_reskin_ctl.setToolTip("Store all currently selected controls into this field.")
            btn_get_reskin_ctl.clicked.connect(self.get_selection_for_reskin_control)
            reskin_row.addWidget(btn_get_reskin_ctl)

            reskin_row.addWidget(QtWidgets.QLabel("Scale:"))
            self.reskin_scale_field = QtWidgets.QLineEdit("1.0")
            self.reskin_scale_field.setFixedWidth(55)
            self.reskin_scale_field.setToolTip(
                "The scale every listed control is set to (uniformly) for the duration "
                "of the rebind, then restored from. This is a TARGET value, not a "
                "multiplier - and it only does anything for a control if it's DIFFERENT "
                "from that control's current scale. Entering a control's current scale "
                "here changes nothing for it (it never visibly moves), which looks "
                "exactly like 'nothing happened'.")
            reskin_row.addWidget(self.reskin_scale_field)
            main_layout.addLayout(reskin_row)

            bind_layout = QtWidgets.QHBoxLayout()
            bind_layout.setContentsMargins(25, 0, 0, 0)
            btn_bind_all = QtWidgets.QPushButton("🦴 Bind All (Meshes -> Joints)")
            btn_bind_all.setToolTip(
                "Default-bind every mesh in the Meshes field (or the current "
                "selection if that field is empty) to every joint in the "
                "Joints field. Meshes that already have a skinCluster are "
                "skipped, not overwritten.")
            btn_bind_all.clicked.connect(self.bind_all_meshes)
            bind_layout.addWidget(btn_bind_all)
            bind_layout.addStretch()
            main_layout.addLayout(bind_layout)

        if p_type == "TWEAKER":
            # Stage 21, request #1: a Tweaker panel can hold several
            # independent vertex groups - each with its own vertex names
            # (from a different source mesh if needed), its own additional
            # meshes, and its own bind-scale/influence-radius/full-weight-
            # radius/falloff settings. Every group runs as its own tweaker
            # setup when the panel's CREATE button is clicked. See
            # TweakerVertexGroup, add_tweaker_group()/remove_tweaker_group().
            groups_label = QtWidgets.QLabel("Vertex Groups (each targets its own vertices/mesh + settings):")
            groups_label.setStyleSheet("color: #888; font-size: 10px; margin-left: 25px;")
            main_layout.addWidget(groups_label)

            self.tweaker_groups_widget = QtWidgets.QWidget()
            self.tweaker_groups_box = QtWidgets.QVBoxLayout(self.tweaker_groups_widget)
            self.tweaker_groups_box.setContentsMargins(25, 0, 0, 0)
            self.tweaker_groups_box.setSpacing(4)
            self.tweaker_groups = []
            main_layout.addWidget(self.tweaker_groups_widget)

            add_row = QtWidgets.QHBoxLayout()
            add_row.setContentsMargins(25, 0, 0, 0)
            btn_add_group = QtWidgets.QPushButton("+ Add Vertex Group")
            btn_add_group.setToolTip(
                "Add another independent vertex group - different vertices "
                "(from a different mesh if needed), its own additional "
                "meshes, and its own bind-scale/influence/falloff settings.")
            btn_add_group.clicked.connect(lambda: self.add_tweaker_group())
            add_row.addWidget(btn_add_group)
            add_row.addStretch()
            main_layout.addLayout(add_row)

            # Same Meshes/Joints rows as the JSON skinCluster panel (reuses
            # get_selection_for_skin/select_skin_meshes/
            # get_selection_for_joints/select_skin_joints as-is - all four
            # are already generic over self.mesh_field/self.joints_field,
            # not skin-panel-specific). Meshes is auto-filled with the
            # Tweaker-created mesh(es) when CREATE succeeds (_execute_
            # tweaker), and Save Skin uses it as the authoritative target
            # list instead of recomputing from the vertex groups every time.
            # Joints is auto-filled with every joint actually influencing
            # those meshes' skinClusters the moment Save Skin succeeds -
            # same "auto-filled ... on Save if left empty" behavior as JSON.
            tw_mesh_layout = QtWidgets.QHBoxLayout()
            tw_mesh_layout.setContentsMargins(25, 0, 0, 0)
            tw_mesh_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText(
                "Auto-filled with the Tweaker mesh(es) when CREATE succeeds...")
            btn_get_sel_tw = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_tw.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel_tw.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes_tw = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes_tw.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes_tw.clicked.connect(self.select_skin_meshes)
            tw_mesh_layout.addWidget(self.mesh_field)
            tw_mesh_layout.addWidget(btn_get_sel_tw)
            tw_mesh_layout.addWidget(btn_select_meshes_tw)
            main_layout.addLayout(tw_mesh_layout)

            tw_joints_layout = QtWidgets.QHBoxLayout()
            tw_joints_layout.setContentsMargins(25, 0, 0, 0)
            tw_joints_layout.addWidget(QtWidgets.QLabel("Joints:"))
            self.joints_field = QtWidgets.QLineEdit()
            self.joints_field.setPlaceholderText(
                "Auto-filled with the influencing joints when Save Skin succeeds...")
            btn_get_sel_j_tw = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_j_tw.setToolTip("Store the currently selected joints into this field.")
            btn_get_sel_j_tw.clicked.connect(self.get_selection_for_joints)
            btn_select_joints_tw = QtWidgets.QPushButton("🎯 Select")
            btn_select_joints_tw.setToolTip("Select the joints listed in this field in the viewport.")
            btn_select_joints_tw.clicked.connect(self.select_skin_joints)
            tw_joints_layout.addWidget(self.joints_field)
            tw_joints_layout.addWidget(btn_get_sel_j_tw)
            tw_joints_layout.addWidget(btn_select_joints_tw)
            main_layout.addLayout(tw_joints_layout)

            self.add_tweaker_group()

        if p_type == "SHAPES":
            shape_ext_layout = QtWidgets.QHBoxLayout()
            shape_ext_layout.setContentsMargins(25, 0, 0, 0)
            shape_ext_layout.addWidget(QtWidgets.QLabel("Pattern:"))
            self.pattern_field = QtWidgets.QLineEdit("*ctl")
            shape_ext_layout.addWidget(self.pattern_field)
            main_layout.addLayout(shape_ext_layout)

        if p_type == "MATERIAL":
            # Same "Meshes" row as JSON's skinCluster panel (reuses
            # get_selection_for_skin/select_skin_meshes as-is - both are
            # already generic over self.mesh_field, not skin-specific).
            mat_mesh_layout = QtWidgets.QHBoxLayout()
            mat_mesh_layout.setContentsMargins(25, 0, 0, 0)
            mat_mesh_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText("Leave empty for selection...")
            btn_get_sel_mat = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_mat.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel_mat.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes_mat = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes_mat.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes_mat.clicked.connect(self.select_skin_meshes)
            mat_mesh_layout.addWidget(self.mesh_field)
            mat_mesh_layout.addWidget(btn_get_sel_mat)
            mat_mesh_layout.addWidget(btn_select_meshes_mat)
            main_layout.addLayout(mat_mesh_layout)

        if p_type == "IMPORT_LOD":
            # Same file field/Browse/Import as IMPORT_3D (reuses self.field,
            # browse_file(), workspace.import_3d_logic - see execute()
            # below), plus the one extra input organize_lod_logic() needs:
            # the asset's name, used to build <AssetName>/<AssetName>_geo/
            # <AssetName>_lod_<N> groups. *_ai_lod-named objects are always
            # deleted (delete_ai_lod=True, matching the original script's
            # own default) rather than offering a checkbox for it.
            lod_asset_layout = QtWidgets.QHBoxLayout()
            lod_asset_layout.setContentsMargins(25, 0, 0, 0)
            lod_asset_layout.addWidget(QtWidgets.QLabel("Asset Name:"))
            self.asset_name_field = QtWidgets.QLineEdit()
            self.asset_name_field.setPlaceholderText("e.g. char_gurudattatreya_a")
            self.asset_name_field.setToolTip(
                "Used to build <AssetName>/<AssetName>_geo/<AssetName>_lod_<N> "
                "groups after import - organizes whatever meshes are "
                "currently in the scene, not just this import.")
            lod_asset_layout.addWidget(self.asset_name_field)
            main_layout.addLayout(lod_asset_layout)

        if p_type in ("DELETE_OBJ", "ZERO_OUT"):
            # One name field, reused for both types - Delete removes
            # whatever's listed, Zero Out builds an offset group above
            # each one and resets its own transform - see execute() below.
            # self.field (the generic path/code field built above) means
            # nothing for either type, so it's hidden.
            self.field.setVisible(False)
            target_layout = QtWidgets.QHBoxLayout()
            target_layout.setContentsMargins(25, 0, 0, 0)
            label_txt = "Object(s) to Delete:" if p_type == "DELETE_OBJ" else "Object(s)/Control(s) to Zero:"
            target_layout.addWidget(QtWidgets.QLabel(label_txt))
            self.target_field = QtWidgets.QLineEdit()
            self.target_field.setPlaceholderText("Comma-separated object/control names...")
            if p_type == "ZERO_OUT":
                self.target_field.setToolTip(
                    "For each object: creates an offset group ('<name>_offset') "
                    "that holds its current position/rotation/scale, parents "
                    "the object under it, then resets the object's own "
                    "translate/rotate/scale to 0/0/0, 0/0/0, 1/1/1 - the "
                    "object doesn't move, but its channels read clean "
                    "defaults again, same as a freshly-built control.")
            btn_get_sel_tgt = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_tgt.setToolTip("Store the currently selected object(s) into this field.")
            btn_get_sel_tgt.clicked.connect(lambda: self._get_selection_into(self.target_field))
            btn_select_tgt = QtWidgets.QPushButton("🎯 Select")
            btn_select_tgt.setToolTip("Select the object(s) listed in this field in the viewport.")
            btn_select_tgt.clicked.connect(lambda: self._select_field_objects(self.target_field))
            target_layout.addWidget(self.target_field)
            target_layout.addWidget(btn_get_sel_tgt)
            target_layout.addWidget(btn_select_tgt)
            main_layout.addLayout(target_layout)

        if p_type == "PARENT_OBJ":
            # Two name fields - self.field (the generic path/code field
            # built above) means nothing here either, so it's hidden too.
            self.field.setVisible(False)
            child_layout = QtWidgets.QHBoxLayout()
            child_layout.setContentsMargins(25, 0, 0, 0)
            child_layout.addWidget(QtWidgets.QLabel("Child(ren):"))
            self.child_field = QtWidgets.QLineEdit()
            self.child_field.setPlaceholderText("Comma-separated object name(s) to parent...")
            btn_get_sel_child = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_child.setToolTip("Store the currently selected object(s) into this field.")
            btn_get_sel_child.clicked.connect(lambda: self._get_selection_into(self.child_field))
            btn_select_child = QtWidgets.QPushButton("🎯 Select")
            btn_select_child.setToolTip("Select the object(s) listed in this field in the viewport.")
            btn_select_child.clicked.connect(lambda: self._select_field_objects(self.child_field))
            child_layout.addWidget(self.child_field)
            child_layout.addWidget(btn_get_sel_child)
            child_layout.addWidget(btn_select_child)
            main_layout.addLayout(child_layout)

            parent_layout = QtWidgets.QHBoxLayout()
            parent_layout.setContentsMargins(25, 0, 0, 0)
            parent_layout.addWidget(QtWidgets.QLabel("Parent:"))
            self.parent_field = QtWidgets.QLineEdit()
            self.parent_field.setPlaceholderText("Object to parent the child(ren) under...")
            btn_get_sel_parent = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_parent.setToolTip("Store the currently selected object into this field.")
            btn_get_sel_parent.clicked.connect(lambda: self._get_selection_into(self.parent_field))
            btn_select_parent = QtWidgets.QPushButton("🎯 Select")
            btn_select_parent.setToolTip("Select the object listed in this field in the viewport.")
            btn_select_parent.clicked.connect(lambda: self._select_field_objects(self.parent_field))
            parent_layout.addWidget(self.parent_field)
            parent_layout.addWidget(btn_get_sel_parent)
            parent_layout.addWidget(btn_select_parent)
            main_layout.addLayout(parent_layout)

        if p_type == "INSTANCE_OBJ":
            # Instances the object below at a set of preset transform
            # offsets (see workspace.create_instances_logic -
            # INSTANCE_DEFAULT_TRANSFORMS - ported from the user's own
            # create_and_transform_instances_by_name script). self.field/
            # func_field above (shown - NOT hidden, unlike DELETE_OBJ/
            # ZERO_OUT/PARENT_OBJ) double as an OPTIONAL custom script
            # override, same convention as a SCRIPT panel.
            self.field.setPlaceholderText(
                "Optional: custom script/path that sets a 'transforms' list "
                "- leave empty for the built-in 3-instance preset...")
            self.field.setToolTip(
                "Optional custom Python script (a .py path, or raw pasted "
                "code) that leaves a 'transforms' variable behind - a list "
                "of {'tx','ty','tz','rx','ry','rz'} dicts, one per instance "
                "to create - used instead of the built-in 3-instance preset "
                "when given. Leave empty to just use the preset.")

            inst_target_layout = QtWidgets.QHBoxLayout()
            inst_target_layout.setContentsMargins(25, 0, 0, 0)
            inst_target_layout.addWidget(QtWidgets.QLabel("Object to Instance:"))
            self.target_field = QtWidgets.QLineEdit()
            self.target_field.setPlaceholderText("Object name to instance (e.g. parshuram_a_geo)...")
            btn_get_sel_inst = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_inst.setToolTip("Store the currently selected object into this field.")
            btn_get_sel_inst.clicked.connect(lambda: self._get_selection_into(self.target_field))
            btn_select_inst = QtWidgets.QPushButton("🎯 Select")
            btn_select_inst.setToolTip("Select the object listed in this field in the viewport.")
            btn_select_inst.clicked.connect(lambda: self._select_field_objects(self.target_field))
            inst_target_layout.addWidget(self.target_field)
            inst_target_layout.addWidget(btn_get_sel_inst)
            inst_target_layout.addWidget(btn_select_inst)
            main_layout.addLayout(inst_target_layout)

            inst_del_layout = QtWidgets.QHBoxLayout()
            inst_del_layout.setContentsMargins(25, 0, 0, 0)
            self.btn_delete_instances = QtWidgets.QPushButton("🗑 Delete All Instances")
            self.btn_delete_instances.setToolTip(
                "Deletes every instance THIS panel has created, however many "
                "times it's been run - each instance is tagged with a "
                "hidden attribute when created, so this finds them all even "
                "after a save/reload, not just the most recent Run.")
            self.btn_delete_instances.setStyleSheet("background-color: #452a29; color: white;")
            self.btn_delete_instances.clicked.connect(self.delete_created_instances)
            inst_del_layout.addWidget(self.btn_delete_instances)
            inst_del_layout.addStretch()
            main_layout.addLayout(inst_del_layout)

        if p_type == "NOTE":
            # Purely informational - not a build step at all (execute()
            # below no-ops for NOTE). The common file/run/cache widgets
            # built above stay alive (never removed) so every other method
            # on this class, and every generic per-panel save/load/copy/
            # paste call elsewhere (workspace.py's get_current_pipeline_data/
            # load_pipeline_from_file, copy_panel/paste_panel below), still
            # finds real objects to work with instead of needing its own
            # NOTE special-case for them - they're just hidden here, since
            # none of them mean anything for a note.
            self.field.setVisible(False)
            self.btn_run.setVisible(False)
            self.btn_reset_err.setVisible(False)
            self.btn_cache_rem.setVisible(False)
            self.btn_cache_save.setVisible(False)
            self.btn_cache_run.setVisible(False)
            self.chk_cache.setVisible(False)

            # Defaults ("in default also you can decide") - text/background
            # color and text size are all still fully user-adjustable per
            # note, just from the "..." (More Options) menu now rather
            # than a dedicated toolbar row - see show_context_menu below.
            self.note_text_color = "#ffffff"
            self.note_bg_color = "#1a1a2e"
            self.note_font_size = 20
            self.note_height = 90

            self.note_edit = QtWidgets.QPlainTextEdit()
            self.note_edit.setPlaceholderText(
                "Write a note here for anyone reading this Rig Build Workspace - "
                "what's happening, what's left, anything worth flagging...")
            self.note_edit.setFixedHeight(self.note_height)
            self.note_edit.setToolTip(
                "Free-text note - purely informational, never part of the build.")
            main_layout.addWidget(self.note_edit)

            # Drag to resize this note's height - vertical only, never the
            # panel's width (that's always fixed to the workspace column).
            self.note_resize_handle = _NoteVerticalResizeHandle(self.note_edit, on_resize=self._set_note_height)
            main_layout.addWidget(self.note_resize_handle)

            self._apply_note_style()

        btn_dots.clicked.connect(self.show_context_menu)
        self.btn_run.clicked.connect(self.on_btn_run_clicked)
        self.btn_del.clicked.connect(lambda: self.workspace.delete_panel(self))

        # Stage 49: collapse toggle - must run last, once every row
        # this panel type adds has been put into main_layout.
        self._init_collapse(main_layout, header_layout)

    def update_style(self):
        accent = getattr(self, 'accent', '#2bb5a8')
        self.setStyleSheet(
            f"SortablePanel {{ background: {self.bg_color}; border: 1px solid #333;"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" SortablePanel:hover {{ border: 1px solid #555; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

    def _apply_note_style(self):
        """NOTE panels only: (re)style the note's own text box from
        self.note_text_color/note_bg_color/note_font_size - separate from
        update_style() above, which only ever touches the panel's outer
        QFrame chrome (background/border), not anything inside it."""
        if not hasattr(self, "note_edit"):
            return
        self.note_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: {self.note_bg_color}; color: {self.note_text_color};"
            f" border: 1px solid #333; border-radius: 3px; padding: 6px;"
            f" font-size: {self.note_font_size}px; }}")

    def change_note_text_color(self):
        current_color = QtGui.QColor(self.note_text_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Note Text Color")
        if color.isValid():
            self.note_text_color = color.name()
            self._apply_note_style()

    def change_note_bg_color(self):
        current_color = QtGui.QColor(self.note_bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Note Background Color")
        if color.isValid():
            self.note_bg_color = color.name()
            self._apply_note_style()

    def change_note_font_size(self, value):
        self.note_font_size = value
        self._apply_note_style()

    def _set_note_height(self, height):
        self.note_height = height

    def populate_versions_menu(self, switch_menu):
        v_actions = {}
        base_path = self.path().strip()
        if not base_path:
            switch_menu.setEnabled(False)
            return v_actions
            
        dir_name = os.path.dirname(base_path)
        if not os.path.exists(dir_name):
            switch_menu.setEnabled(False)
            return v_actions
            
        base_name, ext = os.path.splitext(os.path.basename(base_path))
        base_name_no_v = re.sub(r'_v\d+$', '', base_name)
        pattern = re.compile(r"^" + re.escape(base_name_no_v) + r"(?:_v(\d+))?" + re.escape(ext) + r"$")
        
        versions = []
        for f in os.listdir(dir_name):
            match = pattern.match(f)
            if match:
                versions.append(os.path.join(dir_name, f).replace('\\', '/'))
                
        versions.sort()
        if not versions:
            switch_menu.setEnabled(False)
        else:
            for v in versions:
                v_name = os.path.basename(v)
                v_actions[switch_menu.addAction(v_name)] = v
                
        return v_actions

    def save_versioned_data(self, overwrite=False):
        current_path = self.path().strip()
        if not current_path:
            # First save on this panel (Stage 16, request #3): ask where,
            # instead of just erroring - and make sure whatever's picked
            # ends up with the right extension for this panel's data.
            current_path = self.prompt_first_save_path()
            if not current_path:
                return  # user cancelled the Save As dialog
            self.field.setText(self.workspace.relativize_path(current_path))

        if self.p_type in ("JSON", "TWEAKER"):
            # mgear.core.skin.exportSkin() hard-rejects any extension other
            # than .gSkin/.jSkin (it will warn "Not valid file extension for:
            # ..." and silently not write the file). Panels saved/typed with
            # a plain .json - which the Save dialog's own filter offers as a
            # choice - would otherwise pass that check and fail on export, and
            # keep failing on every subsequent versioned save. Normalize here,
            # before computing the versioned path, so the corrected extension
            # is what get_versioned_path() and the field both use from now on.
            root, ext = os.path.splitext(current_path)
            if ext.lower() not in (".jskin", ".gskin"):
                current_path = root + ".jSkin"
                self.field.setText(self.workspace.relativize_path(current_path))

        save_path = current_path
        if not overwrite:
            save_path = get_versioned_path(current_path, get_latest=False)

        if self.p_type == "JSON":
            try:
                from ..utils import find_mesh_skincluster, fast_export_skin
                meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                sel = meshes if meshes else cmds.ls(sl=True)
                if not sel:
                    om.MGlobal.displayError("Select a skinned mesh (or fill the Meshes field) before saving skin.")
                    return
                # Use cmds.select (not pm.select): pymel's select can trigger a
                # spurious "Cannot find Maya documentation" error on installs
                # without the docs package.
                missing = [m for m in sel if not cmds.objExists(m)]
                if missing:
                    om.MGlobal.displayError("These objects don't exist in the scene: {}".format(", ".join(missing)))
                    return
                cmds.select(sel, replace=True)

                # Stage 16, request #1: the naming-convention check used to
                # run once at KRT launch, scanning the whole scene. It's
                # scoped here to just the mesh(es) this export is actually
                # about to touch instead.
                prompt_skincluster_naming_check(
                    self.workspace.main_window, sel,
                    show_popup=self.naming_popup_enabled())

                # If Joints was left empty, capture the influences that are
                # actually bound right now, so this panel remembers the
                # intended influence set for future Bind All / re-import.
                if hasattr(self, 'joints_field') and not self.joints_field.text().strip():
                    captured = []
                    seen = set()
                    for m in sel:
                        skc = find_mesh_skincluster(m)
                        if not skc:
                            continue
                        for j in (cmds.skinCluster(skc, query=True, influence=True) or []):
                            if j not in seen:
                                seen.add(j); captured.append(j)
                    if captured:
                        self.joints_field.setText(",".join(captured))

                try:
                    # fast_export_skin() (utils.py) - same .jSkin file mgear's
                    # own exportSkin() would write, just fast on heavy meshes
                    # (see the "Fast SkinCluster save/import" section there);
                    # falls back to mgear's exporter itself on any error.
                    fast_export_skin(save_path)
                except Exception as ex:
                    # The "Cannot find Maya documentation" message is non-fatal;
                    # if the skin file was actually written, accept the export.
                    if "documentation" not in str(ex).lower() or not os.path.isfile(save_path):
                        raise
                    cmds.warning("[KRT] Ignored a non-fatal Maya docs warning during skin export.")
                if not os.path.isfile(save_path):
                    raise RuntimeError(
                        "Skin file was not written. Make sure the selected mesh(es) actually have a skinCluster.")
                self.field.setText(self.workspace.relativize_path(save_path))
                cmds.warning(f"Skin exported successfully to: {save_path}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export skin: {e}")

        elif self.p_type == "SHAPES":
            pattern = self.pattern_field.text()
            try:
                # Use the path the exporter reports it wrote, not the one we
                # asked for - they are the same now, but the field must never
                # drift from the file on disk again.
                written = export_control_shapes(save_path, search_pattern=pattern)
                if not written:
                    om.MGlobal.displayError(
                        f"Failed to export shapes - nothing matched the pattern '{pattern}'.")
                    return
                self.field.setText(self.workspace.relativize_path(written))
                cmds.warning(f"Shapes exported successfully to: {written}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export shapes: {e}")

        elif self.p_type == "MATERIAL":
            meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
            try:
                result = export_material_data(save_path, meshes=meshes if meshes else None)
                if result:
                    written = result if isinstance(result, str) else save_path
                    self.field.setText(self.workspace.relativize_path(written))
                    cmds.warning(f"Material exported successfully to: {written}")
                else:
                    om.MGlobal.displayError("Failed to export material - nothing to save (select mesh(es) or fill the Meshes field first).")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export material: {e}")

        elif self.p_type == "TWEAKER":
            try:
                from ..utils import find_mesh_skincluster, fast_export_skin
                # The panel-level Meshes field is the authoritative target
                # list once it's filled (auto-filled by _execute_tweaker on
                # a successful Create, or set by hand / Get Selected). Only
                # fall back to re-deriving it from the vertex groups when
                # it's empty, e.g. an older session/panel that never ran
                # Create through this version of the panel yet.
                meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                if meshes:
                    targets = meshes
                else:
                    # Stage 21: aggregate vertex names/additional meshes across
                    # EVERY vertex group on this panel, so Save Skin covers
                    # every group's tweaker meshes in one export, not just the
                    # first group.
                    vertex_names = []
                    additional_meshes = []
                    for group in self.tweaker_groups:
                        vertex_names.extend(v.strip() for v in group.vertex_field.text().split(",") if v.strip())
                        additional_meshes.extend(m.strip() for m in group.mesh_field.text().split(",") if m.strip())
                    targets = self.workspace.get_tweaker_target_meshes(vertex_names, additional_meshes)
                if not targets:
                    om.MGlobal.displayError(
                        "No Tweaker mesh(es) found for the current Vertices/Additional Meshes "
                        "- run Create first.")
                    return
                missing = [t for t in targets if not cmds.objExists(t)]
                if missing:
                    om.MGlobal.displayError("These Tweaker meshes don't exist: {}".format(", ".join(missing)))
                    return
                cmds.select(targets, replace=True)
                prompt_skincluster_naming_check(
                    self.workspace.main_window, targets,
                    show_popup=self.naming_popup_enabled())
                try:
                    fast_export_skin(save_path)
                except Exception as ex:
                    if "documentation" not in str(ex).lower() or not os.path.isfile(save_path):
                        raise
                    cmds.warning("[KRT] Ignored a non-fatal Maya docs warning during skin export.")
                if not os.path.isfile(save_path):
                    raise RuntimeError("Skin file was not written.")
                self.field.setText(self.workspace.relativize_path(save_path))
                if not meshes:
                    # Keep the Meshes field in sync with whatever was
                    # actually exported, same as the auto-fill on Create.
                    self.mesh_field.setText(",".join(targets))
                # Joints is auto-filled with every joint actually influencing
                # the exported meshes' skinClusters, same "auto-filled ... on
                # Save if left empty" behavior as the JSON panel.
                if not self.joints_field.text().strip():
                    captured = []
                    seen = set()
                    for m in targets:
                        skc = find_mesh_skincluster(m)
                        if not skc:
                            continue
                        for j in (cmds.skinCluster(skc, query=True, influence=True) or []):
                            if j not in seen:
                                seen.add(j); captured.append(j)
                    if captured:
                        self.joints_field.setText(",".join(captured))
                cmds.warning(f"Tweaker skin exported successfully to: {save_path}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export Tweaker skin: {e}")

    def prompt_first_save_path(self):
        """Stage 16, request #3: the first time a skinCluster/Tweaker/
        Control-Shapes panel is saved and it has no path yet, ask where to
        save instead of just erroring - and make sure the chosen path ends
        up with the right extension for what's being saved, appending one
        if the user typed a bare name without it. Returns the chosen path,
        or "" if the dialog was cancelled."""
        if self.p_type in ("JSON", "TWEAKER"):
            default_ext = ".jSkin"
            ff = "Skin (*.jSkin *.gSkin *.json);;All Files (*.*)"
            caption = "Save Skin As"
            default_name = "skinCluster" + default_ext
        elif self.p_type == "SHAPES":
            default_ext = ".json"
            ff = "Control Shapes (*.json);;All Files (*.*)"
            caption = "Save Control Shapes As"
            default_name = "controlShapes" + default_ext
        elif self.p_type == "MATERIAL":
            default_ext = ".json"
            ff = "Material (*.json);;All Files (*.*)"
            caption = "Save Material As"
            default_name = "material" + default_ext
        else:
            return ""

        start_dir = self.get_start_dir()
        if not start_dir:
            # Nothing typed in the field yet to derive a folder from -
            # default next to wherever this session's own KRT json lives,
            # same convenience the auto-managed Guide Path already gets.
            session_path = getattr(self.workspace, "session_path", "") or ""
            if session_path:
                start_dir = os.path.dirname(session_path)
        if not start_dir or not os.path.exists(start_dir):
            start_dir = os.path.expanduser("~")

        res = cmds.fileDialog2(
            fileFilter=ff, dialogStyle=2, fileMode=0, caption=caption,
            startingDirectory=os.path.join(start_dir, default_name).replace("\\", "/"))
        if not res:
            return ""
        path = res[0]
        if not os.path.splitext(path)[1]:
            path += default_ext
        elif self.p_type in ("JSON", "TWEAKER") and os.path.splitext(path)[1].lower() not in (".jskin", ".gskin"):
            # The Save dialog's own filter offers ".json" as a pickable
            # option for skin panels, but mgear.core.skin.exportSkin() only
            # accepts .gSkin/.jSkin - swap it here too so a fresh pick never
            # needs the save_versioned_data() fallback to catch it.
            path = os.path.splitext(path)[0] + default_ext
        return path

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
        elif p_type == "LOD_LOADER":
            self.workspace.add_lod_loader_panel(title, index=idx)
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active, "bg_color": self.bg_color}
        # The clipboard is shared by every session tab, and each tab has its
        # own Rig Root - so a relative path copied out of rig A would silently
        # point at rig B's folder when pasted there. Store ABSOLUTE; paste
        # shortens it again only if it happens to sit under the target's root.
        if self.p_type == "MODULE":
            mods = [{"path": self.workspace.resolve_path(self.bubble_layout.itemAt(b).widget().full_path), "active": self.bubble_layout.itemAt(b).widget().is_active} for b in range(self.bubble_layout.count())]
            data["modules"] = mods
        else:
            data["path"] = self.path()
            if self.p_type == "SHAPES": data["pattern"] = self.pattern_field.text()
            if self.p_type == "JSON":
                data["meshes"] = self.mesh_field.text()
                data["joints"] = self.joints_field.text()
                data["reskin_control"] = self.reskin_ctl_field.text()
                data["reskin_scale"] = self.reskin_scale_field.text()
                data["naming_popup"] = self.naming_popup_enabled()
            if self.p_type == "MATERIAL":
                data["meshes"] = self.mesh_field.text()
            if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"): data["func_call"] = self.func_field.text()
            if hasattr(self, 'chk_share_global'): data["share_global"] = self.chk_share_global.isChecked()
            if self.p_type == "TWEAKER":
                data["groups"] = self.get_tweaker_groups_data()
                data["meshes"] = self.mesh_field.text()
                data["joints"] = self.joints_field.text()
                data["naming_popup"] = self.naming_popup_enabled()
            if self.p_type == "NOTE":
                data["note_text"] = self.note_edit.toPlainText()
                data["note_text_color"] = self.note_text_color
                data["note_bg_color"] = self.note_bg_color
                data["note_font_size"] = self.note_font_size
                data["note_height"] = self.note_height
            if self.p_type == "IMPORT_LOD":
                data["asset_name"] = self.asset_name_field.text()
            if self.p_type in ("DELETE_OBJ", "ZERO_OUT"):
                data["target"] = self.target_field.text()
            if self.p_type == "PARENT_OBJ":
                data["child"] = self.child_field.text()
                data["parent"] = self.parent_field.text()
        data["collapsed"] = self.is_collapsed()
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

    def cut_panel(self):
        """Stage 22, request #1: Copy Panel, then delete this panel -
        delete_panel() itself pushes the removed panel onto the workspace's
        undo stack, so a Cut can still be undone same as a plain Delete."""
        self.copy_panel()
        self.workspace.delete_panel(self)

    def paste_panel(self, offset):
        data = getattr(self.workspace.main_window, 'clipboard_panel_data', None)
        if not data: return
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset

        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.workspace.add_module_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            for m in data.get("modules", []):
                # relativize against THIS tab's root: same rig -> short path
                # again; different rig -> stays absolute and still resolves.
                pan.add_module_bubble(pre_path=self.workspace.relativize_path(m.get("path")),
                                      is_active=m.get("active", True))
            if not is_act: pan.checkbox.setChecked(False)
        else:
            pan = self.workspace.add_panel(
                title, p_type, self.workspace.relativize_path(data.get("path", "")), index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            if not is_act: pan.checkbox.setChecked(False)
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
            if "share_global" in data and hasattr(pan, 'chk_share_global'):
                pan.chk_share_global.setChecked(bool(data.get("share_global")))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                if data.get("asset_name"): pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT") and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))
            if p_type == "INSTANCE_OBJ" and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
                if data.get("func_call") and hasattr(pan, 'func_field'): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")
        # A collapsed panel pastes collapsed - the flag travels with the
        # panel like every other bit of its state.
        if data.get("collapsed") and hasattr(pan, "set_collapsed"):
            pan.set_collapsed(True)

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            # Manual click: run regardless of the active checkbox.
            self.execute(None, force=True)

    def _normal_run_text(self):
        return panel_run_label(self.p_type)

    def reset_run_button(self):
        """Restore the run button to its normal state after an error, without
        re-executing the panel. Triggered by the small ↺ button."""
        self.btn_run.setText(self._normal_run_text())
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #2bb5a8; font-weight: bold; color: white; font-size: 13px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(SortablePanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {getattr(self, 'accent', '#2bb5a8')}; font-size: 13px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(SortablePanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton): 
            return super(SortablePanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(SortablePanel, self).mouseMoveEvent(event)
            
        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance(): 
            return super(SortablePanel, self).mouseMoveEvent(event)

        self.workspace.dragged_panel = self
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText("panel_drag")
        drag.setMimeData(mime_data)
        
        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        if IS_PYSIDE6: drag.exec(QtCore.Qt.MoveAction)
        else: drag.exec_(QtCore.Qt.MoveAction)
            
        self.workspace.dragged_panel = None
        super(SortablePanel, self).mouseMoveEvent(event)

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)
        # The RUN button stays clickable while the panel is off - see
        # execute(force=True). Only the tooltip changes, so it is obvious
        # that clicking runs a step the full build will skip.
        if hasattr(self, 'btn_run'):
            self.btn_run.setToolTip(
                "" if state else
                "This panel is OFF - the full build skips it.\nClicking RUN still executes it, once, by hand.")

    def _get_selection_into(self, field):
        """Generic 'Get Selected' for the Delete/Zero Out/Parent panels'
        name field(s) - same idea as get_selection_for_skin()/
        get_selection_for_joints() below, just not hardcoded to one
        specific field, since these panel types have more than one."""
        sel = cmds.ls(sl=True)
        if sel: field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def _select_field_objects(self, field):
        """Generic '🎯 Select' for the Delete/Zero Out/Parent panels' name
        field(s) - same idea as select_skin_meshes()/select_skin_joints()
        below, just not hardcoded to one specific field."""
        names = [n.strip() for n in field.text().split(",") if n.strip()]
        if not names:
            cmds.warning("Nothing listed - use 'Get Selected' first, or type object names.")
            return
        existing = [n for n in names if cmds.objExists(n)]
        missing = [n for n in names if not cmds.objExists(n)]
        if not existing:
            cmds.warning("None of these objects exist in the scene: {}".format(", ".join(names)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} object(s); not found, skipped: {}".format(len(existing), ", ".join(missing)))

    def delete_created_instances(self):
        """Instance Object panel's Delete All Instances button - removes
        every instance this specific panel has created (tracked by the
        krtInstancePanel tag - see workspace.delete_instances_by_panel_logic),
        not just the ones from the last Run."""
        success, error_msg = self.workspace.delete_instances_by_panel_logic(self.uuid)
        if not success:
            cmds.warning("[KRT] {}".format(error_msg))

    def get_selection_for_skin(self):
        sel = cmds.ls(sl=True)
        if sel: self.mesh_field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def select_skin_meshes(self):
        """Select the meshes listed in the Meshes field in the viewport."""
        meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
        if not meshes:
            cmds.warning("No meshes listed - use 'Get Selected' first, or type mesh names.")
            return
        existing = [m for m in meshes if cmds.objExists(m)]
        missing = [m for m in meshes if not cmds.objExists(m)]
        if not existing:
            cmds.warning("None of the listed meshes exist in the scene: {}".format(", ".join(meshes)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} mesh(es). Not found: {}".format(len(existing), ", ".join(missing)))
        else:
            cmds.warning("Selected {} mesh(es).".format(len(existing)))

    def get_selection_for_reskin_control(self):
        """Stores every currently selected object into the Scale Control(s)
        field, comma-separated - Stage 33 supports scaling more than one
        control during the re-bind."""
        sel = cmds.ls(sl=True) or []
        if not sel:
            cmds.warning("Nothing selected.")
            return
        cmds.warning("Using {} selected object(s) as the Re-Skin scale control(s).".format(len(sel)))
        self.reskin_ctl_field.setText(", ".join(sel))

    def reskin_settings(self):
        """(controls, scale) as entered on this panel - `controls` is a list
        (possibly empty; an empty list means "no re-skin should run at all",
        checked by the caller). A scale that isn't a number falls back to
        1.0 (no scaling) rather than failing the run."""
        raw = self.reskin_ctl_field.text() if hasattr(self, 'reskin_ctl_field') else ""
        controls = [c.strip() for c in raw.split(",") if c.strip()]
        try:
            scale = float(self.reskin_scale_field.text().strip())
        except (ValueError, AttributeError):
            if hasattr(self, 'reskin_scale_field') and self.reskin_scale_field.text().strip():
                cmds.warning("Re-Skin Scale '{}' isn't a number - using 1.0 (no scaling).".format(
                    self.reskin_scale_field.text().strip()))
            scale = 1.0
        return controls, scale

    def get_selection_for_joints(self):
        sel = cmds.ls(sl=True, type="joint") or cmds.ls(sl=True)
        if sel: self.joints_field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def select_skin_joints(self):
        """Select the joints listed in the Joints field in the viewport."""
        joints = [j.strip() for j in self.joints_field.text().split(",") if j.strip()]
        if not joints:
            cmds.warning("No joints listed - use 'Get Selected' first, or type joint names.")
            return
        existing = [j for j in joints if cmds.objExists(j)]
        missing = [j for j in joints if not cmds.objExists(j)]
        if not existing:
            cmds.warning("None of the listed joints exist in the scene: {}".format(", ".join(joints)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} joint(s). Not found: {}".format(len(existing), ", ".join(missing)))
        else:
            cmds.warning("Selected {} joint(s).".format(len(existing)))

    def bind_all_meshes(self):
        """Default-bind every mesh in the Meshes field (or the current
        selection) to every joint in the Joints field. A mesh that already
        has a skinCluster is left alone - this only ever creates new binds,
        it never overwrites an existing one."""
        meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
        if not meshes:
            meshes = cmds.ls(sl=True, type="transform") or []
        joints = [j.strip() for j in self.joints_field.text().split(",") if j.strip()]

        if not meshes:
            om.MGlobal.displayError("List meshes in the Meshes field (or select some) before Bind All.")
            return
        if not joints:
            om.MGlobal.displayError("List joints in the Joints field (or use 'Get Selected') before Bind All.")
            return

        from ..utils import find_mesh_skincluster, canonical_skincluster_name
        bound, skipped, failed = [], [], []
        for mesh in meshes:
            if not cmds.objExists(mesh):
                failed.append(mesh)
                continue
            if find_mesh_skincluster(mesh):
                skipped.append(mesh)
                continue
            existing_joints = [j for j in joints if cmds.objExists(j)]
            if not existing_joints:
                failed.append(mesh)
                continue
            try:
                cmds.skinCluster(
                    existing_joints, mesh, toSelectedBones=True,
                    name=canonical_skincluster_name(mesh),
                    bindMethod=0, skinMethod=0, normalizeWeights=1,
                    maximumInfluences=max(1, min(8, len(existing_joints))),
                    obeyMaxInfluences=False)
                bound.append(mesh)
            except Exception:
                traceback.print_exc()
                failed.append(mesh)

        msg = "Bind All: {} bound".format(len(bound))
        if skipped: msg += ", {} skipped (already skinned)".format(len(skipped))
        if failed: msg += ", {} failed".format(len(failed))
        cmds.warning(msg)

    # -- Tweaker vertex groups (Stage 21, request #1) -----------------------
    def add_tweaker_group(self, data=None):
        """Add one more independent TweakerVertexGroup row to this panel -
        the "+ Add Vertex Group" button. `data`, if given, seeds it (used
        when loading/pasting/duplicating a panel)."""
        group = TweakerVertexGroup(self.tweaker_groups_widget)
        group.removed.connect(self.remove_tweaker_group)
        self.tweaker_groups_box.addWidget(group)
        self.tweaker_groups.append(group)
        if data:
            group.from_dict(data)
        return group

    def remove_tweaker_group(self, group):
        if len(self.tweaker_groups) <= 1:
            cmds.warning("A Tweaker panel needs at least one vertex group.")
            return
        if group in self.tweaker_groups:
            self.tweaker_groups.remove(group)
        self.tweaker_groups_box.removeWidget(group)
        group.deleteLater()

    def get_tweaker_groups_data(self):
        return [g.to_dict() for g in self.tweaker_groups]

    def load_tweaker_groups_data(self, groups, legacy_item=None):
        """Restore this panel's vertex groups from saved/copied data.
        `groups` is the Stage 21 list-of-dicts form. `legacy_item`, if
        given, is a pre-Stage-21 flat dict (single vertices/meshes/
        use_bind_scale/influence_radius/full_weight_radius/falloff set) -
        used as a one-group fallback when `groups` isn't present, so an
        older pipeline JSON or clipboard copy still loads correctly."""
        if not groups and legacy_item:
            legacy = {
                "vertices": legacy_item.get("vertices", ""),
                "meshes": legacy_item.get("meshes", ""),
                "use_bind_scale": legacy_item.get("use_bind_scale", True),
                "bind_scale": legacy_item.get("bind_scale", "0.01"),
                "influence_radius": legacy_item.get("influence_radius", "0.08"),
                "full_weight_radius": legacy_item.get("full_weight_radius", "0.0001"),
                "falloff": legacy_item.get("falloff", "2.0"),
            }
            if legacy["vertices"] or legacy["meshes"]:
                groups = [legacy]
        if not groups:
            return
        # First saved group goes onto the default group this panel was
        # created with; any additional ones get their own new row.
        first, rest = groups[0], groups[1:]
        if self.tweaker_groups:
            self.tweaker_groups[0].from_dict(first)
        else:
            self.add_tweaker_group(first)
        for g_data in rest:
            self.add_tweaker_group(g_data)

    def _execute_tweaker(self):
        """Run the Tweaker setup (create_tweaker_setup + add_additional_
        tweaker_meshes, from PanelScripts/Tweaker.py) once per vertex group
        on this panel. Called from execute(). Stops at the first group that
        fails and reports which one."""
        if not self.tweaker_groups:
            return False, "No vertex groups on this panel."

        for i, group in enumerate(self.tweaker_groups):
            vertex_names = [v.strip() for v in group.vertex_field.text().split(",") if v.strip()]
            if not vertex_names and len(self.tweaker_groups) == 1:
                # Single-group panels keep the old "fall back to the current
                # viewport selection" convenience - ambiguous with more than
                # one group, so it's only offered when there's just one.
                sel = cmds.ls(sl=True, flatten=True) or []
                vertex_names = [v for v in sel if ".vtx[" in v]
            if not vertex_names:
                return False, "Vertex Group {}: no vertices provided - fill its Vertices field (or select some in the viewport first, single-group panels only).".format(i + 1)

            additional_meshes = [m.strip() for m in group.mesh_field.text().split(",") if m.strip()]
            try:
                bind_scale = float(group.field_bind_scale.text())
                influence_radius = float(group.field_influence_radius.text())
                full_weight_radius = float(group.field_full_weight_radius.text())
                falloff = float(group.field_falloff.text())
            except ValueError:
                return False, "Vertex Group {}: Bind Scale / Influence Radius / Full Weight Radius / Falloff must be numbers.".format(i + 1)

            ok, err = self.workspace.run_tweaker_logic(
                vertex_names, additional_meshes,
                use_bind_scale=group.chk_use_bind_scale.isChecked(),
                bind_scale=bind_scale,
                influence_radius=influence_radius,
                full_weight_radius=full_weight_radius,
                falloff=falloff)
            if not ok:
                return False, "Vertex Group {}:\n{}".format(i + 1, err)

        # All groups created successfully - auto-fill the panel-level Meshes
        # field with the real Tweaker-created mesh name(s) so Save Skin has
        # an authoritative target list without re-deriving it from the
        # vertex groups every time.
        try:
            all_vertex_names = []
            all_additional_meshes = []
            for group in self.tweaker_groups:
                all_vertex_names.extend(
                    v.strip() for v in group.vertex_field.text().split(",") if v.strip())
                all_additional_meshes.extend(
                    m.strip() for m in group.mesh_field.text().split(",") if m.strip())
            targets = self.workspace.get_tweaker_target_meshes(all_vertex_names, all_additional_meshes)
            if targets:
                self.mesh_field.setText(",".join(targets))
        except Exception:
            # Non-fatal - the panel still works with Meshes left blank;
            # Save Skin falls back to recomputing the targets itself.
            pass

        # A freshly (re)created Tweaker mesh has no weights of its own yet -
        # if this panel's path field already points at a previously saved
        # skin (Save Skin writes it there), load it back onto the new
        # mesh(es) right away instead of leaving them unskinned until the
        # user remembers to hit Load separately. Same lookup the JSON
        # panel's Load action already uses; a missing/blank path or a
        # load failure is silently non-fatal - Create itself still
        # succeeded either way.
        try:
            skin_path = self.path().strip()
            if skin_path and os.path.exists(skin_path) and self.mesh_field.text().strip():
                load_ok, load_err = self.workspace.load_skin_cluster_logic(
                    skin_path, self.mesh_field.text(),
                    show_popup=self.naming_popup_enabled())
                if load_ok:
                    cmds.warning(f"[KRT] Tweaker created and previously saved skin re-applied from: {skin_path}")
                else:
                    cmds.warning(f"[KRT] Tweaker created, but auto-loading the saved skin failed: {load_err}")
        except Exception:
            pass

        return True, ""

    def naming_popup_enabled(self):
        """Whether this panel's own 'Popup' tick (JSON/Tweaker only) wants
        the SkinCluster-naming confirmation shown. True for any panel type
        that doesn't have the tick at all, so callers can use this
        unconditionally without an extra hasattr check."""
        chk = getattr(self, 'chk_naming_popup', None)
        return chk.isChecked() if chk is not None else True

    def path(self):
        """Stage 41: the field's text resolved against the Rig Root - use
        THIS whenever the text is about to be opened/run/checked on disk.
        Inline code and empty text come back unchanged. self.field.text()
        stays the raw (possibly relative) value for display and saving.

        NOTE: this method must read self.field.text() directly - calling
        self.path() here would recurse forever (it did, once).
        """
        return self.workspace.resolve_path(self.field.text())

    # Which project folder each panel type reads from / writes to. Used to
    # open a file browser in the right place instead of at the top of the
    # rigs share (see get_start_dir).
    TYPE_SUBDIR = {
        "SCRIPT": "scripts",
        "GLOBAL_SCRIPT": "scripts",
        "IMPORT_3D": "model",
        "IMPORT_LOD": "model",
        "JSON": "skinCluster",
        "TWEAKER": "skinCluster",
        "SHAPES": "controlShape",
        "MATERIAL": "controlShape",
        "PUBLISH": "rig",
        "MODULE": "guides",
    }

    def get_start_dir(self):
        """Where this panel's file browser should open.

        Order: the folder of whatever the field points at (if it exists) ->
        the project subfolder for this panel type inside the Rig Root ->
        the Rig Root itself -> the studio rigs share. The rigs share is a
        last resort only: opening there means scrolling past every rig in
        the studio to reach the one you are working on.
        """
        current_path = self.path().strip()
        if os.path.isdir(current_path):
            return current_path
        if os.path.isfile(current_path):
            return os.path.dirname(current_path)
        # The field may name a file that does not exist YET (a skin/shapes
        # path about to be saved) - its folder is still the right place.
        if current_path:
            parent = os.path.dirname(current_path)
            if parent and os.path.isdir(parent):
                return parent
        root = self.workspace.rig_root()
        if root and os.path.isdir(root):
            sub = self.TYPE_SUBDIR.get(self.p_type)
            if sub:
                candidate = os.path.join(root, sub).replace("\\", "/")
                if os.path.isdir(candidate):
                    return candidate
            return root
        return self.workspace.default_browse_dir()

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        
        a_undo = menu.addAction("↩ Undo Delete/Cut")
        if not getattr(self.workspace, 'panel_undo_stack', None):
            a_undo.setEnabled(False)
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")
        
        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Default Script (Maya Global)")] = ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", offset)
            actions_map[m.addAction("Add Import 3D Model (.ma/.mb/.fbx/.obj/.abc)")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Material Panel")] = ("MATERIAL PANEL", "MATERIAL", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            actions_map[m.addAction("Add Tweaker Panel")] = ("TWEAKER SETUP", "TWEAKER", offset)
            actions_map[m.addAction("Add LOD Loader Panel (build entire LODs)")] = ("LOD LOADER", "LOD_LOADER", offset)
            actions_map[m.addAction("Add Note Panel (free-text, not a build step)")] = ("NOTE", "NOTE", offset)
            actions_map[m.addAction("Add Import 3D Model + LOD Organize")] = ("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", offset)
            actions_map[m.addAction("Add Delete-by-Name Panel")] = ("DELETE", "DELETE_OBJ", offset)
            actions_map[m.addAction("Add Zero Out Panel")] = ("ZERO OUT", "ZERO_OUT", offset)
            actions_map[m.addAction("Add Parent Panel")] = ("PARENT", "PARENT_OBJ", offset)
            actions_map[m.addAction("Add Instance Panel")] = ("INSTANCE", "INSTANCE_OBJ", offset)

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
        a_cut = menu.addAction("✂ Cut Panel")
        paste_above = menu.addAction("📋 Paste Panel (Above)")
        paste_below = menu.addAction("📋 Paste Panel (Below)")

        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)

        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here (run every step)")
        a_build_till_cached = menu.addAction("⚡ Build Till Here (resume from newest cache)")
        a_load_cache = menu.addAction("📂 Load Cached Scene")
        a_build_from = menu.addAction("⏩ Build FROM Here (load cache + continue)")
        if not self.has_cache():
            a_load_cache.setEnabled(False)
            a_build_from.setEnabled(False)
        a_replace_paths = menu.addAction("🔀 Replace All Paths...")
        # Duplicate is available for every panel type, not just SCRIPT.
        a_dup = menu.addAction("📋 Duplicate Panel")
        menu.addSeparator()

        a_vs = a_load = a_comp = a_rem = a_save_over = a_save_new = None
        v_actions = {}

        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"):
            a_vs = menu.addAction("📝 Edit code in VS Code")
            a_load = menu.addAction("📂 Load any other file")
            a_comp = menu.addAction("⚖ Compare older script in VS Code")
            if is_script_file_ref(self.path()):
                # Stage 19: the field is currently locked to a .py/.mel file
                # path - this is the only way back to a normal, editable,
                # type-your-own-code field.
                a_rem = menu.addAction("❌ Clear (type code instead)")
        elif self.p_type in ("IMPORT_3D", "IMPORT_LOD"):
            a_load = menu.addAction("📂 Load 3D file (.ma/.mb/.fbx/.obj/.abc)")
            a_rem = menu.addAction("❌ Remove file")
        elif self.p_type == "JSON":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Skin (Overwrite)")
            a_save_new = menu.addAction("💾 Save Skin (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "TWEAKER":
            a_load = menu.addAction("📂 Set Skin Save Path")
            a_rem = menu.addAction("❌ Remove path")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Skin (Overwrite)")
            a_save_new = menu.addAction("💾 Save Skin (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "SHAPES":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Shapes (Overwrite)")
            a_save_new = menu.addAction("💾 Save Shapes (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "MATERIAL":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Material (Overwrite)")
            a_save_new = menu.addAction("💾 Save Material (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "PUBLISH":
            a_load = menu.addAction("📂 Load new path")
            a_rem = menu.addAction("❌ Remove path")

        a_note_text_color = a_note_bg_color = a_note_size = None
        if self.p_type == "NOTE":
            a_note_text_color = menu.addAction("🎨 Change Note Text Color")
            a_note_bg_color = menu.addAction("🖌 Change Note Background Color")
            a_note_size = menu.addAction("🔠 Change Note Text Size...")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        
        if not action: return
        
        if action == a_undo: self.workspace.undo_last_panel_delete()
        elif action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
        elif action == a_cut: self.cut_panel()
        elif action == paste_above: self.paste_panel(0)
        elif action == paste_below: self.paste_panel(1)
        elif action == a_build_till:
            print("[KRT] menu: Build Till Here (full) ->", self.title_edit.text())
            self.workspace.build_till_panel(self, resume_from_cache=False)
        elif action == a_build_till_cached:
            print("[KRT] menu: Build Till Here (cached) ->", self.title_edit.text())
            self.workspace.build_till_panel(self, resume_from_cache=True)
        elif action == a_load_cache: self.run_from_cache()
        elif action == a_build_from: self.build_from_cache()
        elif action == a_replace_paths: self.workspace.open_path_replace_dialog()
        elif action == a_vs:
            path = self.path()
            if not os.path.exists(path) and not path.endswith(".py") and not path.endswith(".mel"):
                om.MGlobal.displayError("Cannot open raw code in VS Code. Please save as a file first.")
            else:
                # Stage 17: falls back to KRT's own simple editor if VS Code
                # isn't found, instead of just erroring.
                self.workspace.open_script_externally(path)
        elif action == a_load: self.browse_file()
        elif action == a_dup: self.workspace.duplicate_panel(self)
        elif action == a_comp:
            kwargs = {'fm': 1, 'ff': "Python (*.py)", 'caption': "Select Older File to Compare"}
            sd = self.get_start_dir()
            if os.path.exists(sd): kwargs['dir'] = sd
            old_file = cmds.fileDialog2(**kwargs)
            if old_file: subprocess.Popen(f'code -d "{self.path()}" "{old_file[0]}"', shell=True)
        elif action == a_rem: self.field.setText("")
        elif action == a_save_over: self.save_versioned_data(overwrite=True)
        elif action == a_save_new: self.save_versioned_data(overwrite=False)
        elif action in v_actions: self.field.setText(self.workspace.relativize_path(v_actions[action]))
        elif action == a_note_text_color: self.change_note_text_color()
        elif action == a_note_bg_color: self.change_note_bg_color()
        elif action == a_note_size:
            new_size, ok = QtWidgets.QInputDialog.getInt(
                self, "Note Text Size", "Size:", self.note_font_size, 8, 96)
            if ok:
                self.change_note_font_size(new_size)

    def _update_script_field_lock(self):
        """Stage 19: called on every edit to a SCRIPT/GLOBAL_SCRIPT panel's
        field (and once up front, for a value set by the constructor/Browse/
        Load that never fired textChanged). Locks the field, styled like the
        other read-only path fields, the moment it holds a real .py/.mel
        file path - stays a normal editable field for raw pasted code."""
        if self.p_type not in ("SCRIPT", "GLOBAL_SCRIPT"):
            return
        if is_script_file_ref(self.path()):
            style_readonly_path_field(self.field, self.accent)
        else:
            self.field.setReadOnly(False)
            self.field.setStyleSheet("")
            self.field.setToolTip(
                "Path to a .py/.mel script file (locks automatically once set), "
                "or paste raw Python/MEL code directly.")

    def browse_file(self):
        kwargs = {'fm': 1}
        # "All Files" is listed first so the dialog shows every file type by
        # default; the type-specific filters remain available as options.
        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"): kwargs['ff'] = "All Files (*.*);;Scripts (*.py *.mel);;Python (*.py);;MEL (*.mel)"
        elif self.p_type in ["JSON", "SHAPES", "TWEAKER", "MATERIAL"]: kwargs['ff'] = "All Files (*.*);;JSON (*.jSkin *.json)"
        elif self.p_type in ("IMPORT_3D", "IMPORT_LOD"): kwargs['ff'] = "All Files (*.*);;3D Files (*.fbx *.obj *.abc *.ma *.mb);;FBX (*.fbx);;OBJ (*.obj);;Alembic (*.abc);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        elif self.p_type == "PUBLISH": kwargs['fm'] = 3; kwargs['caption'] = "Select Publish Directory"
        else: return
        
        sd = self.get_start_dir()
        if os.path.exists(sd): kwargs['dir'] = sd
        res = cmds.fileDialog2(**kwargs)
        if res: self.field.setText(self.workspace.relativize_path(res[0]))

    def execute(self, progress_ui=None, force=False):
        """`force=True` runs even when the panel's checkbox is OFF.

        Stage 45: an inactive panel is skipped by the full build (that's what
        the checkbox is for), but its own RUN button should still work - it
        is how you test one step by hand without switching the step back on
        and forgetting to switch it off again. Only the build passes
        force=False."""
        if not self.is_active and not force: return True
        # A NOTE panel is never a build step - it has no RUN button to
        # click (hidden in __init__) and nothing to run even if something
        # called this directly, so always succeed without doing anything.
        if self.p_type == "NOTE": return True
        success = False
        error_msg = ""
        self.btn_run.setText("RUNNING...")

        local_ui = False
        if progress_ui is None:
            self.workspace.main_window.setEnabled(False)
            progress_ui = BuildProgressDialog(self.workspace, total_steps=1)
            progress_ui.lbl_status.setText(f"Executing: {self.title_edit.text()}")
            progress_ui.show()
            local_ui = True

        QtWidgets.QApplication.processEvents()
        start_t = time.time()

        try:
            if progress_ui.is_cancelled:
                success = False
                error_msg = "Cancelled by user."
            else:
                if self.p_type == "SCRIPT":
                    func_call_txt = self.func_field.text().strip()
                    success, error_msg = self.workspace.run_script(
                        self.path(), func_call=func_call_txt,
                        share_global=(hasattr(self, 'chk_share_global')
                                      and self.chk_share_global.isChecked()))
                elif self.p_type == "GLOBAL_SCRIPT":
                    func_call_txt = self.func_field.text().strip()
                    success, error_msg = self.workspace.run_script_global(self.path(), func_call=func_call_txt)
                elif self.p_type == "IMPORT_3D":
                    # Stage 18: MA and IMPORT_3D merged into one panel type -
                    # import_3d_logic already auto-detects by extension
                    # (.abc/.fbx/.obj get their dedicated importer, anything
                    # else - including .ma/.mb - falls back to cmds.file()).
                    success, error_msg = self.workspace.import_3d_logic(self.path())
                elif self.p_type == "JSON":
                    success, error_msg = self.workspace.load_skin_cluster_logic(
                        self.path(), self.mesh_field.text(),
                        show_popup=self.naming_popup_enabled())
                    # Stage 33: re-skin runs automatically after a
                    # successful load, but ONLY if at least one Scale
                    # Control is listed - an empty Scale Control(s) field
                    # means "no re-skin at all", not "re-skin with no
                    # scaling". It also only runs if the weights actually
                    # loaded, since re-binding on top of a failed load would
                    # just bake in whatever wrong state the mesh was left in.
                    meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                    controls, scale = self.reskin_settings()
                    if success and meshes and controls:
                        success, error_msg = self.workspace.run_reskin_logic(meshes, controls, scale)
                elif self.p_type == "TWEAKER":
                    success, error_msg = self._execute_tweaker()
                elif self.p_type == "SHAPES":
                    if os.path.exists(self.path()) or os.path.exists(get_versioned_path(self.path(), True)):
                        try:
                            success = import_control_shapes(self.path())
                            if not success: error_msg = "Failed to import shapes."
                        except Exception as e:
                            success = False; error_msg = traceback.format_exc()
                    else:
                        success = False
                        error_msg = f"Shape file not found: {self.path()}"
                elif self.p_type == "MATERIAL":
                    if os.path.exists(self.path()) or os.path.exists(get_versioned_path(self.path(), True)):
                        try:
                            meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                            success = import_material_data(self.path(), meshes=meshes if meshes else None)
                            if not success: error_msg = "Failed to import material."
                        except Exception as e:
                            success = False; error_msg = traceback.format_exc()
                    else:
                        success = False
                        error_msg = f"Material file not found: {self.path()}"
                elif self.p_type == "PUBLISH":
                    if os.path.exists(self.path()):
                        success = True
                        cmds.warning("Publish Path Validated.")
                    else:
                        success = False
                        error_msg = "Publish Path does not exist!"
                elif self.p_type == "IMPORT_LOD":
                    # Same import_3d_logic() as IMPORT_3D, then
                    # organize_lod_logic() runs over the scene the import
                    # just landed in. A blank file path is allowed (the
                    # rigger may just want to re-organize a scene that's
                    # already been imported/assembled by hand) - only the
                    # organize step is required to have run.
                    path = self.path().strip()
                    if path:
                        success, error_msg = self.workspace.import_3d_logic(path)
                        if not success:
                            pass  # don't attempt to organize on a failed import
                        else:
                            success, error_msg = self.workspace.organize_lod_logic(
                                self.asset_name_field.text())
                    else:
                        success, error_msg = self.workspace.organize_lod_logic(
                            self.asset_name_field.text())
                elif self.p_type == "DELETE_OBJ":
                    success, error_msg = self.workspace.delete_by_name_logic(self.target_field.text())
                elif self.p_type == "ZERO_OUT":
                    success, error_msg = self.workspace.zero_out_logic(self.target_field.text())
                elif self.p_type == "PARENT_OBJ":
                    success, error_msg = self.workspace.parent_logic(
                        self.child_field.text(), self.parent_field.text())
                elif self.p_type == "INSTANCE_OBJ":
                    success, error_msg = self.workspace.create_instances_logic(
                        self.target_field.text(), self.path(),
                        self.func_field.text(), panel_uuid=self.uuid)
        finally:
            QtWidgets.QApplication.processEvents() 
            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)

            if local_ui:
                progress_ui.progress_bar.setValue(1)
                progress_ui.close()
                self.workspace.main_window.setEnabled(True)

            if success:
                self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
                self.btn_run.setText(panel_run_label(self.p_type))
                self.last_error_msg = ""
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(False)
                # Manual click (not part of a build): cache this step too.
                if local_ui and self.p_type != "PUBLISH":
                    self.cache_on_manual_run()
            else:
                self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
                self.btn_run.setText("SHOW ERROR")
                self.last_error_msg = error_msg if error_msg else "Unknown execution failure."
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(True)

        return success
