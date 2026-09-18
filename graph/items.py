"""Auto-split from graph.py."""
from ._shared import *


class RigWire(QtWidgets.QGraphicsPathItem):
    """A parent -> child connection between two RigNodes, drawn as a smooth
    S-curve (like a node-graph wire) rather than a straight line. Selectable
    and deletable (Delete key, or right-click -> Disconnect) so a connection
    can be removed by hand without touching the Parent Module dropdown."""
    def __init__(self, source_node, dest_node):
        super(RigWire, self).__init__()
        self.source = source_node; self.dest = dest_node
        self.source.add_wire(self); self.dest.add_wire(self)
        self.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 3))
        self.setBrush(QtCore.Qt.NoBrush)
        self.setZValue(-1)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.update_position()
        self.refresh_tooltip()

    def update_position(self):
        self.setPath(bezier_path(self.source.sceneBoundingRect(), self.dest.sceneBoundingRect()))

    def refresh_tooltip(self):
        """Stage 28, request #2: show which specific guide locator (not
        just 'somewhere on the parent') this wire actually attaches under,
        at a glance, without opening the Node tab - right-click on the wire
        (Change Attach Point...) to change it."""
        target = self.dest.parent_local_target
        label = target.split("|")[-1] if target else "(Whole Guide Root)"
        self.setToolTip(f"Attached under: {label}")

    def shape(self):
        # The bare bezier path is only a couple of pixels wide - much too
        # thin to click reliably. Stroke it out into a fat invisible band so
        # clicking/selecting/right-clicking near the curve actually hits it.
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget):
        if self.isSelected():
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffaa33"), 4))
        else:
            painter.setPen(self.pen())
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(self.path())


def bezier_path(src_rect, dst_rect):
    """Cubic-bezier QPainterPath from the right edge of src_rect to the left
    edge of dst_rect (falling back to center-to-center when the nodes
    overlap horizontally), with control points that flatten out for long
    connections and stay gentle for short ones."""
    p1 = QtCore.QPointF(src_rect.right(), src_rect.center().y())
    p2 = QtCore.QPointF(dst_rect.left(), dst_rect.center().y())
    if p2.x() < p1.x():
        p1 = src_rect.center()
        p2 = dst_rect.center()
    reach = max(abs(p2.x() - p1.x()) * 0.5, 40.0)
    c1 = QtCore.QPointF(p1.x() + reach, p1.y())
    c2 = QtCore.QPointF(p2.x() - reach, p2.y())
    path = QtGui.QPainterPath(p1)
    path.cubicTo(c1, c2, p2)
    return path

