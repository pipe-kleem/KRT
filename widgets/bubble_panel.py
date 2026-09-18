"""Auto-split from widgets.py."""
from ._shared import *
from .cache_mixin import CacheMixin
from .dialogs import ErrorDialog, GraphNodeOrderDialog
from .flow_layout import FlowLayout
from .style import type_accent, type_bg_tint, type_icon


class ModuleBubble(QtWidgets.QFrame):
    closed = QtCore.Signal(object)
    execute_req = QtCore.Signal(object)
    # Stage 30: "if there are lot of modules so user can hilight that
    # module in graph" - a small locate/target button, shown on hover next
    # to the close "x", that asks the panel to select & center this
    # bubble's actual graph node in the Graph Editor. Left-clicking the
    # bubble's own text still runs it instantly, unchanged - this is a
    # separate, additional affordance, not a replacement for that.
    locate_req = QtCore.Signal(object)

    def __init__(self, text, full_path, parent=None, is_active=True):
        super(ModuleBubble, self).__init__(parent)
        self.text = text
        self.full_path = full_path
        self.is_active = is_active
        self.setContentsMargins(5, 2, 5, 2)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(5)
        
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(self.is_active)
        self.checkbox.setToolTip("Toggle to include or exclude this module from the build")
        self.checkbox.toggled.connect(self.toggle_active)

        self.btn_text = QtWidgets.QPushButton(text)
        self.btn_text.setFlat(True)
        self.btn_text.setToolTip("Click to execute only this module instantly - click and drag to reorder it")
        self.btn_text.clicked.connect(lambda: self.execute_req.emit(self))
        self._drag_start_pos = None
        self.btn_text.installEventFilter(self)

        # Stage 30: only meaningful for a GRAPH:: bubble (a real graph node)
        # - a plain file-path bubble (Browse from File) has no graph node to
        # locate, so this stays hidden for those (see toggle_active/below).
        self.locate_btn = QtWidgets.QPushButton("◎")
        self.locate_btn.setFixedSize(16, 16)
        self.locate_btn.setFlat(True)
        self.locate_btn.setToolTip("Select & center this module in the Graph Editor")
        self.locate_btn.setStyleSheet("color: transparent; font-weight: bold; border: none;")
        self.locate_btn.clicked.connect(lambda: self.locate_req.emit(self))
        self.locate_btn.setVisible(full_path.startswith("GRAPH::"))

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setFlat(True)
        self.close_btn.setToolTip("Remove this module")
        self.close_btn.setStyleSheet("color: transparent; font-weight: bold; border: none;")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))

        layout.addWidget(self.checkbox)
        layout.addWidget(self.btn_text)
        layout.addWidget(self.locate_btn)
        layout.addWidget(self.close_btn)

        self.toggle_active(self.is_active)

    def toggle_active(self, state):
        self.is_active = state
        if state:
            self.setStyleSheet("QFrame { background-color: #3e3e42; border-radius: 10px; border: 1px solid #555; color: #ccc; } QFrame:hover { border: 1px solid #2bb5a8; }")
            self.btn_text.setStyleSheet("color: #ccc; font-weight: normal; border: none; background: transparent; text-align: left; padding: 0px;")
        else:
            self.setStyleSheet("QFrame { background-color: #5a2a2a; border-radius: 10px; border: 1px solid #f44336; color: #ccc; }")
            self.btn_text.setStyleSheet("color: #ff9999; font-weight: normal; border: none; background: transparent; text-align: left; padding: 0px;")

    def set_success(self):
        self.setStyleSheet("QFrame { background-color: #2e4a2e; border-radius: 10px; border: 1px solid #4CAF50; color: #ccc; }")
        self.btn_text.setStyleSheet("color: #aaddaa; font-weight: bold; border: none; background: transparent; text-align: left; padding: 0px;")
        
    def set_error(self):
        self.setStyleSheet("QFrame { background-color: #5a2a2a; border-radius: 10px; border: 1px solid #f44336; color: #ccc; }")
        self.btn_text.setStyleSheet("color: #ff9999; font-weight: bold; border: none; background: transparent; text-align: left; padding: 0px;")

    def reset_style(self):
        self.toggle_active(self.is_active)

    def enterEvent(self, event):
        self.close_btn.setStyleSheet("color: #2bb5a8; font-weight: bold; border: none; background: transparent;")
        if self.locate_btn.isVisible():
            self.locate_btn.setStyleSheet("color: #4ec9ff; font-weight: bold; border: none; background: transparent;")
        super(ModuleBubble, self).enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.setStyleSheet("color: transparent; border: none; background: transparent;")
        self.locate_btn.setStyleSheet("color: transparent; border: none; background: transparent;")
        super(ModuleBubble, self).leaveEvent(event)

    def eventFilter(self, obj, event):
        # btn_text would otherwise swallow every mouse press for its own
        # click handling, so a plain mousePressEvent/mouseMoveEvent override
        # on this QFrame would never fire when the drag starts on top of the
        # button (which is almost the whole bubble). Watching the button's
        # own events here instead lets a short click still execute the
        # module (btn_text.clicked, untouched) while a press-and-drag past
        # the drag threshold reorders the bubble instead - swallowing the
        # move/release so the button never also fires a click for it.
        if obj is self.btn_text:
            et = event.type()
            if et == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self._drag_start_pos = event.pos()
            elif et == QtCore.QEvent.MouseMove and self._drag_start_pos is not None \
                    and (event.buttons() & QtCore.Qt.LeftButton):
                if (event.pos() - self._drag_start_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    self._drag_start_pos = None
                    self.btn_text.setDown(False)
                    self._start_drag()
                    return True
            elif et in (QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.Leave):
                self._drag_start_pos = None
        return super(ModuleBubble, self).eventFilter(obj, event)

    def _find_panel(self):
        p = self.parentWidget()
        while p is not None and not isinstance(p, SortableBubblePanel):
            p = p.parentWidget()
        return p

    def _start_drag(self):
        panel = self._find_panel()
        if panel is None:
            return
        panel.dragging_bubble = self
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText("krt_bubble_drag")
        drag.setMimeData(mime)
        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QtCore.QPoint(10, 10))
        # The real bubble stays put and visible in its old spot for the
        # whole drag - it used to be hidden here so FlowLayout would close
        # its hole immediately, but that hide/show toggle raced with the
        # layout's own (partly deferred) relayout during rapid drag-move
        # events and could leave a bubble stuck invisible, or overlapping
        # the live drop-gap placeholder, if the drag ended mid-relayout.
        # BubbleDropArea._target_index already excludes this bubble from
        # its own position/index math regardless of visibility, so leaving
        # it visible costs nothing functionally - it just means the drag
        # now looks like "old spot stays, dashed gap shows where it'll
        # land", which is also the more familiar drag-and-drop convention.
        try:
            if IS_PYSIDE6:
                drag.exec(QtCore.Qt.MoveAction)
            else:
                drag.exec_(QtCore.Qt.MoveAction)
        finally:
            panel._clear_drop_gap()
            panel.dragging_bubble = None

