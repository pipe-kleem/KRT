"""Auto-split from widgets.py."""
from ._shared import *


class FlowLayout(QtWidgets.QLayout):
    """A left-to-right, top-to-bottom WRAPPING layout - Qt's own classic
    "Flow Layout" example, ported to PySide/PyQt. Drop-in replacement for
    the QHBoxLayout that used to hold a panel's row of module/LOD bubbles:
    with enough bubbles added, a plain QHBoxLayout just runs the row off
    the edge of the panel with no way to see or reach the rest of them.
    This wraps onto as many additional rows as needed instead, and the
    panel grows taller to fit.

    Only the QLayout virtuals below are overridden - addWidget/removeWidget/
    indexOf keep working exactly as they did with QHBoxLayout, since those
    are QLayout base-class methods implemented in terms of addItem/itemAt/
    takeAt/count. insertWidget is NOT part of plain QLayout (only
    QBoxLayout has it), so it's added explicitly - BubbleDropArea.dropEvent
    (in-panel drag reordering) calls it directly."""

    def __init__(self, parent=None, margin=0, h_spacing=4, v_spacing=4):
        super(FlowLayout, self).__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)
        # This is the actual bug behind "loading a JSON pipeline only shows
        # one module bubble until LOAD is pressed" - addItem() is what
        # every plain addWidget() call goes through (QLayout implements
        # addWidget() in terms of addItem()), which is exactly how
        # add_module_bubble() adds each bubble while a pipeline JSON is
        # being loaded - potentially dozens of addItem() calls in a row,
        # often while this panel's page isn't even the visible tab yet.
        # Without marking the layout dirty here, Qt has no idea anything
        # changed: the FIRST bubble (added back when the layout was still
        # genuinely empty and got a real initial geometry pass some other
        # way) is the only one that ever had valid geometry computed for
        # it, and every bubble added after it just sits with no geometry
        # at all - invisible/collapsed - until something UNRELATED forces
        # a relayout later (pressing LOAD happens to do that, via its own
        # QApplication.processEvents()/dialog churn, which is why it
        # "fixes" it). insertWidget already learned this lesson (see its
        # own comment below) - addItem needed the exact same fix.
        self.invalidate()

    def insertWidget(self, index, widget):
        item = QtWidgets.QWidgetItem(widget)
        index = max(0, min(index, len(self._items)))
        self._items.insert(index, item)
        # activate() (not just invalidate()) so the reposition happens
        # synchronously, right now - insertWidget is used heavily during
        # live drag-and-drop reordering (see BubbleDropArea/_show_drop_gap),
        # and invalidate() alone only POSTS a deferred LayoutRequest event.
        # Under rapid drag-move events that deferred pass could still be
        # pending when the next mutation landed, so bubbles briefly rendered
        # at stale/overlapping positions instead of their current slot.
        self.invalidate()
        self.activate()

    def horizontalSpacing(self):
        return self._h_spacing

    def verticalSpacing(self):
        return self._v_spacing

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QtCore.QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            # Skip any genuinely-hidden item exactly like a QHBoxLayout
            # would skip a removed one, so it doesn't leave a gap. (A
            # bubble mid-drag is no longer hidden for this - see
            # ModuleBubble._start_drag - but this stays as the general
            # rule for any widget that IS actually hidden for other
            # reasons, e.g. toggle_active().)
            if widget is not None and not widget.isVisible():
                continue
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom
