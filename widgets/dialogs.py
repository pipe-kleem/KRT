"""Auto-split from widgets.py."""
from ._shared import *


class ErrorDialog(QtWidgets.QDialog):
    def __init__(self, title, msg, detail, parent=None, allow_retry=False):
        super(ErrorDialog, self).__init__(parent)
        self.retry = False
        self.setWindowTitle(title)
        self.setMinimumSize(600, 450)
        self.setStyleSheet("""
            QDialog { background-color: #252526; color: white; } 
            QTextEdit { color: #2bb5a8; font-family: Consolas; font-size: 13px; background: #1e1e1e; border: 1px solid #555; padding: 5px;} 
            QLabel { color: white; font-weight: bold; font-size: 14px; } 
            QPushButton { background-color: #3e3e42; color: white; font-weight: bold; padding: 8px 20px; font-size: 14px; border-radius: 4px;}
            QPushButton:hover { background-color: #555; }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(msg))
        
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(detail)
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        layout.addWidget(text_edit)
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        if allow_retry:
            btn_retry = QtWidgets.QPushButton("🔁 Retry")
            btn_retry.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
            btn_retry.clicked.connect(self._do_retry)
            btn_layout.addWidget(btn_retry)
        btn = QtWidgets.QPushButton("OK")
        btn.clicked.connect(self.accept)
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

    def _do_retry(self):
        self.retry = True
        self.accept()

class GraphNodeOrderDialog(QtWidgets.QDialog):
    """Pick any number of Graph Editor modules, and the exact order they
    should be added to a bubble panel in, in one popup - replaces having
    to select one module at a time in the sidebar and use 'Add from Graph
    Editor' repeatedly for a multi-module panel.

    Modules already in the target panel (existing_uuids, in their current
    bubble order) are pre-numbered here from the start, exactly reflecting
    "last time's" pick order, and are LOCKED - clicking one does nothing,
    since it's already a real bubble in the panel and this dialog only
    ever adds new ones. Any newly-clicked module is appended after all of
    those, so opening this dialog again to add just one more module never
    reshuffles what's already there; the caller only creates bubbles for
    the newly-clicked ones (see its own filtering against existing_uuids)."""

    def __init__(self, nodes, existing_uuids=None, parent=None):
        super(GraphNodeOrderDialog, self).__init__(parent)
        self.nodes = nodes  # list of RigNode, offered in graph/alphabetical order
        node_by_uuid = {n.uuid: n for n in self.nodes}
        # Pre-seed with whatever's already in the panel, in ITS current
        # order - "the order i selected last time" - so the numbering
        # picks up where it left off instead of starting over at 1 and
        # losing all prior work every time this dialog is reopened.
        self.locked_uuids = set(existing_uuids or [])
        self.order = [node_by_uuid[u] for u in (existing_uuids or []) if u in node_by_uuid]

        self.setWindowTitle("Add Modules from Graph Editor")
        self.setMinimumSize(380, 420)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QLabel { color: #cccccc; }
            QListWidget { background: #141414; border: 1px solid #333; color: white; }
            QListWidget::item { padding: 5px; }
            QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Click modules below in the order you want them added to this panel.\n"
            "Click an already-picked module again to remove it from the list.\n"
            "Modules already in this panel (\U0001F512, numbered from last time) are "
            "locked here - new picks are simply appended after them."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for node in self.nodes:
            item = QtWidgets.QListWidgetItem(node.display_title)
            item.setData(QtCore.Qt.UserRole, node.uuid)
            self.list_widget.addItem(item)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        btn_row = QtWidgets.QHBoxLayout()
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.setToolTip("Clears newly-picked modules only - modules already in the panel (locked) stay.")
        btn_clear.clicked.connect(self._clear_order)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QtWidgets.QPushButton("Add Selected")
        btn_ok.setStyleSheet("background-color: #2bb5a8; color: black; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._refresh_labels()

    def _on_item_clicked(self, item):
        node_uuid = item.data(QtCore.Qt.UserRole)
        if node_uuid in self.locked_uuids:
            return  # already a real bubble in the panel - not editable here
        node = next((n for n in self.nodes if n.uuid == node_uuid), None)
        if not node:
            return
        if node in self.order:
            self.order.remove(node)
        else:
            self.order.append(node)
        self._refresh_labels()

    def _clear_order(self):
        # Only drop the newly-picked (unlocked) modules - what's already
        # in the panel isn't touched by this dialog at all, so there's
        # nothing here to "clear" for it.
        self.order = [n for n in self.order if n.uuid in self.locked_uuids]
        self._refresh_labels()

    def _refresh_labels(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            node_uuid = item.data(QtCore.Qt.UserRole)
            node = next((n for n in self.nodes if n.uuid == node_uuid), None)
            if not node:
                continue
            locked = node_uuid in self.locked_uuids
            if node in self.order:
                idx = self.order.index(node) + 1
                if locked:
                    item.setText(f"{idx}. \U0001F512 {node.display_title}")
                    item.setBackground(QtGui.QColor("#2a2a2a"))
                    item.setForeground(QtGui.QColor("#888888"))
                else:
                    item.setText(f"{idx}. {node.display_title}")
                    item.setBackground(QtGui.QColor("#2bb5a8"))
                    item.setForeground(QtGui.QColor("black"))
            else:
                item.setText(node.display_title)
                item.setBackground(QtGui.QColor("#141414"))
                item.setForeground(QtGui.QColor("white"))