class _BubbleDropGap(QtWidgets.QFrame):
    """A dashed-outline pill shown live while a ModuleBubble is being
    dragged over its panel's BubbleDropArea - tracks the mouse and marks
    exactly where the bubble will land if dropped right now. Purely a
    visual stand-in: it's inserted into the real bubble_layout (so the
    other bubbles actually make room / wrap around it, not just an overlay
    drawn on top), but it's never a real module and is always removed the
    instant the drag ends, drop or not."""
    def __init__(self, size):
        super(_BubbleDropGap, self).__init__()
        self._size = size
        self.setFixedSize(size)
        self.setStyleSheet(
            "QFrame { background-color: rgba(43, 181, 168, 45); "
            "border: 2px dashed #2bb5a8; border-radius: 10px; }")

    def sizeHint(self):
        return self._size


class BubbleDropArea(QtWidgets.QWidget):
    """The horizontal strip of ModuleBubble pills inside one SortableBubblePanel.
    Accepts a bubble being dragged (see ModuleBubble._start_drag) and
    reorders it within this same panel - same left/right positioning idea as
    DragDropContainer above, just scoped to one panel's own bubbles instead
    of panels within a whole LOD.

    Rows wrap (FlowLayout, Stage 35), so figuring out "where will this drop"
    from the mouse position needs both axes: _target_index() below groups
    the panel's current bubbles into rows by their y-center, picks the row
    closest to the cursor, then finds the slot within that row by x. The
    previous version only ever compared x - fine for a single row, but once
    bubbles wrapped onto a second/third row it had no idea which row the
    cursor was actually over, so dragging into a later row could silently
    reorder into the wrong one. dragMoveEvent uses the same index to move a
    live dashed-outline gap (_BubbleDropGap) into place as you drag, so
    there's always a visible answer to "where can i drop it" instead of
    finding out only after releasing the mouse."""
    def __init__(self, panel):
        super(BubbleDropArea, self).__init__()
        self.panel = panel
        self.setAcceptDrops(True)

    def _target_index(self, pos, bubble):
        """Which REAL bubble (the dragged bubble itself, and the live
        drop-gap placeholder if one is currently shown, are both excluded)
        the drop should land BEFORE - returned as that widget itself, not
        a numeric count. It used to be a numeric "real bubbles only" count,
        but that count doesn't map back onto a raw layout.insertWidget()
        position once the dragged bubble is still sitting somewhere in the
        raw layout in between (it's excluded from the COUNT but not from
        the actual list) - the numeric index would silently drift off by
        however many excluded items came before it, which is exactly what
        could make the gap (and, after drop, the bubble itself) land one
        slot off and visually overlap a neighbour. Returning the target
        widget instead sidesteps that: _show_drop_gap and dropEvent below
        both resolve it with a fresh layout.indexOf() right before they
        act, so they always agree with wherever things actually are RIGHT
        NOW, however many hidden/excluded items sit in between. None means
        "after every real bubble" (append at the end)."""
        layout = self.panel.bubble_layout
        gap = getattr(self.panel, "drop_gap", None)
        rows = []  # [[row_y_center, [widget, ...]], ...] - real bubbles only
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is None or w is bubble or w is gap or not w.isVisible():
                continue
            cy = w.geometry().center().y()
            row = next((r for r in rows if abs(r[0] - cy) <= w.height() / 2), None)
            if row is None:
                rows.append([cy, []])
                row = rows[-1]
            row[1].append(w)
        if not rows:
            return None
        for row in rows:
            row[1].sort(key=lambda w: w.geometry().x())

        rows_sorted = sorted(rows, key=lambda r: r[0])
        target_row = min(rows_sorted, key=lambda r: abs(r[0] - pos.y()))
        for w in target_row[1]:
            if pos.x() < w.geometry().center().x():
                return w
        # Past every bubble on the closest row - land right after the last
        # one on THAT row (i.e. right before the first bubble of the NEXT
        # row, if any), not at the very end of the whole panel - that
        # mix-up is exactly what an x-only compare used to cause when
        # dragging into anything but the first row.
        row_idx = rows_sorted.index(target_row)
        if row_idx + 1 < len(rows_sorted):
            return rows_sorted[row_idx + 1][1][0]
        return None

    def dragEnterEvent(self, event):
        if getattr(self.panel, 'dragging_bubble', None) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        bubble = getattr(self.panel, 'dragging_bubble', None)
        if bubble is None:
            return
        event.acceptProposedAction()
        pos = event.pos() if hasattr(event, "pos") else event.position().toPoint()
        target_widget = self._target_index(pos, bubble)
        self.panel._show_drop_gap(self, bubble.size(), target_widget)

    def dragLeaveEvent(self, event):
        self.panel._clear_drop_gap()
        super(BubbleDropArea, self).dragLeaveEvent(event)

    def dropEvent(self, event):
        bubble = getattr(self.panel, 'dragging_bubble', None)
        if bubble is None:
            event.ignore()
            return

        pos = event.pos() if hasattr(event, "pos") else event.position().toPoint()
        # target_widget is the real bubble to land BEFORE (or None for "at
        # the end") - see _target_index's docstring for why this is a
        # widget reference rather than a numeric count. Resolved into an
        # actual raw layout index via indexOf() below, AFTER bubble is
        # removed from the layout, so it's always correct regardless of
        # where bubble or the gap placeholder currently sit underneath it.
        target_widget = self._target_index(pos, bubble)
        self.panel._clear_drop_gap()

        layout = self.panel.bubble_layout
        if layout.indexOf(bubble) != -1:
            layout.removeWidget(bubble)
        target_index = layout.indexOf(target_widget) if target_widget is not None else layout.count()
        if target_index == -1:
            target_index = layout.count()
        layout.insertWidget(target_index, bubble)

        self.panel.dragging_bubble = None
        event.acceptProposedAction()


