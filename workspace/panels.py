"""SessionWorkspace - panels methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspacePanelsMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    def add_panel(self, title, p_type, default_val, index=-1):
        container = self.get_current_lod_container()
        if not container: return None
        panel = SortablePanel(title, p_type, default_val, self)
        if index == -1: container.layout.addWidget(panel)
        else: container.layout.insertWidget(index, panel)
        return panel

    def add_module_panel(self, title, index=-1):
        container = self.get_current_lod_container()
        if not container: return None
        panel = SortableBubblePanel(title, self)
        if index == -1: container.layout.addWidget(panel)
        else: container.layout.insertWidget(index, panel)
        return panel

    def duplicate_panel(self, panel):
        """Duplicate any panel in the current LOD, fully replicating its contents.
        Works for every panel type: MODULE bubble panels copy their bubbles,
        SHAPES/JSON/SCRIPT panels copy their extra fields, and the active +
        cache-tick states are carried over as well."""
        container = self.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(panel)
        if idx < 0: idx = container.layout.count() - 1

        p_type = getattr(panel, 'p_type', '')
        new_title = panel.title_edit.text() + " (Copy)"
        new_pan = None

        if p_type == "MODULE":
            new_pan = self.add_module_panel(new_title, idx + 1)
            if new_pan is None: return
            new_pan.bg_color = getattr(panel, 'bg_color', '#252526')
            new_pan.update_style()
            # Replicate every module bubble (path + active state).
            for b in range(panel.bubble_layout.count()):
                bubble = panel.bubble_layout.itemAt(b).widget()
                if bubble is None: continue
                new_pan.add_module_bubble(pre_path=bubble.full_path, is_active=bubble.is_active)
        elif p_type == "LOD_LOADER":
            new_pan = self.add_lod_loader_panel(new_title, idx + 1)
            if new_pan is None: return
            new_pan.bg_color = getattr(panel, 'bg_color', '#252526')
            new_pan.update_style()
            # Replicate the checked LOD-name set from the source panel.
            checked = panel.checked_lod_names() if hasattr(panel, 'checked_lod_names') else []
            new_pan.set_checked_lod_names(checked)
        else:
            new_pan = self.add_panel(new_title, p_type, panel.field.text(), idx + 1)
            if new_pan is None: return
            new_pan.bg_color = getattr(panel, 'bg_color', '#252526')
            new_pan.update_style()
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and hasattr(new_pan, 'func_field') and hasattr(panel, 'func_field'):
                new_pan.func_field.setText(panel.func_field.text())
            if p_type == "JSON" and hasattr(new_pan, 'mesh_field') and hasattr(panel, 'mesh_field'):
                new_pan.mesh_field.setText(panel.mesh_field.text())
                if hasattr(new_pan, 'joints_field') and hasattr(panel, 'joints_field'):
                    new_pan.joints_field.setText(panel.joints_field.text())
                if hasattr(new_pan, 'reskin_ctl_field') and hasattr(panel, 'reskin_ctl_field'):
                    new_pan.reskin_ctl_field.setText(panel.reskin_ctl_field.text())
                    new_pan.reskin_scale_field.setText(panel.reskin_scale_field.text())
                if hasattr(new_pan, 'chk_naming_popup') and hasattr(panel, 'chk_naming_popup'):
                    new_pan.chk_naming_popup.setChecked(panel.chk_naming_popup.isChecked())
            if p_type == "SHAPES" and hasattr(new_pan, 'pattern_field') and hasattr(panel, 'pattern_field'):
                new_pan.pattern_field.setText(panel.pattern_field.text())
            if p_type == "MATERIAL" and hasattr(new_pan, 'mesh_field') and hasattr(panel, 'mesh_field'):
                new_pan.mesh_field.setText(panel.mesh_field.text())
            if p_type == "TWEAKER" and hasattr(new_pan, 'load_tweaker_groups_data') and hasattr(panel, 'get_tweaker_groups_data'):
                new_pan.load_tweaker_groups_data(panel.get_tweaker_groups_data())
                if hasattr(new_pan, 'mesh_field') and hasattr(panel, 'mesh_field'):
                    new_pan.mesh_field.setText(panel.mesh_field.text())
                if hasattr(new_pan, 'joints_field') and hasattr(panel, 'joints_field'):
                    new_pan.joints_field.setText(panel.joints_field.text())
                if hasattr(new_pan, 'chk_naming_popup') and hasattr(panel, 'chk_naming_popup'):
                    new_pan.chk_naming_popup.setChecked(panel.chk_naming_popup.isChecked())

        # Carry over cache-tick and enabled/disabled state for all panel types.
        if hasattr(panel, 'cache_marked') and hasattr(new_pan, 'set_cache_marked'):
            new_pan.set_cache_marked(panel.cache_marked())
        if hasattr(panel, 'is_active') and not panel.is_active:
            new_pan.checkbox.setChecked(False)

    def delete_panel(self, panel):
        container = self.get_current_lod_container()
        if not container: return
        # Stage 22, request #1: remember this panel (and exactly where it
        # was) before it's actually removed, so Undo can put it back.
        self._push_panel_undo(panel, container)
        container.layout.removeWidget(panel); panel.deleteLater()

    def _push_panel_undo(self, panel, container=None):
        """Snapshot a panel that's about to be deleted (via Delete Panel or
        Cut Panel) onto self.panel_undo_stack, so undo_last_panel_delete()
        can reconstruct it later in the same LOD and position."""
        if container is None:
            container = self.get_current_lod_container()
        if not container:
            return
        data = self.serialize_panel_data(panel)
        if data is None:
            return
        idx = container.layout.indexOf(panel)
        lod_row = self.lod_list.currentRow()
        self.panel_undo_stack.append({"lod_row": lod_row, "index": idx, "data": data})
        # Cap it so a long session doesn't grow this unbounded.
        self.panel_undo_stack = self.panel_undo_stack[-20:]

    def serialize_panel_data(self, panel):
        """Return this panel's contents as a plain dict, in the same shape
        the pipeline JSON uses for one execution_sequence item - shared by
        the panel-delete undo stack, and usable anywhere else a panel needs
        to be captured independent of the clipboard (Copy Panel writes to
        the clipboard directly instead, to avoid clobbering it on every
        delete)."""
        p_type = getattr(panel, 'p_type', None)
        if not p_type:
            return None
        data = {
            "title": panel.title_edit.text(), "type": p_type,
            "active": getattr(panel, 'is_active', True),
            "bg_color": getattr(panel, 'bg_color', '#252526'),
            "uuid": getattr(panel, 'uuid', ''),
            "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False,
        }
        if p_type == "MODULE":
            data["modules"] = [
                {"path": panel.bubble_layout.itemAt(b).widget().full_path,
                 "active": panel.bubble_layout.itemAt(b).widget().is_active}
                for b in range(panel.bubble_layout.count())]
        elif p_type == "LOD_LOADER":
            data["lod_names"] = panel.checked_lod_names() if hasattr(panel, 'checked_lod_names') else []
        else:
            data["path"] = panel.field.text() if hasattr(panel, 'field') else ""
            if hasattr(panel, 'chk_share_global'):
                data["share_global"] = panel.chk_share_global.isChecked()
            if p_type == "JSON":
                if hasattr(panel, 'mesh_field'): data["meshes"] = panel.mesh_field.text()
                if hasattr(panel, 'joints_field'): data["joints"] = panel.joints_field.text()
                if hasattr(panel, 'reskin_ctl_field'):
                    data["reskin_control"] = panel.reskin_ctl_field.text()
                    data["reskin_scale"] = panel.reskin_scale_field.text()
                if hasattr(panel, 'chk_naming_popup'): data["naming_popup"] = panel.chk_naming_popup.isChecked()
            if p_type == "SHAPES" and hasattr(panel, 'pattern_field'):
                data["pattern"] = panel.pattern_field.text()
            if p_type == "MATERIAL" and hasattr(panel, 'mesh_field'):
                data["meshes"] = panel.mesh_field.text()
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ") and hasattr(panel, 'func_field'):
                data["func_call"] = panel.func_field.text()
            if p_type == "TWEAKER" and hasattr(panel, 'get_tweaker_groups_data'):
                data["groups"] = panel.get_tweaker_groups_data()
                if hasattr(panel, 'mesh_field'): data["meshes"] = panel.mesh_field.text()
                if hasattr(panel, 'joints_field'): data["joints"] = panel.joints_field.text()
                if hasattr(panel, 'chk_naming_popup'): data["naming_popup"] = panel.chk_naming_popup.isChecked()
            if p_type == "IMPORT_LOD" and hasattr(panel, 'asset_name_field'):
                data["asset_name"] = panel.asset_name_field.text()
            if p_type in ("DELETE_OBJ", "ZERO_OUT", "INSTANCE_OBJ") and hasattr(panel, 'target_field'):
                data["target"] = panel.target_field.text()
            if p_type == "PARENT_OBJ" and hasattr(panel, 'child_field'):
                data["child"] = panel.child_field.text()
                data["parent"] = panel.parent_field.text()
        return data
        if hasattr(panel, "is_collapsed"):
            data["collapsed"] = panel.is_collapsed()

    def restore_panel_from_data(self, data, lod_row=None, index=-1):
        """Reconstruct a panel from serialize_panel_data()'s dict shape -
        used by undo_last_panel_delete() and available generally. Switches
        to `lod_row` first (if given and still valid) so the panel comes
        back in the same LOD it was removed from."""
        if not data:
            return None
        if lod_row is not None and 0 <= lod_row < self.lod_list.count():
            self.lod_list.setCurrentRow(lod_row)
        p_type = data.get("type")
        title = data.get("title", "Restored Panel")
        is_act = data.get("active", True)
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.add_module_panel(title, index=index)
            if pan is None: return None
            pan.bg_color = bg_col; pan.update_style()
            for m in data.get("modules", []):
                pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
        elif p_type == "LOD_LOADER":
            pan = self.add_lod_loader_panel(title, index=index)
            if pan is None: return None
            pan.bg_color = bg_col; pan.update_style()
            pan.set_checked_lod_names(data.get("lod_names", []))
        else:
            pan = self.add_panel(title, p_type, data.get("path", ""), index=index)
            if pan is None: return None
            pan.bg_color = bg_col; pan.update_style()
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "SHAPES" and data.get("pattern"):
                pan.pattern_field.setText(data.get("pattern"))
            if p_type == "MATERIAL" and data.get("meshes"):
                pan.mesh_field.setText(data.get("meshes"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ") and data.get("func_call") and hasattr(pan, 'func_field'):
                pan.func_field.setText(data.get("func_call"))
            if "share_global" in data and hasattr(pan, 'chk_share_global'):
                pan.chk_share_global.setChecked(bool(data.get("share_global")))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field') and data.get("asset_name"):
                pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT", "INSTANCE_OBJ") and hasattr(pan, 'target_field') and data.get("target"):
                pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))

        if not is_act: pan.checkbox.setChecked(False)
        if data.get("uuid"): pan.uuid = data.get("uuid")
        if hasattr(pan, 'set_cache_marked'): pan.set_cache_marked(data.get("cache_enabled", False))
        if hasattr(pan, 'refresh_cache_ui'): pan.refresh_cache_ui()
        return pan
        if data.get("collapsed") and hasattr(pan, "set_collapsed"):
            pan.set_collapsed(True)

    def undo_last_panel_delete(self):
        """The "↩ Undo" panel-menu action - pops the most recently
        deleted/cut panel off panel_undo_stack and puts it back where it
        was (same LOD, same position)."""
        if not self.panel_undo_stack:
            cmds.warning("Nothing to undo.")
            return
        entry = self.panel_undo_stack.pop()
        pan = self.restore_panel_from_data(entry.get("data"), lod_row=entry.get("lod_row"), index=entry.get("index", -1))
        if pan:
            cmds.warning("Undo: restored panel '{}'.".format(entry.get("data", {}).get("title", "")))
