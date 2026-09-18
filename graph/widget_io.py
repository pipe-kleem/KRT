"""ModuleGraphWidget - io methods (mixin, auto-split from graph.py)."""
from ._shared import *


class GraphIoMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    def compute_default_guide_path(self):
        """Where 'Save Guides'/'Load Guides' points by default: a 'guide'
        subfolder right next to the current session's own KRT pipeline JSON,
        named to match it - e.g. '.../MyRig.json' -> '.../guide/MyRig_guide.json'.
        Falls back to the home-directory default when the session hasn't
        been saved anywhere yet."""
        session_path = getattr(self.workspace, "session_path", "") or ""
        if session_path:
            session_dir = os.path.dirname(session_path)
            base = os.path.splitext(os.path.basename(session_path))[0]
            return os.path.join(session_dir, "guide", base + "_guide.json").replace("\\", "/")
        return os.path.join(os.path.expanduser('~'), "kleem_guide.json").replace("\\", "/")

    def refresh_default_guide_path(self):
        """Re-point the Guide Path field at the current session's own
        'guide' subfolder - called whenever the session's save location
        changes (Save Session, Load JSON Pipeline, new/closed tab), so the
        guide file always follows the KRT json without the user having to
        browse for it by hand. A manual edit to the field survives until the
        next such change, then gets recomputed again."""
        self.path_field.setText(self.compute_default_guide_path())

    def _guide_browse_start_dir(self):
        """Where the guide-JSON Browse/Import dialogs should open (Stage 17):
        the CURRENT guide path's own folder if it's already a real path,
        else the most recent pipeline JSON KRT knows about
        (session_manager's recent_files) - the same "fall back to something
        recent" idea behind KRT's own Load JSON Pipeline recent-files list,
        instead of leaving it to whatever folder Maya's fileDialog2 happened
        to open last, anywhere in the whole Maya session."""
        current = self.path_field.text().strip()
        if current:
            d = os.path.dirname(current)
            if d and os.path.exists(d):
                return d
        session_path = getattr(self.workspace, "session_path", "") or ""
        if session_path:
            d = os.path.dirname(session_path)
            if d and os.path.exists(d):
                return d
        try:
            recents = self.workspace.main_window.session.data.get("recent_files", [])
        except Exception:
            recents = []
        for p in recents:
            if p and os.path.exists(p):
                return os.path.dirname(p)
        return ""

    def browse_path(self):
        start_dir = self._guide_browse_start_dir()
        # fileMode=1 ("an existing file must be selected") - not 0 ("any
        # file, whether it exists or not"), which is what made this open as
        # a Save-As dialog (native "Save As" title, "Save" button) even
        # though Browse is for picking an EXISTING guide JSON to point the
        # field at, not for choosing where to save one.
        kwargs = {"fileFilter": "KRT Guide JSON (*.json)", "dialogStyle": 2, "fileMode": 1,
                  "caption": "Browse Guide JSON"}
        if start_dir:
            kwargs["startingDirectory"] = start_dir
        file_path = cmds.fileDialog2(**kwargs)
        if file_path:
            self.path_field.setText(file_path[0])

    def _populate_guide_versions_menu(self, switch_menu):
        """Guide Path equivalent of widgets.py's SortablePanel.
        populate_versions_menu(): lists sibling "<base>_vNNN.<ext>" files
        next to the current Guide Path (the same "_vNNN" convention
        save_all_guides(overwrite=False) writes) so "Switch Version" can
        point the field at any of them without a file dialog."""
        v_actions = {}
        base_path = self.path_field.text().strip()
        if not base_path:
            switch_menu.setEnabled(False)
            return v_actions

        dir_name = os.path.dirname(base_path)
        if not dir_name or not os.path.exists(dir_name):
            switch_menu.setEnabled(False)
            return v_actions

        base_name, ext = os.path.splitext(os.path.basename(base_path))
        base_name_no_v = re.sub(r'_v\d+$', '', base_name)
        pattern = re.compile(r"^" + re.escape(base_name_no_v) + r"(?:_v(\d+))?" + re.escape(ext) + r"$")

        versions = []
        for f in os.listdir(dir_name):
            if pattern.match(f):
                versions.append(os.path.join(dir_name, f).replace('\\', '/'))
        versions.sort()

        if not versions:
            switch_menu.setEnabled(False)
        else:
            for v in versions:
                v_actions[switch_menu.addAction(os.path.basename(v))] = v
        return v_actions

    def show_guide_path_menu(self):
        """The Guide Path row's "..." menu (Stage 35): Browse / Save Guide
        (Overwrite or New Version) / Switch Version - the same save-versus-
        version-switch pattern the Rig Build workspace panels use in their
        own "..." menu (widgets.py's SortablePanel.show_context_menu), now
        that Browse/Save Guides/Export Config/Import Config are no longer
        separate always-visible buttons here."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")

        a_browse = menu.addAction("📂 Browse...")
        menu.addSeparator()
        a_save_over = menu.addAction("💾 Save Guide (Overwrite)")
        a_save_new = menu.addAction("💾 Save Guide (New Version)")
        switch_menu = menu.addMenu("🔄 Switch Version")
        v_actions = self._populate_guide_versions_menu(switch_menu)

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if not action:
            return

        if action == a_browse:
            self.browse_path()
        elif action == a_save_over:
            self.save_all_guides(overwrite=True)
        elif action == a_save_new:
            self.save_all_guides(overwrite=False)
        elif action in v_actions:
            self.path_field.setText(v_actions[action])

    def save_all_guides(self, overwrite=True):
        """Save this graph's own guide-relevant data (every node's type,
        position, side, Plebe/attach-point/control-shapes-library choices,
        etc - everything build_node_guide()/_build_plebe_guide() need to
        redraw the guide - plus the rig-wide Guide Settings tab) as plain
        KRT JSON.

        Deliberately does NOT touch the live Maya scene or require a guide
        to currently exist there: it just saves what's already in the graph
        - unlike a real mGear .sgt export, which needs a live scene guide to
        read from. KRT's own build flow (a module bubble's LOAD button, and
        the panel LOAD button) now deletes the guide from the scene right
        after building it, so relying on a live scene guide here would fail
        immediately after almost any normal build.

        overwrite=True (default - "Save Guide (Overwrite)", and every
        automatic sync from a KRT pipeline JSON save, see
        SessionWorkspace._save_pipeline_assets()/AdvancedSaveDialog/the
        AYON publish flow): writes to the Guide Path field's CURRENT path,
        unchanged - this is what keeps that field's path always matching
        the exact graph JSON on disk after a KRT save.

        overwrite=False ("Save Guide (New Version)"): bumps the path to the
        next "_vNNN" version first, the same convention the Rig Build
        workspace panels' own "Save (New Version)" uses, points the field
        at it, THEN writes - a deliberate "only Graph" save gets its own
        new version; a KRT-save-triggered sync does not.
        """
        path = self.path_field.text().strip()
        if not path: return

        if not overwrite:
            from .utils import get_versioned_path
            path = get_versioned_path(path, get_latest=False)
            self.path_field.setText(path)

        # Stage 28, request #3: capture every node's CURRENT live guide
        # positions right before writing anything out, so a rigger who moved
        # guide locators by hand after Build Guides has that placement
        # remembered here, in the guide data itself - the next Build Guides
        # (which redraws from scratch, e.g. after the module-bubble LOAD
        # flow's own guide auto-deletion) reapplies it automatically.
        # Stage 31: now captures mGear Component Settings changes too - see
        # capture_all_live_state().
        self.capture_all_live_state()

        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception:
                traceback.print_exc()
                cmds.error(f"Could not create guide folder '{directory}' - see Script Editor.")
                return

        try:
            with open(path, "w") as f:
                json.dump(self.get_graph_config_data(), f, indent=4)
            cmds.warning(f"Guide data (from the graph, not the scene) saved to {path}")
        except Exception:
            traceback.print_exc()
            cmds.error("Failed to save guide data - see Script Editor for details.")

    def load_all_guides(self):
        """Inverse of save_all_guides(): rebuilds the graph's nodes/wires and
        Guide Settings from a previously saved guide JSON. Doesn't touch the
        Maya scene either - use 'Build Guides' afterward to actually draw
        real guides from the restored graph."""
        path = self.path_field.text()
        if not os.path.exists(path):
            cmds.warning("Specified guide file does not exist.")
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            traceback.print_exc()
            cmds.error("Failed to read guide file - see Script Editor for details.")
            return

        if not isinstance(data, dict) or "nodes" not in data:
            cmds.warning("That file doesn't look like a KRT guide JSON (no 'nodes' key found).")
            return

        self._clear_undo_history()
        self._apply_graph_config_data(data)
        cmds.warning(f"Guide data loaded from {path}")

    # =====================================================
    # Graph Config JSON: everything KRT itself remembers about the graph -
    # node positions/types, per-node custom scripts, Plebe/attach-point/
    # separate-guide-group choices, and the rig-wide Guide Settings tab -
    # as its own standalone JSON, separate from the full pipeline/session
    # JSON (which also carries LOD panels, build steps, etc). "Save Guides"/
    # "Load Guides" above share this exact same data - they just write it
    # to the auto-managed 'guide' subfolder instead of a manually chosen
    # path. Neither one touches, or requires, a live Maya scene guide.
    # =====================================================

    def serialize_node(self, node):
        """Every KRT-specific thing about one graph node that isn't
        derivable from the Maya scene. Shared by the full pipeline JSON
        (workspace.py's get_current_pipeline_data/load_pipeline_from_file)
        and this standalone Graph Config JSON, so the two never drift apart
        on what a node needs to remember."""
        return {
            "uuid": node.uuid, "module_type": node.module_type, "custom_name": node.custom_name,
            "side": node.side, "x": node.pos().x(), "y": node.pos().y(),
            "custom_script_code": node.custom_script_code, "custom_script_lang": node.custom_script_lang,
            "custom_script_when": node.custom_script_when,
            "custom_script_trigger_node_uuid": node.custom_script_trigger_node_uuid,
            "plebe_template_path": node.plebe_template_path, "plebe_template_name": node.plebe_template_name,
            "align_guides_auto": node.align_guides_auto,
            "apply_guide_positions": node.apply_guide_positions,
            "fan_joint_enabled": node.fan_joint_enabled, "fan_joint_script": node.fan_joint_script,
            "stretchy_joint_enabled": node.stretchy_joint_enabled, "stretchy_joint_script": node.stretchy_joint_script,
            "control_shapes_library": node.control_shapes_library,
            "parent_local_target": node.parent_local_target,
            "build_separate_guide_group": node.build_separate_guide_group,
            "custom_sgt_path": node.custom_sgt_path,
            "comp_index": node.comp_index, "connector": node.connector,
            "use_joint_index": node.use_joint_index, "parent_joint_index": node.parent_joint_index,
            "joint_names": node.joint_names,
            "joint_rot_offset_x": node.joint_rot_offset_x, "joint_rot_offset_y": node.joint_rot_offset_y,
            "joint_rot_offset_z": node.joint_rot_offset_z,
            "ui_host": node.ui_host, "ctl_group": node.ctl_group,
            "override_colors": node.override_colors, "use_rgb_colors": node.use_rgb_colors,
            "color_fk_index": node.color_fk_index, "color_ik_index": node.color_ik_index,
            "color_fk_rgb": list(node.color_fk_rgb), "color_ik_rgb": list(node.color_ik_rgb),
            "guide_position_snapshot": node.guide_position_snapshot,
            "component_settings_snapshot": node.component_settings_snapshot,
        }

    def deserialize_node(self, nd):
        """Inverse of serialize_node() - builds a RigNode (not yet added to
        any scene) from a saved dict."""
        node = RigNode(nd["x"], nd["y"], nd["module_type"], nd["side"], nd.get("custom_name", ""))
        node.uuid = nd["uuid"]
        node.custom_script_code = nd.get("custom_script_code", "")
        node.custom_script_lang = nd.get("custom_script_lang", "python")
        node.custom_script_when = nd.get("custom_script_when", "none")
        node.custom_script_trigger_node_uuid = nd.get("custom_script_trigger_node_uuid")
        node.plebe_template_path = nd.get("plebe_template_path")
        node.plebe_template_name = nd.get("plebe_template_name", "")
        node.align_guides_auto = nd.get("align_guides_auto", True)
        node.apply_guide_positions = nd.get("apply_guide_positions", True)
        node.fan_joint_enabled = nd.get("fan_joint_enabled", False)
        node.fan_joint_script = nd.get("fan_joint_script", DEFAULT_FAN_JOINT_SCRIPT)
        node.stretchy_joint_enabled = nd.get("stretchy_joint_enabled", False)
        node.stretchy_joint_script = nd.get("stretchy_joint_script", DEFAULT_STRETCHY_JOINT_SCRIPT)
        node.control_shapes_library = nd.get(
            "control_shapes_library",
            DEFAULT_CONTROL_SHAPES_LIBRARY if node.module_type == PLEBE_MODULE_TYPE else "")
        node.parent_local_target = nd.get("parent_local_target")
        node.build_separate_guide_group = nd.get("build_separate_guide_group", False)
        node.custom_sgt_path = nd.get("custom_sgt_path")
        node.comp_index = nd.get("comp_index", 0)
        node.connector = nd.get("connector", "standard")
        node.use_joint_index = nd.get("use_joint_index", False)
        node.parent_joint_index = nd.get("parent_joint_index", -1)
        node.joint_names = nd.get("joint_names", "")
        node.joint_rot_offset_x = nd.get("joint_rot_offset_x", 0.0)
        node.joint_rot_offset_y = nd.get("joint_rot_offset_y", 0.0)
        node.joint_rot_offset_z = nd.get("joint_rot_offset_z", 0.0)
        node.ui_host = nd.get("ui_host", "")
        node.ctl_group = nd.get("ctl_group", "")
        node.override_colors = nd.get("override_colors", False)
        node.use_rgb_colors = nd.get("use_rgb_colors", False)
        node.color_fk_index = nd.get("color_fk_index", 6)
        node.color_ik_index = nd.get("color_ik_index", 18)
        node.color_fk_rgb = tuple(nd.get("color_fk_rgb", [0.0, 0.0, 1.0]))
        node.color_ik_rgb = tuple(nd.get("color_ik_rgb", [0.0, 0.25, 1.0]))
        node.guide_position_snapshot = nd.get("guide_position_snapshot", {}) or {}
        node.component_settings_snapshot = nd.get("component_settings_snapshot", {}) or {}
        node.update_display()
        return node

    def get_graph_config_data(self):
        nodes, wires = [], []
        for item in self.graph_view.scene.items():
            if isinstance(item, RigNode):
                nodes.append(self.serialize_node(item))
            elif isinstance(item, RigWire):
                wires.append({"source": item.source.uuid, "dest": item.dest.uuid})
        return {
            "krt_graph_config": True,
            "guide_path": self.path_field.text(),
            "nodes": nodes,
            "wires": wires,
            "guide_settings": self.guide_settings_panel.get_settings_dict(),
        }

    def _apply_graph_config_data(self, data):
        """Shared rebuild-the-graph-from-a-dict logic behind load_all_guides()
        (Stage 35: also used to be shared with the now-removed standalone
        Export/Import Config JSON buttons - Save/Load Guides above cover the
        same data now) - clears the current graph and recreates every node/
        wire from `data`, then reapplies the Guide Settings tab if present.
        Doesn't touch path_field (callers that care about a stored
        guide_path handle that themselves)."""
        self.graph_view.scene.clear()
        uuid_to_node = {}
        for nd in data.get("nodes", []):
            node = self.deserialize_node(nd)
            self.graph_view.scene.addItem(node)
            uuid_to_node[node.uuid] = node
        for wd in data.get("wires", []):
            src = uuid_to_node.get(wd.get("source")); dst = uuid_to_node.get(wd.get("dest"))
            if src and dst:
                self.graph_view.scene.addItem(RigWire(src, dst))

        if "guide_settings" in data:
            self.guide_settings_panel.apply_settings_dict(data["guide_settings"])

        self.workspace.refresh_module_list()
        self.update_attr_editor()
