"""Auto-split from widgets.py."""
from ._shared import *


class DragDropContainer(QtWidgets.QWidget):
    def __init__(self, workspace):
        super(DragDropContainer, self).__init__()
        self.workspace = workspace
        self.setAcceptDrops(True)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def dragEnterEvent(self, event):
        if hasattr(self.workspace, 'dragged_panel') and self.workspace.dragged_panel is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if hasattr(self.workspace, 'dragged_panel') and self.workspace.dragged_panel is not None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if hasattr(self.workspace, 'dragged_panel') and self.workspace.dragged_panel is not None:
            panel = self.workspace.dragged_panel
            drop_y = event.pos().y()
            index = -1
            for i in range(self.layout.count()):
                w = self.layout.itemAt(i).widget()
                if w and drop_y < w.geometry().center().y():
                    index = i
                    break
            
            if index == -1: self.layout.addWidget(panel)
            else: self.layout.insertWidget(index, panel)
            
            self.workspace.dragged_panel = None
            event.acceptProposedAction()
