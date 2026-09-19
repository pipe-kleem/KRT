"""ModuleGraphWidget - positions methods (mixin, auto-split from graph.py)."""
from ._shared import *
from .items import RigNode


class GraphPositionsMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    def _make_apply_positions_row(self):
        """Build one "Apply Saved Guide Positions" checkbox + "Clear" button
        row. Returns (checkbox, layout).

        Stage 31: KRT remembers hand-moved guide placement and replays it
        after every rebuild (Stage 28). That is right when the rigger moved
        something on purpose, and wrong when they didn't - a placement stored
        by an earlier save gets replayed over a freshly auto-aligned guide and
        drags it back, which looks like the build moving guides by itself.
        Unchecking this leaves a rebuilt guide exactly where mGear (and, for a
        Plebe biped, its auto-align) put it. The stored placement is kept, not
        discarded, so this is reversible; 'Clear' is the separate, explicit
        way to actually throw a stale one away."""
        container = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        chk = QtWidgets.QCheckBox("Apply Saved Guide Positions")
        chk.setToolTip(
            "ON (default): after this node's guide is rebuilt, whatever guide placement "
            "was recorded for it is applied on top - so guides you moved by hand come "
            "back where you left them. For a Plebe biped this happens AFTER auto-align, "
            "so your own tweaks win.\n\n"
            "OFF: the rebuilt guide is left exactly where mGear (and auto-align) drew it. "
            "Use this if you never moved anything by hand and a stored placement from an "
            "earlier save is dragging your guides somewhere you don't want.\n\n"
            "Turning this off does NOT delete the stored placement - tick it again and it "
            "applies as before. Use 'Clear' to actually discard it."
        )
        chk.toggled.connect(self.on_attr_changed)
        row.addWidget(chk)

        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.setFixedWidth(60)
        btn_clear.setToolTip(
            "Permanently forget the guide placement recorded for this node, so future "
            "rebuilds use mGear's own placement (and auto-align) only. The next time you "
            "record a placement it starts fresh from wherever the guides are then."
        )
        btn_clear.clicked.connect(self.clear_selected_node_guide_positions)
        row.addWidget(btn_clear)
        row.addStretch()
        return chk, container

    def clear_selected_node_guide_positions(self):
        """Throw away the selected node's stored guide placement."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module in the graph first.")
            return
        node = selected[0]
        if not node.guide_position_snapshot:
            cmds.warning(f"'{node.display_title}' has no recorded guide placement to clear.")
            return
        self._push_undo_snapshot()
        node.guide_position_snapshot = {}
        # Whatever the guide is at right now becomes the new "unmoved"
        # reference, so the placement light doesn't immediately go red off
        # the snapshot that was just deleted.
        self._capture_position_baseline(node)
        self._refresh_position_watch()
        cmds.warning(f"[KRT] Cleared the recorded guide placement for '{node.display_title}'. "
                     "Rebuilds will now use mGear's own placement only. Save to persist this.")

    # =====================================================
    # Stage 28, request #3: remember/restore hand-moved guide positions
    # =====================================================

    def capture_node_guide_positions(self, node):
        """Snapshot the current local translate/rotate/scale of every
        transform under `node`'s own built guide (root included), keyed by
        its path RELATIVE TO THE GUIDE ROOT (see _guide_key()), onto
        node.guide_position_snapshot - a no-op that leaves the previous
        snapshot untouched if this node's guide isn't currently built in
        the scene (nothing new to capture, and the last real snapshot is
        worth more than an empty one). Local (not world) values, the same
        numbers mGear's own guide locators actually store on their
        translate/rotate/scale attributes - safe to re-apply after a rebuild
        regardless of where the parent guide itself ends up.

        Keying by the relative path (not bare short name) is what lets two
        differently-parented transforms that happen to share the same short
        name - easy to hit on a large composite guide with several
        similarly-built sub-chains - both get their own remembered
        position, instead of one silently overwriting the other's entry.
        """
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        transforms = self._guide_transforms(root)
        if not transforms:
            return
        root_long = transforms[0]
        snapshot = {}
        for long_name in transforms:
            key = self._guide_key(root_long, long_name)
            try:
                snapshot[key] = {
                    "t": cmds.getAttr(f"{long_name}.translate")[0],
                    "r": cmds.getAttr(f"{long_name}.rotate")[0],
                    "s": cmds.getAttr(f"{long_name}.scale")[0],
                }
            except Exception:
                continue
        if snapshot:
            node.guide_position_snapshot = snapshot

    def capture_all_guide_positions(self):
        """Capture every graph node's currently-built guide positions in one
        pass - called right before Save Guides/Export Config write anything
        out, so "where the guides actually are right now" is what gets
        remembered, without the user needing a separate manual step."""
        for item in self.graph_view.scene.items():
            if isinstance(item, RigNode):
                self.capture_node_guide_positions(item)

    def apply_node_guide_positions(self, node):
        """Inverse of capture_node_guide_positions() - called right after a
        fresh guide is drawn for `node` (build_node_guide's normal-component
        branch, _build_plebe_guide, _build_custom_sgt_guide), reapplying any
        previously-captured positions by matching short name.

        Stage 31: this is now the single post-build restore hook every build
        path already calls, so it also replays the node's mGear Component
        Settings snapshot (which a rebuild would otherwise discard exactly
        like it used to discard hand-moved positions), and records where the
        guide ended up as the live position watcher's "unmoved" reference -
        so the indicator can tell a hand-moved guide from a freshly-built one
        even for a node nothing has ever been recorded for."""
        self._apply_node_guide_positions(node)
        self.apply_node_component_settings(node)
        self._capture_position_baseline(node)

    def _apply_node_guide_positions(self, node):
        """The actual re-apply. Silently skips anything in the snapshot that
        no longer exists on the freshly-drawn guide (a template/version
        change is more likely than a bug), and leaves anything with no saved
        entry at whatever mGear's own default just drew it at."""
        # Stage 31: the rigger can switch this replay off per node (the
        # "Apply Saved Guide Positions" checkbox, right under "Align Guides
        # Automatically" for a Plebe). The stored placement is deliberately
        # left intact - this only stops it being pushed onto the guide.
        if not getattr(node, "apply_guide_positions", True):
            return
        root = node.maya_guide_root
        snapshot = node.guide_position_snapshot
        if not root or not snapshot or not cmds.objExists(root):
            return
        transforms = self._guide_transforms(root)
        if not transforms:
            return
        root_long = transforms[0]
        for long_name in transforms:
            saved = snapshot.get(self._guide_key(root_long, long_name))
            if saved is None:
                # Backward compat with a guide JSON saved before this fix
                # (bare-short-name keys).
                saved = snapshot.get(long_name.split("|")[-1])
            if not saved:
                continue
            try:
                if "t" in saved: cmds.setAttr(f"{long_name}.translate", *saved["t"])
                if "r" in saved: cmds.setAttr(f"{long_name}.rotate", *saved["r"])
                if "s" in saved: cmds.setAttr(f"{long_name}.scale", *saved["s"])
            except Exception:
                continue

    def capture_all_live_state(self):
        """Stage 31, request #2: "whatever we are doing and saving in guide
        json, all things will save in KRT json also".

        The single "pull everything the user has changed in Maya back into
        the graph's own data" pass, called from EVERY place that writes a
        JSON - Save Guides, Export Config, and workspace.py's pipeline/session
        JSON. Both JSONs already share serialize_node(), so having one shared
        capture entry point is what keeps them from drifting apart as more
        live state gets remembered over time."""
        for item in self.graph_view.scene.items():
            if not isinstance(item, RigNode):
                continue
            self.capture_node_guide_positions(item)
            self.sync_node_main_settings_from_guide(item)
            self.capture_node_component_settings(item)

    def _guide_transforms(self, root):
        """[root's own long path] + every descendant transform's long path,
        root normalized to its full scene path first so it's directly
        comparable (same format) to what listRelatives(fullPath=True)
        returns for everything under it - _guide_key() below relies on
        that to correctly strip the root's own prefix off each descendant."""
        try:
            root_long = cmds.ls(root, long=True)[0]
            return [root_long] + (cmds.listRelatives(
                root_long, allDescendents=True, type="transform", fullPath=True) or [])
        except Exception:
            return []

    def _guide_key(self, root_long, long_name):
        """Key a guide transform by its path RELATIVE TO THE GUIDE ROOT,
        not just its bare short name. A large composite guide (several
        similarly-built sub-chains - e.g. repeated finger/tooth/tentacle
        locator naming across different limbs) can easily have two
        DIFFERENT transforms that share the same short name; keying by
        short name alone made capture/apply/compare silently collide on
        those - only one of several same-named locators' positions ever
        got remembered, a rebuild could push that ONE saved position onto
        all of them, and the live-placement watcher would then compare the
        others against the wrong locator's saved values forever - the "●"
        light staying/going red with nothing actually moved. Falls back to
        the short name if `long_name` doesn't start with `root_long` for
        some reason (should not normally happen)."""
        if long_name == root_long:
            return ""
        prefix = root_long + "|"
        if long_name.startswith(prefix):
            return long_name[len(prefix):]
        return long_name.split("|")[-1]

    def _read_guide_placement(self, root):
        """{relative path under root: {t,r,s}} for everything under a built
        guide root."""
        placement = {}
        transforms = self._guide_transforms(root)
        root_long = transforms[0] if transforms else root
        for long_name in transforms:
            try:
                placement[self._guide_key(root_long, long_name)] = {
                    "t": cmds.getAttr(f"{long_name}.translate")[0],
                    "r": cmds.getAttr(f"{long_name}.rotate")[0],
                    "s": cmds.getAttr(f"{long_name}.scale")[0],
                }
            except Exception:
                continue
        return placement

    def _capture_position_baseline(self, node):
        """Record where this node's guide sits right now as the watcher's
        "unmoved" reference. Memory only - deliberately NOT persisted and
        NOT written into guide_position_snapshot, so a build can never
        quietly overwrite placements the user actually recorded."""
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        try:
            node._pos_baseline = self._read_guide_placement(root)
        except Exception:
            traceback.print_exc()

    def _node_position_reference(self, node):
        """What this node's live guide should be compared against: whatever
        the user last recorded, else where it was when it was built.

        Stage 31: with "Apply Saved Guide Positions" off, the stored
        placement is deliberately NOT what the guide is built to, so
        comparing against it would light this node red forever. Compare
        against where the build actually left it instead."""
        if not getattr(node, "apply_guide_positions", True):
            return getattr(node, "_pos_baseline", None)
        return node.guide_position_snapshot or getattr(node, "_pos_baseline", None)

    def _node_position_moved(self, node):
        """True if this node's built guide has been moved away from its
        reference placement. Stops at the first difference found - on a full
        biped guide that keeps the common "nothing moved" case cheap."""
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return False
        reference = self._node_position_reference(node)
        if not reference:
            return False
        transforms = self._guide_transforms(root)
        root_long = transforms[0] if transforms else root
        for long_name in transforms:
            saved = reference.get(self._guide_key(root_long, long_name))
            if saved is None:
                # Backward compat: a guide JSON saved before this fix keyed
                # everything by bare short name - fall back to that so an
                # older recorded placement still matches instead of the
                # whole node reading as "moved" the first time it's opened.
                saved = reference.get(long_name.split("|")[-1])
            if not saved:
                continue
            for key, attr in (("t", "translate"), ("r", "rotate"), ("s", "scale")):
                if key not in saved:
                    continue
                try:
                    current = cmds.getAttr(f"{long_name}.{attr}")[0]
                except Exception:
                    continue
                for now, then in zip(current, saved[key]):
                    if abs(now - then) > self.POSITION_EPSILON:
                        return True
        return False

    def _set_position_watch_ui(self, dirty, moved_count):
        self._pos_watch_dirty = bool(dirty)
        if dirty:
            color, border = "#e05252", "#ff8a8a"
            self.lbl_pos_watch.setText(
                "Guide placement changed on {} module(s) - click to record it".format(moved_count))
            self.lbl_pos_watch.setStyleSheet("color: #e08a8a; font-size: 11px; border: none;")
            tip = ("RED: at least one built guide has been moved in the scene since its placement "
                   "was last recorded.\n\nClick to record where every built guide sits right now. "
                   "That placement is saved with the guides JSON, and is reapplied automatically "
                   "the next time these guides are rebuilt (for a Plebe biped, after its own "
                   "auto-align, so your tweak wins).")
        else:
            color, border = "#3faf5f", "#7fd89a"
            self.lbl_pos_watch.setText("Guide placement up to date")
            self.lbl_pos_watch.setStyleSheet("color: #777; font-size: 11px; border: none;")
            tip = ("GREEN: every built guide is sitting where it was last recorded (or where it "
                   "was built).\n\nMove any guide in the scene and this turns red. Clicking it "
                   "records the current placement into the guides JSON so a rebuild puts "
                   "everything back exactly where you left it.")
        self.btn_pos_watch.setStyleSheet(
            "QPushButton {{ background-color: {0}; color: {0}; border: 2px solid {1};"
            " border-radius: 11px; font-size: 1px; }}"
            " QPushButton:hover {{ border: 2px solid white; }}".format(color, border))
        self.btn_pos_watch.setToolTip(tip)

    def _refresh_position_watch(self):
        """Timer tick - read-only, and every Maya call inside is individually
        guarded, so a scene mid-change or a half-deleted guide can never turn
        this into an error storm."""
        if self._pos_watch_suspended or not self.isVisible():
            return
        try:
            moved = 0
            for item in self.graph_view.scene.items():
                if isinstance(item, RigNode) and self._node_position_moved(item):
                    moved += 1
            self._set_position_watch_ui(moved > 0, moved)
        except Exception:
            # Never let a background tick spam the Script Editor.
            pass

    def on_position_watch_clicked(self):
        """Record the live placement of every built guide, so a later rebuild
        redraws them exactly where they sit now."""
        recorded = []
        for item in self.graph_view.scene.items():
            if not isinstance(item, RigNode):
                continue
            root = item.maya_guide_root
            if not root or not cmds.objExists(root):
                continue
            before = self._node_position_moved(item)
            self.capture_node_guide_positions(item)
            self._capture_position_baseline(item)
            if before:
                recorded.append(item.display_title)
        self._set_position_watch_ui(False, 0)
        if recorded:
            cmds.warning("[KRT] Recorded new guide placement for: {}. Save Guides (or Save "
                         "Session) to write it to disk - a rebuild will now redraw these "
                         "guides where they are now.".format(", ".join(recorded)))
        else:
            cmds.warning("[KRT] Guide placement recorded - nothing had moved since the last "
                         "recording.")
