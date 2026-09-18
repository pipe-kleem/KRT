import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om
import os
import json
import time
import math
import traceback
import re
import shutil
import subprocess
import fnmatch
import tempfile
import getpass
import sys
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6, QMediaPlayer, QVideoWidget, QAudioOutput, QMediaContent, HAS_MULTIMEDIA
from .dialogs import AdvancedSaveDialog, BuildProgressDialog, SimpleCodeEditorDialog
from .widgets import DragDropContainer, SortablePanel, SortableBubblePanel, LodLoaderPanel, panel_run_label, prompt_skincluster_naming_check, PBCameraViewWidget, PBWipeCompareWidget
from .graph import ModuleGraphWidget, RigNode, RigWire
from .utils import read_skin_file_meshes, log_crash

# Stage 17: default location for the Rigging Workspace's script/tools
# library - always this by default, but editable per-user (see
# SessionWorkspace.page_scripts / set_scripts_lib_path); a change is saved
# into that user's own session_data.json, same as every other per-user KRT
# preference (recent files, autosave toggle, etc).
DEFAULT_SCRIPTS_LIB_PATH = r"P:\pipeline_database\Maya\Scripts\ONE"

# Stage 37: the studio's shared Studio Library install - KRT's Playblast
# tab reuses Studio Library's own "mutils" package to load a .anim clip
# (see SessionWorkspace.pb_ensure_studiolibrary), instead of re-implementing
# animation-curve pasting from scratch.
DEFAULT_STUDIOLIBRARY_SRC_PATH = r"P:\rigging_team\Rigging_local_share\QC\studiolibrary-2.20.2\src"

