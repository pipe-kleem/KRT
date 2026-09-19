"""ModuleGraphWidget - undo methods (mixin, auto-split from graph.py)."""
from ._shared import *
from .items import RigNode


class GraphUndoMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    # =====================================================
    # Graph editor undo/redo (Ctrl+Z / Ctrl+Shift+Z)
    #
    # A snapshot stack, not a command stack - each entry is a full
    # get_graph_config_data() dict (every node's type/position/side/scripts/
    # Plebe+custom-sgt fields/attach-point choice, every wire, and the Guide
    # Settings tab), restored wholesale via _apply_graph_config_data(). This
    # reuses the exact same read/write path Save/Load Guides and Export/
    # Import Config already rely on, instead of hand-writing a separate
    # undo-command class for every one of the many things that can change
    # in this editor - simpler and much less likely to miss something than
    # trying to enumerate every mutation site with its own inverse.
    # =====================================================

    def _clear_undo_history(self):
        """Called when a whole new graph gets loaded (Load Guides, Import
        Config, opening a different pipeline JSON) - the old undo/redo
        history belongs to a different graph and would just be confusing
        (or wrong) applied on top of this one."""
        self._undo_stack = []
        self._redo_stack = []
        self._edit_snapshot_pending = True

    def _push_undo_snapshot(self):
        """Record the graph's current state onto the undo stack, right
        BEFORE a mutating action is applied - call this first, then make
        the change. No-ops while a snapshot is already being applied (undo/
        redo/loading a file), so restoring a snapshot never records itself
        as a new undo step."""
        if self._suspend_undo_capture:
            return
        try:
            snap = copy.deepcopy(self.get_graph_config_data())
        except Exception:
            traceback.print_exc()
            return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self._max_undo_states:
            self._undo_stack.pop(0)
        self._redo_stack = []

    def _cancel_last_undo_snapshot(self):
        """Drop the most recently pushed undo snapshot - used when a
        'maybe this changed something' action (e.g. a node drag) turns out
        to have been a no-op (a plain click), so it doesn't leave a useless
        do-nothing entry in the undo history."""
        if self._undo_stack:
            self._undo_stack.pop()

    def _maybe_snapshot_before_edit(self):
        """Coalescing snapshot for Node-tab field edits: only the FIRST
        call since the selection last changed (or since the last undo/redo)
        actually pushes a snapshot, so typing a new Custom Name doesn't
        create one undo step per keystroke - Ctrl+Z undoes the whole recent
        edit, same as text-undo in most editors. update_attr_editor() resets
        the "pending" flag every time the Node tab repopulates for a
        (possibly different) selection."""
        if getattr(self, "_updating_attr", False):
            return
        if self._edit_snapshot_pending:
            self._push_undo_snapshot()
            self._edit_snapshot_pending = False

    def _restore_selection_by_uuid(self, uuids):
        """After a snapshot restore, re-select whichever of the
        previously-selected nodes still exist (they're all brand-new
        RigNode instances post-restore, same uuids) - otherwise every
        Ctrl+Z would also blank the Node tab, which gets old fast across a
        few undos in a row."""
        if not uuids:
            return
        found_any = False
        for u in uuids:
            node = self.get_node_by_uuid(u)
            if node:
                node.setSelected(True)
                found_any = True
        if found_any:
            self.update_attr_editor()

    def undo(self):
        if not self._undo_stack:
            return
        current = copy.deepcopy(self.get_graph_config_data())
        snap = self._undo_stack.pop()
        self._redo_stack.append(current)
        selected_uuids = [i.uuid for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        self._suspend_undo_capture = True
        try:
            self._apply_graph_config_data(snap)
        finally:
            self._suspend_undo_capture = False
        self._restore_selection_by_uuid(selected_uuids)
        self._edit_snapshot_pending = True

    def redo(self):
        if not self._redo_stack:
            return
        current = copy.deepcopy(self.get_graph_config_data())
        snap = self._redo_stack.pop()
        self._undo_stack.append(current)
        selected_uuids = [i.uuid for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        self._suspend_undo_capture = True
        try:
            self._apply_graph_config_data(snap)
        finally:
            self._suspend_undo_capture = False
        self._restore_selection_by_uuid(selected_uuids)
        self._edit_snapshot_pending = True
