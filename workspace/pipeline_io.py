"""SessionWorkspace - pipeline_io methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspacePipelineIoMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    def get_current_pipeline_data(self, ayon_context=None):
        pipeline_data = {"lods": []}
        if hasattr(self, 'edit_rig_name'): pipeline_data["rig_name"] = self.edit_rig_name.text().strip()
        pipeline_data["comment"] = getattr(self, 'pipeline_comment', "")
        pipeline_data["root_path"] = self.rig_root()   # Stage 41

        # Stage 38, request #2: everything set on the Playblast tab now
        # travels with the pipeline JSON too, same as every other KRT
        # setting - camera/group/anim/output paths, the QC info fields,
        # frame range/fps/resolution, and the Generate Camera settings -
        # instead of resetting to defaults every time this session is
        # reopened.
        if hasattr(self, 'pb_camera_field'):
            pipeline_data["playblast"] = self.pb_get_settings_dict()

        for i in range(self.lod_list.count()):
            lod_item = self.lod_list.item(i); lod_name = lod_item.text()
            brush = lod_item.foreground()
            lod_color = brush.color().name() if brush.style() != QtCore.Qt.NoBrush else "#2bb5a8"
            page = self.lod_stack.widget(i); container = page.panels_container

            seq = []
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if panel.p_type == "MODULE":
                    mods = [{"path": self.relativize_path(panel.bubble_layout.itemAt(b).widget().full_path), "active": panel.bubble_layout.itemAt(b).widget().is_active} for b in range(panel.bubble_layout.count())]
                    seq.append({"title": panel.title_edit.text(), "type": "MODULE", "modules": mods, "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False})
                elif panel.p_type == "LOD_LOADER":
                    seq.append({"title": panel.title_edit.text(), "type": "LOD_LOADER", "lod_names": panel.checked_lod_names(), "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', '')})
                else:
                    data = {"title": panel.title_edit.text(), "type": panel.p_type, "path": self.relativize_path(panel.field.text()), "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False}
                    if panel.p_type == "SHAPES": data["pattern"] = panel.pattern_field.text()
                    if panel.p_type == "JSON":
                        data["meshes"] = panel.mesh_field.text()
                        data["joints"] = panel.joints_field.text()
                        data["reskin_control"] = panel.reskin_ctl_field.text()
                        data["reskin_scale"] = panel.reskin_scale_field.text()
                        if hasattr(panel, 'chk_naming_popup'): data["naming_popup"] = panel.chk_naming_popup.isChecked()
                    if panel.p_type == "MATERIAL": data["meshes"] = panel.mesh_field.text()
                    if panel.p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ") and hasattr(panel, 'func_field'):
                        data["func_call"] = panel.func_field.text()
                    if panel.p_type == "TWEAKER":
                        data["groups"] = panel.get_tweaker_groups_data()
                        data["meshes"] = panel.mesh_field.text()
                        data["joints"] = panel.joints_field.text()
                        if hasattr(panel, 'chk_naming_popup'): data["naming_popup"] = panel.chk_naming_popup.isChecked()
                    if panel.p_type == "NOTE" and hasattr(panel, 'note_edit'):
                        data["note_text"] = panel.note_edit.toPlainText()
                        data["note_text_color"] = panel.note_text_color
                        data["note_bg_color"] = panel.note_bg_color
                        data["note_font_size"] = panel.note_font_size
                        data["note_height"] = panel.note_height
                    if panel.p_type == "IMPORT_LOD" and hasattr(panel, 'asset_name_field'):
                        data["asset_name"] = panel.asset_name_field.text()
                    if panel.p_type in ("DELETE_OBJ", "ZERO_OUT", "INSTANCE_OBJ") and hasattr(panel, 'target_field'):
                        data["target"] = panel.target_field.text()
                    if panel.p_type == "PARENT_OBJ" and hasattr(panel, 'child_field'):
                        data["child"] = panel.child_field.text()
                        data["parent"] = panel.parent_field.text()
                    seq.append(data)
            pipeline_data["lods"].append({"name": lod_name, "color": lod_color, "execution_sequence": seq})

        # Stage 28, request #3 / Stage 31, request #2: capture every node's
        # live guide state (hand-moved guide positions, and the mGear
        # Component Settings edited through the embedded settings UI) right
        # before saving, exactly as Save Guides/Export Config do - so this
        # KRT pipeline JSON remembers everything the guides JSON does, rather
        # than only the graph's structure. capture_all_live_state() is the
        # shared entry point all three writers go through so they can't drift
        # apart; the older positions-only method is kept as the fallback for
        # a graph widget that predates it.
        if hasattr(self.graph_widget, "capture_all_live_state"):
            self.graph_widget.capture_all_live_state()
        elif hasattr(self.graph_widget, "capture_all_guide_positions"):
            self.graph_widget.capture_all_guide_positions()

        # Node/wire serialization lives on graph_widget (serialize_node /
        # deserialize_node) so this full pipeline JSON and the standalone
        # Guide JSON (ModuleGraphWidget.save_all_guides/get_graph_config_data)
        # always agree on what a node needs to remember.
        graph_data = {
            "guide_path": self.graph_widget.path_field.text(),
            "nodes": [], "wires": [],
        }
        for item in self.graph_widget.graph_view.scene.items():
            if isinstance(item, RigNode):
                graph_data["nodes"].append(self.graph_widget.serialize_node(item))
            elif isinstance(item, RigWire):
                graph_data["wires"].append({"source": item.source.uuid, "dest": item.dest.uuid})
        # Stage 16, request #2: the rig-wide Guide Settings tab (Shifter
        # options + Custom Steps) now travels with the main pipeline JSON
        # too - it used to be captured only by the separate "Save Guides"/
        # "Export Config" JSON, so opening a pipeline JSON on its own left
        # this tab at whatever defaults happened to already be on screen.
        if hasattr(self.graph_widget, "guide_settings_panel"):
            graph_data["guide_settings"] = self.graph_widget.guide_settings_panel.get_settings_dict()
        pipeline_data["graph_data"] = graph_data
        if ayon_context: pipeline_data["ayon_publish_context"] = ayon_context
        return pipeline_data

    def get_publishable_files(self):
        seen  = set()
        paths = []
        FIELD_TYPES = {"SCRIPT", "GLOBAL_SCRIPT", "MA", "JSON", "SHAPES", "IMPORT_3D", "TWEAKER", "MATERIAL"}

        for lod_idx in range(self.lod_stack.count()):
            page      = self.lod_stack.widget(lod_idx)
            container = page.panels_container

            for panel_idx in range(container.layout.count()):
                panel  = container.layout.itemAt(panel_idx).widget()
                p_type = getattr(panel, 'p_type', None)

                if p_type in FIELD_TYPES:
                    path = self.resolve_path(panel.field.text()).strip().replace("\\", "/")
                    if path and os.path.isfile(path) and path not in seen:
                        seen.add(path); paths.append(path)

                elif p_type == "MODULE":
                    bubble_layout = getattr(panel, 'bubble_layout', None)
                    if bubble_layout:
                        for b in range(bubble_layout.count()):
                            bubble = bubble_layout.itemAt(b).widget()
                            if bubble is None: continue
                            bp = getattr(bubble, 'full_path', None)
                            if bp:
                                bp = bp.strip().replace("\\", "/")
                                if bp and os.path.isfile(bp) and bp not in seen:
                                    seen.add(bp); paths.append(bp)
        return paths

    def perform_autosave(self):
        if not self.session_manager.data.get("auto_save_enabled", True): return
        if self.lod_list.count() == 0 and not [i for i in self.graph_widget.graph_view.scene.items() if isinstance(i, RigNode)]: return
        data = self.get_current_pipeline_data()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.session_manager.autosave_dir, f"autosave_{id(self)}_{timestamp}.json").replace("\\", "/")
        try:
            with open(filepath, 'w') as f: json.dump(data, f, indent=4)
            self.session_manager.add_autosave(filepath)
            self.main_window.refresh_all_session_lists()
        except Exception: pass

    def get_current_publish_dir(self):
        """Return the directory set in the current LOD's PUBLISH PATH panel.
        Prefers an active PUBLISH panel; falls back to any PUBLISH panel."""
        container = self.get_current_lod_container()
        if not container: return ""
        fallback = ""
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if getattr(panel, 'p_type', '') == "PUBLISH":
                p = self.resolve_path(panel.field.text()).strip()
                if p:
                    if getattr(panel, 'is_active', True):
                        return p
                    if not fallback:
                        fallback = p
        return fallback

    def browse_pipeline_json(self):
        # Open the load dialog at the PUBLISH PATH panel's directory so the user
        # lands where their published pipeline JSONs live, instead of a default.
        kwargs = {'fm': 1, 'ff': "JSON (*.json)", 'caption': "Load Pipeline JSON"}
        start_dir = self.get_current_publish_dir()
        if start_dir:
            start_dir = start_dir.replace("\\", "/")
            if os.path.isdir(start_dir):
                kwargs['dir'] = start_dir
            elif os.path.isfile(start_dir):
                kwargs['dir'] = os.path.dirname(start_dir)
        res = cmds.fileDialog2(**kwargs)
        if not res: return
        self.load_pipeline_from_file(res[0])
        
    def load_pipeline_from_file(self, file_path):
        try:
            with open(file_path, 'r') as f: data = json.load(f)
            if "rig_name" in data and hasattr(self, 'edit_rig_name'): self.edit_rig_name.setText(data["rig_name"])
            self.pipeline_comment = data.get("comment", "")
            self.refresh_comment_view()
            # Stage 41: root first, so relative paths in the panels below
            # resolve from the moment they appear. Existing paths are NOT
            # rewritten here (they come in from the file as saved).
            self._pending_legacy_root = "root_path" not in data
            self.set_rig_root(data.get("root_path", ""), relativize_existing=False)

            # Stage 38, request #2: restore the Playblast tab's settings,
            # if this pipeline JSON has them (older files won't - the tab
            # just keeps whatever's already in the UI, same as every other
            # field here). See get_current_pipeline_data() for what's saved.
            pb_data = data.get("playblast")
            if pb_data and hasattr(self, 'pb_camera_field'):
                self.pb_apply_settings_dict(pb_data)
            lods = data.get("lods", [])
            if not lods and "execution_sequence" in data:
                lods = [{"name": "LOD0", "color": "#2bb5a8", "execution_sequence": data["execution_sequence"]}]
            graph_data = data.get("graph_data", {})
            if not lods and not graph_data: return
            
            if graph_data:
                self.graph_widget.graph_view.scene.clear()
                if hasattr(self.graph_widget, "_clear_undo_history"):
                    self.graph_widget._clear_undo_history()
                # Stage 35, Rule 3: the Guide Path field gets pointed at
                # graph_data["guide_path"] down in set_session_path() below,
                # not set here - that's the EXACT graph JSON version this
                # pipeline JSON was saved together with (Rule 2 guarantees a
                # real file exists there, written the moment this pipeline
                # JSON itself was saved), so loading this KRT json restores
                # that same graph version, not just whichever file happens
                # to be this pipeline JSON's own path.
                uuid_to_node = {}
                for nd in graph_data.get("nodes", []):
                    node = self.graph_widget.deserialize_node(nd)
                    self.graph_widget.graph_view.scene.addItem(node); uuid_to_node[node.uuid] = node
                for wd in graph_data.get("wires", []):
                    src = uuid_to_node.get(wd["source"]); dst = uuid_to_node.get(wd["dest"])
                    if src and dst: wire = RigWire(src, dst); self.graph_widget.graph_view.scene.addItem(wire)
                # Stage 16, request #2: restore the rig-wide Guide Settings
                # tab too, if this pipeline JSON has one (older files won't -
                # they just keep whatever's already in the UI, same as
                # before). Safe to call with no live scene guide yet -
                # apply_settings_dict() just loads the UI fields in that
                # case and warns (not a popup) instead of erroring.
                if "guide_settings" in graph_data and hasattr(self.graph_widget, "guide_settings_panel"):
                    self.graph_widget.guide_settings_panel.apply_settings_dict(graph_data["guide_settings"])
                self.refresh_module_list()

            if lods:
                self.clear_all_panels()
                # LOD Loader panels reference other LODs by name - some of
                # those LODs may not exist yet at the point their panel is
                # created (a panel can reference a LOD defined later in this
                # same file), so collect (panel, names) pairs and apply the
                # checked set only after every LOD in the file has been
                # created below.
                pending_lod_loaders = []
                for lod_data in lods:
                    color = lod_data.get("color", "#2bb5a8")
                    page = self.create_lod_workspace(lod_data.get("name", "LOD"), set_active=False, color=color, seed_defaults=False)
                    self.lod_stack.setCurrentWidget(page)
                    for item in lod_data.get("execution_sequence", []):
                        p_type = item.get("type"); is_act = item.get("active", True)
                        # Stage 18: MA and IMPORT_3D were merged into one
                        # auto-detecting panel type. Older pipeline JSONs may
                        # still have panels saved with the old "MA" type -
                        # normalize them on load so they come back as the
                        # current, single 3D-import panel instead of an
                        # unrecognized/orphaned type.
                        if p_type == "MA":
                            p_type = "IMPORT_3D"
                        if p_type == "MODULE":
                            pan = self.add_module_panel(item.get("title", "LOAD MODULE SCRIPTS"))
                            pan.bg_color = item.get("bg_color", "#252526")
                            pan.update_style()
                            for m in item.get("modules", []):
                                if isinstance(m, dict): pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
                                else: pan.add_module_bubble(pre_path=m)
                            # Belt-and-suspenders on top of FlowLayout.addItem's
                            # own fix: force one synchronous relayout now that
                            # every bubble for this panel is in, rather than
                            # relying on Qt to get around to the deferred
                            # LayoutRequest on its own. This page is very
                            # possibly not even the visible LOD tab yet while a
                            # pipeline JSON is loading, so don't wait on a
                            # resize/show event that might not come until the
                            # user switches to it - this was the actual bug
                            # behind "only one module bubble visible until
                            # LOAD is pressed" (pressing LOAD just happened to
                            # force an unrelated relayout).
                            pan.bubble_layout.activate()
                            if not is_act: pan.checkbox.setChecked(False)
                            if item.get("uuid"): pan.uuid = item.get("uuid")
                            if hasattr(pan, 'set_cache_marked'): pan.set_cache_marked(item.get("cache_enabled", False))
                            pan.refresh_cache_ui()
                        elif p_type == "LOD_LOADER":
                            pan = self.add_lod_loader_panel(item.get("title", "LOD LOADER"))
                            if pan is None: continue
                            pan.bg_color = item.get("bg_color", "#252526")
                            pan.update_style()
                            if not is_act: pan.checkbox.setChecked(False)
                            if item.get("uuid"): pan.uuid = item.get("uuid")
                            pending_lod_loaders.append((pan, item.get("lod_names", [])))
                        else:
                            pan = self.add_panel(item.get("title", "LOAD SCRIPT"), p_type, item.get("path", ""))
                            pan.bg_color = item.get("bg_color", "#252526")
                            pan.update_style()
                            if not is_act: pan.checkbox.setChecked(False)
                            if p_type == "JSON":
                                if item.get("meshes"): pan.mesh_field.setText(item.get("meshes"))
                                if item.get("joints"): pan.joints_field.setText(item.get("joints"))
                                if item.get("reskin_control"): pan.reskin_ctl_field.setText(item.get("reskin_control"))
                                if item.get("reskin_scale"): pan.reskin_scale_field.setText(item.get("reskin_scale"))
                                if "naming_popup" in item and hasattr(pan, 'chk_naming_popup'):
                                    pan.chk_naming_popup.setChecked(bool(item.get("naming_popup")))
                            if p_type == "MATERIAL" and item.get("meshes"): pan.mesh_field.setText(item.get("meshes"))
                            if p_type == "SHAPES" and item.get("pattern"): pan.pattern_field.setText(item.get("pattern"))
                            if p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ") and item.get("func_call") and hasattr(pan, 'func_field'):
                                pan.func_field.setText(item.get("func_call"))
                            if p_type == "TWEAKER":
                                pan.load_tweaker_groups_data(item.get("groups"), legacy_item=item)
                                if item.get("meshes"): pan.mesh_field.setText(item.get("meshes"))
                                if item.get("joints"): pan.joints_field.setText(item.get("joints"))
                                if "naming_popup" in item and hasattr(pan, 'chk_naming_popup'):
                                    pan.chk_naming_popup.setChecked(bool(item.get("naming_popup")))
                            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                                if item.get("note_text"): pan.note_edit.setPlainText(item.get("note_text"))
                                pan.note_text_color = item.get("note_text_color", pan.note_text_color)
                                pan.note_bg_color = item.get("note_bg_color", pan.note_bg_color)
                                pan.note_font_size = item.get("note_font_size", pan.note_font_size)
                                pan.note_height = item.get("note_height", pan.note_height)
                                pan.note_edit.setFixedHeight(pan.note_height)
                                pan._apply_note_style()
                            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                                if item.get("asset_name"): pan.asset_name_field.setText(item.get("asset_name"))
                            if p_type in ("DELETE_OBJ", "ZERO_OUT", "INSTANCE_OBJ") and hasattr(pan, 'target_field'):
                                if item.get("target"): pan.target_field.setText(item.get("target"))
                            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                                if item.get("child"): pan.child_field.setText(item.get("child"))
                                if item.get("parent"): pan.parent_field.setText(item.get("parent"))
                            if item.get("uuid"): pan.uuid = item.get("uuid")
                            if hasattr(pan, 'set_cache_marked'): pan.set_cache_marked(item.get("cache_enabled", False))
                            pan.refresh_cache_ui()
                # Now that every LOD in this file exists, sync each LOD
                # Loader panel's list (adds all LODs, keeps only the ones
                # actually saved as checked) and restore its checked set.
                for pan, names in pending_lod_loaders:
                    pan.sync_from_lod_manager()
                    pan.set_checked_lod_names(names)
                if self.lod_list.count() > 0: self.lod_list.setCurrentRow(0)

            # Stage 41: a JSON saved before Rig Root existed has only absolute
            # paths - adopt the PUBLISH folder as root and shorten on screen.
            # Nothing is written to disk until the user saves.
            if getattr(self, "_pending_legacy_root", False) and not self.rig_root():
                inferred = self.infer_rig_root_from_panels()
                if inferred:
                    cmds.warning(f"[KRT] No root_path in this pipeline JSON - using PUBLISH folder as Rig Root: {inferred}")
                    self.set_rig_root(inferred, relativize_existing=True)
            self._pending_legacy_root = False

            saved_guide_path = graph_data.get("guide_path") or None
            self.set_session_path(file_path, guide_path=saved_guide_path, refresh_guide_default=(saved_guide_path is None))
            self.session_manager.add_recent(file_path); self.main_window.refresh_all_session_lists()
        except Exception: traceback.print_exc()

    def populate_pipeline_versions_menu(self, switch_menu):
        """Same sibling-file scan widgets.py's SortablePanel.populate_versions_menu
        / graph.py's _populate_guide_versions_menu use for a panel's own
        "Switch Version" - just scoped to the whole loaded pipeline JSON
        (self.session_path) instead of one panel's field. Lists every
        "<base>_vNNN.json" (and the bare "<base>.json", if present)
        sibling of the currently loaded file, so e.g. loading
        ganesh_a_Rig_v084.json also offers v083, v082, ... alongside it."""
        v_actions = {}
        base_path = self.session_path
        if not base_path:
            switch_menu.setEnabled(False)
            return v_actions

        dir_name = os.path.dirname(base_path)
        if not os.path.isdir(dir_name):
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
                label = f"● {v_name}" if v == base_path else v_name
                v_actions[switch_menu.addAction(label)] = v

        return v_actions

    def _save_pipeline_assets(self, save_maya=True, save_json=True, dialog_title="Save All"):
        """Shared logic behind the Rig Build workspace's three save buttons
        (Stage 34: Save Maya File / Save All / Save JSON File used to be one
        SAVE ALL button that always did both). Finds the active Publish
        Path, prompts once for a save comment, then does whichever of the
        Maya-file save / pipeline-JSON save was asked for.

        Returns the (ma_path, json_path) actually written (either may be
        None), or None if the save was aborted (no Publish Path, cancelled
        comment dialog, or the Maya file failed to save)."""
        publish_dir = None
        container = self.get_current_lod_container()
        if container:
            for i in range(container.layout.count()):
                panel = container.layout.itemAt(i).widget()
                if hasattr(panel, 'p_type') and panel.p_type == "PUBLISH" and panel.is_active:
                    publish_dir = self.resolve_path(panel.field.text()); break
        if not publish_dir or not os.path.exists(publish_dir):
            cmds.warning("[KRT] {}: no valid PUBLISH directory set.".format(dialog_title))
            return None

        # Ask for a comment for this save (pre-filled with the last one),
        # and whether to overwrite the current latest version instead of
        # saving a new one.
        from .dialogs import SaveCommentDialog
        from .compat import IS_PYSIDE6
        dlg = SaveCommentDialog(self, dialog_title, getattr(self, 'pipeline_comment', ""))
        result = dlg.exec() if IS_PYSIDE6 else dlg.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return None
        text, overwrite = dlg.result_values()
        self.pipeline_comment = text
        self.refresh_comment_view()

        rig_name = self.edit_rig_name.text().strip() or "Unnamed_Rig"
        from .utils import get_versioned_path

        ma_path = None
        if save_maya:
            ma_path_base = os.path.join(publish_dir, f"{rig_name}.ma").replace("\\", "/")
            ma_path = get_versioned_path(ma_path_base, get_latest=overwrite)
            try:
                cmds.file(rename=ma_path)
                cmds.file(save=True, type="mayaAscii")
            except Exception:
                cmds.warning("[KRT] {}: failed to save the Maya file.".format(dialog_title))
                return None

        json_path = None
        if save_json:
            pipeline_data = self.get_current_pipeline_data()
            json_path_base = os.path.join(publish_dir, f"{rig_name}.json").replace("\\", "/")
            json_path = get_versioned_path(json_path_base, get_latest=overwrite)
            with open(json_path, 'w') as f: json.dump(pipeline_data, f, indent=4)
            # Stage 35, Rule 2: keep the standalone graph/guide JSON in sync
            # with this KRT pipeline JSON save - re-write it to its CURRENT
            # version (overwrite=True; this never bumps the version, that's
            # Rule 1's "Save Guide (New Version)" menu action) so the exact
            # file this pipeline JSON's own embedded graph_data["guide_path"]
            # points at always exists on disk, matching what was just saved.
            if hasattr(self.graph_widget, "save_all_guides"):
                self.graph_widget.save_all_guides(overwrite=True)
            self.set_session_path(json_path)
            self.session_manager.add_published(json_path)
            self.main_window.refresh_all_session_lists()

        if json_path:
            cmds.warning(f"Successfully published: {json_path}")
        elif ma_path:
            cmds.warning(f"Successfully saved Maya file: {ma_path}")
        return ma_path, json_path

    def save_maya_file_logic(self):
        """SAVE MAYA FILE button - saves only a new versioned .ma. No
        pipeline JSON is written, so the current session's JSON path/version
        is untouched."""
        self._save_pipeline_assets(save_maya=True, save_json=False, dialog_title="Save Maya File")

    def save_json_file_logic(self):
        """SAVE JSON FILE button - saves only a new versioned pipeline JSON.
        No .ma is written, so the Maya scene on disk is untouched."""
        self._save_pipeline_assets(save_maya=False, save_json=True, dialog_title="Save JSON File")

    def publish_asset_logic(self):
        """SAVE ALL button - saves both the Maya file and the pipeline JSON
        (the original, unsplit SAVE ALL behavior)."""
        self._save_pipeline_assets(save_maya=True, save_json=True, dialog_title="Save All")
