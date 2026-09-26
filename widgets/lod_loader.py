"""Auto-split from widgets.py."""
from ._shared import *
from .collapse import CollapseMixin
from .selection import SelectableMixin
from .dialogs import ErrorDialog
from .flow_layout import FlowLayout
from .style import type_accent, type_bg_tint, type_icon


class LodLoaderBubble(QtWidgets.QFrame):
    """Stage 21: one bubble in a LOD Loader panel - a single LOD picked to
    be included in this panel's LOAD build, in the order it was added.
    Click the name to jump to that LOD's own panels; × removes it from
    this panel (it stays a real LOD, of course - this only removes it from
    THIS panel's build list)."""

    closed = QtCore.Signal(object)
    jump_req = QtCore.Signal(str)

    def __init__(self, name):
        super(LodLoaderBubble, self).__init__()
        self.name = name
        self.setStyleSheet(
            "LodLoaderBubble { background:#3e3e42; border-radius: 10px; border:1px solid #555; }")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.btn_text = QtWidgets.QPushButton(name)
        self.btn_text.setFlat(True)
        self.btn_text.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_text.setStyleSheet("background: transparent; border: none; color: #ccc; font-weight: bold;")
        self.btn_text.setToolTip("Click to jump to this LOD's panels")
        self.btn_text.clicked.connect(lambda: self.jump_req.emit(self.name))
        layout.addWidget(self.btn_text)

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setToolTip("Remove from this panel")
        self.close_btn.setStyleSheet("background: transparent; border: none; color: #e57373; font-weight: bold;")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))
        layout.addWidget(self.close_btn)


