"""SessionWorkspace - pages methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspacePagesMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


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

        # Stage 41: Rig Root row. One folder; every path field below stores
        # only its part under this root (scripts/utils.py) - see
        # workspace/root_path.py for resolve/relativize.
        root_layout = QtWidgets.QHBoxLayout()
        root_layout.setContentsMargins(15, 0, 15, 5)
        lbl_root = QtWidgets.QLabel("<b>Rig Root:</b>")
        lbl_root.setStyleSheet("color: #cccccc; font-size: 13px;")
        root_layout.addWidget(lbl_root)
        self.edit_rig_root = QtWidgets.QLineEdit(getattr(self, "_rig_root", ""))
        self.edit_rig_root.setPlaceholderText("P:/.../all_Rigs/<rig_name>   - every path below is relative to this folder")
        self.edit_rig_root.setToolTip(
            "Root folder of this rig. Panel paths, module files and graph .sgt paths\n"
            "are stored RELATIVE to it (e.g. scripts/utils.py). Paths outside the\n"
            "root stay absolute. Saved into the pipeline JSON as 'root_path'.")
        self.edit_rig_root.setStyleSheet(
            "QLineEdit { background: #1e1e1e; border: 1px solid #2bb5a8; color: #ffd27f; padding: 5px;"
            " font-size: 13px; border-radius: 3px; }")
        self.edit_rig_root.editingFinished.connect(self.on_rig_root_edited)
        root_layout.addWidget(self.edit_rig_root, 1)
        btn_root_browse = QtWidgets.QPushButton("📁")
        btn_root_browse.setFixedWidth(34)
        btn_root_browse.setToolTip("Browse for the rig root folder.")
        btn_root_browse.clicked.connect(self.browse_rig_root)
        root_layout.addWidget(btn_root_browse)
        btn_root_rel = QtWidgets.QPushButton("⇄ Make Relative")
        btn_root_rel.setToolTip("Shorten every path that lives under the Rig Root (panels, module bubbles, graph nodes).")
        btn_root_rel.setStyleSheet(
            "QPushButton { background: #333; color: #cccccc; border: 1px solid #2bb5a8; padding: 5px 8px;"
            " border-radius: 3px; } QPushButton:hover { background: #444; color: white; }")
        btn_root_rel.clicked.connect(self.relativize_all_paths)
        root_layout.addWidget(btn_root_rel)
        main_vbox.addLayout(root_layout)

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
        from ..dialogs import AyonPublishDialog
        from ..compat import IS_PYSIDE6
        dialog = AyonPublishDialog(self)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def open_path_replace_dialog(self):
        from ..dialogs import PathReplaceDialog
        dialog = PathReplaceDialog(self)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def refresh_comment_view(self):
        """Show the current file's saved comment in the read-only bottom row."""
        cv = getattr(self, 'comment_view', None)
        if cv is not None:
            cv.setText(getattr(self, 'pipeline_comment', "") or "")

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