class RigNode(QtWidgets.QGraphicsRectItem):
    def __init__(self, x, y, module_type="", side="L", custom_name=""):
        super(RigNode, self).__init__(0, 0, 140, 40)
        self.setPos(x, y)

        self.uuid = str(uuid.uuid4())
        self.module_type = module_type
        self.custom_name = custom_name or module_type
        self.side = side

        # Set once "Build Guides" has actually drawn this component in the
        # scene: the long name of its mGear guide root transform. Lets later
        # "Build Modules" calls (and the Rig Builder Workspace module panel)
        # find the real Maya node without re-drawing it.
        self.maya_guide_root = None

        # Optional per-module custom script: runs after this node's guide is
        # drawn ("guides") or after it is built into a rig ("modules"), or
        # never ("none"). Set/edited via the Node Editor's Custom Script button.
        self.custom_script_code = ""
        self.custom_script_lang = "python"   # "python" or "mel"
        # Stage 26: a brand-new Custom Script node's whole purpose IS its
        # script, so default it to actually running (at "guides" time, since
        # that's this node type's only real build phase) instead of the
        # normal "none" - every other node type still defaults to "none".
        self.custom_script_when = "guides" if module_type == CUSTOM_SCRIPT_MODULE_TYPE else "none"

        # Stage 30: only meaningful for a CUSTOM_SCRIPT_MODULE_TYPE node -
        # lets the user pick ANY other node in the graph (not just this
        # node's own graph-parent) as the thing this script waits on. When
        # set, _build_custom_script_node builds that specific chosen node's
        # guide (recursively, through the normal build_node_guide path)
        # before firing the script, instead of only ever building its own
        # graph-parent chain. None = old behavior (own graph parent only).
        # Stores the target node's uuid, not a live reference, so it
        # survives save/load; self-heals to "no dependency" if the target
        # was deleted (see _build_custom_script_node).
        self.custom_script_trigger_node_uuid = None

        # Only meaningful when module_type == PLEBE_MODULE_TYPE: which
        # character-generator template (mgear/shifter/plebes_templates/*.json)
        # to align mGear's biped guide to, and whether that alignment runs
        # automatically as part of "Build Guides".
        self.plebe_template_path = None
        self.plebe_template_name = ""
        self.align_guides_auto = True

        # Stage 31, request: "i did not change the placement of plebe guides,
        # but it is still changing the position of guides when i am loading
        # and building." Remembering hand-moved guide placement (Stage 28) is
        # only ever wanted if the rigger DID move something - a stored
        # snapshot from an earlier save otherwise gets replayed on top of a
        # freshly auto-aligned biped and drags it back to where it used to
        # be, which reads as the build randomly moving guides on its own.
        # This switches that replay off per node, without throwing the stored
        # placement away (turn it back on and it applies again). Capturing
        # continues either way - see ModuleGraphWidget.
        # apply_node_guide_positions().
        self.apply_guide_positions = True

        # Stage 19, also Plebe-only: Fan Joint / Stretchy Joint auto-scripts,
        # each independently toggleable (default OFF) and independently
        # editable (defaults to the studio's UniUtils calls). Both run right
        # after this node's rig is built - see run_node_auto_scripts().
        self.fan_joint_enabled = False
        self.fan_joint_script = DEFAULT_FAN_JOINT_SCRIPT
        self.stretchy_joint_enabled = False
        self.stretchy_joint_script = DEFAULT_STRETCHY_JOINT_SCRIPT

        # Also only meaningful for a Plebe node: a .ma/.mb file of
        # "*_controlBuffer" curves merged into this node's guide right after
        # it's drawn, so the biped's controls come out shaped from it
        # instead of the default icon shapes (see build_node_guide's
        # sibling, _build_plebe_guide, and utils.apply_control_shapes_library).
        # Defaults to the studio library for a Plebe node; stays empty (and
        # unused) for a regular Shifter component.
        self.control_shapes_library = DEFAULT_CONTROL_SHAPES_LIBRARY if module_type == PLEBE_MODULE_TYPE else ""

        # Only meaningful when module_type == CUSTOM_SGT_MODULE_TYPE: the
        # standalone .sgt guide template file this node imports instead of
        # drawing a catalog component (see _build_custom_sgt_guide).
        self.custom_sgt_path = None

        # Only meaningful when module_type == CUSTOM_SCRIPT_MODULE_TYPE: this
        # node type has no guide of its own, so there's no maya_guide_root to
        # hang a "built" checkmark off of the way every other node type does
        # - this tracks whether its script has actually run successfully at
        # least once instead (see run_node_custom_script / update_display).
        # Deliberately NOT saved in serialize_node - like maya_guide_root,
        # it's runtime build state, not something to persist between sessions.
        self.custom_script_ran = False

        # Stage 27: mGear's own per-component "Settings" dialog (Main
        # Settings tab) mirrored directly into this Node tab, so it never
        # needs opening separately - see ModuleGraphWidget's component_group
        # UI, build_node_guide's normal-component branch (feeds these in via
        # comp_guide.setParamDefValue before drawFromUI), and
        # apply_main_settings_live (writes straight to the real Maya
        # attribute once a guide already exists). Only meaningful for a real
        # Shifter catalog component - not Plebe/Custom Module/Custom Script,
        # none of which draw a normal component guide with these attributes.
        # Defaults match mGear's own addParam defaults (component/guide.py).
        self.comp_index = 0
        self.connector = "standard"
        self.use_joint_index = False
        self.parent_joint_index = -1
        self.joint_names = ""              # comma-joined, same storage mGear itself uses
        self.joint_rot_offset_x = 0.0
        self.joint_rot_offset_y = 0.0
        self.joint_rot_offset_z = 0.0
        self.ui_host = ""                  # explicit override; empty = inherit from parent (unchanged prior behavior)
        self.ctl_group = ""                # explicit override; empty = inherit from parent (unchanged prior behavior)
        self.override_colors = False
        self.use_rgb_colors = False
        self.color_fk_index = 6
        self.color_ik_index = 18
        self.color_fk_rgb = (0.0, 0.0, 1.0)
        self.color_ik_rgb = (0.0, 0.25, 1.0)

        # Which specific guide locator under the parent node's built guide to
        # attach beneath (e.g. a "chest" locator on a spine module), rather
        # than the parent's whole guide root. None = attach at the parent's
        # own root (the previous, only, behavior). Long Maya node name.
        #
        # This is the single source of truth for where this node parents -
        # it is set once (Attach Under combo, the popup after dragging a
        # wire, or the wire's own right-click menu) and from then on is
        # ALWAYS trusted as-is on every rebuild: _resolve_attach_parent()
        # never renames or clears it on its own. If the exact name isn't in
        # the scene when this node's guide gets (re)built - the parent
        # module hasn't been built yet, say - the child still gets drawn
        # (at its saved WORLD position, see capture_node_guide_positions),
        # just not parented under that specific locator; parent_local_target
        # itself is left untouched for the very next build to try again.
        self.parent_local_target = None

        # Only matters for a node with no parent connection (a top-level
        # module, or the root of its own branch): when True, "Build Guides"
        # always starts a brand-new top-level guide group for it (Maya
        # auto-names it guide1, guide2, ... once "guide" is taken) instead
        # of merging into whatever shared guide hierarchy already exists in
        # the scene. Lets multiple independent characters/props be guided
        # side by side in one scene rather than always sharing one "guide".
        self.build_separate_guide_group = False

        # Most recent traceback from this node's custom script, if its last
        # run failed - drives the "Script Error" state in the Node tab and
        # the warning marker on the node itself. Cleared on a successful run
        # or when the script is edited and re-saved (see CustomScriptDialog).
        self.custom_script_last_error = ""

        # Stage 28, request #3: a rigger commonly hand-moves guide locators
        # around in the viewport after "Build Guides" (to actually match the
        # character) - but a guide that later gets deleted and redrawn (the
        # module-bubble LOAD flow always does this; so does re-running Build
        # Guides after a "Save Guides"/reload) used to come back at mGear's
        # default template position every time, silently discarding that
        # work. This holds the last-captured local translate/rotate/scale of
        # every transform under this node's own guide, keyed by short name -
        # see ModuleGraphWidget.capture_node_guide_positions() (writes this,
        # called from Save Guides/Export Config) and
        # apply_node_guide_positions() (reads it, called right after a fresh
        # guide is drawn). Persisted via serialize_node/deserialize_node so
        # it travels with Save Guides/Export Config/the pipeline JSON, same
        # as everything else about this node.
        self.guide_position_snapshot = {}

        # Stage 31: where this node's guide sat immediately after it was last
        # built, in the same shape as guide_position_snapshot. Memory only -
        # deliberately NOT serialized, and never written into
        # guide_position_snapshot by a build - it exists purely so the live
        # placement watcher can answer "has this been moved since it was
        # built?" for a node the user has never recorded a placement for.
        # See ModuleGraphWidget._capture_position_baseline().
        self._pos_baseline = None

        # Stage 31, request #1: every OTHER user setting on this node's guide
        # root - i.e. everything mGear's own "Component Settings" tab edits
        # (control_01's joint/leafJoint/uniScale/icon/ctlSize/keyable
        # channels/ikRefArray, and whatever the equivalent is for each of the
        # other ~50 component types). Captured generically as
        # {attribute name: value} straight off the live guide root rather
        # than field-by-field, because those attributes are different for
        # every single component type - the same "read Maya's own truth
        # instead of re-implementing it" approach the Main Settings mirror
        # deliberately does NOT take (it only covers the handful of
        # attributes that are common to every component).
        # Written by ModuleGraphWidget.capture_node_component_settings(),
        # replayed by apply_node_component_settings() after a rebuild, and
        # persisted through serialize_node/deserialize_node - so it travels
        # in the guides JSON and the KRT pipeline JSON alike.
        self.component_settings_snapshot = {}

        self.setBrush(QtGui.QBrush(QtGui.QColor("#3e3e42")))
        self.setPen(QtGui.QPen(QtGui.QColor("#555555"), 2))

        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemSendsGeometryChanges |
                      QtWidgets.QGraphicsItem.ItemIsSelectable)

        self.text = QtWidgets.QGraphicsTextItem("", self)
        self.text.setDefaultTextColor(QtGui.QColor("#cccccc"))
        self.text.setPos(10, 8)
        self.wires = []

        # Radius of the small connector "pin" drawn at the left (parent
        # input) and right (child output) edges - click-drag from the right
        # pin to wire this node as a parent, drop on another node's left pin
        # (or anywhere on its body) to make the connection. No Maya-node
        # editor requires holding Ctrl for this; Ctrl+drag from the node
        # body still works too, for muscle memory.
        self.PORT_RADIUS = 5.5

        self.update_display()

    def update_display(self):
        icon = "🧍 " if self.module_type == PLEBE_MODULE_TYPE \
            else "📄 " if self.module_type == CUSTOM_SGT_MODULE_TYPE \
            else "📝 " if self.module_type == CUSTOM_SCRIPT_MODULE_TYPE else ""
        # A Custom Script node never gets a maya_guide_root (no guide) - use
        # custom_script_ran as its stand-in "built" signal instead.
        built_or_ran = bool(self.maya_guide_root) or \
            (self.module_type == CUSTOM_SCRIPT_MODULE_TYPE and self.custom_script_ran)
        mark = "✓ " if built_or_ran else ""
        # Stage 30: "i need prof that it is running" - a colored dot right
        # on the node itself, visible on the canvas with no need to open
        # the Node tab: 🔴 error, 🟢 ran successfully at least once this
        # session, 🔵 attached and set to run but hasn't fired yet. See
        # _update_script_label for the same three states spelled out in
        # the Node tab's Scripts page.
        if self.custom_script_last_error:
            script_mark = " 🔴 SCRIPT ERROR"
        elif self.custom_script_when != "none" and self.custom_script_code.strip():
            script_mark = " 🟢" if self.custom_script_ran else " 🔵"
        else:
            script_mark = ""
        self.display_title = f"{icon}{mark}{self.custom_name} [{self.side}]{script_mark}"
        self.setToolTip(self.display_title)

        # Keep the label fully readable: widen the box to fit short/medium
        # names, and elide (with "...") only once a name would make the box
        # unreasonably wide - the full name is always still on the tooltip.
        fm = QtGui.QFontMetrics(self.text.font())
        text_advance = (fm.horizontalAdvance if hasattr(fm, "horizontalAdvance") else fm.width)
        min_box_w, max_box_w = 140, 240
        shown_text = self.display_title
        if text_advance(shown_text) + 20 > max_box_w:
            shown_text = fm.elidedText(self.display_title, QtCore.Qt.ElideRight, max_box_w - 20)
        self.text.setPlainText(shown_text)
        box_w = max(min_box_w, min(max_box_w, text_advance(shown_text) + 24))
        self.prepareGeometryChange()
        self.setRect(0, 0, box_w, 40)
        self.text.setPos(10, 8)

        # Green-tinted border once the component's guide actually exists in
        # the scene, so it's obvious at a glance what still needs building.
        if built_or_ran:
            self.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 2))
        else:
            self.setPen(QtGui.QPen(QtGui.QColor("#555555"), 2))
        # Plebe (character-template) nodes get a distinct purple tint so
        # they read as "whole biped template" rather than a single component;
        # a custom .sgt-file node gets its own distinct brown tint.
        if self.module_type == PLEBE_MODULE_TYPE:
            self.setBrush(QtGui.QBrush(QtGui.QColor("#3d2e52")))
        elif self.module_type == CUSTOM_SGT_MODULE_TYPE:
            self.setBrush(QtGui.QBrush(QtGui.QColor("#4a3826")))
        elif self.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            # Stage 30: "should look very different (its design should look
            # like just for script and very different color and design)" -
            # this node type has no guide at all, so it's deliberately made
            # to read as a different KIND of thing on the canvas, not just a
            # different color of the same box: a distinct magenta fill AND
            # a dashed (not solid) border, always - the dash is a visual
            # shorthand for "no guide lives here, it's a script hook", the
            # same idea as a dashed line meaning "no physical connection" in
            # a wiring diagram. Deliberately NOT trying a different node
            # SHAPE (e.g. rounded/diamond) - RigNode's rect-based geometry
            # (boundingRect, port positions, bezier wire math) all assume a
            # plain rectangle, and changing that is real layout risk with no
            # way to verify it outside a live Maya/Qt session (see the
            # Stage 28 Known Caveats entry on the multi-pin redesign for the
            # same reasoning).
            self.setBrush(QtGui.QBrush(QtGui.QColor("#4a1f4a")))
            pen = self.pen()
            pen.setStyle(QtCore.Qt.DashLine)
            self.setPen(pen)
        else:
            self.setBrush(QtGui.QBrush(QtGui.QColor("#3e3e42")))
        # A failed custom script takes priority over every other border
        # color - it needs to be impossible to miss on the canvas.
        if self.custom_script_last_error:
            pen = QtGui.QPen(QtGui.QColor("#ff5555"), 2)
            if self.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                pen.setStyle(QtCore.Qt.DashLine)
            self.setPen(pen)

    def add_wire(self, wire): self.wires.append(wire)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            for wire in self.wires: wire.update_position()
        return super(RigNode, self).itemChange(change, value)

    def _owning_graph_widget(self):
        """Find this node's ModuleGraphWidget (for undo snapshots) - a
        RigNode doesn't keep its own reference to it, so reach it the same
        way graph.py's other node-agnostic helpers do: via the view that's
        actually showing this node's scene."""
        scene = self.scene()
        if not scene:
            return None
        views = scene.views()
        if not views or not hasattr(views[0], "workspace"):
            return None
        return getattr(views[0].workspace, "graph_widget", None)

    def mousePressEvent(self, event):
        # A plain drag moves the node (Qt's own ItemIsMovable) - snapshot
        # BEFORE the move happens so Ctrl+Z can put it back, then drop that
        # snapshot again in mouseReleaseEvent below if the position turns
        # out not to have actually changed (a plain click/select).
        if event.button() == QtCore.Qt.LeftButton:
            self._krt_drag_start_pos = self.pos()
            gw = self._owning_graph_widget()
            if gw:
                gw._push_undo_snapshot()
        super(RigNode, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super(RigNode, self).mouseReleaseEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            start = getattr(self, "_krt_drag_start_pos", None)
            if start is not None and self.pos() == start:
                gw = self._owning_graph_widget()
                if gw:
                    gw._cancel_last_undo_snapshot()
            self._krt_drag_start_pos = None

    def input_port_pos(self):
        """Local-coordinates position of the left-edge ('parent') pin."""
        r = self.rect()
        return QtCore.QPointF(r.left(), r.center().y())

    def output_port_pos(self):
        """Local-coordinates position of the right-edge ('child') pin."""
        r = self.rect()
        return QtCore.QPointF(r.right(), r.center().y())

    def boundingRect(self):
        # Extend past the plain rect so the connector pins (which sit centred
        # on the left/right edges) never get clipped mid-paint.
        r = super(RigNode, self).boundingRect()
        pad = self.PORT_RADIUS + 2
        return r.adjusted(-pad, 0, pad, 0)

    def paint(self, painter, option, widget):
        if self.isSelected():
            # A selection needs to read clearly at a glance even on an
            # already-built (teal-bordered) node, so it gets its own color
            # and a filled highlight rather than sharing the teal outline.
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffaa33"), 3))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#4a3d1f")))
        else:
            painter.setPen(self.pen())
            painter.setBrush(self.brush())
        painter.drawRect(self.rect())

        # Connector pins, drawn like any standard node-editor's input/output
        # sockets - filled teal when something is wired there, hollow when
        # not, so an empty attachment point is visually obvious too.
        has_input = any(w.dest is self for w in self.wires)
        has_output = any(w.source is self for w in self.wires)
        painter.setPen(QtGui.QPen(QtGui.QColor("#1e1e1e"), 1.5))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#2bb5a8") if has_input else QtGui.QColor("#3e3e42")))
        painter.drawEllipse(self.input_port_pos(), self.PORT_RADIUS, self.PORT_RADIUS)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#2bb5a8") if has_output else QtGui.QColor("#3e3e42")))
        painter.drawEllipse(self.output_port_pos(), self.PORT_RADIUS, self.PORT_RADIUS)