# Stage 19: shared look for a labelled section box within a tab (Rigging
# Workspace's Script Library / LOD Build Manager sections) - one place to
# keep this consistent instead of retyping the stylesheet per group box.
SECTION_GROUPBOX_STYLE = (
    "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 8px; "
    "font-weight: bold; color: #aaa; } "
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")


class CurrentPageStackedWidget(QtWidgets.QStackedWidget):
    """A QStackedWidget whose size hint reflects only its CURRENTLY VISIBLE
    page, not the largest of every page it holds.

    Qt's default QStackedWidget reports sizeHint()/minimumSizeHint() as the
    max across ALL pages, so it can switch between them without the window
    visibly jumping. The side effect: the whole KRT window's minimum size is
    permanently dictated by whichever tab happens to have the tallest/widest
    natural layout (Rig Workspace, with its LOD panels, tends to be it) -
    EVEN while looking at a different, more compact tab like the Module
    Graph Editor. That's what made the window refuse to shrink much no
    matter what was showing. This subclass fixes that by sizing to only the
    active page; switching tabs calls updateGeometry() so the window's
    effective minimum is recalculated immediately.
    """

    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current else super(CurrentPageStackedWidget, self).sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current else super(CurrentPageStackedWidget, self).minimumSizeHint()

    def setCurrentIndex(self, index):
        super(CurrentPageStackedWidget, self).setCurrentIndex(index)
        self.updateGeometry()

    def setCurrentWidget(self, widget):
        super(CurrentPageStackedWidget, self).setCurrentWidget(widget)
        self.updateGeometry()


class SessionWorkspace(QtWidgets.QWidget):
    def __init__(self, main_window):
        super(SessionWorkspace, self).__init__()
        self.main_window = main_window
        self.session_manager = main_window.session
        self.session_path = ""
        self.pipeline_comment = ""
        self.dragged_panel = None
        self._syncing_selection = False
        # Node uuids in the order the user actually built up the current
        # selection (oldest first) - tracked incrementally in
        # sync_list_to_graph/sync_graph_to_list as selection changes, since
        # neither QListWidget.selectedItems() nor QGraphicsScene.selectedItems()
        # report items in selection order. Lets "Build Guides"/"Build
        # Modules" on multiple selected nodes build in the order they were
        # selected, not scene/list order.
        self.selection_order = []

        # Stage 22, request #1: a small undo stack for panel Delete/Cut -
        # each entry remembers a removed panel's serialized data plus which
        # LOD and position it came from, so "Undo" (in any panel's ...
        # context menu) can put it back. Capped so it can't grow forever.
        self.panel_undo_stack = []

        self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

        # Playblast QC capture (Stage 36): HUD-visibility/camera-gate state
        # saved by pb_hide_all_huds()/pb_hide_camera_gates() right before a
        # capture, restored by pb_restore_all_huds()/pb_restore_camera_gates()
        # in create_playblast()'s finally block - see that method.
        self.pb_hud_original_visibility = {}
        self.pb_gate_camera = None
        self.pb_gate_original_values = {}

        self.setup_ui()

    def set_session_path(self, path, guide_path=None, refresh_guide_default=False):
        """Sets this session's own save location, and - Stage 35's Graph
        JSON / KRT JSON versioning rules - decides what happens to the
        Module Graph Editor's Guide Path field at the same time:

        - guide_path given (Rule 3: load_pipeline_from_file() passes the
          exact graph_data["guide_path"] this KRT json was saved with):
          point the field at THAT exact graph version, so Load Guides
          restores the same graph state this pipeline JSON was saved with.
        - refresh_guide_default=True (a brand new/empty session, or a
          loaded pipeline JSON with no guide_path of its own to restore):
          recompute the auto-managed default ("guide/<rig>_guide.json"
          next to this session's own path).
        - neither given (every KRT pipeline JSON SAVE -
          _save_pipeline_assets()/AdvancedSaveDialog/the AYON publish flow):
          leave the field exactly as it is. A save doesn't change which
          graph version is "current" - Rule 1 (ModuleGraphWidget.
          save_all_guides(overwrite=False), the "Save Guide (New Version)"
          menu action) is the only thing that bumps the version; Rule 2
          (save_all_guides(overwrite=True), called right after this by
          every KRT save) just re-syncs that same current version to disk.
        """
        self.session_path = path
        tab_index = self.main_window.session_stack.indexOf(self)
        tab_name = os.path.basename(path) if path else "Untitled Session"
        self.main_window.tab_bar.setTabText(tab_index, tab_name)

        if self.main_window.session_stack.currentIndex() == tab_index:
            self.main_window.session_path_field.setText(path)

        # Caches are stored per-JSON, so the current session's cache folder just
        # changed - re-evaluate every step's cached state against the new folder.
        self.refresh_all_cache_ui()

        if hasattr(self, "graph_widget"):
            if guide_path:
                self.graph_widget.path_field.setText(guide_path)
            elif refresh_guide_default:
                self.graph_widget.refresh_default_guide_path()
            # else: leave the Guide Path field untouched - see docstring.

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
        self.btn_scripts = self.create_nav_btn("🧰", "Rigging Workspace - Script/Tools Library")
        self.btn_playblast = self.create_nav_btn("🎬", "Playblast")
        self.btn_docs = self.create_nav_btn("📖", "Open Documentation")
        self.btn_prof = self.create_nav_btn("👤", "User Profile Settings")

        for b in [self.btn_file, self.btn_rig, self.btn_node, self.btn_scripts, self.btn_playblast, self.btn_docs]: act_layout.addWidget(b)
        act_layout.addStretch(); act_layout.addWidget(self.btn_prof)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setObjectName("SidebarFrame")
        side_layout = QtWidgets.QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0,0,0,0)
        
        self.sidebar_stack = CurrentPageStackedWidget()
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

        self.workspace_stack = CurrentPageStackedWidget()
        self.graph_widget = ModuleGraphWidget(self) 
        
        self.workspace_stack.addWidget(self.page_file())      # 0
        self.workspace_stack.addWidget(self.page_rig())       # 1
        self.workspace_stack.addWidget(self.graph_widget)     # 2
        self.workspace_stack.addWidget(self.page_docs())      # 3
        self.workspace_stack.addWidget(self.page_profile())   # 4
        self.workspace_stack.addWidget(self.page_scripts())   # 5
        self.workspace_stack.addWidget(self.page_playblast()) # 6

        self.layout_main.addWidget(self.activity_bar)
        self.layout_main.addWidget(self.sidebar)
        self.layout_main.addWidget(self.workspace_stack)

        self.btn_file.clicked.connect(lambda: self.switch_tab(0))
        self.btn_rig.clicked.connect(lambda: self.switch_tab(1))
        self.btn_node.clicked.connect(lambda: self.switch_tab(2))
        self.btn_docs.clicked.connect(lambda: self.switch_tab(3))
        self.btn_prof.clicked.connect(lambda: self.switch_tab(4))
        self.btn_scripts.clicked.connect(lambda: self.switch_tab(5))
        self.btn_playblast.clicked.connect(lambda: self.switch_tab(6))
        
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

        if index == 5:
            self.refresh_scripts_lib_list()
        elif index == 6:
            self.refresh_playblast_list()

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
        # rig_list is rebuilt from scratch below, which would otherwise wipe
        # out selection every time - and refresh_module_list() runs after
        # almost any graph edit (renaming, wiring, dragging a connection...),
        # so a node selected in the graph a moment before clicking "Build
        # Guides" could silently show as unselected in this list, producing
        # a "No modules selected" warning despite looking selected on canvas.
        # Capture the graph's selection (the source of truth) first and
        # reapply it to the freshly rebuilt list items.
        self._syncing_selection = True
        selected_uuids = set()
        if hasattr(self, 'graph_widget'):
            selected_uuids = {i.uuid for i in self.graph_widget.graph_view.scene.selectedItems()
                              if isinstance(i, RigNode)}
        self.rig_list.clear()
        if not hasattr(self, 'graph_widget'):
            self._syncing_selection = False
            return
        nodes = [item for item in self.graph_widget.graph_view.scene.items() if isinstance(item, RigNode)]
        for node in reversed(nodes):
            item = QtWidgets.QListWidgetItem(node.display_title)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            item.setData(QtCore.Qt.UserRole, node.uuid)
            self.rig_list.addItem(item)
            if node.uuid in selected_uuids:
                item.setSelected(True)
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

    def _track_selection_order(self, current_uuids):
        """Keep self.selection_order as (oldest -> newest) uuids currently
        selected: drop anything no longer selected, keep the relative order
        of what's still selected, and append anything newly selected."""
        current_set = set(current_uuids)
        self.selection_order = [u for u in self.selection_order if u in current_set]
        for u in current_uuids:
            if u not in self.selection_order:
                self.selection_order.append(u)

    def sync_list_to_graph(self):
        if self._syncing_selection: return
        self._syncing_selection = True
        selected_uuids = [item.data(QtCore.Qt.UserRole) for item in self.rig_list.selectedItems()]
        self.graph_widget.graph_view.scene.clearSelection()
        for item in self.graph_widget.graph_view.scene.items():
            if isinstance(item, RigNode) and item.uuid in selected_uuids:
                item.setSelected(True)
        self._track_selection_order(selected_uuids)
        self.graph_widget.update_attr_editor()
        self._syncing_selection = False

    def sync_graph_to_list(self):
        if self._syncing_selection: return
        self._syncing_selection = True
        selected_uuids = [i.uuid for i in self.graph_widget.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        for i in range(self.rig_list.count()):
            item = self.rig_list.item(i)
            item.setSelected(item.data(QtCore.Qt.UserRole) in selected_uuids)
        self._track_selection_order(selected_uuids)
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

        # Same "..." More Options pattern every panel type's context menu
        # already uses (widgets.py's SortablePanel.show_context_menu /
        # graph.py's Guide Path row) - here it's scoped to the whole loaded
        # pipeline JSON rather than one panel's field, so a rigger can jump
        # to an older/newer "<name>_vNNN.json" sibling of whatever pipeline
        # is currently loaded (self.session_path) without hunting for it
        # through Load JSON Pipeline's file browser.
        self.btn_rig_dots = QtWidgets.QPushButton("...")
        self.btn_rig_dots.setFixedWidth(28)
        self.btn_rig_dots.setToolTip("More options: Switch to another saved version of this pipeline JSON.")
        self.btn_rig_dots.setStyleSheet(
            "QPushButton { background: #333; color: #cccccc; border: 1px solid #2bb5a8;"
            " padding: 6px; border-radius: 3px; font-weight: bold; }"
            " QPushButton:hover { background: #444; color: white; }")
        self.btn_rig_dots.clicked.connect(self.show_rig_header_menu)
        header_layout.addWidget(self.btn_rig_dots)

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

        # Stage 34: the old single SAVE ALL button is now three buttons -
        # Save Maya File (just the .ma), Save All (both, the original
        # behavior), Save JSON File (just the pipeline JSON) - all three
        # share the same underlying _save_pipeline_assets() logic so a
        # rigger who only wants one half doesn't have to write out the
        # other every time.
        btn_save_maya = QtWidgets.QPushButton("SAVE MAYA FILE")
        btn_save_maya.setFixedHeight(50)
        btn_save_maya.setToolTip("Save the current scene as a new versioned .ma in the Publish Path - no pipeline JSON.")
        btn_save_maya.setStyleSheet("background: #444; color: white; border: 1px solid #2bb5a8; font-weight: bold;")
        btn_save_maya.clicked.connect(self.save_maya_file_logic)

        btn_publish = QtWidgets.QPushButton("SAVE ALL")
        btn_publish.setFixedHeight(50)
        btn_publish.setToolTip("Save both a new versioned .ma and the pipeline JSON in the Publish Path.")
        btn_publish.setStyleSheet("background: #2bb5a8; color: white; font-weight: bold;")
        btn_publish.clicked.connect(self.publish_asset_logic)

        btn_save_json = QtWidgets.QPushButton("SAVE JSON FILE")
        btn_save_json.setFixedHeight(50)
        btn_save_json.setToolTip("Save the current pipeline as a new versioned JSON in the Publish Path - no Maya file.")
        btn_save_json.setStyleSheet("background: #444; color: white; border: 1px solid #2bb5a8; font-weight: bold;")
        btn_save_json.clicked.connect(self.save_json_file_logic)

        btn_publish_ayon = QtWidgets.QPushButton("🚀 PUBLISH AYON")
        btn_publish_ayon.setFixedHeight(50)
        btn_publish_ayon.setStyleSheet("background: #2196F3; color: white; font-weight: bold; border: 1px solid #1976D2;")
        btn_publish_ayon.clicked.connect(self.open_ayon_publish_dialog)

        # Stage 34 fix: btn_layout used to hold exactly 3 widgets (Build,
        # the old single SAVE ALL, Publish AYON), each getting an equal
        # 1/3 share of the row's width from QHBoxLayout's default stretch.
        # Simply adding the 3 new save buttons as more top-level widgets
        # dropped that to a 1/5 share each - shrinking Build and Publish
        # AYON, which were never supposed to change. Grouping the 3 save
        # buttons into their own sub-layout keeps btn_layout back at 3
        # top-level items, so Build and Publish AYON get their original
        # 1/3 share back, and only the space the old SAVE ALL button used
        # to occupy is subdivided further, three ways, between them.
        save_btn_layout = QtWidgets.QHBoxLayout()
        save_btn_layout.setSpacing(4)
        save_btn_layout.addWidget(btn_save_maya)
        save_btn_layout.addWidget(btn_publish)
        save_btn_layout.addWidget(btn_save_json)

        btn_layout.addWidget(btn_build)
        btn_layout.addLayout(save_btn_layout)
        btn_layout.addWidget(btn_publish_ayon)
        main_vbox.addLayout(btn_layout)

        comment_view_layout = QtWidgets.QHBoxLayout()
        comment_view_layout.setContentsMargins(20, 0, 20, 10)
        lbl_cv = QtWidgets.QLabel("💬 Comment:")
        lbl_cv.setStyleSheet("color: #999999; font-size: 12px;")
        comment_view_layout.addWidget(lbl_cv)
        self.comment_view = QtWidgets.QLineEdit()
        self.comment_view.setReadOnly(True)
        self.comment_view.setPlaceholderText("No comment saved for this file yet - added when you press Save Maya File, Save All, or Save JSON File.")
        self.comment_view.setToolTip("Comment for the current file. Edit it via the Save Maya File / Save All / Save JSON File prompt.")
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

    def reset_scene_and_ui(self, wipe_scene=True):
        """wipe_scene=False (Stage 24): reset only the panel buttons'
        text/style, without touching the live Maya scene or the shared
        script namespace - used when a build needs to happen on TOP of
        whatever's already in the scene (see run_full_build's own
        reset_scene parameter) instead of starting from an empty file."""
        if wipe_scene:
            cmds.file(new=True, force=True)
            self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

        for i in range(self.lod_stack.count()):
            container = self.lod_stack.widget(i).panels_container
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if hasattr(panel, 'btn_run'):
                    panel.btn_run.setText(panel_run_label(getattr(panel, 'p_type', '')))
                    panel.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
                if getattr(panel, 'p_type', '') == "MODULE":
                    for b in range(panel.bubble_layout.count()): panel.bubble_layout.itemAt(b).widget().reset_style()
                if hasattr(panel, 'refresh_cache_ui'): panel.refresh_cache_ui()
        if wipe_scene:
            cmds.warning("Scene wiped. Memory Namespace Flushed. UI Buttons Reset.")
        else:
            cmds.warning("UI Buttons Reset. (Scene left as-is.)")

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
                    mods = [{"path": panel.bubble_layout.itemAt(b).widget().full_path, "active": panel.bubble_layout.itemAt(b).widget().is_active} for b in range(panel.bubble_layout.count())]
                    seq.append({"title": panel.title_edit.text(), "type": "MODULE", "modules": mods, "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False})
                elif panel.p_type == "LOD_LOADER":
                    seq.append({"title": panel.title_edit.text(), "type": "LOD_LOADER", "lod_names": panel.checked_lod_names(), "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', '')})
                else:
                    data = {"title": panel.title_edit.text(), "type": panel.p_type, "path": panel.field.text(), "active": panel.is_active, "bg_color": getattr(panel, 'bg_color', '#252526'), "uuid": getattr(panel, 'uuid', ''), "cache_enabled": panel.cache_marked() if hasattr(panel, 'cache_marked') else False}
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

    def show_rig_header_menu(self):
        """The "..." button next to Rig Name (Stage 36): right now this is
        just "Switch Version" for the whole loaded pipeline JSON, but lives
        as its own menu (not crammed onto the Load JSON Pipeline button) so
        more whole-pipeline options can land here later, same reasoning as
        every panel's own "..." menu."""
        menu = QtWidgets.QMenu(self)
        switch_menu = menu.addMenu("🔄 Switch Version")
        v_actions = self.populate_pipeline_versions_menu(switch_menu)

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if not action:
            return
        if action in v_actions:
            target_path = v_actions[action]
            if target_path == self.session_path:
                return  # already on this version
            self.load_pipeline_from_file(target_path)

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

    def run_full_build(self, reset_scene=True):
        """reset_scene=False (Stage 24): build this LOD's panel stack on top
        of whatever's currently in the scene, instead of wiping to a new
        file first - used when this LOD is being pulled in as one step of
        an already-in-progress build (a LOD Loader panel's RUN, whether
        clicked directly or reached mid-sequence via Build Till Here),
        rather than a standalone "Build Current LOD" from the toolbar."""
        cmds.warning("--- Starting Procedural Build for Current LOD ---")
        self.reset_scene_and_ui(wipe_scene=reset_scene)
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
            log_crash("Custom Module (.sgt): {}".format(sgt_path), e)
            return False, traceback.format_exc()

    def open_script_externally(self, path):
        """Open `path` in VS Code if it's on this machine's PATH, else fall
        back to KRT's own simple in-Maya editor (Stage 17). Shared by the
        Rigging Workspace's script library list and by a SCRIPT/
        GLOBAL_SCRIPT panel's 'Edit code in VS Code' action - that action
        used to just show an error when VS Code wasn't found; now it opens
        the fallback editor instead."""
        if not path or not os.path.isfile(path):
            cmds.warning("File not found: {}".format(path))
            return
        has_code = shutil.which("code") or shutil.which("code.cmd")
        if has_code:
            try:
                subprocess.Popen('code "{}"'.format(path), shell=True)
                return
            except Exception:
                traceback.print_exc()
        dialog = SimpleCodeEditorDialog(path, self.main_window)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

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
            log_crash("Custom script: {}".format(path_or_code[:120]), e)
            return False, traceback.format_exc()

    def run_script_global(self, path_or_code, func_call=""):
        """Stage 17: the "Default Script (Maya Global)" panel type. Identical
        to run_script() except Python code executes into Maya's REAL global
        namespace (__main__.__dict__ - the same dict Maya's own Script
        Editor uses) instead of self.shared_namespace, a dict private to
        this one KRT session/tab.

        The problem this solves: a dependency script (helper functions,
        imported modules) run through a normal SCRIPT panel only exists
        inside KRT's own isolated namespace - anything else in Maya
        (the Script Editor, another tool, a manually-run snippet) can't see
        it, so the user ends up re-running the same script by hand outside
        KRT too. Running it here instead makes it show up everywhere in
        Maya, exactly like typing it into the Script Editor would.

        MEL has no such distinction - mel.eval() already always runs in
        MEL's own single global scope, KRT-scoped or not, so the .mel
        branch below is identical to run_script()'s.

        Stage 25: a normal SCRIPT panel's shared_namespace is pre-seeded
        with cmds/mel/om (see reset_scene_and_ui) so a script can call
        cmds.something(...) straight away with no import of its own. Maya's
        REAL __main__ namespace has no such thing by default - a script
        that relies on that convenience (works fine as a normal SCRIPT
        panel, since that convenience is exactly why it worked) would hit a
        bare NameError the moment it touched cmds/mel/om here and silently
        fail before doing anything, which is exactly what "the script in
        the global panel isn't initializing, but the normal script panel
        works fine" looks like from the UI - no crash dialog if the script
        happens to only warn/print, or a real error that never got
        surfaced from a panel already in a good state. Seeding __main__
        with the same three names removes that gap, so a script behaves
        identically whether it runs as a SCRIPT or a GLOBAL_SCRIPT panel."""
        import __main__ as maya_main
        maya_main.__dict__.setdefault('cmds', cmds)
        maya_main.__dict__.setdefault('mel', mel)
        maya_main.__dict__.setdefault('om', om)
        try:
            if not path_or_code.strip():
                if func_call:
                    exec(func_call, maya_main.__dict__)
                return True, ""

            if os.path.exists(path_or_code):
                if path_or_code.endswith(".mel"):
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    mel.eval(script_code)
                    if func_call: mel.eval(func_call)
                else:
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    exec(script_code, maya_main.__dict__)
                    if func_call: exec(func_call, maya_main.__dict__)
                return True, ""
            else:
                exec(path_or_code, maya_main.__dict__)
                if func_call: exec(func_call, maya_main.__dict__)
                return True, ""
        except Exception as e:
            log_crash("Default script (Maya global): {}".format(path_or_code[:120]), e)
            return False, traceback.format_exc()

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

    def organize_lod_logic(self, asset_name, delete_ai_lod=True):
        """Organize every mesh currently in the scene into
        <asset_name>/<asset_name>_geo/<asset_name>_lod_<N> groups, folding
        any *_ai_lod naming into its own group (or deleting it outright if
        delete_ai_lod is on). This is the rigger's own organize_and_convert_lod
        script, kept exactly as given - only wrapped to return (success,
        message) like every other panel's Run logic, and with its own
        top-level error handling so a bad object can't silently abort the
        rest of the pass.

        Meant to run right after an Import 3D Model step on the same
        panel (the Import 3D + LOD Organize panel) - it works over
        whatever meshes are CURRENTLY in the scene, not just the ones a
        specific import just added, matching the original script's own
        behavior.
        """
        asset_name = (asset_name or "").strip()
        if not asset_name:
            return False, "No Asset Name given - type the asset's name first."

        try:
            # Part 1: Gather and ensure top-level groups
            meshes = cmds.ls(type="mesh")
            if not meshes:
                return False, "No polygon objects found in the scene."

            transforms = list(set(cmds.listRelatives(meshes, p=True, f=True) or []))
            to_group = [t for t in transforms if t.split("|")[-1] != asset_name and "|{}|".format(asset_name) not in t]

            top_grp = cmds.ls(asset_name, long=True)[0] if cmds.objExists(asset_name) else cmds.group(em=True, n=asset_name)
            for obj in to_group:
                try: cmds.parent(obj, top_grp)
                except Exception: pass

            geo_grp_name = "{}_geo".format(asset_name)
            geo_grp = next((c for c in (cmds.listRelatives(top_grp, c=True, f=True) or [])
                             if c.split("|")[-1] == geo_grp_name), None)
            if not geo_grp:
                geo_grp = cmds.group(em=True, n=geo_grp_name, p=top_grp)

            # Part 2: Parse and Sort LODs
            deleted_count = 0
            for mesh in cmds.listRelatives(top_grp, c=True, type="transform", f=True) or []:
                short_name = mesh.split("|")[-1]
                if short_name == geo_grp_name or not cmds.objExists(mesh):
                    continue

                # Handle AI LOD deletion
                if re.search(r"ai_lod", short_name, re.I) and delete_ai_lod:
                    cmds.delete(mesh)
                    deleted_count += 1
                    continue

                # Match prefix/suffix or fallback to AI LOD naming patterns
                match = re.search(r"(\d+)_lod|_lod_(\d+)", short_name, re.I)
                if match:
                    idx = match.group(1) or match.group(2)
                    lod_name = "{}_lod_{}".format(asset_name, idx)
                elif re.search(r"ai_lod", short_name, re.I):
                    lod_name = "{}_ai_lod".format(asset_name)
                else:
                    continue

                tgt_grp = cmds.ls("{}|{}".format(geo_grp, lod_name), l=True) or \
                    [cmds.group(em=True, n=lod_name, p=geo_grp)]
                try:
                    cmds.parent(mesh, tgt_grp[0])
                except Exception as e:
                    cmds.warning("[KRT] Could not parent {}: {}".format(short_name, e))

            msg = "LOD hierarchy generated successfully for '{}'.".format(asset_name)
            if delete_ai_lod and deleted_count:
                msg += " (Deleted {} AI LOD object(s))".format(deleted_count)
            cmds.inViewMessage(amg="<hl>{}</hl>".format(msg), pos="midCenter", fade=True)
            cmds.warning("[KRT] " + msg)
            return True, ""
        except Exception as e:
            return False, "LOD organize failed: {}".format(e)

    def delete_by_name_logic(self, names_text):
        """Delete every named object - the Delete panel's Run. Comma-
        separated names, same convention as every other multi-name field
        in KRT (Meshes/Joints/etc). A name that doesn't exist is reported
        and skipped, not fatal - a typo in one name shouldn't block
        deleting the rest."""
        names = [n.strip() for n in (names_text or "").split(",") if n.strip()]
        if not names:
            return False, "No object name(s) given - type one or more names (comma-separated)."
        missing = [n for n in names if not cmds.objExists(n)]
        existing = [n for n in names if cmds.objExists(n)]
        if not existing:
            return False, "None of these objects exist in the scene: {}".format(", ".join(names))
        try:
            cmds.delete(existing)
        except Exception as e:
            return False, "Failed to delete {}: {}".format(", ".join(existing), e)
        msg = "Deleted: {}".format(", ".join(existing))
        if missing:
            msg += "  (not found, skipped: {})".format(", ".join(missing))
        cmds.warning("[KRT] " + msg)
        return True, ""

    def zero_out_logic(self, names_text):
        """"Zero out" the named object(s)/control(s) - the Zero Out panel's
        Run. Rather than just resetting translate/rotate/scale on the
        object itself (which would snap it back to the origin), this
        creates an offset group above each object that absorbs its
        current world transform, then zeroes the object's own channels.
        The object doesn't move - its current position/rotation/scale is
        now held entirely on the new "<obj>_offset" group, and the
        object's own translate/rotate/scale channels read the clean
        default (0/0/0, 0/0/0, 1/1/1), exactly like a freshly-built
        rig control. Comma-separated names. A locked or connected (e.g.
        constrained) attribute on the object is skipped rather than
        failing the whole object, matching how zeroing a control by hand
        in the Channel Box behaves."""
        names = [n.strip() for n in (names_text or "").split(",") if n.strip()]
        if not names:
            return False, "No object name(s) given - type one or more names (comma-separated)."
        missing = [n for n in names if not cmds.objExists(n)]
        existing = [n for n in names if cmds.objExists(n)]
        if not existing:
            return False, "None of these objects exist in the scene: {}".format(", ".join(names))

        zeroed, already_zeroed, failed = [], [], []
        for obj in existing:
            try:
                if not cmds.objExists(obj):
                    failed.append(obj)
                    continue

                short_name = obj.split("|")[-1]
                parent_list = cmds.listRelatives(obj, parent=True, fullPath=True) or []
                parent = parent_list[0] if parent_list else None

                # Re-running Zero Out on a control that's already sitting
                # directly under its own "<obj>_offset" group should be a
                # no-op, not stack a second offset group on top of it.
                if parent and parent.split("|")[-1] == "{}_offset".format(short_name):
                    already_zeroed.append(obj)
                    continue

                # Unique offset group name, in case "<obj>_offset" is
                # already taken by something unrelated.
                offset_name = "{}_offset".format(short_name)
                base_offset_name = offset_name
                suffix = 1
                while cmds.objExists(offset_name):
                    offset_name = "{}{}".format(base_offset_name, suffix)
                    suffix += 1

                # Create the offset group and snap it onto the object's
                # current world transform (translate/rotate/scale/pivot),
                # so the object visually stays exactly where it is.
                offset_grp = cmds.group(empty=True, name=offset_name)
                world_matrix = cmds.xform(obj, query=True, worldSpace=True, matrix=True)
                cmds.xform(offset_grp, worldSpace=True, matrix=world_matrix)

                # Put the offset group where the object used to be in the
                # hierarchy, then put the object under the offset group.
                # cmds.parent preserves each node's world transform by
                # default, so nothing jumps.
                if parent:
                    cmds.parent(offset_grp, parent)
                cmds.parent(obj, offset_grp)

                # Now the object's own local transform is (at most, minus
                # float error) already identity - explicitly clean it to
                # exact 0/0/0, 0/0/0, 1/1/1 on whatever's settable.
                for attr, val in (("translateX", 0), ("translateY", 0), ("translateZ", 0),
                                   ("rotateX", 0), ("rotateY", 0), ("rotateZ", 0),
                                   ("scaleX", 1), ("scaleY", 1), ("scaleZ", 1)):
                    if not cmds.attributeQuery(attr, node=obj, exists=True):
                        continue
                    plug = "{}.{}".format(obj, attr)
                    try:
                        if cmds.getAttr(plug, lock=True) or cmds.listConnections(plug, source=True, destination=False):
                            continue
                        cmds.setAttr(plug, val)
                    except Exception:
                        pass

                zeroed.append(obj)
            except Exception:
                traceback.print_exc()
                failed.append(obj)

        if not zeroed and not already_zeroed:
            return False, "Nothing could be zeroed - see the Script Editor for details."

        msg_parts = []
        if zeroed:
            msg_parts.append("Zeroed out (offset group created): {}".format(", ".join(zeroed)))
        if already_zeroed:
            msg_parts.append("Already zeroed, skipped: {}".format(", ".join(already_zeroed)))
        msg = "  ".join(msg_parts)
        if failed:
            msg += "  (failed: {})".format(", ".join(failed))
        if missing:
            msg += "  (not found, skipped: {})".format(", ".join(missing))
        cmds.warning("[KRT] " + msg)
        return True, ""

    def parent_logic(self, children_text, parent_text):
        """Parent every listed child under the given parent - the Parent
        panel's Run. Children is comma-separated (Maya's own parent
        command accepts more than one child at once); Parent is a single
        object name. A child already under this parent is left alone
        (cmds.parent() errors on a no-op reparent) rather than failing
        the whole call."""
        children = [c.strip() for c in (children_text or "").split(",") if c.strip()]
        parent = (parent_text or "").strip()
        if not children:
            return False, "No child object(s) given - type one or more names (comma-separated)."
        if not parent:
            return False, "No Parent object given."
        if not cmds.objExists(parent):
            return False, "Parent object '{}' does not exist in the scene.".format(parent)
        missing = [c for c in children if not cmds.objExists(c)]
        existing = [c for c in children if cmds.objExists(c)]
        if not existing:
            return False, "None of these child objects exist in the scene: {}".format(", ".join(children))

        parent_short = parent.split("|")[-1]
        current_parents = {}
        for c in existing:
            p = cmds.listRelatives(c, parent=True, fullPath=True) or []
            current_parents[c] = p[0].split("|")[-1] if p else None
        to_parent = [c for c in existing if current_parents.get(c) != parent_short]
        already = [c for c in existing if c not in to_parent]

        failed = []
        if to_parent:
            try:
                cmds.parent(to_parent, parent)
            except Exception:
                # One bad child (a shape node, an object under itself, an
                # instanced/duplicate short name) shouldn't block the rest -
                # fall back to parenting one at a time.
                for c in to_parent:
                    try:
                        cmds.parent(c, parent)
                    except Exception as e:
                        failed.append((c, str(e)))

        succeeded = [c for c in to_parent if c not in [f[0] for f in failed]]
        if not succeeded and not already:
            return False, "Failed to parent: {}".format("; ".join("{} ({})".format(c, e) for c, e in failed))

        msg_parts = []
        if succeeded: msg_parts.append("Parented under '{}': {}".format(parent, ", ".join(succeeded)))
        if already: msg_parts.append("Already under '{}': {}".format(parent, ", ".join(already)))
        if missing: msg_parts.append("Not found, skipped: {}".format(", ".join(missing)))
        if failed: msg_parts.append("Failed: {}".format(", ".join(c for c, e in failed)))
        cmds.warning("[KRT] " + "  ".join(msg_parts))
        return True, ""

    # ------------------------------------------------------------------
    # Instance Object panel: instances a named object at a set of preset
    # transform offsets (ported from the user's own standalone
    # create_and_transform_instances_by_name script), plus an optional
    # custom-script override and a matching "Delete All Instances" that
    # can find and remove everything a given panel has created, even
    # across a save/reload (each created instance is tagged with a
    # hidden 'krtInstancePanel' string attribute holding the owning
    # panel's uuid, rather than relying on an in-memory list that would
    # be lost the moment KRT closes).
    # ------------------------------------------------------------------
    INSTANCE_DEFAULT_TRANSFORMS = [
        {"tx": -2.000, "ty": 0.000, "tz": 0.000, "rx": 0.0, "ry": -45.0, "rz": 0.0},
        {"tx": 2.000, "ty": 0.000, "tz": 0.000, "rx": 0.0, "ry": 90.0, "rz": 0.0},
        {"tx": 0.899, "ty": 2.669, "tz": 0.000, "rx": 90.0, "ry": 0.0, "rz": 0.0},
    ]

    INSTANCE_TAG_ATTR = "krtInstancePanel"

    def resolve_instance_transforms(self, script_code, func_call=""):
        """Runs an optional custom script (path to a .py file, or raw
        pasted code - identical convention to a SCRIPT panel's field) and
        returns whatever list of transform dicts it leaves behind in a
        variable called `transforms`. Returns KRT's own built-in 3-preset
        list (from the user's original create_and_transform_instances_by_name
        script) when no custom script is given, or when a custom script
        doesn't define `transforms`. Raises on a script error, same as
        run_script/run_script_global - the caller (create_instances_logic)
        is responsible for catching it."""
        script_code = (script_code or "").strip()
        if not script_code:
            return list(self.INSTANCE_DEFAULT_TRANSFORMS)

        ns = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}
        if os.path.exists(script_code):
            with open(script_code, 'r') as f:
                code_text = f.read()
        else:
            code_text = script_code
        exec(code_text, ns)
        if func_call and func_call.strip():
            exec(func_call.strip(), ns)

        transforms = ns.get("transforms")
        if not transforms:
            return list(self.INSTANCE_DEFAULT_TRANSFORMS)
        return transforms

    def create_instances_logic(self, target_name, script_code="", func_call="", panel_uuid=""):
        """Instances `target_name` once per entry in the resolved transform
        list (see resolve_instance_transforms), applying each entry's
        tx/ty/tz/rx/ry/rz - identical logic to the user's own
        create_and_transform_instances_by_name(), just driven by KRT's UI
        instead of being hardcoded to one object name. The ORIGINAL object
        is left completely untouched, exactly like cmds.instance() always
        does. Every created instance is tagged with panel_uuid (if given)
        so "Delete All Instances" can find them again later, even after a
        save/reload."""
        target_name = (target_name or "").strip()
        if not target_name:
            return False, "No object given - type or Get Selected an object name to instance."
        if not cmds.objExists(target_name):
            return False, "Object '{}' does not exist in the scene.".format(target_name)

        try:
            transforms = self.resolve_instance_transforms(script_code, func_call)
        except Exception as e:
            log_crash("Instance Object: custom script", e)
            return False, "Custom instance script failed: {}".format(traceback.format_exc())

        if not transforms:
            return False, "No transforms to instance with (custom script left 'transforms' empty)."

        created = []
        try:
            for t in transforms:
                inst_nodes = cmds.instance(target_name, smartTransform=True)
                obj_name = inst_nodes[0]
                cmds.setAttr(
                    "{}.translate".format(obj_name),
                    float(t.get("tx", 0.0)), float(t.get("ty", 0.0)), float(t.get("tz", 0.0)),
                    type="double3")
                cmds.setAttr(
                    "{}.rotate".format(obj_name),
                    float(t.get("rx", 0.0)), float(t.get("ry", 0.0)), float(t.get("rz", 0.0)),
                    type="double3")
                if panel_uuid:
                    if not cmds.attributeQuery(self.INSTANCE_TAG_ATTR, node=obj_name, exists=True):
                        cmds.addAttr(obj_name, longName=self.INSTANCE_TAG_ATTR, dataType="string")
                    tag_plug = "{}.{}".format(obj_name, self.INSTANCE_TAG_ATTR)
                    cmds.setAttr(tag_plug, panel_uuid, type="string")
                    cmds.setAttr(tag_plug, lock=True)
                created.append(obj_name)
        except Exception as e:
            log_crash("Instance Object: create_instances_logic", e)
            if created:
                cmds.select(created, replace=True)
            return False, "Failed after creating {} instance(s) of '{}': {}".format(
                len(created), target_name, e)

        cmds.select(created, replace=True)
        cmds.warning("[KRT] Created {} instance(s) of '{}': {}".format(
            len(created), target_name, ", ".join(created)))
        return True, ""

    def delete_instances_by_panel_logic(self, panel_uuid):
        """Deletes every instance tagged with panel_uuid (see
        create_instances_logic) - Delete All Instances. Scans every
        transform in the scene for the tag rather than keeping an
        in-memory list, so this still works correctly after a JSON
        save/reload, a scene reopen, or a KRT restart."""
        if not panel_uuid:
            return False, "This panel has no id to look up instances by."
        tagged = []
        for node in (cmds.ls(type="transform") or []):
            plug = "{}.{}".format(node, self.INSTANCE_TAG_ATTR)
            if not cmds.attributeQuery(self.INSTANCE_TAG_ATTR, node=node, exists=True):
                continue
            try:
                if cmds.getAttr(plug) == panel_uuid:
                    tagged.append(node)
            except Exception:
                continue
        if not tagged:
            return False, "No instances created by this panel were found in the scene."
        try:
            cmds.delete(tagged)
        except Exception as e:
            return False, "Failed to delete some instances: {}".format(e)
        cmds.warning("[KRT] Deleted {} instance(s): {}".format(len(tagged), ", ".join(tagged)))
        return True, ""

    def load_skin_cluster_logic(self, path, meshes=None, show_popup=True):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try:
            from .utils import ensure_skin_ready_for_import, fast_import_skin
            # Use cmds.select (not pm.select) to avoid pymel's spurious
            # "Cannot find Maya documentation" error on installs without docs.
            mesh_list = []
            if meshes and meshes.strip() != "":
                mesh_list = [m.strip() for m in meshes.split(",") if m.strip()]
                if mesh_list:
                    cmds.select(mesh_list, replace=True)

            # Before mgear's own import runs: make sure every mesh this file
            # covers already has every influence the file expects on its
            # CURRENT skinCluster (found by history, not name). mgear's
            # importSkin silently drops the weight for any influence that
            # isn't already present instead of adding it, which is what was
            # corrupting a mesh on re-import whenever its current skin was
            # missing a joint that existed when the skin was saved (a newly
            # added influence, a different bind setup, etc - requests #1/#3).
            #
            # NOTE: mgear's importSkin() always processes every object
            # stored in the file, regardless of the current selection or
            # this panel's Meshes field (that field only decides what gets
            # *selected* beforehand, which importSkin itself ignores) - so
            # this pre-pass intentionally covers the whole file too, not
            # just `mesh_list`, to match what will actually be imported.
            #
            # Stage 16, request #1: the naming-convention check moved from
            # KRT's own launch (scanning the whole scene every time) to
            # right here, scoped to just the mesh(es) this file actually
            # covers - same "whole file, not just the Meshes field" scope
            # as the influence pre-pass above, for the same reason.
            file_meshes = read_skin_file_meshes(path)
            prompt_skincluster_naming_check(
                self.main_window, file_meshes, show_popup=show_popup)

            # Disable Maya's undo queue for the actual weight-writing work
            # below (influence adds + the weight import itself). A heavy
            # character mesh can be skinned to 500+ joints, and every
            # skinCluster edit on a mesh that size is, by default, fully
            # undoable - Maya's undo system snapshots the WHOLE weight
            # array (not just what changed) for each one. Importing a
            # file like that was observed ballooning Maya's memory into
            # the 100+ GB range and crashing the machine outright. Nobody
            # is going to want to undo an import one internal step at a
            # time anyway - a bad import gets fixed by re-importing, not
            # by walking back through hundreds of undo entries - so undo
            # is turned off for this whole load and always restored after,
            # success or failure.
            undo_was_on = cmds.undoInfo(query=True, state=True)
            if undo_was_on:
                cmds.undoInfo(state=False)
            try:
                ensure_skin_ready_for_import(path)

                # fast_import_skin() (utils.py) - same .jSkin/.gSkin file
                # mgear's own importSkin() would read, just fast on heavy
                # meshes (see the "Fast SkinCluster save/import" section
                # there); any vertex-count mismatch, or any error in the
                # fast path itself, falls back to mgear's own importSkin()
                # automatically.
                fast_import_skin(path)
            finally:
                if undo_was_on:
                    cmds.undoInfo(state=True)
            return True, ""
        except Exception as e:
            log_crash("Skin import: {}".format(path), e)
            return False, str(e)

    def _load_tweaker_module(self):
        """Dynamically (re)load PanelScripts/Tweaker.py, which sits beside
        the KRT package itself, so the tweaker algorithm can be hand-edited
        there later without touching KRT's own code (request #5). Returns
        the loaded module, or None (and a Script Editor warning) if it
        can't be found/loaded."""
        try:
            import importlib.util
            krt_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(krt_dir, "PanelScripts", "Tweaker.py")
            if not os.path.isfile(script_path):
                cmds.warning("[KRT] PanelScripts/Tweaker.py not found next to the KRT package.")
                return None
            spec = importlib.util.spec_from_file_location("krt_panel_tweaker", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            traceback.print_exc()
            return None

    def run_reskin_logic(self, meshes, controls=None, scale_value=1.0):
        """Scale zero or more controls up, re-skin the given meshes, then put
        every control back exactly where it was - the SkinCluster panel's
        Re-Skin option.

        `controls` is a list. An empty/None list means "no scaling" - the
        caller (the panel's execute()) is the one deciding whether to call
        this at all based on whether any control was listed, since an
        empty list here still performs a plain re-skin if asked to.

        The point of the scaling is that the re-bind recomputes each
        influence's bind matrix from the CURRENT pose, so temporarily scaling
        a control changes what the rebound skin considers its rest state.
        Which is also why the restore is in a `finally`: if the re-skin
        itself throws halfway through, the rigger must not be left with a
        control silently stuck at 10x scale. Every control that exists gets
        its scale read up front - if any listed control doesn't exist, the
        whole call fails before anything is touched (no half-scaled scene).

        Returns (success, message)."""
        from .utils import re_skin_meshes

        meshes = [m.strip() for m in (meshes or []) if m and m.strip()]
        if not meshes:
            meshes = cmds.ls(selection=True) or []
        if not meshes:
            return False, ("No meshes to re-skin - fill the SkinCluster panel's Meshes field "
                           "or select the skinned mesh(es) first.")

        controls = [c.strip() for c in (controls or []) if c and c.strip()]

        # Read every control's current scale before touching anything, so a
        # missing/unreadable control fails the whole call up front rather
        # than leaving earlier controls in the list scaled with no way back.
        originals = {}
        for control in controls:
            if not cmds.objExists(control):
                return False, "Re-Skin scale control '{}' does not exist in the scene.".format(control)
            try:
                originals[control] = cmds.getAttr(control + ".scale")[0]
            except Exception:
                return False, "Could not read the current scale of '{}'.".format(control)

        scaled = []  # controls actually changed, so only these get restored
        try:
            if controls and float(scale_value) != 1.0:
                for control in controls:
                    try:
                        cmds.setAttr(control + ".scale", scale_value, scale_value, scale_value)
                        scaled.append(control)
                    except Exception as e:
                        return False, ("Could not scale '{}' to {} (is it locked or connected?): {}"
                                       .format(control, scale_value, e))
            done, errors = re_skin_meshes(meshes)
        finally:
            # Always put every scaled control back, even when the re-skin
            # blew up half way. Only the ones actually moved, though - a
            # control with a locked scale shouldn't be poked (and warned
            # about) for a restore that isn't needed.
            for control in scaled:
                try:
                    cmds.setAttr(control + ".scale", *originals[control])
                except Exception:
                    cmds.warning("[KRT] Re-skin finished but '{}' could not be scaled back to {} "
                                 "- check it by hand.".format(control, tuple(originals[control])))

        if errors and not done:
            return False, "Re-skin failed:\n" + "\n".join(errors)
        msg = "Re-skinned {} mesh(es).".format(done)
        if controls:
            msg += " (scaled {} to {} during the rebind, then restored {})".format(
                ", ".join("'{}'".format(c) for c in controls), scale_value,
                "them" if len(controls) > 1 else "it")
        if errors:
            msg += "\nSkipped/failed:\n" + "\n".join(errors)
        cmds.warning("[KRT] " + msg)
        return True, msg

    def run_tweaker_logic(self, vertex_names, additional_meshes, use_bind_scale=True,
                           bind_scale=0.01, influence_radius=0.08, full_weight_radius=0.0001,
                           falloff=2.0):
        """Create a Tweaker setup (PanelScripts/Tweaker.py's own
        create_tweaker_setup) from `vertex_names`, then bind any
        `additional_meshes` to the same offsets via its
        add_additional_tweaker_meshes - the Tweaker panel's CREATE button.

        Every field here mirrors the values already used in the pipeline's
        real TweakerMain() calling convention (see the .txt example that
        was handed off): falloff_mode is always "center", control_size/
        offset/direction and follicle_scale_source are always the same -
        only the values that actually vary call to call (bind scale and
        whether the bind uses it, influence/full-weight radius, falloff)
        are exposed on the panel. bind_scale used to be a fixed 0.01 here;
        the real TweakerMain() now takes it as its own settable value, so
        the panel does too - 0.01 is just this function's default.
        """
        tweaker = self._load_tweaker_module()
        if not tweaker:
            return False, "Could not load PanelScripts/Tweaker.py - see Script Editor."
        if not vertex_names:
            return False, "No vertex names provided."

        try:
            tweaker.create_tweaker_setup(
                vertex_name=vertex_names,
                bind_scale=bind_scale,
                use_bind_scale=use_bind_scale,
                influence_radius=influence_radius,
                full_weight_radius=full_weight_radius,
                falloff=falloff,
                falloff_mode="center",
                control_size=0.02,
                control_offset_y=0.0,
                control_direction="-z",
                copy_plane_skin=True,
                follicle_scale_source="local_C0_ctl",
            )

            if additional_meshes:
                source_mesh = vertex_names[0].split(".vtx[")[0]
                other_sources = set(
                    v.split(".vtx[")[0] for v in vertex_names
                    if v.split(".vtx[")[0] != source_mesh)
                if other_sources:
                    cmds.warning(
                        "[KRT] Tweaker vertices span multiple meshes ({} and {}); "
                        "Additional Meshes will be bound to {} only.".format(
                            source_mesh, ", ".join(other_sources), source_mesh))
                tweaker.add_additional_tweaker_meshes(
                    additional_meshes=additional_meshes,
                    source_mesh=source_mesh,
                    bind_scale=bind_scale,
                    use_bind_scale=False,
                )
            return True, ""
        except Exception:
            return False, traceback.format_exc()

    def get_tweaker_target_meshes(self, vertex_names, additional_meshes):
        """Resolve the actual Tweaker-created duplicate mesh(es) - the ones
        that hold the real skinCluster, not the original source meshes -
        for a Tweaker panel's Vertices/Additional Meshes fields, via
        PanelScripts/Tweaker.py's own system_names() naming convention.
        Used to auto-fill the Tweaker panel's own Meshes field on a
        successful Create (SortablePanel._execute_tweaker), and as the
        Save Skin action's fallback when that Meshes field is left empty
        (e.g. an older panel/session that predates it)."""
        tweaker = self._load_tweaker_module()
        if not tweaker:
            return []

        sources = []
        seen = set()
        for v in vertex_names:
            src = v.split(".vtx[")[0]
            if src and src not in seen:
                seen.add(src); sources.append(src)
        for m in additional_meshes:
            if m and m not in seen:
                seen.add(m); sources.append(m)

        targets = []
        for src in sources:
            if not cmds.objExists(src):
                continue
            try:
                _, target, _, _, _, _, _ = tweaker.system_names(src)
            except Exception:
                continue
            if cmds.objExists(target) and target not in targets:
                targets.append(target)
        return targets

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
                    publish_dir = panel.field.text(); break
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

    def page_docs(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)

        header = QtWidgets.QLabel("<b>📖 KRT DOCUMENTATION</b>")
        header.setStyleSheet("font-size: 15px; color: #2bb5a8;")
        layout.addWidget(header)

        browser = QtWidgets.QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(
            "QTextBrowser { background:#1e1e1e; border:1px solid #333; color:#ddd; "
            "padding: 14px; font-size: 13px; }")
        browser.setHtml(self._docs_html())
        layout.addWidget(browser)

        return page

    def _docs_html(self):
        """Stage 18, request #4: the Documentation tab used to just say
        'Documentation' with nothing under it - this is the actual written
        guide to KRT, covering every tab and panel type. Kept as one plain
        HTML string (styled inline, since QTextBrowser doesn't read an
        external stylesheet) so it's easy to extend as new features land."""
        return """
        <style>
            h2 { color: #2bb5a8; margin-top: 18px; margin-bottom: 4px; }
            h3 { color: #4fc3f7; margin-top: 12px; margin-bottom: 2px; }
            p, li { color: #ccc; line-height: 1.5; }
            b.tag { color: #a1887f; }
            code { background:#2a2a2a; padding: 1px 5px; border-radius: 3px; color:#f0c674; }
            .icon { font-size: 14px; }
        </style>

        <h2>Overview</h2>
        <p>KRT (Kleem Rigging Tool) is a module-based biped/creature rig-building pipeline on top
        of mGear Shifter. A rig is assembled as a sequence of <b>panels</b> inside a
        <b>LOD workspace</b> - each panel is one step (run a script, import a model, load a
        skinCluster, build a module, etc.) - plus a <b>Module Graph</b> where the actual mGear
        guide components live and connect to each other.</p>

        <h2>Top Tabs</h2>
        <h3>📂 File</h3>
        <p>Save/Load the current pipeline as a KRT JSON, auto-save settings, recent files list,
        and session comments. This is where a rig session's whole state - LODs, panels, the
        Module Graph, and the Guide Settings tab - is written to or read from disk.</p>

        <h3>🛠️ Rig Build Workspace</h3>
        <p>The main step-by-step builder. The left sidebar lists your <b>LODs</b> (LOD0, LOD1...);
        each LOD holds its own stack of panels that run top-to-bottom when you build. See
        "Panel Types" below for what each kind of panel does.</p>

        <h3>🔌 Module Graph Editor</h3>
        <p>A node-graph view of the actual mGear guide components (arms, legs, spine, a full
        Plebe biped template, or a Custom Module from a standalone <code>.sgt</code> file).
        Drag from a node's right edge to another node's body to parent them; Tab or double-click
        empty canvas to search for a component to add. Ctrl+drag pans, Shift+click multi-selects,
        Ctrl+Z / Ctrl+Shift+Z undo/redo graph changes (not Maya scene changes). The Guide Settings
        panel on the right holds the rig-wide Shifter build options and Custom Steps, and now
        saves/loads with the normal pipeline JSON, not just the separate Save/Load Guides buttons.</p>

        <h3>🧰 Rigging Workspace</h3>
        <p>A browsable library of your own scripts/tools, independent of any pipeline file - always
        available regardless of what session is open. Defaults to
        <code>P:\\pipeline_database\\Maya\\Scripts\\ONE</code> but you can point it anywhere; your
        choice is remembered per-user. Double-click a script to open it in VS Code (or KRT's own
        built-in editor if VS Code isn't installed on this machine); "Show in Explorer" jumps to
        the file on disk.</p>

        <h3>🎬 Playblast</h3>
        <p>Create and review playblasts without leaving KRT. Give it an existing camera, or a
        group whose bounding box it should auto-frame with a temporary camera. Set a start/end
        frame and click Create Playblast - the result plays back right in the big preview screen,
        and every past playblast for this session stays listed in the dropdown at the bottom so
        you can flip back through them. The Animation (.anim) field loads a Studio Library
        animation clip straight onto whatever controls in the scene match the Controls Filter
        below it (e.g. <code>*_ctl</code>) before capturing - Browse picks the clip's <code>.anim</code>
        folder and auto-fills Start/End from the clip's own frame range. This reuses Studio
        Library's own "mutils" package (from the studio's shared install) to paste the actual
        animation curves, so it needs that install to be reachable on this machine.</p>

        <h3>👤 Profile</h3>
        <p>Your own persistent notes (autosaved, per-user, always here regardless of which
        pipeline is open) - and, at KRT launch, a warning if the last session didn't close
        cleanly, with the option to restore the most recent auto-saved backup.</p>

        <h2>Panel Types (Rig Build Workspace)</h2>
        <p>Every panel type has its own icon and background tint so you can tell them apart at a
        glance. Fields marked <b class="tag">read-only (brown)</b> are always set for you by a
        Browse/Save/Switch Version action - never typed by hand.</p>

        <h3>🐍 Script</h3>
        <p>Runs a Python or MEL file (or pasted code) inside KRT's own private namespace for this
        session tab. Good for anything that only needs to matter while this rig is being built.</p>

        <h3>🌐 Maya Global Script</h3>
        <p>Same as Script, but runs Python straight into Maya's real <code>__main__</code> session
        instead of KRT's private namespace - use this for anything you want to still be able to
        call from Maya's own Script Editor afterward, without re-running it by hand.</p>

        <h3>🧊 Import 3D Model <span style="color:#888;">— read-only field</span></h3>
        <p>Imports any 3D file - <code>.ma</code>, <code>.mb</code>, <code>.fbx</code>,
        <code>.obj</code>, or <code>.abc</code> - auto-detecting the right importer from the file's
        extension. One panel type covers everything you'd have previously split across separate
        "Maya .MA" and "Import 3D" panels.</p>

        <h3>🦴 Skin JSON <span style="color:#888;">— read-only field</span></h3>
        <p>Saves/loads a skinCluster as KRT's own <code>.jSkin</code>/<code>.json</code> file, with
        a Meshes field to scope the export/import and a Joints field + "Bind All" for a quick bind.
        Save/Load automatically checks for skinCluster naming mismatches on just the mesh(es)
        involved and offers to fix them.</p>

        <h3>🎨 Control Shapes <span style="color:#888;">— read-only field</span></h3>
        <p>Saves/loads control-curve shapes (CV positions) as KRT's own JSON format, matched back
        onto controls by name on import.</p>

        <h3>📤 Publish Path <span style="color:#888;">— read-only field</span></h3>
        <p>A folder this rig's finished output is expected to land in. Validates that the folder
        exists rather than running anything.</p>

        <h3>🎚️ Tweaker <span style="color:#888;">— read-only field</span></h3>
        <p>Runs the studio's Tweaker weighting setup (from <code>PanelScripts/Tweaker.py</code>) on
        the given vertices/meshes, with Influence Radius / Full Weight Radius / Falloff controls,
        then saves/loads its own skin file the same way the Skin JSON panel does.</p>

        <h3>🧩 Module Bubbles</h3>
        <p>Holds one or more module "bubbles" pulled from the Module Graph (or a raw script/
        <code>.sgt</code> file). Clicking its green LOAD button draws every bubble's guide, builds
        them all together in one Shifter build, runs each node's post-build script, then cleans up
        every guide the batch touched.</p>

        <h2>Tips</h2>
        <ul>
            <li>Right-click any panel for its full menu - Add Panel above/below, Duplicate, Replace
            All Paths, and type-specific actions (Load/Save/Switch Version, Edit in VS Code...).</li>
            <li>A red ⚠ on a Module Graph node means its custom script errored last build - click it
            for the error, fix and re-save the script to clear it.</li>
            <li>If KRT shows a "didn't close normally last time" message at launch, it's offering to
            restore your most recent auto-saved backup - safe to accept, it just runs a normal
            Load JSON Pipeline on that backup.</li>
        </ul>

        <p style="color:#666; font-size:11px; margin-top:18px;">
        KRT owner / point of contact: Vishal Nagpal &lt;vishalnagpal878@gmail.com&gt;
        </p>
        """

    def page_profile(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header = QtWidgets.QLabel("<b>USER PROFILE</b>")
        header.setStyleSheet("font-size: 16px; color: #2bb5a8;")
        layout.addWidget(header)

        notes_header = QtWidgets.QHBoxLayout()
        lbl_notes = QtWidgets.QLabel(
            "<b>Notes</b> &nbsp;<span style='color:#888; font-weight:normal;'>"
            "(yours alone - not tied to any pipeline file, always here when KRT opens)</span>"
        )
        notes_header.addWidget(lbl_notes)
        notes_header.addStretch()
        self.lbl_notes_saved = QtWidgets.QLabel("Saved")
        self.lbl_notes_saved.setStyleSheet("color: #888; font-size: 11px;")
        notes_header.addWidget(self.lbl_notes_saved)
        layout.addLayout(notes_header)

        self.notes_edit = QtWidgets.QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "Jot down anything here - reminders, TODOs, future planning...\n"
            "Saved automatically, per-user, on this machine."
        )
        self.notes_edit.setPlainText(self.session_manager.get_notes())
        self.notes_edit.setStyleSheet(
            "background:#1e1e1e; border:1px solid #333; color:white; "
            "padding:8px; font-family:'Consolas'; font-size:12px;"
        )
        layout.addWidget(self.notes_edit)

        self._notes_save_timer = QtCore.QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.timeout.connect(self.save_user_notes)
        self.notes_edit.textChanged.connect(self.on_notes_changed)

        return page

    def on_notes_changed(self):
        self.lbl_notes_saved.setText("Saving...")
        self._notes_save_timer.start(800)

    def save_user_notes(self):
        self.session_manager.set_notes(self.notes_edit.toPlainText())
        self.lbl_notes_saved.setText("Saved")

    # =====================================================
    # Rigging Workspace (Stage 17): a browsable library of custom scripts/
    # tools, defaulting to DEFAULT_SCRIPTS_LIB_PATH but editable (and saved)
    # per user. Not tied to any pipeline JSON - same "always here regardless
    # of which session is open" idea as the Notes page above.
    # =====================================================

    def _scripts_lib_current_path(self):
        return self.session_manager.data.get("scripts_library_path", DEFAULT_SCRIPTS_LIB_PATH)

    def page_scripts(self):
        page = QtWidgets.QWidget()
        outer_layout = QtWidgets.QVBoxLayout(page)
        outer_layout.setContentsMargins(20, 15, 20, 15)
        outer_layout.setSpacing(8)

        header = QtWidgets.QLabel("<b>🛠️ RIGGING WORKSPACE</b>")
        header.setStyleSheet("font-size: 15px; color: #2bb5a8;")
        outer_layout.addWidget(header)

        # ── Script / Tools Library ──────────────────────────────────────────
        # Stage 20: the LOD Build Manager that used to live below this as a
        # second section has been moved out - it's now a proper panel type
        # (LOD_LOADER) addable inside the Rig Build Workspace itself, same as
        # Control Shapes / Module Bubbles panels. See add_lod_loader_panel /
        # build_lod_sequence / widgets.LodLoaderPanel.
        lib_group = QtWidgets.QGroupBox("📜 Script / Tools Library")
        lib_group.setStyleSheet(SECTION_GROUPBOX_STYLE)
        lib_layout = QtWidgets.QVBoxLayout(lib_group)

        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(QtWidgets.QLabel("Scripts Folder:"))
        self.scripts_lib_field = QtWidgets.QLineEdit(self._scripts_lib_current_path())
        self.scripts_lib_field.setToolTip(
            "Defaults to {} for everyone - change it and it's remembered just "
            "for you, saved in your own KRT preferences on this machine.".format(DEFAULT_SCRIPTS_LIB_PATH))
        self.scripts_lib_field.editingFinished.connect(
            lambda: self.set_scripts_lib_path(self.scripts_lib_field.text().strip()))
        btn_browse_lib = QtWidgets.QPushButton("📂 Browse")
        btn_browse_lib.clicked.connect(self.browse_scripts_lib_path)
        btn_reset_lib = QtWidgets.QPushButton("↺ Reset to Default")
        btn_reset_lib.setToolTip("Reset to " + DEFAULT_SCRIPTS_LIB_PATH)
        btn_reset_lib.clicked.connect(lambda: self.set_scripts_lib_path(DEFAULT_SCRIPTS_LIB_PATH))
        btn_refresh_lib = QtWidgets.QPushButton("🔄 Refresh")
        btn_refresh_lib.clicked.connect(self.refresh_scripts_lib_list)
        path_row.addWidget(self.scripts_lib_field)
        path_row.addWidget(btn_browse_lib)
        path_row.addWidget(btn_reset_lib)
        path_row.addWidget(btn_refresh_lib)
        lib_layout.addLayout(path_row)

        # Stage 19, request #2: search/filter the library list.
        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("🔍"))
        self.scripts_lib_search = QtWidgets.QLineEdit()
        self.scripts_lib_search.setPlaceholderText("Search scripts by name or folder...")
        self.scripts_lib_search.textChanged.connect(self.filter_scripts_lib_list)
        search_row.addWidget(self.scripts_lib_search)
        self.lbl_scripts_search_count = QtWidgets.QLabel("")
        self.lbl_scripts_search_count.setStyleSheet("color: #888;")
        search_row.addWidget(self.lbl_scripts_search_count)
        lib_layout.addLayout(search_row)

        self.scripts_lib_list = QtWidgets.QListWidget()
        # Stage 19, request #2: padding + a border between rows (plus a
        # hover highlight) so scripts read as a list of separate entries
        # instead of visually running together.
        self.scripts_lib_list.setStyleSheet(
            "QListWidget { background:#1e1e1e; border:1px solid #333; color: white; font-family:'Consolas'; }"
            "QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #333; }"
            "QListWidget::item:selected { background:#2c3e47; border: 1px solid #2bb5a8; color: white; }"
            "QListWidget::item:hover { background:#262626; }")
        self.scripts_lib_list.itemDoubleClicked.connect(self.open_scripts_lib_item)
        lib_layout.addWidget(self.scripts_lib_list, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_open = QtWidgets.QPushButton("📝 Open (VS Code / Editor)")
        btn_open.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold; padding: 6px 12px;")
        btn_open.clicked.connect(self.open_selected_scripts_lib_item)
        btn_show = QtWidgets.QPushButton("📂 Show in Explorer")
        btn_show.clicked.connect(self.show_selected_scripts_lib_item)
        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_show)
        btn_row.addStretch()
        lib_layout.addLayout(btn_row)

        self.lbl_scripts_lib_status = QtWidgets.QLabel("")
        self.lbl_scripts_lib_status.setStyleSheet("color: #888;")
        lib_layout.addWidget(self.lbl_scripts_lib_status)

        outer_layout.addWidget(lib_group, 1)

        self.refresh_scripts_lib_list()
        return page

    def browse_scripts_lib_path(self):
        start = self._scripts_lib_current_path()
        kwargs = {"fileMode": 3, "caption": "Select Scripts Folder"}
        if start and os.path.exists(start):
            kwargs["startingDirectory"] = start
        res = cmds.fileDialog2(**kwargs)
        if res:
            self.set_scripts_lib_path(res[0])

    def set_scripts_lib_path(self, path):
        path = (path or "").strip() or DEFAULT_SCRIPTS_LIB_PATH
        self.session_manager.data["scripts_library_path"] = path
        self.session_manager.save_session()
        if hasattr(self, "scripts_lib_field"):
            self.scripts_lib_field.setText(path)
        self.refresh_scripts_lib_list()

    def refresh_scripts_lib_list(self):
        if not hasattr(self, "scripts_lib_list"):
            return
        self.scripts_lib_list.clear()
        root = self._scripts_lib_current_path()
        if not root or not os.path.isdir(root):
            self.lbl_scripts_lib_status.setText("Folder not found: {}".format(root))
            return
        found = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn.lower().endswith((".py", ".mel")):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, root)
                    found.append((rel, full))
        found.sort(key=lambda t: t[0].lower())
        for rel, full in found:
            item = QtWidgets.QListWidgetItem(rel)
            item.setToolTip(full)
            item.setData(QtCore.Qt.UserRole, full)
            self.scripts_lib_list.addItem(item)
        self.lbl_scripts_lib_status.setText("{} script(s) found in {}".format(len(found), root))
        # Stage 19: re-apply whatever search text is already typed, so a
        # Refresh mid-search doesn't silently drop back to showing everything.
        self.filter_scripts_lib_list()

    def filter_scripts_lib_list(self, text=None):
        """Stage 19, request #2: live filter for the Script/Tools Library
        list, purely visual (setHidden) - matches against the relative
        path shown, so searching "Tweaker" finds a Tweaker.py anywhere
        under the library root, not just at the top level."""
        if not hasattr(self, "scripts_lib_list"):
            return
        if text is None:
            text = self.scripts_lib_search.text() if hasattr(self, "scripts_lib_search") else ""
        q = (text or "").strip().lower()
        shown = 0
        total = self.scripts_lib_list.count()
        for i in range(total):
            item = self.scripts_lib_list.item(i)
            match = (not q) or (q in item.text().lower())
            item.setHidden(not match)
            if match:
                shown += 1
        if hasattr(self, "lbl_scripts_search_count"):
            self.lbl_scripts_search_count.setText("" if not q else "{} / {}".format(shown, total))

    def open_scripts_lib_item(self, item):
        self.open_script_externally(item.data(QtCore.Qt.UserRole))

    def open_selected_scripts_lib_item(self):
        item = self.scripts_lib_list.currentItem()
        if not item:
            cmds.warning("Select a script first.")
            return
        self.open_script_externally(item.data(QtCore.Qt.UserRole))

    def show_selected_scripts_lib_item(self):
        item = self.scripts_lib_list.currentItem()
        if not item:
            cmds.warning("Select a script first.")
            return
        path = item.data(QtCore.Qt.UserRole).replace("/", "\\")
        try:
            subprocess.Popen('explorer /select,"{}"'.format(path))
        except Exception as e:
            cmds.warning("Could not open Explorer: {}".format(e))

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

    # =====================================================
    # Playblast review (Stage 17): create a playblast (with a given camera,
    # or an auto-built one framing a group's bounding box if no camera is
    # given), and play it back right here via an embedded video player.
    #
    # The "animation JSON" field/pattern are wired up and saved but the
    # actual apply-animation step is a placeholder (see create_playblast) -
    # it needs a sample of the user's actual anim-JSON format before it can
    # do anything real with it.
    # =====================================================

    def get_playblast_dir(self):
        """Where playblasts land: a 'playblasts' subfolder next to the
        current session's own KRT json (same auto-pathed-beside-the-json
        convention as the Guide Path field and step caches), or the user's
        home folder if this session hasn't been saved anywhere yet."""
        base_dir = os.path.dirname(self.session_path) if self.session_path else os.path.expanduser("~")
        d = os.path.join(base_dir, "playblasts").replace("\\", "/")
        if not os.path.exists(d):
            try:
                os.makedirs(d)
            except Exception:
                pass
        return d

    def create_auto_camera_from_group(self, group):
        """No camera given - build one that frames `group`'s bounding box.
        Creates a temporary camera, points it at the group's center from
        far enough away (based on the bbox diagonal and the camera's own
        field of view, plus some padding) to fit the whole thing in frame,
        aimed via a throwaway aimConstraint. The caller is responsible for
        deleting this camera once the playblast is done."""
        if not group or not cmds.objExists(group):
            return None
        try:
            bbox = cmds.exactWorldBoundingBox(group)
        except Exception:
            bbox = cmds.xform(group, query=True, boundingBox=True, worldSpace=True)
        cx, cy, cz = (bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0, (bbox[2] + bbox[5]) / 2.0
        sx, sy, sz = bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]
        diag = (sx * sx + sy * sy + sz * sz) ** 0.5
        if diag <= 0.0001:
            diag = 10.0

        cam_tfm, _cam_shape = cmds.camera()
        cam_tfm = cmds.rename(cam_tfm, "KRT_playblast_cam#")
        hfov = cmds.camera(cam_tfm, query=True, horizontalFieldOfView=True) or 54.4
        distance = (diag * 0.7) / max(0.01, math.tan(math.radians(hfov / 2.0)))
        distance = max(distance, diag)

        cmds.setAttr(cam_tfm + ".translate", cx, cy, cz + distance, type="double3")
        aim = cmds.aimConstraint(group, cam_tfm, aimVector=(0, 0, -1), upVector=(0, 1, 0),
                                  worldUpType="vector", worldUpVector=(0, 1, 0))
        cmds.delete(aim)
        return cam_tfm

    # ------------------------------------------------------------------
    # Generate Camera (Stage 38): a second, fully manual way to get a
    # camera to playblast through when there's no existing one - full
    # control over position plus the same lens settings the Attribute
    # Editor's Camera Shape tab shows, instead of only the automatic
    # frame-a-group's-bounding-box option above.
    # ------------------------------------------------------------------
    def pb_compute_angle_of_view(self, focal_length, horizontal_film_aperture_mm=36.0):
        """Angle of View (degrees) for a given focal length (mm), assuming
        Maya's default 36mm (1.41732in) horizontal film aperture - the
        same relationship the Attribute Editor's Camera Shape tab keeps
        Angle of View synced to Focal Length with. Returns None for a
        non-positive focal length (can't compute, avoid a ZeroDivisionError)."""
        try:
            focal_length = float(focal_length)
        except (TypeError, ValueError):
            return None
        if focal_length <= 0:
            return None
        return 2.0 * math.degrees(math.atan(horizontal_film_aperture_mm / (2.0 * focal_length)))

    def pb_update_gen_camera_aov(self, *_args):
        """Wired to the Focal Length field's textChanged - keeps the
        read-only Angle of View field in sync, live, the same way Maya's
        own Camera Shape tab keeps the two in sync with each other."""
        if not hasattr(self, "pb_gen_aov_display"):
            return
        aov = self.pb_compute_angle_of_view(self.pb_gen_focal_length.text().strip())
        self.pb_gen_aov_display.setText("{:.2f}".format(aov) if aov is not None else "")

    def pb_generate_camera(self, pos_x, pos_y, pos_z, focal_length, camera_scale,
                            near_clip, far_clip, auto_render_clip_planes,
                            rot_x=0.0, rot_y=0.0, rot_z=0.0):
        """Creates a camera at the given position/rotation with the given
        lens settings (all straight off the Generate Camera UI's fields)
        and returns its transform name. rot_x/y/z default to 0 (looking
        down -Z, same as a plain new Maya camera) when not given, so
        existing callers keep working unchanged."""
        cam_tfm, cam_shape = cmds.camera()
        cam_tfm = cmds.rename(cam_tfm, "KRT_generated_cam#")
        cam_shape = (cmds.listRelatives(cam_tfm, shapes=True, fullPath=True) or [cam_shape])[0]

        cmds.setAttr(cam_tfm + ".translate", float(pos_x), float(pos_y), float(pos_z), type="double3")
        cmds.setAttr(cam_tfm + ".rotate", float(rot_x), float(rot_y), float(rot_z), type="double3")
        cmds.setAttr(cam_shape + ".focalLength", float(focal_length))
        cmds.setAttr(cam_shape + ".cameraScale", float(camera_scale))
        cmds.setAttr(cam_shape + ".nearClipPlane", float(near_clip))
        cmds.setAttr(cam_shape + ".farClipPlane", float(far_clip))
        if cmds.attributeQuery("autoRenderClipPlanes", node=cam_shape, exists=True):
            cmds.setAttr(cam_shape + ".autoRenderClipPlanes", bool(auto_render_clip_planes))

        return cam_tfm

    def pb_generate_camera_clicked(self):
        try:
            pos_x = float(self.pb_gen_pos_x.text().strip() or 0)
            pos_y = float(self.pb_gen_pos_y.text().strip() or 0)
            pos_z = float(self.pb_gen_pos_z.text().strip() or 0)
            rot_x = float(self.pb_gen_rot_x.text().strip() or 0) if hasattr(self, "pb_gen_rot_x") else 0.0
            rot_y = float(self.pb_gen_rot_y.text().strip() or 0) if hasattr(self, "pb_gen_rot_y") else 0.0
            rot_z = float(self.pb_gen_rot_z.text().strip() or 0) if hasattr(self, "pb_gen_rot_z") else 0.0
            focal_length = float(self.pb_gen_focal_length.text().strip() or 35.0)
            camera_scale = float(self.pb_gen_camera_scale.text().strip() or 1.0)
            near_clip = float(self.pb_gen_near_clip.text().strip() or 0.1)
            far_clip = float(self.pb_gen_far_clip.text().strip() or 10000.0)
        except ValueError:
            cmds.warning("[KRT] Generate Camera: one of the fields isn't a valid number.")
            return

        if near_clip <= 0:
            cmds.warning("[KRT] Generate Camera: Near Clip Plane must be greater than zero.")
            return
        if far_clip <= near_clip:
            cmds.warning("[KRT] Generate Camera: Far Clip Plane must be greater than Near Clip Plane.")
            return

        try:
            cam_tfm = self.pb_generate_camera(
                pos_x, pos_y, pos_z, focal_length, camera_scale, near_clip, far_clip,
                self.pb_gen_auto_clip_chk.isChecked(), rot_x=rot_x, rot_y=rot_y, rot_z=rot_z)
        except Exception as e:
            log_crash("Generate Camera", e)
            cmds.warning("[KRT] Generate Camera failed: {}".format(e))
            return

        self.pb_camera_field.setText(cam_tfm)
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Generated camera: {}".format(cam_tfm))
        # Request #1: the live camera-view screen should immediately show
        # the newly generated camera, not stay pointed at whatever it had
        # before (or nothing).
        self.pb_set_live_view_camera(cam_tfm)

    # ------------------------------------------------------------------
    # Playblast QC helpers (Stage 36): ported from the studio's standalone
    # "Mahavatar Parshuram QC Playblast" script into KRT's own embedded
    # Playblast tab. Everything below is pure/self-contained (no Qt), so
    # it can run - and be stub-tested - without a UI. See create_playblast()
    # for how these get wired together.
    # ------------------------------------------------------------------
    def pb_clean_display_name(self, value):
        value = re.sub(r"[_\-.]+", " ", value or "")
        value = re.sub(r"\s+", " ", value).strip()
        return value.title() if value else ""

    def pb_is_version_or_task_token(self, token):
        token = (token or "").lower()
        exact_task_tokens = {
            "qc", "rig", "model", "mod", "texture", "tex", "lookdev",
            "look", "anim", "animation", "layout", "blocking",
            "publish", "playblast", "final", "wip", "scene", "shot",
            "asset", "ma", "mb"
        }
        if token in exact_task_tokens:
            return True
        patterns = (
            r"v\d+", r"ver\d+", r"version\d+", r"rev\d+", r"r\d+",
            r"take\d+", r"tk\d+", r"wip\d*", r"final\d*",
            r"\d{3,4}to\d{3,4}", r"\d{3,4}-\d{3,4}", r"\d{6,8}"
        )
        return any(re.fullmatch(pattern, token) for pattern in patterns)

    def pb_parse_artist_from_filename(self, scene_stem):
        tokens = [t for t in re.split(r"[_\-.]+", scene_stem or "") if t]
        lower_tokens = [t.lower() for t in tokens]
        for marker in ("artist", "by"):
            if marker in lower_tokens:
                idx = lower_tokens.index(marker)
                if idx + 1 < len(tokens):
                    return self.pb_clean_display_name(tokens[idx + 1])
        return self.pb_clean_display_name(getpass.getuser())

    def pb_parse_character_from_filename(self, scene_stem, project_name=""):
        """Same heuristic as the studio script's parse_character_from_filename,
        generalized for KRT's multi-project pipeline: instead of a
        hardcoded project-name ignore-list, the CURRENT project name's own
        words are ignored (so "CHR_Jamadagni_v003.ma" under project "Mahavatar
        Parshuram" doesn't mistake "Mahavatar"/"Parshuram" for the
        character on some other show's scene)."""
        tokens = [t for t in re.split(r"[_\-.]+", scene_stem or "") if t]
        lower_tokens = [t.lower() for t in tokens]

        for marker in ("character", "char", "chr"):
            if marker in lower_tokens:
                index = lower_tokens.index(marker) + 1
                character_tokens = []
                for token in tokens[index:]:
                    lower = token.lower()
                    if lower in ("artist", "by"):
                        break
                    if self.pb_is_version_or_task_token(lower):
                        break
                    character_tokens.append(token)
                    if len(character_tokens) >= 3:
                        break
                if character_tokens:
                    return self.pb_clean_display_name(" ".join(character_tokens))

        project_words = set(re.split(r"[_\-.\s]+", (project_name or "").lower()))
        ignored_tokens = {"project", "artist", "by"} | project_words
        ignored_tokens.discard("")

        candidate_tokens = []
        for token in tokens:
            lower = token.lower()
            if lower in ignored_tokens:
                continue
            if self.pb_is_version_or_task_token(lower):
                continue
            if re.fullmatch(r"\d+", lower):
                continue
            candidate_tokens.append(token)

        if candidate_tokens:
            return self.pb_clean_display_name(" ".join(candidate_tokens[:3]))
        return "Character"

    def pb_get_scene_fps(self):
        time_unit = cmds.currentUnit(query=True, time=True)
        standard_units = {
            "game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0,
            "show": 48.0, "palf": 50.0, "ntscf": 60.0
        }
        if time_unit in standard_units:
            return standard_units[time_unit]
        match = re.match(r"([0-9]+(?:\.[0-9]+)?)fps$", time_unit)
        if match:
            return float(match.group(1))
        return 24.0

    def pb_format_fps(self, fps):
        if abs(float(fps) - round(float(fps))) < 0.0001:
            return str(int(round(float(fps))))
        return "{:.3f}".format(float(fps)).rstrip("0").rstrip(".")

    def pb_detect_ffmpeg(self):
        """No hardcoded studio machine path (the source script's own
        C:\\ffmpeg\\ffmpeg.exe default) - checks the system PATH first,
        then falls back to the same common Windows install locations.
        Returns None (not a guessed, possibly-nonexistent path) if
        nothing is actually found, so callers can cleanly fall back to
        the native (non-MP4) playblast path instead of crashing on a
        missing exe."""
        found = shutil.which("ffmpeg")
        if found:
            return found.replace("\\", "/")
        common_paths = [
            r"C:\ffmpeg\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path
        return None

    def pb_get_font_path(self):
        font_paths = (
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arial.ttf"
        )
        for font_path in font_paths:
            if os.path.isfile(font_path):
                return font_path
        return ""

    def pb_escape_ffmpeg_filter_path(self, path):
        return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

    def pb_create_metadata_file(self, output_root, project_name, character_name,
                                 artist_name, start_frame, end_frame, fps):
        metadata_path = output_root + "_metadata.txt"
        metadata_text = (
            "PROJECT: {}    |    CHARACTER: {}    |    ARTIST: {}    |    "
            "FRAME RANGE: {} - {}    |    FPS: {}"
        ).format(project_name, character_name, artist_name, start_frame, end_frame,
                  self.pb_format_fps(fps))
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(metadata_text)
        return metadata_path, metadata_text

    def pb_build_metadata_filter(self, width, height, metadata_path, metadata_text,
                                  start_frame):
        # Keep enough room on the right for the live frame counter.
        available_left_width = width * 0.79
        estimated_font_from_width = int(available_left_width / max(len(metadata_text) * 0.55, 1))
        preferred_font = int(height * 0.026)
        font_size = max(16, min(preferred_font, estimated_font_from_width))
        strip_height = max(54, int(font_size * 2.45))
        if strip_height % 2:
            strip_height += 1
        horizontal_padding = max(18, int(width * 0.012))
        text_y = height + max(5, int((strip_height - font_size) * 0.40))
        metadata_path_filter = self.pb_escape_ffmpeg_filter_path(metadata_path)

        font_path = self.pb_get_font_path()
        font_option = "fontfile='{}':".format(self.pb_escape_ffmpeg_filter_path(font_path)) if font_path else ""

        filters = [
            "pad=iw:ih+{}:0:0:color=black".format(strip_height),
            "drawbox=x=0:y={}:w=iw:h={}:color=0xE9ECEC@0.96:t=fill".format(height, strip_height),
            "drawtext={}textfile='{}':fontcolor=black@0.98:fontsize={}:x={}:y={}".format(
                font_option, metadata_path_filter, font_size, horizontal_padding, text_y),
            "drawtext={}text='FRAME\\: %{{frame_num}}':start_number={}:"
            "fontcolor=black@0.98:fontsize={}:x=w-tw-{}:y={}".format(
                font_option, int(start_frame), font_size, horizontal_padding, text_y),
        ]
        return ",".join(filters)

    def pb_hide_all_huds(self):
        self.pb_hud_original_visibility = {}
        huds = cmds.headsUpDisplay(listHeadsUpDisplays=True) or []
        for hud in huds:
            try:
                visible = bool(cmds.headsUpDisplay(hud, query=True, visible=True))
                self.pb_hud_original_visibility[hud] = visible
                if visible:
                    cmds.headsUpDisplay(hud, edit=True, visible=False)
            except Exception:
                pass

    def pb_restore_all_huds(self):
        for hud, visible in self.pb_hud_original_visibility.items():
            if not cmds.headsUpDisplay(hud, exists=True):
                continue
            try:
                cmds.headsUpDisplay(hud, edit=True, visible=visible)
            except Exception:
                pass
        self.pb_hud_original_visibility = {}

    def pb_hide_camera_gates(self, camera_shape_or_transform):
        """Hides film/resolution gate, safe action/title, field chart and
        gate mask on whichever camera the playblast is actually shooting
        through (the same `cam` create_playblast() already resolved -
        NOT necessarily the active viewport camera)."""
        self.pb_gate_camera = None
        self.pb_gate_original_values = {}
        cam = camera_shape_or_transform
        if not cam or not cmds.objExists(cam):
            return
        if cmds.nodeType(cam) == "transform":
            shapes = cmds.listRelatives(cam, shapes=True, fullPath=True, type="camera") or []
            cam = shapes[0] if shapes else None
        if not cam:
            return
        self.pb_gate_camera = cam

        gate_attributes = (
            "displayFilmGate", "displayResolution", "displaySafeAction",
            "displaySafeTitle", "displayFieldChart", "displayGateMask",
            "displayFilmOrigin", "displayFilmPivot"
        )
        for attribute in gate_attributes:
            if not cmds.attributeQuery(attribute, node=cam, exists=True):
                continue
            plug = "{}.{}".format(cam, attribute)
            try:
                self.pb_gate_original_values[attribute] = cmds.getAttr(plug)
                cmds.setAttr(plug, 0)
            except Exception:
                pass

    def pb_restore_camera_gates(self):
        if not self.pb_gate_camera or not cmds.objExists(self.pb_gate_camera):
            self.pb_gate_camera = None
            self.pb_gate_original_values = {}
            return
        for attribute, original_value in self.pb_gate_original_values.items():
            try:
                cmds.setAttr("{}.{}".format(self.pb_gate_camera, attribute), original_value)
            except Exception:
                pass
        self.pb_gate_camera = None
        self.pb_gate_original_values = {}

    def pb_run_ffmpeg_encode(self, ffmpeg_path, frames_dir, expected_frame_count,
                              fps, metadata_filter, final_mp4_path):
        """Encodes the exact captured JPG sequence (frame_%06d.jpg, 0-based,
        in `frames_dir`) into the final H.264 MP4 with the metadata filter
        chain burned in. Returns (success, error_message)."""
        ffmpeg_input_pattern = os.path.join(frames_dir, "frame_%06d.jpg").replace("\\", "/")

        startup_info = None
        creation_flags = 0
        if os.name == "nt":
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        ffmpeg_command = [
            ffmpeg_path, "-y",
            "-framerate", self.pb_format_fps(fps),
            "-start_number", "0",
            "-i", ffmpeg_input_pattern,
            "-frames:v", str(expected_frame_count),
            "-vf", metadata_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            final_mp4_path
        ]

        process = subprocess.run(
            ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, startupinfo=startup_info, creationflags=creation_flags
        )

        if process.returncode != 0:
            error = process.stderr[-6000:] if process.stderr else "Unknown FFmpeg error."
            return False, "FFmpeg could not create the final MP4.\n\n{}".format(error)
        if not os.path.isfile(final_mp4_path):
            return False, "FFmpeg finished, but the final MP4 was not created:\n{}".format(final_mp4_path)
        return True, ""

    # ------------------------------------------------------------------
    # Studio Library animation clip loading (Stage 37): the Playblast
    # tab's "Animation (.anim)" field loads a Studio Library clip straight
    # onto whatever controls match the Controls Filter, reusing Studio
    # Library's OWN animation-curve transfer code (the "mutils" package,
    # from the studio's shared install at DEFAULT_STUDIOLIBRARY_SRC_PATH)
    # rather than KRT re-implementing curve pasting/matching from scratch.
    # ------------------------------------------------------------------
    def pb_ensure_studiolibrary(self):
        """Makes Studio Library's "mutils" package importable. Tries a
        plain import first (already on sys.path via some other tool this
        session); falls back to the studio's shared network install (or
        the KRT_STUDIOLIBRARY_SRC env var, if someone's install lives
        somewhere else). Returns the imported `mutils` module, or None
        if it truly isn't reachable."""
        try:
            import mutils
            return mutils
        except ImportError:
            pass

        for candidate in (os.environ.get("KRT_STUDIOLIBRARY_SRC", ""), DEFAULT_STUDIOLIBRARY_SRC_PATH):
            if candidate and os.path.isdir(candidate) and candidate not in sys.path:
                sys.path.insert(0, candidate)

        try:
            import mutils
            return mutils
        except ImportError:
            return None

    def pb_is_studiolibrary_anim_path(self, path):
        """True if `path` looks like a Studio Library .anim item - a
        FOLDER (not a single file) ending in .anim, containing pose.json
        and an animation.ma/.mb - matching mutils.Animation's own
        mayaPath()/poseJsonPath() layout."""
        if not path:
            return False
        path = path.rstrip("/\\")
        if not path.lower().endswith(".anim"):
            return False
        if not os.path.isdir(path):
            return False
        if not os.path.isfile(os.path.join(path, "pose.json")):
            return False
        return (os.path.isfile(os.path.join(path, "animation.ma")) or
                os.path.isfile(os.path.join(path, "animation.mb")))

    def pb_get_anim_frame_range(self, anim_path):
        """(startFrame, endFrame) stored in a Studio Library .anim clip's
        own pose.json metadata, or (None, None) if unavailable. Used to
        auto-fill the Start/End fields when Browse picks a clip, so the
        Playblast's capture range matches the clip by default."""
        mutils_mod = self.pb_ensure_studiolibrary()
        if not mutils_mod:
            return None, None
        try:
            anim = mutils_mod.Animation.fromPath(anim_path)
            return anim.startFrame(), anim.endFrame()
        except Exception:
            return None, None

    def pb_load_anim_on_filtered_controls(self, anim_path, ctl_pattern, start_frame=None):
        """Loads a Studio Library .anim clip's animation curves onto
        whatever controls in the CURRENT scene match `ctl_pattern` (the
        Playblast tab's existing Controls Filter field, e.g. "*_ctl") -
        the actual feature: load the clip straight onto the filtered rig
        controls instead of requiring a plain baked-value JSON.
        `start_frame`, if given, shifts the clip so its first frame lands
        there (mutils.Animation.load's own startFrame semantics);
        left as None, the clip loads at its own original frame numbers.

        Returns (success, error_msg, matched_control_count)."""
        mutils_mod = self.pb_ensure_studiolibrary()
        if not mutils_mod:
            return False, (
                "Studio Library's 'mutils' package could not be found/imported "
                "(checked sys.path, then {}). Animation clip loading needs "
                "it.".format(DEFAULT_STUDIOLIBRARY_SRC_PATH)), 0

        if not self.pb_is_studiolibrary_anim_path(anim_path):
            return False, (
                "'{}' doesn't look like a Studio Library .anim item - expected "
                "a folder ending in .anim containing pose.json and "
                "animation.ma/.mb.".format(anim_path)), 0

        pattern = (ctl_pattern or "*").strip() or "*"
        matched = cmds.ls(pattern, type="transform") or []
        if not matched:
            return False, "No controls in the scene match the filter '{}'.".format(pattern), 0

        try:
            anim = mutils_mod.Animation.fromPath(anim_path)
            anim.load(
                objects=matched,
                option="replace all",
                startFrame=start_frame,
                currentTime=False,
            )
            return True, "", len(matched)
        except Exception as e:
            log_crash("Load Studio Library animation", e)
            return False, str(e), 0

    def create_playblast(self, camera_name, group_name, anim_json_path, ctl_pattern,
                          start_frame=None, end_frame=None, width=None, height=None,
                          fps=None, project_name="", character_name="", artist_name="",
                          output_path_override=None):
        """Returns (success, error_msg, output_path).

        Stage 36: when FFmpeg is available, this now does what the studio's
        standalone QC Playblast script does - hides HUDs/camera gates,
        captures an exact-frame-count JPG sequence, and encodes it to an
        H.264 MP4 with a burned-in metadata strip (project/character/
        artist/frame range/fps) and a live per-frame counter. When FFmpeg
        can't be found, it falls back to KRT's original native
        cmds.playblast QuickTime capture (still with HUDs/gates hidden),
        so the tool keeps working either way."""
        created_cam = None
        out_dir = self.get_playblast_dir()
        temporary_sequence_dir = None
        metadata_path = None
        conversion_succeeded = False
        try:
            cam = (camera_name or "").strip()
            if cam and not cmds.objExists(cam):
                cmds.warning("[KRT] Camera '{}' not found - falling back to a bounding-box camera.".format(cam))
                cam = ""

            if not cam:
                group = (group_name or "").strip()
                if not group or not cmds.objExists(group):
                    return False, "No valid camera given, and no valid group to build one from.", None
                cam = self.create_auto_camera_from_group(group)
                if not cam:
                    return False, "Could not build a camera from '{}'.".format(group), None
                created_cam = cam

            # Stage 37: load a Studio Library .anim clip onto whatever
            # controls match ctl_pattern, before capturing - see
            # pb_load_anim_on_filtered_controls(). A bad/missing clip
            # aborts the playblast entirely (rather than silently
            # capturing the scene's un-animated current state), since
            # the whole point of this run was to review that animation.
            if anim_json_path and anim_json_path.strip():
                ok_anim, anim_err, matched_count = self.pb_load_anim_on_filtered_controls(
                    anim_json_path.strip(), ctl_pattern, start_frame=start_frame)
                if not ok_anim:
                    return False, "Could not load animation clip: {}".format(anim_err), None
                cmds.warning(
                    "[KRT] Loaded animation clip onto {} matching control(s) "
                    "(filter: '{}').".format(matched_count, ctl_pattern or "*"))

            cmds.lookThru(cam)

            ts = time.strftime("%Y%m%d_%H%M%S")
            ffmpeg_path = self.pb_detect_ffmpeg()

            self.pb_hide_all_huds()
            self.pb_hide_camera_gates(cam)
            cmds.refresh(force=True)

            if ffmpeg_path:
                # ---- QC MP4 pipeline (FFmpeg found) --------------------
                if output_path_override and output_path_override.strip():
                    out_path = output_path_override.strip().replace("\\", "/")
                    if not out_path.lower().endswith(".mp4"):
                        out_path += ".mp4"
                    override_dir = os.path.dirname(out_path)
                    if override_dir and not os.path.isdir(override_dir):
                        os.makedirs(override_dir)
                else:
                    out_path = os.path.join(out_dir, "playblast_{}.mp4".format(ts)).replace("\\", "/")
                output_root = os.path.splitext(out_path)[0]

                effective_start = int(start_frame) if start_frame is not None else int(cmds.playbackOptions(query=True, minTime=True))
                effective_end = int(end_frame) if end_frame is not None else int(cmds.playbackOptions(query=True, maxTime=True))
                effective_fps = float(fps) if fps else self.pb_get_scene_fps()
                expected_frame_count = (effective_end - effective_start) + 1
                if expected_frame_count <= 0:
                    return False, "Start frame must be lower than or equal to end frame.", None

                w = int(width) if width else 1920
                h = int(height) if height else 1080

                temporary_sequence_dir = tempfile.mkdtemp(prefix="KRT_qc_frames_").replace("\\", "/")
                maya_sequence_prefix = os.path.join(temporary_sequence_dir, "maya_capture").replace("\\", "/")

                cmds.playblast(
                    filename=maya_sequence_prefix, format="image", compression="jpg",
                    quality=100, startTime=effective_start, endTime=effective_end,
                    framePadding=6, width=w, height=h, showOrnaments=False,
                    percent=100, viewer=False, clearCache=True, forceOverwrite=True,
                    offScreen=True
                )

                generated_frames = []
                for filename in os.listdir(temporary_sequence_dir):
                    if filename.lower().endswith((".jpg", ".jpeg")):
                        generated_frames.append(os.path.join(temporary_sequence_dir, filename))

                def frame_number_from_path(path):
                    match = re.search(r"(-?\d+)(?=\.[^.]+$)", os.path.basename(path))
                    return int(match.group(1)) if match else 0

                generated_frames.sort(key=frame_number_from_path)

                if len(generated_frames) != expected_frame_count:
                    return False, (
                        "Maya captured {} images, but {} were expected.\n\n"
                        "Frame range: {} - {}\nTemporary sequence:\n{}".format(
                            len(generated_frames), expected_frame_count,
                            effective_start, effective_end, temporary_sequence_dir)
                    ), None

                # Rename to a guaranteed zero-based continuous FFmpeg
                # sequence (staged through a throwaway prefix first, so a
                # renumber never collides with a still-original filename).
                staged_paths = []
                for index, source_path in enumerate(generated_frames):
                    staged_path = os.path.join(temporary_sequence_dir, "_stage_{:06d}.jpg".format(index))
                    os.rename(source_path, staged_path)
                    staged_paths.append(staged_path)
                for index, staged_path in enumerate(staged_paths):
                    normalized_path = os.path.join(temporary_sequence_dir, "frame_{:06d}.jpg".format(index))
                    os.rename(staged_path, normalized_path)

                metadata_path, metadata_text = self.pb_create_metadata_file(
                    output_root=output_root,
                    project_name=project_name or "Untitled Project",
                    character_name=character_name or "Character",
                    artist_name=artist_name or "Artist",
                    start_frame=effective_start, end_frame=effective_end, fps=effective_fps
                )
                metadata_filter = self.pb_build_metadata_filter(
                    width=w, height=h, metadata_path=metadata_path,
                    metadata_text=metadata_text, start_frame=effective_start
                )

                ok, err = self.pb_run_ffmpeg_encode(
                    ffmpeg_path, temporary_sequence_dir, expected_frame_count,
                    effective_fps, metadata_filter, out_path
                )
                if not ok:
                    return False, err, None

                conversion_succeeded = True
                return True, "", out_path

            else:
                # ---- Native fallback (no FFmpeg found) ------------------
                cmds.warning(
                    "[KRT] FFmpeg not found - playblasting without the MP4/"
                    "metadata-strip QC pipeline. Install FFmpeg (or put "
                    "ffmpeg.exe on PATH) to get burned-in metadata + a "
                    "true H.264 MP4.")
                if output_path_override and output_path_override.strip():
                    out_path = os.path.splitext(output_path_override.strip())[0].replace("\\", "/")
                    override_dir = os.path.dirname(out_path)
                    if override_dir and not os.path.isdir(override_dir):
                        os.makedirs(override_dir)
                else:
                    out_path = os.path.join(out_dir, "playblast_{}".format(ts)).replace("\\", "/")
                kwargs = dict(filename=out_path, format="qt", forceOverwrite=True, viewer=False,
                              percent=100, clearCache=True, offScreen=True, showOrnaments=False)
                if start_frame is not None: kwargs["startTime"] = start_frame
                if end_frame is not None: kwargs["endTime"] = end_frame
                if width: kwargs["width"] = int(width)
                if height: kwargs["height"] = int(height)
                result_path = cmds.playblast(**kwargs)
                return True, "", result_path

        except Exception as e:
            log_crash("Create playblast", e)
            return False, traceback.format_exc(), None
        finally:
            self.pb_restore_camera_gates()
            self.pb_restore_all_huds()
            try:
                cmds.refresh(force=True)
            except Exception:
                pass
            if created_cam and cmds.objExists(created_cam):
                cmds.delete(created_cam)
            if metadata_path:
                try:
                    if os.path.isfile(metadata_path):
                        os.remove(metadata_path)
                except Exception:
                    pass
            # Keep a failed capture's temp sequence around for diagnosis;
            # clean it up once it's been successfully encoded.
            if conversion_succeeded and temporary_sequence_dir:
                try:
                    shutil.rmtree(temporary_sequence_dir)
                except Exception:
                    pass

    def page_playblast(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)

        header_row = QtWidgets.QHBoxLayout()
        header = QtWidgets.QLabel("<b>🎬 PLAYBLAST</b>")
        header.setStyleSheet("font-size: 15px; color: #2bb5a8;")
        header_row.addWidget(header)
        header_row.addStretch()
        # ── Collapse Settings (fix: the preview screen was reading too
        # small with every settings row stacked above it) - hides the
        # whole Playblast Settings box down to just its title bar, and the
        # splitter below lets the settings/preview split be dragged to any
        # size in between, instead of a fixed layout either way. ─────────
        self.btn_pb_collapse_settings = QtWidgets.QPushButton("▲ Collapse Settings")
        self.btn_pb_collapse_settings.setCheckable(True)
        self.btn_pb_collapse_settings.setToolTip(
            "Hide the settings box so the preview screen gets more room - "
            "or just drag the horizontal bar between them to resize "
            "either one to whatever size you want.")
        self.btn_pb_collapse_settings.setStyleSheet(
            "QPushButton { background-color: #2bb5a8; color: #101010; font-weight: bold; padding: 4px 10px; border-radius: 3px; } "
            "QPushButton:hover { background-color: #33cbbd; } "
            "QPushButton:checked { background-color: #3e3e42; color: white; }")
        self.btn_pb_collapse_settings.clicked.connect(self.pb_toggle_settings_collapsed)
        header_row.addWidget(self.btn_pb_collapse_settings)
        layout.addLayout(header_row)

        # ── Compact settings bar (request #3: keep this small so the video
        # preview below gets the bulk of the tab) ──────────────────────────
        settings_group = QtWidgets.QGroupBox("Playblast Settings")
        settings_group.setStyleSheet(
            "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 8px; "
            "font-weight: bold; color: #aaa; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grid = QtWidgets.QGridLayout(settings_group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # ── Scene/QC info row (Stage 36, ported from the studio QC
        # Playblast script): Project/Character/Artist, auto-detected from
        # the scene filename, burned into the MP4's metadata strip below.
        # Refresh From Scene re-runs the detection (e.g. after Save As). ──
        info_row = QtWidgets.QHBoxLayout()
        info_row.addWidget(QtWidgets.QLabel("Project:"))
        self.pb_project_field = QtWidgets.QLineEdit()
        self.pb_project_field.setFixedWidth(140)
        info_row.addWidget(self.pb_project_field)
        info_row.addWidget(QtWidgets.QLabel("Character:"))
        self.pb_character_field = QtWidgets.QLineEdit()
        self.pb_character_field.setFixedWidth(140)
        info_row.addWidget(self.pb_character_field)
        info_row.addWidget(QtWidgets.QLabel("Artist:"))
        self.pb_artist_field = QtWidgets.QLineEdit()
        self.pb_artist_field.setFixedWidth(120)
        info_row.addWidget(self.pb_artist_field)
        info_row.addStretch()
        btn_refresh_scene = QtWidgets.QPushButton("🔄 Refresh From Scene")
        btn_refresh_scene.setToolTip(
            "Re-detects Project/Character/Artist from the scene's filename, "
            "and Start/End/FPS from the scene itself.")
        btn_refresh_scene.clicked.connect(lambda: self.pb_refresh_from_scene(update_status=True))
        info_row.addWidget(btn_refresh_scene)
        grid.addLayout(info_row, 0, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Camera:"), 1, 0)
        self.pb_camera_field = QtWidgets.QLineEdit()
        self.pb_camera_field.setPlaceholderText("Existing camera - leave empty to auto-build one from Group")
        grid.addWidget(self.pb_camera_field, 1, 1)
        btn_cam_sel = QtWidgets.QPushButton("🎯 Use Selected")
        btn_cam_sel.clicked.connect(self.pb_use_selected_camera)
        grid.addWidget(btn_cam_sel, 1, 2)

        grid.addWidget(QtWidgets.QLabel("Group (if no camera):"), 2, 0)
        self.pb_group_field = QtWidgets.QLineEdit()
        self.pb_group_field.setPlaceholderText("A group/node - its bounding box auto-builds a camera to frame it")
        grid.addWidget(self.pb_group_field, 2, 1)
        btn_grp_sel = QtWidgets.QPushButton("🎯 Use Selected")
        btn_grp_sel.clicked.connect(self.pb_use_selected_group)
        grid.addWidget(btn_grp_sel, 2, 2)

        # ── Generate Camera (Stage 38): when there's no existing camera to
        # playblast through, this builds one - full manual control over
        # position and the same lens settings the Attribute Editor's Camera
        # Shape tab shows (Angle of View/Focal Length/Camera Scale/Auto
        # Render Clip Plane/Near+Far Clip Plane), instead of only the
        # existing auto-frame-a-group option above. ────────────────────────
        gen_cam_group = QtWidgets.QGroupBox("Generate Camera (if none exists)")
        gen_cam_group.setStyleSheet(
            "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 6px; "
            "font-weight: bold; color: #888; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        gen_cam_layout = QtWidgets.QVBoxLayout(gen_cam_group)
        gen_cam_layout.setSpacing(4)

        gen_row1 = QtWidgets.QHBoxLayout()
        gen_row1.addWidget(QtWidgets.QLabel("Position X:"))
        self.pb_gen_pos_x = QtWidgets.QLineEdit("0.0")
        self.pb_gen_pos_x.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_x)
        gen_row1.addWidget(QtWidgets.QLabel("Y:"))
        self.pb_gen_pos_y = QtWidgets.QLineEdit("0.0")
        self.pb_gen_pos_y.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_y)
        gen_row1.addWidget(QtWidgets.QLabel("Z:"))
        self.pb_gen_pos_z = QtWidgets.QLineEdit("24.0")
        self.pb_gen_pos_z.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_z)
        gen_row1.addSpacing(12)
        # ── Rotation X/Y/Z (request #1): so the live camera view's real-
        # time tumble/pan sync has somewhere to write the camera's live
        # rotation - also editable by hand, same as Position. ──────────
        gen_row1.addWidget(QtWidgets.QLabel("Rotation X:"))
        self.pb_gen_rot_x = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_x.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_x)
        gen_row1.addWidget(QtWidgets.QLabel("Y:"))
        self.pb_gen_rot_y = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_y.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_y)
        gen_row1.addWidget(QtWidgets.QLabel("Z:"))
        self.pb_gen_rot_z = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_z.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_z)
        gen_row1.addSpacing(12)
        gen_row1.addWidget(QtWidgets.QLabel("Focal Length:"))
        self.pb_gen_focal_length = QtWidgets.QLineEdit("35.000")
        self.pb_gen_focal_length.setFixedWidth(70)
        self.pb_gen_focal_length.setToolTip("Drives Angle of View below (same coupling as the Attribute Editor's Camera Shape tab).")
        self.pb_gen_focal_length.textChanged.connect(self.pb_update_gen_camera_aov)
        gen_row1.addWidget(self.pb_gen_focal_length)
        gen_row1.addWidget(QtWidgets.QLabel("Angle of View:"))
        self.pb_gen_aov_display = QtWidgets.QLineEdit()
        self.pb_gen_aov_display.setFixedWidth(60)
        self.pb_gen_aov_display.setReadOnly(True)
        self.pb_gen_aov_display.setToolTip("Computed from Focal Length (assumes Maya's default 36mm horizontal film aperture) - read-only, matching how the two stay in sync in Maya's own Camera Shape tab.")
        gen_row1.addWidget(self.pb_gen_aov_display)
        gen_row1.addStretch()
        gen_cam_layout.addLayout(gen_row1)

        gen_row2 = QtWidgets.QHBoxLayout()
        gen_row2.addWidget(QtWidgets.QLabel("Camera Scale:"))
        self.pb_gen_camera_scale = QtWidgets.QLineEdit("1.000")
        self.pb_gen_camera_scale.setFixedWidth(60)
        gen_row2.addWidget(self.pb_gen_camera_scale)
        self.pb_gen_auto_clip_chk = QtWidgets.QCheckBox("Auto Render Clip Plane")
        self.pb_gen_auto_clip_chk.setChecked(True)
        self.pb_gen_auto_clip_chk.setToolTip(
            "Maps to the camera's own autoRenderClipPlanes attribute - on: "
            "Maya manages the RENDER clip planes automatically; the Near/Far "
            "Clip Plane fields still set the regular viewport clip planes "
            "either way.")
        gen_row2.addWidget(self.pb_gen_auto_clip_chk)
        gen_row2.addWidget(QtWidgets.QLabel("Near Clip Plane:"))
        self.pb_gen_near_clip = QtWidgets.QLineEdit("0.100")
        self.pb_gen_near_clip.setFixedWidth(70)
        gen_row2.addWidget(self.pb_gen_near_clip)
        gen_row2.addWidget(QtWidgets.QLabel("Far Clip Plane:"))
        self.pb_gen_far_clip = QtWidgets.QLineEdit("10000.000")
        self.pb_gen_far_clip.setFixedWidth(70)
        gen_row2.addWidget(self.pb_gen_far_clip)
        gen_row2.addStretch()
        btn_gen_camera = QtWidgets.QPushButton("🎥 Generate Camera")
        btn_gen_camera.setStyleSheet("background-color: #3e3e42; color: white; font-weight: bold;")
        btn_gen_camera.setToolTip("Creates a camera at the position/lens settings above and puts it straight into the Camera field.")
        btn_gen_camera.clicked.connect(self.pb_generate_camera_clicked)
        gen_row2.addWidget(btn_gen_camera)
        gen_cam_layout.addLayout(gen_row2)

        grid.addWidget(gen_cam_group, 3, 0, 1, 3)
        self.pb_update_gen_camera_aov()

        grid.addWidget(QtWidgets.QLabel("Animation (.anim):"), 4, 0)
        # Default animation clip (request): a new Playblast tab starts
        # pointed at the studio's standard Biped QC clip instead of empty -
        # still fully editable/clearable/Browse-able same as any other
        # field, and a pipeline JSON's own saved anim_path (if it has one)
        # always overrides this the moment it's loaded (see
        # pb_apply_settings_dict/load_pipeline_from_file).
        PB_DEFAULT_ANIM_PATH = "P:/rigging_team/Rigging_local_share/QC/Rig_QC_animation/playblast/Biped QC.anim"
        self.pb_anim_field = QtWidgets.QLineEdit(PB_DEFAULT_ANIM_PATH)
        self.pb_anim_field.setPlaceholderText("Studio Library .anim clip folder - leave empty to playblast as-is")
        self.pb_anim_field.setToolTip(
            "A Studio Library animation clip (the '<name>.anim' FOLDER, "
            "containing pose.json + animation.ma/.mb) - loaded onto whatever "
            "controls in the scene match the Controls Filter below, right "
            "before capturing. Needs the studio's Studio Library install to "
            "be reachable (see the Docs tab).")
        grid.addWidget(self.pb_anim_field, 4, 1)
        btn_anim_browse = QtWidgets.QPushButton("📂 Browse")
        btn_anim_browse.clicked.connect(self.pb_browse_anim_json)
        grid.addWidget(btn_anim_browse, 4, 2)

        # ── Output MP4 path (Stage 36): optional - leave blank to keep the
        # existing auto-timestamped-into-the-playblasts-folder behavior. ──
        grid.addWidget(QtWidgets.QLabel("Save MP4 As (optional):"), 5, 0)
        self.pb_output_field = QtWidgets.QLineEdit()
        self.pb_output_field.setPlaceholderText(
            "Leave empty to auto-name into this session's playblasts folder...")
        grid.addWidget(self.pb_output_field, 5, 1)
        btn_output_browse = QtWidgets.QPushButton("📂 Browse")
        btn_output_browse.clicked.connect(self.pb_browse_output_path)
        grid.addWidget(btn_output_browse, 5, 2)

        tail_row = QtWidgets.QHBoxLayout()
        tail_row.addWidget(QtWidgets.QLabel("Controls Filter:"))
        self.pb_pattern_field = QtWidgets.QLineEdit("*_ctl")
        self.pb_pattern_field.setFixedWidth(100)
        self.pb_pattern_field.setToolTip("Only nodes matching this pattern are affected by the animation JSON above.")
        tail_row.addWidget(self.pb_pattern_field)
        tail_row.addSpacing(12)
        tail_row.addWidget(QtWidgets.QLabel("Start:"))
        self.pb_start_field = QtWidgets.QLineEdit(str(int(cmds.playbackOptions(query=True, minTime=True))))
        self.pb_start_field.setFixedWidth(50)
        tail_row.addWidget(self.pb_start_field)
        tail_row.addWidget(QtWidgets.QLabel("End:"))
        self.pb_end_field = QtWidgets.QLineEdit(str(int(cmds.playbackOptions(query=True, maxTime=True))))
        self.pb_end_field.setFixedWidth(50)
        tail_row.addWidget(self.pb_end_field)
        tail_row.addWidget(QtWidgets.QLabel("FPS:"))
        self.pb_fps_field = QtWidgets.QLineEdit(self.pb_format_fps(self.pb_get_scene_fps()))
        self.pb_fps_field.setFixedWidth(50)
        self.pb_fps_field.setToolTip("Frame rate baked into the encoded MP4. Refresh From Scene re-reads this from the scene.")
        tail_row.addWidget(self.pb_fps_field)
        tail_row.addStretch()
        grid.addLayout(tail_row, 6, 0, 1, 3)

        # ── Resolution + Create Playblast (Stage 36: resolution presets,
        # ported from the studio script; "Current Viewport" (KRT's original
        # default) keeps the native viewport size instead of forcing one. ──
        final_row = QtWidgets.QHBoxLayout()
        final_row.addWidget(QtWidgets.QLabel("Resolution:"))
        self.pb_resolution_menu = QtWidgets.QComboBox()
        self.pb_resolution_menu.addItems([
            "Current Viewport",
            "HD 720 (1280x720)",
            "HD 1080 (1920x1080)",
            "VGA (640x480)",
            "Square (1024x1024)",
        ])
        self.pb_resolution_menu.setFixedWidth(180)
        final_row.addWidget(self.pb_resolution_menu)
        final_row.addStretch()
        btn_create = QtWidgets.QPushButton("🎬 Create Playblast")
        btn_create.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold; padding: 6px 14px;")
        btn_create.clicked.connect(self.pb_create_clicked)
        final_row.addWidget(btn_create)
        grid.addLayout(final_row, 7, 0, 1, 3)

        # ── Compare (requests #5/#6): every playblast is already saved as
        # its own timestamped version (never overwritten - see the ts =
        # time.strftime(...) naming in create_playblast), so "versions to
        # compare" already exist on disk; this row is what makes picking
        # two of them from a version LIST convenient (instead of only
        # browsing to a path by hand every time), and adds a proper
        # wipe/slider overlay mode on top of the existing side-by-side one. ─
        grid.addWidget(QtWidgets.QLabel("Compare A:"), 8, 0)
        compare_a_row = QtWidgets.QHBoxLayout()
        compare_a_row.setSpacing(4)
        self.pb_compare_a_combo = QtWidgets.QComboBox()
        self.pb_compare_a_combo.setToolTip(
            "Pick any saved version of this playblast (newest first) - "
            "Compare uses this as the LEFT / 'before' side.")
        compare_a_row.addWidget(self.pb_compare_a_combo, 1)
        grid.addLayout(compare_a_row, 8, 1)

        grid.addWidget(QtWidgets.QLabel("Compare B:"), 9, 0)
        compare_b_row = QtWidgets.QHBoxLayout()
        compare_b_row.setSpacing(4)
        self.pb_compare_b_combo = QtWidgets.QComboBox()
        self.pb_compare_b_combo.setToolTip(
            "Pick any saved version of this playblast (newest first) - "
            "Compare uses this as the RIGHT / 'after' side.")
        compare_b_row.addWidget(self.pb_compare_b_combo, 1)
        btn_compare_b_browse = QtWidgets.QPushButton("📂 Other...")
        btn_compare_b_browse.setToolTip("Browse to an older playblast video that isn't in this session's own list.")
        btn_compare_b_browse.clicked.connect(self.pb_browse_compare_path)
        compare_b_row.addWidget(btn_compare_b_browse)
        grid.addLayout(compare_b_row, 9, 1)

        # Kept for JSON persistence / backward compatibility with anything
        # already saved from before Compare A/B existed - not shown, see
        # pb_browse_compare_path/pb_get_settings_dict/pb_apply_settings_dict.
        self.pb_compare_field = QtWidgets.QLineEdit()
        self.pb_compare_field.setVisible(False)

        compare_mode_row = QtWidgets.QHBoxLayout()
        compare_mode_row.setSpacing(4)
        compare_mode_row.addWidget(QtWidgets.QLabel("Mode:"))
        self.pb_compare_mode_combo = QtWidgets.QComboBox()
        self.pb_compare_mode_combo.addItems(["Wipe / Slider", "Side-by-Side"])
        self.pb_compare_mode_combo.setToolTip(
            "Wipe/Slider - one screen, drag the line to reveal A vs B at "
            "the same moment (needs PySide6/Qt6 - falls back to Side-by-"
            "Side automatically if that's not available). Side-by-Side - "
            "two independent players next to each other.")
        compare_mode_row.addWidget(self.pb_compare_mode_combo)
        self.btn_pb_compare_toggle = QtWidgets.QPushButton("🆚 Compare")
        self.btn_pb_compare_toggle.setCheckable(True)
        self.btn_pb_compare_toggle.setToolTip("Compare Compare A against Compare B in the mode selected above.")
        self.btn_pb_compare_toggle.clicked.connect(self.pb_toggle_compare_mode)
        compare_mode_row.addWidget(self.btn_pb_compare_toggle)
        grid.addLayout(compare_mode_row, 9, 2)

        grid.setColumnStretch(1, 1)

        # ── Settings box / preview screen split (fix: preview was reading
        # too small with this many settings rows stacked above it) - a
        # draggable QSplitter instead of a fixed stack, so the divider
        # between them can be pulled to whatever size the user wants,
        # on top of the Collapse Settings button above for one-click
        # "give the preview all the room" too. ─────────────────────────
        self.pb_main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.pb_main_splitter.setChildrenCollapsible(False)
        # request #4 fix: the handle at #3e3e42/6px was reading as
        # invisible - it blended into the settings box's own border color
        # with barely any width. Made it thicker and a bright, unmistakable
        # color with a hover highlight, same as Maya's own splitter grips.
        self.pb_main_splitter.setHandleWidth(10)
        self.pb_main_splitter.setStyleSheet(
            "QSplitter::handle { background: #55555c; border-top: 1px solid #6e6e78; "
            "border-bottom: 1px solid #222; } "
            "QSplitter::handle:hover { background: #2bb5a8; }")
        self.pb_main_splitter.addWidget(settings_group)

        # ── Big preview screen (request #3: this is the main event - it
        # gets almost all the remaining vertical space). Stage 39, requests
        # #1/#3: this is now a QStackedWidget with three pages instead of a
        # single fixed frame:
        #   0 - live embedded Maya camera view (shown by default / whenever
        #       nothing has been picked to review yet - "the blank screen"
        #       from the user's request now shows the live camera instead)
        #   1 - the existing single-video playback (a picked playblast)
        #   2 - side-by-side compare mode (current vs. an older playblast)
        # ────────────────────────────────────────────────────────────────
        self.pb_preview_stack = QtWidgets.QStackedWidget()
        self.pb_preview_stack.setStyleSheet("background:#000; border: 1px solid #333;")
        self.pb_preview_stack.setMinimumHeight(360)

        # -- page 0: live camera view -----------------------------------
        self.pb_camera_view = PBCameraViewWidget(
            self.pb_preview_stack, on_transform_changed=self.pb_on_live_camera_transform)
        self.pb_preview_stack.addWidget(self.pb_camera_view)

        # -- page 1: single-video playback (unchanged from before) ------
        preview_frame = QtWidgets.QFrame()
        preview_frame.setStyleSheet("background:#000;")
        preview_layout = QtWidgets.QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        if HAS_MULTIMEDIA:
            self.pb_media_player = QMediaPlayer(preview_frame)
            self.pb_video_widget = QVideoWidget(preview_frame)
            self.pb_video_widget.setMinimumHeight(360)
            if IS_PYSIDE6 and QAudioOutput is not None:
                self._pb_audio_output = QAudioOutput(preview_frame)
                self.pb_media_player.setAudioOutput(self._pb_audio_output)
                self.pb_media_player.setVideoOutput(self.pb_video_widget)
            else:
                self.pb_media_player.setVideoOutput(self.pb_video_widget)
            preview_layout.addWidget(self.pb_video_widget)
        else:
            self.pb_media_player = None
            self.pb_video_widget = None
            warn = QtWidgets.QLabel(
                "Embedded playback isn't available in this Maya's Qt install "
                "(QtMultimedia not found) - pick a playblast below to open it "
                "in your default video player instead.")
            warn.setAlignment(QtCore.Qt.AlignCenter)
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #ffcc66; padding: 40px;")
            preview_layout.addWidget(warn)
        self.pb_preview_stack.addWidget(preview_frame)

        # -- page 2: compare mode (request #3) - current playblast on the
        # left, an older one (from the Compare Path field) on the right --
        compare_frame = QtWidgets.QFrame()
        compare_frame.setStyleSheet("background:#000;")
        compare_layout = QtWidgets.QHBoxLayout(compare_frame)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.setSpacing(2)

        self.pb_compare_media_player = None
        self.pb_compare_video_widget = None
        if HAS_MULTIMEDIA:
            left_lbl = QtWidgets.QLabel("Current")
            left_lbl.setAlignment(QtCore.Qt.AlignCenter)
            left_lbl.setStyleSheet("color:#2bb5a8; background:#111; font-weight:bold;")
            # Re-use pb_video_widget itself for the "current" side so there's
            # only one media player driving the current clip either way -
            # it just gets reparented between pages 1 and 2's layouts.
            self.pb_compare_current_container = QtWidgets.QWidget()
            cur_layout = QtWidgets.QVBoxLayout(self.pb_compare_current_container)
            cur_layout.setContentsMargins(0, 0, 0, 0)
            cur_layout.addWidget(left_lbl)
            compare_layout.addWidget(self.pb_compare_current_container, 1)

            right_col = QtWidgets.QVBoxLayout()
            right_lbl = QtWidgets.QLabel("Older / Compare")
            right_lbl.setAlignment(QtCore.Qt.AlignCenter)
            right_lbl.setStyleSheet("color:#ffcc66; background:#111; font-weight:bold;")
            self.pb_compare_media_player = QMediaPlayer(compare_frame)
            self.pb_compare_video_widget = QVideoWidget(compare_frame)
            self.pb_compare_video_widget.setMinimumHeight(300)
            if IS_PYSIDE6 and QAudioOutput is not None:
                self._pb_compare_audio_output = QAudioOutput(compare_frame)
                self.pb_compare_media_player.setAudioOutput(self._pb_compare_audio_output)
                self.pb_compare_media_player.setVideoOutput(self.pb_compare_video_widget)
            else:
                self.pb_compare_media_player.setVideoOutput(self.pb_compare_video_widget)
            right_col.addWidget(right_lbl)
            right_col.addWidget(self.pb_compare_video_widget, 1)
            compare_layout.addLayout(right_col, 1)
        else:
            warn2 = QtWidgets.QLabel(
                "Compare mode needs embedded playback (QtMultimedia), which "
                "isn't available in this Maya's Qt install.")
            warn2.setAlignment(QtCore.Qt.AlignCenter)
            warn2.setWordWrap(True)
            warn2.setStyleSheet("color: #ffcc66; padding: 40px;")
            compare_layout.addWidget(warn2)
        self.pb_preview_stack.addWidget(compare_frame)

        # -- page 3: wipe/slider compare (request #6) --------------------
        self.pb_wipe_compare = PBWipeCompareWidget(self.pb_preview_stack)
        self.pb_preview_stack.addWidget(self.pb_wipe_compare)

        self.pb_preview_stack.setCurrentIndex(0)   # default: live camera view

        preview_and_bottom = QtWidgets.QWidget()
        preview_and_bottom_layout = QtWidgets.QVBoxLayout(preview_and_bottom)
        preview_and_bottom_layout.setContentsMargins(0, 0, 0, 0)
        preview_and_bottom_layout.setSpacing(8)
        preview_and_bottom_layout.addWidget(self.pb_preview_stack, 1)

        # ── Bottom bar (request #3): loading a past playblast AND the
        # transport (play/pause/stop) controls live together here, below the
        # big screen, laid out as one clean toolbar-style row instead of a
        # side list competing with the preview for width. ─────────────────
        bottom_bar = QtWidgets.QFrame()
        bottom_bar.setStyleSheet("background:#2d2d30; border: 1px solid #3e3e42; border-radius: 4px;")
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 8, 10, 8)
        bottom_layout.setSpacing(10)

        bottom_layout.addWidget(QtWidgets.QLabel("📂 Playblast:"))
        self.pb_combo = QtWidgets.QComboBox()
        self.pb_combo.setMinimumWidth(260)
        self.pb_combo.setStyleSheet(
            "background:#1e1e1e; border:1px solid #444; color:white; padding: 4px;")
        self.pb_combo.currentIndexChanged.connect(self.pb_on_combo_changed)
        bottom_layout.addWidget(self.pb_combo, 1)

        btn_refresh_pb = QtWidgets.QPushButton("🔄")
        btn_refresh_pb.setToolTip("Refresh the list of playblasts")
        btn_refresh_pb.setFixedWidth(34)
        btn_refresh_pb.clicked.connect(self.refresh_playblast_list)
        bottom_layout.addWidget(btn_refresh_pb)

        sep0 = QtWidgets.QFrame(); sep0.setFrameShape(QtWidgets.QFrame.VLine); sep0.setStyleSheet("color:#555;")
        bottom_layout.addWidget(sep0)

        # ── Copy/Paste Settings (request #2): copy every Playblast tab
        # field from this rig's session and one-click paste them into
        # another rig's/session's Playblast tab. Goes through a class-level
        # clipboard shared by every open SessionWorkspace. ────────────────
        btn_pb_copy = QtWidgets.QPushButton("📋 Copy Settings")
        btn_pb_copy.setToolTip("Copy all Playblast tab settings to paste into another rig's Playblast tab.")
        btn_pb_copy.clicked.connect(self.pb_copy_settings)
        bottom_layout.addWidget(btn_pb_copy)

        btn_pb_paste = QtWidgets.QPushButton("📥 Paste Settings")
        btn_pb_paste.setToolTip("Paste the last-copied Playblast tab settings into this rig's Playblast tab.")
        btn_pb_paste.clicked.connect(self.pb_paste_settings)
        bottom_layout.addWidget(btn_pb_paste)

        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.VLine); sep.setStyleSheet("color:#555;")
        bottom_layout.addWidget(sep)

        btn_play = QtWidgets.QPushButton("▶")
        btn_play.setToolTip("Play")
        btn_pause = QtWidgets.QPushButton("⏸")
        btn_pause.setToolTip("Pause")
        btn_stop = QtWidgets.QPushButton("⏹")
        btn_stop.setToolTip("Stop")
        for b in (btn_play, btn_pause, btn_stop):
            b.setFixedSize(34, 28)
            b.setStyleSheet("background-color: #3e3e42; color: white; font-weight: bold;")
            bottom_layout.addWidget(b)
        if HAS_MULTIMEDIA:
            # Dispatchers (not the player directly) so these three buttons
            # also drive whichever compare page (side-by-side or wipe) is
            # currently active, not just the single-video page.
            btn_play.clicked.connect(self.pb_transport_play)
            btn_pause.clicked.connect(self.pb_transport_pause)
            btn_stop.clicked.connect(self.pb_transport_stop)
        else:
            btn_play.clicked.connect(self.pb_play_current_selection)
            btn_pause.setEnabled(False)
            btn_stop.setEnabled(False)

        self.lbl_pb_status = QtWidgets.QLabel("")
        self.lbl_pb_status.setStyleSheet("color: #888;")
        bottom_layout.addWidget(self.lbl_pb_status, 1)

        preview_and_bottom_layout.addWidget(bottom_bar)

        self.pb_main_splitter.addWidget(preview_and_bottom)
        self.pb_main_splitter.setStretchFactor(0, 0)
        self.pb_main_splitter.setStretchFactor(1, 1)
        # Initial split favors the preview screen (fix: it was reading too
        # small) - still fully draggable afterward, and Collapse Settings
        # above gives it the rest of the space in one click.
        self.pb_main_splitter.setSizes([260, 640])
        layout.addWidget(self.pb_main_splitter, 1)

        self.refresh_playblast_list()
        self.pb_refresh_from_scene(update_status=False)

        # Request #1: keep the live camera view pointed at whatever's in
        # the Camera field, live, as the user types/browses/selects.
        self.pb_camera_field.textChanged.connect(self.pb_on_camera_field_changed)
        self.pb_on_camera_field_changed(self.pb_camera_field.text())

        return page

    def pb_toggle_settings_collapsed(self, checked=None):
        """Collapse Settings button - fix for the preview screen reading
        too small with every settings row stacked above it. Shrinks the
        settings pane of the splitter down to just its title bar (not a
        hide - the splitter handle stays usable to pull it back open, and
        clicking the button again restores the previous split)."""
        if checked is None:
            checked = self.btn_pb_collapse_settings.isChecked()
        if not hasattr(self, "pb_main_splitter"):
            return
        sizes = self.pb_main_splitter.sizes()
        total = sum(sizes) or 900
        if checked:
            self._pb_settings_split_before_collapse = sizes
            self.pb_main_splitter.setSizes([28, total - 28])
            self.btn_pb_collapse_settings.setText("▼ Expand Settings")
        else:
            restore = getattr(self, "_pb_settings_split_before_collapse", None)
            self.pb_main_splitter.setSizes(restore if restore else [260, total - 260])
            self.btn_pb_collapse_settings.setText("▲ Collapse Settings")

    # ------------------------------------------------------------------
    # Live camera view wiring (Stage 39, request #1)
    # ------------------------------------------------------------------
    def pb_set_live_view_camera(self, camera_name):
        """Points the embedded live camera view (preview page 0) at
        `camera_name` and switches the preview screen to show it."""
        if not hasattr(self, "pb_camera_view"):
            return
        self.pb_camera_view.set_camera(camera_name)
        if hasattr(self, "pb_preview_stack") and not self.btn_pb_compare_toggle.isChecked():
            self.pb_preview_stack.setCurrentIndex(0)

    def pb_on_camera_field_changed(self, text):
        text = (text or "").strip()
        if text and cmds.objExists(text):
            self.pb_set_live_view_camera(text)

    def pb_on_live_camera_transform(self, pos, rot):
        """Called (via QTimer polling inside PBCameraViewWidget) whenever
        the live view's camera has moved - pushes the new position/
        rotation into the Generate Camera group's fields in real time, as
        requested, unless the user is actively typing in one of them."""
        fields = (
            (self.pb_gen_pos_x, pos[0]), (self.pb_gen_pos_y, pos[1]), (self.pb_gen_pos_z, pos[2]),
            (self.pb_gen_rot_x, rot[0]), (self.pb_gen_rot_y, rot[1]), (self.pb_gen_rot_z, rot[2]),
        )
        for field, value in fields:
            if field.hasFocus():
                continue
            field.setText("{:.3f}".format(value))

    # ------------------------------------------------------------------
    # Compare mode (Stage 39/40, requests #3/#5/#6): every playblast is
    # already saved as a distinct timestamped version (create_playblast's
    # ts = time.strftime(...) naming - nothing here ever overwrites an
    # older one unless "Save MP4 As" is set to the exact same path by
    # hand), so Compare A/B just need to let the user PICK two of those
    # versions instead of typing/browsing a path every time.
    # ------------------------------------------------------------------
    def pb_refresh_compare_combos(self):
        """Repopulates Compare A/B from the same playblast folder listing
        refresh_playblast_list already builds for the bottom bar's combo -
        newest first. Defaults A to the newest version and B to the
        second-newest, so 'compare the last two versions' works with zero
        clicks beyond hitting Compare. A manually browsed 'Other...' path
        (pb_browse_compare_path) is appended as its own entry in B so it
        doesn't get lost the next time this refreshes."""
        if not hasattr(self, "pb_compare_a_combo"):
            return
        d = self.get_playblast_dir()
        prev_a = self.pb_compare_a_combo.currentData()
        prev_b = self.pb_compare_b_combo.currentData()
        other_path = self.pb_compare_field.text().strip()

        entries = []
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.lower().endswith((".mov", ".avi", ".mp4"))]
            files.sort(reverse=True)
            entries = [(f, os.path.join(d, f).replace("\\", "/")) for f in files]

        entry_paths = {full for _label, full in entries}
        for combo, prev in ((self.pb_compare_a_combo, prev_a), (self.pb_compare_b_combo, prev_b)):
            combo.blockSignals(True)
            combo.clear()
            for label, full in entries:
                combo.addItem(label, full)
            if other_path and other_path not in entry_paths:
                combo.addItem("Other: {}".format(os.path.basename(other_path)), other_path)
            if combo.count() == 0:
                combo.addItem("(no playblasts yet)", "")
            combo.blockSignals(False)

        # Restore the previous picks if they still exist, otherwise default
        # to "newest" for A and "second-newest" for B.
        def _select(combo, prev, default_index):
            idx = combo.findData(prev) if prev else -1
            if idx < 0:
                idx = default_index if default_index < combo.count() else 0
            combo.setCurrentIndex(max(0, idx))

        _select(self.pb_compare_a_combo, prev_a, 0)
        _select(self.pb_compare_b_combo, prev_b, 1)

    def pb_browse_compare_path(self):
        current = self.pb_compare_field.text().strip()
        start_dir = os.path.dirname(current) if current else self.get_playblast_dir()
        res = cmds.fileDialog2(
            fileMode=1, caption="Select an Older Playblast to Compare Against",
            startingDirectory=start_dir if os.path.exists(start_dir) else "",
            fileFilter="Video (*.mp4 *.mov *.avi)")
        if not res:
            return
        self.pb_compare_field.setText(res[0])
        self.pb_refresh_compare_combos()
        # Select the just-browsed path in Compare B straight away.
        idx = self.pb_compare_b_combo.findData(res[0])
        if idx >= 0:
            self.pb_compare_b_combo.setCurrentIndex(idx)

    def pb_resolve_compare_paths(self):
        """Returns (path_a, path_b, label_a, label_b) from Compare A/B,
        falling back to the current/last-played clip for A and the legacy
        freeform Compare field for B if either combo has nothing usable -
        keeps old saved settings (from before A/B existed) working."""
        path_a = self.pb_compare_a_combo.currentData() if hasattr(self, "pb_compare_a_combo") else None
        path_b = self.pb_compare_b_combo.currentData() if hasattr(self, "pb_compare_b_combo") else None
        if not path_a or not os.path.isfile(path_a):
            path_a = getattr(self, "_pb_last_loaded_path", None)
        if not path_b or not os.path.isfile(path_b):
            fallback_b = self.pb_compare_field.text().strip()
            path_b = fallback_b if fallback_b and os.path.isfile(fallback_b) else path_b
        label_a = os.path.basename(path_a) if path_a else "A"
        label_b = os.path.basename(path_b) if path_b else "B"
        return path_a, path_b, label_a, label_b

    def pb_toggle_compare_mode(self, checked=None):
        if checked is None:
            checked = self.btn_pb_compare_toggle.isChecked()
        if checked:
            self.pb_enter_compare_mode()
        else:
            self.pb_exit_compare_mode()

    def pb_enter_compare_mode(self):
        if not hasattr(self, "pb_preview_stack"):
            self.btn_pb_compare_toggle.setChecked(False)
            return
        path_a, path_b, label_a, label_b = self.pb_resolve_compare_paths()
        if not path_a or not os.path.isfile(path_a) or not path_b or not os.path.isfile(path_b):
            cmds.warning("[KRT] Pick a valid Compare A and Compare B (or Browse an 'Other...' B) first.")
            self.btn_pb_compare_toggle.setChecked(False)
            return

        want_wipe = self.pb_compare_mode_combo.currentText().startswith("Wipe")
        use_wipe = want_wipe and hasattr(self, "pb_wipe_compare") and self.pb_wipe_compare.is_available()
        if want_wipe and not use_wipe:
            cmds.warning(
                "[KRT] Wipe/Slider compare needs PySide6/Qt6 multimedia, which "
                "isn't available in this Maya's Qt install - showing Side-by-"
                "Side instead.")

        if use_wipe:
            self.pb_wipe_compare.load(path_a, path_b, label_a=label_a, label_b=label_b)
            self.pb_wipe_compare.play()
            self.pb_preview_stack.setCurrentIndex(3)
            self.btn_pb_compare_toggle.setChecked(True)
            return

        if not HAS_MULTIMEDIA:
            cmds.warning("[KRT] Compare mode needs embedded playback (QtMultimedia), which isn't available here.")
            self.btn_pb_compare_toggle.setChecked(False)
            return

        # Move the single "current" video widget over into the compare
        # page's left-hand container so the same media player drives it
        # in either mode, rather than needing a second player just for
        # the current clip.
        self.pb_compare_current_container.layout().addWidget(self.pb_video_widget, 1)
        self.pb_load_media(self.pb_media_player, path_a)
        self.pb_load_media(self.pb_compare_media_player, path_b)
        self.pb_preview_stack.setCurrentIndex(2)
        self.btn_pb_compare_toggle.setChecked(True)

    def pb_exit_compare_mode(self):
        self.btn_pb_compare_toggle.setChecked(False)
        if not hasattr(self, "pb_preview_stack"):
            return
        if hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.stop()
        if HAS_MULTIMEDIA:
            # Move the "current" video widget back to its normal single-
            # video playback page.
            parent_widget = self.pb_preview_stack.widget(1)
            if parent_widget is not None and self.pb_video_widget.parentWidget() is not parent_widget:
                parent_widget.layout().addWidget(self.pb_video_widget)
            if self.pb_compare_media_player is not None:
                self.pb_compare_media_player.stop()
        self.pb_preview_stack.setCurrentIndex(1 if self._pb_has_loaded_media() else 0)

    def pb_load_media(self, player, path):
        """Small shared helper - loads `path` into `player` (a
        QMediaPlayer), the same call pattern already used by
        pb_on_combo_changed for the single-video page."""
        if player is None or not path:
            return
        try:
            url = QtCore.QUrl.fromLocalFile(path)
            if IS_PYSIDE6:
                player.setSource(url)
            elif QMediaContent is not None:
                player.setMedia(QMediaContent(url))
            player.play()
        except Exception:
            pass

    def _pb_has_loaded_media(self):
        return bool(getattr(self, "_pb_last_loaded_path", ""))

    def pb_transport_play(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.play()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.play()
            self.pb_compare_media_player.play()
        else:
            self.pb_media_player.play()

    def pb_transport_pause(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.pause()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.pause()
            self.pb_compare_media_player.pause()
        else:
            self.pb_media_player.pause()

    def pb_transport_stop(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.stop()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.stop()
            self.pb_compare_media_player.stop()
        else:
            self.pb_media_player.stop()

    def pb_use_selected_camera(self):
        sel = cmds.ls(sl=True, type="camera") or cmds.listRelatives(cmds.ls(sl=True) or [], shapes=True, type="camera") or []
        sel_transforms = cmds.ls(sl=True, type="transform") or []
        cam = None
        for t in sel_transforms:
            shapes = cmds.listRelatives(t, shapes=True, type="camera") or []
            if shapes:
                cam = t
                break
        if not cam:
            cmds.warning("Select a camera (or its transform) first.")
            return
        self.pb_camera_field.setText(cam)

    def pb_use_selected_group(self):
        sel = cmds.ls(sl=True) or []
        if not sel:
            cmds.warning("Select a group/node first.")
            return
        self.pb_group_field.setText(sel[0])

    # ------------------------------------------------------------------
    # Playblast settings dict (Stage 39): the single source of truth for
    # what "all Playblast tab settings" means, shared by JSON save/load
    # (get_current_pipeline_data/load_pipeline_from_file) AND the new
    # Copy/Paste Settings buttons (request #2), so the three stay in sync
    # instead of drifting apart across separate implementations.
    # ------------------------------------------------------------------
    _pb_settings_clipboard = None   # class-level: shared across every open SessionWorkspace/rig

    def pb_get_settings_dict(self):
        return {
            "camera": self.pb_camera_field.text(),
            "group": self.pb_group_field.text(),
            "anim_path": self.pb_anim_field.text(),
            "output_path": self.pb_output_field.text(),
            "project": self.pb_project_field.text(),
            "character": self.pb_character_field.text(),
            "artist": self.pb_artist_field.text(),
            "controls_filter": self.pb_pattern_field.text(),
            "start_frame": self.pb_start_field.text(),
            "end_frame": self.pb_end_field.text(),
            "fps": self.pb_fps_field.text(),
            "resolution": self.pb_resolution_menu.currentText(),
            "gen_pos_x": self.pb_gen_pos_x.text(),
            "gen_pos_y": self.pb_gen_pos_y.text(),
            "gen_pos_z": self.pb_gen_pos_z.text(),
            "gen_rot_x": self.pb_gen_rot_x.text() if hasattr(self, "pb_gen_rot_x") else "0.0",
            "gen_rot_y": self.pb_gen_rot_y.text() if hasattr(self, "pb_gen_rot_y") else "0.0",
            "gen_rot_z": self.pb_gen_rot_z.text() if hasattr(self, "pb_gen_rot_z") else "0.0",
            "gen_focal_length": self.pb_gen_focal_length.text(),
            "gen_camera_scale": self.pb_gen_camera_scale.text(),
            "gen_near_clip": self.pb_gen_near_clip.text(),
            "gen_far_clip": self.pb_gen_far_clip.text(),
            "gen_auto_clip": self.pb_gen_auto_clip_chk.isChecked(),
            "compare_path": self.pb_compare_field.text() if hasattr(self, "pb_compare_field") else "",
            "compare_mode": self.pb_compare_mode_combo.currentText() if hasattr(self, "pb_compare_mode_combo") else "Wipe / Slider",
        }

    def pb_apply_settings_dict(self, pb_data):
        if not pb_data:
            return
        self.pb_camera_field.setText(pb_data.get("camera", ""))
        self.pb_group_field.setText(pb_data.get("group", ""))
        self.pb_anim_field.setText(pb_data.get("anim_path", ""))
        self.pb_output_field.setText(pb_data.get("output_path", ""))
        self.pb_project_field.setText(pb_data.get("project", ""))
        self.pb_character_field.setText(pb_data.get("character", ""))
        self.pb_artist_field.setText(pb_data.get("artist", ""))
        self.pb_pattern_field.setText(pb_data.get("controls_filter", "*_ctl"))
        if pb_data.get("start_frame"): self.pb_start_field.setText(pb_data.get("start_frame"))
        if pb_data.get("end_frame"): self.pb_end_field.setText(pb_data.get("end_frame"))
        if pb_data.get("fps"): self.pb_fps_field.setText(pb_data.get("fps"))
        resolution = pb_data.get("resolution")
        if resolution:
            idx = self.pb_resolution_menu.findText(resolution)
            if idx >= 0: self.pb_resolution_menu.setCurrentIndex(idx)
        if pb_data.get("gen_pos_x") is not None: self.pb_gen_pos_x.setText(pb_data.get("gen_pos_x"))
        if pb_data.get("gen_pos_y") is not None: self.pb_gen_pos_y.setText(pb_data.get("gen_pos_y"))
        if pb_data.get("gen_pos_z") is not None: self.pb_gen_pos_z.setText(pb_data.get("gen_pos_z"))
        if hasattr(self, "pb_gen_rot_x"):
            if pb_data.get("gen_rot_x") is not None: self.pb_gen_rot_x.setText(pb_data.get("gen_rot_x"))
            if pb_data.get("gen_rot_y") is not None: self.pb_gen_rot_y.setText(pb_data.get("gen_rot_y"))
            if pb_data.get("gen_rot_z") is not None: self.pb_gen_rot_z.setText(pb_data.get("gen_rot_z"))
        if pb_data.get("gen_focal_length"): self.pb_gen_focal_length.setText(pb_data.get("gen_focal_length"))
        if pb_data.get("gen_camera_scale"): self.pb_gen_camera_scale.setText(pb_data.get("gen_camera_scale"))
        if pb_data.get("gen_near_clip"): self.pb_gen_near_clip.setText(pb_data.get("gen_near_clip"))
        if pb_data.get("gen_far_clip"): self.pb_gen_far_clip.setText(pb_data.get("gen_far_clip"))
        if "gen_auto_clip" in pb_data: self.pb_gen_auto_clip_chk.setChecked(bool(pb_data.get("gen_auto_clip")))
        if hasattr(self, "pb_compare_field") and pb_data.get("compare_path") is not None:
            self.pb_compare_field.setText(pb_data.get("compare_path"))
        if hasattr(self, "pb_compare_mode_combo") and pb_data.get("compare_mode"):
            idx = self.pb_compare_mode_combo.findText(pb_data.get("compare_mode"))
            if idx >= 0: self.pb_compare_mode_combo.setCurrentIndex(idx)
        if hasattr(self, "pb_compare_a_combo"):
            self.pb_refresh_compare_combos()
        # Camera field's textChanged is already wired to keep the live
        # view in sync - re-push it explicitly too, in case the text
        # didn't actually change (setText is a no-op signal-wise then).
        if hasattr(self, "pb_camera_view"):
            self.pb_on_camera_field_changed(self.pb_camera_field.text())

    def pb_copy_settings(self):
        """Request #2: copies every Playblast tab field on this rig into a
        class-level clipboard, shared by every open KRT session/rig, so it
        can be pasted into a different rig's Playblast tab with one click."""
        SessionWorkspace._pb_settings_clipboard = self.pb_get_settings_dict()
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Playblast settings copied - use Paste Settings on another rig to apply them.")

    def pb_paste_settings(self):
        """Request #2: applies the last Copy Settings' clipboard to this
        rig's Playblast tab. Camera/Group/Anim/Output/Compare are text
        paths - they're pasted as-is (they may point at nodes/files that
        don't exist on this rig/scene, same as typing them in by hand)."""
        clip = SessionWorkspace._pb_settings_clipboard
        if not clip:
            cmds.warning("[KRT] No Playblast settings have been copied yet - use Copy Settings first.")
            return
        self.pb_apply_settings_dict(clip)
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Playblast settings pasted from clipboard.")

    def pb_browse_anim_json(self):
        """Stage 37: picks a Studio Library .anim clip - these are
        FOLDERS (e.g. "myWave.anim/"), not a single JSON file, so this
        uses a directory picker. Also auto-fills Start/End from the
        clip's own frame range (still editable) so the Playblast's
        capture range matches the clip by default."""
        start_dir = self.get_playblast_dir()
        res = cmds.fileDialog2(fileMode=3, caption="Select a Studio Library Animation (.anim) Folder",
                               startingDirectory=start_dir if os.path.exists(start_dir) else "")
        if not res:
            return
        anim_path = res[0].rstrip("/\\")
        self.pb_anim_field.setText(anim_path)

        if not self.pb_is_studiolibrary_anim_path(anim_path):
            cmds.warning(
                "[KRT] '{}' doesn't look like a Studio Library .anim item "
                "(expected pose.json + animation.ma/.mb inside it).".format(anim_path))
            return

        start_frame, end_frame = self.pb_get_anim_frame_range(anim_path)
        if start_frame is not None and end_frame is not None:
            self.pb_start_field.setText(str(int(start_frame)))
            self.pb_end_field.setText(str(int(end_frame)))
            if hasattr(self, "lbl_pb_status"):
                self.lbl_pb_status.setText(
                    "Animation clip selected: {} ({} - {})".format(
                        os.path.basename(anim_path), int(start_frame), int(end_frame)))

    def pb_browse_output_path(self):
        """Stage 36: optional explicit Save MP4 As... path, ported from the
        studio script's own output Browse button. Leaving the field blank
        keeps KRT's original auto-timestamped-into-the-playblasts-folder
        naming (see create_playblast)."""
        current = self.pb_output_field.text().strip()
        start_dir = os.path.dirname(current) if current else self.get_playblast_dir()
        selected = cmds.fileDialog2(
            fileMode=0, dialogStyle=2, caption="Save QC Playblast MP4",
            startingDirectory=start_dir if os.path.exists(start_dir) else "",
            fileFilter="MP4 Video (*.mp4)")
        if not selected:
            return
        out_path = selected[0]
        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
        self.pb_output_field.setText(out_path)

    def pb_refresh_from_scene(self, update_status=True):
        """Refresh From Scene (Stage 36, ported from the studio QC Playblast
        script): re-detects Project/Character/Artist from the scene's
        filename, and Start/End/FPS from the scene itself. Project is only
        auto-filled if the field is currently empty - a manually-typed
        project name is never overwritten, since (unlike the single-project
        studio script) KRT is used across multiple shows/characters."""
        if not hasattr(self, "pb_project_field"):
            return

        scene_path = cmds.file(query=True, sceneName=True) or ""
        scene_stem = os.path.splitext(os.path.basename(scene_path))[0] if scene_path else "Untitled"

        current_project = self.pb_project_field.text().strip()
        if not current_project:
            current_project = self.edit_rig_name.text().strip() if hasattr(self, "edit_rig_name") else ""
            current_project = current_project or "Untitled Project"
            self.pb_project_field.setText(current_project)

        character = self.pb_parse_character_from_filename(scene_stem, project_name=current_project)
        artist = self.pb_parse_artist_from_filename(scene_stem)

        start_frame = int(round(cmds.playbackOptions(query=True, minTime=True)))
        end_frame = int(round(cmds.playbackOptions(query=True, maxTime=True)))
        fps = self.pb_get_scene_fps()

        self.pb_character_field.setText(character)
        self.pb_artist_field.setText(artist)
        self.pb_start_field.setText(str(start_frame))
        self.pb_end_field.setText(str(end_frame))
        self.pb_fps_field.setText(self.pb_format_fps(fps))

        if update_status and hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText(
                "Refreshed from scene: {} | {}-{} | {} FPS".format(
                    scene_stem, start_frame, end_frame, self.pb_format_fps(fps)))

    def pb_get_output_resolution(self):
        """(width, height), or (None, None) for "Current Viewport" - i.e.
        don't force a size, matching KRT's original playblast behavior."""
        if not hasattr(self, "pb_resolution_menu"):
            return None, None
        selected = self.pb_resolution_menu.currentText()
        if "720" in selected:
            return 1280, 720
        if "1080" in selected:
            return 1920, 1080
        if "VGA" in selected:
            return 640, 480
        if "Square" in selected:
            return 1024, 1024
        return None, None

    def pb_create_clicked(self):
        try:
            start = int(self.pb_start_field.text().strip())
        except Exception:
            start = None
        try:
            end = int(self.pb_end_field.text().strip())
        except Exception:
            end = None
        try:
            fps = float(self.pb_fps_field.text().strip())
            if fps <= 0:
                fps = None
        except Exception:
            fps = None

        width, height = self.pb_get_output_resolution()

        self.lbl_pb_status.setText("Creating playblast...")
        QtWidgets.QApplication.processEvents()
        success, err, out_path = self.create_playblast(
            self.pb_camera_field.text(), self.pb_group_field.text(),
            self.pb_anim_field.text(), self.pb_pattern_field.text(),
            start_frame=start, end_frame=end, width=width, height=height, fps=fps,
            project_name=self.pb_project_field.text().strip(),
            character_name=self.pb_character_field.text().strip(),
            artist_name=self.pb_artist_field.text().strip(),
            output_path_override=self.pb_output_field.text().strip())
        if not success:
            self.lbl_pb_status.setText("Failed - see Script Editor.")
            cmds.warning("[KRT] Playblast failed: {}".format(err))
            try:
                cmds.confirmDialog(
                    title="Playblast Error", message=(err or "")[-6000:],
                    button=["OK"], defaultButton="OK", icon="critical")
            except Exception:
                pass
            return
        self.lbl_pb_status.setText("Created: {}".format(out_path))
        self.refresh_playblast_list(select_path=out_path)
        if out_path:
            self.pb_play_path(out_path)

    def refresh_playblast_list(self, select_path=None):
        """Repopulate the bottom bar's Playblast dropdown. `select_path`, if
        given (e.g. right after Create Playblast), is selected afterward -
        otherwise the current selection is kept if it's still in the list."""
        if not hasattr(self, "pb_combo"):
            return
        prev_path = select_path or self.pb_combo.currentData()
        self.pb_combo.blockSignals(True)
        self.pb_combo.clear()
        d = self.get_playblast_dir()
        select_index = -1
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.lower().endswith((".mov", ".avi", ".mp4"))]
            files.sort(reverse=True)
            for fn in files:
                full = os.path.join(d, fn).replace("\\", "/")
                self.pb_combo.addItem(fn, full)
                if prev_path and full == prev_path:
                    select_index = self.pb_combo.count() - 1
            if self.pb_combo.count() == 0:
                self.pb_combo.addItem("(no playblasts yet)", "")
        else:
            self.pb_combo.addItem("(no playblasts yet)", "")
        self.pb_combo.blockSignals(False)
        if select_index >= 0:
            self.pb_combo.setCurrentIndex(select_index)
        elif select_path:
            # Just-created file didn't match anything (shouldn't normally
            # happen) - default to the newest entry instead of nothing.
            self.pb_combo.setCurrentIndex(0)
        self.pb_refresh_compare_combos()

    def pb_on_combo_changed(self, index):
        path = self.pb_combo.itemData(index)
        if path and os.path.isfile(path):
            self.pb_play_path(path)

    def pb_play_current_selection(self):
        path = self.pb_combo.currentData()
        if not path:
            cmds.warning("No playblast selected.")
            return
        self.pb_play_path(path)

    def pb_play_path(self, path):
        if not path or not os.path.isfile(path):
            cmds.warning("Playblast file not found: {}".format(path))
            return
        if HAS_MULTIMEDIA and self.pb_media_player is not None:
            url = QtCore.QUrl.fromLocalFile(path)
            if IS_PYSIDE6:
                self.pb_media_player.setSource(url)
            elif QMediaContent is not None:
                self.pb_media_player.setMedia(QMediaContent(url))
            else:
                # Older PySide2 without QMediaContent available - can't wire
                # up embedded playback reliably, fall back to the OS player.
                try:
                    os.startfile(path)
                except Exception as e:
                    cmds.warning("Could not open playblast: {}".format(e))
                return
            self.pb_media_player.play()
            self.lbl_pb_status.setText("Playing: {}".format(os.path.basename(path)))
            self._pb_last_loaded_path = path
            # Stage 39: picking a playblast to review switches the preview
            # screen off the live camera view and onto the video page (or
            # keeps compare mode's page if that's active).
            if hasattr(self, "pb_preview_stack") and not self.btn_pb_compare_toggle.isChecked():
                self.pb_preview_stack.setCurrentIndex(1)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                cmds.warning("Could not open playblast: {}".format(e))

    def create_nav_btn(self, icon, tip):
        btn = QtWidgets.QPushButton(icon); btn.setFixedSize(50, 50); btn.setToolTip(tip); btn.setFlat(True)
        btn.setStyleSheet("font-size: 22px; color: white; border: none;"); return btn