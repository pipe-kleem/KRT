import maya.cmds as cmds
import os
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from .session import SessionManager
from .dialogs import AdvancedSaveDialog
from .workspace import SessionWorkspace

class KRT_Tool(MayaQWidgetBaseMixin, QtWidgets.QDialog):
    def __init__(self, parent=None):
        # Initialize Maya's native workspace mixin layer safely
        super(KRT_Tool, self).__init__(parent=parent)

        self.setWindowTitle("KRT | Procedural Builder")
        self.setMinimumSize(1100, 850)
        self.setObjectName("KRT_Window")
        
        self.session = SessionManager()
        
        self.setup_ui()
        self.apply_style()
        self.create_new_session()

        # Autosave background heartbeat
        self.autosave_timer = QtCore.QTimer(self)
        self.autosave_timer.timeout.connect(self.trigger_global_autosave)
        self.autosave_timer.start(300000) # 5 minutes

    def trigger_global_autosave(self):
        for i in range(self.session_stack.count()):
            self.session_stack.widget(i).perform_autosave()

    def closeEvent(self, event):
        """Native Qt intercept to kill background timers before C++ deletion."""
        if hasattr(self, 'autosave_timer') and self.autosave_timer.isActive():
            self.autosave_timer.stop()
        event.accept()

    def setup_ui(self):
        self.layout_main = QtWidgets.QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        # --- Top Tab Bar ---
        top_bar_widget = QtWidgets.QWidget()
        top_bar_widget.setStyleSheet("background-color: #2d2d30; border-bottom: 1px solid #1e1e1e;")
        top_layout = QtWidgets.QHBoxLayout(top_bar_widget)
        top_layout.setContentsMargins(5, 5, 5, 5)
        
        self.tab_bar = QtWidgets.QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.currentChanged.connect(self.on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self.close_session)
        
        btn_add = QtWidgets.QPushButton("+")
        btn_add.setFixedSize(25, 25)
        btn_add.setStyleSheet("background-color: transparent; font-weight: bold; color: white;")
        btn_add.clicked.connect(lambda: self.create_new_session())
        
        top_layout.addWidget(self.tab_bar)
        top_layout.addWidget(btn_add)
        top_layout.addStretch() 
        
        # --- Right Aligned Session Controls ---
        self.session_controls_widget = QtWidgets.QWidget()
        sc_layout = QtWidgets.QHBoxLayout(self.session_controls_widget)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(8)
        sc_layout.setAlignment(QtCore.Qt.AlignRight)

        self.btn_load_json = QtWidgets.QPushButton("📂 Load JSON Pipeline")
        self.btn_load_json.setStyleSheet("background-color: #3e3e42; font-weight: bold; padding: 5px 10px;")
        self.btn_load_json.clicked.connect(self.trigger_browse_pipeline)
        
        self.btn_reset = QtWidgets.QPushButton("🔄 Reset Scene & UI")
        self.btn_reset.setStyleSheet("background-color: #3e3e42; font-weight: bold; padding: 5px 10px;")
        self.btn_reset.clicked.connect(self.trigger_reset_scene)

        self.btn_save_session = QtWidgets.QPushButton("💾 Save Session")
        self.btn_save_session.setStyleSheet("background-color: #2bb5a8; font-weight: bold; color: white; padding: 5px 10px;")
        self.btn_save_session.clicked.connect(self.open_advanced_save_dialog)
        
        self.btn_browse_path = QtWidgets.QPushButton("📂")
        self.btn_browse_path.setToolTip("Browse and load a JSON session file")
        self.btn_browse_path.setStyleSheet("background-color: transparent; font-size: 16px;")
        self.btn_browse_path.clicked.connect(self.browse_session_path)

        lbl_path = QtWidgets.QLabel(" Current Path:")
        lbl_path.setStyleSheet("color: #ccc; font-weight: bold;")
        self.session_path_field = QtWidgets.QLineEdit()
        self.session_path_field.setToolTip("Edit path and press Enter to Load")
        self.session_path_field.returnPressed.connect(self.load_path_from_field)
        self.session_path_field.setFixedWidth(200)
        
        self.btn_load_path = QtWidgets.QPushButton("Load")
        self.btn_load_path.setStyleSheet("background-color: #3e3e42; color: white;")
        self.btn_load_path.clicked.connect(self.load_path_from_field)

        sc_layout.addWidget(self.btn_load_json)
        sc_layout.addWidget(self.btn_reset)
        sc_layout.addWidget(self.btn_save_session)
        sc_layout.addWidget(self.btn_browse_path)
        sc_layout.addWidget(lbl_path)
        sc_layout.addWidget(self.session_path_field)
        sc_layout.addWidget(self.btn_load_path)

        top_layout.addWidget(self.session_controls_widget)
        self.layout_main.addWidget(top_bar_widget)

        # --- Workspace Stack ---
        self.session_stack = QtWidgets.QStackedWidget()
        self.layout_main.addWidget(self.session_stack)

    def trigger_browse_pipeline(self):
        curr_ws = self.session_stack.currentWidget()
        if curr_ws: curr_ws.browse_pipeline_json()

    def trigger_reset_scene(self):
        curr_ws = self.session_stack.currentWidget()
        if curr_ws: curr_ws.reset_scene_and_ui()

    def create_new_session(self, load_path=None):
        new_workspace = SessionWorkspace(self)
        self.session_stack.addWidget(new_workspace)
        
        idx = self.tab_bar.addTab("Untitled Session")
        self.tab_bar.setCurrentIndex(idx)
        
        if load_path:
            new_workspace.load_pipeline_from_file(load_path)

    def on_tab_changed(self, index):
        if index >= 0:
            self.session_stack.setCurrentIndex(index)
            ws = self.session_stack.widget(index)
            self.session_path_field.setText(ws.session_path)

            inner_idx = ws.workspace_stack.currentIndex()
            ws.switch_tab(inner_idx) 

    def close_session(self, index):
        if self.tab_bar.count() == 1:
            ws = self.session_stack.widget(0)
            ws.reset_scene_and_ui()
            ws.clear_all_panels()
            ws.create_lod_workspace("LOD0")
            ws.setup_default_panels()
            ws.graph_widget.graph_view.scene.clear()
            ws.set_session_path("")
        else:
            ws = self.session_stack.widget(index)
            self.session_stack.removeWidget(ws)
            self.tab_bar.removeTab(index)
            ws.deleteLater()

    def browse_session_path(self):
        res = cmds.fileDialog2(fm=1, ff="JSON (*.json)", caption="Load Pipeline JSON Session")
        if res:
            self.session_path_field.setText(res[0])
            self.load_path_from_field()

    def load_path_from_field(self):
        path = self.session_path_field.text().strip()
        if os.path.exists(path):
            current_ws = self.session_stack.currentWidget()
            if current_ws:
                current_ws.load_pipeline_from_file(path)
        else:
            cmds.warning("Invalid Path provided.")

    def open_advanced_save_dialog(self):
        current_ws = self.session_stack.currentWidget()
        if not current_ws: return
        dialog = AdvancedSaveDialog(current_ws)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def refresh_all_session_lists(self):
        for i in range(self.session_stack.count()):
            self.session_stack.widget(i).refresh_session_lists()

    def apply_style(self):
        # Scoped to #KRT_Window and its children so Maya's own theme cannot bleed
        # in and so this sheet never leaks out onto Maya's native UI. Menus,
        # combo boxes, checkboxes and scrollbars are styled explicitly here
        # because those popups otherwise inherit Maya's look and mismatch.
        self.setStyleSheet("""
            QDialog#KRT_Window { background-color: #1e1e1e; color: white; }
            QWidget { color: #e6e6e6; }
            QFrame#SidebarFrame { background-color: #252526; border-right: 1px solid #333; }
            QLineEdit { background: #1e1e1e; border: 1px solid #333; color: white; padding: 6px; font-family: 'Consolas'; }
            QLineEdit:focus { border: 1px solid #2bb5a8; }
            QListWidget { background: #1e1e1e; border: 1px solid #333; padding: 5px; }
            QListWidget::item:selected { background: #14403c; border: 1px solid #2bb5a8; border-radius: 3px; }
            QListWidget#LodList QLineEdit {
                font-family: Arial, Helvetica, sans-serif;
                font-size: 16pt;
                font-weight: normal;
                background: #3e3e42;
                color: white;
                border: 1px solid #2bb5a8;
            }
            QPushButton { background: #333; color: white; padding: 6px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
            QTabBar::tab { background: #333; color: #ccc; padding: 5px 10px; margin-right: 2px; }
            QTabBar::tab:selected { background: #1e1e1e; color: white; border-top: 2px solid #2bb5a8; font-weight: bold; }
            QTabBar::close-button { image: url(); background: transparent; color: #2bb5a8; font-weight: bold; margin: 2px; }
            QTabBar::close-button:hover { background: #555; }
            QMenu { background-color: #252526; color: white; border: 1px solid #2bb5a8; }
            QMenu::item { padding: 5px 22px; }
            QMenu::item:selected { background-color: #2bb5a8; color: #10221f; }
            QMenu::separator { height: 1px; background: #3e3e42; margin: 4px 6px; }
            QComboBox { background: #1e1e1e; border: 1px solid #333; color: white; padding: 4px; }
            QComboBox:hover { border: 1px solid #2bb5a8; }
            QComboBox QAbstractItemView { background: #252526; color: white; selection-background-color: #2bb5a8; }
            QCheckBox { color: #cccccc; }
            QCheckBox::indicator:checked { background-color: #2bb5a8; border: 1px solid #2bb5a8; }
            QScrollBar:vertical { background: #1e1e1e; width: 12px; }
            QScrollBar::handle:vertical { background: #3e3e42; border-radius: 4px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: #2bb5a8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

def run_tool():
    """Finds any existing window instances, cleanly closes them to halt background tasks, then runs fresh."""
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == "KRT_Window":
            w.close()
            w.deleteLater()

    global krt_app
    krt_app = KRT_Tool()
    krt_app.show()

if __name__ == "__main__":
    run_tool()