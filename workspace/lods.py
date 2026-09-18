"""SessionWorkspace - lods methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspaceLodsMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    def change_selected_lod_color(self, item=None):
        if not item:
            item = self.lod_list.currentItem()
        if not item: 
            cmds.warning("Please select an LOD first to change its color.")
            return
            
        current_color = item.foreground().color()
        if not current_color.isValid(): current_color = QtGui.QColor("#2bb5a8")
        
        color = QtWidgets.QColorDialog.getColor(current_color, self, "Choose LOD Color")
        if color.isValid():
            item.setForeground(color)
            self.lod_list.clearSelection()
            item.setSelected(True)

    def show_lod_context_menu(self, pos):
        item = self.lod_list.itemAt(pos)
        if not item: return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        a_color = menu.addAction("🎨 Change Color")
        a_del = menu.addAction("❌ Delete LOD")
        
        action = menu.exec(self.lod_list.mapToGlobal(pos)) if IS_PYSIDE6 else menu.exec_(self.lod_list.mapToGlobal(pos))
        
        if action == a_color:
            self.change_selected_lod_color(item)
        elif action == a_del:
            self.delete_selected_lod(item)

    def delete_current_lod_shortcut(self):
        item = self.lod_list.currentItem()
        if item: self.delete_selected_lod(item)

    def delete_selected_lod(self, item):
        if self.lod_list.count() <= 1:
            cmds.warning("Cannot delete the last LOD workspace.")
            return
            
        res = cmds.confirmDialog(
            title='Delete LOD', message=f"Are you sure you want to delete '{item.text()}' and all its panels?",
            button=['Yes', 'Cancel'], defaultButton='Cancel', cancelButton='Cancel', dismissString='Cancel'
        )
        if res == 'Yes':
            row = self.lod_list.row(item)
            page = self.lod_stack.widget(row)
            self.lod_stack.removeWidget(page)
            page.deleteLater()
            self.lod_list.takeItem(row)

    def create_lod_workspace(self, name="LOD0", set_active=True, color="#2bb5a8", seed_defaults=True):
        item = QtWidgets.QListWidgetItem(name)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        font = item.font(); font.setPointSize(16); font.setBold(False); item.setFont(font)
        item.setForeground(QtGui.QColor(color)); item.setSizeHint(QtCore.QSize(0, 35))
        self.lod_list.addItem(item)

        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0,0,0,0)
        
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_content = QtWidgets.QWidget(); rig_vbox = QtWidgets.QVBoxLayout(scroll_content); rig_vbox.setContentsMargins(20, 10, 20, 20)
        
        panels_container = DragDropContainer(self)
        rig_vbox.addWidget(panels_container)

        btn_add_panel = QtWidgets.QPushButton("➕ Add New Panel to this LOD")
        btn_add_panel.setStyleSheet("background-color: #3e3e42; padding: 10px; font-weight: bold;")
        menu_add = QtWidgets.QMenu(self)
        menu_add.addAction("Add Python/MEL Script Panel", lambda: self.add_panel("CUSTOM SCRIPT", "SCRIPT", ""))
        menu_add.addAction("Add Default Script Panel (Maya Global)", lambda: self.add_panel("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", ""))
        menu_add.addAction("Add Import 3D Model Panel (.ma/.mb/.fbx/.obj/.abc)", lambda: self.add_panel("IMPORT 3D MODEL", "IMPORT_3D", ""))
        menu_add.addAction("Add Module Bubbles Panel", lambda: self.add_module_panel("LOAD MODULE SCRIPTS"))
        menu_add.addAction("Add Skin JSON Panel", lambda: self.add_panel("CUSTOM SKIN JSON", "JSON", ""))
        menu_add.addAction("Add Control Shapes Panel", lambda: self.add_panel("CONTROL SHAPES", "SHAPES", ""))
        menu_add.addAction("Add Material Panel", lambda: self.add_panel("MATERIAL PANEL", "MATERIAL", ""))
        menu_add.addAction("Add Publish Path Panel", lambda: self.add_panel("PUBLISH PATH", "PUBLISH", ""))
        menu_add.addAction("Add Tweaker Panel", lambda: self.add_panel("TWEAKER SETUP", "TWEAKER", ""))
        menu_add.addAction("Add LOD Loader Panel (build entire LODs)", lambda: self.add_lod_loader_panel("LOD LOADER"))
        menu_add.addAction("Add Note Panel (free-text, not a build step)", lambda: self.add_panel("NOTE", "NOTE", ""))
        menu_add.addAction("Add Import 3D Model + LOD Organize", lambda: self.add_panel("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", ""))
        menu_add.addAction("Add Delete-by-Name Panel", lambda: self.add_panel("DELETE", "DELETE_OBJ", ""))
        menu_add.addAction("Add Zero Out Panel", lambda: self.add_panel("ZERO OUT", "ZERO_OUT", ""))
        menu_add.addAction("Add Parent Panel", lambda: self.add_panel("PARENT", "PARENT_OBJ", ""))
        btn_add_panel.setMenu(menu_add); rig_vbox.addWidget(btn_add_panel); rig_vbox.addStretch()

        scroll.setWidget(scroll_content); layout.addWidget(scroll)
        page.panels_container = panels_container
        self.lod_stack.addWidget(page)
        if set_active: self.lod_list.setCurrentItem(item); self.lod_stack.setCurrentWidget(page)

        # Stage 22, request #3: a brand-new LOD always starts with one
        # default GLOBAL_SCRIPT panel already in place - a normal panel
        # with the exact same functionality as any other GLOBAL_SCRIPT
        # panel (editable, deletable, etc.), it just doesn't start empty.
        # Skipped when reconstructing LODs from a loaded pipeline JSON
        # (load_pipeline_from_file passes seed_defaults=False) so loading
        # a file never injects a panel that wasn't actually saved in it,
        # and skipped by setup_default_panels() (which wipes and rebuilds
        # its own fixed panel set, including its own GLOBAL_SCRIPT entry).
        if seed_defaults:
            default_global = SortablePanel("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", "", self)
            panels_container.layout.addWidget(default_global)

        return page

    def get_current_lod_container(self):
        curr_widget = self.lod_stack.currentWidget()
        if curr_widget: return curr_widget.panels_container
        return None

    def on_lod_selection_changed(self):
        selected = self.lod_list.currentRow()
        if selected >= 0:
            self.lod_stack.setCurrentIndex(selected)
            # Re-apply the active search to the newly shown LOD.
            self.filter_panels()

    def filter_panels(self, text=None):
        """Show only the panels of the current LOD that match the search text.
        Matches against the panel title, its path field, its type, and (for
        module panels) every module bubble's name/path. Empty text shows all.
        Filtering is purely visual - the build still runs every panel."""
        if text is None:
            text = self.panel_search.text() if hasattr(self, 'panel_search') else ""
        q = (text or "").strip().lower()
        container = self.get_current_lod_container()
        if not container:
            return
        shown = 0
        total = 0
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if panel is None:
                continue
            total += 1
            if not q:
                panel.setVisible(True)
                shown += 1
                continue
            hay = [getattr(panel, 'p_type', '')]
            title_edit = getattr(panel, 'title_edit', None)
            if title_edit is not None:
                hay.append(title_edit.text())
            field = getattr(panel, 'field', None)
            if field is not None:
                hay.append(field.text())
            bl = getattr(panel, 'bubble_layout', None)
            if bl is not None:
                for b in range(bl.count()):
                    bub = bl.itemAt(b).widget()
                    if bub is not None:
                        hay.append(getattr(bub, 'text', '') or '')
                        hay.append(getattr(bub, 'full_path', '') or '')
            match = any(q in (h or '').lower() for h in hay)
            panel.setVisible(match)
            if match:
                shown += 1
        if hasattr(self, 'lbl_search_count'):
            self.lbl_search_count.setText("" if not q else f"{shown} / {total}")

    def setup_default_panels(self):
        container = self.get_current_lod_container()
        if not container: return
        while container.layout.count():
            item = container.layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.add_panel("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", "")
        self.add_panel("LOAD SCRIPT PANEL", "SCRIPT", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\Kleem_Rigging_Tool\scripts\Utils.py")
        self.add_panel("LOAD MODEL (3D file)", "IMPORT_3D", r"E:/Pipe_Storage/Vishal_workspace/All_Doc/My/script/My_Temp/hand_final.ma")
        self.add_module_panel("LOAD MODULE")
        self.add_panel("LOAD SKINCLUSTER", "JSON", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp\Hand2.jSkin")
        self.add_panel("CUSTOM SCRIPT", "SCRIPT", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\Kleem_Rigging_Tool\scripts\post_script.py")
        self.add_panel("CONTROL SHAPES", "SHAPES", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp\Shapes.json")
        self.add_panel("PUBLISH PATH", "PUBLISH", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp")

    def clear_all_panels(self):
        while self.lod_stack.count() > 0:
            widget = self.lod_stack.widget(0); self.lod_stack.removeWidget(widget); widget.deleteLater()
        self.lod_list.clear()

    # =====================================================
    # LOD Loader panel support (Stage 20): the LOD Build Manager is now a
    # proper panel type (LOD_LOADER, see widgets.LodLoaderPanel) addable
    # inside a LOD's own panel stack in the Rig Build Workspace, instead of
    # a fixed section in the Rigging Workspace tab. This section holds the
    # workspace-level helpers that panel instances call into.
    # =====================================================

    def _find_lod_row_by_name(self, name):
        for i in range(self.lod_list.count()):
            if self.lod_list.item(i).text() == name:
                return i
        return None

    def add_lod_loader_panel(self, title, index=-1):
        """Construct a widgets.LodLoaderPanel and insert it into the
        CURRENTLY SELECTED LOD's panel stack - the same way add_panel /
        add_module_panel insert other panel types. Returns the new panel."""
        container = self.get_current_lod_container()
        if not container:
            cmds.warning("Select or create a LOD first.")
            return None
        panel = LodLoaderPanel(title or "LOD LOADER", self)
        if index == -1: container.layout.addWidget(panel)
        else: container.layout.insertWidget(index, panel)
        panel.sync_from_lod_manager()
        return panel

    def build_lod_sequence(self, names):
        """Build each named LOD, in order, via run_full_build() - each one's
        own panel stack runs top to bottom exactly as BUILD CURRENT LOD
        would run it by hand. Stops on the first failure unless Ignore
        Errors is on. Returns (all_ok, message) for the calling panel to
        report.

        Stage 22, request #2: building necessarily has to select each LOD
        in turn (run_full_build() always builds "the currently selected
        LOD"), but the user should not end up LOOKING AT whichever LOD
        happened to build last just because they clicked LOAD - that kind
        of navigation should only ever happen when they deliberately click
        a LOD Loader bubble. So the sidebar selection in place before this
        started is restored once the whole sequence finishes (success,
        failure, or a stop partway through).

        Stage 24: a LOD Loader panel is itself just one ordinary step in
        its OWN LOD's panel stack, and is meant to run in that same
        position - a panel before it in that stack may have already built
        things into the current scene (this is exactly what "Build Till
        Here" reaching this panel looks like). run_full_build() used to
        always start each named LOD from a wiped, brand-new scene, which
        threw away everything the panels before this one had just built.
        Every LOD in `names` is now built with reset_scene=False - on top
        of whatever's already in the scene - so this panel behaves like
        any other panel and never "refreshes Maya" out from under an
        in-progress build."""
        orig_row = self.lod_list.currentRow()
        ignore = self.ignore_errors_enabled()
        built_ok = 0
        failed = []
        try:
            for name in names:
                idx = self._find_lod_row_by_name(name)
                if idx is None:
                    failed.append("{} (not found)".format(name))
                    if not ignore:
                        break
                    continue
                self.lod_list.setCurrentRow(idx)
                QtWidgets.QApplication.processEvents()
                ok = self.run_full_build(reset_scene=False)
                if ok:
                    built_ok += 1
                else:
                    failed.append(name)
                    if not ignore:
                        break
        finally:
            if 0 <= orig_row < self.lod_list.count():
                self.lod_list.setCurrentRow(orig_row)

        all_ok = not failed
        msg = "Built {}/{} LOD(s) successfully.".format(built_ok, len(names))
        if failed:
            msg += " Failed/skipped: {}".format(", ".join(failed))
        cmds.warning("[KRT] LOD Loader panel: {}/{} LOD(s) built successfully.".format(built_ok, len(names)))
        return all_ok, msg
