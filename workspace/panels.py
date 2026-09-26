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

        if hasattr(panel, "extra_data") and hasattr(new_pan, "apply_extra_data"):
            new_pan.apply_extra_data(panel.extra_data())     # Stage 55 generic hook
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
        if hasattr(panel, "is_collapsed"):
            data["collapsed"] = panel.is_collapsed()
        if hasattr(panel, "extra_data"):          # Stage 55 generic hook
            data.update(panel.extra_data())
        return data

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
        if hasattr(pan, "apply_extra_data"):      # Stage 55 generic hook
            pan.apply_extra_data(data)
        if data.get("collapsed") and hasattr(pan, "set_collapsed"):
            pan.set_collapsed(True)
        return pan

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

    # ------------------------------------------------------------------
    # Stage 53: multi-panel selection + copy / cut / paste
    # ------------------------------------------------------------------
    # The selection is a plain list of panel objects kept on the workspace.
    # Panels are only drawn differently (SelectableMixin._border_css); the
    # ORDER used for copying always comes from the LOD's layout, so copied
    # panels paste back in build order no matter which order you clicked.

    def _panel_sel(self):
        if not hasattr(self, "_selected_panels"):
            self._selected_panels = []
        return self._selected_panels

    def _alive(self, panel):
        try:
            panel.objectName()      # raises RuntimeError once Qt deleted it
            return True
        except RuntimeError:
            return False

    def _container_panels(self, container=None):
        """Every panel in the (current) LOD, in layout = build order."""
        container = container or self.get_current_lod_container()
        if not container:
            return []
        out = []
        for i in range(container.layout.count()):
            w = container.layout.itemAt(i).widget()
            if w is not None and hasattr(w, "clipboard_data"):
                out.append(w)
        return out

    def selected_panels(self):
        order = self._container_panels()
        sel = [p for p in self._panel_sel() if self._alive(p)]
        return [p for p in order if p in sel]

    def clear_panel_selection(self):
        for p in self._panel_sel():
            if self._alive(p):
                p.set_selected(False)
        self._selected_panels = []

    def _select(self, panels):
        for p in panels:
            if p not in self._panel_sel():
                self._panel_sel().append(p)
            p.set_selected(True)

    def on_panel_clicked(self, panel, modifiers):
        """Plain click = select only this one (click again to deselect),
        Ctrl+click = add/remove, Shift+click = range from the last click."""
        from ..widgets.selection import _has_mod
        ctrl = _has_mod(modifiers, QtCore.Qt.ControlModifier)
        shift = _has_mod(modifiers, QtCore.Qt.ShiftModifier)
        sel = self._panel_sel()
        anchor = getattr(self, "_selection_anchor", None)

        if shift and anchor is not None and self._alive(anchor):
            order = self._container_panels()
            if anchor in order and panel in order:
                a, b = sorted((order.index(anchor), order.index(panel)))
                self._select(order[a:b + 1])
        elif ctrl:
            if panel in sel:
                sel.remove(panel)
                panel.set_selected(False)
            else:
                self._select([panel])
            self._selection_anchor = panel
        else:
            only_this = (sel == [panel])
            self.clear_panel_selection()
            if not only_this:
                self._select([panel])
            self._selection_anchor = panel

        # Give the panel keyboard focus so Ctrl+C / Ctrl+V reach it.
        panel.setFocusPolicy(QtCore.Qt.ClickFocus)
        panel.setFocus()

    def _panels_to_act_on(self, source):
        """The whole selection if `source` is part of it, else just `source`."""
        sel = self.selected_panels()
        if source in sel and len(sel) > 1:
            return sel
        return [source]

    def _clipboard_list(self):
        data = getattr(self.main_window, "clipboard_panel_data", None)
        if not data:
            return []
        if isinstance(data, dict):      # a single-panel copy from before Stage 53
            return [data]
        return list(data)

    def panel_copy_label(self, source, verb):
        n = len(self._panels_to_act_on(source))
        return "{} Panel".format(verb) if n == 1 else "{} {} Selected Panels".format(verb, n)

    def panel_paste_label(self, where):
        n = len(self._clipboard_list())
        what = "Panel" if n <= 1 else "{} Panels".format(n)
        return "📋 Paste {} ({})".format(what, where)

    def copy_panels(self, source):
        panels = self._panels_to_act_on(source)
        # A LIST on the shared main-window clipboard, so it can be pasted
        # into another LOD or another session tab.
        self.main_window.clipboard_panel_data = [p.clipboard_data() for p in panels]
        cmds.warning("[KRT] Copied {} panel(s): {}".format(
            len(panels), ", ".join(p.title_edit.text() for p in panels)))
        return panels

    def cut_panels(self, source):
        panels = self.copy_panels(source)
        self.clear_panel_selection()
        for p in panels:
            # LOD Loader panels disconnect their signals first.
            if hasattr(p, "_on_delete_clicked"):
                p._on_delete_clicked()
            else:
                self.delete_panel(p)

    def paste_panels_at(self, anchor, offset):
        """offset 0 = above `anchor`, 1 = below it."""
        container = self.get_current_lod_container()
        if not container:
            return []
        idx = container.layout.indexOf(anchor)
        idx = -1 if idx < 0 else idx + offset
        return self._paste_clipboard(idx)

    def paste_panels_below_selection(self):
        """Ctrl+V: below the last selected panel, else at the end of the LOD."""
        sel = self.selected_panels()
        if sel:
            return self.paste_panels_at(sel[-1], 1)
        return self._paste_clipboard(-1)

    def _paste_clipboard(self, idx):
        items = self._clipboard_list()
        if not items:
            cmds.warning("[KRT] Nothing to paste - copy a panel first.")
            return []
        new = []
        for i, data in enumerate(items):
            pan = self._paste_one(data, -1 if idx < 0 else idx + i)
            if pan is not None:
                new.append(pan)
        # The pasted panels become the selection, ready to move/copy again.
        self.clear_panel_selection()
        self._select(new)
        cmds.warning("[KRT] Pasted {} panel(s).".format(len(new)))
        return new

    def _paste_one(self, data, idx):
        """Create ONE panel from a clipboard dict at layout index `idx`
        (-1 = end). Was copy-pasted into all three panel classes before."""
        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.add_module_panel(title, index=idx)
            if pan is None: return None
            for m in data.get("modules", []):
                # relativize against THIS tab's root: same rig -> short path
                # again; different rig -> stays absolute and still resolves.
                pan.add_module_bubble(pre_path=self.relativize_path(m.get("path")),
                                      is_active=m.get("active", True))
        elif p_type == "LOD_LOADER":
            pan = self.add_lod_loader_panel(title, index=idx)
            if pan is None: return None
            pan.set_checked_lod_names(data.get("lod_names", []))
        else:
            pan = self.add_panel(title, p_type, self.relativize_path(data.get("path", "")), index=idx)
            if pan is None: return None
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ") and data.get("func_call") and hasattr(pan, "func_field"):
                pan.func_field.setText(data.get("func_call"))
            if "share_global" in data and hasattr(pan, "chk_share_global"):
                pan.chk_share_global.setChecked(bool(data.get("share_global")))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
            if "naming_popup" in data and hasattr(pan, "chk_naming_popup"):
                pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, "note_edit"):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, "asset_name_field") and data.get("asset_name"):
                pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT", "INSTANCE_OBJ") and hasattr(pan, "target_field") and data.get("target"):
                pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, "child_field"):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))

        pan.bg_color = bg_col
        pan.update_style()
        if not is_act: pan.checkbox.setChecked(False)
        if hasattr(pan, "set_cache_marked"): pan.set_cache_marked(data.get("cache_enabled", False))
        if hasattr(pan, "apply_extra_data"):      # Stage 55 generic hook
            pan.apply_extra_data(data)
        # A collapsed panel pastes collapsed - the flag travels with it.
        if data.get("collapsed") and hasattr(pan, "set_collapsed"):
            pan.set_collapsed(True)
        return pan
