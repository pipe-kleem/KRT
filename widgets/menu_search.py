"""add_menu_search(menu): put a search box at the top of an 'Add Panel' menu."""
from ..compat import QtWidgets, QtCore, QtGui


def add_menu_search(menu):
    """Insert a 'Search panels...' line edit as the first entry of `menu`.
    Typing hides the entries that do not match; Enter picks the first match."""
    actions = menu.actions()
    box = QtWidgets.QLineEdit()
    box.setPlaceholderText("Search panels...")
    box.setClearButtonEnabled(True)
    box.setStyleSheet("QLineEdit { background: #1e1e1e; color: white; border: 1px solid #2bb5a8; "
                      "padding: 4px; margin: 4px; }")
    wa = QtWidgets.QWidgetAction(menu)
    wa.setDefaultWidget(box)
    if actions:
        menu.insertAction(actions[0], wa)
        menu.insertSeparator(actions[0])
    else:
        menu.addAction(wa)

    def _entries():
        return [a for a in menu.actions() if a is not wa and not a.isSeparator() and a.text()]

    def _filter(text):
        t = text.strip().lower()
        for a in _entries():
            a.setVisible((not t) or t in a.text().lower())

    def _enter():
        for a in _entries():
            if a.isVisible() and a.isEnabled():
                menu.setActiveAction(a)
                ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
                QtWidgets.QApplication.sendEvent(menu, ev)
                return

    box.textChanged.connect(_filter)
    box.returnPressed.connect(_enter)
    menu.aboutToShow.connect(lambda: (box.clear(), QtCore.QTimer.singleShot(0, box.setFocus)))
    return box
