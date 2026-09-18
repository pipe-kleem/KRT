"""Auto-split from graph.py."""
from ._shared import *
from .catalog import list_mgear_components, list_plebe_templates
from .dialogs import CustomScriptDialog, NodeSearchPopup, PlebeTemplateDialog
from .items import RigNode, RigWire, bezier_path


class NodeGraphView(QtWidgets.QGraphicsView):
    def __init__(self, workspace):
        super(NodeGraphView, self).__init__()
        self.workspace = workspace
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.setSceneRect(0, 0, 4000, 4000)

        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#1e1e1e")))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)

        # Without an explicit resize anchor, QGraphicsView defaults to
        # keeping the scene's top-left corner fixed and just reveals/hides
        # more of the bottom-right as the widget resizes - which reads as
        # the graph "jumping" or getting clipped whenever the KRT window is
        # resized while the graph tab is open. Anchoring to the view's
        # center instead keeps whatever you were looking at roughly in
        # place across a resize.
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        # Connection-drag state (Ctrl+drag from one RigNode onto another
        # wires them as parent -> child in the mGear guide hierarchy).
        self._connect_source = None
        self._temp_wire_line = None
        # True while a Ctrl+drag on empty canvas is panning the view.
        self._pan_active = False

        if IS_PYSIDE6:
            self.shortcut_tab = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)
        else:
            self.shortcut_tab = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)

        self.shortcut_tab.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.shortcut_tab.activated.connect(self.show_module_menu)

        self.scene.selectionChanged.connect(self.workspace.sync_graph_to_list)

    def enterEvent(self, event):
        self.setFocus()
        # Cheap safety net: whenever the user's mouse enters the graph, make
        # sure the Guide Settings tab reflects whatever is actually in the
        # scene right now, rather than relying only on an explicit tab click.
        gw = getattr(self.workspace, 'graph_widget', None)
        if gw is not None and hasattr(gw, 'guide_settings_panel'):
            gw.guide_settings_panel.refresh_from_scene()
        super(NodeGraphView, self).enterEvent(event)

    def drawBackground(self, painter, rect):
        """A grid is always shown (not just once zoomed in) so it reads as
        an obvious visual reference for whether Ctrl+Scroll zoom is actually
        doing anything, at any zoom level."""
        super(NodeGraphView, self).drawBackground(painter, rect)
        grid_size = 25
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)

        thin_lines, thick_lines = [], []
        x = left
        while x < rect.right():
            line = QtCore.QLineF(x, rect.top(), x, rect.bottom())
            (thick_lines if x % (grid_size * 4) == 0 else thin_lines).append(line)
            x += grid_size
        y = top
        while y < rect.bottom():
            line = QtCore.QLineF(rect.left(), y, rect.right(), y)
            (thick_lines if y % (grid_size * 4) == 0 else thin_lines).append(line)
            y += grid_size

        painter.setPen(QtGui.QPen(QtGui.QColor("#2a2a2c"), 0))
        painter.drawLines(thin_lines)
        painter.setPen(QtGui.QPen(QtGui.QColor("#333336"), 0))
        painter.drawLines(thick_lines)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            angle = event.angleDelta().y()
            if angle == 0:
                return
            factor = 1.15 if angle > 0 else 1.0 / 1.15
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
            self.scale(factor, factor)
            event.accept()
            return
        super(NodeGraphView, self).wheelEvent(event)

    def keyPressEvent(self, event):
        # Ctrl+Z / Ctrl+Shift+Z (and the common Ctrl+Y redo alternative) -
        # undo/redo for the graph editor itself (nodes, wires, positions,
        # every Node-tab field). Only active while the graph view has
        # keyboard focus, so it doesn't fight a text field's own Ctrl+Z
        # while editing there (see ModuleGraphWidget.undo/redo).
        if event.key() == QtCore.Qt.Key_Z and (event.modifiers() & QtCore.Qt.ControlModifier):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                self.workspace.graph_widget.redo()
            else:
                self.workspace.graph_widget.undo()
            return
        if event.key() == QtCore.Qt.Key_Y and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.workspace.graph_widget.redo()
            return

        # Stage 27, request #2: standard copy/cut/paste keyboard shortcuts
        # for graph nodes, alongside the same actions on the right-click menu
        # (see contextMenuEvent). Only active while the graph view itself has
        # keyboard focus, same as Ctrl+Z above, so it doesn't fight a Node
        # tab text field's own Ctrl+C/V.
        if event.key() == QtCore.Qt.Key_C and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.copy_selected_nodes()
            return
        if event.key() == QtCore.Qt.Key_X and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.cut_selected_nodes()
            return
        if event.key() == QtCore.Qt.Key_V and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.paste_nodes_from_clipboard()
            return

        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            selected = self.scene.selectedItems()
            if selected:
                self.workspace.graph_widget._push_undo_snapshot()
            for item in [i for i in selected if isinstance(i, RigNode)]:
                for wire in item.wires[:]:
                    self._remove_wire(wire)
                self.scene.removeItem(item)
            for wire in [i for i in selected if isinstance(i, RigWire)]:
                self._remove_wire(wire)
            self.workspace.refresh_module_list()
            self.workspace.graph_widget.update_attr_editor()

        elif event.key() == QtCore.Qt.Key_F:
            items = self.scene.selectedItems()
            if not items:
                items = [i for i in self.scene.items() if isinstance(i, RigNode)]
            if items:
                rect = items[0].sceneBoundingRect()
                for item in items[1:]:
                    rect = rect.united(item.sceneBoundingRect())
                rect.adjust(-100, -100, 100, 100)
                self.fitInView(rect, QtCore.Qt.KeepAspectRatio)
        else:
            super(NodeGraphView, self).keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            item = self.itemAt(event.pos())
            if not item:
                self.show_module_menu()
        super(NodeGraphView, self).mouseDoubleClickEvent(event)

    def _rig_node_at(self, view_pos):
        """itemAt() returns the topmost item under the cursor, which for a
        RigNode is usually its child QGraphicsTextItem label rather than the
        node's rect itself. Walk up to the owning RigNode."""
        item = self.itemAt(view_pos)
        while item is not None and not isinstance(item, RigNode):
            item = item.parentItem()
        return item

    def _port_at(self, view_pos, tolerance=11):
        """Return (RigNode, 'input'|'output') if `view_pos` (view/widget
        coordinates, e.g. straight from a mouse event) lands on or near one
        of that node's connector pins, else None. Checked before falling
        back to whole-node dragging so a press on a pin always starts a
        wire rather than moving the node."""
        best, best_dist = None, tolerance
        for item in self.scene.items():
            if not isinstance(item, RigNode):
                continue
            for local_pos, kind in ((item.output_port_pos(), "output"), (item.input_port_pos(), "input")):
                port_view_pos = self.mapFromScene(item.mapToScene(local_pos))
                dist = QtCore.QLineF(QtCore.QPointF(port_view_pos), QtCore.QPointF(view_pos)).length()
                if dist < best_dist:
                    best_dist = dist
                    best = (item, kind)
        return best

    def _remove_wire(self, wire):
        if wire.scene() is not None:
            self.scene.removeItem(wire)
        if wire in wire.source.wires: wire.source.wires.remove(wire)
        if wire in wire.dest.wires: wire.dest.wires.remove(wire)
        wire.dest.parent_local_target = None
        wire.dest.update_display()

    def _start_wire_drag(self, node):
        start = node.sceneBoundingRect()
        self._temp_wire_line = QtWidgets.QGraphicsPathItem(bezier_path(start, start))
        self._temp_wire_line.setPen(QtGui.QPen(QtGui.QColor("#ffcc66"), 2, QtCore.Qt.DashLine))
        self._temp_wire_line.setZValue(10)
        self.scene.addItem(self._temp_wire_line)

    # -- Node -> node wiring: drag from a node's connector pin (like any
    # standard node editor), or Ctrl+drag from anywhere on the node body --
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            port_hit = self._port_at(event.pos())
            # Only the output (right-side) pin starts a new connection drag -
            # matches the usual node-editor convention (drag OUT of an
            # output, drop ON an input). The input pin is left alone here so
            # clicking near it still just selects/moves the node normally;
            # detaching its existing wire is done via right-click-on-the-wire
            # or Delete on the selected wire instead.
            if port_hit is not None and port_hit[1] == "output":
                self._connect_source = port_hit[0]
                self._start_wire_drag(port_hit[0])
                return
            if event.modifiers() & QtCore.Qt.ControlModifier:
                item = self._rig_node_at(event.pos())
                if isinstance(item, RigNode):
                    self._connect_source = item
                    self._start_wire_drag(item)
                    return
                # Ctrl+drag starting on empty canvas pans the graph around
                # instead of rubber-band selecting - hand off to Qt's own
                # hand-drag panning for the rest of this drag.
                self._pan_active = True
                self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                super(NodeGraphView, self).mousePressEvent(event)
                return
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                # QGraphicsScene only natively toggles selection on Ctrl+click
                # (used above for wire-dragging here), and has no built-in
                # notion of Shift+click at all - so Shift+click-to-multi-select
                # a node has to be implemented by hand.
                item = self._rig_node_at(event.pos())
                if isinstance(item, RigNode):
                    item.setSelected(not item.isSelected())
                    return
        super(NodeGraphView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._connect_source is not None and self._temp_wire_line is not None:
            src_rect = self._connect_source.sceneBoundingRect()
            end_pos = self.mapToScene(event.pos())
            end_rect = QtCore.QRectF(end_pos, end_pos)
            self._temp_wire_line.setPath(bezier_path(src_rect, end_rect))
            return
        super(NodeGraphView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_active and event.button() == QtCore.Qt.LeftButton:
            super(NodeGraphView, self).mouseReleaseEvent(event)
            self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
            self._pan_active = False
            return
        if self._connect_source is not None:
            source = self._connect_source
            if self._temp_wire_line is not None:
                self.scene.removeItem(self._temp_wire_line)
                self._temp_wire_line = None
            self._connect_source = None

            port_hit = self._port_at(event.pos())
            target = port_hit[0] if port_hit is not None else self._rig_node_at(event.pos())
            if isinstance(target, RigNode) and target is not source:
                self.workspace.graph_widget._push_undo_snapshot()
                # Only one parent per node - drop any existing incoming wire.
                for wire in target.wires[:]:
                    if wire.dest is target:
                        self._remove_wire(wire)
                new_wire = RigWire(source, target)
                self.scene.addItem(new_wire)
                target.parent_local_target = None
                gw = self.workspace.graph_widget
                self._offer_attach_point(gw, source, target)
                new_wire.refresh_tooltip()
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            return
        super(NodeGraphView, self).mouseReleaseEvent(event)

    def _offer_attach_point(self, gw, parent_node, child_node, force=False):
        """If `parent_node` already has a built guide with more than one
        possible attachment locator (e.g. a spine's chest/neck/hip
        locators), ask which one `child_node` should parent under instead
        of always the whole guide root - the same choice you'd get dragging
        a component onto a specific locator in Shifter's own Guide Manager
        outliner. Silently keeps "whole guide root" when there's nothing
        (yet) to choose between - unless `force` is set (Stage 28: the
        wire right-click menu's "Change Attach Point..." always shows the
        menu, even with 0-1 real locators, since asking for it directly is
        a deliberate action, not an incidental side effect of a drag)."""
        points = gw._list_attach_points(parent_node)
        if len(points) < 2 and not force:
            return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        menu.addSection(f"Attach under which part of '{parent_node.display_title}'?")
        a_root = menu.addAction("(Whole Guide Root)")
        menu.addSeparator()
        actions = {}
        for label, long_name in points:
            actions[menu.addAction(label)] = long_name
        chosen = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if chosen is not None and chosen is not a_root:
            child_node.parent_local_target = actions.get(chosen)
        child_node.update_display()

    def contextMenuEvent(self, event):
        node = self._rig_node_at(event.pos())
        gw = self.workspace.graph_widget

        if isinstance(node, RigNode):
            # Stage 27, request #2: right-clicking a node that's already
            # part of a multi-selection acts on the whole selection (Copy/
            # Cut/Duplicate/Delete all of them); right-clicking an
            # unselected node selects just that one first - same convention
            # most node editors use.
            selected_nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
            if node not in selected_nodes:
                self.scene.clearSelection()
                node.setSelected(True)
                selected_nodes = [node]

            self._last_cursor_scene_pos = self.mapToScene(event.pos())
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            count = len(selected_nodes)
            suffix = f" ({count})" if count > 1 else ""
            a_copy = menu.addAction(f"📄 Copy Module{suffix}")
            a_cut = menu.addAction(f"✂ Cut Module{suffix}")
            a_dup = menu.addAction(f"🧬 Duplicate Module{suffix}")
            has_clip = bool(getattr(self.workspace.main_window, 'clipboard_node_data', None))
            a_paste = menu.addAction("📋 Paste Module(s)")
            a_paste.setEnabled(has_clip)
            a_delete = menu.addAction(f"🗑 Delete Module{suffix}")

            a_import = a_fix = a_constrain = a_skin = None
            if count == 1 and node.module_type == PLEBE_MODULE_TYPE:
                menu.addSeparator()
                a_import = menu.addAction("📥 Import Character FBX...")
                a_fix = menu.addAction("🔧 Fix FBX Naming")
                menu.addSeparator()
                a_constrain = menu.addAction("🔗 Constrain Character to Rig")
                a_skin = menu.addAction("🎨 Skin Character to Rig")

            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_copy:
                self.copy_selected_nodes()
            elif action == a_cut:
                self.cut_selected_nodes()
            elif action == a_dup:
                self.duplicate_selected_nodes()
            elif action == a_paste:
                self.paste_nodes_from_clipboard()
            elif action == a_delete:
                self._delete_nodes(selected_nodes)
            elif action == a_import:
                gw.plebe_import_fbx(node)
            elif action == a_fix:
                gw.plebe_fix_fbx_naming(node)
            elif action == a_constrain:
                gw.plebe_constrain_to_rig(node)
            elif action == a_skin:
                gw.plebe_skin_to_rig(node)
            return

        wire = self.itemAt(event.pos())
        if isinstance(wire, RigWire):
            gw = self.workspace.graph_widget
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            current = wire.dest.parent_local_target
            current_label = current.split("|")[-1] if current else "(Whole Guide Root)"
            a_attach = menu.addAction(f"🔗 Change Attach Point... (currently: {current_label})")
            menu.addSeparator()
            a_disconnect = menu.addAction("✂ Disconnect")
            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_disconnect:
                gw._push_undo_snapshot()
                self._remove_wire(wire)
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            elif action == a_attach:
                # Stage 28, request #2: an already-connected wire can have
                # its attach point changed directly, right-click here,
                # instead of needing to disconnect and redrag it just to
                # reach the same choice _offer_attach_point() already gives
                # at drop time - same underlying "all the options where else
                # this can parent" list, reached from one more place.
                gw._push_undo_snapshot()
                self._offer_attach_point(gw, wire.source, wire.dest, force=True)
                wire.refresh_tooltip()
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            return

        # Empty canvas: the only thing worth offering is Paste, if there's
        # something on the node clipboard to paste.
        if getattr(self.workspace.main_window, 'clipboard_node_data', None):
            self._last_cursor_scene_pos = self.mapToScene(event.pos())
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            a_paste = menu.addAction("📋 Paste Module(s)")
            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_paste:
                self.paste_nodes_from_clipboard()
            return

        super(NodeGraphView, self).contextMenuEvent(event)

    # -- Stage 27, request #2: copy/cut/paste/duplicate for graph nodes --
    def _copy_nodes_to_clipboard(self, nodes):
        """Serialize `nodes` (via the same serialize_node every other
        persistence path uses) plus every wire that connects two of THEM to
        each other, onto a clipboard shared with the rest of KRT
        (main_window.clipboard_node_data - a sibling of the panel clipboard
        Stage 22 added for the Rig Build Workspace). A wire to something
        OUTSIDE the copied set is deliberately dropped - a pasted copy
        starts with no external parent, same as any freshly created node."""
        gw = self.workspace.graph_widget
        node_set = set(nodes)
        node_dicts = [gw.serialize_node(n) for n in nodes]
        wire_pairs = [(w.source.uuid, w.dest.uuid) for n in nodes for w in n.wires
                      if w.dest is n and w.source in node_set]
        self.workspace.main_window.clipboard_node_data = {"nodes": node_dicts, "wires": wire_pairs}

    def copy_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        cmds.warning(f"Copied {len(nodes)} module(s) to clipboard.")

    def cut_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        self._delete_nodes(nodes)
        cmds.warning(f"Cut {len(nodes)} module(s) to clipboard.")

    def duplicate_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        self.paste_nodes_from_clipboard()

    def _delete_nodes(self, nodes):
        if not nodes:
            return
        self.workspace.graph_widget._push_undo_snapshot()
        for item in nodes:
            for wire in item.wires[:]:
                self._remove_wire(wire)
            self.scene.removeItem(item)
        self.workspace.refresh_module_list()
        self.workspace.graph_widget.update_attr_editor()

    def paste_nodes_from_clipboard(self):
        """Pastes at the current mouse position over the graph canvas -
        works identically whether triggered from the right-click menu (the
        cursor is already where the click happened) or Ctrl+V (wherever the
        mouse happens to be hovering)."""
        data = getattr(self.workspace.main_window, 'clipboard_node_data', None)
        if not data or not data.get("nodes"):
            return
        gw = self.workspace.graph_widget
        node_dicts = data["nodes"]

        min_x = min(nd["x"] for nd in node_dicts)
        min_y = min(nd["y"] for nd in node_dicts)
        anchor = self.mapToScene(self.mapFromGlobal(QtGui.QCursor.pos()))

        gw._push_undo_snapshot()
        self.scene.clearSelection()

        uuid_map = {}
        new_nodes = []
        for nd in node_dicts:
            nd2 = dict(nd)
            nd2["uuid"] = str(uuid.uuid4())  # a paste is always a brand-new node, never a duplicate id
            nd2["x"] = anchor.x() + (nd["x"] - min_x)
            nd2["y"] = anchor.y() + (nd["y"] - min_y)
            new_node = gw.deserialize_node(nd2)
            uuid_map[nd["uuid"]] = new_node
            self.scene.addItem(new_node)
            new_nodes.append(new_node)

        for src_uuid, dst_uuid in data.get("wires", []):
            src, dst = uuid_map.get(src_uuid), uuid_map.get(dst_uuid)
            if src and dst:
                self.scene.addItem(RigWire(src, dst))

        for n in new_nodes:
            n.setSelected(True)
        self.workspace.refresh_module_list()
        gw.update_attr_editor()
        cmds.warning(f"Pasted {len(new_nodes)} module(s).")

    def show_module_menu(self):
        all_modules = [PLEBE_SEARCH_LABEL, CUSTOM_SGT_SEARCH_LABEL, CUSTOM_SCRIPT_SEARCH_LABEL] + list_mgear_components()

        if len(all_modules) == 3:
            cmds.warning("No mGear Shifter components found. Is mGear installed/loaded?")
            return

        # Recently-added modules float to the top of the unfiltered list, so
        # the components this user actually reaches for aren't buried in a
        # long alphabetical catalog. Typing to search still searches
        # everything regardless of recency (see NodeSearchPopup.filter_list).
        recent_names = self.workspace.session_manager.get_recent_modules()
        recents = [m for m in recent_names if m in all_modules]
        rest = [m for m in all_modules if m not in recents]

        modules, header_labels = [], set()
        if recents:
            header_labels = {"── Recent ──", "── All Modules ──"}
            modules.append("── Recent ──")
            modules.extend(recents)
            modules.append("── All Modules ──")
        modules.extend(rest)

        cursor_pos = QtGui.QCursor.pos()
        view_pos = self.mapFromGlobal(cursor_pos)
        self._last_cursor_scene_pos = self.mapToScene(view_pos)

        self.search_popup = NodeSearchPopup(modules, self.create_node, header_labels=header_labels)
        self.search_popup.move(cursor_pos)
        self.search_popup.show()

    def create_node(self, module_name):
        if module_name == PLEBE_SEARCH_LABEL:
            self.create_plebe_node()
            return
        if module_name == CUSTOM_SGT_SEARCH_LABEL:
            self.create_custom_sgt_node()
            return
        if module_name == CUSTOM_SCRIPT_SEARCH_LABEL:
            self.create_custom_script_node()
            return

        result = cmds.confirmDialog(
            title='Select Module Side',
            message=f'Which side do you want to build {module_name} for?',
            button=['Left (L_)', 'Right (R_)', 'Center (C_)', 'Cancel'],
            defaultButton='Left (L_)',
            cancelButton='Cancel',
            dismissString='Cancel'
        )

        if result == 'Cancel': return

        side = "L" if "Left" in result else "R" if "Right" in result else "C"

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 60, pos.y() - 20, module_type=module_name, side=side)
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(module_name)
        self.workspace.refresh_module_list()

    def create_plebe_node(self):
        templates = list_plebe_templates()
        if not templates:
            cmds.warning("No mGear Plebe character templates found (mgear/shifter/plebes_templates).")
            return

        dialog = PlebeTemplateDialog(templates, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result != QtWidgets.QDialog.Accepted or not dialog.selected_path:
            return

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=PLEBE_MODULE_TYPE, side="C",
                           custom_name=f"Plebe: {dialog.selected_name}")
        new_node.plebe_template_path = dialog.selected_path
        new_node.plebe_template_name = dialog.selected_name
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(PLEBE_SEARCH_LABEL)
        self.workspace.refresh_module_list()

    def create_custom_sgt_node(self):
        """A node that imports a standalone .sgt guide template someone
        saved themselves - e.g. a stock component they hand-tweaked and
        re-exported from mGear's own Guide Manager - instead of drawing one
        of the catalog components. Same 'graft onto a parent' behavior as
        any other component once placed (see build_node_guide /
        _build_custom_sgt_guide)."""
        res = cmds.fileDialog2(fm=1, ff="mGear Guide Template (*.sgt);;All Files (*.*)",
                               caption="Choose a Custom Module .sgt File")
        if not res:
            return
        sgt_path = res[0]
        default_name = os.path.splitext(os.path.basename(sgt_path))[0]

        result = cmds.confirmDialog(
            title='Select Module Side',
            message=f'Which side do you want to build {default_name} for?',
            button=['Left (L_)', 'Right (R_)', 'Center (C_)', 'Cancel'],
            defaultButton='Left (L_)',
            cancelButton='Cancel',
            dismissString='Cancel'
        )
        if result == 'Cancel': return
        side = "L" if "Left" in result else "R" if "Right" in result else "C"

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=CUSTOM_SGT_MODULE_TYPE, side=side,
                           custom_name=default_name)
        new_node.custom_sgt_path = sgt_path
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(CUSTOM_SGT_SEARCH_LABEL)
        self.workspace.refresh_module_list()

    def create_custom_script_node(self):
        """Stage 26: 'like custom module there should be a custom script
        module also where i dont need to load any module, i just wants to
        write custom script there' - no file picker, no side picker, no
        guide of any kind. Just a node whose entire purpose is the script
        attached to it (see CUSTOM_SCRIPT_MODULE_TYPE), so the script editor
        opens immediately after it's dropped - writing that script IS the
        only thing left to do with this node."""
        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=CUSTOM_SCRIPT_MODULE_TYPE, side="C",
                           custom_name="Custom Script")
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(CUSTOM_SCRIPT_SEARCH_LABEL)
        self.workspace.refresh_module_list()

        all_nodes = [i for i in self.scene.items() if isinstance(i, RigNode) and i is not new_node]
        dialog = CustomScriptDialog(new_node, self.workspace.main_window, all_nodes=all_nodes)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            dialog.apply_to_node()
        self.workspace.graph_widget.update_attr_editor()
