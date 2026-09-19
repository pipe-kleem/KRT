"""ModuleGraphWidget - component_settings methods (mixin, auto-split from graph.py)."""
from ._shared import *
from .catalog import list_plebe_templates
from .dialogs import PlebeTemplateDialog
from .items import RigNode


class GraphComponentSettingsMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    def _refresh_mgear_settings_group(self, node, is_component):
        """Stage 31, request #2 / Stage 34 (reverted the inline embed):
        decide what the 'Main Settings' tab shows and whether the "Open
        Full mGear Settings" button is usable.

        Previously this tab held exactly one thing - KRT's mirror of mGear's
        Main Settings - shown only for a plain catalog component, so selecting
        a Custom Module (.sgt) node gave a completely blank tab with no hint
        as to why. Now: the button to open mGear's own Settings window (which
        is where the 'Component Settings' tab lives) is offered for ANY node
        whose built guide is a real Shifter component, and when nothing
        applies the tab says so instead of showing nothing.

        Stage 34: no more inline embed - mGear's Settings window opens in
        its own real window (open_mgear_component_settings), exactly as
        Shifter Guide Manager's own "Settings" button does. Simpler, and it
        doesn't depend on reparenting a QDialog's internals out from under
        it, which is what made the inline version unreliable."""
        comp_type = self._guide_root_comp_type(node)
        is_script = node.module_type == CUSTOM_SCRIPT_MODULE_TYPE
        has_guide = bool(node.maya_guide_root and cmds.objExists(node.maya_guide_root))

        # A script-only node never has a guide, so mGear settings can't ever
        # apply to it; everything else gets the button, enabled once its
        # built guide turns out to be a real Shifter component.
        show_group = not is_script
        self.mgear_settings_group.setVisible(show_group)
        if show_group:
            self.btn_open_mgear_settings.setEnabled(bool(comp_type))
            if comp_type:
                self.btn_open_mgear_settings.setToolTip(self._mgear_settings_btn_tooltip)
                self.lbl_mgear_settings_state.setText(
                    "Live guide is an mGear '<b>{}</b>' component - the button above opens "
                    "mGear's own Settings window for it (Main Settings + Component Settings + "
                    "any Ctl/Joint name tabs).".format(comp_type))
            elif not has_guide:
                self.btn_open_mgear_settings.setToolTip(
                    "Build this node's guide first (Build Guides, or the ⟲ button on the "
                    "Hierarchy tab) - mGear's own Settings window reads/writes the LIVE "
                    "Maya node, so there's nothing for it to open yet.")
                self.lbl_mgear_settings_state.setText(
                    "Guide not built yet. mGear's Settings window edits the live Maya guide, "
                    "so build this node's guide first and this becomes available.")
            else:
                self.btn_open_mgear_settings.setToolTip(
                    "This node's built guide has no 'comp_type' attribute, so it isn't a "
                    "Shifter component guide and mGear's Settings window doesn't apply to it.")
                self.lbl_mgear_settings_state.setText(
                    "This node's built guide isn't a Shifter component guide (no 'comp_type'), "
                    "so mGear's Settings window doesn't apply to it.")

        # KRT's own mirror of mGear's Main Settings fields - the only way to
        # set these before a guide is built, and still useful afterward for
        # anyone who doesn't want to pop open a separate window.
        self.component_group.setVisible(is_component)

        # The explanatory note only appears when the tab would otherwise be
        # empty or nearly so - never when there are real settings on screen.
        if is_component:
            self.lbl_main_settings_note.setVisible(False)
        else:
            self.lbl_main_settings_note.setVisible(True)
            if is_script:
                self.lbl_main_settings_note.setText(
                    "A Custom Script node has no guide and no component settings - it just runs "
                    "its script. See the <b>Scripts</b> tab.")
            elif node.module_type == PLEBE_MODULE_TYPE:
                self.lbl_main_settings_note.setText(
                    "This is a whole character template (Plebe), not a single mGear component, so "
                    "it has no single set of Main Settings. Its own options are on the "
                    "<b>Template</b> tab; the individual components inside its built guide can be "
                    "edited with mGear's Settings window above, or by selecting them in Maya.")
            else:
                self.lbl_main_settings_note.setText(
                    "This is a Custom Module (.sgt file) node. KRT's Main Settings mirror only "
                    "applies to catalog components it builds itself - but if the guide this file "
                    "imports is a real mGear component, use the button above to edit it with "
                    "mGear's own Settings window (Component Settings included).")

    def _static_locator_names_for_type(self, comp_type):
        """Stage 30: the set of guide-locator names a catalog component of
        `comp_type` will create, worked out WITHOUT building anything in
        Maya - by reading that component's own guide.py source directly
        (mgear.shifter_classic_components.<type>.guide / shifter_epic_
        components.<type>.guide) and pulling out every literal name passed
        to self.addLoc(...), the same call mGear's own guide code uses to
        actually create each locator.

        This is deliberately a static-source read, not a live probe build -
        no scene interaction, no risk of colliding with an existing guide,
        safe to call at any time (module search, node selection, before
        anything is ever built). The tradeoff: a name built from a runtime
        value (a loop counter, a spinner-driven joint count, an f-string/%-
        format) isn't a plain string literal in the source, so it won't be
        found here - those components fall back to just whatever a live
        build already reveals via _list_attach_points once actually built.
        Cached per comp_type for the life of this widget - it's a single
        file read + regex, but there's no reason to repeat it.
        """
        if comp_type in self._type_locator_static_cache:
            return self._type_locator_static_cache[comp_type]

        names = []
        try:
            import mgear.shifter as mg_shifter_mod
            guide_module = mg_shifter_mod.importComponentGuide(comp_type)
            src_path = os.path.join(os.path.dirname(guide_module.__file__), "guide.py")
            if not os.path.exists(src_path):
                src_path = guide_module.__file__
            with open(src_path, "r") as f:
                source = f.read()
            # self.addLoc("root", ...) or self.addLoc(self.getName("root"), ...)
            # - either way, the literal name string is what we want.
            pattern = re.compile(r'\.addLoc\(\s*(?:self\.getName\(\s*)?["\']([A-Za-z0-9_\-]+)["\']')
            names = sorted(set(pattern.findall(source)))
        except Exception:
            # Any failure here (mGear not loaded, component type not found,
            # unexpected source layout) just means no pre-build preview for
            # this type - not a reason to break node selection over.
            names = []

        self._type_locator_static_cache[comp_type] = names
        return names

    def _list_attach_points(self, parent_node):
        """Every real Maya transform under `parent_node`'s built guide that
        the selected/dragged child could plausibly attach beneath instead of
        the whole guide root - e.g. a spine's per-section locators, or a
        Plebe biped's named guide locators. Returns [(label, long_name)],
        sorted, and only the guide's own descendants (never controls/joints
        from a rig that may already be built alongside it).

        Stage 28: cached per guide-root long name (see
        _invalidate_attach_points_cache) so repeatedly selecting different
        nodes that share the same already-built parent doesn't re-walk that
        parent's whole guide hierarchy in Maya every single time - this was
        the actual source of the "Attach Under takes too long to check"
        slowdown on a full biped guide.

        Stage 30: if the parent's guide hasn't actually been built yet, this
        no longer just returns empty - for a real catalog component it
        falls back to _static_locator_names_for_type(), so Attach Under has
        real, name-accurate options to offer immediately, with no need to
        build that parent's guide first just to see what's there. These
        returned pairs are (short_name, short_name) rather than a real long
        Maya path (there's no live node yet) - node.parent_local_target
        already self-heals a name that doesn't cmds.objExists() by matching
        short names against whatever's actually live at build time (see
        _resolve_attach_parent), which is exactly what lets a pre-build pick
        made here resolve correctly once the guide is really drawn."""
        if not parent_node:
            return []
        if not parent_node.maya_guide_root or not cmds.objExists(parent_node.maya_guide_root):
            if parent_node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
                return []
            static_names = self._static_locator_names_for_type(parent_node.module_type)
            return [(name, name) for name in static_names]
        root = parent_node.maya_guide_root
        cached = self._attach_points_cache.get(root)
        if cached is not None:
            return cached
        try:
            descendants = cmds.listRelatives(root, allDescendents=True,
                                             type="transform", fullPath=True) or []
        except Exception:
            return []
        points = []
        for long_name in descendants:
            short = long_name.split("|")[-1]
            # Guide locators are plain transforms named things like
            # "spine_C0_1_loc" or "chest" - skip anything that is clearly a
            # rig control/joint rather than a guide locator, in case a rig
            # has already been built alongside this guide.
            if short.endswith(("_ctl", "_jnt", "Shape")):
                continue
            points.append((short, long_name))
        points.sort(key=lambda p: p[0].lower())
        self._attach_points_cache[root] = points
        return points

    def _invalidate_attach_points_cache(self, root=None):
        """Drop the _list_attach_points() cache - for one specific guide
        root (a rebuild that reuses the same root name, e.g. mGear's biped
        'guide') or, when `root` is None, entirely (a batch delete/undo/redo/
        load can touch more roots than are worth tracking individually).
        Cheap to over-invalidate - the next selection just re-walks Maya once
        and re-caches; the expensive part this is protecting against is
        re-walking on EVERY click, not the occasional real rebuild."""
        if root is None:
            self._attach_points_cache.clear()
        else:
            self._attach_points_cache.pop(root, None)

    def capture_node_component_settings(self, node):
        """Snapshot every user setting on this node's live guide root that
        isn't identity and isn't already a mirrored Main Settings field -
        i.e. everything mGear's own 'Component Settings' tab edits, whatever
        the component type happens to be.

        Attributes with an incoming connection are skipped deliberately:
        their value is driven by something else, so re-applying a frozen copy
        of it later is meaningless at best and destructive at worst (the same
        lesson the Material panel's shadingEngine.surfaceShader bug taught)."""
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        try:
            attrs = cmds.listAttr(root, userDefined=True) or []
        except Exception:
            traceback.print_exc()
            return
        snapshot = {}
        for attr in attrs:
            if attr in self.COMPONENT_IDENTITY_ATTRS or attr in self.MIRRORED_MAIN_SETTINGS_ATTRS:
                continue
            plug = f"{root}.{attr}"
            try:
                if cmds.getAttr(plug, type=True) == "message":
                    continue
                if cmds.listConnections(plug, source=True, destination=False, plugs=True):
                    continue
                value = cmds.getAttr(plug)
            except Exception:
                continue
            if isinstance(value, (int, float, bool, str)):
                snapshot[attr] = value
            elif isinstance(value, (list, tuple)) and value:
                try:
                    if isinstance(value[0], (list, tuple)):
                        snapshot[attr] = [list(v) for v in value]
                    elif isinstance(value[0], (int, float, str)):
                        snapshot[attr] = list(value)
                except Exception:
                    continue
        if snapshot:
            node.component_settings_snapshot = snapshot

    def apply_node_component_settings(self, node):
        """Replay a captured Component Settings snapshot onto a freshly built
        guide. Anything the snapshot names that this guide doesn't have (a
        component/mGear version change) is skipped rather than treated as an
        error, same tolerance as apply_node_guide_positions."""
        root = node.maya_guide_root
        snapshot = node.component_settings_snapshot
        if not root or not snapshot or not cmds.objExists(root):
            return
        for attr, value in snapshot.items():
            plug = f"{root}.{attr}"
            try:
                if not cmds.attributeQuery(attr, node=root, exists=True):
                    continue
                if cmds.listConnections(plug, source=True, destination=False, plugs=True):
                    continue
                if isinstance(value, str):
                    cmds.setAttr(plug, value, type="string")
                elif isinstance(value, list):
                    if value and isinstance(value[0], list):
                        cmds.setAttr(plug, *value[0])
                    else:
                        cmds.setAttr(plug, *value)
                else:
                    cmds.setAttr(plug, value)
            except Exception:
                continue

    def sync_node_main_settings_from_guide(self, node):
        """Read the Main Settings attributes back OFF the live guide root
        into the node's own fields. Needed because those fields are no longer
        only editable through KRT's mirror - mGear's own Settings window
        (opened via the "⚙ Settings" button) writes them straight onto the
        guide, and without this the KRT-side copy would go stale and then
        overwrite the user's change on the next build."""
        if node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
            return
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return

        def _get(attr, default=None):
            try:
                if not cmds.attributeQuery(attr, node=root, exists=True):
                    return default
                return cmds.getAttr(f"{root}.{attr}")
            except Exception:
                return default

        try:
            node.comp_index = int(_get("comp_index", node.comp_index))
            node.connector = _get("connector", node.connector) or node.connector
            node.use_joint_index = bool(_get("useIndex", node.use_joint_index))
            node.parent_joint_index = int(_get("parentJointIndex", node.parent_joint_index))
            node.joint_names = _get("joint_names", node.joint_names) or ""
            node.joint_rot_offset_x = float(_get("joint_rot_offset_x", node.joint_rot_offset_x))
            node.joint_rot_offset_y = float(_get("joint_rot_offset_y", node.joint_rot_offset_y))
            node.joint_rot_offset_z = float(_get("joint_rot_offset_z", node.joint_rot_offset_z))
            node.ui_host = _get("ui_host", node.ui_host) or ""
            node.ctl_group = _get("ctlGrp", node.ctl_group) or ""
            node.override_colors = bool(_get("Override_Color", node.override_colors))
            node.use_rgb_colors = bool(_get("Use_RGB_Color", node.use_rgb_colors))
            node.color_fk_index = int(_get("color_fk", node.color_fk_index))
            node.color_ik_index = int(_get("color_ik", node.color_ik_index))
            rgb_fk = _get("RGB_fk")
            if rgb_fk:
                node.color_fk_rgb = tuple(rgb_fk[0]) if isinstance(rgb_fk[0], (list, tuple)) else tuple(rgb_fk)
            rgb_ik = _get("RGB_ik")
            if rgb_ik:
                node.color_ik_rgb = tuple(rgb_ik[0]) if isinstance(rgb_ik[0], (list, tuple)) else tuple(rgb_ik)
        except Exception:
            traceback.print_exc()

    def _refresh_attach_point_combo(self, node, parent_node):
        self.combo_attach_point.blockSignals(True)
        self.combo_attach_point.clear()
        self.combo_attach_point.addItem("(Whole Guide Root)", "")
        points = self._list_attach_points(parent_node) if parent_node else []
        select_idx = 0
        for label, long_name in points:
            self.combo_attach_point.addItem(label, long_name)
            if long_name == node.parent_local_target:
                select_idx = self.combo_attach_point.count() - 1
        self.combo_attach_point.setCurrentIndex(select_idx)
        self.combo_attach_point.setEnabled(parent_node is not None and len(points) > 0)
        self.combo_attach_point.blockSignals(False)

    def _snap_attach_point_text(self):
        """Stage 26: the Attach Under combo is editable (for search), so
        clicking away or Tab-ing out after typing a partial filter with no
        exact match would otherwise leave that typed fragment sitting in the
        field looking like a selection. Snap it back to whatever's actually
        selected (the real current index's text) whenever the typed text
        isn't an exact match for one of the real entries."""
        combo = self.combo_attach_point
        text = combo.currentText()
        idx = combo.findText(text, QtCore.Qt.MatchFixedString)
        if idx >= 0:
            if idx != combo.currentIndex():
                combo.setCurrentIndex(idx)
        else:
            combo.setEditText(combo.itemText(combo.currentIndex()))

    def on_attach_point_combo_changed(self, index):
        if getattr(self, "_updating_attr", False): return
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        self._push_undo_snapshot()
        node.parent_local_target = self.combo_attach_point.itemData(index) or None
        node.update_display()
        self._refresh_wire_tooltip_for(node)
        self.workspace.refresh_module_list()

    def open_mgear_component_settings(self):
        """Stage 29: open mGear's OWN, completely unmodified per-component
        'Settings' window - the exact same thing Shifter Guide Manager's own
        'Settings' button opens (mgear.shifter.guide_manager.inspect_settings)
        - for the selected node's LIVE built guide.

        Why this exists instead of KRT hand-reimplementing it: mGear's real
        Settings window is actually up to 4 tabs, and only the first ("Main
        Settings") is generic across every component type - Stage 27 mirrors
        that one directly into the Node tab. The rest are NOT generic:
        - "Component Settings" is defined separately by EVERY ONE of mGear's
          ~50+ component types (control_01's has icon/joint/keyable-channel/
          ikRefArray fields; a completely different component type's tab has
          entirely different fields) - hand-porting all of them, from a
          sandbox that can never run Maya to check the result against a real
          guide, isn't a realistic or safe undertaking.
        - "Joints/Ctl/Space Alias Description Names" tabs only appear for a
          component type that actually defines that kind of name (checked via
          hasAttr on the live guide root), each holding one label+textbox+
          Reset row per name.
        Reusing mGear's own classes directly (`shifter.importComponentGuide
        (comp_type).componentSettings`) means every one of these, for every
        component type, is always exactly correct - it IS mGear's code -
        without KRT tracking any of it by hand. The real limitation: mGear's
        dialog reads/writes the LIVE Maya node (`pm.selected()[0]`), so this
        only works once the node's guide is actually built - there's no
        pre-build equivalent the way Stage 27's Main Settings mirror has.
        """
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            cmds.warning(f"'{node.display_title}' has no built guide yet - use Build Guides "
                         "(or the ⟲ Build Parent's Guide button) first.")
            return
        if not cmds.attributeQuery("comp_type", node=root, exists=True):
            cmds.warning(f"'{node.display_title}'s guide root has no 'comp_type' attribute - "
                         "it isn't a real Shifter component guide, so mGear's own Settings "
                         "window doesn't apply to it.")
            return

        try:
            from mgear import shifter as mg_shifter
            from mgear.core import pyqt as mg_pyqt
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return

        comp_type = cmds.getAttr(f"{root}.comp_type")
        cmds.select(root, replace=True)
        try:
            guide_module = mg_shifter.importComponentGuide(comp_type)
            wind = mg_pyqt.showDialog(guide_module.componentSettings, dockable=True)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to open mGear's Settings window for '{node.display_title}' "
                         f"(component type '{comp_type}') - see Script Editor.")
            return
        return wind

    def change_selected_node_template(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or selected[0].module_type != PLEBE_MODULE_TYPE:
            return
        node = selected[0]
        templates = list_plebe_templates()
        if not templates:
            cmds.warning("No mGear Plebe character templates found.")
            return
        dialog = PlebeTemplateDialog(templates, self.workspace.main_window, current_path=node.plebe_template_path)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted and dialog.selected_path:
            self._push_undo_snapshot()
            node.plebe_template_path = dialog.selected_path
            node.plebe_template_name = dialog.selected_name
            if not node.custom_name.strip() or node.custom_name.startswith("Plebe:"):
                node.custom_name = f"Plebe: {dialog.selected_name}"
            node.update_display()
            self.update_attr_editor()
            self.workspace.refresh_module_list()

    def _style_rgb_button(self, button, rgb):
        """Stage 27: paint an "RGB..." picker button with the color it
        currently holds, so Color Settings reads at a glance without needing
        to open the picker - same idea as mGear's own FK/IK swatch labels."""
        r, g, b = (max(0.0, min(1.0, c)) for c in rgb)
        button.setStyleSheet(
            f"background-color: rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)}); "
            "color: white; font-weight: bold;"
        )

    def pick_component_rgb_color(self, which):
        """Stage 27: 'RGB...' button next to the FK/IK color index spinbox -
        opens a normal color picker and stores the result as this node's
        color_fk_rgb/color_ik_rgb (only actually used by mGear when Use RGB
        Colors is checked - same as mGear's own dialog)."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        current = node.color_fk_rgb if which == "fk" else node.color_ik_rgb
        r, g, b = (max(0.0, min(1.0, c)) for c in current)
        initial = QtGui.QColor(int(r * 255), int(g * 255), int(b * 255))
        color = QtWidgets.QColorDialog.getColor(initial, self.workspace.main_window, "Pick a Color")
        if not color.isValid():
            return
        self._push_undo_snapshot()
        rgb = (color.redF(), color.greenF(), color.blueF())
        if which == "fk":
            node.color_fk_rgb = rgb
            self._style_rgb_button(self.btn_rgb_fk, rgb)
        else:
            node.color_ik_rgb = rgb
            self._style_rgb_button(self.btn_rgb_ik, rgb)
        self.apply_main_settings_live(node)

    def grab_selected_as_ui_host(self):
        """Stage 27: the "<<" button next to Channels Host - grabs whatever
        guide transform is currently selected in Maya, same convenience
        mGear's own Settings dialog offers (updateHostUI). Only accepts an
        actual guide object (has the 'isGearGuide' attribute mGear stamps
        on every guide transform), same restriction mGear itself applies."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        sel = cmds.ls(selection=True, long=True) or []
        if not sel:
            cmds.warning("Nothing selected in Maya to grab as the UI host.")
            return
        target = sel[0]
        if not cmds.attributeQuery("isGearGuide", node=target, exists=True):
            cmds.warning("The selected object is not a guide element - pick a real mGear guide transform.")
            return
        self._push_undo_snapshot()
        node.ui_host = target
        self.edit_ui_host.setText(target)
        self.apply_main_settings_live(node)

    def edit_selected_node_joint_names(self):
        """Stage 27: 'Configure...' next to Joint Names - a lightweight
        stand-in for mGear's own ordered-table editor. Same underlying
        storage (a comma-joined string in the 'joint_names' attribute), just
        edited here as one name per line for simplicity."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        current = "\n".join(n.strip() for n in node.joint_names.split(",") if n.strip())
        dialog = QtWidgets.QDialog(self.workspace.main_window)
        dialog.setWindowTitle(f"Joint Names - {node.display_title}")
        dialog.setMinimumSize(360, 320)
        dialog.setStyleSheet("QDialog { background-color: #1e1e1e; color: white; } "
                             "QLabel { color: #cccccc; } "
                             "QPlainTextEdit { background: #141414; border: 1px solid #333; color: #d4d4d4; } "
                             "QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }")
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel("One joint name per line, in order (blank lines are dropped):"))
        text_edit = QtWidgets.QPlainTextEdit()
        text_edit.setPlainText(current)
        layout.addWidget(text_edit)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = QtWidgets.QPushButton("Save")
        btn_ok.setStyleSheet("background-color: #2bb5a8; font-weight: bold;")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return
        self._push_undo_snapshot()
        names = [n.strip() for n in text_edit.toPlainText().splitlines() if n.strip()]
        node.joint_names = ",".join(names)
        summary = "Joint Names (<b>{0} set</b>)".format(len(names)) if names else "Joint Names (None)"
        self.lbl_joint_names.setText(summary)
        self.apply_main_settings_live(node)

    def change_selected_node_sgt_path(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or selected[0].module_type != CUSTOM_SGT_MODULE_TYPE:
            return
        node = selected[0]
        start_dir = os.path.dirname(self.workspace.resolve_path(node.custom_sgt_path)) if node.custom_sgt_path else self.workspace.default_browse_dir()
        res = cmds.fileDialog2(
            fm=1, ff="mGear Guide Template (*.sgt);;All Files (*.*)",
            caption="Choose a Custom Module .sgt File",
            dir=start_dir if os.path.exists(start_dir) else "")
        if res:
            self._push_undo_snapshot()
            node.custom_sgt_path = self.workspace.relativize_path(res[0])   # Stage 41
            if not node.custom_name.strip():
                node.custom_name = os.path.splitext(os.path.basename(res[0]))[0]
            node.update_display()
            self.update_attr_editor()
            self.workspace.refresh_module_list()

    def apply_main_settings_live(self, node):
        """Stage 27: once a real Shifter component's guide already exists in
        the scene, editing one of the Main Settings fields in the Node tab
        should take effect immediately - same expectation as mGear's own
        Settings dialog, which edits the live guide attributes directly -
        instead of only being picked up on the NEXT full rebuild. No-ops
        silently if there's no guide yet (build_node_guide's
        comp_guide.setParamDefValue calls are what apply these on first
        build) or the node isn't a real component (Plebe/Custom Module/
        Custom Script nodes don't have any of these attributes)."""
        if node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
            return
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        try:
            cmds.setAttr(f"{root}.comp_index", node.comp_index)
            cmds.setAttr(f"{root}.connector", node.connector, type="string")
            cmds.setAttr(f"{root}.useIndex", node.use_joint_index)
            cmds.setAttr(f"{root}.parentJointIndex", node.parent_joint_index)
            cmds.setAttr(f"{root}.joint_names", node.joint_names, type="string")
            cmds.setAttr(f"{root}.joint_rot_offset_x", node.joint_rot_offset_x)
            cmds.setAttr(f"{root}.joint_rot_offset_y", node.joint_rot_offset_y)
            cmds.setAttr(f"{root}.joint_rot_offset_z", node.joint_rot_offset_z)
            if node.ui_host and cmds.attributeQuery("ui_host", node=root, exists=True):
                cmds.setAttr(f"{root}.ui_host", node.ui_host, type="string")
            if node.ctl_group and cmds.attributeQuery("ctlGrp", node=root, exists=True):
                cmds.setAttr(f"{root}.ctlGrp", node.ctl_group, type="string")
            cmds.setAttr(f"{root}.Override_Color", node.override_colors)
            cmds.setAttr(f"{root}.Use_RGB_Color", node.use_rgb_colors)
            cmds.setAttr(f"{root}.color_fk", node.color_fk_index)
            cmds.setAttr(f"{root}.color_ik", node.color_ik_index)
            cmds.setAttr(f"{root}.RGB_fk", *node.color_fk_rgb, type="double3")
            cmds.setAttr(f"{root}.RGB_ik", *node.color_ik_rgb, type="double3")
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Couldn't apply Main Settings live to '{node.display_title}' - "
                         "see Script Editor. The values are still saved and will apply on the next build.")