class LodLoaderPanel(CollapseMixin, SelectableMixin, QtWidgets.QFrame):
    """A panel type that builds ENTIRE LODs, one RUN click at a time - the
    corrected form of Stage 19's "LOD Build Manager" request (Stage 20).
    Stage 23: its button reads RUN, not LOAD - it's a normal step that
    participates in ordered runs (Build Till Here, etc) same as any other
    panel, not a special separate action.
    Lives inside a LOD's own panel stack in the Rig Build Workspace,
    addable the same way Control Shapes / Module Bubbles panels are (the
    "+Add New Panel" dropdown and the right-click "Add Panel" submenus),
    and is visually distinct via its own PANEL_TYPE_ACCENTS/ICONS/BG_TINT
    entry ("LOD_LOADER").

    Stage 21 revision: sized and laid out exactly like a Module Bubbles
    panel instead of the taller, list-based Stage 20 layout - a "+ Add LOD"
    button opens a menu of real LODs not already in this panel (pick which
    ones you want, instead of starting with every LOD pre-added), each
    picked LOD becomes a small bubble (LodLoaderBubble) in the order
    added, and there's no manual Sync button anymore - this panel listens
    directly to the real LOD list (self.workspace.lod_list) and prunes any
    bubble whose LOD gets deleted or renamed elsewhere, automatically.

    Does not use CacheMixin: caching one step doesn't compose meaningfully
    when the "step" is itself a full multi-panel LOD build.
    """

    def __init__(self, title, workspace):
        super(LodLoaderPanel, self).__init__()
        self.p_type = "LOD_LOADER"
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint("LOD_LOADER")
        self.accent = type_accent("LOD_LOADER")
        self.uuid = uuid.uuid4().hex
        self.lod_bubbles = []

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(self.toggle_active)

        self.icon_label = QtWidgets.QLabel(type_icon("LOD_LOADER"))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip("LOD Loader - builds entire LODs")

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        # Stage 50: panel titles are WHITE, not the panel-type accent.
        # The accent colours (green/purple/orange...) sit at 40-60% contrast
        # against the dark card and are hard to read at 13px; the type is
        # still signalled by the icon and the left border stripe, so the
        # title itself does not need to carry it.
        self.title_edit.setStyleSheet("background: transparent; border: none; font-weight: bold; color: white; font-size: 15px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox); header_layout.addWidget(self.icon_label); header_layout.addWidget(self.title_edit); header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Stage 52: the step's action buttons (cache 🗑 💾 ⏩, RUN/LOAD, ↺,
        # Cache tick) live in the HEADER row, right-aligned, instead of the
        # body row - so they stay usable while the panel is collapsed.
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.setSpacing(4)

        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        ctrl_layout.addWidget(self.btn_del)

        self.bubble_area = QtWidgets.QWidget()
        # Stage 35: same wrapping fix as the Module Bubbles panel - enough
        # LOD bubbles added here used to run off the edge the same way.
        self.bubble_layout = FlowLayout(self.bubble_area, margin=0, h_spacing=4, v_spacing=4)

        btn_add_lod = QtWidgets.QPushButton("+ Add LOD")
        btn_add_lod.setFixedWidth(100)
        btn_add_lod.setToolTip("Pick which LOD to add to this panel's build list.")
        btn_add_lod.clicked.connect(self.add_lod_bubble_picker)

        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.clicked.connect(self.show_context_menu)

        self.btn_run = QtWidgets.QPushButton("🚀 RUN")
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #ffca28; color: #1a1a1a; font-weight: bold;")
        self.btn_run.clicked.connect(self.on_btn_run_clicked)

        body_layout.addLayout(ctrl_layout)
        body_layout.addWidget(self.bubble_area)
        body_layout.addWidget(btn_add_lod)
        action_layout.addWidget(self.btn_run)

        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        action_layout.addWidget(self.btn_reset_err)
        action_layout.addWidget(btn_dots)   # Stage 53: "..." in the title row
        header_layout.addLayout(action_layout)

        # Stage 35: same top-alignment fix as the Module Bubbles panel - once
        # self.bubble_area can be several rows tall, a plain QHBoxLayout
        # centers every other widget on the full height of that block.
        for i in range(body_layout.count()):
            item = body_layout.itemAt(i)
            target = item.widget() or item.layout()
            if target is not None and target is not self.bubble_area:
                body_layout.setAlignment(target, QtCore.Qt.AlignTop)

        main_layout.addLayout(body_layout)
        self.btn_del.clicked.connect(self._on_delete_clicked)

        # Stage 21: no more manual "Sync" button - listen directly to the
        # real LOD list so a LOD deleted or renamed elsewhere automatically
        # drops out of this panel instead of sitting there stale until a
        # button click. (A rename shows up as a delete of the old name -
        # the renamed LOD itself just needs picking again via + Add LOD,
        # since there's no reliable way to tell "renamed" apart from
        # "removed, unrelated one added" from the list signals alone.)
        if hasattr(self.workspace, "lod_list"):
            self.workspace.lod_list.itemChanged.connect(self._on_lod_manager_changed)
            self.workspace.lod_list.model().rowsRemoved.connect(self._on_lod_manager_changed)

        # Stage 49: collapse toggle - must run last, once every row
        # this panel type adds has been put into main_layout.
        self._init_collapse(main_layout, header_layout)

    # -- bubble management -------------------------------------------------
    def add_lod_bubble_picker(self):
        if not hasattr(self.workspace, "lod_list"):
            cmds.warning("No LODs available yet.")
            return
        existing = {b.name for b in self.lod_bubbles}
        available = [self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())
                     if self.workspace.lod_list.item(i).text() not in existing]
        if not available:
            cmds.warning("No more LODs available to add (or none exist yet).")
            return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        actions = {}
        for name in available:
            actions[menu.addAction(name)] = name
        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if action and action in actions:
            self._add_lod_bubble(actions[action])

    def _add_lod_bubble(self, name):
        bubble = LodLoaderBubble(name)
        bubble.closed.connect(self._remove_lod_bubble)
        bubble.jump_req.connect(self.jump_to_lod_by_name)
        self.bubble_layout.addWidget(bubble)
        self.lod_bubbles.append(bubble)
        return bubble

    def _remove_lod_bubble(self, bubble):
        if bubble in self.lod_bubbles:
            self.lod_bubbles.remove(bubble)
        self.bubble_layout.removeWidget(bubble)
        bubble.deleteLater()

    def _on_lod_manager_changed(self, *args):
        try:
            self._prune_stale_bubbles()
        except RuntimeError:
            pass

    def _prune_stale_bubbles(self):
        if not hasattr(self.workspace, "lod_list"):
            return
        real_names = {self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())}
        for bubble in list(self.lod_bubbles):
            if bubble.name not in real_names:
                self._remove_lod_bubble(bubble)

    def sync_from_lod_manager(self):
        """Stage 21: bubbles are now added one at a time via '+ Add LOD',
        not auto-populated from the full LOD list - this just prunes any
        bubble whose LOD no longer exists. Kept as the entry point
        workspace.py already calls right after construction/on load."""
        self._prune_stale_bubbles()

    def checked_lod_names(self):
        return [b.name for b in self.lod_bubbles]

    def set_checked_lod_names(self, names):
        for b in list(self.lod_bubbles):
            self._remove_lod_bubble(b)
        if not names:
            return
        real_names = None
        if hasattr(self.workspace, "lod_list"):
            real_names = {self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())}
        for name in names:
            if real_names is None or name in real_names:
                self._add_lod_bubble(name)

    def jump_to_lod_by_name(self, name):
        idx = self.workspace._find_lod_row_by_name(name)
        if idx is None:
            cmds.warning("LOD '{}' not found anymore.".format(name))
            return
        self.workspace.lod_list.setCurrentRow(idx)

    # -- appearance / rename / drag (same pattern as the other panel types) --
    def reset_run_button(self):
        self.btn_run.setText("🚀 RUN")
        self.btn_run.setStyleSheet("background-color: #ffca28; color: #1a1a1a; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def update_style(self):
        accent = getattr(self, 'accent', type_accent("LOD_LOADER"))
        self.setStyleSheet(
            f"LodLoaderPanel {{ background: {self.bg_color}; border: {self._border_css()};"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" LodLoaderPanel:hover {{ border: {self._border_css('#555')}; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #ffca28; font-weight: bold; color: white; font-size: 15px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(LodLoaderPanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet("background: transparent; border: none; font-weight: bold; color: white; font-size: 15px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(LodLoaderPanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton):
            return super(LodLoaderPanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(LodLoaderPanel, self).mouseMoveEvent(event)

        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return super(LodLoaderPanel, self).mouseMoveEvent(event)

        self.workspace.dragged_panel = self
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText("panel_drag")
        drag.setMimeData(mime_data)

        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        if IS_PYSIDE6: drag.exec(QtCore.Qt.MoveAction)
        else: drag.exec_(QtCore.Qt.MoveAction)

        self.workspace.dragged_panel = None
        super(LodLoaderPanel, self).mouseMoveEvent(event)

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
        elif p_type == "LOD_LOADER":
            self.workspace.add_lod_loader_panel(title, index=idx)
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")

        a_undo = menu.addAction("↩ Undo Delete/Cut")
        if not getattr(self.workspace, 'panel_undo_stack', None):
            a_undo.setEnabled(False)
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")

        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Default Script (Maya Global)")] = ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", offset)
            actions_map[m.addAction("Add Import 3D Model (.ma/.mb/.fbx/.obj/.abc)")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Material Panel")] = ("MATERIAL PANEL", "MATERIAL", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            actions_map[m.addAction("Add Tweaker Panel")] = ("TWEAKER SETUP", "TWEAKER", offset)
            actions_map[m.addAction("Add LOD Loader Panel (build entire LODs)")] = ("LOD LOADER", "LOD_LOADER", offset)
            actions_map[m.addAction("Add Note Panel (free-text, not a build step)")] = ("NOTE", "NOTE", offset)
            actions_map[m.addAction("Add Import 3D Model + LOD Organize")] = ("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", offset)
            actions_map[m.addAction("Add Delete-by-Name Panel")] = ("DELETE", "DELETE_OBJ", offset)
            actions_map[m.addAction("Add Zero Out Panel")] = ("ZERO OUT", "ZERO_OUT", offset)
            actions_map[m.addAction("Add Parent Panel")] = ("PARENT", "PARENT_OBJ", offset)
            actions_map[m.addAction("Add Instance Panel")] = ("INSTANCE", "INSTANCE_OBJ", offset)
            actions_map[m.addAction("Add CC Import Panel (Character Creator FBX)")] = ("CC IMPORT", "CC_IMPORT", offset)

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        # Stage 22, request #4: the same Copy/Cut/Paste and Build Till Here
        # options every other panel type's "..." menu has - everything that
        # is actually meaningful for this panel type. Left out on purpose:
        # Load Cached Scene / Build FROM Here (this panel doesn't use
        # CacheMixin - caching one step doesn't compose meaningfully when
        # the "step" is itself a full multi-panel LOD build) and Replace
        # All Paths (this panel has no file-path field for that dialog to
        # touch).
        a_copy = menu.addAction(self.workspace.panel_copy_label(self, "📄 Copy"))
        a_cut = menu.addAction(self.workspace.panel_copy_label(self, "✂ Cut"))
        paste_above = menu.addAction(self.workspace.panel_paste_label("Above"))
        paste_below = menu.addAction(self.workspace.panel_paste_label("Below"))
        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)
        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here (run every step)")
        a_build_till_cached = menu.addAction("⚡ Build Till Here (resume from newest cache)")
        a_dup = menu.addAction("📋 Duplicate Panel")
        a_del = menu.addAction("❌ Delete Panel")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if not action: return

        if action == a_undo: self.workspace.undo_last_panel_delete()
        elif action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
        elif action == a_cut: self.cut_panel()
        elif action == paste_above: self.paste_panel(0)
        elif action == paste_below: self.paste_panel(1)
        elif action == a_build_till:
            print("[KRT] menu: Build Till Here (full) ->", self.title_edit.text())
            self.workspace.build_till_panel(self, resume_from_cache=False)
        elif action == a_build_till_cached:
            print("[KRT] menu: Build Till Here (cached) ->", self.title_edit.text())
            self.workspace.build_till_panel(self, resume_from_cache=True)
        elif action == a_dup: self.workspace.duplicate_panel(self)
        elif action == a_del: self._on_delete_clicked()

    def clipboard_data(self):
        """This panel as a clipboard dict (paths ABSOLUTE - see copy note)."""
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active,
                "bg_color": self.bg_color, "lod_names": self.checked_lod_names()}
        data["collapsed"] = self.is_collapsed()
        return data

    # Stage 53: copy/cut/paste go through the workspace, which knows the
    # multi-panel selection. clipboard_data() above only describes THIS panel.
    def copy_panel(self):
        self.workspace.copy_panels(self)

    def cut_panel(self):
        self.workspace.cut_panels(self)

    def paste_panel(self, offset):
        self.workspace.paste_panels_at(self, offset)

    def _on_delete_clicked(self):
        """Stop listening to the real LOD list before this panel is torn
        down, so a later add/remove/rename elsewhere never calls back into
        a deleted Qt widget."""
        if hasattr(self.workspace, "lod_list"):
            try:
                self.workspace.lod_list.itemChanged.disconnect(self._on_lod_manager_changed)
            except (RuntimeError, TypeError):
                pass
            try:
                self.workspace.lod_list.model().rowsRemoved.disconnect(self._on_lod_manager_changed)
            except (RuntimeError, TypeError):
                pass
        self.workspace.delete_panel(self)

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            # Manual click: run regardless of the active checkbox.
            self.execute(None, force=True)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def execute(self, progress_ui=None, force=False):
        """`force=True` runs even when the panel's checkbox is OFF.

        Stage 45: an inactive panel is skipped by the full build (that's what
        the checkbox is for), but its own RUN button should still work - it
        is how you test one step by hand without switching the step back on
        and forgetting to switch it off again. Only the build passes
        force=False."""
        if not self.is_active and not force: return True
        names = self.checked_lod_names()
        if not names:
            cmds.warning("No LODs added to this LOD Loader panel yet - use + Add LOD.")
            return True

        self.btn_run.setText("RUNNING...")
        QtWidgets.QApplication.processEvents()

        try:
            all_ok, msg = self.workspace.build_lod_sequence(names)
        except Exception:
            all_ok = False
            msg = traceback.format_exc()

        if all_ok:
            self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            self.btn_run.setText("🚀 RUN")
            self.last_error_msg = ""
            if hasattr(self, 'btn_reset_err'):
                self.btn_reset_err.setVisible(False)
        else:
            self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
            self.btn_run.setText("SHOW ERROR")
            self.last_error_msg = msg
            if hasattr(self, 'btn_reset_err'):
                self.btn_reset_err.setVisible(True)
        return all_ok
