"""Auto-split from workspace.py."""
from ._shared import *


from .lods import WorkspaceLodsMixin
from .pages import WorkspacePagesMixin
from .panels import WorkspacePanelsMixin
from .build import WorkspaceBuildMixin
from .pipeline_io import WorkspacePipelineIoMixin
from .executors import WorkspaceExecutorsMixin
from .playblast import WorkspacePlayblastMixin


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
class SessionWorkspace(WorkspaceLodsMixin, WorkspacePagesMixin, WorkspacePanelsMixin, WorkspaceBuildMixin, WorkspacePipelineIoMixin, WorkspaceExecutorsMixin, WorkspacePlayblastMixin, QtWidgets.QWidget):
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

    def _pb_has_loaded_media(self):
        return bool(getattr(self, "_pb_last_loaded_path", ""))

    # ------------------------------------------------------------------
    # Playblast settings dict (Stage 39): the single source of truth for
    # what "all Playblast tab settings" means, shared by JSON save/load
    # (get_current_pipeline_data/load_pipeline_from_file) AND the new
    # Copy/Paste Settings buttons (request #2), so the three stay in sync
    # instead of drifting apart across separate implementations.
    # ------------------------------------------------------------------
    _pb_settings_clipboard = None   # class-level: shared across every open SessionWorkspace/rig

    def create_nav_btn(self, icon, tip):
        btn = QtWidgets.QPushButton(icon); btn.setFixedSize(50, 50); btn.setToolTip(tip); btn.setFlat(True)
        btn.setStyleSheet("font-size: 22px; color: white; border: none;"); return btn