class SortableBubblePanel(CacheMixin, QtWidgets.QFrame):
    def __init__(self, title, workspace):
        super(SortableBubblePanel, self).__init__()
        self.p_type = "MODULE"
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint("MODULE")
        self.accent = type_accent("MODULE")
        self.uuid = uuid.uuid4().hex
        # Bubble currently being dragged for in-panel reordering (see
        # ModuleBubble._start_drag / BubbleDropArea) - None the rest of the time.
        self.dragging_bubble = None
        # Live dashed-outline placeholder (_BubbleDropGap) shown while
        # dragging_bubble is set, tracking where it would land right now -
        # see _show_drop_gap/_clear_drop_gap below. None the rest of the time.
        self.drop_gap = None
        self._drop_gap_target = None

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(self.toggle_active)

        self.icon_label = QtWidgets.QLabel(type_icon("MODULE"))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip("Module")

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox); header_layout.addWidget(self.icon_label); header_layout.addWidget(self.title_edit); header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        ctrl_layout.addWidget(self.btn_del)
        
        self.bubble_area = BubbleDropArea(self)
        # Stage 35: wraps onto additional rows instead of running module
        # bubbles off the edge of the panel once there are enough of them.
        self.bubble_layout = FlowLayout(self.bubble_area, margin=0, h_spacing=4, v_spacing=4)
        
        btn_add_mod = QtWidgets.QPushButton("+ Add Module")
        btn_add_mod.setFixedWidth(100)
        btn_add_mod.clicked.connect(self.add_module_bubble)
        
        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.clicked.connect(self.show_context_menu)

        self.btn_run = QtWidgets.QPushButton("LOAD")
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.on_btn_run_clicked)
        
        body_layout.addLayout(ctrl_layout)
        body_layout.addWidget(self.bubble_area)
        body_layout.addWidget(btn_add_mod)
        body_layout.addWidget(btn_dots)
        self._build_cache_controls(body_layout)
        body_layout.addWidget(self.btn_run)

        # Reset-error button (hidden until this panel is in the SHOW ERROR state).
        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        body_layout.addWidget(self.btn_reset_err)

        self._build_cache_tick(body_layout)

        # Stage 35: now that self.bubble_area can be several rows tall (the
        # FlowLayout wrap fix above), a plain QHBoxLayout centers every
        # OTHER widget in the row on the full height of that tall block -
        # "+ Add Module" / LOAD / etc. drift down into empty space to the
        # right instead of lining up the way they do on every other panel
        # type (where the row is always exactly one line tall). Pinning
        # everything except the bubble area itself to the top keeps them
        # level with the FIRST row of bubbles, same as before there was
        # ever more than one row.
        for i in range(body_layout.count()):
            item = body_layout.itemAt(i)
            target = item.widget() or item.layout()
            if target is not None and target is not self.bubble_area:
                body_layout.setAlignment(target, QtCore.Qt.AlignTop)

        main_layout.addLayout(body_layout)
        self.btn_del.clicked.connect(lambda: self.workspace.delete_panel(self))

    def reset_run_button(self):
        """Restore the LOAD button to normal after an error, without re-running."""
        self.btn_run.setText("LOAD")
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def update_style(self):
        accent = getattr(self, 'accent', '#2bb5a8')
        self.setStyleSheet(
            f"SortableBubblePanel {{ background: {self.bg_color}; border: 1px solid #333;"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" SortableBubblePanel:hover {{ border: 1px solid #555; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

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

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active, "bg_color": self.bg_color}
        if self.p_type == "MODULE":
            mods = [{"path": self.bubble_layout.itemAt(b).widget().full_path, "active": self.bubble_layout.itemAt(b).widget().is_active} for b in range(self.bubble_layout.count())]
            data["modules"] = mods
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

    def cut_panel(self):
        """Stage 22, request #1: Copy Panel, then delete this panel -
        delete_panel() itself pushes the removed panel onto the workspace's
        undo stack, so a Cut can still be undone same as a plain Delete."""
        self.copy_panel()
        self.workspace.delete_panel(self)

    def paste_panel(self, offset):
        data = getattr(self.workspace.main_window, 'clipboard_panel_data', None)
        if not data: return
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset

        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.workspace.add_module_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            for m in data.get("modules", []):
                pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
            if not is_act: pan.checkbox.setChecked(False)
        else:
            pan = self.workspace.add_panel(title, p_type, data.get("path", ""), index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            if not is_act: pan.checkbox.setChecked(False)
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                if data.get("asset_name"): pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT") and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))
            if p_type == "INSTANCE_OBJ" and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
                if data.get("func_call") and hasattr(pan, 'func_field'): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            self.execute(None)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #2bb5a8; font-weight: bold; color: white; font-size: 13px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(SortableBubblePanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {getattr(self, 'accent', '#2bb5a8')}; font-size: 13px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(SortableBubblePanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton): 
            return super(SortableBubblePanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(SortableBubblePanel, self).mouseMoveEvent(event)
            
        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance(): 
            return super(SortableBubblePanel, self).mouseMoveEvent(event)

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
        super(SortableBubblePanel, self).mouseMoveEvent(event)

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

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
        a_cut = menu.addAction("✂ Cut Panel")
        paste_above = menu.addAction("📋 Paste Panel (Above)")
        paste_below = menu.addAction("📋 Paste Panel (Below)")

        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)

        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here")
        a_dup = menu.addAction("📋 Duplicate Panel")

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
        elif action == a_build_till: self.workspace.build_till_panel(self)
        elif action == a_dup: self.workspace.duplicate_panel(self)

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)

    def _show_drop_gap(self, drop_area, size, target_widget):
        """Move the live drop-placeholder to sit immediately before
        `target_widget` (or at the very end if `target_widget` is None) -
        resolved via a fresh layout.indexOf() lookup every call, so it's
        always correct regardless of where the dragged bubble (still a
        real item in the layout, just excluded from _target_index's own
        count) or the gap itself currently happen to sit in the raw
        layout. A plain numeric index couldn't make that same guarantee -
        see _target_index's docstring for the off-by-one this replaced.
        This is a no-op when it's already exactly there, so hovering in
        place during a drag doesn't thrash the layout on every single
        mouse-move event."""
        if self.drop_gap is not None and self._drop_gap_target is target_widget:
            return
        layout = self.bubble_layout
        if self.drop_gap is None:
            self.drop_gap = _BubbleDropGap(size)
            self.drop_gap.setParent(drop_area)
            self.drop_gap.show()
        else:
            layout.removeWidget(self.drop_gap)
        index = layout.indexOf(target_widget) if target_widget is not None else layout.count()
        if index == -1:
            index = layout.count()
        layout.insertWidget(index, self.drop_gap)
        self._drop_gap_target = target_widget

    def _clear_drop_gap(self):
        """Remove the live drop-placeholder, if one is currently shown.
        Called on drop, on the drag leaving the panel without dropping, and
        as a safety net once ModuleBubble._start_drag's blocking drag.exec_()
        call returns no matter how it ended, so a cancelled/failed drag can
        never leave a stray placeholder bubble sitting in the layout (which
        would otherwise corrupt this panel's saved build order - every other
        bubble_layout reader assumes every item is a real ModuleBubble with
        a .full_path)."""
        if self.drop_gap is None:
            return
        self.bubble_layout.removeWidget(self.drop_gap)
        # removeWidget() (a QLayout base-class method, not FlowLayout's own
        # insertWidget) only posts a deferred relayout - force it now so the
        # remaining bubbles snap back to their real slots immediately
        # instead of momentarily overlapping the spot the gap just vacated.
        self.bubble_layout.activate()
        self.drop_gap.setParent(None)
        self.drop_gap.deleteLater()
        self.drop_gap = None
        self._drop_gap_target = None

    def add_module_bubble(self, pre_path=None, is_active=True):
        if not pre_path:
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            a_file = menu.addAction("📂 Browse from File")
            a_graph = menu.addAction("🔌 Add from Graph Editor")
            action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
            
            if action == a_file:
                kwargs = {'fm': 1, 'ff': "All Files (*.*);;Module Files (*.py *.sgt);;Python (*.py);;mGear Guide (*.sgt)"}
                if self.bubble_layout.count() > 0:
                    last_path = self.workspace.resolve_path(self.bubble_layout.itemAt(self.bubble_layout.count()-1).widget().full_path)
                    sd = os.path.dirname(last_path)
                    if os.path.exists(sd): kwargs['dir'] = sd

                res = cmds.fileDialog2(**kwargs)
                if not res: return
                pre_path = self.workspace.relativize_path(res[0])   # Stage 41
                
                bubble = ModuleBubble(os.path.basename(pre_path), pre_path, is_active=is_active)
                bubble.closed.connect(self.remove_bubble)
                bubble.execute_req.connect(self.execute_single_module)
                bubble.locate_req.connect(self.locate_bubble_in_graph)
                self.bubble_layout.addWidget(bubble)
                
            elif action == a_graph:
                from .graph import RigNode, CUSTOM_SCRIPT_MODULE_TYPE
                # Stage 30: "we don't need to call it in bubble module panel
                # as well just to run it. it is just a script which will
                # automatically trigger when some specific module will
                # build" - a Custom Script node has no guide of its own
                # (build_node_guide always returns None for it), so adding
                # one here would only ever show up as a build failure in
                # this panel's LOAD flow. It already runs on its own, via
                # its own trigger dependency (graph parent, or the "Trigger
                # after module" pick in its Custom Script settings) - never
                # by being included in a bubble panel's batch.
                all_nodes = [item for item in self.workspace.graph_widget.graph_view.scene.items()
                             if isinstance(item, RigNode) and item.module_type != CUSTOM_SCRIPT_MODULE_TYPE]
                if not all_nodes:
                    cmds.warning("No modules exist in the Graph Editor yet!")
                    return
                all_nodes.sort(key=lambda n: n.display_title.lower())

                # Modules already in THIS panel, in their current bubble
                # order - GraphNodeOrderDialog pre-numbers and locks these
                # ("last time's" order), so reopening this dialog just to
                # add one more module doesn't lose or reshuffle what's
                # already here; only genuinely new picks come back needing
                # a bubble below.
                existing_uuids = [b.full_path.split("::")[1]
                                   for i in range(self.bubble_layout.count())
                                   for b in [self.bubble_layout.itemAt(i).widget()]
                                   if b.full_path.startswith("GRAPH::")]

                # A popup to multi-select modules AND set the order they're
                # added in, instead of one at a time via sidebar selection.
                dialog = GraphNodeOrderDialog(all_nodes, existing_uuids, self.workspace.main_window)
                result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
                if result != QtWidgets.QDialog.Accepted:
                    return

                new_nodes = [n for n in dialog.order if n.uuid not in dialog.locked_uuids]
                for node in new_nodes:
                    v_path = f"GRAPH::{node.uuid}"
                    v_name = node.display_title
                    bubble = ModuleBubble(v_name, v_path, is_active=is_active)
                    bubble.closed.connect(self.remove_bubble)
                    bubble.execute_req.connect(self.execute_single_module)
                    bubble.locate_req.connect(self.locate_bubble_in_graph)
                    self.bubble_layout.addWidget(bubble)
            return
        else:
            name = os.path.basename(pre_path)
            if pre_path.startswith("GRAPH::"):
                node_uuid = pre_path.split("::")[1]
                n = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
                if n: name = n.display_title
                else: name = "Graph Node (Not Found)"
                
            bubble = ModuleBubble(name, pre_path, is_active=is_active)
            bubble.closed.connect(self.remove_bubble)
            bubble.execute_req.connect(self.execute_single_module)
            bubble.locate_req.connect(self.locate_bubble_in_graph)
            self.bubble_layout.addWidget(bubble)

    def remove_bubble(self, widget):
        self.bubble_layout.removeWidget(widget)
        widget.deleteLater()

    def locate_bubble_in_graph(self, bubble):
        """Stage 30: the bubble's own locate button ('select & highlight
        that module in graph', for when a panel has a lot of bubbles and
        it's hard to tell which graph node a given one actually is) -
        switches to the Graph Editor tab, selects just that node, and
        centers the view on it. Only meaningful for a GRAPH:: bubble; the
        button is hidden for a plain file-path bubble (see ModuleBubble),
        so this shouldn't normally be reached for one, but still guards
        against it just in case."""
        path = bubble.full_path
        if not path.startswith("GRAPH::"):
            cmds.warning("This module points at a file on disk, not a Graph Editor module.")
            return
        node_uuid = path.split("::")[1]
        node = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
        if not node:
            cmds.warning("That module no longer exists in the Graph Editor.")
            return

        self.workspace.switch_tab(2)  # Graph Editor page
        scene = self.workspace.graph_widget.graph_view.scene
        scene.clearSelection()
        node.setSelected(True)
        self.workspace.graph_widget.graph_view.centerOn(node)
        self.workspace.graph_widget.update_attr_editor()
        if hasattr(self.workspace, 'sync_graph_to_list'):
            self.workspace.sync_graph_to_list()

    def _build_bubble_guide(self, bubble):
        """Resolve a GRAPH:: bubble to its graph node and draw (or reuse) its
        guide. Does NOT build the rig or touch the scene otherwise - that's
        left to _finish_graph_batch so a panel's LOAD button can draw every
        guide first before building anything.
        Returns (ok, error_msg, node, root)."""
        path = bubble.full_path
        node_uuid = path.split("::")[1]
        node = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
        if not node:
            return False, f"Graph node with UUID {node_uuid} not found.", None, None

        # Stage 30: a Custom Script node has no guide of its own by design
        # (it runs off its own trigger dependency instead) - this bubble
        # can only be here from before that node type was excluded from
        # "Add from Graph Editor", so say so plainly instead of the generic
        # "could not build guide" a caller would otherwise see below.
        from .graph import CUSTOM_SCRIPT_MODULE_TYPE
        if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            return (False,
                    f"'{node.display_title}' is a Custom Script module - it has no guide to build "
                    "and doesn't belong in a Module Bubbles panel. Remove this bubble; the script "
                    "already runs on its own via its Trigger dependency.",
                    None, None)

        try:
            from mgear import shifter as mg_shifter
            import mgear.pymaya as pm
        except ImportError:
            return False, "mGear is not installed/loaded in this Maya session.", None, None

        # Draws the guide (if it isn't already built) and recursively builds
        # any parent components wired above it in the graph.
        root = self.workspace.graph_widget.build_node_guide(node, mg_shifter, pm)
        if not root:
            return False, f"Could not build guide for '{node.display_title}' - see Script Editor.", None, None

        return True, "", node, root

    def _finish_graph_batch(self, pending):
        """Second half of a GRAPH:: bubble LOAD: given [(bubble, node, root), ...]
        whose guides are ALL already drawn, build every one of them in a
        single Shifter build (not one build per bubble), run each node's
        "after Build Modules" custom script, then delete every guide this
        batch touched - including the shared top-level guide group(s), not
        just each component's own root, since the whole batch is done with
        them once the build succeeds.
        Returns (ok, [error_msg, ...])."""
        if not pending:
            return True, []

        try:
            from mgear import shifter as mg_shifter
        except ImportError:
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["mGear is not installed/loaded in this Maya session."]

        roots = [root for (_, _, root) in pending if root and cmds.objExists(root)]
        if not roots:
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["None of the drawn guides still exist in the scene - nothing to build."]

        try:
            cmds.select(roots, replace=True)
            mg_shifter.Rig().buildFromSelection()
        except Exception as e:
            err = traceback.format_exc()
            log_crash("Build Modules ({} node(s))".format(len(pending)), e)
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["[Build Modules]:\n" + err]

        for bubble, node, root in pending:
            self.workspace.graph_widget.run_node_custom_script(node, "modules")
            self.workspace.graph_widget.run_node_auto_scripts(node, "modules")
            bubble.set_success()

        self._delete_batch_guides(pending)
        return True, []

    def _delete_batch_guides(self, pending):
        """Delete every guide a just-built batch consumed, including the
        shared top-level guide group(s) they hang off of (mGear's "ismodel"
        marker), not just each component's own root. Safe to call once a
        build from `pending`'s roots has already succeeded."""
        guide_groups = set()
        for bubble, node, root in pending:
            if not root or not cmds.objExists(root):
                continue
            try:
                walker = root
                while walker:
                    if cmds.attributeQuery("ismodel", node=walker, exists=True):
                        guide_groups.add(walker)
                        break
                    parents = cmds.listRelatives(walker, parent=True, fullPath=True)
                    walker = parents[0] if parents else None
            except Exception:
                pass

        to_delete = guide_groups or {root for (_, _, root) in pending if root and cmds.objExists(root)}
        for grp in to_delete:
            try:
                if cmds.objExists(grp):
                    cmds.delete(grp)
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Could not auto-delete guide group '{grp}' - see Script Editor.")

        for bubble, node, root in pending:
            node.maya_guide_root = None
            node.update_display()

        gw = self.workspace.graph_widget
        if hasattr(gw, "_invalidate_attach_points_cache"):
            gw._invalidate_attach_points_cache()
        gw.update_attr_editor()
        if hasattr(gw, "guide_settings_panel"):
            gw.guide_settings_panel.refresh_from_scene()
        self.workspace.refresh_module_list()

    def execute_single_module(self, bubble):
        if not self.is_active or not bubble.is_active: return True, ""
        path = bubble.full_path
        success = False
        error_msg = ""
        QtWidgets.QApplication.processEvents()

        try:
            if path.startswith("GRAPH::"):
                ok, err, node, root = self._build_bubble_guide(bubble)
                if not ok:
                    bubble.set_error()
                    return False, err
                success, errs = self._finish_graph_batch([(bubble, node, root)])
                error_msg = "\n\n".join(errs)
                return success, error_msg

            elif path.endswith(".py"):
                success, error_msg = self.workspace.run_script(self.workspace.resolve_path(path))
            elif path.endswith(".sgt"):
                success, error_msg = self.workspace.run_mgear_sgt(self.workspace.resolve_path(path))
        except Exception as e:
            error_msg = traceback.format_exc()
            log_crash("Module bubble ({})".format(path), e)
            success = False

        if success: bubble.set_success()
        else: bubble.set_error()
        return success, error_msg

    def execute(self, progress_ui=None):
        if not self.is_active: return True
        all_success = True
        error_msgs = []

        self.btn_run.setText("RUNNING...")

        # Same fix graph.py's own "Build Guides" button already has: hold the
        # Graph Editor's live guide-placement watcher (the red/green dot)
        # while this panel is actually drawing guides below. Its QTimer
        # ticks every 1.5s and reads guide positions off the live scene - the
        # progress dialog's own QApplication.processEvents() calls further
        # down (needed to keep the UI responsive/cancellable during a long
        # batch) can let that timer fire mid-build, catching a guide that's
        # only half-drawn or not yet repositioned to its saved placement and
        # flashing the dot red for no real reason. Suspended here for the
        # whole batch, not just the "guides" sub-step, since GRAPH:: bubbles
        # draw guides interleaved with non-graph bubbles (scripts/.sgt) in
        # this same loop.
        graph_widget = getattr(self.workspace, "graph_widget", None)
        if graph_widget is not None:
            graph_widget._pos_watch_suspended = True

        local_ui = False
        if progress_ui is None:
            self.workspace.main_window.setEnabled(False)
            progress_ui = BuildProgressDialog(self.workspace, total_steps=self.bubble_layout.count())
            progress_ui.lbl_status.setText(f"Executing: {self.title_edit.text()}")
            progress_ui.show()
            local_ui = True

        QtWidgets.QApplication.processEvents()
        start_t = time.time()

        # GRAPH:: bubbles are batched: every guide in this panel is drawn
        # first (in bubble order, so a later bubble can attach onto an
        # earlier one's freshly-drawn guide), THEN every module is built in
        # one Shifter build, and only THEN are the guides deleted - see
        # _finish_graph_batch/_delete_batch_guides. Non-graph bubbles (a raw
        # .py script or a .sgt guide template added via "Browse from File")
        # aren't part of that and still just run in place, same as before.
        #
        # "Bubble order" for the GRAPH:: ones specifically means the same
        # hierarchy-stable order the Graph Editor's own "Build Guides (From
        # Sidebar Selection)"/"Build Modules (From Sidebar Selection)"
        # buttons use (_sorted_by_hierarchy: a node's graph parent, when
        # also present in this build, always comes before it) - not
        # whatever order the pills happen to be dragged/dropped into in
        # this panel, which is purely a display/organizing convenience (see
        # the bubble reorder/gap feature above). build_node_guide already
        # recurses upward to build a missing parent guide regardless, so
        # this reordering isn't required for correctness, but it makes this
        # panel's build behave identically to selecting the same modules in
        # the Graph Editor and building them there - which is the one thing
        # this panel is meant to add on top of (batching every guide draw,
        # then one combined rig build, then deleting the guide group -
        # everything else should match the Graph Editor's own flow exactly,
        # per spec). Non-GRAPH:: bubbles (.py scripts / .sgt templates) have
        # no graph hierarchy and keep their original panel-order slot.
        bubble_order = [self.bubble_layout.itemAt(i).widget() for i in range(self.bubble_layout.count())]
        if graph_widget is not None:
            graph_slots = [(pos, b) for pos, b in enumerate(bubble_order)
                            if b.full_path.startswith("GRAPH::")]
            node_of = {}
            for pos, b in graph_slots:
                n = graph_widget.get_node_by_uuid(b.full_path.split("::")[1])
                if n is not None:
                    node_of[b] = n
            if node_of:
                sorted_nodes = graph_widget._sorted_by_hierarchy(list(node_of.values()))
                bubble_of_node = {n: b for b, n in node_of.items()}
                sorted_bubbles = [bubble_of_node[n] for n in sorted_nodes]
                # Only the slots whose bubble actually resolved to a graph
                # node get reassigned, and in that same relative order they
                # already held (positions is built from graph_slots, which
                # is in original panel order) - so if raw slot 1 resolved
                # and raw slot 3 resolved, slot 1 gets whichever of the two
                # comes first in hierarchy order and slot 3 gets the other,
                # rather than shifting either one into a completely
                # different position in the panel. A bubble whose graph
                # node couldn't be resolved (a stale UUID) is simply never
                # in `positions` here, so its slot in bubble_order is left
                # untouched - it stays exactly where it was, and
                # _build_bubble_guide still runs on it below and reports
                # its own "not found" error, same as it always has.
                positions = [pos for pos, b in graph_slots if b in node_of]
                for pos, b in zip(positions, sorted_bubbles):
                    bubble_order[pos] = b

        pending_graph = []

        try:
            for i, bubble in enumerate(bubble_order):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    all_success = False
                    error_msgs.append("Cancelled by user.")
                    break

                if bubble.is_active:
                    if local_ui:
                        progress_ui.lbl_status.setText(f"Building guide: {bubble.text}")
                        progress_ui.progress_bar.setValue(i)

                    path = bubble.full_path
                    if path.startswith("GRAPH::"):
                        # _build_bubble_guide (and the mgear guide-drawing
                        # calls under it) previously had nothing catching an
                        # exception here - it would bubble all the way out
                        # of this panel's LOAD click uncaught. Wrapped so a
                        # guide-build failure becomes a normal SHOW ERROR
                        # like every other panel type, and gets durably
                        # logged for check_last_session_health() either way.
                        try:
                            ok, err, node, root = self._build_bubble_guide(bubble)
                        except Exception as e:
                            ok, err, node, root = False, traceback.format_exc(), None, None
                            log_crash("Build guide: {}".format(bubble.text), e)
                        if not ok:
                            all_success = False
                            error_msgs.append(f"[{bubble.text}]:\n{err}")
                            bubble.set_error()
                            break
                        pending_graph.append((bubble, node, root))
                    else:
                        success, err = self.execute_single_module(bubble)
                        if not success:
                            all_success = False
                            error_msgs.append(f"[{bubble.text}]:\n{err}")
                            break

            if all_success and pending_graph:
                if local_ui:
                    progress_ui.lbl_status.setText(f"Building {len(pending_graph)} module(s)...")
                QtWidgets.QApplication.processEvents()
                ok, errs = self._finish_graph_batch(pending_graph)
                if not ok:
                    all_success = False
                    error_msgs.extend(errs)
        finally:
            if graph_widget is not None:
                graph_widget._pos_watch_suspended = False
                # Settle the dot immediately off the now-finished (guides
                # deleted post-build, or left in place on a failure/cancel)
                # scene state, instead of waiting up to 1.5s for the next
                # timer tick.
                if hasattr(graph_widget, "_refresh_position_watch"):
                    graph_widget._refresh_position_watch()

            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)

            if local_ui:
                progress_ui.progress_bar.setValue(self.bubble_layout.count())
                progress_ui.close()
                self.workspace.main_window.setEnabled(True)

            if all_success and self.bubble_layout.count() > 0:
                self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
                self.btn_run.setText("LOAD")
                self.last_error_msg = ""
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(False)
                if local_ui:
                    self.cache_on_manual_run()
            else:
                self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
                self.btn_run.setText("SHOW ERROR")
                self.last_error_msg = "\n\n".join(error_msgs) if error_msgs else "Unknown execution failure."
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(True)

        return all_success
