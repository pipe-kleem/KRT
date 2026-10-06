import maya.cmds as cmds
import os
import uuid
import json
import importlib.util
import sys
import traceback
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6

class RigWire(QtWidgets.QGraphicsLineItem):
    def __init__(self, source_node, dest_node):
        super(RigWire, self).__init__()
        self.source = source_node; self.dest = dest_node
        self.source.add_wire(self); self.dest.add_wire(self)
        self.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 3)); self.setZValue(-1)
        self.update_position()
    def update_position(self):
        self.setLine(QtCore.QLineF(self.source.sceneBoundingRect().center(), self.dest.sceneBoundingRect().center()))

class RigNode(QtWidgets.QGraphicsRectItem):
    def __init__(self, x, y, module_type="", side="L", custom_name=""):
        super(RigNode, self).__init__(0, 0, 140, 40)
        self.setPos(x, y)
        
        self.uuid = str(uuid.uuid4())
        self.module_type = module_type
        self.custom_name = custom_name or module_type
        self.side = side
        
        self.setBrush(QtGui.QBrush(QtGui.QColor("#3e3e42")))
        self.setPen(QtGui.QPen(QtGui.QColor("#555555"), 2))
        
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | 
                      QtWidgets.QGraphicsItem.ItemSendsGeometryChanges | 
                      QtWidgets.QGraphicsItem.ItemIsSelectable)
                      
        self.text = QtWidgets.QGraphicsTextItem("", self)
        self.text.setDefaultTextColor(QtGui.QColor("#cccccc"))
        self.text.setPos(10, 8)
        self.wires = []
        
        self.update_display()
        
    def update_display(self):
        self.display_title = f"{self.custom_name} [{self.side}]"
        self.text.setPlainText(self.display_title)
        
    def add_wire(self, wire): self.wires.append(wire)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            for wire in self.wires: wire.update_position()
        return super(RigNode, self).itemChange(change, value)
        
    def paint(self, painter, option, widget):
        if self.isSelected():
            painter.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 2))
        else:
            painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(self.rect())

class NodeSearchPopup(QtWidgets.QWidget):
    def __init__(self, modules_list, callback, parent=None):
        super(NodeSearchPopup, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        
        self.setStyleSheet("""
            QWidget { background-color: #252526; color: #cccccc; border: 1px solid #2bb5a8; border-radius: 3px; }
            QLineEdit { background-color: #1e1e1e; border: 1px solid #555; padding: 5px; font-family: 'Consolas'; color: white;}
            QListWidget { border: none; outline: none; font-size: 13px; padding: 2px;}
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #2bb5a8; color: white; border-radius: 2px;}
            QListWidget::item:hover { background-color: #3e3e42; }
        """)
        
        self.setFixedSize(220, 280)
        self.callback = callback
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("Search modules...")
        layout.addWidget(self.search_bar)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)

        for mod in modules_list:
            self.list_widget.addItem(mod)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self.search_bar.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_selected)
        self.search_bar.returnPressed.connect(self.on_enter_pressed)
        
        self.search_bar.installEventFilter(self)
        self.search_bar.setFocus()

    def filter_list(self, text):
        search_text = text.lower()
        first_visible = -1
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            match = search_text in item.text().lower()
            item.setHidden(not match)
            if match and first_visible == -1:
                first_visible = i
        
        if first_visible != -1:
            self.list_widget.setCurrentRow(first_visible)

    def on_item_selected(self, item):
        self.callback(item.text())
        self.close()

    def on_enter_pressed(self):
        item = self.list_widget.currentItem()
        if item and not item.isHidden():
            self.callback(item.text())
            self.close()

    def eventFilter(self, obj, event):
        if obj == self.search_bar and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Up:
                self.move_selection(-1)
                return True
            elif event.key() == QtCore.Qt.Key_Down:
                self.move_selection(1)
                return True
        return super(NodeSearchPopup, self).eventFilter(obj, event)

    def move_selection(self, step):
        row = self.list_widget.currentRow()
        for _ in range(self.list_widget.count()):
            row += step
            if 0 <= row < self.list_widget.count():
                if not self.list_widget.item(row).isHidden():
                    self.list_widget.setCurrentRow(row)
                    break
            else:
                break

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
        
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.modules_path = r"P:\pipeline_database\Maya\Scripts\Kleem_Rigging_Tool\modules"

        if IS_PYSIDE6:
            self.shortcut_tab = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)
        else:
            self.shortcut_tab = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)
            
        self.shortcut_tab.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.shortcut_tab.activated.connect(self.show_module_menu)
        
        self.scene.selectionChanged.connect(self.workspace.sync_graph_to_list)

    def enterEvent(self, event):
        self.setFocus()
        super(NodeGraphView, self).enterEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            for item in self.scene.selectedItems():
                if isinstance(item, RigNode):
                    for wire in item.wires[:]:
                        self.scene.removeItem(wire)
                        if wire.source != item and wire in wire.source.wires:
                            wire.source.wires.remove(wire)
                        if wire.dest != item and wire in wire.dest.wires:
                            wire.dest.wires.remove(wire)
                    self.scene.removeItem(item)
            self.workspace.refresh_module_list()
        
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

    def show_module_menu(self):
        modules = []
        if os.path.exists(self.modules_path):
            for f in os.listdir(self.modules_path):
                if f.endswith(".py") and not f.startswith("__"):
                    modules.append(os.path.splitext(f)[0])

        if not modules:
            cmds.warning("No Python modules found in the specified path.")
            return

        cursor_pos = QtGui.QCursor.pos()
        view_pos = self.mapFromGlobal(cursor_pos)
        self._last_cursor_scene_pos = self.mapToScene(view_pos)

        self.search_popup = NodeSearchPopup(modules, self.create_node)
        self.search_popup.move(cursor_pos)
        self.search_popup.show()

    def create_node(self, module_name):
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
        new_node = RigNode(pos.x() - 60, pos.y() - 20, module_type=module_name, side=side)
        self.scene.addItem(new_node)
        
        self.workspace.refresh_module_list()


