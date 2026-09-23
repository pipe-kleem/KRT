"""Panel collapse (Stage 49).

Every panel class is built the same way: a QVBoxLayout whose FIRST item is
the header row (checkbox, icon, title) and whose remaining items are the
body. Collapsing therefore means "hide everything after item 0" - the frame
shrinks to the header on its own, because a QVBoxLayout re-measures when its
children are hidden.

Widgets are hidden rather than removed so nothing is rebuilt: state, signals
and field contents all survive a collapse/expand round trip untouched.
"""
from ._shared import *


class CollapseMixin(object):

    def _init_collapse(self, main_layout, header_layout):
        """Call at the END of __init__, once every row has been added."""
        self._main_layout = main_layout
        self._collapsed = False

        self.btn_collapse = QtWidgets.QPushButton("▾")
        self.btn_collapse.setFixedSize(20, 20)
        self.btn_collapse.setToolTip("Collapse this panel to just its title.")
        self.btn_collapse.setStyleSheet(
            "QPushButton { background: transparent; color: #cccccc; border: none;"
            " font-size: 13px; font-weight: bold; }"
            " QPushButton:hover { color: #2bb5a8; }")
        self.btn_collapse.clicked.connect(self.toggle_collapsed)
        # Left of the checkbox, so the disclosure triangle reads as belonging
        # to the whole panel rather than to the active toggle.
        header_layout.insertWidget(0, self.btn_collapse)

    def _body_items(self):
        """Every widget below the header row, nested layouts included."""
        layout = getattr(self, "_main_layout", None)
        if layout is None:
            return []
        widgets = []

        def collect(item):
            w = item.widget()
            if w is not None:
                widgets.append(w)
                return
            sub = item.layout()
            if sub is not None:
                for i in range(sub.count()):
                    collect(sub.itemAt(i))

        for i in range(1, layout.count()):     # 1 = skip the header row
            collect(layout.itemAt(i))
        return widgets

    def is_collapsed(self):
        return bool(getattr(self, "_collapsed", False))

    def set_collapsed(self, state, remember=True):
        state = bool(state)
        if remember:
            self._collapsed = state
        for w in self._body_items():
            w.setVisible(not state)
        if hasattr(self, "btn_collapse"):
            self.btn_collapse.setText("▸" if state else "▾")
            self.btn_collapse.setToolTip(
                "Expand this panel." if state else "Collapse this panel to just its title.")
        # Let the stack re-flow immediately instead of on the next event.
        self.updateGeometry()
        if self.layout() is not None:
            self.layout().activate()
        self.adjustSize()

    def toggle_collapsed(self):
        self.set_collapsed(not self.is_collapsed())
