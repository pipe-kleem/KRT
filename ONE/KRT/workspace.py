import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om
import os
import json
import time
import traceback
import re
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from .dialogs import AdvancedSaveDialog, BuildProgressDialog
from .widgets import DragDropContainer, SortablePanel, SortableBubblePanel
from .graph import ModuleGraphWidget, RigNode, RigWire

class SessionWorkspace(QtWidgets.QWidget):
    def __init__(self, main_window):
        super(SessionWorkspace, self).__init__()
        self.main_window = main_window
        self.session_manager = main_window.session
        self.session_path = ""
        self.pipeline_comment = ""
        self.dragged_panel = None
        self._syncing_selection = False
        
        self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

        self.setup_ui()

    def set_session_path(self, path):
        self.session_path = path
        tab_index = self.main_window.session_stack.indexOf(self)
        tab_name = os.path.basename(path) if path else "Untitled Session"
        self.main_window.tab_bar.setTabText(tab_index, tab_name)

        if self.main_window.session_stack.currentIndex() == tab_index:
            self.main_window.session_path_field.setText(path)

        # Caches are stored per-JSON, so the current session's cache folder just
        # changed - re-evaluate every step's cached state against the new folder.
        self.refresh_all_cache_ui()

    def get_cache_dir(self):
        """The step-cache folder for the currently open pipeline JSON."""
        return self.session_manager.cache_dir_for(self.session_path)

    def setup_ui(self):
        self.layout_main = QtWidgets.QHBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        self.activity_bar = QtWidgets.QFrame()
        self.activity_bar.setFixedWidth(60)
        self.activity_bar.setStyleSheet("background-color: #333333;")
        act_layout = QtWidgets.QVBoxLayout(self.activity_bar)
        act_layout.setAlignment(QtCore.Qt.AlignTop)
        
        self.btn_file = self.create_nav_btn("📂", "File Session Options")
        self.btn_rig  = self.create_nav_btn("🛠️", "Rig Build Workspace")
        self.btn_node = self.create_nav_btn("🔌", "Module Graph Editor")
        self.btn_docs = self.create_nav_btn("📖", "Open Documentation")
        self.btn_prof = self.create_nav_btn("👤", "User Profile Settings")

        for b in [self.btn_file, self.btn_rig, self.btn_node, self.btn_docs]: act_layout.addWidget(b)
        act_layout.addStretch(); act_layout.addWidget(self.btn_prof)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setObjectName("SidebarFrame")
        side_layout = QtWidgets.QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0,0,0,0)
        
        self.sidebar_stack = QtWidgets.QStackedWidget()
        side_layout.addWidget(self.sidebar_stack)

        self.sidebar_empty = QtWidgets.QWidget()
        self.sidebar_stack.addWidget(self.sidebar_empty)

        self.sidebar_lods = QtWidgets.QWidget()
        lod_side_layout = QtWidgets.QVBoxLayout(self.sidebar_lods)
        lod_side_layout.addWidget(QtWidgets.QLabel("<b>LOD MANAGER</b>"))
        
        self.lod_list = QtWidgets.QListWidget()
        self.lod_list.setObjectName("LodList")
        self.lod_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.lod_list.itemSelectionChanged.connect(self.on_lod_selection_changed)
        
        self.lod_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.lod_list.customContextMenuRequested.connect(self.show_lod_context_menu)
        
        if IS_PYSIDE6: self.shortcut_del_lod = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.lod_list)
        else: self.shortcut_del_lod = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.lod_list)
        self.shortcut_del_lod.setContext(QtCore.Qt.WidgetShortcut)
        self.shortcut_del_lod.activated.connect(self.delete_current_lod_shortcut)
        
        btn_add_lod = QtWidgets.QPushButton("+ Add LOD")
        btn_add_lod.setStyleSheet("background-color: #3e3e42; font-weight: bold; padding: 5px;")
        btn_add_lod.clicked.connect(lambda: self.create_lod_workspace("New LOD"))
        
        btn_color_lod = QtWidgets.QPushButton("🎨 Color")
        btn_color_lod.setStyleSheet("background-color: #3e3e42; font-weight: bold; padding: 5px;")
        btn_color_lod.clicked.connect(lambda: self.change_selected_lod_color())

        lod_btn_layout = QtWidgets.QHBoxLayout()
        lod_btn_layout.setContentsMargins(0, 0, 0, 0)
        lod_btn_layout.addWidget(btn_add_lod)
        lod_btn_layout.addWidget(btn_color_lod)
        
        lod_side_layout.addWidget(self.lod_list)
        lod_side_layout.addLayout(lod_btn_layout)
        self.sidebar_stack.addWidget(self.sidebar_lods)

        self.sidebar_modules = QtWidgets.QWidget()
        mod_side_layout = QtWidgets.QVBoxLayout(self.sidebar_modules)
        mod_side_layout.addWidget(QtWidgets.QLabel("<b>SESSION GRAPH</b>"))
        
        self.rig_list = QtWidgets.QListWidget()
        self.rig_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.rig_list.itemSelectionChanged.connect(self.sync_list_to_graph)
        self.rig_list.itemChanged.connect(self.on_list_item_renamed)
        mod_side_layout.addWidget(self.rig_list)
        self.sidebar_stack.addWidget(self.sidebar_modules)

        self.workspace_stack = QtWidgets.QStackedWidget()
        self.graph_widget = ModuleGraphWidget(self) 
        
        self.workspace_stack.addWidget(self.page_file())      # 0
        self.workspace_stack.addWidget(self.page_rig())       # 1
        self.workspace_stack.addWidget(self.graph_widget)     # 2
        self.workspace_stack.addWidget(self.page_docs())      # 3
        self.workspace_stack.addWidget(self.page_profile())   # 4

        self.layout_main.addWidget(self.activity_bar)
        self.layout_main.addWidget(self.sidebar)
        self.layout_main.addWidget(self.workspace_stack)

        self.btn_file.clicked.connect(lambda: self.switch_tab(0))
        self.btn_rig.clicked.connect(lambda: self.switch_tab(1))
        self.btn_node.clicked.connect(lambda: self.switch_tab(2))
        self.btn_docs.clicked.connect(lambda: self.switch_tab(3))
        self.btn_prof.clicked.connect(lambda: self.switch_tab(4))
        
        self.switch_tab(1)
        self.create_lod_workspace("LOD0")
        self.setup_default_panels()

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

    def switch_tab(self, index):
        self.workspace_stack.setCurrentIndex(index)
        if index in [0, 1, 2]: self.main_window.session_controls_widget.show()
        else: self.main_window.session_controls_widget.hide()
            
        if index == 1:
            self.sidebar.show(); self.sidebar_stack.setCurrentIndex(1)
        elif index == 2:
            self.sidebar.show(); self.sidebar_stack.setCurrentIndex(2)
        else: self.sidebar.hide()

    def page_file(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.chk_autosave = QtWidgets.QCheckBox("Enable Auto-Save Pipeline (Every 5 minutes)")
        self.chk_autosave.setStyleSheet("font-size: 14px; font-weight: bold; color: #2bb5a8;")
        self.chk_autosave.setChecked(self.session_manager.data.get("auto_save_enabled", True))
        self.chk_autosave.toggled.connect(self.toggle_autosave)
        layout.addWidget(self.chk_autosave)
        
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        w_recent = QtWidgets.QWidget(); l_recent = QtWidgets.QVBoxLayout(w_recent)
        l_recent.addWidget(QtWidgets.QLabel("<b>Recent Files</b>"))
        self.list_recent = QtWidgets.QListWidget(); self.list_recent.itemDoubleClicked.connect(self.load_from_list)
        l_recent.addWidget(self.list_recent); splitter.addWidget(w_recent)
        
        w_auto = QtWidgets.QWidget(); l_auto = QtWidgets.QVBoxLayout(w_auto)
        l_auto.addWidget(QtWidgets.QLabel("<b>Autosaves</b>"))
        self.list_autosave = QtWidgets.QListWidget(); self.list_autosave.itemDoubleClicked.connect(self.load_from_list)
        l_auto.addWidget(self.list_autosave); splitter.addWidget(w_auto)
        
        w_pub = QtWidgets.QWidget(); l_pub = QtWidgets.QVBoxLayout(w_pub)
        l_pub.addWidget(QtWidgets.QLabel("<b>Published Files</b>"))
        self.list_published = QtWidgets.QListWidget(); self.list_published.itemDoubleClicked.connect(self.load_from_list)
        l_pub.addWidget(self.list_published); splitter.addWidget(w_pub)
        
        layout.addWidget(splitter)
        self.refresh_session_lists()
        return page

    def toggle_autosave(self, state):
        self.session_manager.data["auto_save_enabled"] = state
        self.session_manager.save_session()

    def refresh_session_lists(self):
        self.list_recent.clear(); self.list_autosave.clear(); self.list_published.clear()
        for path in self.session_manager.data["recent_files"]:
            if os.path.exists(path):
                item = QtWidgets.QListWidgetItem(os.path.basename(path))
                item.setToolTip(path); item.setData(QtCore.Qt.UserRole, path); self.list_recent.addItem(item)
                
        for path in self.session_manager.data["autosave_files"]:
            if os.path.exists(path):
                item = QtWidgets.QListWidgetItem(os.path.basename(path))
                item.setToolTip(path); item.setData(QtCore.Qt.UserRole, path); self.list_autosave.addItem(item)
                
        for path in self.session_manager.data["published_files"]:
            if os.path.exists(path):
                item = QtWidgets.QListWidgetItem(os.path.basename(path))
                item.setToolTip(path); item.setData(QtCore.Qt.UserRole, path); self.list_published.addItem(item)

    def load_from_list(self, item):
        path = item.data(QtCore.Qt.UserRole)
        if not os.path.exists(path):
            cmds.warning("File no longer exists!")
            return
        res = cmds.confirmDialog(
            title='Load Session', message='Where do you want to load this session?',
            button=['Current Session', 'New Tab', 'Cancel'], defaultButton='New Tab', cancelButton='Cancel', dismissString='Cancel'
        )
        if res == 'New Tab': self.main_window.create_new_session(load_path=path)
        elif res == 'Current Session':
            self.load_pipeline_from_file(path)
            self.switch_tab(1) 

    def refresh_module_list(self):
        self._syncing_selection = True
        self.rig_list.clear()
        if not hasattr(self, 'graph_widget'): return
        nodes = [item for item in self.graph_widget.graph_view.scene.items() if isinstance(item, RigNode)]
        for node in reversed(nodes):
            item = QtWidgets.QListWidgetItem(node.display_title)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            item.setData(QtCore.Qt.UserRole, node.uuid)
            self.rig_list.addItem(item)
        self._syncing_selection = False

    def on_list_item_renamed(self, item):
        if self._syncing_selection: return
        node_uuid = item.data(QtCore.Qt.UserRole)
        node = self.graph_widget.get_node_by_uuid(node_uuid)
        if node:
            new_text = item.text().strip()
            match = re.match(r"(.*)\s+\[([LRC])\]$", new_text)
            if match:
                node.custom_name = match.group(1).strip()
                node.side = match.group(2)
            else:
                node.custom_name = new_text
            node.update_display()
            self._syncing_selection = True
            item.setText(node.display_title)
            self._syncing_selection = False
            self.graph_widget.update_attr_editor()

    def sync_list_to_graph(self):
        if self._syncing_selection: return
        self._syncing_selection = True
        selected_uuids = [item.data(QtCore.Qt.UserRole) for item in self.rig_list.selectedItems()]
        self.graph_widget.graph_view.scene.clearSelection()
        for item in self.graph_widget.graph_view.scene.items():
            if isinstance(item, RigNode) and item.uuid in selected_uuids:
                item.setSelected(True)
        self.graph_widget.update_attr_editor()
        self._syncing_selection = False

    def sync_graph_to_list(self):
        if self._syncing_selection: return
        self._syncing_selection = True
        selected_uuids = [i.uuid for i in self.graph_widget.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        for i in range(self.rig_list.count()):
            item = self.rig_list.item(i)
            item.setSelected(item.data(QtCore.Qt.UserRole) in selected_uuids)
        self.graph_widget.update_attr_editor()
        self._syncing_selection = False

    def page_rig(self):
        page = QtWidgets.QWidget()
        main_vbox = QtWidgets.QVBoxLayout(page)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(15, 15, 15, 5)
        lbl_rig = QtWidgets.QLabel("<b>Rig Name:</b>")
        lbl_rig.setStyleSheet("color: #cccccc; font-size: 15px;")
        header_layout.addWidget(lbl_rig)
        
        self.edit_rig_name = QtWidgets.QLineEdit("Unnamed_Rig")
        self.edit_rig_name.setToolTip("This name will automatically be used in the AYON Publisher.")
        self.edit_rig_name.setStyleSheet("""
            QLineEdit { background: #1e1e1e; border: 1px solid #2bb5a8; color: white; padding: 6px; font-size: 15px; font-weight: bold; border-radius: 3px; }
        """)
        header_layout.addWidget(self.edit_rig_name)

        self.chk_cache_build = QtWidgets.QCheckBox("Cache steps during build")
        self.chk_cache_build.setChecked(True)
        self.chk_cache_build.setToolTip(
            "When on, a full/partial build removes old caches and writes a fresh scene\n"
            "snapshot after every step. Turn off for the fastest build with no cache I/O.")
        self.chk_cache_build.setStyleSheet("color: #cccccc; font-size: 13px;")
        header_layout.addWidget(self.chk_cache_build)

        self.btn_clear_caches = QtWidgets.QPushButton("🗑 Delete all caches")
        self.btn_clear_caches.setToolTip(
            "Delete every step cache for the current pipeline (all LODs).\n"
            "Other rigs' caches are untouched.")
        self.btn_clear_caches.setStyleSheet(
            "QPushButton { background: #3a2a2a; color: #e0b0b0; border: 1px solid #2bb5a8;"
            " padding: 4px 8px; border-radius: 3px; font-size: 12px; }"
            " QPushButton:hover { background: #5a2a2a; color: white; }")
        self.btn_clear_caches.clicked.connect(self.on_delete_all_caches)
        header_layout.addWidget(self.btn_clear_caches)

        self.chk_ignore_errors = QtWidgets.QCheckBox("Ignore errors (continue)")
        self.chk_ignore_errors.setChecked(False)
        self.chk_ignore_errors.setToolTip(
            "When on, a failed step does NOT stop the build - it is logged and the\n"
            "build continues with the next step. Cache loads also ignore 'unknown node'\n"
            "warnings and open anyway. Turn off to stop on the first error.")
        self.chk_ignore_errors.setStyleSheet("color: #cccccc; font-size: 13px;")
        header_layout.addWidget(self.chk_ignore_errors)
        main_vbox.addLayout(header_layout)

        # Panel search bar: filters the panels of the current LOD live.
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.setContentsMargins(15, 0, 15, 5)
        self.panel_search = QtWidgets.QLineEdit()
        self.panel_search.setPlaceholderText("🔍  Search panels by title, path or type…")
        self.panel_search.setClearButtonEnabled(True)
        self.panel_search.setToolTip(
            "Filter the panels in the current LOD by title, file path, panel type,\n"
            "or (for module panels) any module name. Clear to show all.")
        self.panel_search.setStyleSheet(
            "QLineEdit { background: #1e1e1e; border: 1px solid #333; color: white;"
            " padding: 6px; border-radius: 3px; } QLineEdit:focus { border: 1px solid #2bb5a8; }")
        self.panel_search.textChanged.connect(self.filter_panels)
        search_layout.addWidget(self.panel_search)

        self.lbl_search_count = QtWidgets.QLabel("")
        self.lbl_search_count.setStyleSheet("color: #888888; font-size: 12px;")
        search_layout.addWidget(self.lbl_search_count)
        main_vbox.addLayout(search_layout)

        self.lod_stack = QtWidgets.QStackedWidget()
        main_vbox.addWidget(self.lod_stack)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setContentsMargins(20, 10, 20, 20)
        
        btn_build = QtWidgets.QPushButton("BUILD CURRENT LOD")
        btn_build.setFixedHeight(50)
        btn_build.setStyleSheet("background: #444; color: white; border: 1px solid #2bb5a8; font-weight: bold;")
        btn_build.clicked.connect(self.run_full_build)

        btn_publish = QtWidgets.QPushButton("SAVE ALL")
        btn_publish.setFixedHeight(50)
        btn_publish.setStyleSheet("background: #2bb5a8; color: white; font-weight: bold;")
        btn_publish.clicked.connect(self.publish_asset_logic)

        btn_publish_ayon = QtWidgets.QPushButton("🚀 PUBLISH AYON")
        btn_publish_ayon.setFixedHeight(50)
        btn_publish_ayon.setStyleSheet("background: #2196F3; color: white; font-weight: bold; border: 1px solid #1976D2;")
        btn_publish_ayon.clicked.connect(self.open_ayon_publish_dialog)

        btn_layout.addWidget(btn_build)
        btn_layout.addWidget(btn_publish)
        btn_layout.addWidget(btn_publish_ayon)
        main_vbox.addLayout(btn_layout)

        comment_view_layout = QtWidgets.QHBoxLayout()
        comment_view_layout.setContentsMargins(20, 0, 20, 10)
        lbl_cv = QtWidgets.QLabel("💬 Comment:")
        lbl_cv.setStyleSheet("color: #999999; font-size: 12px;")
        comment_view_layout.addWidget(lbl_cv)
        self.comment_view = QtWidgets.QLineEdit()
        self.comment_view.setReadOnly(True)
        self.comment_view.setPlaceholderText("No comment saved for this file yet - added when you press SAVE ALL.")
        self.comment_view.setToolTip("Comment for the current file. Edit it via the SAVE ALL prompt.")
        self.comment_view.setStyleSheet(
            "QLineEdit { background: #1e1e1e; border: 1px solid #444; color: #bbbbbb;"
            " padding: 4px; font-size: 12px; border-radius: 3px; }")
        comment_view_layout.addWidget(self.comment_view)
        main_vbox.addLayout(comment_view_layout)
        self.refresh_comment_view()

        return page

    def open_ayon_publish_dialog(self):
        from .dialogs import AyonPublishDialog
        from .compat import IS_PYSIDE6
        dialog = AyonPublishDialog(self)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def open_path_replace_dialog(self):
        from .dialogs import PathReplaceDialog
        dialog = PathReplaceDialog(self)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def create_lod_workspace(self, name="LOD0", set_active=True, color="#2bb5a8"):
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
        menu_add.addAction("Add Maya .MA Panel", lambda: self.add_panel("CUSTOM .MA FILE", "MA", ""))
        menu_add.addAction("Add Import 3D Panel", lambda: self.add_panel("IMPORT 3D MODEL", "IMPORT_3D", ""))
        menu_add.addAction("Add Module Bubbles Panel", lambda: self.add_module_panel("LOAD MODULE SCRIPTS"))
        menu_add.addAction("Add Skin JSON Panel", lambda: self.add_panel("CUSTOM SKIN JSON", "JSON", ""))
        menu_add.addAction("Add Control Shapes Panel", lambda: self.add_panel("CONTROL SHAPES", "SHAPES", ""))
        menu_add.addAction("Add Publish Path Panel", lambda: self.add_panel("PUBLISH PATH", "PUBLISH", ""))
        btn_add_panel.setMenu(menu_add); rig_vbox.addWidget(btn_add_panel); rig_vbox.addStretch()
        
        scroll.setWidget(scroll_content); layout.addWidget(scroll)
        page.panels_container = panels_container
        self.lod_stack.addWidget(page)
        if set_active: self.lod_list.setCurrentItem(item); self.lod_stack.setCurrentWidget(page)
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
            
        self.add_panel("LOAD SCRIPT PANEL", "SCRIPT", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\Kleem_Rigging_Tool\scripts\Utils.py")
        self.add_panel("LOAD MODEL (.ma file)", "MA", r"E:/Pipe_Storage/Vishal_workspace/All_Doc/My/script/My_Temp/hand_final.ma")
        self.add_module_panel("LOAD MODULE")
        self.add_panel("LOAD SKINCLUSTER", "JSON", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp\Hand2.jSkin")
        self.add_panel("CUSTOM SCRIPT", "SCRIPT", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\Kleem_Rigging_Tool\scripts\post_script.py")
        self.add_panel("CONTROL SHAPES", "SHAPES", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp\Shapes.json")
        self.add_panel("PUBLISH PATH", "PUBLISH", r"E:\Pipe_Storage\Vishal_workspace\All_Doc\My\script\My_Temp")

    def clear_all_panels(self):
        while self.lod_stack.count() > 0:
            widget = self.lod_stack.widget(0); self.lod_stack.removeWidget(widget); widget.deleteLater()
        self.lod_list.clear()

    def reset_scene_and_ui(self):
        cmds.file(new=True, force=True)
        self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

        for i in range(self.lod_stack.count()):
            container = self.lod_stack.widget(i).panels_container
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if hasattr(panel, 'btn_run'):
                    btn_txt = "RUN" if getattr(panel, 'p_type', '') == "SCRIPT" else "VALIDATE" if getattr(panel, 'p_type', '') == "PUBLISH" else "LOAD"
                    panel.btn_run.setText(btn_txt)
                    panel.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
                if getattr(panel, 'p_type', '') == "MODULE":
                    for b in range(panel.bubble_layout.count()): panel.bubble_layout.itemAt(b).widget().reset_style()
                if hasattr(panel, 'refresh_cache_ui'): panel.refresh_cache_ui()
        cmds.warning("Scene wiped. Memory Namespace Flushed. UI Buttons Reset.")

    def reset_namespace_only(self):
        self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

    def restore_namespace_preamble(self, target_panel):
        """Rebuild the Python helper namespace after loading a cache, by re-running
        the leading run-of SCRIPT panels that point at an existing file (the util /
        function libraries at the top of the list). Inline-code and later scripts are
        skipped so scene edits already baked into the cache are not re-applied."""
        self.reset_namespace_only()
        container = self.get_current_lod_container()
        if not container: return
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if panel is target_panel: break
            if getattr(panel, 'p_type', '') != "SCRIPT": break
            path = panel.field.text().strip()
            if not path or not os.path.isfile(path): break
            try: self.run_script(path, func_call=panel.func_field.text().strip())
            except Exception: pass

    def refresh_comment_view(self):
        """Show the current file's saved comment in the read-only bottom row."""
        cv = getattr(self, 'comment_view', None)
        if cv is not None:
            cv.setText(getattr(self, 'pipeline_comment', "") or "")

    def refresh_all_cache_ui(self):
        """Re-evaluate the cached (green) state of every step across all LODs.
        Called after opening a JSON or switching sessions so the UI reflects
        the caches that actually exist in the current pipeline's folder."""
        if not hasattr(self, 'lod_stack'):
            return
        for i in range(self.lod_stack.count()):
            page = self.lod_stack.widget(i)
            container = getattr(page, 'panels_container', None)
            if not container:
                continue
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if hasattr(panel, 'refresh_cache_ui'):
                    panel.refresh_cache_ui()

    def clear_all_caches_current_pipeline(self):
        """Delete every step cache belonging to the currently open pipeline
        (all LODs). Only touches this JSON's own cache folder - other rigs are
        untouched."""
        removed = 0
        try:
            cdir = self.get_cache_dir()
        except Exception:
            cdir = ""
        try:
            if cdir and os.path.isdir(cdir):
                for fn in os.listdir(cdir):
                    if fn.lower().endswith(".ma"):
                        try:
                            os.remove(os.path.join(cdir, fn)); removed += 1
                        except Exception:
                            pass
        except Exception:
            pass
        self.refresh_all_cache_ui()
        return removed

    def on_delete_all_caches(self):
        """Confirm, then wipe all caches for the current pipeline."""
        name = os.path.basename(self.session_path) if self.session_path else "this unsaved pipeline"
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("Delete all caches")
        box.setText("Delete ALL step caches for {}?".format(name))
        box.setInformativeText(
            "This clears cached scene snapshots for every step across all LODs of\n"
            "the current pipeline. Other rigs are unaffected.")
        box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        box.setDefaultButton(QtWidgets.QMessageBox.No)
        res = box.exec() if IS_PYSIDE6 else box.exec_()
        if res == QtWidgets.QMessageBox.Yes:
            n = self.clear_all_caches_current_pipeline()
            cmds.warning("Deleted {} cache(s) for the current pipeline.".format(n))

    def clear_all_caches_current_lod(self):
        container = self.get_current_lod_container()
        if not container: return 0
        removed = 0
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if hasattr(panel, 'get_cache_path'):
                p = panel.get_cache_path()
                try:
                    if p and os.path.isfile(p):
                        os.remove(p); removed += 1
                except Exception: pass
                if hasattr(panel, 'refresh_cache_ui'): panel.refresh_cache_ui()
        return removed

    def remove_caches_from(self, panel, inclusive=True):
        """Delete the cache of `panel` (if inclusive) and every step after it in the
        current LOD, since those downstream snapshots are now stale."""
        container = self.get_current_lod_container()
        if not container: return 0
        idx = -1
        for i in range(container.layout.count()):
            if container.layout.itemAt(i).widget() is panel:
                idx = i; break
        if idx < 0: return 0
        start = idx if inclusive else idx + 1
        removed = 0
        for i in range(start, container.layout.count()):
            p = container.layout.itemAt(i).widget()
            if hasattr(p, 'get_cache_path'):
                cp = p.get_cache_path()
                try:
                    if cp and os.path.isfile(cp):
                        os.remove(cp); removed += 1
                except Exception:
                    pass
                if hasattr(p, 'refresh_cache_ui'): p.refresh_cache_ui()
        return removed

    def _begin_fast_build(self):
        """Put Maya into a fast, non-interactive state for the duration of a build.
        All changes are restored in _end_fast_build."""
        state = {}
        try: state['undo'] = cmds.undoInfo(q=True, state=True)
        except Exception: state['undo'] = None
        try: cmds.undoInfo(state=False)
        except Exception: pass
        try: state['echo'] = cmds.commandEcho(q=True, state=True)
        except Exception: state['echo'] = None
        try: cmds.commandEcho(state=False)
        except Exception: pass
        try: cmds.refresh(suspend=True)
        except Exception: pass
        return state

    def _end_fast_build(self, state):
        try: cmds.refresh(suspend=False)
        except Exception: pass
        try:
            if state.get('undo') is not None: cmds.undoInfo(state=state['undo'])
        except Exception: pass
        try:
            if state.get('echo') is not None: cmds.commandEcho(state=state['echo'])
        except Exception: pass
        try: cmds.refresh(force=True)
        except Exception: pass

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
        else:
            new_pan = self.add_panel(new_title, p_type, panel.field.text(), idx + 1)
            if new_pan is None: return
            new_pan.bg_color = getattr(panel, 'bg_color', '#252526')
            new_pan.update_style()
            if p_type == "SCRIPT" and hasattr(new_pan, 'func_field') and hasattr(panel, 'func_field'):
                new_pan.func_field.setText(panel.func_field.text())
            if p_type == "JSON" and hasattr(new_pan, 'mesh_field') and hasattr(panel, 'mesh_field'):
                new_pan.mesh_field.setText(panel.mesh_field.text())
            if p_type == "SHAPES" and hasattr(new_pan, 'pattern_field') and hasattr(panel, 'pattern_field'):
                new_pan.pattern_field.setText(panel.pattern_field.text())

        # Carry over cache-tick and enabled/disabled state for all panel types.
        if hasattr(panel, 'cache_marked') and hasattr(new_pan, 'set_cache_marked'):
            new_pan.set_cache_marked(panel.cache_marked())
        if hasattr(panel, 'is_active') and not panel.is_active:
            new_pan.checkbox.setChecked(False)

    def delete_panel(self, panel):
        container = self.get_current_lod_container()
        if not container: return
        container.layout.removeWidget(panel); panel.deleteLater()

    def build_till_panel(self, target_panel):
        cmds.warning("--- Starting Partial Procedural Build ---")
        container = self.get_current_lod_container()
        if not container: return
        total_panels = container.layout.count()
        if total_panels == 0: return

        # Locate the target step.
        tgt = -1
        for i in range(total_panels):
            if container.layout.itemAt(i).widget() is target_panel:
                tgt = i; break
        if tgt < 0: return

        # Find the newest cached step BEFORE the target and resume from it,
        # instead of rebuilding everything from scratch.
        start_k = -1
        for i in range(tgt - 1, -1, -1):
            p = container.layout.itemAt(i).widget()
            if hasattr(p, 'has_cache') and p.has_cache():
                start_k = i; break

        if start_k >= 0:
            cached_panel = container.layout.itemAt(start_k).widget()
            cmds.warning(f"[KRT] Resuming from cache '{cached_panel.title_edit.text()}' "
                         f"(step {start_k + 1}), running through target.")
            if not self.load_cache_only(cached_panel):
                cmds.warning("[KRT] Cache load failed - falling back to full run.")
                start_k = -1
                self.reset_scene_and_ui()
        else:
            self.reset_scene_and_ui()

        begin = start_k + 1  # start_k == -1 -> begin at 0
        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        self.main_window.setEnabled(False)
        progress_ui = BuildProgressDialog(self, total_steps=total_panels)
        progress_ui.progress_bar.setValue(begin)
        progress_ui.show(); start_t = time.time()
        timings = []

        fast = self._begin_fast_build()
        try:
            for i in range(begin, total_panels):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled: break
                panel = container.layout.itemAt(i).widget()
                if panel and hasattr(panel, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {panel.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = panel.execute(progress_ui=progress_ui)
                    if getattr(panel, 'is_active', True):
                        timings.append((time.time() - step_t, panel.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {panel.title_edit.text()}")
                        else:
                            break
                    elif do_cache and getattr(panel, 'is_active', True) and getattr(panel, 'cache_marked', lambda: False)() and hasattr(panel, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {panel.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        panel.cache_now(silent=True)
                    if panel == target_panel:
                        progress_ui.progress_bar.setValue(total_panels)
                        cmds.warning("Partial Build Finished.")
                        break
        finally:
            self._end_fast_build(fast)
            elapsed = time.time() - start_t
            progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

    def get_current_pipeline_data(self, ayon_context=None):
        pipeline_data = {"lods": []}
        if hasattr(self, 'edit_rig_name'): pipeline_data["rig_name"] = self.edit_rig_name.text().strip()
        pipeline_data["comment"] = getattr(self, 'pipeline_comment', "")

        for i in range(self.lod_list.count()):
            lod_item = self.lod_list.item(i); lod_name = lod_item.text()
            brush = lod_item.foreground()
            lod_color = brush.color().name() if brush.style() != QtCore.Qt.NoBrush else "#2bb5a8"
            page = self.lod_stack.widget(i); container = page.panels_container

            seq = []
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if panel.p_type == "MODULE":
                    mods = [{"path": panel.bubble_layout.itemAt(b).widget().full_path, "active": panel.bubble_layout.itemAt(b).widget().is_active} for b in range(panel.bubble_layout.count())]
                    seq.append({"title": panel.title_edit.text(), "type": "MODULE", "modules": mods, "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False})
                else:
                    data = {"title": panel.title_edit.text(), "type": panel.p_type, "path": panel.field.text(), "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False}
                    if panel.p_type == "SHAPES": data["pattern"] = panel.pattern_field.text()
                    if panel.p_type == "JSON": data["meshes"] = panel.mesh_field.text()
                    if panel.p_type == "SCRIPT": data["func_call"] = panel.func_field.text()
                    seq.append(data)
            pipeline_data["lods"].append({"name": lod_name, "color": lod_color, "execution_sequence": seq})

        graph_data = {"guide_path": self.graph_widget.path_field.text(), "nodes": [], "wires": []}
        for item in self.graph_widget.graph_view.scene.items():
            if isinstance(item, RigNode):
                graph_data["nodes"].append({"uuid": item.uuid, "module_type": item.module_type, "custom_name": item.custom_name, "side": item.side, "x": item.pos().x(), "y": item.pos().y()})
            elif isinstance(item, RigWire):
                graph_data["wires"].append({"source": item.source.uuid, "dest": item.dest.uuid})
        pipeline_data["graph_data"] = graph_data
        if ayon_context: pipeline_data["ayon_publish_context"] = ayon_context
        return pipeline_data

    def get_publishable_files(self):
        seen  = set()
        paths = []
        FIELD_TYPES = {"SCRIPT", "MA", "JSON", "SHAPES", "IMPORT_3D"}

        for lod_idx in range(self.lod_stack.count()):
            page      = self.lod_stack.widget(lod_idx)
            container = page.panels_container

            for panel_idx in range(container.layout.count()):
                panel  = container.layout.itemAt(panel_idx).widget()
                p_type = getattr(panel, 'p_type', None)

                if p_type in FIELD_TYPES:
                    path = panel.field.text().strip().replace("\\", "/")
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
                p = panel.field.text().strip()
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
            lods = data.get("lods", [])
            if not lods and "execution_sequence" in data:
                lods = [{"name": "LOD0", "color": "#2bb5a8", "execution_sequence": data["execution_sequence"]}]
            graph_data = data.get("graph_data", {})
            if not lods and not graph_data: return
            
            if graph_data:
                self.graph_widget.graph_view.scene.clear()
                self.graph_widget.path_field.setText(graph_data.get("guide_path", ""))
                uuid_to_node = {}
                for nd in graph_data.get("nodes", []):
                    node = RigNode(nd["x"], nd["y"], nd["module_type"], nd["side"], nd.get("custom_name", ""))
                    node.uuid = nd["uuid"]; self.graph_widget.graph_view.scene.addItem(node); uuid_to_node[node.uuid] = node
                for wd in graph_data.get("wires", []):
                    src = uuid_to_node.get(wd["source"]); dst = uuid_to_node.get(wd["dest"])
                    if src and dst: wire = RigWire(src, dst); self.graph_widget.graph_view.scene.addItem(wire)
                self.refresh_module_list()
                
            if lods:
                self.clear_all_panels()
                for lod_data in lods:
                    color = lod_data.get("color", "#2bb5a8")
                    page = self.create_lod_workspace(lod_data.get("name", "LOD"), set_active=False, color=color)
                    self.lod_stack.setCurrentWidget(page)
                    for item in lod_data.get("execution_sequence", []):
                        p_type = item.get("type"); is_act = item.get("active", True)
                        if p_type == "MODULE":
                            pan = self.add_module_panel(item.get("title", "LOAD MODULE SCRIPTS"))
                            pan.bg_color = item.get("bg_color", "#252526")
                            pan.update_style()
                            for m in item.get("modules", []):
                                if isinstance(m, dict): pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
                                else: pan.add_module_bubble(pre_path=m)
                            if not is_act: pan.checkbox.setChecked(False)
                            if item.get("uuid"): pan.uuid = item.get("uuid")
                            if hasattr(pan, 'set_cache_marked'): pan.set_cache_marked(item.get("cache_enabled", False))
                            pan.refresh_cache_ui()
                        else:
                            pan = self.add_panel(item.get("title", "LOAD SCRIPT"), p_type, item.get("path", ""))
                            pan.bg_color = item.get("bg_color", "#252526")
                            pan.update_style()
                            if not is_act: pan.checkbox.setChecked(False)
                            if p_type == "JSON" and item.get("meshes"): pan.mesh_field.setText(item.get("meshes"))
                            if p_type == "SHAPES" and item.get("pattern"): pan.pattern_field.setText(item.get("pattern"))
                            if p_type == "SCRIPT" and item.get("func_call"): pan.func_field.setText(item.get("func_call"))
                            if item.get("uuid"): pan.uuid = item.get("uuid")
                            if hasattr(pan, 'set_cache_marked'): pan.set_cache_marked(item.get("cache_enabled", False))
                            pan.refresh_cache_ui()
                if self.lod_list.count() > 0: self.lod_list.setCurrentRow(0)
            
            self.set_session_path(file_path); self.session_manager.add_recent(file_path); self.main_window.refresh_all_session_lists()
        except Exception: traceback.print_exc()

    def cache_steps_enabled(self):
        chk = getattr(self, 'chk_cache_build', None)
        return chk.isChecked() if chk is not None else True

    def ignore_errors_enabled(self):
        chk = getattr(self, 'chk_ignore_errors', None)
        return chk.isChecked() if chk is not None else False

    def _open_scene_tolerant(self, path):
        """Open a scene, tolerating 'unknown node' warnings and missing plugins.
        Suppresses blocking file prompts so a build never halts on a dialog.
        Returns True if the file opened (even with warnings)."""
        try: prev_prompt = cmds.file(q=True, prompt=True)
        except Exception: prev_prompt = None
        try:
            cmds.file(prompt=False)              # no blocking "unknown node" dialogs
            cmds.file(new=True, force=True)
            cmds.file(path, open=True, force=True, ignoreVersion=True, prompt=False)
            return True
        except Exception:
            # File may still have opened with unknown nodes; honor the ignore toggle.
            cmds.warning(f"[KRT] Scene open reported issues:\n{traceback.format_exc()}")
            return self.ignore_errors_enabled()
        finally:
            try:
                if prev_prompt is not None: cmds.file(prompt=prev_prompt)
            except Exception: pass

    def run_full_build(self):
        cmds.warning("--- Starting Procedural Build for Current LOD ---")
        self.reset_scene_and_ui()
        container = self.get_current_lod_container()
        if not container: return False
        total_panels = container.layout.count()
        if total_panels == 0: return False

        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        if do_cache:
            removed = self.clear_all_caches_current_lod()
            cmds.warning(f"Cleared {removed} old step cache(s). Fresh caches will be written during this build.")

        self.main_window.setEnabled(False)
        progress_ui = BuildProgressDialog(self, total_steps=total_panels)
        progress_ui.show(); start_t = time.time()
        build_ok = True
        timings = []

        fast = self._begin_fast_build()
        try:
            for i in range(total_panels):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    build_ok = False
                    break
                panel = container.layout.itemAt(i).widget()
                if panel and hasattr(panel, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {panel.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = panel.execute(progress_ui=progress_ui)
                    step_elapsed = time.time() - step_t
                    if getattr(panel, 'is_active', True):
                        timings.append((step_elapsed, panel.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {panel.title_edit.text()}")
                            continue
                        build_ok = False
                        break
                    if do_cache and getattr(panel, 'is_active', True) and getattr(panel, 'cache_marked', lambda: False)() and hasattr(panel, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {panel.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        panel.cache_now(silent=True)
        finally:
            self._end_fast_build(fast)
            progress_ui.progress_bar.setValue(total_panels)
            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)
            progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

        return build_ok

    def _report_build_timings(self, timings, elapsed):
        try:
            mins, secs = divmod(int(elapsed), 60)
            cmds.warning(f"[BUILD] Total Execution Time: {mins:02d}:{secs:02d}")
            slowest = sorted(timings, reverse=True)[:5]
            if slowest:
                cmds.warning("[BUILD] Slowest steps:")
                for dur, title in slowest:
                    cmds.warning(f"    {dur:7.2f}s  -  {title}")
        except Exception:
            pass

    def load_cache_only(self, panel):
        """Just open this step's cached scene (no further building)."""
        if not hasattr(panel, 'has_cache') or not panel.has_cache():
            cmds.warning("No cache exists for this step yet.")
            return False
        ok = self._open_scene_tolerant(panel.get_cache_path())
        if not ok:
            cmds.warning(f"Failed to load cache: {panel.title_edit.text()}")
            return False
        try:
            self.restore_namespace_preamble(panel)
        except Exception:
            cmds.warning(f"[KRT] Namespace preamble issue (continuing):\n{traceback.format_exc()}")
        cmds.warning(f"Loaded cached scene: {panel.title_edit.text()}")
        return True

    def build_from_cache(self, panel):
        """Load this step's cache, then continue executing the remaining steps."""
        if not hasattr(panel, 'has_cache') or not panel.has_cache():
            cmds.warning("No cache for this step to build from.")
            return False
        container = self.get_current_lod_container()
        if not container: return False
        idx = -1
        for i in range(container.layout.count()):
            if container.layout.itemAt(i).widget() is panel:
                idx = i; break
        if idx < 0: return False

        cmds.warning(f"--- Building FROM cache: {panel.title_edit.text()} ---")
        if not self.load_cache_only(panel):
            return False

        total = container.layout.count()
        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        self.main_window.setEnabled(False)
        progress_ui = BuildProgressDialog(self, total_steps=total)
        progress_ui.progress_bar.setValue(idx + 1)
        progress_ui.show(); start_t = time.time()
        timings = []; build_ok = True

        fast = self._begin_fast_build()
        try:
            for i in range(idx + 1, total):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    build_ok = False; break
                p = container.layout.itemAt(i).widget()
                if p and hasattr(p, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {p.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = p.execute(progress_ui=progress_ui)
                    if getattr(p, 'is_active', True):
                        timings.append((time.time() - step_t, p.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {p.title_edit.text()}")
                            continue
                        build_ok = False; break
                    if do_cache and getattr(p, 'is_active', True) and getattr(p, 'cache_marked', lambda: False)() and hasattr(p, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {p.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        p.cache_now(silent=True)
        finally:
            self._end_fast_build(fast)
            progress_ui.progress_bar.setValue(total)
            elapsed = time.time() - start_t
            progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

        return build_ok

    def run_mgear_sgt(self, sgt_path):
        try: from mgear.shifter import io, guide_manager
        except ImportError: return False, "mGear not found or not loaded."
        if not os.path.exists(sgt_path): return False, f"SGT Path not found: {sgt_path}"
        try:
            io.import_guide_template(sgt_path)
            guide_node = cmds.ls("guide")
            if guide_node:
                cmds.select(guide_node); QtWidgets.QApplication.processEvents()
                guide_manager.build_from_selection(); cmds.delete(guide_node); return True, ""
            return False, "Guide node not found after SGT import."
        except Exception as e:
            return False, traceback.format_exc()

    def run_script(self, path_or_code, func_call=""):
        try:
            if not path_or_code.strip():
                if func_call:
                    exec(func_call, self.shared_namespace)
                return True, "" 
                
            if os.path.exists(path_or_code):
                if path_or_code.endswith(".mel"):
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    mel.eval(script_code)
                    if func_call: mel.eval(func_call)
                else:
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    exec(script_code, self.shared_namespace)
                    if func_call: exec(func_call, self.shared_namespace)
                return True, ""
            else:
                exec(path_or_code, self.shared_namespace)
                if func_call: exec(func_call, self.shared_namespace)
                return True, ""
        except Exception as e:
            return False, traceback.format_exc()

    def import_ma_logic(self, path):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try: 
            cmds.file(path, i=True)
            return True, ""
        except Exception as e: 
            return False, str(e)
        
    def import_3d_logic(self, path):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try:
            path_lower = path.lower()
            if path_lower.endswith(".abc"):
                if not cmds.pluginInfo('AbcImport', query=True, loaded=True): cmds.loadPlugin('AbcImport')
                cmds.AbcImport(path, mode="import")
            elif path_lower.endswith(".fbx"):
                if not cmds.pluginInfo('fbxmaya', query=True, loaded=True): cmds.loadPlugin('fbxmaya')
                cmds.file(path, i=True, type="FBX", ignoreVersion=True, mergeNamespacesOnClash=False, namespace=":")
            elif path_lower.endswith(".obj"):
                if not cmds.pluginInfo('objExport', query=True, loaded=True): cmds.loadPlugin('objExport')
                cmds.file(path, i=True, type="OBJ", ignoreVersion=True, mergeNamespacesOnClash=False, namespace=":")
            else: cmds.file(path, i=True)
            return True, ""
        except Exception as e: 
            return False, str(e)

    def load_skin_cluster_logic(self, path, meshes=None):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try:
            from mgear.core import skin
            # Use cmds.select (not pm.select) to avoid pymel's spurious
            # "Cannot find Maya documentation" error on installs without docs.
            if meshes and meshes.strip() != "":
                mesh_list = [m.strip() for m in meshes.split(",") if m.strip()]
                if mesh_list:
                    cmds.select(mesh_list, replace=True)
            skin.importSkin(path)
            return True, ""
        except Exception as e:
            return False, str(e)

    def publish_asset_logic(self):
        publish_dir = None
        container = self.get_current_lod_container()
        if container:
            for i in range(container.layout.count()):
                panel = container.layout.itemAt(i).widget()
                if hasattr(panel, 'p_type') and panel.p_type == "PUBLISH" and panel.is_active:
                    publish_dir = panel.field.text(); break
        if not publish_dir or not os.path.exists(publish_dir):
            cmds.warning("[KRT] Save All: no valid PUBLISH directory set.")
            return

        # Ask for a comment for this save (pre-filled with the last one).
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, "Save All", "Comment for this save (optional):",
            getattr(self, 'pipeline_comment', ""))
        if not ok:
            return
        self.pipeline_comment = text
        self.refresh_comment_view()

        rig_name = self.edit_rig_name.text().strip() or "Unnamed_Rig"
        from .utils import get_versioned_path

        ma_path_base = os.path.join(publish_dir, f"{rig_name}.ma").replace("\\", "/")
        ma_path = get_versioned_path(ma_path_base, get_latest=False)

        try: cmds.file(rename=ma_path); cmds.file(save=True, type="mayaAscii")
        except Exception: return

        pipeline_data = self.get_current_pipeline_data()
        json_path_base = os.path.join(publish_dir, f"{rig_name}.json").replace("\\", "/")
        json_path = get_versioned_path(json_path_base, get_latest=False)

        with open(json_path, 'w') as f: json.dump(pipeline_data, f, indent=4)
        
        self.set_session_path(json_path)
        self.session_manager.add_published(json_path)
        self.main_window.refresh_all_session_lists()
        cmds.warning(f"Successfully published: {json_path}")

    def page_docs(self):
        page = QtWidgets.QWidget(); l = QtWidgets.QVBoxLayout(page); l.addWidget(QtWidgets.QLabel("Documentation")); return page
    def page_profile(self):
        page = QtWidgets.QWidget(); l = QtWidgets.QVBoxLayout(page); l.addWidget(QtWidgets.QLabel("User Profile")); return page
    def create_nav_btn(self, icon, tip):
        btn = QtWidgets.QPushButton(icon); btn.setFixedSize(50, 50); btn.setToolTip(tip); btn.setFlat(True)
        btn.setStyleSheet("font-size: 22px; color: white; border: none;"); return btn