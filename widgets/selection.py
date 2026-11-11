"""Multi-panel selection (Stage 53).

Click a panel's title/background to select it, Ctrl+click to add/remove,
Shift+click to select a range. The selection is owned by the workspace
(see workspace/panels.py - on_panel_clicked, copy_panels, paste_panels_at);
this mixin only turns a *click that was not a drag* into a call to it, and
draws the selected border.

Keyboard: with a panel focused (click it first), Ctrl+C copies the
selection, Ctrl+V pastes below the last selected panel, Esc clears.
"""
from ._shared import *


def _has_mod(mods, flag):
    """True if `flag` is held in `mods`. PySide2 (QFlags) and PySide6
    (Python enum.Flag) spell this differently, so try both."""
    try:
        return bool(mods & flag)
    except Exception:
        try:
            return (int(mods) & int(flag)) != 0
        except Exception:
            return False


class SelectableMixin(object):

    SELECT_COLOR = "#4fc3f7"

    def is_selected(self):
        return bool(getattr(self, "_selected", False))

    def set_selected(self, state):
        self._selected = bool(state)
        self.update_style()

    def _border_css(self, default="#333"):
        """Border used by update_style(): thick light-blue when selected."""
        if self.is_selected():
            return "2px solid " + self.SELECT_COLOR
        return "1px solid " + default

    def mouseReleaseEvent(self, event):
        # mousePressEvent (in each panel class) stores drag_start_pos. If the
        # mouse barely moved it was a click, not a drag-to-reorder.
        if event.button() == QtCore.Qt.LeftButton and hasattr(self, "drag_start_pos"):
            moved = (event.pos() - self.drag_start_pos).manhattanLength()
            if moved < QtWidgets.QApplication.startDragDistance():
                ws = getattr(self, "workspace", None)
                if ws is not None and hasattr(ws, "on_panel_clicked"):
                    ws.on_panel_clicked(self, event.modifiers())
        super(SelectableMixin, self).mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Stage 56: right-click on a panel opens its "..." menu. Child
        widgets that have their own menu (text fields, the ⏩ button)
        handle the event first, so they keep theirs."""
        if hasattr(self, "show_context_menu"):
            self.show_context_menu()
            event.accept()
            return
        super(SelectableMixin, self).contextMenuEvent(event)

    # --- keyboard -------------------------------------------------------
    _SEL_KEYS = ("copy", "paste", "esc")

    def _sel_key_action(self, event):
        mods = event.modifiers()
        ctrl = _has_mod(mods, QtCore.Qt.ControlModifier)
        key = event.key()
        if ctrl and key == QtCore.Qt.Key_C: return "copy"
        if ctrl and key == QtCore.Qt.Key_V: return "paste"
        if key == QtCore.Qt.Key_Escape: return "esc"
        return None

    def event(self, event):
        # ShortcutOverride: Qt asks the focused widget "do you want this key
        # yourself?" BEFORE any QShortcut/Maya hotkey fires. Accepting it
        # means Ctrl+C/V reach our keyPressEvent instead of Maya.
        if event.type() == QtCore.QEvent.ShortcutOverride and self._sel_key_action(event):
            event.accept()
            return True
        return super(SelectableMixin, self).event(event)

    def keyPressEvent(self, event):
        action = self._sel_key_action(event)
        ws = getattr(self, "workspace", None)
        if action and ws is not None:
            if action == "copy": ws.copy_panels(self)
            elif action == "paste": ws.paste_panels_below_selection()
            elif action == "esc": ws.clear_panel_selection()
            event.accept()
            return
        super(SelectableMixin, self).keyPressEvent(event)