class ModuleGraphWidget(QtWidgets.QWidget):
    def __init__(self, workspace):
        super(ModuleGraphWidget, self).__init__()
        self.workspace = workspace
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Guide Path:"))
        default_path = os.path.join(os.path.expanduser('~'), "kleem_guides.json").replace("\\", "/")
        self.path_field = QtWidgets.QLineEdit(default_path)
        top_layout.addWidget(self.path_field)
        
        btn_browse = QtWidgets.QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_path)
        
        btn_save = QtWidgets.QPushButton("Save Guides")
        btn_save.setStyleSheet("background-color: #996633; font-weight: bold;")
        btn_save.clicked.connect(self.save_all_guides)
        
        btn_load = QtWidgets.QPushButton("Load Guides")
        btn_load.setStyleSheet("background-color: #998033; font-weight: bold;")
        btn_load.clicked.connect(self.load_all_guides)
        
        top_layout.addWidget(btn_browse)
        top_layout.addWidget(btn_save)
        top_layout.addWidget(btn_load)
        self.layout.addLayout(top_layout)
        
        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.graph_view = NodeGraphView(self.workspace)
        self.split.addWidget(self.graph_view)
        
        self.attr_frame = QtWidgets.QFrame()
        self.attr_frame.setFixedWidth(220)
        self.attr_frame.setStyleSheet("background-color: #252526; border: 1px solid #333; border-radius: 4px;")
        attr_layout = QtWidgets.QVBoxLayout(self.attr_frame)
        attr_layout.setAlignment(QtCore.Qt.AlignTop)
        
        attr_layout.addWidget(QtWidgets.QLabel("<b>NODE EDITOR</b>"))
        
        self.lbl_node_type = QtWidgets.QLabel("Module Type: N/A")
        self.lbl_node_type.setStyleSheet("color: #aaa; border: none;")
        attr_layout.addWidget(self.lbl_node_type)
        
        attr_layout.addWidget(QtWidgets.QLabel("Custom Name:"))
        self.edit_custom_name = QtWidgets.QLineEdit()
        self.edit_custom_name.textChanged.connect(self.on_attr_changed)
        attr_layout.addWidget(self.edit_custom_name)
        
        attr_layout.addWidget(QtWidgets.QLabel("Side:"))
        self.combo_side = QtWidgets.QComboBox()
        self.combo_side.addItems(["L", "R", "C"])
        self.combo_side.currentTextChanged.connect(self.on_attr_changed)
        attr_layout.addWidget(self.combo_side)
        
        self.split.addWidget(self.attr_frame)
        self.layout.addWidget(self.split)
        
        bot_layout = QtWidgets.QHBoxLayout()
        btn_build_guides = QtWidgets.QPushButton("Build Guides (From Sidebar Selection)")
        btn_build_guides.setFixedHeight(40)
        btn_build_guides.setStyleSheet("background-color: #336699; font-weight: bold; font-size: 14px;")
        btn_build_guides.clicked.connect(lambda: self.execute_graph_nodes("guides"))
        
        btn_build_module = QtWidgets.QPushButton("Build Modules (From Sidebar Selection)")
        btn_build_module.setFixedHeight(40)
        btn_build_module.setStyleSheet("background-color: #339966; font-weight: bold; font-size: 14px;")
        btn_build_module.clicked.connect(lambda: self.execute_graph_nodes("rig"))
        
        bot_layout.addWidget(btn_build_guides)
        bot_layout.addWidget(btn_build_module)
        self.layout.addLayout(bot_layout)
        
        self.update_attr_editor()

    def get_node_by_uuid(self, uuid_str):
        for item in self.graph_view.scene.items():
            if isinstance(item, RigNode) and item.uuid == uuid_str:
                return item
        return None

    def update_attr_editor(self):
        if getattr(self, "_updating_attr", False): return
        
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) == 1:
            self.attr_frame.setEnabled(True)
            node = selected[0]
            self._updating_attr = True
            self.lbl_node_type.setText(f"Type: <b>{node.module_type}</b>")
            self.edit_custom_name.setText(node.custom_name)
            self.combo_side.setCurrentText(node.side)
            self._updating_attr = False
        else:
            self.attr_frame.setEnabled(False)
            self._updating_attr = True
            self.lbl_node_type.setText("Type: N/A")
            self.edit_custom_name.setText("")
            self._updating_attr = False

    def on_attr_changed(self):
        if getattr(self, "_updating_attr", False): return
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) == 1:
            node = selected[0]
            node.custom_name = self.edit_custom_name.text()
            node.side = self.combo_side.currentText()
            node.update_display()
            self.workspace.refresh_module_list()

    def browse_path(self):
        file_path = cmds.fileDialog2(fileFilter="JSON Files (*.json)", dialogStyle=2, fileMode=0)
        if file_path:
            self.path_field.setText(file_path[0])

    def save_all_guides(self):
        path = self.path_field.text()
        if not path: return
        guides = cmds.ls("*_guide", type="joint")
        if not guides:
            cmds.warning("No guides found ending in '_guide' to save.")
            return
            
        guide_data = {g: cmds.xform(g, query=True, translation=True, worldSpace=True) for g in guides}
        try:
            with open(path, 'w') as f:
                json.dump(guide_data, f, indent=4)
            cmds.warning(f"Successfully saved {len(guides)} guides to {path}")
        except Exception as e:
            cmds.error(f"Failed to save guides: {e}")

    def load_all_guides(self):
        path = self.path_field.text()
        if not os.path.exists(path):
            cmds.warning("Specified JSON file does not exist.")
            return
            
        try:
            with open(path, 'r') as f:
                guide_data = json.load(f)
            loaded_count = 0
            for guide_name, pos in guide_data.items():
                if cmds.objExists(guide_name):
                    cmds.xform(guide_name, translation=pos, worldSpace=True)
                    loaded_count += 1
            cmds.warning(f"Successfully loaded positions for {loaded_count} guides.")
        except Exception as e:
            cmds.error(f"Failed to load guides: {e}")

    def execute_graph_nodes(self, action):
        selected_items = self.workspace.rig_list.selectedItems()
        if not selected_items:
            cmds.warning("No modules selected in the left sidebar to build!")
            return
            
        selected_uuids = [item.data(QtCore.Qt.UserRole) for item in selected_items]
        
        nodes = [item for item in self.graph_view.scene.items() 
                 if isinstance(item, RigNode) and item.uuid in selected_uuids]
                 
        if not nodes:
            cmds.warning("No matching module nodes found in the graph editor to build!")
            return
            
        mod_path = self.graph_view.modules_path
        if mod_path not in sys.path:
            sys.path.insert(0, mod_path)
            
        for node in reversed(nodes):
            mod_name = node.module_type
            side = node.side
            file_path = os.path.join(mod_path, f"{mod_name}.py")
            
            if not os.path.exists(file_path):
                cmds.error(f"Module file not found: {file_path}")
                continue
                
            try:
                spec = importlib.util.spec_from_file_location(mod_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if action == "guides":
                    if hasattr(module, "build_guides"):
                        module.build_guides(side)
                    else:
                        cmds.warning(f"Module '{mod_name}' is missing a 'build_guides(side)' function.")
                        
                elif action == "rig":
                    if hasattr(module, "build_rig"):
                        module.build_rig(side)
                    else:
                        cmds.warning(f"Module '{mod_name}' is missing a 'build_rig(side)' function.")
                        
            except Exception as e:
                traceback.print_exc()
                cmds.error(f"Error executing {mod_name}: {e}")