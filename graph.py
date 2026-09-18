import maya.cmds as cmds
import os
import json
import re
import uuid
import copy
import traceback
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from .utils import apply_control_shapes_library

# ---------------------------------------------------------------------------
# mGear Shifter component discovery
#
# The Module Graph Editor no longer reads custom per-studio .py "module"
# scripts from a hardcoded network path. Instead it lists every real Shifter
# component (classic + epic) the same way Shifter's own Guide Manager does,
# and drives the real mgear guide/build API directly.
# ---------------------------------------------------------------------------

# Sentinel module_type for a node representing mGear's "Rig Plebe" biped
# template workflow (import biped guide -> align to a character-generator
# template) rather than a single atomic Shifter component.
PLEBE_MODULE_TYPE = "__plebe_biped__"
PLEBE_SEARCH_LABEL = "★ mGear Plebe - Biped Template..."

# Sentinel module_type for a node that imports a standalone .sgt guide
# template file the user saved themselves (e.g. a stock component they
# hand-tweaked and re-exported from mGear's own Guide Manager) rather than
# building one of the catalog components listed by list_mgear_components().
CUSTOM_SGT_MODULE_TYPE = "__custom_sgt__"
CUSTOM_SGT_SEARCH_LABEL = "📄 Custom Module (from .sgt file)..."

# Stage 26: sentinel module_type for a node that imports/draws NO guide at
# all - unlike every other node type, it has no catalog component and no
# .sgt file, nothing to configure except its own custom script (the generic
# custom_script_code/lang/when fields every RigNode already has - see
# CustomScriptDialog). Exists purely so a script-only build step (scene
# cleanup, an export, calling into another tool, enforcing build order
# between two unrelated branches, etc) can sit in the graph as its own node
# instead of being tacked onto some unrelated component that happens to be
# nearby. See RigNode.custom_script_ran / ModuleGraphWidget.
# _build_custom_script_node for how it participates in Build Guides/Build
# Modules without ever having a maya_guide_root.
CUSTOM_SCRIPT_MODULE_TYPE = "__custom_script__"
CUSTOM_SCRIPT_SEARCH_LABEL = "📝 Custom Script Module (no guide)..."

# Shared control-shapes library: a .ma/.mb file of "*_controlBuffer" curves
# (mGear's own hand-authored-shape convention - see build_node_guide()) that
# gets merged into every guide's controllers_org automatically, so every
# module's controls come out shaped like this instead of the component's
# generic default icon. Editable per-graph in the Node tab; this is only
# the starting default shown there.
DEFAULT_CONTROL_SHAPES_LIBRARY = r"R:\Pipeline_Share\Pipeline_share\RigUtils\controlShapes.ma"

# Stage 19: the studio's Fan Joint / Stretchy Joint setup scripts for a Plebe
# biped node (Node tab, right after Align Guides Automatically). Both run
# automatically right after this node's rig is actually built ("modules"),
# same timing as the per-node custom script, since they act on real built
# joints rather than guides. Editable per-node in the Node tab (a plain
# python/mel-style text box, same idea as the custom script editor) - these
# are only the starting defaults.
DEFAULT_FAN_JOINT_SCRIPT = (
    "import maya.cmds as cmds\n"
    "import re\n"
    "import sys\n"
    "import importlib\n"
    "import os\n"
    "sys.path.append(r\"R:/Pipeline_Share/Pipeline_share/RigUtils\")\n"
    "import UniUtils\n"
    "importlib.reload(UniUtils)\n"
    "UniUtils.run_Fan()\n"
)
DEFAULT_STRETCHY_JOINT_SCRIPT = (
    "import maya.cmds as cmds\n"
    "import re\n"
    "import sys\n"
    "import importlib\n"
    "import os\n"
    "sys.path.append(r\"R:/Pipeline_Share/Pipeline_share/RigUtils\")\n"
    "import UniUtils\n"
    "importlib.reload(UniUtils)\n"
    "UniUtils.run_stretchy()\n"
)

_MGEAR_COMPONENT_CACHE = None


def list_mgear_components(force_refresh=False):
    """Return a sorted list of every available mGear Shifter component type
    (e.g. 'arm_2jnt_01', 'chain_01', ...), matching the Component List shown
    in Shifter's own Guide Manager window.

    Results are cached for the Maya session; pass force_refresh=True (or
    call clear_mgear_component_cache()) after installing new custom
    components at runtime.
    """
    global _MGEAR_COMPONENT_CACHE
    if _MGEAR_COMPONENT_CACHE is not None and not force_refresh:
        return _MGEAR_COMPONENT_CACHE

    try:
        from mgear import shifter as mg_shifter
    except ImportError:
        cmds.warning("mGear is not installed/loaded - cannot list Shifter components.")
        return []

    try:
        comp_dirs = mg_shifter.getComponentDirectories()
        names = set()
        for directory, entries in comp_dirs.items():
            for entry in entries:
                if entry.startswith("__"):
                    continue
                full = os.path.join(directory, entry)
                if os.path.isdir(full) and os.path.exists(os.path.join(full, "guide.py")):
                    names.add(entry)
        _MGEAR_COMPONENT_CACHE = sorted(names)
    except Exception:
        traceback.print_exc()
        cmds.warning("Failed to gather mGear Shifter component list - see Script Editor.")
        _MGEAR_COMPONENT_CACHE = []

    return _MGEAR_COMPONENT_CACHE


def clear_mgear_component_cache():
    global _MGEAR_COMPONENT_CACHE
    _MGEAR_COMPONENT_CACHE = None


def list_plebe_templates():
    """Every character-generator template mGear's own "Rig Plebe" tool would
    list in its "Choose a Character Template" menu (mgear.shifter.plebes.
    Plebes.populate_template_menu), as {display_name: json_path}.

    Reads mgear/shifter/plebes_templates/*.json plus any extra directories
    named in the PLEBE_TEMPLATES_DIR environment variable.
    """
    entries = {}
    try:
        from mgear.shifter import plebes as mg_plebes
    except ImportError:
        return entries

    search_dirs = []
    env_dirs = os.environ.get("PLEBE_TEMPLATES_DIR", "")
    if env_dirs:
        # Plebe's own code splits on ':', which breaks on Windows drive
        # letters (C:\...) - os.pathsep is correct on every platform.
        search_dirs.extend(p for p in env_dirs.split(os.pathsep) if p)
    search_dirs.append(os.path.join(os.path.dirname(mg_plebes.__file__), "plebes_templates"))

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not fname.lower().endswith(".json"):
                continue
            display = fname[:-5].replace("_", " ").title()
            entries[display] = os.path.join(directory, fname)
    return entries


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


class CustomScriptDialog(QtWidgets.QDialog):
    """Lets the user attach a MEL or Python script to a single graph node,
    to be run automatically right after that node's guide is drawn or right
    after it is built into a rig."""

    WHEN_LABELS = [("Do not run", "none"), ("After Build Guides", "guides"), ("After Build Modules", "modules")]

    def __init__(self, node, parent=None, all_nodes=None):
        super(CustomScriptDialog, self).__init__(parent)
        self.node = node
        # Stage 30: every OTHER node currently in the graph, offered as a
        # "wait for this module's guide before running" choice - only
        # actually shown for a CUSTOM_SCRIPT_MODULE_TYPE node (see below).
        # Passed in by the caller (which has the live scene) rather than
        # looked up here, so this dialog stays scene-access-free like the
        # rest of its own code.
        self.all_nodes = all_nodes or []
        self.setWindowTitle(f"Custom Script - {node.display_title}")
        self.setMinimumSize(520, 420)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QLabel { color: #cccccc; }
            QComboBox { background: #1e1e1e; border: 1px solid #333; color: white; padding: 4px; }
            QPlainTextEdit { background: #141414; border: 1px solid #333; color: #d4d4d4; font-family: 'Consolas'; font-size: 12px; }
            QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Language:"))
        self.combo_lang = QtWidgets.QComboBox()
        self.combo_lang.addItems(["Python", "MEL"])
        self.combo_lang.setCurrentText("MEL" if node.custom_script_lang == "mel" else "Python")
        row.addWidget(self.combo_lang)

        row.addSpacing(20)
        row.addWidget(QtWidgets.QLabel("Run:"))
        self.combo_when = QtWidgets.QComboBox()
        for label, _ in self.WHEN_LABELS:
            self.combo_when.addItem(label)
        cur_idx = next((i for i, (_, key) in enumerate(self.WHEN_LABELS) if key == node.custom_script_when), 0)
        self.combo_when.setCurrentIndex(cur_idx)
        row.addWidget(self.combo_when)
        row.addStretch()
        layout.addLayout(row)

        # Stage 30: "the custom script module which we have created - add
        # option that when it will trigger - means after which module. i
        # should able to select any module in its option" - only meaningful
        # for a Custom Script node (a regular component's own attached
        # script already has a real, single build slot on ITS OWN guide/rig
        # - there's nothing else for it to "wait for").
        self.combo_trigger = None
        if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            trig_row = QtWidgets.QHBoxLayout()
            trig_row.addWidget(QtWidgets.QLabel("Trigger after module:"))
            self.combo_trigger = QtWidgets.QComboBox()
            self.combo_trigger.addItem("(default - own graph parent, if any)", None)
            cur_target_idx = 0
            for i, other in enumerate(sorted(self.all_nodes, key=lambda n: n.display_title.lower())):
                self.combo_trigger.addItem(other.display_title, other.uuid)
                if other.uuid == node.custom_script_trigger_node_uuid:
                    cur_target_idx = i + 1
            self.combo_trigger.setCurrentIndex(cur_target_idx)
            trig_row.addWidget(self.combo_trigger, 1)
            layout.addLayout(trig_row)
            hint = QtWidgets.QLabel(
                "This node's guide-build will wait for the picked module's guide to be built "
                "first (recursively, same as it already does for its own graph parent), then "
                "run the script above - instead of only ever waiting on its own graph parent."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(hint)

        layout.addWidget(QtWidgets.QLabel(f"Script for: {node.display_title}  (type: {node.module_type})"))

        self.code_edit = QtWidgets.QPlainTextEdit()
        self.code_edit.setPlainText(node.custom_script_code)
        self.code_edit.setPlaceholderText("# Runs in KRT's shared Python/MEL namespace once this module reaches the point selected above.")
        layout.addWidget(self.code_edit)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self.code_edit.clear)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QtWidgets.QPushButton("Save")
        btn_ok.setStyleSheet("background-color: #2bb5a8; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_clear); btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def apply_to_node(self):
        self.node.custom_script_lang = "mel" if self.combo_lang.currentText() == "MEL" else "python"
        self.node.custom_script_when = self.WHEN_LABELS[self.combo_when.currentIndex()][1]
        if self.combo_trigger is not None:
            self.node.custom_script_trigger_node_uuid = self.combo_trigger.currentData()
        new_code = self.code_edit.toPlainText()
        if new_code != self.node.custom_script_code:
            # Editing and saving the script is treated as an attempted fix -
            # auto-clear any previous error state rather than leaving a
            # stale ⚠ warning up for a script that has since changed. Stage
            # 30: also clear the "ran ✓" status - that was proof the OLD
            # code ran, which says nothing about whether this new code will.
            self.node.custom_script_last_error = ""
            self.node.custom_script_ran = False
        self.node.custom_script_code = new_code
        self.node.update_display()


class AutoScriptEditDialog(QtWidgets.QDialog):
    """Stage 19: minimal editor for a Plebe node's Fan Joint / Stretchy Joint
    auto-script - a plain Python text box with Save/Cancel/Reset to Default.
    Simpler than CustomScriptDialog on purpose: these two always run as
    Python, right after Build Modules, so there's no language/when picker
    to show."""

    def __init__(self, title, current_code, default_code, parent=None):
        super(AutoScriptEditDialog, self).__init__(parent)
        self.default_code = default_code
        self.setWindowTitle(title)
        self.setMinimumSize(520, 380)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QLabel { color: #cccccc; }
            QPlainTextEdit { background: #141414; border: 1px solid #333; color: #d4d4d4; font-family: 'Consolas'; font-size: 12px; }
            QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(title))

        self.code_edit = QtWidgets.QPlainTextEdit()
        self.code_edit.setPlainText(current_code)
        layout.addWidget(self.code_edit)

        btn_row = QtWidgets.QHBoxLayout()
        btn_default = QtWidgets.QPushButton("Reset to Default")
        btn_default.setToolTip("Replace the text above with the studio's default script for this action.")
        btn_default.clicked.connect(lambda: self.code_edit.setPlainText(self.default_code))
        btn_row.addWidget(btn_default)
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QtWidgets.QPushButton("Save")
        btn_ok.setStyleSheet("background-color: #2bb5a8; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def result_code(self):
        return self.code_edit.toPlainText()


class PlebeTemplateDialog(QtWidgets.QDialog):
    """Character-template picker mirroring mGear Plebe's own 'Choose a
    Character Template' dropdown + help preview (mgear.shifter.plebes)."""

    def __init__(self, templates, parent=None, current_path=None):
        super(PlebeTemplateDialog, self).__init__(parent)
        self.templates = templates  # {display_name: json_path}
        self.selected_name = None
        self.selected_path = None

        self.setWindowTitle("mGear Plebe - Choose a Character Template")
        self.setMinimumSize(380, 340)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QLabel { color: #cccccc; }
            QComboBox { background: #1e1e1e; border: 1px solid #333; color: white; padding: 4px; }
            QTextEdit { background: #141414; border: 1px solid #333; color: #d4d4d4; font-size: 12px; }
            QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Imports mGear's standard biped guide template, then can align it to your\n"
            "imported character using the same guide/joint mapping mGear's own\n"
            "'Rig Plebe' window uses for this generator."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QtWidgets.QLabel("Character Template:"))
        self.combo = QtWidgets.QComboBox()
        self.names = sorted(templates.keys())
        self.combo.addItems(self.names)
        self.combo.currentTextChanged.connect(self._on_change)
        layout.addWidget(self.combo)

        self.help_view = QtWidgets.QTextEdit()
        self.help_view.setReadOnly(True)
        layout.addWidget(self.help_view)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QtWidgets.QPushButton("Use This Template")
        btn_ok.setStyleSheet("background-color: #2bb5a8; font-weight: bold;")
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        start_name = None
        if current_path:
            for name, path in templates.items():
                if path == current_path:
                    start_name = name
                    break
        if start_name:
            self.combo.setCurrentText(start_name)
        elif self.names:
            self._on_change(self.names[0])

    def _on_change(self, name):
        path = self.templates.get(name)
        help_text = ""
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                help_text = data.get("help", "") or "(No help text in this template.)"
            except Exception:
                help_text = "(Could not read this template's help text.)"
        self.help_view.setPlainText(help_text)

    def _accept(self):
        name = self.combo.currentText()
        if not name:
            cmds.warning("Pick a character template first.")
            return
        self.selected_name = name
        self.selected_path = self.templates.get(name)
        self.accept()


class NodeSearchPopup(QtWidgets.QWidget):
    """Tab/double-click component picker. `header_labels`, if given, marks
    certain entries (e.g. a "── Recent ──" divider) as unselectable section
    headers - shown while browsing the full list, hidden while actively
    typing a search (since they're not real matches for anything)."""
    def __init__(self, modules_list, callback, parent=None, header_labels=None):
        super(NodeSearchPopup, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.setStyleSheet("""
            QWidget { background-color: #252526; color: #cccccc; border: 1px solid #2bb5a8; border-radius: 3px; }
            QLineEdit { background-color: #1e1e1e; border: 1px solid #555; padding: 5px; font-family: 'Consolas'; color: white;}
            QListWidget { border: none; outline: none; font-size: 13px; padding: 2px;}
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #2bb5a8; color: white; border-radius: 2px;}
            QListWidget::item:hover { background-color: #3e3e42; }
        """)

        self.setFixedSize(240, 320)
        self.callback = callback
        self.header_labels = set(header_labels or [])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("Search mGear components...")
        layout.addWidget(self.search_bar)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)

        for mod in modules_list:
            item = QtWidgets.QListWidgetItem(mod)
            if mod in self.header_labels:
                item.setFlags(QtCore.Qt.NoItemFlags)
                item.setForeground(QtGui.QColor("#777777"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list_widget.addItem(item)
        self._select_first_selectable()

        self.search_bar.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_selected)
        self.search_bar.returnPressed.connect(self.on_enter_pressed)

        self.search_bar.installEventFilter(self)
        self.search_bar.setFocus()

    def _select_first_selectable(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden() and item.text() not in self.header_labels:
                self.list_widget.setCurrentRow(i)
                return

    def filter_list(self, text):
        search_text = text.lower()
        first_visible = -1
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.text() in self.header_labels:
                # Headers only make sense while browsing the unfiltered
                # list - hide them once the user is actively searching.
                item.setHidden(bool(search_text))
                continue
            match = search_text in item.text().lower()
            item.setHidden(not match)
            if match and first_visible == -1:
                first_visible = i

        if first_visible != -1:
            self.list_widget.setCurrentRow(first_visible)

    def on_item_selected(self, item):
        if item.text() in self.header_labels:
            return
        self.callback(item.text())
        self.close()

    def on_enter_pressed(self):
        item = self.list_widget.currentItem()
        if item and not item.isHidden() and item.text() not in self.header_labels:
            self.callback(item.text())
            self.close()

    def eventFilter(self, obj, event):
        if obj == self.search_bar and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Up:
                self.move_selection(-1)
                return True
            elif event.key() == QtCore.Qt.Key_Down:
                self.move_selection(1)
                return True
        return super(NodeSearchPopup, self).eventFilter(obj, event)

    def move_selection(self, step):
        row = self.list_widget.currentRow()
        for _ in range(self.list_widget.count()):
            row += step
            if 0 <= row < self.list_widget.count():
                item = self.list_widget.item(row)
                if not item.isHidden() and item.text() not in self.header_labels:
                    self.list_widget.setCurrentRow(row)
                    break
            else:
                break

class NodeGraphView(QtWidgets.QGraphicsView):
    def __init__(self, workspace):
        super(NodeGraphView, self).__init__()
        self.workspace = workspace
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.setSceneRect(0, 0, 4000, 4000)

        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#1e1e1e")))
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)

        # Without an explicit resize anchor, QGraphicsView defaults to
        # keeping the scene's top-left corner fixed and just reveals/hides
        # more of the bottom-right as the widget resizes - which reads as
        # the graph "jumping" or getting clipped whenever the KRT window is
        # resized while the graph tab is open. Anchoring to the view's
        # center instead keeps whatever you were looking at roughly in
        # place across a resize.
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        # Connection-drag state (Ctrl+drag from one RigNode onto another
        # wires them as parent -> child in the mGear guide hierarchy).
        self._connect_source = None
        self._temp_wire_line = None
        # True while a Ctrl+drag on empty canvas is panning the view.
        self._pan_active = False

        if IS_PYSIDE6:
            self.shortcut_tab = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)
        else:
            self.shortcut_tab = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self)

        self.shortcut_tab.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.shortcut_tab.activated.connect(self.show_module_menu)

        self.scene.selectionChanged.connect(self.workspace.sync_graph_to_list)

    def enterEvent(self, event):
        self.setFocus()
        # Cheap safety net: whenever the user's mouse enters the graph, make
        # sure the Guide Settings tab reflects whatever is actually in the
        # scene right now, rather than relying only on an explicit tab click.
        gw = getattr(self.workspace, 'graph_widget', None)
        if gw is not None and hasattr(gw, 'guide_settings_panel'):
            gw.guide_settings_panel.refresh_from_scene()
        super(NodeGraphView, self).enterEvent(event)

    def drawBackground(self, painter, rect):
        """A grid is always shown (not just once zoomed in) so it reads as
        an obvious visual reference for whether Ctrl+Scroll zoom is actually
        doing anything, at any zoom level."""
        super(NodeGraphView, self).drawBackground(painter, rect)
        grid_size = 25
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)

        thin_lines, thick_lines = [], []
        x = left
        while x < rect.right():
            line = QtCore.QLineF(x, rect.top(), x, rect.bottom())
            (thick_lines if x % (grid_size * 4) == 0 else thin_lines).append(line)
            x += grid_size
        y = top
        while y < rect.bottom():
            line = QtCore.QLineF(rect.left(), y, rect.right(), y)
            (thick_lines if y % (grid_size * 4) == 0 else thin_lines).append(line)
            y += grid_size

        painter.setPen(QtGui.QPen(QtGui.QColor("#2a2a2c"), 0))
        painter.drawLines(thin_lines)
        painter.setPen(QtGui.QPen(QtGui.QColor("#333336"), 0))
        painter.drawLines(thick_lines)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            angle = event.angleDelta().y()
            if angle == 0:
                return
            factor = 1.15 if angle > 0 else 1.0 / 1.15
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
            self.scale(factor, factor)
            event.accept()
            return
        super(NodeGraphView, self).wheelEvent(event)

    def keyPressEvent(self, event):
        # Ctrl+Z / Ctrl+Shift+Z (and the common Ctrl+Y redo alternative) -
        # undo/redo for the graph editor itself (nodes, wires, positions,
        # every Node-tab field). Only active while the graph view has
        # keyboard focus, so it doesn't fight a text field's own Ctrl+Z
        # while editing there (see ModuleGraphWidget.undo/redo).
        if event.key() == QtCore.Qt.Key_Z and (event.modifiers() & QtCore.Qt.ControlModifier):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                self.workspace.graph_widget.redo()
            else:
                self.workspace.graph_widget.undo()
            return
        if event.key() == QtCore.Qt.Key_Y and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.workspace.graph_widget.redo()
            return

        # Stage 27, request #2: standard copy/cut/paste keyboard shortcuts
        # for graph nodes, alongside the same actions on the right-click menu
        # (see contextMenuEvent). Only active while the graph view itself has
        # keyboard focus, same as Ctrl+Z above, so it doesn't fight a Node
        # tab text field's own Ctrl+C/V.
        if event.key() == QtCore.Qt.Key_C and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.copy_selected_nodes()
            return
        if event.key() == QtCore.Qt.Key_X and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.cut_selected_nodes()
            return
        if event.key() == QtCore.Qt.Key_V and (event.modifiers() & QtCore.Qt.ControlModifier):
            self.paste_nodes_from_clipboard()
            return

        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            selected = self.scene.selectedItems()
            if selected:
                self.workspace.graph_widget._push_undo_snapshot()
            for item in [i for i in selected if isinstance(i, RigNode)]:
                for wire in item.wires[:]:
                    self._remove_wire(wire)
                self.scene.removeItem(item)
            for wire in [i for i in selected if isinstance(i, RigWire)]:
                self._remove_wire(wire)
            self.workspace.refresh_module_list()
            self.workspace.graph_widget.update_attr_editor()

        elif event.key() == QtCore.Qt.Key_F:
            items = self.scene.selectedItems()
            if not items:
                items = [i for i in self.scene.items() if isinstance(i, RigNode)]
            if items:
                rect = items[0].sceneBoundingRect()
                for item in items[1:]:
                    rect = rect.united(item.sceneBoundingRect())
                rect.adjust(-100, -100, 100, 100)
                self.fitInView(rect, QtCore.Qt.KeepAspectRatio)
        else:
            super(NodeGraphView, self).keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            item = self.itemAt(event.pos())
            if not item:
                self.show_module_menu()
        super(NodeGraphView, self).mouseDoubleClickEvent(event)

    def _rig_node_at(self, view_pos):
        """itemAt() returns the topmost item under the cursor, which for a
        RigNode is usually its child QGraphicsTextItem label rather than the
        node's rect itself. Walk up to the owning RigNode."""
        item = self.itemAt(view_pos)
        while item is not None and not isinstance(item, RigNode):
            item = item.parentItem()
        return item

    def _port_at(self, view_pos, tolerance=11):
        """Return (RigNode, 'input'|'output') if `view_pos` (view/widget
        coordinates, e.g. straight from a mouse event) lands on or near one
        of that node's connector pins, else None. Checked before falling
        back to whole-node dragging so a press on a pin always starts a
        wire rather than moving the node."""
        best, best_dist = None, tolerance
        for item in self.scene.items():
            if not isinstance(item, RigNode):
                continue
            for local_pos, kind in ((item.output_port_pos(), "output"), (item.input_port_pos(), "input")):
                port_view_pos = self.mapFromScene(item.mapToScene(local_pos))
                dist = QtCore.QLineF(QtCore.QPointF(port_view_pos), QtCore.QPointF(view_pos)).length()
                if dist < best_dist:
                    best_dist = dist
                    best = (item, kind)
        return best

    def _remove_wire(self, wire):
        if wire.scene() is not None:
            self.scene.removeItem(wire)
        if wire in wire.source.wires: wire.source.wires.remove(wire)
        if wire in wire.dest.wires: wire.dest.wires.remove(wire)
        wire.dest.parent_local_target = None
        wire.dest.update_display()

    def _start_wire_drag(self, node):
        start = node.sceneBoundingRect()
        self._temp_wire_line = QtWidgets.QGraphicsPathItem(bezier_path(start, start))
        self._temp_wire_line.setPen(QtGui.QPen(QtGui.QColor("#ffcc66"), 2, QtCore.Qt.DashLine))
        self._temp_wire_line.setZValue(10)
        self.scene.addItem(self._temp_wire_line)

    # -- Node -> node wiring: drag from a node's connector pin (like any
    # standard node editor), or Ctrl+drag from anywhere on the node body --
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            port_hit = self._port_at(event.pos())
            # Only the output (right-side) pin starts a new connection drag -
            # matches the usual node-editor convention (drag OUT of an
            # output, drop ON an input). The input pin is left alone here so
            # clicking near it still just selects/moves the node normally;
            # detaching its existing wire is done via right-click-on-the-wire
            # or Delete on the selected wire instead.
            if port_hit is not None and port_hit[1] == "output":
                self._connect_source = port_hit[0]
                self._start_wire_drag(port_hit[0])
                return
            if event.modifiers() & QtCore.Qt.ControlModifier:
                item = self._rig_node_at(event.pos())
                if isinstance(item, RigNode):
                    self._connect_source = item
                    self._start_wire_drag(item)
                    return
                # Ctrl+drag starting on empty canvas pans the graph around
                # instead of rubber-band selecting - hand off to Qt's own
                # hand-drag panning for the rest of this drag.
                self._pan_active = True
                self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                super(NodeGraphView, self).mousePressEvent(event)
                return
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                # QGraphicsScene only natively toggles selection on Ctrl+click
                # (used above for wire-dragging here), and has no built-in
                # notion of Shift+click at all - so Shift+click-to-multi-select
                # a node has to be implemented by hand.
                item = self._rig_node_at(event.pos())
                if isinstance(item, RigNode):
                    item.setSelected(not item.isSelected())
                    return
        super(NodeGraphView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._connect_source is not None and self._temp_wire_line is not None:
            src_rect = self._connect_source.sceneBoundingRect()
            end_pos = self.mapToScene(event.pos())
            end_rect = QtCore.QRectF(end_pos, end_pos)
            self._temp_wire_line.setPath(bezier_path(src_rect, end_rect))
            return
        super(NodeGraphView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_active and event.button() == QtCore.Qt.LeftButton:
            super(NodeGraphView, self).mouseReleaseEvent(event)
            self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
            self._pan_active = False
            return
        if self._connect_source is not None:
            source = self._connect_source
            if self._temp_wire_line is not None:
                self.scene.removeItem(self._temp_wire_line)
                self._temp_wire_line = None
            self._connect_source = None

            port_hit = self._port_at(event.pos())
            target = port_hit[0] if port_hit is not None else self._rig_node_at(event.pos())
            if isinstance(target, RigNode) and target is not source:
                self.workspace.graph_widget._push_undo_snapshot()
                # Only one parent per node - drop any existing incoming wire.
                for wire in target.wires[:]:
                    if wire.dest is target:
                        self._remove_wire(wire)
                new_wire = RigWire(source, target)
                self.scene.addItem(new_wire)
                target.parent_local_target = None
                gw = self.workspace.graph_widget
                self._offer_attach_point(gw, source, target)
                new_wire.refresh_tooltip()
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            return
        super(NodeGraphView, self).mouseReleaseEvent(event)

    def _offer_attach_point(self, gw, parent_node, child_node, force=False):
        """If `parent_node` already has a built guide with more than one
        possible attachment locator (e.g. a spine's chest/neck/hip
        locators), ask which one `child_node` should parent under instead
        of always the whole guide root - the same choice you'd get dragging
        a component onto a specific locator in Shifter's own Guide Manager
        outliner. Silently keeps "whole guide root" when there's nothing
        (yet) to choose between - unless `force` is set (Stage 28: the
        wire right-click menu's "Change Attach Point..." always shows the
        menu, even with 0-1 real locators, since asking for it directly is
        a deliberate action, not an incidental side effect of a drag)."""
        points = gw._list_attach_points(parent_node)
        if len(points) < 2 and not force:
            return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        menu.addSection(f"Attach under which part of '{parent_node.display_title}'?")
        a_root = menu.addAction("(Whole Guide Root)")
        menu.addSeparator()
        actions = {}
        for label, long_name in points:
            actions[menu.addAction(label)] = long_name
        chosen = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if chosen is not None and chosen is not a_root:
            child_node.parent_local_target = actions.get(chosen)
        child_node.update_display()

    def contextMenuEvent(self, event):
        node = self._rig_node_at(event.pos())
        gw = self.workspace.graph_widget

        if isinstance(node, RigNode):
            # Stage 27, request #2: right-clicking a node that's already
            # part of a multi-selection acts on the whole selection (Copy/
            # Cut/Duplicate/Delete all of them); right-clicking an
            # unselected node selects just that one first - same convention
            # most node editors use.
            selected_nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
            if node not in selected_nodes:
                self.scene.clearSelection()
                node.setSelected(True)
                selected_nodes = [node]

            self._last_cursor_scene_pos = self.mapToScene(event.pos())
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            count = len(selected_nodes)
            suffix = f" ({count})" if count > 1 else ""
            a_copy = menu.addAction(f"📄 Copy Module{suffix}")
            a_cut = menu.addAction(f"✂ Cut Module{suffix}")
            a_dup = menu.addAction(f"🧬 Duplicate Module{suffix}")
            has_clip = bool(getattr(self.workspace.main_window, 'clipboard_node_data', None))
            a_paste = menu.addAction("📋 Paste Module(s)")
            a_paste.setEnabled(has_clip)
            a_delete = menu.addAction(f"🗑 Delete Module{suffix}")

            a_import = a_fix = a_constrain = a_skin = None
            if count == 1 and node.module_type == PLEBE_MODULE_TYPE:
                menu.addSeparator()
                a_import = menu.addAction("📥 Import Character FBX...")
                a_fix = menu.addAction("🔧 Fix FBX Naming")
                menu.addSeparator()
                a_constrain = menu.addAction("🔗 Constrain Character to Rig")
                a_skin = menu.addAction("🎨 Skin Character to Rig")

            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_copy:
                self.copy_selected_nodes()
            elif action == a_cut:
                self.cut_selected_nodes()
            elif action == a_dup:
                self.duplicate_selected_nodes()
            elif action == a_paste:
                self.paste_nodes_from_clipboard()
            elif action == a_delete:
                self._delete_nodes(selected_nodes)
            elif action == a_import:
                gw.plebe_import_fbx(node)
            elif action == a_fix:
                gw.plebe_fix_fbx_naming(node)
            elif action == a_constrain:
                gw.plebe_constrain_to_rig(node)
            elif action == a_skin:
                gw.plebe_skin_to_rig(node)
            return

        wire = self.itemAt(event.pos())
        if isinstance(wire, RigWire):
            gw = self.workspace.graph_widget
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            current = wire.dest.parent_local_target
            current_label = current.split("|")[-1] if current else "(Whole Guide Root)"
            a_attach = menu.addAction(f"🔗 Change Attach Point... (currently: {current_label})")
            menu.addSeparator()
            a_disconnect = menu.addAction("✂ Disconnect")
            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_disconnect:
                gw._push_undo_snapshot()
                self._remove_wire(wire)
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            elif action == a_attach:
                # Stage 28, request #2: an already-connected wire can have
                # its attach point changed directly, right-click here,
                # instead of needing to disconnect and redrag it just to
                # reach the same choice _offer_attach_point() already gives
                # at drop time - same underlying "all the options where else
                # this can parent" list, reached from one more place.
                gw._push_undo_snapshot()
                self._offer_attach_point(gw, wire.source, wire.dest, force=True)
                wire.refresh_tooltip()
                self.workspace.refresh_module_list()
                gw.update_attr_editor()
            return

        # Empty canvas: the only thing worth offering is Paste, if there's
        # something on the node clipboard to paste.
        if getattr(self.workspace.main_window, 'clipboard_node_data', None):
            self._last_cursor_scene_pos = self.mapToScene(event.pos())
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            a_paste = menu.addAction("📋 Paste Module(s)")
            action = menu.exec(event.globalPos()) if IS_PYSIDE6 else menu.exec_(event.globalPos())
            if action == a_paste:
                self.paste_nodes_from_clipboard()
            return

        super(NodeGraphView, self).contextMenuEvent(event)

    # -- Stage 27, request #2: copy/cut/paste/duplicate for graph nodes --
    def _copy_nodes_to_clipboard(self, nodes):
        """Serialize `nodes` (via the same serialize_node every other
        persistence path uses) plus every wire that connects two of THEM to
        each other, onto a clipboard shared with the rest of KRT
        (main_window.clipboard_node_data - a sibling of the panel clipboard
        Stage 22 added for the Rig Build Workspace). A wire to something
        OUTSIDE the copied set is deliberately dropped - a pasted copy
        starts with no external parent, same as any freshly created node."""
        gw = self.workspace.graph_widget
        node_set = set(nodes)
        node_dicts = [gw.serialize_node(n) for n in nodes]
        wire_pairs = [(w.source.uuid, w.dest.uuid) for n in nodes for w in n.wires
                      if w.dest is n and w.source in node_set]
        self.workspace.main_window.clipboard_node_data = {"nodes": node_dicts, "wires": wire_pairs}

    def copy_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        cmds.warning(f"Copied {len(nodes)} module(s) to clipboard.")

    def cut_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        self._delete_nodes(nodes)
        cmds.warning(f"Cut {len(nodes)} module(s) to clipboard.")

    def duplicate_selected_nodes(self):
        nodes = [i for i in self.scene.selectedItems() if isinstance(i, RigNode)]
        if not nodes:
            return
        self._copy_nodes_to_clipboard(nodes)
        self.paste_nodes_from_clipboard()

    def _delete_nodes(self, nodes):
        if not nodes:
            return
        self.workspace.graph_widget._push_undo_snapshot()
        for item in nodes:
            for wire in item.wires[:]:
                self._remove_wire(wire)
            self.scene.removeItem(item)
        self.workspace.refresh_module_list()
        self.workspace.graph_widget.update_attr_editor()

    def paste_nodes_from_clipboard(self):
        """Pastes at the current mouse position over the graph canvas -
        works identically whether triggered from the right-click menu (the
        cursor is already where the click happened) or Ctrl+V (wherever the
        mouse happens to be hovering)."""
        data = getattr(self.workspace.main_window, 'clipboard_node_data', None)
        if not data or not data.get("nodes"):
            return
        gw = self.workspace.graph_widget
        node_dicts = data["nodes"]

        min_x = min(nd["x"] for nd in node_dicts)
        min_y = min(nd["y"] for nd in node_dicts)
        anchor = self.mapToScene(self.mapFromGlobal(QtGui.QCursor.pos()))

        gw._push_undo_snapshot()
        self.scene.clearSelection()

        uuid_map = {}
        new_nodes = []
        for nd in node_dicts:
            nd2 = dict(nd)
            nd2["uuid"] = str(uuid.uuid4())  # a paste is always a brand-new node, never a duplicate id
            nd2["x"] = anchor.x() + (nd["x"] - min_x)
            nd2["y"] = anchor.y() + (nd["y"] - min_y)
            new_node = gw.deserialize_node(nd2)
            uuid_map[nd["uuid"]] = new_node
            self.scene.addItem(new_node)
            new_nodes.append(new_node)

        for src_uuid, dst_uuid in data.get("wires", []):
            src, dst = uuid_map.get(src_uuid), uuid_map.get(dst_uuid)
            if src and dst:
                self.scene.addItem(RigWire(src, dst))

        for n in new_nodes:
            n.setSelected(True)
        self.workspace.refresh_module_list()
        gw.update_attr_editor()
        cmds.warning(f"Pasted {len(new_nodes)} module(s).")

    def show_module_menu(self):
        all_modules = [PLEBE_SEARCH_LABEL, CUSTOM_SGT_SEARCH_LABEL, CUSTOM_SCRIPT_SEARCH_LABEL] + list_mgear_components()

        if len(all_modules) == 3:
            cmds.warning("No mGear Shifter components found. Is mGear installed/loaded?")
            return

        # Recently-added modules float to the top of the unfiltered list, so
        # the components this user actually reaches for aren't buried in a
        # long alphabetical catalog. Typing to search still searches
        # everything regardless of recency (see NodeSearchPopup.filter_list).
        recent_names = self.workspace.session_manager.get_recent_modules()
        recents = [m for m in recent_names if m in all_modules]
        rest = [m for m in all_modules if m not in recents]

        modules, header_labels = [], set()
        if recents:
            header_labels = {"── Recent ──", "── All Modules ──"}
            modules.append("── Recent ──")
            modules.extend(recents)
            modules.append("── All Modules ──")
        modules.extend(rest)

        cursor_pos = QtGui.QCursor.pos()
        view_pos = self.mapFromGlobal(cursor_pos)
        self._last_cursor_scene_pos = self.mapToScene(view_pos)

        self.search_popup = NodeSearchPopup(modules, self.create_node, header_labels=header_labels)
        self.search_popup.move(cursor_pos)
        self.search_popup.show()

    def create_node(self, module_name):
        if module_name == PLEBE_SEARCH_LABEL:
            self.create_plebe_node()
            return
        if module_name == CUSTOM_SGT_SEARCH_LABEL:
            self.create_custom_sgt_node()
            return
        if module_name == CUSTOM_SCRIPT_SEARCH_LABEL:
            self.create_custom_script_node()
            return

        result = cmds.confirmDialog(
            title='Select Module Side',
            message=f'Which side do you want to build {module_name} for?',
            button=['Left (L_)', 'Right (R_)', 'Center (C_)', 'Cancel'],
            defaultButton='Left (L_)',
            cancelButton='Cancel',
            dismissString='Cancel'
        )

        if result == 'Cancel': return

        side = "L" if "Left" in result else "R" if "Right" in result else "C"

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 60, pos.y() - 20, module_type=module_name, side=side)
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(module_name)
        self.workspace.refresh_module_list()

    def create_plebe_node(self):
        templates = list_plebe_templates()
        if not templates:
            cmds.warning("No mGear Plebe character templates found (mgear/shifter/plebes_templates).")
            return

        dialog = PlebeTemplateDialog(templates, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result != QtWidgets.QDialog.Accepted or not dialog.selected_path:
            return

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=PLEBE_MODULE_TYPE, side="C",
                           custom_name=f"Plebe: {dialog.selected_name}")
        new_node.plebe_template_path = dialog.selected_path
        new_node.plebe_template_name = dialog.selected_name
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(PLEBE_SEARCH_LABEL)
        self.workspace.refresh_module_list()

    def create_custom_sgt_node(self):
        """A node that imports a standalone .sgt guide template someone
        saved themselves - e.g. a stock component they hand-tweaked and
        re-exported from mGear's own Guide Manager - instead of drawing one
        of the catalog components. Same 'graft onto a parent' behavior as
        any other component once placed (see build_node_guide /
        _build_custom_sgt_guide)."""
        res = cmds.fileDialog2(fm=1, ff="mGear Guide Template (*.sgt);;All Files (*.*)",
                               caption="Choose a Custom Module .sgt File")
        if not res:
            return
        sgt_path = res[0]
        default_name = os.path.splitext(os.path.basename(sgt_path))[0]

        result = cmds.confirmDialog(
            title='Select Module Side',
            message=f'Which side do you want to build {default_name} for?',
            button=['Left (L_)', 'Right (R_)', 'Center (C_)', 'Cancel'],
            defaultButton='Left (L_)',
            cancelButton='Cancel',
            dismissString='Cancel'
        )
        if result == 'Cancel': return
        side = "L" if "Left" in result else "R" if "Right" in result else "C"

        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=CUSTOM_SGT_MODULE_TYPE, side=side,
                           custom_name=default_name)
        new_node.custom_sgt_path = sgt_path
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(CUSTOM_SGT_SEARCH_LABEL)
        self.workspace.refresh_module_list()

    def create_custom_script_node(self):
        """Stage 26: 'like custom module there should be a custom script
        module also where i dont need to load any module, i just wants to
        write custom script there' - no file picker, no side picker, no
        guide of any kind. Just a node whose entire purpose is the script
        attached to it (see CUSTOM_SCRIPT_MODULE_TYPE), so the script editor
        opens immediately after it's dropped - writing that script IS the
        only thing left to do with this node."""
        pos = getattr(self, '_last_cursor_scene_pos', QtCore.QPointF(0, 0))
        self.workspace.graph_widget._push_undo_snapshot()
        new_node = RigNode(pos.x() - 70, pos.y() - 20, module_type=CUSTOM_SCRIPT_MODULE_TYPE, side="C",
                           custom_name="Custom Script")
        new_node.update_display()
        self.scene.addItem(new_node)

        self.workspace.session_manager.add_recent_module(CUSTOM_SCRIPT_SEARCH_LABEL)
        self.workspace.refresh_module_list()

        all_nodes = [i for i in self.scene.items() if isinstance(i, RigNode) and i is not new_node]
        dialog = CustomScriptDialog(new_node, self.workspace.main_window, all_nodes=all_nodes)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            dialog.apply_to_node()
        self.workspace.graph_widget.update_attr_editor()


def _find_guide_root():
    """Return the long name of the scene's mGear guide root ("ismodel"
    transform), or None if no guide has been built yet.

    Defensive against attributeQuery raising on odd/ambiguous nodes (default
    cameras, referenced duplicates, etc.) - one bad node must never silently
    kill the whole Guide Settings panel.
    """
    for n in cmds.ls(type="transform") or []:
        try:
            if cmds.attributeQuery("ismodel", node=n, exists=True):
                long_names = cmds.ls(n, long=True)
                if long_names:
                    return long_names[0]
        except Exception:
            continue
    return None


class CustomStepListEditor(QtWidgets.QWidget):
    """Editor for one of mGear's pre/post Custom Step script lists.

    Serializes to the same "name | path" comma-separated legacy string
    format Shifter's own CustomStepListWidget falls back to reading (see
    mgear.shifter.custom_step_widget.CustomStepData / _parseLegacyFormat),
    so steps added here run correctly in a normal Shifter build and remain
    readable if the guide is later opened in mGear's own Custom Steps tab.
    A '*' prefix on a stored name marks a step disabled; that maps to the
    checkbox state here.
    """

    def __init__(self, parent=None):
        super(CustomStepListEditor, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet("background:#1e1e1e; border:1px solid #333;")
        self.list_widget.setFixedHeight(110)
        self.list_widget.itemChanged.connect(lambda _item: self._notify())
        layout.addWidget(self.list_widget)

        btn_row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("+ Add Script")
        btn_add.clicked.connect(self.add_script)
        btn_remove = QtWidgets.QPushButton("Remove")
        btn_remove.clicked.connect(self.remove_selected)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_remove)
        layout.addLayout(btn_row)

        # Set by the owning panel; called whenever the list content changes
        # so it can be written straight back onto the guide root's attr.
        self.on_change = None

    def add_script(self):
        res = cmds.fileDialog2(fm=4, ff="Python (*.py)")  # fm=4: multiple existing files
        if not res:
            return
        for path in res:
            name = os.path.splitext(os.path.basename(path))[0]
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            item.setData(QtCore.Qt.UserRole, path)
            item.setToolTip(path)
            self.list_widget.addItem(item)
        self._notify()

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._notify()

    def _notify(self):
        if callable(self.on_change):
            self.on_change()

    def to_legacy_string(self):
        parts = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(QtCore.Qt.UserRole) or ""
            prefix = "" if item.checkState() == QtCore.Qt.Checked else "*"
            parts.append(f"{prefix}{item.text()} | {path}")
        return ", ".join(parts)

    def load_from_string(self, data_string):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        stripped = (data_string or "").strip()
        if stripped.startswith("{"):
            # A v2 JSON blob written by Shifter's own Custom Steps tab
            # (groups, templates, ...) - too rich to round-trip here safely.
            # Leave it untouched rather than risk mangling it.
            item = QtWidgets.QListWidgetItem("<advanced step list - edit via mGear's own Custom Steps tab>")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.list_widget.addItem(item)
        else:
            for entry in stripped.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                active = True
                if entry.startswith("*"):
                    active = False
                    entry = entry[1:]
                name, _, path = entry.partition("|")
                item = QtWidgets.QListWidgetItem(name.strip())
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked if active else QtCore.Qt.Unchecked)
                item.setData(QtCore.Qt.UserRole, path.strip())
                item.setToolTip(path.strip())
                self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)


class GuideSettingsPanel(QtWidgets.QWidget):
    """The full mGear Shifter "Guide Settings" dialog for the guide root,
    reproduced tab-for-tab (Guide Settings / Custom Steps / Naming Rules /
    Blueprint) so switching over to Shifter's own UI is never required.

    These are rig-wide options (they live as attributes on the single
    "guide" root transform), not per-component, so this panel always edits
    whichever guide root currently exists in the scene rather than the
    selected graph node.
    """

    _COLOR_ROWS = [
        ("L", "L_color_fk", "L_color_ik"),
        ("C", "C_color_fk", "C_color_ik"),
        ("R", "R_color_fk", "R_color_ik"),
    ]

    def __init__(self, graph_widget):
        super(GuideSettingsPanel, self).__init__()
        self.graph_widget = graph_widget

        self._fields = {}  # attr name -> widget
        self._updating = False
        # Stage 31, request #3: set whenever a field is edited while there is
        # no guide root in the scene to write it to. Those edits live only in
        # the panel until a guide exists, so push_pending_to_scene() (called
        # right after Build Guides) knows it must push them onto the new
        # guide root rather than letting refresh_from_scene() pull mGear's
        # freshly-built defaults back over the top of them.
        self._pending_scene_push = False

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        self.lbl_status = QtWidgets.QLabel(
            "No mGear guide in the scene yet - these settings are still editable.\n"
            "They're saved with the rig, and applied to the guide as soon as you Build Guides."
        )
        self.lbl_status.setStyleSheet("color: #ffcc66; padding: 4px;")
        self.lbl_status.setWordWrap(True)
        root_layout.addWidget(self.lbl_status)

        btn_refresh = QtWidgets.QPushButton("🔄 Refresh from Scene")
        btn_refresh.clicked.connect(self.refresh_from_scene)
        root_layout.addWidget(btn_refresh)

        self.inner_tabs = QtWidgets.QTabWidget()
        self.inner_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #333; } QTabBar::tab { padding: 4px 6px; font-size: 11px; }"
        )
        root_layout.addWidget(self.inner_tabs)

        self.inner_tabs.addTab(self._make_scroll_page(self._build_guide_settings_page), "Guide Settings")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_custom_steps_page), "Custom Steps")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_naming_rules_page), "Naming Rules")
        self.inner_tabs.addTab(self._make_scroll_page(self._build_blueprint_page), "Blueprint")

        self.inner_tabs.setEnabled(False)

    # -- page / group scaffolding ------------------------------------------
    def _make_scroll_page(self, build_fn):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #252526; }")
        container = QtWidgets.QWidget()
        scroll.setWidget(container)
        page_layout = QtWidgets.QVBoxLayout(container)
        page_layout.setAlignment(QtCore.Qt.AlignTop)
        page_layout.setContentsMargins(4, 4, 4, 4)
        page_layout.setSpacing(10)
        build_fn(page_layout)
        return scroll

    def _group(self, target_layout, title):
        box = QtWidgets.QGroupBox(title)
        box.setStyleSheet(
            "QGroupBox { color: #2bb5a8; font-weight: bold; border: 1px solid #333; "
            "border-radius: 4px; margin-top: 8px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        layout = QtWidgets.QFormLayout(box)
        layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        target_layout.addWidget(box)
        return box, layout

    # -- field builders ------------------------------------------------------
    def _bool_field(self, layout, label, attr_name):
        chk = QtWidgets.QCheckBox()
        chk.toggled.connect(lambda v, a=attr_name: self._set_attr(a, v))
        layout.addRow(label, chk)
        self._fields[attr_name] = chk
        return chk

    def _string_field(self, layout, label, attr_name, with_browse=False):
        row = QtWidgets.QHBoxLayout()
        edit = QtWidgets.QLineEdit()
        edit.editingFinished.connect(lambda a=attr_name, e=edit: self._set_attr(a, e.text()))
        row.addWidget(edit)
        if with_browse:
            btn = QtWidgets.QPushButton("...")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _, a=attr_name, e=edit: self._browse_into(a, e))
            row.addWidget(btn)
        wrap = QtWidgets.QWidget(); wrap.setLayout(row)
        layout.addRow(label, wrap)
        self._fields[attr_name] = edit
        return edit

    def _enum_field(self, layout, label, attr_name, options):
        combo = QtWidgets.QComboBox()
        combo.addItems(options)
        combo.currentIndexChanged.connect(lambda idx, a=attr_name: self._set_attr(a, idx))
        layout.addRow(label, combo)
        self._fields[attr_name] = combo
        return combo

    def _int_field(self, layout, label, attr_name, minimum, maximum):
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.valueChanged.connect(lambda v, a=attr_name: self._set_attr(a, v))
        layout.addRow(label, spin)
        self._fields[attr_name] = spin
        return spin

    # -- Tab 1: Guide Settings ----------------------------------------------
    def _build_guide_settings_page(self, page_layout):
        self._build_rig_settings_group(page_layout)
        self._build_anim_channels_group(page_layout)
        self._build_base_rig_control_group(page_layout)
        self._build_skinning_group(page_layout)
        self._build_joint_settings_group(page_layout)
        self._build_data_collector_group(page_layout)
        self._build_color_settings_group(page_layout)

    def _build_rig_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Rig Settings")
        self._string_field(layout, "Rig Name", "rig_name")
        self._enum_field(layout, "Debug Mode", "mode", ["Final", "WIP"])
        self._enum_field(layout, "Guide Build Steps", "step",
                         ["All Steps", "Objects", "Properties", "Operators", "Connect", "Joints", "Finalize"])

    def _build_anim_channels_group(self, page_layout):
        box, layout = self._group(page_layout, "Animation Channels Settings")
        self._bool_field(layout, "Add Internal Proxy Channels", "proxyChannels")
        self._bool_field(layout, "Use Classic Channel Names", "classicChannelNames")
        self._bool_field(layout, "Use Component Instance Name for Attributes Prefix", "attrPrefixName")

    def _build_base_rig_control_group(self, page_layout):
        box, layout = self._group(page_layout, "Base Rig Control")
        self._bool_field(layout, "Use World Ctl or Custom Name", "worldCtl")
        self._string_field(layout, "Name", "world_ctl_name")

    def _build_skinning_group(self, page_layout):
        box, layout = self._group(page_layout, "Skinning Settings")
        self._bool_field(layout, "Import Skin", "importSkin")
        self._string_field(layout, "Skin Path", "skin", with_browse=True)

    def _build_joint_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Joint Settings")
        self._bool_field(layout, "Separated Joint Structure", "joint_rig")
        self._bool_field(layout, "Force World Oriented", "joint_worldOri")
        self._bool_field(layout, "Force uniform scaling in all joints", "force_uniScale")
        self._bool_field(layout, "Connect to existing joints", "connect_joints")
        self._bool_field(layout, "Force Segment Scale Compensate", "force_SSC")

    def _build_data_collector_group(self, page_layout):
        box, layout = self._group(page_layout, "Post Build Data Collector")
        self._bool_field(layout, "Collect Data on External File", "data_collector")
        self._string_field(layout, "Data Path", "data_collector_path", with_browse=True)
        self._bool_field(layout, "Collect Data Embedded on Root/Custom Joint", "data_collector_embedded")
        self._string_field(layout, "Custom Joint or Transform", "data_collector_embedded_custom_joint")

    def _build_color_settings_group(self, page_layout):
        box, layout = self._group(page_layout, "Color Settings")
        self._bool_field(layout, "Use RGB Colors", "Use_RGB_Color")
        for side_label, fk_attr, ik_attr in self._COLOR_ROWS:
            self._int_field(layout, f"{side_label}  FK", fk_attr, 0, 31)
            self._int_field(layout, f"{side_label}  IK", ik_attr, 0, 31)

    # -- Tab 2: Custom Steps --------------------------------------------------
    def _build_custom_steps_page(self, page_layout):
        box, form = self._group(page_layout, "Pre Custom Steps")
        self._bool_field(form, "Run Pre Custom Steps", "doPreCustomStep")
        self.pre_step_editor = CustomStepListEditor()
        self.pre_step_editor.on_change = lambda: self._set_attr("preCustomStep", self.pre_step_editor.to_legacy_string())
        form.addRow(self.pre_step_editor)

        box2, form2 = self._group(page_layout, "Post Custom Steps")
        self._bool_field(form2, "Run Post Custom Steps", "doPostCustomStep")
        self.post_step_editor = CustomStepListEditor()
        self.post_step_editor.on_change = lambda: self._set_attr("postCustomStep", self.post_step_editor.to_legacy_string())
        form2.addRow(self.post_step_editor)

        hint = QtWidgets.QLabel(
            "Scripts run top to bottom; uncheck to skip without removing.\n"
            "This is mGear's own rig-wide Custom Steps mechanism - separate from "
            "the per-module script on the Node tab, which only runs for one component."
        )
        hint.setStyleSheet("color:#888; font-size:10px;")
        hint.setWordWrap(True)
        page_layout.addWidget(hint)

    # -- Tab 3: Naming Rules --------------------------------------------------
    def _build_naming_rules_page(self, page_layout):
        box, layout = self._group(page_layout, "Naming Rules")
        self._string_field(layout, "Ctl Name Rule", "ctl_name_rule")
        self._string_field(layout, "Joint Name Rule", "joint_name_rule")
        self._string_field(layout, "Ctl Name Extension", "ctl_name_ext")
        self._string_field(layout, "Joint Name Extension", "joint_name_ext")
        self._enum_field(layout, "Ctl Description Case", "ctl_description_letter_case",
                         ["Default", "Upper Case", "Lower Case", "Capitalization"])
        self._enum_field(layout, "Joint Description Case", "joint_description_letter_case",
                         ["Default", "Upper Case", "Lower Case", "Capitalization"])
        self._int_field(layout, "Ctl Index Padding", "ctl_index_padding", 0, 99)
        self._int_field(layout, "Joint Index Padding", "joint_index_padding", 0, 99)

        box2, layout2 = self._group(page_layout, "Side Names (Controls)")
        self._string_field(layout2, "Left", "side_left_name")
        self._string_field(layout2, "Right", "side_right_name")
        self._string_field(layout2, "Center", "side_center_name")

        box3, layout3 = self._group(page_layout, "Side Names (Joints)")
        self._string_field(layout3, "Left", "side_joint_left_name")
        self._string_field(layout3, "Right", "side_joint_right_name")
        self._string_field(layout3, "Center", "side_joint_center_name")

    # -- Tab 4: Blueprint ------------------------------------------------------
    def _build_blueprint_page(self, page_layout):
        box, layout = self._group(page_layout, "Blueprint Guide")
        self._bool_field(layout, "Use Blueprint", "use_blueprint")
        self._string_field(layout, "Blueprint Path", "blueprint_path", with_browse=True)

        box2, layout2 = self._group(page_layout, "Override Sections (use local values instead of blueprint)")
        self._bool_field(layout2, "Rig Settings", "override_rig_settings")
        self._bool_field(layout2, "Animation Channels", "override_anim_channels")
        self._bool_field(layout2, "Base Rig Control", "override_base_rig_control")
        self._bool_field(layout2, "Skinning", "override_skinning")
        self._bool_field(layout2, "Joint Settings", "override_joint_settings")
        self._bool_field(layout2, "Data Collector", "override_data_collector")
        self._bool_field(layout2, "Color Settings", "override_color_settings")
        self._bool_field(layout2, "Naming Rules", "override_naming_rules")
        self._bool_field(layout2, "Pre Custom Steps", "override_pre_custom_steps")
        self._bool_field(layout2, "Post Custom Steps", "override_post_custom_steps")

    # -- scene <-> UI sync --------------------------------------------------
    def _browse_into(self, attr_name, line_edit):
        res = cmds.fileDialog2(fm=1, ff="All Files (*.*)")
        if res:
            line_edit.setText(res[0])
            self._set_attr(attr_name, res[0])

    def _set_attr(self, attr_name, value):
        if self._updating:
            return
        root = _find_guide_root()
        if not root:
            # Stage 31, request #3: no guide to write to yet - the edit still
            # counts, it just has to wait for one. Remember that so it gets
            # pushed at build time instead of being silently dropped.
            self._pending_scene_push = True
            return
        try:
            plug = f"{root}.{attr_name}"
            if isinstance(value, bool):
                cmds.setAttr(plug, value)
            elif isinstance(value, str):
                cmds.setAttr(plug, value, type="string")
            else:
                cmds.setAttr(plug, value)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Could not set guide option '{attr_name}' - see Script Editor.")

    def get_settings_dict(self):
        """Snapshot of every field this panel manages, as plain JSON-safe
        values - independent of whether a guide root currently exists in
        the scene. Used by the standalone Graph Config JSON export."""
        data = {}
        for attr_name, widget in self._fields.items():
            if isinstance(widget, QtWidgets.QCheckBox):
                data[attr_name] = widget.isChecked()
            elif isinstance(widget, QtWidgets.QLineEdit):
                data[attr_name] = widget.text()
            elif isinstance(widget, QtWidgets.QComboBox):
                data[attr_name] = widget.currentIndex()
            elif isinstance(widget, QtWidgets.QSpinBox):
                data[attr_name] = widget.value()
        data["preCustomStep"] = self.pre_step_editor.to_legacy_string()
        data["postCustomStep"] = self.post_step_editor.to_legacy_string()
        return data

    def apply_settings_dict(self, data):
        """Inverse of get_settings_dict(): loads values into the UI, then -
        if a guide root actually exists in the scene right now - pushes
        them onto its real Maya attributes too, same as editing each field
        by hand would. If no guide exists yet, the UI still reflects the
        loaded values so 'Refresh from Scene' (or reloading this JSON) can
        push them once a guide has been built."""
        if not isinstance(data, dict):
            return
        self._updating = True
        try:
            for attr_name, widget in self._fields.items():
                if attr_name not in data:
                    continue
                value = data[attr_name]
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(value or "")
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(int(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))
            if "preCustomStep" in data:
                self.pre_step_editor.load_from_string(data["preCustomStep"] or "")
            if "postCustomStep" in data:
                self.post_step_editor.load_from_string(data["postCustomStep"] or "")
        except Exception:
            traceback.print_exc()
        finally:
            self._updating = False

        root = _find_guide_root()
        if not root:
            cmds.warning("Guide Settings loaded into the panel, but no guide root exists in the "
                         "scene yet - build a guide, then reload this JSON (or edit a field by "
                         "hand) to push these values onto it.")
            return
        for attr_name, value in data.items():
            if attr_name in self._fields:
                self._set_attr(attr_name, value)
        if "preCustomStep" in data:
            self._set_attr("preCustomStep", data["preCustomStep"] or "")
        if "postCustomStep" in data:
            self._set_attr("postCustomStep", data["postCustomStep"] or "")

    def push_pending_to_scene(self):
        """Stage 31, request #3: push settings the user edited while no guide
        existed onto the guide that has just been built.

        Called right after Build Guides and BEFORE refresh_from_scene(),
        because refresh reads the scene into the panel - which, on a
        just-built guide, would replace the rigger's settings with mGear's
        defaults, quietly losing them. Returns True if anything was pushed."""
        if not self._pending_scene_push:
            return False
        root = _find_guide_root()
        if not root:
            return False
        data = self.get_settings_dict()
        for attr_name, value in data.items():
            self._set_attr(attr_name, value)
        self._pending_scene_push = False
        cmds.warning("[KRT] Applied your Guide Settings to the newly built guide.")
        return True

    def refresh_from_scene(self):
        try:
            root = _find_guide_root()
        except Exception:
            traceback.print_exc()
            self.lbl_status.setText("Could not check the scene for a guide - see Script Editor.")
            self.lbl_status.setStyleSheet("color: #ff6666; padding: 4px;")
            self.inner_tabs.setEnabled(False)
            return

        if not root:
            # Stage 31, request #3: "i am again not able to change these
            # setting". This used to disable the entire tab strip whenever
            # no guide existed in the scene, which made every Guide Setting
            # unreachable until after a build - even though these values are
            # a property of the RIG, are saved in the guides JSON and the KRT
            # session JSON, and are exactly the sort of thing a rigger sets
            # up BEFORE building anything. They stay editable now: edits are
            # held in the panel, and pushed onto the guide root the moment
            # one exists (see push_pending_to_scene(), called right after
            # Build Guides).
            self.lbl_status.setText(
                "No mGear guide in the scene yet - these settings are still editable.\n"
                "They're saved with the rig, and applied to the guide as soon as you Build Guides.")
            self.lbl_status.setStyleSheet("color: #ffcc66; padding: 4px;")
            self.inner_tabs.setEnabled(True)
            return

        self.lbl_status.setText(f"Editing guide root: {root.split('|')[-1]}")
        self.lbl_status.setStyleSheet("color: #2bb5a8; padding: 4px;")
        self.inner_tabs.setEnabled(True)

        self._updating = True
        try:
            for attr_name, widget in self._fields.items():
                if not cmds.attributeQuery(attr_name, node=root, exists=True):
                    continue
                value = cmds.getAttr(f"{root}.{attr_name}")
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(value or "")
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(int(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))

            if cmds.attributeQuery("preCustomStep", node=root, exists=True):
                self.pre_step_editor.load_from_string(cmds.getAttr(f"{root}.preCustomStep") or "")
            if cmds.attributeQuery("postCustomStep", node=root, exists=True):
                self.post_step_editor.load_from_string(cmds.getAttr(f"{root}.postCustomStep") or "")
        except Exception:
            traceback.print_exc()
            self.lbl_status.setText(f"Editing guide root: {root.split('|')[-1]}  (some fields failed to load - see Script Editor)")
            self.lbl_status.setStyleSheet("color: #ffaa33; padding: 4px;")
        finally:
            self._updating = False


class ModuleGraphWidget(QtWidgets.QWidget):
    def __init__(self, workspace):
        super(ModuleGraphWidget, self).__init__()
        self.workspace = workspace

        # Graph-editor undo/redo (Ctrl+Z / Ctrl+Shift+Z) - a stack of whole
        # graph-state snapshots (the same dict get_graph_config_data()/
        # _apply_graph_config_data() already use for JSON export/import and
        # Save/Load Guides), NOT Maya's own undo queue - this only covers
        # the graph editor's own nodes/wires/positions/Node-tab fields, not
        # actual Maya scene changes from Build Guides/Modules (those already
        # go through Maya's native undo via cmds.undoInfo chunks elsewhere).
        # See _push_undo_snapshot()/undo()/redo() further down.
        self._undo_stack = []
        self._redo_stack = []
        self._max_undo_states = 60

        # Stage 28, request #1: "Attach Under" was re-walking a parent's
        # ENTIRE built guide hierarchy (cmds.listRelatives(allDescendents))
        # from scratch every single time ANY node got selected in the graph
        # (update_attr_editor -> _refresh_attach_point_combo ->
        # _list_attach_points ran unconditionally, regardless of whether the
        # parent or its guide had actually changed since the last look) - on
        # a full biped guide (100+ locators) that's a real, repeated cost for
        # something that's usually unchanged between clicks. Cache the
        # resolved (label, long_name) list per guide-root long name; a cache
        # hit skips the Maya query entirely. See _list_attach_points() and
        # _invalidate_attach_points_cache().
        self._attach_points_cache = {}

        # Stage 30, request #1: "i want more [attach points]... i am tired
        # to find where... it first build module in maya then it check
        # where need to parent." A per-component-TYPE cache of guide-locator
        # names parsed straight out of that component's own guide.py source
        # (mgear.shifter_classic_components.<type>/shifter_epic_components.
        # <type>) - completely static, no Maya scene interaction at all, so
        # it's available for the Attach Under combo / drag-drop popup BEFORE
        # that specific node's guide has ever been built, not just after.
        # See _static_locator_names_for_type() / _list_attach_points().
        self._type_locator_static_cache = {}
        self._suspend_undo_capture = False
        # Coalesces a burst of rapid edits (e.g. every keystroke in Custom
        # Name) into a single undo step - only the FIRST edit since the
        # last selection change/undo/redo actually pushes a snapshot.
        self._edit_snapshot_pending = True

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Guide Path:"))
        default_path = os.path.join(os.path.expanduser('~'), "kleem_guide.json").replace("\\", "/")
        self.path_field = QtWidgets.QLineEdit(default_path)
        top_layout.addWidget(self.path_field)

        # Stage 35: matches the Rig Build workspace panels' own field + Load
        # + "..." layout (widgets.py's SortablePanel) instead of a row of
        # always-visible buttons. Browse/Export Config/Import Config/Save
        # Guides all moved into the "..." menu (show_guide_path_menu) below -
        # Load is the only action common enough to stay a dedicated button.
        btn_load = QtWidgets.QPushButton("Load Guides")
        btn_load.setStyleSheet("background-color: #998033; font-weight: bold;")
        btn_load.setToolTip(
            "Rebuild the graph's nodes/wires/settings from the JSON at the path above. "
            "Doesn't touch the Maya scene - use 'Build Guides' afterward to actually draw guides."
        )
        btn_load.clicked.connect(self.load_all_guides)

        btn_guide_dots = QtWidgets.QPushButton("...")
        btn_guide_dots.setFixedWidth(30)
        btn_guide_dots.setToolTip(
            "More Options: Browse, Save Guide (Overwrite/New Version), Switch Version - "
            "same save/version pattern as the Rig Build workspace panels."
        )
        btn_guide_dots.clicked.connect(self.show_guide_path_menu)

        top_layout.addWidget(btn_load)
        top_layout.addWidget(btn_guide_dots)
        self.layout.addLayout(top_layout)

        hint = QtWidgets.QLabel(
            "Tab or double-click empty canvas: add an mGear component  •  "
            "Drag from a node's ● pin (or Ctrl+Drag from anywhere on it) → drop on another node: parent/child connection  •  "
            "Shift+Click a node: add/remove it from selection  •  "
            "Ctrl+Drag empty canvas: pan the graph  •  "
            "Right-click a wire to change its Attach Point or disconnect it (Delete also disconnects)  •  "
            "Ctrl+Scroll: zoom  •  "
            "✓ built guide, 🖉 has a custom script, ⚠ script error  •  "
            "\"Guide Settings\" tab: rig-wide Shifter options"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        self.layout.addWidget(hint)

        # =====================================================
        # Stage 31, request #1: live "guide placement changed" indicator
        # =====================================================
        # A round light sitting at the top-left of the canvas: GREEN while
        # every built guide still sits where it was last recorded, RED the
        # moment any of them has been moved in the Maya scene. Clicking it
        # records wherever they sit now, so a later rebuild redraws them in
        # exactly those places. See _refresh_position_watch() /
        # on_position_watch_clicked() / _node_position_state() below.
        watch_row = QtWidgets.QHBoxLayout()
        watch_row.setContentsMargins(0, 0, 0, 0)
        watch_row.setSpacing(6)

        self.btn_pos_watch = QtWidgets.QPushButton("●")
        self.btn_pos_watch.setFixedSize(22, 22)
        self.btn_pos_watch.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_pos_watch.clicked.connect(self.on_position_watch_clicked)
        watch_row.addWidget(self.btn_pos_watch)

        self.lbl_pos_watch = QtWidgets.QLabel("")
        self.lbl_pos_watch.setStyleSheet("color: #888; font-size: 11px; border: none;")
        watch_row.addWidget(self.lbl_pos_watch)
        watch_row.addStretch()
        self.layout.addLayout(watch_row)

        # Live state for the watcher. _pos_baseline lives on each RigNode
        # (memory only, never persisted) and records where a guide sat right
        # after it was built - so "has anything moved since the build?" can
        # be answered even before the user has ever recorded anything.
        self._pos_watch_dirty = False
        self._pos_watch_suspended = False
        self._pos_watch_timer = QtCore.QTimer(self)
        self._pos_watch_timer.setInterval(1500)
        self._pos_watch_timer.timeout.connect(self._refresh_position_watch)
        self._pos_watch_timer.start()
        self._set_position_watch_ui(False, 0)

        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.graph_view = NodeGraphView(self.workspace)
        self.split.addWidget(self.graph_view)

        self.attr_frame = QtWidgets.QFrame()
        attr_layout = QtWidgets.QVBoxLayout(self.attr_frame)
        attr_layout.setAlignment(QtCore.Qt.AlignTop)

        attr_layout.addWidget(QtWidgets.QLabel("<b>NODE EDITOR</b>"))

        self.lbl_node_type = QtWidgets.QLabel("Module Type: N/A")
        self.lbl_node_type.setStyleSheet("color: #aaa; border: none;")
        attr_layout.addWidget(self.lbl_node_type)

        attr_layout.addWidget(QtWidgets.QLabel("Custom Name:"))
        self.edit_custom_name = QtWidgets.QLineEdit()
        self.edit_custom_name.textChanged.connect(self.on_attr_changed)
        attr_layout.addWidget(self.edit_custom_name)

        attr_layout.addWidget(QtWidgets.QLabel("Side:"))
        self.combo_side = QtWidgets.QComboBox()
        self.combo_side.addItems(["L", "R", "C"])
        self.combo_side.currentTextChanged.connect(self.on_attr_changed)
        attr_layout.addWidget(self.combo_side)

        # Stage 28, request #4: everything below used to be one long
        # flat scroll of stacked sections (Parent/Attach, Character
        # Template, Custom Module, Main Settings, build/script state) -
        # unorganized once a real component's full Main Settings section
        # (Stage 27) was added on top of everything else. Split it into its
        # own inner tab strip instead, same pattern GuideSettingsPanel
        # already uses for ITS four tabs - each section gets its own full-
        # height page instead of fighting the others for scroll space, and
        # nothing about any individual field/widget/connection below
        # changed - they just get added to a different page's layout than
        # before.
        self.node_inner_tabs = QtWidgets.QTabWidget()
        self.node_inner_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #333; } QTabBar::tab { padding: 4px 6px; font-size: 11px; }")

        def _node_tab_page():
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: #252526; }")
            container = QtWidgets.QWidget()
            scroll.setWidget(container)
            page_layout = QtWidgets.QVBoxLayout(container)
            page_layout.setAlignment(QtCore.Qt.AlignTop)
            page_layout.setContentsMargins(4, 4, 4, 4)
            page_layout.setSpacing(8)
            return scroll, page_layout

        hierarchy_scroll, hierarchy_layout = _node_tab_page()
        main_settings_scroll, main_settings_layout = _node_tab_page()
        template_scroll, template_layout = _node_tab_page()
        scripts_scroll, scripts_layout = _node_tab_page()

        self.node_inner_tabs.addTab(hierarchy_scroll, "Hierarchy")
        self.node_inner_tabs.addTab(main_settings_scroll, "Main Settings")
        self.node_inner_tabs.addTab(template_scroll, "Template")
        self.node_inner_tabs.addTab(scripts_scroll, "Scripts")

        parent_label = QtWidgets.QLabel("Parent Module:")
        parent_label.setStyleSheet("margin-top: 8px;")
        hierarchy_layout.addWidget(parent_label)
        self.combo_parent = QtWidgets.QComboBox()
        self.combo_parent.setToolTip(
            "Which module this one parents under in the mGear guide hierarchy "
            "(e.g. parent an arm under a clavicle, or a chest add-on under the spine).\n"
            "Same effect as Ctrl+Drag one node onto another on the canvas."
        )
        self.combo_parent.currentIndexChanged.connect(self.on_parent_combo_changed)
        hierarchy_layout.addWidget(self.combo_parent)

        attach_label = QtWidgets.QLabel("Attach Under (on parent's guide):")
        hierarchy_layout.addWidget(attach_label)
        attach_row = QtWidgets.QHBoxLayout()
        self.combo_attach_point = QtWidgets.QComboBox()
        self.combo_attach_point.setToolTip(
            "Which specific guide locator on the parent module to attach under "
            "(e.g. the chest or a specific spine section), instead of always the\n"
            "parent's whole guide root. Only has choices once the parent's guide "
            "has actually been built - options reflect whatever locators mGear\n"
            "drew for that component, all the way down (every guide in a full "
            "biped, not just its top-level pieces). Same choice offered right "
            "after dragging a connection when more than one is available.\n"
            "Type to search/filter the list - a full biped guide can have "
            "dozens of locators."
        )
        # Stage 26, request #1: a full biped guide can have dozens of
        # locators (arm_L0_crv, arm_L0_eff, arm_L0_elbow, ...) - typing to
        # filter is much faster than scrolling a long dropdown. Making the
        # combo editable with a "contains" QCompleter gives it a real search
        # box while it's still fundamentally a fixed-choice dropdown: typing
        # narrows the popup list, but only actually picking one of the real
        # entries (click, or Enter/Tab on a completer match) changes the
        # attach point - see _snap_attach_point_text, which reverts any
        # leftover typed text that isn't an exact item back to the current
        # selection once the field loses focus.
        self.combo_attach_point.setEditable(True)
        self.combo_attach_point.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.combo_attach_point.lineEdit().setPlaceholderText("Type to search...")
        attach_completer = QtWidgets.QCompleter(self.combo_attach_point)
        attach_completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        attach_completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        attach_completer.setFilterMode(QtCore.Qt.MatchContains)
        self.combo_attach_point.setCompleter(attach_completer)
        self.combo_attach_point.lineEdit().editingFinished.connect(self._snap_attach_point_text)
        self.combo_attach_point.currentIndexChanged.connect(self.on_attach_point_combo_changed)
        attach_row.addWidget(self.combo_attach_point)
        hierarchy_layout.addLayout(attach_row)

        # Only shown for a Plebe (character-template) node.
        self.plebe_group = QtWidgets.QWidget()
        plebe_layout = QtWidgets.QVBoxLayout(self.plebe_group)
        plebe_layout.setContentsMargins(0, 8, 0, 0)
        plebe_layout.setSpacing(4)
        plebe_layout.addWidget(QtWidgets.QLabel("<b>Character Template</b>"))
        self.lbl_plebe_template = QtWidgets.QLabel("None")
        self.lbl_plebe_template.setStyleSheet("color: #2bb5a8;")
        self.lbl_plebe_template.setWordWrap(True)
        plebe_layout.addWidget(self.lbl_plebe_template)
        btn_change_template = QtWidgets.QPushButton("Change Template...")
        btn_change_template.clicked.connect(self.change_selected_node_template)
        plebe_layout.addWidget(btn_change_template)
        self.chk_align_guides = QtWidgets.QCheckBox("Align Guides Automatically")
        self.chk_align_guides.setToolTip(
            "When Build Guides runs this node, also snap the biped guide onto\n"
            "the imported character using this template's mapping. Turn off to\n"
            "import the guide only and align it by hand."
        )
        self.chk_align_guides.toggled.connect(self.on_attr_changed)
        plebe_layout.addWidget(self.chk_align_guides)

        # Stage 31: sits directly under "Align Guides Automatically" because
        # that's the pairing that actually matters - align works out where the
        # guides should go, and replaying a stored placement straight
        # afterwards overrides it. See _make_apply_positions_row().
        self.chk_apply_positions_plebe, self.apply_positions_row_plebe = \
            self._make_apply_positions_row()
        plebe_layout.addWidget(self.apply_positions_row_plebe)

        # Stage 19: Fan Joint / Stretchy Joint, each independently toggled
        # (default ON) and independently editable - see run_node_auto_scripts.
        fan_row = QtWidgets.QHBoxLayout()
        self.chk_fan_joint = QtWidgets.QCheckBox("Fan Joint")
        self.chk_fan_joint.setToolTip(
            "Runs the studio's Fan Joint setup script right after this node's "
            "rig is actually built (same timing as an 'after Build Modules' "
            "custom script). Edit the script itself with the button on the right."
        )
        self.chk_fan_joint.toggled.connect(self.on_attr_changed)
        fan_row.addWidget(self.chk_fan_joint)
        fan_row.addStretch()
        btn_edit_fan = QtWidgets.QPushButton("✏ Edit Script...")
        btn_edit_fan.setToolTip("Edit the Fan Joint script attached to this node.")
        btn_edit_fan.clicked.connect(self.edit_fan_joint_script)
        fan_row.addWidget(btn_edit_fan)
        plebe_layout.addLayout(fan_row)

        stretchy_row = QtWidgets.QHBoxLayout()
        self.chk_stretchy_joint = QtWidgets.QCheckBox("Stretchy Joint")
        self.chk_stretchy_joint.setToolTip(
            "Runs the studio's Stretchy Joint setup script right after this node's "
            "rig is actually built (same timing as an 'after Build Modules' "
            "custom script). Edit the script itself with the button on the right."
        )
        self.chk_stretchy_joint.toggled.connect(self.on_attr_changed)
        stretchy_row.addWidget(self.chk_stretchy_joint)
        stretchy_row.addStretch()
        btn_edit_stretchy = QtWidgets.QPushButton("✏ Edit Script...")
        btn_edit_stretchy.setToolTip("Edit the Stretchy Joint script attached to this node.")
        btn_edit_stretchy.clicked.connect(self.edit_stretchy_joint_script)
        stretchy_row.addWidget(btn_edit_stretchy)
        plebe_layout.addLayout(stretchy_row)

        lib_label = QtWidgets.QLabel("Control Shapes Library:")
        lib_label.setStyleSheet("margin-top: 6px;")
        lib_tooltip = (
            "A .ma/.mb file of \"*_controlBuffer\" curves (mGear's own hand-authored "
            "control-shape convention, matching this biped's UI control names - "
            "legUI_L0_ctl, spineUI_C0_ctl, etc). Automatically merged into THIS node's "
            "guide controllers_org right after its guide is drawn, so every matching "
            "control comes out shaped from this file instead of the default biped "
            "icon shapes. Per-Plebe-node setting - leave blank to skip it. Not shown "
            "for regular Shifter component modules, since their control names won't "
            "match a biped library like this anyway."
        )
        lib_label.setToolTip(lib_tooltip)
        plebe_layout.addWidget(lib_label)
        lib_row = QtWidgets.QHBoxLayout()
        self.edit_control_shapes_lib = QtWidgets.QLineEdit()
        self.edit_control_shapes_lib.setToolTip(lib_tooltip)
        self.edit_control_shapes_lib.editingFinished.connect(self.on_attr_changed)
        lib_row.addWidget(self.edit_control_shapes_lib)
        btn_browse_lib = QtWidgets.QPushButton("...")
        btn_browse_lib.setFixedWidth(30)
        btn_browse_lib.setToolTip("Browse for a control-shapes library .ma/.mb file")
        btn_browse_lib.clicked.connect(self.browse_control_shapes_library)
        lib_row.addWidget(btn_browse_lib)
        plebe_layout.addLayout(lib_row)

        template_layout.addWidget(self.plebe_group)
        self.plebe_group.setVisible(False)

        # Only shown for a Custom Module (.sgt file) node.
        self.sgt_group = QtWidgets.QWidget()
        sgt_layout = QtWidgets.QVBoxLayout(self.sgt_group)
        sgt_layout.setContentsMargins(0, 8, 0, 0)
        sgt_layout.setSpacing(4)
        sgt_layout.addWidget(QtWidgets.QLabel("<b>Custom .sgt File</b>"))
        self.lbl_sgt_path = QtWidgets.QLabel("None")
        self.lbl_sgt_path.setStyleSheet("color: #2bb5a8;")
        self.lbl_sgt_path.setWordWrap(True)
        sgt_layout.addWidget(self.lbl_sgt_path)
        btn_change_sgt = QtWidgets.QPushButton("Change File...")
        btn_change_sgt.setToolTip(
            "Pick a different mGear partial guide template (.sgt) for this node - "
            "e.g. a stock Shifter component you hand-modified and re-exported from "
            "Guide Manager."
        )
        btn_change_sgt.clicked.connect(self.change_selected_node_sgt_path)
        sgt_layout.addWidget(btn_change_sgt)
        template_layout.addWidget(self.sgt_group)
        self.sgt_group.setVisible(False)
        template_layout.addStretch()

        # Stage 27, request #1: mGear's own per-component "Main Settings" -
        # the fields shown in mGear's own Settings dialog (Component Index/
        # Connector, Joint Settings, Channels Host, Custom Controllers
        # Group, Color Settings) - mirrored directly here so that dialog
        # never needs opening. Only shown for a real Shifter catalog
        # component (not Plebe/Custom Module/Custom Script).
        # Stage 31, request #2: "i am not able to see these two component
        # setting and the Main setting when i am selecting any module".
        # The mGear Settings button used to live INSIDE component_group,
        # which is hidden for anything that isn't a plain Shifter catalog
        # component - so selecting a Custom Module (.sgt) node showed a
        # completely blank "Main Settings" tab, with no button and no
        # explanation, even when that node HAD a real built component guide
        # that mGear's own Settings window would happily open. It now lives
        # in its own group, shown for ANY node whose built guide is a real
        # Shifter component, independent of the KRT field mirror below.
        self.mgear_settings_group = QtWidgets.QWidget()
        mgear_layout = QtWidgets.QVBoxLayout(self.mgear_settings_group)
        mgear_layout.setContentsMargins(0, 8, 0, 0)
        mgear_layout.setSpacing(4)
        mgear_layout.addWidget(QtWidgets.QLabel("<b>mGear Component Settings</b>"))

        # Stage 29, request: mGear's own "Settings" window (Shifter Guide
        # Manager's "Settings" button) is more than just Main Settings - it
        # also has a "Component Settings" tab that's completely different
        # for every one of mGear's ~50+ component types (control_01's is
        # icon/joint/keyable-channels/ikRefArray; a totally different
        # component type's is something else entirely), plus, for
        # component types that define them, "Joints Description Names" /
        # "Ctl Description Names" / "Space Alias Description Names" tabs.
        # Hand-reimplementing all of that per component type isn't
        # realistic from a sandbox that can't run Maya to verify any of it
        # against dozens of real component guides - so instead this opens
        # mGear's OWN, completely unmodified Settings window directly
        # (`open_mgear_component_settings`), the exact same code and UI
        # Shifter Guide Manager's own "Settings" button opens, for
        # whichever component type this node actually is. Only needs a
        # built guide (mGear's dialog reads/writes the LIVE Maya node).
        self.btn_open_mgear_settings = QtWidgets.QPushButton("⚙ Settings")
        self.btn_open_mgear_settings.setStyleSheet(
            "background-color: #4a3d1f; font-weight: bold;")
        self.btn_open_mgear_settings.setToolTip(
            "Opens mGear's own Settings window for this component's LIVE built guide - "
            "exactly what Shifter Guide Manager's own 'Settings' button opens, unmodified. "
            "Covers everything the Main Settings section below does NOT: this component "
            "type's own 'Component Settings' tab (different for every mGear component "
            "type), plus Joints/Ctl/Space-Alias Description Names tabs when this "
            "component type has them.\n"
            "Requires the guide to already be built first - it edits the live Maya node "
            "directly, same as mGear's own dialog always has."
        )
        self.btn_open_mgear_settings.clicked.connect(self.open_mgear_component_settings)
        mgear_layout.addWidget(self.btn_open_mgear_settings)
        # Fixed reference copy of the explanatory tooltip above - update_attr_editor()
        # swaps the button's live tooltip to a "build the guide first" message when
        # there's no guide yet, and needs to restore exactly this text, not whatever
        # the tooltip happens to currently say (which could itself be that swapped-in
        # message from the last time a different node was selected).
        self._mgear_settings_btn_tooltip = self.btn_open_mgear_settings.toolTip()

        # Says, in the panel itself, what that window covers and what has to
        # be true for it to open - previously only discoverable by hovering.
        self.lbl_mgear_settings_state = QtWidgets.QLabel("")
        self.lbl_mgear_settings_state.setWordWrap(True)
        self.lbl_mgear_settings_state.setStyleSheet("color: #888; font-size: 10px; border: none;")
        mgear_layout.addWidget(self.lbl_mgear_settings_state)

        # Stage 34: reverted the inline embed (Stage 31 request #1) - it
        # stopped reliably opening mGear's Settings for some users ("the
        # setting window from mgear is not opening anymore") and added a lot
        # of fragile machinery (reparenting mGear's own QTabWidget out of a
        # QDialog it half-owns, tracking whether the embed needs rebuilding,
        # surfacing embed-specific errors) for a UI mGear already ships and
        # maintains. Simpler and more robust: the button above just opens
        # mGear's real, unmodified Settings window - no new UI to keep in
        # sync with mGear's ~50+ component types.
        main_settings_layout.addWidget(self.mgear_settings_group)
        self.mgear_settings_group.setVisible(False)

        # Shown instead of everything else when this node type simply has no
        # component settings, so the tab explains itself rather than being
        # blank (which read as a bug).
        self.lbl_main_settings_note = QtWidgets.QLabel("")
        self.lbl_main_settings_note.setWordWrap(True)
        self.lbl_main_settings_note.setStyleSheet(
            "color: #888; font-size: 11px; border: none; margin-top: 8px;")
        main_settings_layout.addWidget(self.lbl_main_settings_note)
        self.lbl_main_settings_note.setVisible(False)

        self.component_group = QtWidgets.QWidget()
        comp_layout = QtWidgets.QVBoxLayout(self.component_group)
        comp_layout.setContentsMargins(0, 8, 0, 0)
        comp_layout.setSpacing(4)
        comp_layout.addWidget(QtWidgets.QLabel("<b>Main Settings</b> (mGear component)"))

        idx_row = QtWidgets.QHBoxLayout()
        idx_row.addWidget(QtWidgets.QLabel("Component Index:"))
        self.spin_comp_index = QtWidgets.QSpinBox()
        self.spin_comp_index.setRange(0, 999)
        self.spin_comp_index.valueChanged.connect(self.on_attr_changed)
        idx_row.addWidget(self.spin_comp_index)
        idx_row.addSpacing(10)
        idx_row.addWidget(QtWidgets.QLabel("Connector:"))
        self.edit_connector = QtWidgets.QLineEdit()
        self.edit_connector.setToolTip(
            "How this component's root attaches to its parent (mGear's own connector "
            "types are per-component, e.g. 'standard'/'orientation'/'average') - "
            "leave as 'standard' unless a specific connector is needed."
        )
        self.edit_connector.editingFinished.connect(self.on_attr_changed)
        idx_row.addWidget(self.edit_connector)
        comp_layout.addLayout(idx_row)

        comp_layout.addWidget(QtWidgets.QLabel("<i>Joint Settings</i>"))
        joint_idx_row = QtWidgets.QHBoxLayout()
        self.chk_use_joint_index = QtWidgets.QCheckBox("Use Parent Joint Index")
        self.chk_use_joint_index.setToolTip(
            "Parent this component's own joint chain onto a specific joint (by index) "
            "of its parent component's joint chain, instead of the default connection."
        )
        self.chk_use_joint_index.toggled.connect(self.on_attr_changed)
        joint_idx_row.addWidget(self.chk_use_joint_index)
        joint_idx_row.addWidget(QtWidgets.QLabel("Parent Joint Index:"))
        self.spin_parent_joint_index = QtWidgets.QSpinBox()
        self.spin_parent_joint_index.setRange(-1, 999)
        self.spin_parent_joint_index.valueChanged.connect(self.on_attr_changed)
        joint_idx_row.addWidget(self.spin_parent_joint_index)
        comp_layout.addLayout(joint_idx_row)

        joint_names_row = QtWidgets.QHBoxLayout()
        self.lbl_joint_names = QtWidgets.QLabel("Joint Names (None)")
        joint_names_row.addWidget(self.lbl_joint_names)
        joint_names_row.addStretch()
        btn_joint_names = QtWidgets.QPushButton("Configure...")
        btn_joint_names.clicked.connect(self.edit_selected_node_joint_names)
        joint_names_row.addWidget(btn_joint_names)
        comp_layout.addLayout(joint_names_row)

        comp_layout.addWidget(QtWidgets.QLabel("Orientation Offset XYZ:"))
        offset_row = QtWidgets.QHBoxLayout()
        self.spin_joint_offset_x = QtWidgets.QDoubleSpinBox()
        self.spin_joint_offset_y = QtWidgets.QDoubleSpinBox()
        self.spin_joint_offset_z = QtWidgets.QDoubleSpinBox()
        for spin in (self.spin_joint_offset_x, self.spin_joint_offset_y, self.spin_joint_offset_z):
            spin.setRange(-360.0, 360.0)
            spin.setDecimals(2)
            spin.valueChanged.connect(self.on_attr_changed)
            offset_row.addWidget(spin)
        comp_layout.addLayout(offset_row)

        comp_layout.addWidget(QtWidgets.QLabel("<i>Channels Host Settings</i>"))
        host_row = QtWidgets.QHBoxLayout()
        self.edit_ui_host = QtWidgets.QLineEdit()
        self.edit_ui_host.setPlaceholderText("(inherit from parent)")
        self.edit_ui_host.editingFinished.connect(self.on_attr_changed)
        host_row.addWidget(self.edit_ui_host)
        btn_grab_host = QtWidgets.QPushButton("<<")
        btn_grab_host.setFixedWidth(30)
        btn_grab_host.setToolTip("Grab the currently-selected guide in Maya as this component's UI host.")
        btn_grab_host.clicked.connect(self.grab_selected_as_ui_host)
        host_row.addWidget(btn_grab_host)
        comp_layout.addLayout(host_row)

        comp_layout.addWidget(QtWidgets.QLabel("Custom Controllers Group:"))
        self.edit_ctl_group = QtWidgets.QLineEdit()
        self.edit_ctl_group.setPlaceholderText("(inherit from parent)")
        self.edit_ctl_group.editingFinished.connect(self.on_attr_changed)
        comp_layout.addWidget(self.edit_ctl_group)

        comp_layout.addWidget(QtWidgets.QLabel("<i>Color Settings</i>"))
        self.chk_override_colors = QtWidgets.QCheckBox("Override Colors")
        self.chk_override_colors.toggled.connect(self.on_attr_changed)
        comp_layout.addWidget(self.chk_override_colors)
        self.chk_use_rgb_colors = QtWidgets.QCheckBox("Use RGB Colors")
        self.chk_use_rgb_colors.toggled.connect(self.on_attr_changed)
        comp_layout.addWidget(self.chk_use_rgb_colors)

        fk_row = QtWidgets.QHBoxLayout()
        fk_row.addWidget(QtWidgets.QLabel("FK:"))
        self.spin_color_fk = QtWidgets.QSpinBox()
        self.spin_color_fk.setRange(0, 31)
        self.spin_color_fk.setToolTip("Maya override color index (0-31). Used when Use RGB Colors is off.")
        self.spin_color_fk.valueChanged.connect(self.on_attr_changed)
        fk_row.addWidget(self.spin_color_fk)
        self.btn_rgb_fk = QtWidgets.QPushButton("RGB...")
        self.btn_rgb_fk.setToolTip("Pick an exact RGB color. Used when Use RGB Colors is on.")
        self.btn_rgb_fk.clicked.connect(lambda: self.pick_component_rgb_color("fk"))
        fk_row.addWidget(self.btn_rgb_fk)
        comp_layout.addLayout(fk_row)

        ik_row = QtWidgets.QHBoxLayout()
        ik_row.addWidget(QtWidgets.QLabel("IK:"))
        self.spin_color_ik = QtWidgets.QSpinBox()
        self.spin_color_ik.setRange(0, 31)
        self.spin_color_ik.setToolTip("Maya override color index (0-31). Used when Use RGB Colors is off.")
        self.spin_color_ik.valueChanged.connect(self.on_attr_changed)
        ik_row.addWidget(self.spin_color_ik)
        self.btn_rgb_ik = QtWidgets.QPushButton("RGB...")
        self.btn_rgb_ik.setToolTip("Pick an exact RGB color. Used when Use RGB Colors is on.")
        self.btn_rgb_ik.clicked.connect(lambda: self.pick_component_rgb_color("ik"))
        ik_row.addWidget(self.btn_rgb_ik)
        comp_layout.addLayout(ik_row)

        main_settings_layout.addWidget(self.component_group)
        self.component_group.setVisible(False)
        main_settings_layout.addStretch()

        self.lbl_built_state = QtWidgets.QLabel("Guide: Not built")
        self.lbl_built_state.setStyleSheet("color: #aaa; border: none; margin-top: 8px;")
        hierarchy_layout.addWidget(self.lbl_built_state)

        self.chk_separate_guide = QtWidgets.QCheckBox("Build in Separate Guide Group (guide1, guide2...)")
        self.chk_separate_guide.setStyleSheet("margin-top: 6px;")
        self.chk_separate_guide.setToolTip(
            "Only applies to a module with no Parent Module set. Checked: 'Build Guides' always "
            "starts this module in a brand-new top-level guide group of its own (Maya auto-numbers "
            "it guide1, guide2, ... once 'guide' is taken), instead of merging into whichever guide "
            "hierarchy already exists in the scene. Use this to build multiple independent "
            "characters or props side by side in one scene rather than under one shared guide."
        )
        self.chk_separate_guide.toggled.connect(self.on_attr_changed)
        hierarchy_layout.addWidget(self.chk_separate_guide)

        # Stage 31: the same "replay stored placement or not" switch for node
        # types that have no "Align Guides Automatically" option to sit under.
        # Only one of the two is ever visible at a time (this one for
        # non-Plebe nodes, the Plebe group's copy for Plebe nodes), so they
        # can never show contradicting states for the one underlying value.
        self.chk_apply_positions_node, self.apply_positions_row_node = \
            self._make_apply_positions_row()
        hierarchy_layout.addWidget(self.apply_positions_row_node)
        hierarchy_layout.addStretch()

        self.btn_custom_script = QtWidgets.QPushButton("🖉 Custom Script...")
        self.btn_custom_script.setStyleSheet("margin-top: 8px;")
        self.btn_custom_script.setToolTip("Attach a MEL/Python script to run after this module's guide or rig is built.")
        self.btn_custom_script.clicked.connect(self.open_custom_script_dialog)
        scripts_layout.addWidget(self.btn_custom_script)

        self.lbl_script_state = QtWidgets.QLabel("Script: none")
        self.lbl_script_state.setStyleSheet("color: #aaa; border: none;")
        self.lbl_script_state.setWordWrap(True)
        scripts_layout.addWidget(self.lbl_script_state)

        # Shown only while the node's custom script's last run failed -
        # mirrors the Rig Builder Workspace panel's SHOW ERROR / ↺ pattern.
        script_err_row = QtWidgets.QHBoxLayout()
        self.btn_script_error = QtWidgets.QPushButton("⚠ Show Error")
        self.btn_script_error.setStyleSheet("background-color: #5a2a2a; color: #ffaaaa; font-weight: bold;")
        self.btn_script_error.setToolTip("Show the full traceback from this node's last custom script failure.")
        self.btn_script_error.clicked.connect(self.show_script_error_dialog)
        self.btn_script_error.setVisible(False)
        self.btn_script_reset = QtWidgets.QPushButton("↺")
        self.btn_script_reset.setFixedWidth(28)
        self.btn_script_reset.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_script_reset.setToolTip("Reset error - restore to normal without re-running. "
                                         "Editing and saving the script also does this automatically.")
        self.btn_script_reset.clicked.connect(self.reset_script_error)
        self.btn_script_reset.setVisible(False)
        script_err_row.addWidget(self.btn_script_error)
        script_err_row.addWidget(self.btn_script_reset)
        scripts_layout.addLayout(script_err_row)
        scripts_layout.addStretch()

        attr_layout.addWidget(self.node_inner_tabs, 1)

        # Right-hand side: per-node editing (above) and root-level Shifter
        # "Guide Settings" (rig-wide options, matching mGear's own Guide
        # Settings dialog) side by side in a tab widget.
        self.side_tabs = QtWidgets.QTabWidget()
        # A hard fixed width here fights the splitter/window whenever the
        # KRT window is resized (shrinking the window can't shrink this
        # panel, which starves the graph view of space instead) - give it a
        # sane range and let the splitter handle actually resize it.
        self.side_tabs.setMinimumWidth(300)
        self.side_tabs.setMaximumWidth(460)
        self.side_tabs.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.side_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; background: #252526; }")
        self.side_tabs.addTab(self.attr_frame, "Node")

        self.guide_settings_panel = GuideSettingsPanel(self)
        self.side_tabs.addTab(self.guide_settings_panel, "Guide Settings")
        self.side_tabs.currentChanged.connect(self._on_side_tab_changed)

        self.split.addWidget(self.side_tabs)
        # Any extra/lost space from resizing the KRT window goes to the
        # graph canvas first - the Node/Guide Settings panel only grows
        # within its own min/max range once the graph already has room.
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setCollapsible(0, False)
        self.split.setCollapsible(1, False)
        self.layout.addWidget(self.split, 1)

        bot_layout = QtWidgets.QHBoxLayout()
        btn_build_guides = QtWidgets.QPushButton("Build Guides (From Sidebar Selection)")
        btn_build_guides.setFixedHeight(40)
        btn_build_guides.setStyleSheet("background-color: #336699; font-weight: bold; font-size: 14px;")
        btn_build_guides.clicked.connect(lambda: self.execute_graph_nodes("guides"))

        btn_build_module = QtWidgets.QPushButton("Build Modules (From Sidebar Selection)")
        btn_build_module.setFixedHeight(40)
        btn_build_module.setStyleSheet("background-color: #339966; font-weight: bold; font-size: 14px;")
        btn_build_module.clicked.connect(lambda: self.execute_graph_nodes("rig"))

        bot_layout.addWidget(btn_build_guides)
        bot_layout.addWidget(btn_build_module)
        self.layout.addLayout(bot_layout)

        self.update_attr_editor()

    def get_node_by_uuid(self, uuid_str):
        for item in self.graph_view.scene.items():
            if isinstance(item, RigNode) and item.uuid == uuid_str:
                return item
        return None

    def get_parent_node(self, node):
        """The node whose wire points INTO `node`, i.e. its parent in the
        mGear guide hierarchy. None if `node` has no incoming wire (it
        parents directly under the top level guide root)."""
        for item in self.graph_view.scene.items():
            if isinstance(item, RigWire) and item.dest is node:
                return item.source
        return None

    def _refresh_wire_tooltip_for(self, node):
        """Refresh the incoming wire's tooltip (Stage 28) after `node`'s
        parent_local_target changed some way other than dragging a brand
        new connection or the wire's own right-click menu (both of which
        already keep it current) - e.g. the Node tab's Attach Under combo."""
        for item in self.graph_view.scene.items():
            if isinstance(item, RigWire) and item.dest is node:
                item.refresh_tooltip()

    def _sorted_by_hierarchy(self, nodes):
        """Return `nodes` reordered so a node's parent (when it is also in
        the list) always comes before it - guides must be drawn top-down."""
        node_set = set(nodes)
        ordered = []

        def visit(n, trail=None):
            if n in ordered:
                return
            trail = trail or set()
            if id(n) in trail:
                return  # cyclical wiring - bail rather than recurse forever
            trail = trail | {id(n)}
            parent = self.get_parent_node(n)
            if parent in node_set and parent not in ordered:
                visit(parent, trail)
            ordered.append(n)

        for n in nodes:
            visit(n)
        return ordered

    def _descendants_of(self, node):
        """Every node reachable by following outgoing wires from `node`,
        so the Parent Module combo can never offer a choice that would
        create a cycle."""
        result = set()
        stack = [node]
        while stack:
            n = stack.pop()
            for item in self.graph_view.scene.items():
                if isinstance(item, RigWire) and item.source is n and item.dest not in result:
                    result.add(item.dest)
                    stack.append(item.dest)
        return result

    def update_attr_editor(self):
        if getattr(self, "_updating_attr", False): return

        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) == 1:
            self.attr_frame.setEnabled(True)
            node = selected[0]
            # A genuinely new selection gets its own fresh undo-coalescing
            # window (see _maybe_snapshot_before_edit) - re-populating the
            # Node tab for the SAME node (e.g. after an unrelated refresh)
            # must not reset it, or a rapid burst of edits to one field
            # could each end up as their own undo step.
            if getattr(self, "_last_edited_node_uuid", None) != node.uuid:
                self._edit_snapshot_pending = True
                self._last_edited_node_uuid = node.uuid
            self._updating_attr = True
            self.lbl_node_type.setText(f"Type: <b>{node.module_type}</b>")
            self.edit_custom_name.setText(node.custom_name)
            self.combo_side.setCurrentText(node.side)

            self.combo_parent.clear()
            self.combo_parent.addItem("— None (Top Level) —", "")
            excluded = self._descendants_of(node) | {node}
            current_parent = self.get_parent_node(node)
            select_idx = 0
            for other in [i for i in self.graph_view.scene.items() if isinstance(i, RigNode)]:
                if other in excluded:
                    continue
                self.combo_parent.addItem(other.display_title, other.uuid)
                if other is current_parent:
                    select_idx = self.combo_parent.count() - 1
            self.combo_parent.setCurrentIndex(select_idx)
            self._refresh_attach_point_combo(node, current_parent)

            is_plebe = node.module_type == PLEBE_MODULE_TYPE
            self.plebe_group.setVisible(is_plebe)
            if is_plebe:
                self.lbl_plebe_template.setText(node.plebe_template_name or "None")
                self.chk_align_guides.setChecked(node.align_guides_auto)
                self.chk_fan_joint.setChecked(node.fan_joint_enabled)
                self.chk_stretchy_joint.setChecked(node.stretchy_joint_enabled)
                self.edit_control_shapes_lib.setText(node.control_shapes_library or "")

            is_custom_sgt = node.module_type == CUSTOM_SGT_MODULE_TYPE
            self.sgt_group.setVisible(is_custom_sgt)
            if is_custom_sgt:
                self.lbl_sgt_path.setText(node.custom_sgt_path or "None")

            # Stage 27: "Main Settings" only makes sense for a real Shifter
            # catalog component - Plebe/Custom Module/Custom Script nodes
            # don't draw a normal component guide with these attributes.
            is_component = node.module_type not in (
                PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE)
            self.component_group.setVisible(is_component)
            if is_component:
                self.spin_comp_index.setValue(node.comp_index)
                self.edit_connector.setText(node.connector)
                self.chk_use_joint_index.setChecked(node.use_joint_index)
                self.spin_parent_joint_index.setValue(node.parent_joint_index)
                names = [n for n in node.joint_names.split(",") if n.strip()]
                self.lbl_joint_names.setText(
                    "Joint Names (<b>{0} set</b>)".format(len(names)) if names else "Joint Names (None)")
                self.spin_joint_offset_x.setValue(node.joint_rot_offset_x)
                self.spin_joint_offset_y.setValue(node.joint_rot_offset_y)
                self.spin_joint_offset_z.setValue(node.joint_rot_offset_z)
                self.edit_ui_host.setText(node.ui_host)
                self.edit_ctl_group.setText(node.ctl_group)
                self.chk_override_colors.setChecked(node.override_colors)
                self.chk_use_rgb_colors.setChecked(node.use_rgb_colors)
                self.spin_color_fk.setValue(node.color_fk_index)
                self.spin_color_ik.setValue(node.color_ik_index)
                self._style_rgb_button(self.btn_rgb_fk, node.color_fk_rgb)
                self._style_rgb_button(self.btn_rgb_ik, node.color_ik_rgb)
            # Stage 31, request #2: mGear's own Settings window (the one with
            # the "Component Settings" tab) works off the LIVE guide root and
            # only needs it to be a real Shifter component - which a Custom
            # Module (.sgt) node's built guide very often IS. Offer it for any
            # node whose guide qualifies, not just catalog-component nodes,
            # and always say why when it isn't offered.
            self._refresh_mgear_settings_group(node, is_component)

            if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                # Stage 26: no guide at all for this node type - report on
                # its script instead of a guide that will never exist.
                self.lbl_built_state.setText("Script: ran ✓" if node.custom_script_ran
                                             else "Script: not run yet (no guide - script-only node)")
            elif node.maya_guide_root:
                self.lbl_built_state.setText(f"Guide: Built ({node.maya_guide_root.split('|')[-1]})")
            else:
                self.lbl_built_state.setText("Guide: Not built")

            self.chk_separate_guide.setChecked(node.build_separate_guide_group)
            # Only meaningful for a node with no parent - a child always
            # builds under whatever its parent resolves to regardless.
            self.chk_separate_guide.setEnabled(current_parent is None)

            # Stage 31: one value, two places to show it - under "Align
            # Guides Automatically" for a Plebe (where it was asked for,
            # and where it matters most), on the Hierarchy tab for every
            # other node type. Exactly one is visible at a time.
            apply_pos = getattr(node, "apply_guide_positions", True)
            self.chk_apply_positions_plebe.setChecked(apply_pos)
            self.chk_apply_positions_node.setChecked(apply_pos)
            # The Plebe copy lives inside plebe_group, which is already shown
            # only for Plebe nodes; hide the Hierarchy copy for those so the
            # same switch never appears twice at once.
            self.apply_positions_row_node.setVisible(not is_plebe)

            self._update_script_label(node)
            self._updating_attr = False
        else:
            self._last_edited_node_uuid = None
            self.attr_frame.setEnabled(False)
            self._updating_attr = True
            self.lbl_node_type.setText("Type: N/A")
            self.edit_custom_name.setText("")
            self.combo_parent.clear()
            self.combo_attach_point.clear()
            self.combo_attach_point.setEnabled(False)
            self.plebe_group.setVisible(False)
            self.sgt_group.setVisible(False)
            self.component_group.setVisible(False)
            self.mgear_settings_group.setVisible(False)
            self.lbl_main_settings_note.setVisible(True)
            self.lbl_main_settings_note.setText("Select a module in the graph to see its settings.")
            self.lbl_built_state.setText("Guide: Not built")
            self.chk_separate_guide.setChecked(False)
            self.chk_separate_guide.setEnabled(False)
            self.lbl_script_state.setText("Script: none")
            self.btn_script_error.setVisible(False)
            self.btn_script_reset.setVisible(False)
            self._updating_attr = False

    def _guide_root_comp_type(self, node):
        """The Shifter component type of this node's LIVE built guide root,
        or None if it has no guide yet / the guide isn't a Shifter component.
        This is what mGear's own Settings window keys off - and, importantly,
        it's true of plenty of Custom Module (.sgt) guides too, not only of
        nodes KRT classifies as catalog components."""
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return None
        try:
            if not cmds.attributeQuery("comp_type", node=root, exists=True):
                return None
            return cmds.getAttr(f"{root}.comp_type")
        except Exception:
            return None

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

    def _refresh_mgear_settings_group(self, node, is_component):
        """Stage 31, request #2 / Stage 34 (reverted the inline embed):
        decide what the 'Main Settings' tab shows and whether the "Open
        Full mGear Settings" button is usable.

        Previously this tab held exactly one thing - KRT's mirror of mGear's
        Main Settings - shown only for a plain catalog component, so selecting
        a Custom Module (.sgt) node gave a completely blank tab with no hint
        as to why. Now: the button to open mGear's own Settings window (which
        is where the 'Component Settings' tab lives) is offered for ANY node
        whose built guide is a real Shifter component, and when nothing
        applies the tab says so instead of showing nothing.

        Stage 34: no more inline embed - mGear's Settings window opens in
        its own real window (open_mgear_component_settings), exactly as
        Shifter Guide Manager's own "Settings" button does. Simpler, and it
        doesn't depend on reparenting a QDialog's internals out from under
        it, which is what made the inline version unreliable."""
        comp_type = self._guide_root_comp_type(node)
        is_script = node.module_type == CUSTOM_SCRIPT_MODULE_TYPE
        has_guide = bool(node.maya_guide_root and cmds.objExists(node.maya_guide_root))

        # A script-only node never has a guide, so mGear settings can't ever
        # apply to it; everything else gets the button, enabled once its
        # built guide turns out to be a real Shifter component.
        show_group = not is_script
        self.mgear_settings_group.setVisible(show_group)
        if show_group:
            self.btn_open_mgear_settings.setEnabled(bool(comp_type))
            if comp_type:
                self.btn_open_mgear_settings.setToolTip(self._mgear_settings_btn_tooltip)
                self.lbl_mgear_settings_state.setText(
                    "Live guide is an mGear '<b>{}</b>' component - the button above opens "
                    "mGear's own Settings window for it (Main Settings + Component Settings + "
                    "any Ctl/Joint name tabs).".format(comp_type))
            elif not has_guide:
                self.btn_open_mgear_settings.setToolTip(
                    "Build this node's guide first (Build Guides, or the ⟲ button on the "
                    "Hierarchy tab) - mGear's own Settings window reads/writes the LIVE "
                    "Maya node, so there's nothing for it to open yet.")
                self.lbl_mgear_settings_state.setText(
                    "Guide not built yet. mGear's Settings window edits the live Maya guide, "
                    "so build this node's guide first and this becomes available.")
            else:
                self.btn_open_mgear_settings.setToolTip(
                    "This node's built guide has no 'comp_type' attribute, so it isn't a "
                    "Shifter component guide and mGear's Settings window doesn't apply to it.")
                self.lbl_mgear_settings_state.setText(
                    "This node's built guide isn't a Shifter component guide (no 'comp_type'), "
                    "so mGear's Settings window doesn't apply to it.")

        # KRT's own mirror of mGear's Main Settings fields - the only way to
        # set these before a guide is built, and still useful afterward for
        # anyone who doesn't want to pop open a separate window.
        self.component_group.setVisible(is_component)

        # The explanatory note only appears when the tab would otherwise be
        # empty or nearly so - never when there are real settings on screen.
        if is_component:
            self.lbl_main_settings_note.setVisible(False)
        else:
            self.lbl_main_settings_note.setVisible(True)
            if is_script:
                self.lbl_main_settings_note.setText(
                    "A Custom Script node has no guide and no component settings - it just runs "
                    "its script. See the <b>Scripts</b> tab.")
            elif node.module_type == PLEBE_MODULE_TYPE:
                self.lbl_main_settings_note.setText(
                    "This is a whole character template (Plebe), not a single mGear component, so "
                    "it has no single set of Main Settings. Its own options are on the "
                    "<b>Template</b> tab; the individual components inside its built guide can be "
                    "edited with mGear's Settings window above, or by selecting them in Maya.")
            else:
                self.lbl_main_settings_note.setText(
                    "This is a Custom Module (.sgt file) node. KRT's Main Settings mirror only "
                    "applies to catalog components it builds itself - but if the guide this file "
                    "imports is a real mGear component, use the button above to edit it with "
                    "mGear's own Settings window (Component Settings included).")

    def _static_locator_names_for_type(self, comp_type):
        """Stage 30: the set of guide-locator names a catalog component of
        `comp_type` will create, worked out WITHOUT building anything in
        Maya - by reading that component's own guide.py source directly
        (mgear.shifter_classic_components.<type>.guide / shifter_epic_
        components.<type>.guide) and pulling out every literal name passed
        to self.addLoc(...), the same call mGear's own guide code uses to
        actually create each locator.

        This is deliberately a static-source read, not a live probe build -
        no scene interaction, no risk of colliding with an existing guide,
        safe to call at any time (module search, node selection, before
        anything is ever built). The tradeoff: a name built from a runtime
        value (a loop counter, a spinner-driven joint count, an f-string/%-
        format) isn't a plain string literal in the source, so it won't be
        found here - those components fall back to just whatever a live
        build already reveals via _list_attach_points once actually built.
        Cached per comp_type for the life of this widget - it's a single
        file read + regex, but there's no reason to repeat it.
        """
        if comp_type in self._type_locator_static_cache:
            return self._type_locator_static_cache[comp_type]

        names = []
        try:
            import mgear.shifter as mg_shifter_mod
            guide_module = mg_shifter_mod.importComponentGuide(comp_type)
            src_path = os.path.join(os.path.dirname(guide_module.__file__), "guide.py")
            if not os.path.exists(src_path):
                src_path = guide_module.__file__
            with open(src_path, "r") as f:
                source = f.read()
            # self.addLoc("root", ...) or self.addLoc(self.getName("root"), ...)
            # - either way, the literal name string is what we want.
            pattern = re.compile(r'\.addLoc\(\s*(?:self\.getName\(\s*)?["\']([A-Za-z0-9_\-]+)["\']')
            names = sorted(set(pattern.findall(source)))
        except Exception:
            # Any failure here (mGear not loaded, component type not found,
            # unexpected source layout) just means no pre-build preview for
            # this type - not a reason to break node selection over.
            names = []

        self._type_locator_static_cache[comp_type] = names
        return names

    def _list_attach_points(self, parent_node):
        """Every real Maya transform under `parent_node`'s built guide that
        the selected/dragged child could plausibly attach beneath instead of
        the whole guide root - e.g. a spine's per-section locators, or a
        Plebe biped's named guide locators. Returns [(label, long_name)],
        sorted, and only the guide's own descendants (never controls/joints
        from a rig that may already be built alongside it).

        Stage 28: cached per guide-root long name (see
        _invalidate_attach_points_cache) so repeatedly selecting different
        nodes that share the same already-built parent doesn't re-walk that
        parent's whole guide hierarchy in Maya every single time - this was
        the actual source of the "Attach Under takes too long to check"
        slowdown on a full biped guide.

        Stage 30: if the parent's guide hasn't actually been built yet, this
        no longer just returns empty - for a real catalog component it
        falls back to _static_locator_names_for_type(), so Attach Under has
        real, name-accurate options to offer immediately, with no need to
        build that parent's guide first just to see what's there. These
        returned pairs are (short_name, short_name) rather than a real long
        Maya path (there's no live node yet) - node.parent_local_target
        already self-heals a name that doesn't cmds.objExists() by matching
        short names against whatever's actually live at build time (see
        _resolve_attach_parent), which is exactly what lets a pre-build pick
        made here resolve correctly once the guide is really drawn."""
        if not parent_node:
            return []
        if not parent_node.maya_guide_root or not cmds.objExists(parent_node.maya_guide_root):
            if parent_node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
                return []
            static_names = self._static_locator_names_for_type(parent_node.module_type)
            return [(name, name) for name in static_names]
        root = parent_node.maya_guide_root
        cached = self._attach_points_cache.get(root)
        if cached is not None:
            return cached
        try:
            descendants = cmds.listRelatives(root, allDescendents=True,
                                             type="transform", fullPath=True) or []
        except Exception:
            return []
        points = []
        for long_name in descendants:
            short = long_name.split("|")[-1]
            # Guide locators are plain transforms named things like
            # "spine_C0_1_loc" or "chest" - skip anything that is clearly a
            # rig control/joint rather than a guide locator, in case a rig
            # has already been built alongside this guide.
            if short.endswith(("_ctl", "_jnt", "Shape")):
                continue
            points.append((short, long_name))
        points.sort(key=lambda p: p[0].lower())
        self._attach_points_cache[root] = points
        return points

    def _invalidate_attach_points_cache(self, root=None):
        """Drop the _list_attach_points() cache - for one specific guide
        root (a rebuild that reuses the same root name, e.g. mGear's biped
        'guide') or, when `root` is None, entirely (a batch delete/undo/redo/
        load can touch more roots than are worth tracking individually).
        Cheap to over-invalidate - the next selection just re-walks Maya once
        and re-caches; the expensive part this is protecting against is
        re-walking on EVERY click, not the occasional real rebuild."""
        if root is None:
            self._attach_points_cache.clear()
        else:
            self._attach_points_cache.pop(root, None)

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

    # =====================================================
    # Stage 31, request #1: remember mGear's own Component Settings
    # =====================================================
    # Editing a setting in mGear's Settings UI writes it straight onto the
    # live guide root - which a rebuild then throws away, exactly like
    # hand-moved guide positions used to be thrown away. These capture the
    # whole set generically and replay it after a rebuild.

    # Guide-root attributes NOT to snapshot generically:
    #  - identity, which KRT itself owns and rewrites on every build;
    #  - the Main Settings attributes KRT already mirrors as real fields on
    #    the node (serialized individually, applied by build_node_guide /
    #    apply_main_settings_live) - snapshotting those too would mean two
    #    sources of truth for one attribute, quietly fighting each other on
    #    the next build. sync_node_main_settings_from_guide() below keeps
    #    those fields honest instead, by reading them back off the guide.
    COMPONENT_IDENTITY_ATTRS = {
        "comp_type", "comp_name", "comp_side", "ismodel", "isGearGuide",
        "gear_version", "guide_root",
    }
    MIRRORED_MAIN_SETTINGS_ATTRS = {
        "comp_index", "connector", "useIndex", "parentJointIndex", "joint_names",
        "joint_rot_offset_x", "joint_rot_offset_y", "joint_rot_offset_z",
        "ui_host", "ctlGrp", "Override_Color", "Use_RGB_Color",
        "color_fk", "color_ik", "RGB_fk", "RGB_ik",
    }

    def capture_node_component_settings(self, node):
        """Snapshot every user setting on this node's live guide root that
        isn't identity and isn't already a mirrored Main Settings field -
        i.e. everything mGear's own 'Component Settings' tab edits, whatever
        the component type happens to be.

        Attributes with an incoming connection are skipped deliberately:
        their value is driven by something else, so re-applying a frozen copy
        of it later is meaningless at best and destructive at worst (the same
        lesson the Material panel's shadingEngine.surfaceShader bug taught)."""
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        try:
            attrs = cmds.listAttr(root, userDefined=True) or []
        except Exception:
            traceback.print_exc()
            return
        snapshot = {}
        for attr in attrs:
            if attr in self.COMPONENT_IDENTITY_ATTRS or attr in self.MIRRORED_MAIN_SETTINGS_ATTRS:
                continue
            plug = f"{root}.{attr}"
            try:
                if cmds.getAttr(plug, type=True) == "message":
                    continue
                if cmds.listConnections(plug, source=True, destination=False, plugs=True):
                    continue
                value = cmds.getAttr(plug)
            except Exception:
                continue
            if isinstance(value, (int, float, bool, str)):
                snapshot[attr] = value
            elif isinstance(value, (list, tuple)) and value:
                try:
                    if isinstance(value[0], (list, tuple)):
                        snapshot[attr] = [list(v) for v in value]
                    elif isinstance(value[0], (int, float, str)):
                        snapshot[attr] = list(value)
                except Exception:
                    continue
        if snapshot:
            node.component_settings_snapshot = snapshot

    def apply_node_component_settings(self, node):
        """Replay a captured Component Settings snapshot onto a freshly built
        guide. Anything the snapshot names that this guide doesn't have (a
        component/mGear version change) is skipped rather than treated as an
        error, same tolerance as apply_node_guide_positions."""
        root = node.maya_guide_root
        snapshot = node.component_settings_snapshot
        if not root or not snapshot or not cmds.objExists(root):
            return
        for attr, value in snapshot.items():
            plug = f"{root}.{attr}"
            try:
                if not cmds.attributeQuery(attr, node=root, exists=True):
                    continue
                if cmds.listConnections(plug, source=True, destination=False, plugs=True):
                    continue
                if isinstance(value, str):
                    cmds.setAttr(plug, value, type="string")
                elif isinstance(value, list):
                    if value and isinstance(value[0], list):
                        cmds.setAttr(plug, *value[0])
                    else:
                        cmds.setAttr(plug, *value)
                else:
                    cmds.setAttr(plug, value)
            except Exception:
                continue

    def sync_node_main_settings_from_guide(self, node):
        """Read the Main Settings attributes back OFF the live guide root
        into the node's own fields. Needed because those fields are no longer
        only editable through KRT's mirror - mGear's own Settings window
        (opened via the "⚙ Settings" button) writes them straight onto the
        guide, and without this the KRT-side copy would go stale and then
        overwrite the user's change on the next build."""
        if node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
            return
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return

        def _get(attr, default=None):
            try:
                if not cmds.attributeQuery(attr, node=root, exists=True):
                    return default
                return cmds.getAttr(f"{root}.{attr}")
            except Exception:
                return default

        try:
            node.comp_index = int(_get("comp_index", node.comp_index))
            node.connector = _get("connector", node.connector) or node.connector
            node.use_joint_index = bool(_get("useIndex", node.use_joint_index))
            node.parent_joint_index = int(_get("parentJointIndex", node.parent_joint_index))
            node.joint_names = _get("joint_names", node.joint_names) or ""
            node.joint_rot_offset_x = float(_get("joint_rot_offset_x", node.joint_rot_offset_x))
            node.joint_rot_offset_y = float(_get("joint_rot_offset_y", node.joint_rot_offset_y))
            node.joint_rot_offset_z = float(_get("joint_rot_offset_z", node.joint_rot_offset_z))
            node.ui_host = _get("ui_host", node.ui_host) or ""
            node.ctl_group = _get("ctlGrp", node.ctl_group) or ""
            node.override_colors = bool(_get("Override_Color", node.override_colors))
            node.use_rgb_colors = bool(_get("Use_RGB_Color", node.use_rgb_colors))
            node.color_fk_index = int(_get("color_fk", node.color_fk_index))
            node.color_ik_index = int(_get("color_ik", node.color_ik_index))
            rgb_fk = _get("RGB_fk")
            if rgb_fk:
                node.color_fk_rgb = tuple(rgb_fk[0]) if isinstance(rgb_fk[0], (list, tuple)) else tuple(rgb_fk)
            rgb_ik = _get("RGB_ik")
            if rgb_ik:
                node.color_ik_rgb = tuple(rgb_ik[0]) if isinstance(rgb_ik[0], (list, tuple)) else tuple(rgb_ik)
        except Exception:
            traceback.print_exc()

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

    # =====================================================
    # Stage 31, request #1: live "guide placement changed" watcher
    # =====================================================
    # The round light next to the canvas. GREEN = every built guide still
    # sits where it was last recorded (or where it was built, for a node
    # nothing has been recorded for yet); RED = at least one guide has been
    # moved in the scene since then. Clicking it records the current
    # placement onto every node's guide_position_snapshot - which
    # serialize_node() already writes into the guides JSON, and which
    # apply_node_guide_positions() already replays after a rebuild (for a
    # Plebe biped, deliberately AFTER its own auto-align, so a hand tweak
    # survives instead of being overwritten - see _build_plebe_guide).

    # Below this, a difference is float noise rather than a real move.
    POSITION_EPSILON = 1e-4

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

    def _refresh_attach_point_combo(self, node, parent_node):
        self.combo_attach_point.blockSignals(True)
        self.combo_attach_point.clear()
        self.combo_attach_point.addItem("(Whole Guide Root)", "")
        points = self._list_attach_points(parent_node) if parent_node else []
        select_idx = 0
        for label, long_name in points:
            self.combo_attach_point.addItem(label, long_name)
            if long_name == node.parent_local_target:
                select_idx = self.combo_attach_point.count() - 1
        self.combo_attach_point.setCurrentIndex(select_idx)
        self.combo_attach_point.setEnabled(parent_node is not None and len(points) > 0)
        self.combo_attach_point.blockSignals(False)

    def _snap_attach_point_text(self):
        """Stage 26: the Attach Under combo is editable (for search), so
        clicking away or Tab-ing out after typing a partial filter with no
        exact match would otherwise leave that typed fragment sitting in the
        field looking like a selection. Snap it back to whatever's actually
        selected (the real current index's text) whenever the typed text
        isn't an exact match for one of the real entries."""
        combo = self.combo_attach_point
        text = combo.currentText()
        idx = combo.findText(text, QtCore.Qt.MatchFixedString)
        if idx >= 0:
            if idx != combo.currentIndex():
                combo.setCurrentIndex(idx)
        else:
            combo.setEditText(combo.itemText(combo.currentIndex()))

    def on_attach_point_combo_changed(self, index):
        if getattr(self, "_updating_attr", False): return
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        self._push_undo_snapshot()
        node.parent_local_target = self.combo_attach_point.itemData(index) or None
        node.update_display()
        self._refresh_wire_tooltip_for(node)
        self.workspace.refresh_module_list()

    def open_mgear_component_settings(self):
        """Stage 29: open mGear's OWN, completely unmodified per-component
        'Settings' window - the exact same thing Shifter Guide Manager's own
        'Settings' button opens (mgear.shifter.guide_manager.inspect_settings)
        - for the selected node's LIVE built guide.

        Why this exists instead of KRT hand-reimplementing it: mGear's real
        Settings window is actually up to 4 tabs, and only the first ("Main
        Settings") is generic across every component type - Stage 27 mirrors
        that one directly into the Node tab. The rest are NOT generic:
        - "Component Settings" is defined separately by EVERY ONE of mGear's
          ~50+ component types (control_01's has icon/joint/keyable-channel/
          ikRefArray fields; a completely different component type's tab has
          entirely different fields) - hand-porting all of them, from a
          sandbox that can never run Maya to check the result against a real
          guide, isn't a realistic or safe undertaking.
        - "Joints/Ctl/Space Alias Description Names" tabs only appear for a
          component type that actually defines that kind of name (checked via
          hasAttr on the live guide root), each holding one label+textbox+
          Reset row per name.
        Reusing mGear's own classes directly (`shifter.importComponentGuide
        (comp_type).componentSettings`) means every one of these, for every
        component type, is always exactly correct - it IS mGear's code -
        without KRT tracking any of it by hand. The real limitation: mGear's
        dialog reads/writes the LIVE Maya node (`pm.selected()[0]`), so this
        only works once the node's guide is actually built - there's no
        pre-build equivalent the way Stage 27's Main Settings mirror has.
        """
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            cmds.warning(f"'{node.display_title}' has no built guide yet - use Build Guides "
                         "(or the ⟲ Build Parent's Guide button) first.")
            return
        if not cmds.attributeQuery("comp_type", node=root, exists=True):
            cmds.warning(f"'{node.display_title}'s guide root has no 'comp_type' attribute - "
                         "it isn't a real Shifter component guide, so mGear's own Settings "
                         "window doesn't apply to it.")
            return

        try:
            from mgear import shifter as mg_shifter
            from mgear.core import pyqt as mg_pyqt
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return

        comp_type = cmds.getAttr(f"{root}.comp_type")
        cmds.select(root, replace=True)
        try:
            guide_module = mg_shifter.importComponentGuide(comp_type)
            wind = mg_pyqt.showDialog(guide_module.componentSettings, dockable=True)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to open mGear's Settings window for '{node.display_title}' "
                         f"(component type '{comp_type}') - see Script Editor.")
            return
        return wind

    def on_parent_combo_changed(self, index):
        if getattr(self, "_updating_attr", False): return
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        self._push_undo_snapshot()

        # Drop any existing incoming wire before (maybe) adding a new one -
        # a node has at most one parent.
        for item in list(self.graph_view.scene.items()):
            if isinstance(item, RigWire) and item.dest is node:
                self.graph_view.scene.removeItem(item)
                if item in item.source.wires: item.source.wires.remove(item)
                if item in item.dest.wires: item.dest.wires.remove(item)

        target_uuid = self.combo_parent.itemData(index)
        parent_node = self.get_node_by_uuid(target_uuid) if target_uuid else None
        if parent_node:
            new_wire = RigWire(parent_node, node)
            self.graph_view.scene.addItem(new_wire)

        # A different (or removed) parent invalidates any specific guide
        # locator that was picked for the old one.
        node.parent_local_target = None
        node.update_display()
        self._refresh_attach_point_combo(node, parent_node)
        self.workspace.refresh_module_list()

    def change_selected_node_template(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or selected[0].module_type != PLEBE_MODULE_TYPE:
            return
        node = selected[0]
        templates = list_plebe_templates()
        if not templates:
            cmds.warning("No mGear Plebe character templates found.")
            return
        dialog = PlebeTemplateDialog(templates, self.workspace.main_window, current_path=node.plebe_template_path)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted and dialog.selected_path:
            self._push_undo_snapshot()
            node.plebe_template_path = dialog.selected_path
            node.plebe_template_name = dialog.selected_name
            if not node.custom_name.strip() or node.custom_name.startswith("Plebe:"):
                node.custom_name = f"Plebe: {dialog.selected_name}"
            node.update_display()
            self.update_attr_editor()
            self.workspace.refresh_module_list()

    def _style_rgb_button(self, button, rgb):
        """Stage 27: paint an "RGB..." picker button with the color it
        currently holds, so Color Settings reads at a glance without needing
        to open the picker - same idea as mGear's own FK/IK swatch labels."""
        r, g, b = (max(0.0, min(1.0, c)) for c in rgb)
        button.setStyleSheet(
            f"background-color: rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)}); "
            "color: white; font-weight: bold;"
        )

    def pick_component_rgb_color(self, which):
        """Stage 27: 'RGB...' button next to the FK/IK color index spinbox -
        opens a normal color picker and stores the result as this node's
        color_fk_rgb/color_ik_rgb (only actually used by mGear when Use RGB
        Colors is checked - same as mGear's own dialog)."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        current = node.color_fk_rgb if which == "fk" else node.color_ik_rgb
        r, g, b = (max(0.0, min(1.0, c)) for c in current)
        initial = QtGui.QColor(int(r * 255), int(g * 255), int(b * 255))
        color = QtWidgets.QColorDialog.getColor(initial, self.workspace.main_window, "Pick a Color")
        if not color.isValid():
            return
        self._push_undo_snapshot()
        rgb = (color.redF(), color.greenF(), color.blueF())
        if which == "fk":
            node.color_fk_rgb = rgb
            self._style_rgb_button(self.btn_rgb_fk, rgb)
        else:
            node.color_ik_rgb = rgb
            self._style_rgb_button(self.btn_rgb_ik, rgb)
        self.apply_main_settings_live(node)

    def grab_selected_as_ui_host(self):
        """Stage 27: the "<<" button next to Channels Host - grabs whatever
        guide transform is currently selected in Maya, same convenience
        mGear's own Settings dialog offers (updateHostUI). Only accepts an
        actual guide object (has the 'isGearGuide' attribute mGear stamps
        on every guide transform), same restriction mGear itself applies."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        sel = cmds.ls(selection=True, long=True) or []
        if not sel:
            cmds.warning("Nothing selected in Maya to grab as the UI host.")
            return
        target = sel[0]
        if not cmds.attributeQuery("isGearGuide", node=target, exists=True):
            cmds.warning("The selected object is not a guide element - pick a real mGear guide transform.")
            return
        self._push_undo_snapshot()
        node.ui_host = target
        self.edit_ui_host.setText(target)
        self.apply_main_settings_live(node)

    def edit_selected_node_joint_names(self):
        """Stage 27: 'Configure...' next to Joint Names - a lightweight
        stand-in for mGear's own ordered-table editor. Same underlying
        storage (a comma-joined string in the 'joint_names' attribute), just
        edited here as one name per line for simplicity."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        current = "\n".join(n.strip() for n in node.joint_names.split(",") if n.strip())
        dialog = QtWidgets.QDialog(self.workspace.main_window)
        dialog.setWindowTitle(f"Joint Names - {node.display_title}")
        dialog.setMinimumSize(360, 320)
        dialog.setStyleSheet("QDialog { background-color: #1e1e1e; color: white; } "
                             "QLabel { color: #cccccc; } "
                             "QPlainTextEdit { background: #141414; border: 1px solid #333; color: #d4d4d4; } "
                             "QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }")
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel("One joint name per line, in order (blank lines are dropped):"))
        text_edit = QtWidgets.QPlainTextEdit()
        text_edit.setPlainText(current)
        layout.addWidget(text_edit)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = QtWidgets.QPushButton("Save")
        btn_ok.setStyleSheet("background-color: #2bb5a8; font-weight: bold;")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return
        self._push_undo_snapshot()
        names = [n.strip() for n in text_edit.toPlainText().splitlines() if n.strip()]
        node.joint_names = ",".join(names)
        summary = "Joint Names (<b>{0} set</b>)".format(len(names)) if names else "Joint Names (None)"
        self.lbl_joint_names.setText(summary)
        self.apply_main_settings_live(node)

    def change_selected_node_sgt_path(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or selected[0].module_type != CUSTOM_SGT_MODULE_TYPE:
            return
        node = selected[0]
        start_dir = os.path.dirname(node.custom_sgt_path) if node.custom_sgt_path else ""
        res = cmds.fileDialog2(
            fm=1, ff="mGear Guide Template (*.sgt);;All Files (*.*)",
            caption="Choose a Custom Module .sgt File",
            dir=start_dir if os.path.exists(start_dir) else "")
        if res:
            self._push_undo_snapshot()
            node.custom_sgt_path = res[0]
            if not node.custom_name.strip():
                node.custom_name = os.path.splitext(os.path.basename(res[0]))[0]
            node.update_display()
            self.update_attr_editor()
            self.workspace.refresh_module_list()

    def _update_script_label(self, node):
        """Stage 30: 'i think custom script not running. i need prof that it
        is running.' - a plain colored dot, impossible to miss, giving an
        unambiguous answer at a glance instead of having to infer it from
        wording: 🔴 red = last run actually failed (unchanged - already had
        its own bold red text), 🟢 green = the script has run successfully
        at least once (custom_script_ran, now tracked for every node type
        with a script, not just Custom Script nodes - see
        run_node_custom_script), 🔵 blue = a script IS attached and set to
        run, but hasn't fired yet this session (e.g. its trigger point
        hasn't happened, or the guide/rig hasn't been (re)built since the
        script last changed - see CustomScriptDialog.apply_to_node, which
        resets custom_script_ran back to False whenever the code changes,
        since a past 'ran' only proves the OLD code ran)."""
        has_error = bool(node.custom_script_last_error)
        self.btn_script_error.setVisible(has_error)
        self.btn_script_reset.setVisible(has_error)
        if has_error:
            self.lbl_script_state.setText("🔴 Script: last run FAILED - see Show Error")
            self.lbl_script_state.setStyleSheet("color: #ff8888; border: none; font-weight: bold;")
        elif node.custom_script_when == "none" or not node.custom_script_code.strip():
            self.lbl_script_state.setText("Script: none")
            self.lbl_script_state.setStyleSheet("color: #aaa; border: none;")
        else:
            when_label = "after Build Guides" if node.custom_script_when == "guides" else "after Build Modules"
            trigger_note = ""
            if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE and node.custom_script_trigger_node_uuid:
                target = next(
                    (n for n in self.graph_view.scene.items()
                     if isinstance(n, RigNode) and n.uuid == node.custom_script_trigger_node_uuid),
                    None,
                )
                # Plain name+side only - NOT target.display_title, which
                # carries the TARGET's own icon/checkmark/script-status dot
                # baked into its text. Using display_title here made this
                # node's OWN status line show a stray unrelated green/blue
                # dot that actually belonged to the target node, not to
                # this trigger relationship - confusing regardless of
                # whether this node's own script had run or not.
                trigger_note = f", waits for '{target.custom_name} [{target.side}]'" if target \
                    else ", waits for a deleted module"
            dot = "🟢" if node.custom_script_ran else "🔵"
            ran_note = "has run ✓" if node.custom_script_ran else "has NOT run yet this session"
            self.lbl_script_state.setText(
                f"{dot} Script: {node.custom_script_lang.upper()}, runs {when_label}{trigger_note} - {ran_note}"
            )
            self.lbl_script_state.setStyleSheet(
                "color: #8fd694; border: none;" if node.custom_script_ran else "color: #6fb8ff; border: none;"
            )

    def open_custom_script_dialog(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to attach a custom script to.")
            return
        node = selected[0]
        all_nodes = [i for i in self.graph_view.scene.items() if isinstance(i, RigNode) and i is not node]
        dialog = CustomScriptDialog(node, self.workspace.main_window, all_nodes=all_nodes)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            dialog.apply_to_node()
            self._update_script_label(node)
            self.workspace.refresh_module_list()

    def edit_fan_joint_script(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to edit its Fan Joint script.")
            return
        node = selected[0]
        dialog = AutoScriptEditDialog("Fan Joint Script - {}".format(node.display_title),
                                       node.fan_joint_script, DEFAULT_FAN_JOINT_SCRIPT, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            node.fan_joint_script = dialog.result_code()

    def edit_stretchy_joint_script(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to edit its Stretchy Joint script.")
            return
        node = selected[0]
        dialog = AutoScriptEditDialog("Stretchy Joint Script - {}".format(node.display_title),
                                       node.stretchy_joint_script, DEFAULT_STRETCHY_JOINT_SCRIPT, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            node.stretchy_joint_script = dialog.result_code()

    def show_script_error_dialog(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or not selected[0].custom_script_last_error:
            return
        node = selected[0]
        from .widgets import ErrorDialog
        dialog = ErrorDialog("Custom Script Error", f"Custom script failed - {node.display_title}",
                             node.custom_script_last_error, self.workspace.main_window, allow_retry=True)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if getattr(dialog, "retry", False):
            self.run_node_custom_script(node, node.custom_script_when)
            self._update_script_label(node)

    def reset_script_error(self):
        """Restore the script status back to normal without re-running -
        matches the Rig Builder Workspace panel's own ↺ reset button.
        Editing and re-saving the script (see CustomScriptDialog.apply_to_node)
        clears the same flag automatically, as an alternative to this."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        node.custom_script_last_error = ""
        node.update_display()
        self._update_script_label(node)

    def run_node_custom_script(self, node, phase):
        """Run `node`'s attached script if it is set to fire at `phase`
        ('guides' or 'modules'). Failures are reported but never abort the
        larger build - a broken per-module script shouldn't nuke a batch build.
        A failure is recorded on the node (⚠ marker on the graph, red border,
        "Show Error"/"↺" controls in the Node tab) so it's discoverable after
        the fact rather than only in the moment via the Script Editor."""
        if node.custom_script_when != phase or not node.custom_script_code.strip():
            return
        try:
            if node.custom_script_lang == "mel":
                import maya.mel as mel
                mel.eval(node.custom_script_code)
            else:
                exec(node.custom_script_code, self.workspace.shared_namespace)
        except Exception:
            node.custom_script_last_error = traceback.format_exc()
            traceback.print_exc()
            cmds.warning(f"Custom script failed for '{node.display_title}' ({phase}) - see Script Editor "
                         "or the Node tab's 'Show Error' button.")
        else:
            node.custom_script_last_error = ""
            # Stage 26 introduced this only for a Custom Script node (which
            # has no guide of its own, so this was its only "did it actually
            # run" signal). Stage 30: "i need proof that it is running" -
            # now tracked for EVERY node type with an attached script, not
            # just Custom Script nodes, so any component's Scripts tab can
            # show a real ran/not-run/error status instead of just an error
            # state. See _update_script_label / RigNode.update_display for
            # where this actually gets shown.
            node.custom_script_ran = True
        node.update_display()
        if node in [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]:
            self._update_script_label(node)

    def run_node_auto_scripts(self, node, phase):
        """Stage 19: Fan Joint / Stretchy Joint, each independently toggled
        and independently editable (Node tab, Plebe nodes only). Both always
        run as Python at the 'modules' phase (right after this node's rig is
        actually built) - there's no per-script "when" picker like the
        custom script has, since these act on real built joints and only
        ever make sense at that one point. Only meaningful for a Plebe node;
        a regular Shifter component or Custom Module node never has these
        enabled (module_type check below is the actual guard, not just the
        Node tab hiding the checkboxes)."""
        if phase != "modules" or node.module_type != PLEBE_MODULE_TYPE:
            return
        for enabled, script, label in (
            (node.fan_joint_enabled, node.fan_joint_script, "Fan Joint"),
            (node.stretchy_joint_enabled, node.stretchy_joint_script, "Stretchy Joint"),
        ):
            if not enabled or not script.strip():
                continue
            try:
                exec(script, self.workspace.shared_namespace)
            except Exception:
                traceback.print_exc()
                cmds.warning(f"{label} script failed for '{node.display_title}' - see Script Editor.")

    def _on_side_tab_changed(self, index):
        if self.side_tabs.widget(index) is self.guide_settings_panel:
            self.guide_settings_panel.refresh_from_scene()

    def browse_control_shapes_library(self):
        start = self.edit_control_shapes_lib.text().strip()
        start_dir = os.path.dirname(start) if start else ""
        res = cmds.fileDialog2(
            fm=1, ff="Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb);;All Files (*.*)",
            caption="Choose Control Shapes Library",
            dir=start_dir if os.path.exists(start_dir) else "")
        if res:
            self.edit_control_shapes_lib.setText(res[0])
            # setText() alone doesn't fire editingFinished, so the node
            # wouldn't otherwise pick up a Browse-selected path until some
            # unrelated edit happened to trigger a save.
            self.on_attr_changed()

    def apply_control_shapes_library_to(self, guide_model, lib_path):
        """Merge `lib_path`'s Control Shapes Library into `guide_model`'s
        controllers_org. Safe to call repeatedly - skips entirely once
        already applied for this exact library path."""
        if not lib_path or not guide_model or not cmds.objExists(guide_model):
            return
        marker_attr = guide_model + ".krt_ctlShapesLibApplied"
        try:
            if cmds.attributeQuery("krt_ctlShapesLibApplied", node=guide_model, exists=True):
                if cmds.getAttr(marker_attr) == lib_path:
                    return
            else:
                cmds.addAttr(guide_model, longName="krt_ctlShapesLibApplied", dataType="string")
            apply_control_shapes_library(lib_path, guide_model)
            cmds.setAttr(marker_attr, lib_path, type="string")
        except Exception:
            traceback.print_exc()
            cmds.warning("Could not apply Control Shapes Library - see Script Editor.")

    def compute_default_guide_path(self):
        """Where 'Save Guides'/'Load Guides' points by default: a 'guide'
        subfolder right next to the current session's own KRT pipeline JSON,
        named to match it - e.g. '.../MyRig.json' -> '.../guide/MyRig_guide.json'.
        Falls back to the home-directory default when the session hasn't
        been saved anywhere yet."""
        session_path = getattr(self.workspace, "session_path", "") or ""
        if session_path:
            session_dir = os.path.dirname(session_path)
            base = os.path.splitext(os.path.basename(session_path))[0]
            return os.path.join(session_dir, "guide", base + "_guide.json").replace("\\", "/")
        return os.path.join(os.path.expanduser('~'), "kleem_guide.json").replace("\\", "/")

    def refresh_default_guide_path(self):
        """Re-point the Guide Path field at the current session's own
        'guide' subfolder - called whenever the session's save location
        changes (Save Session, Load JSON Pipeline, new/closed tab), so the
        guide file always follows the KRT json without the user having to
        browse for it by hand. A manual edit to the field survives until the
        next such change, then gets recomputed again."""
        self.path_field.setText(self.compute_default_guide_path())

    def on_attr_changed(self):
        if getattr(self, "_updating_attr", False): return
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) == 1:
            self._maybe_snapshot_before_edit()
            node = selected[0]
            node.custom_name = self.edit_custom_name.text()
            node.side = self.combo_side.currentText()
            if node.module_type == PLEBE_MODULE_TYPE:
                node.align_guides_auto = self.chk_align_guides.isChecked()
                node.fan_joint_enabled = self.chk_fan_joint.isChecked()
                node.stretchy_joint_enabled = self.chk_stretchy_joint.isChecked()
                node.control_shapes_library = self.edit_control_shapes_lib.text().strip()
            if node.module_type not in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
                # Stage 27: mGear's own "Main Settings" fields.
                node.comp_index = self.spin_comp_index.value()
                node.connector = self.edit_connector.text().strip() or "standard"
                node.use_joint_index = self.chk_use_joint_index.isChecked()
                node.parent_joint_index = self.spin_parent_joint_index.value()
                node.joint_rot_offset_x = self.spin_joint_offset_x.value()
                node.joint_rot_offset_y = self.spin_joint_offset_y.value()
                node.joint_rot_offset_z = self.spin_joint_offset_z.value()
                node.ui_host = self.edit_ui_host.text().strip()
                node.ctl_group = self.edit_ctl_group.text().strip()
                node.override_colors = self.chk_override_colors.isChecked()
                node.use_rgb_colors = self.chk_use_rgb_colors.isChecked()
                node.color_fk_index = self.spin_color_fk.value()
                node.color_ik_index = self.spin_color_ik.value()
                self.apply_main_settings_live(node)
            node.build_separate_guide_group = self.chk_separate_guide.isChecked()
            # Stage 31: whichever of the two "Apply Saved Guide Positions"
            # checkboxes is the visible one for this node type is the one
            # that carries the user's intent.
            node.apply_guide_positions = (
                self.chk_apply_positions_plebe.isChecked()
                if node.module_type == PLEBE_MODULE_TYPE
                else self.chk_apply_positions_node.isChecked())
            node.update_display()
            self.workspace.refresh_module_list()
            # Turning the replay on/off changes what the placement light is
            # comparing against, so settle it now instead of up to a tick later.
            self._refresh_position_watch()

    def _guide_browse_start_dir(self):
        """Where the guide-JSON Browse/Import dialogs should open (Stage 17):
        the CURRENT guide path's own folder if it's already a real path,
        else the most recent pipeline JSON KRT knows about
        (session_manager's recent_files) - the same "fall back to something
        recent" idea behind KRT's own Load JSON Pipeline recent-files list,
        instead of leaving it to whatever folder Maya's fileDialog2 happened
        to open last, anywhere in the whole Maya session."""
        current = self.path_field.text().strip()
        if current:
            d = os.path.dirname(current)
            if d and os.path.exists(d):
                return d
        session_path = getattr(self.workspace, "session_path", "") or ""
        if session_path:
            d = os.path.dirname(session_path)
            if d and os.path.exists(d):
                return d
        try:
            recents = self.workspace.main_window.session.data.get("recent_files", [])
        except Exception:
            recents = []
        for p in recents:
            if p and os.path.exists(p):
                return os.path.dirname(p)
        return ""

    def browse_path(self):
        start_dir = self._guide_browse_start_dir()
        # fileMode=1 ("an existing file must be selected") - not 0 ("any
        # file, whether it exists or not"), which is what made this open as
        # a Save-As dialog (native "Save As" title, "Save" button) even
        # though Browse is for picking an EXISTING guide JSON to point the
        # field at, not for choosing where to save one.
        kwargs = {"fileFilter": "KRT Guide JSON (*.json)", "dialogStyle": 2, "fileMode": 1,
                  "caption": "Browse Guide JSON"}
        if start_dir:
            kwargs["startingDirectory"] = start_dir
        file_path = cmds.fileDialog2(**kwargs)
        if file_path:
            self.path_field.setText(file_path[0])

    def _populate_guide_versions_menu(self, switch_menu):
        """Guide Path equivalent of widgets.py's SortablePanel.
        populate_versions_menu(): lists sibling "<base>_vNNN.<ext>" files
        next to the current Guide Path (the same "_vNNN" convention
        save_all_guides(overwrite=False) writes) so "Switch Version" can
        point the field at any of them without a file dialog."""
        v_actions = {}
        base_path = self.path_field.text().strip()
        if not base_path:
            switch_menu.setEnabled(False)
            return v_actions

        dir_name = os.path.dirname(base_path)
        if not dir_name or not os.path.exists(dir_name):
            switch_menu.setEnabled(False)
            return v_actions

        base_name, ext = os.path.splitext(os.path.basename(base_path))
        base_name_no_v = re.sub(r'_v\d+$', '', base_name)
        pattern = re.compile(r"^" + re.escape(base_name_no_v) + r"(?:_v(\d+))?" + re.escape(ext) + r"$")

        versions = []
        for f in os.listdir(dir_name):
            if pattern.match(f):
                versions.append(os.path.join(dir_name, f).replace('\\', '/'))
        versions.sort()

        if not versions:
            switch_menu.setEnabled(False)
        else:
            for v in versions:
                v_actions[switch_menu.addAction(os.path.basename(v))] = v
        return v_actions

    def show_guide_path_menu(self):
        """The Guide Path row's "..." menu (Stage 35): Browse / Save Guide
        (Overwrite or New Version) / Switch Version - the same save-versus-
        version-switch pattern the Rig Build workspace panels use in their
        own "..." menu (widgets.py's SortablePanel.show_context_menu), now
        that Browse/Save Guides/Export Config/Import Config are no longer
        separate always-visible buttons here."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")

        a_browse = menu.addAction("📂 Browse...")
        menu.addSeparator()
        a_save_over = menu.addAction("💾 Save Guide (Overwrite)")
        a_save_new = menu.addAction("💾 Save Guide (New Version)")
        switch_menu = menu.addMenu("🔄 Switch Version")
        v_actions = self._populate_guide_versions_menu(switch_menu)

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if not action:
            return

        if action == a_browse:
            self.browse_path()
        elif action == a_save_over:
            self.save_all_guides(overwrite=True)
        elif action == a_save_new:
            self.save_all_guides(overwrite=False)
        elif action in v_actions:
            self.path_field.setText(v_actions[action])

    def save_all_guides(self, overwrite=True):
        """Save this graph's own guide-relevant data (every node's type,
        position, side, Plebe/attach-point/control-shapes-library choices,
        etc - everything build_node_guide()/_build_plebe_guide() need to
        redraw the guide - plus the rig-wide Guide Settings tab) as plain
        KRT JSON.

        Deliberately does NOT touch the live Maya scene or require a guide
        to currently exist there: it just saves what's already in the graph
        - unlike a real mGear .sgt export, which needs a live scene guide to
        read from. KRT's own build flow (a module bubble's LOAD button, and
        the panel LOAD button) now deletes the guide from the scene right
        after building it, so relying on a live scene guide here would fail
        immediately after almost any normal build.

        overwrite=True (default - "Save Guide (Overwrite)", and every
        automatic sync from a KRT pipeline JSON save, see
        SessionWorkspace._save_pipeline_assets()/AdvancedSaveDialog/the
        AYON publish flow): writes to the Guide Path field's CURRENT path,
        unchanged - this is what keeps that field's path always matching
        the exact graph JSON on disk after a KRT save.

        overwrite=False ("Save Guide (New Version)"): bumps the path to the
        next "_vNNN" version first, the same convention the Rig Build
        workspace panels' own "Save (New Version)" uses, points the field
        at it, THEN writes - a deliberate "only Graph" save gets its own
        new version; a KRT-save-triggered sync does not.
        """
        path = self.path_field.text().strip()
        if not path: return

        if not overwrite:
            from .utils import get_versioned_path
            path = get_versioned_path(path, get_latest=False)
            self.path_field.setText(path)

        # Stage 28, request #3: capture every node's CURRENT live guide
        # positions right before writing anything out, so a rigger who moved
        # guide locators by hand after Build Guides has that placement
        # remembered here, in the guide data itself - the next Build Guides
        # (which redraws from scratch, e.g. after the module-bubble LOAD
        # flow's own guide auto-deletion) reapplies it automatically.
        # Stage 31: now captures mGear Component Settings changes too - see
        # capture_all_live_state().
        self.capture_all_live_state()

        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception:
                traceback.print_exc()
                cmds.error(f"Could not create guide folder '{directory}' - see Script Editor.")
                return

        try:
            with open(path, "w") as f:
                json.dump(self.get_graph_config_data(), f, indent=4)
            cmds.warning(f"Guide data (from the graph, not the scene) saved to {path}")
        except Exception:
            traceback.print_exc()
            cmds.error("Failed to save guide data - see Script Editor for details.")

    def load_all_guides(self):
        """Inverse of save_all_guides(): rebuilds the graph's nodes/wires and
        Guide Settings from a previously saved guide JSON. Doesn't touch the
        Maya scene either - use 'Build Guides' afterward to actually draw
        real guides from the restored graph."""
        path = self.path_field.text()
        if not os.path.exists(path):
            cmds.warning("Specified guide file does not exist.")
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            traceback.print_exc()
            cmds.error("Failed to read guide file - see Script Editor for details.")
            return

        if not isinstance(data, dict) or "nodes" not in data:
            cmds.warning("That file doesn't look like a KRT guide JSON (no 'nodes' key found).")
            return

        self._clear_undo_history()
        self._apply_graph_config_data(data)
        cmds.warning(f"Guide data loaded from {path}")

    # =====================================================
    # Graph Config JSON: everything KRT itself remembers about the graph -
    # node positions/types, per-node custom scripts, Plebe/attach-point/
    # separate-guide-group choices, and the rig-wide Guide Settings tab -
    # as its own standalone JSON, separate from the full pipeline/session
    # JSON (which also carries LOD panels, build steps, etc). "Save Guides"/
    # "Load Guides" above share this exact same data - they just write it
    # to the auto-managed 'guide' subfolder instead of a manually chosen
    # path. Neither one touches, or requires, a live Maya scene guide.
    # =====================================================

    def serialize_node(self, node):
        """Every KRT-specific thing about one graph node that isn't
        derivable from the Maya scene. Shared by the full pipeline JSON
        (workspace.py's get_current_pipeline_data/load_pipeline_from_file)
        and this standalone Graph Config JSON, so the two never drift apart
        on what a node needs to remember."""
        return {
            "uuid": node.uuid, "module_type": node.module_type, "custom_name": node.custom_name,
            "side": node.side, "x": node.pos().x(), "y": node.pos().y(),
            "custom_script_code": node.custom_script_code, "custom_script_lang": node.custom_script_lang,
            "custom_script_when": node.custom_script_when,
            "custom_script_trigger_node_uuid": node.custom_script_trigger_node_uuid,
            "plebe_template_path": node.plebe_template_path, "plebe_template_name": node.plebe_template_name,
            "align_guides_auto": node.align_guides_auto,
            "apply_guide_positions": node.apply_guide_positions,
            "fan_joint_enabled": node.fan_joint_enabled, "fan_joint_script": node.fan_joint_script,
            "stretchy_joint_enabled": node.stretchy_joint_enabled, "stretchy_joint_script": node.stretchy_joint_script,
            "control_shapes_library": node.control_shapes_library,
            "parent_local_target": node.parent_local_target,
            "build_separate_guide_group": node.build_separate_guide_group,
            "custom_sgt_path": node.custom_sgt_path,
            "comp_index": node.comp_index, "connector": node.connector,
            "use_joint_index": node.use_joint_index, "parent_joint_index": node.parent_joint_index,
            "joint_names": node.joint_names,
            "joint_rot_offset_x": node.joint_rot_offset_x, "joint_rot_offset_y": node.joint_rot_offset_y,
            "joint_rot_offset_z": node.joint_rot_offset_z,
            "ui_host": node.ui_host, "ctl_group": node.ctl_group,
            "override_colors": node.override_colors, "use_rgb_colors": node.use_rgb_colors,
            "color_fk_index": node.color_fk_index, "color_ik_index": node.color_ik_index,
            "color_fk_rgb": list(node.color_fk_rgb), "color_ik_rgb": list(node.color_ik_rgb),
            "guide_position_snapshot": node.guide_position_snapshot,
            "component_settings_snapshot": node.component_settings_snapshot,
        }

    def deserialize_node(self, nd):
        """Inverse of serialize_node() - builds a RigNode (not yet added to
        any scene) from a saved dict."""
        node = RigNode(nd["x"], nd["y"], nd["module_type"], nd["side"], nd.get("custom_name", ""))
        node.uuid = nd["uuid"]
        node.custom_script_code = nd.get("custom_script_code", "")
        node.custom_script_lang = nd.get("custom_script_lang", "python")
        node.custom_script_when = nd.get("custom_script_when", "none")
        node.custom_script_trigger_node_uuid = nd.get("custom_script_trigger_node_uuid")
        node.plebe_template_path = nd.get("plebe_template_path")
        node.plebe_template_name = nd.get("plebe_template_name", "")
        node.align_guides_auto = nd.get("align_guides_auto", True)
        node.apply_guide_positions = nd.get("apply_guide_positions", True)
        node.fan_joint_enabled = nd.get("fan_joint_enabled", False)
        node.fan_joint_script = nd.get("fan_joint_script", DEFAULT_FAN_JOINT_SCRIPT)
        node.stretchy_joint_enabled = nd.get("stretchy_joint_enabled", False)
        node.stretchy_joint_script = nd.get("stretchy_joint_script", DEFAULT_STRETCHY_JOINT_SCRIPT)
        node.control_shapes_library = nd.get(
            "control_shapes_library",
            DEFAULT_CONTROL_SHAPES_LIBRARY if node.module_type == PLEBE_MODULE_TYPE else "")
        node.parent_local_target = nd.get("parent_local_target")
        node.build_separate_guide_group = nd.get("build_separate_guide_group", False)
        node.custom_sgt_path = nd.get("custom_sgt_path")
        node.comp_index = nd.get("comp_index", 0)
        node.connector = nd.get("connector", "standard")
        node.use_joint_index = nd.get("use_joint_index", False)
        node.parent_joint_index = nd.get("parent_joint_index", -1)
        node.joint_names = nd.get("joint_names", "")
        node.joint_rot_offset_x = nd.get("joint_rot_offset_x", 0.0)
        node.joint_rot_offset_y = nd.get("joint_rot_offset_y", 0.0)
        node.joint_rot_offset_z = nd.get("joint_rot_offset_z", 0.0)
        node.ui_host = nd.get("ui_host", "")
        node.ctl_group = nd.get("ctl_group", "")
        node.override_colors = nd.get("override_colors", False)
        node.use_rgb_colors = nd.get("use_rgb_colors", False)
        node.color_fk_index = nd.get("color_fk_index", 6)
        node.color_ik_index = nd.get("color_ik_index", 18)
        node.color_fk_rgb = tuple(nd.get("color_fk_rgb", [0.0, 0.0, 1.0]))
        node.color_ik_rgb = tuple(nd.get("color_ik_rgb", [0.0, 0.25, 1.0]))
        node.guide_position_snapshot = nd.get("guide_position_snapshot", {}) or {}
        node.component_settings_snapshot = nd.get("component_settings_snapshot", {}) or {}
        node.update_display()
        return node

    def get_graph_config_data(self):
        nodes, wires = [], []
        for item in self.graph_view.scene.items():
            if isinstance(item, RigNode):
                nodes.append(self.serialize_node(item))
            elif isinstance(item, RigWire):
                wires.append({"source": item.source.uuid, "dest": item.dest.uuid})
        return {
            "krt_graph_config": True,
            "guide_path": self.path_field.text(),
            "nodes": nodes,
            "wires": wires,
            "guide_settings": self.guide_settings_panel.get_settings_dict(),
        }

    def _apply_graph_config_data(self, data):
        """Shared rebuild-the-graph-from-a-dict logic behind load_all_guides()
        (Stage 35: also used to be shared with the now-removed standalone
        Export/Import Config JSON buttons - Save/Load Guides above cover the
        same data now) - clears the current graph and recreates every node/
        wire from `data`, then reapplies the Guide Settings tab if present.
        Doesn't touch path_field (callers that care about a stored
        guide_path handle that themselves)."""
        self.graph_view.scene.clear()
        uuid_to_node = {}
        for nd in data.get("nodes", []):
            node = self.deserialize_node(nd)
            self.graph_view.scene.addItem(node)
            uuid_to_node[node.uuid] = node
        for wd in data.get("wires", []):
            src = uuid_to_node.get(wd.get("source")); dst = uuid_to_node.get(wd.get("dest"))
            if src and dst:
                self.graph_view.scene.addItem(RigWire(src, dst))

        if "guide_settings" in data:
            self.guide_settings_panel.apply_settings_dict(data["guide_settings"])

        self.workspace.refresh_module_list()
        self.update_attr_editor()

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

    # =====================================================
    # mGear Rig Plebe (character-template biped import) integration
    # =====================================================

    def _plebe_instance(self, node):
        """Build a headless mgear.shifter.plebes.Plebes() instance for
        `node`, with its selected character template already loaded.

        Plebes.set_template() also pushes the template's help text into a
        native Maya scrollField that only exists after .gui() has been run
        (self.help), so calling it directly on a bare Plebes() raises. We
        replicate just the JSON-loading half of it here instead.
        """
        try:
            from mgear.shifter import plebes as mg_plebes
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        if not node.plebe_template_path or not os.path.exists(node.plebe_template_path):
            cmds.warning(f"'{node.display_title}' has no valid Plebe character template set. "
                         "Right-click it isn't available - use 'Change Template...' in the Node tab.")
            return None

        plebe = mg_plebes.Plebes()
        try:
            with open(node.plebe_template_path) as f:
                plebe.template = json.load(f)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to load Plebe character template: {node.plebe_template_path}")
            return None
        return plebe

    def plebe_import_fbx(self, node):
        """Right-click action: import the character FBX (mesh/skeleton) that
        will later be aligned/constrained/skinned to the Shifter rig."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.import_fbx()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to import character FBX - see Script Editor for details.")

    def plebe_fix_fbx_naming(self, node):
        """Right-click action: fix FBXASCxxx-mangled names left behind by
        some FBX importers, matching mGear Plebe's own 'Fix Naming' step."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.fix_fbx_naming()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to fix FBX naming - see Script Editor for details.")

    def plebe_constrain_to_rig(self, node):
        """Right-click action: constrain the imported character skeleton to
        the built Shifter rig, using the node's character template mapping."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.constrain_to_rig()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to constrain character to rig - see Script Editor for details.")

    def plebe_skin_to_rig(self, node):
        """Right-click action: transfer the character's skin weights onto
        the Shifter rig's own joints. Select the skinned geometry first.

        mGear's own dialog exposes an 'Export Only' checkbox that skips the
        unbind/rebind step; this headless invocation always performs the
        full re-skin (equivalent to that checkbox being off), since there is
        no GUI checkbox to read here.
        """
        plebe = self._plebe_instance(node)
        if not plebe:
            return

        class _ExportOnlyShim(object):
            def getValue(self):
                return False

        plebe.export_only_check = _ExportOnlyShim()
        try:
            plebe.skin_to_rig()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to skin character to rig - see Script Editor for details.")

    def _resolve_attach_parent(self, node, parent_node, parent_root, pm):
        """The actual PyNode `node` should attach under when its guide gets
        built: the specific 'Attach Under' locator if it currently exists,
        otherwise the parent's whole guide root, silently."""
        attach_target = node.parent_local_target
        if attach_target and cmds.objExists(attach_target):
            return pm.PyNode(attach_target)
        return pm.PyNode(parent_root)

    def _build_plebe_guide(self, node):
        """Plebe-node counterpart to build_node_guide(). Imports mGear's
        standard biped guide template ('Build Guides' equivalent for a
        Plebe node) and, if the node's 'Align Guides Automatically' toggle
        is on, aligns it using the node's character template mapping.

        mGear's biped guide root is built as literally "guide" (it is not
        parameterized like Shifter component guides). By default, if one
        already exists in the scene, it's adopted instead of importing a
        second one - only one Plebe biped can usefully share that name. If
        this node's "Build in Separate Guide Group" is checked, a new import
        is forced instead; Maya then auto-numbers the fresh group (guide1,
        guide2, ...) since "guide" is already taken, so the new root is
        found by diffing the scene's top-level guide transforms before/after
        the import rather than assuming the literal name "guide".
        """
        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        plebe = self._plebe_instance(node)
        if not plebe:
            return None

        try:
            from mgear.shifter import io as sh_io
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        if cmds.objExists("guide") and not node.build_separate_guide_group:
            cmds.warning("A guide named 'guide' already exists in the scene - adopting it "
                         f"for '{node.display_title}' instead of importing a new biped template.")
            node.maya_guide_root = cmds.ls("guide", long=True)[0]
        else:
            before = {n for n in (cmds.ls(assemblies=True, long=True) or [])
                     if cmds.attributeQuery("ismodel", node=n, exists=True)}
            try:
                sh_io.import_sample_template("biped.sgt")
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Failed to import mGear's biped guide template for '{node.display_title}'.")
                return None

            after = {n for n in (cmds.ls(assemblies=True, long=True) or [])
                    if cmds.attributeQuery("ismodel", node=n, exists=True)}
            new_roots = list(after - before)
            if new_roots:
                node.maya_guide_root = new_roots[0]
            elif cmds.objExists("guide"):
                # Fallback for older mGear builds where the diff above finds
                # nothing (e.g. "ismodel" not queryable pre-creation) but a
                # plain "guide" still appeared.
                node.maya_guide_root = cmds.ls("guide", long=True)[0]

        if not node.maya_guide_root or not cmds.objExists(node.maya_guide_root):
            cmds.warning("Biped guide import did not produce a recognizable guide root - see Script Editor.")
            node.maya_guide_root = None
            return None
        node.update_display()
        self._invalidate_attach_points_cache()

        # Auto-replace this biped's control shapes from its Control Shapes
        # Library, right away - before align/custom-script - so anything
        # that inspects the guide afterward already sees the real shapes.
        self.apply_control_shapes_library_to(node.maya_guide_root, node.control_shapes_library)

        if node.align_guides_auto:
            try:
                plebe.align_guides()
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Auto-align failed for '{node.display_title}' - guide was still "
                             "imported. See Script Editor for details.")

        # Stage 28: reapply any hand-moved guide positions LAST, after
        # align - so a saved manual tweak (the whole point of capturing it)
        # isn't immediately overwritten by the template's own auto-align.
        self.apply_node_guide_positions(node)

        self.run_node_custom_script(node, "guides")
        return node.maya_guide_root

    def _build_custom_sgt_guide(self, node, mg_shifter, pm):
        """Custom-.sgt-node counterpart to build_node_guide(). Imports the
        user's own saved partial guide template (an mGear component .sgt
        file they hand-tweaked and re-exported from Shifter's own Guide
        Manager) via mgear.shifter.io.import_partial_guide(), grafting it
        under this node's resolved parent - same "Attach Under"/
        parent_local_target handling build_node_guide uses for a normal
        catalog component.

        Unlike a catalog component (drawn fresh from a blank ComponentGuide
        via drawFromUI), a .sgt file already carries its own fully-exported
        guide dict - side, name, connector, even its own control-shape
        buffer curves - from whenever it was saved, so there's no
        comp_side/comp_name/connector-inheritance step here; the file's own
        settings win as-is. import_partial_guide()/draw_guide() don't hand
        back the new root's name directly, so it's found the same way
        _build_plebe_guide finds its import: diffing the scene's transforms
        before/after, then keeping only whichever new node's parent already
        existed (the actual top of the freshly-grafted subtree).
        """
        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        if not node.custom_sgt_path or not os.path.exists(node.custom_sgt_path):
            cmds.warning(f"'{node.display_title}' has no valid .sgt file set - "
                         "use Change File... in the Node tab to pick one.")
            return None

        try:
            from mgear.shifter import io as sh_io
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        # Same parent resolution build_node_guide uses for a normal
        # component: recursively build the graph parent's guide first, then
        # prefer a specific chosen locator (Attach Under) over its whole
        # guide root.
        parent_node = self.get_parent_node(node)
        parent_pynode = None
        if parent_node:
            parent_root = parent_node.maya_guide_root or self.build_node_guide(parent_node, mg_shifter, pm)
            if parent_root and cmds.objExists(parent_root):
                parent_pynode = self._resolve_attach_parent(node, parent_node, parent_root, pm)
        elif not node.build_separate_guide_group:
            existing_root = _find_guide_root()
            if existing_root:
                parent_pynode = pm.PyNode(existing_root)
        # else: no graph parent and "Build in Separate Guide Group" is on
        # (or nothing exists yet) - leave parent_pynode None so draw_guide()
        # creates its own fresh top-level guide hierarchy.

        before = set(cmds.ls(type="transform", long=True) or [])

        try:
            sh_io.import_partial_guide(filePath=node.custom_sgt_path, initParent=parent_pynode)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to import custom .sgt guide for '{node.display_title}' - "
                         "see Script Editor. (If it was grafted onto an existing guide, make "
                         "sure Attach Under points at an actual guide locator, not just the "
                         "whole guide root.)")
            return None

        after = set(cmds.ls(type="transform", long=True) or [])
        new_nodes = after - before
        if not new_nodes:
            cmds.warning(f"Custom .sgt import for '{node.display_title}' did not add any new nodes - see Script Editor.")
            return None

        # The top of the freshly-grafted subtree: a new node whose parent is
        # NOT itself one of the new nodes (either it's a fresh top-level
        # assembly, or it hangs off whatever already-existing parent we
        # passed in).
        roots = []
        for n in new_nodes:
            parents = cmds.listRelatives(n, parent=True, fullPath=True)
            if not parents or parents[0] not in new_nodes:
                roots.append(n)
        # Prefer one that's actually mGear guide-flavored (has ismodel or
        # comp_type) over any incidental new transform - and, matching
        # mGear's own guide_manager.inspect_settings() (which walks UP from
        # a selection checking comp_type before ever falling back to
        # ismodel), a comp_type root wins over an ismodel root when a .sgt
        # import produces both as siblings among `roots`. Getting this
        # backwards is exactly why a Custom Module node could end up with
        # maya_guide_root pointed at a plain model/group node instead of its
        # real component root - which has no comp_type, so the "⚙ Settings"
        # button (open_mgear_component_settings) never had anything to key
        # off and the Main/Component Settings tabs stayed blank even
        # though the guide itself built and drew correctly. `roots` (and
        # `new_nodes`) come from set subtraction, so their iteration order
        # isn't guaranteed - sorting keeps which one gets picked stable
        # across runs when more than one candidate of the same kind exists.
        preferred_comp = sorted(r for r in roots
                                if cmds.attributeQuery("comp_type", node=r, exists=True))
        preferred_model = sorted(r for r in roots
                                 if cmds.attributeQuery("ismodel", node=r, exists=True))
        node.maya_guide_root = (preferred_comp or preferred_model or sorted(roots) or sorted(new_nodes))[0]

        if not node.maya_guide_root or not cmds.objExists(node.maya_guide_root):
            cmds.warning(f"Custom .sgt import for '{node.display_title}' did not produce a recognizable guide root.")
            node.maya_guide_root = None
            return None
        node.update_display()
        self._invalidate_attach_points_cache()
        self.apply_node_guide_positions(node)

        self.run_node_custom_script(node, "guides")
        return node.maya_guide_root

    def _build_custom_script_node(self, node, mg_shifter, pm):
        """Stage 26: Custom-Script-node counterpart to build_node_guide() /
        _build_custom_sgt_guide() - except this node type never imports or
        draws any guide at all. Its parent chain is still built first,
        exactly like a real component, so it still holds its place in build
        order (Build Till Here, ordered LOD builds, etc all still see it in
        sequence) - it just never sets maya_guide_root, since there's no
        guide transform to point at.

        Because of that, this node can NOT be used as an "Attach Under"
        parent for a real component below it in the graph - there's no
        guide locator to attach to, so a child parented under it just falls
        back to whatever whole-scene guide root already exists (same as
        having no parent at all). It's meant as a standalone/leaf step for
        the script's own side effects (scene cleanup, an export, calling
        into another tool, enforcing order between two branches, etc), not
        as a hierarchy node other guides graft onto.

        Stage 30: by default this still waits on its own graph-parent chain
        (exactly the behavior above), but the user can instead pick ANY
        other node in the graph as the thing to wait on
        (node.custom_script_trigger_node_uuid, set via CustomScriptDialog's
        "Trigger after module" combo) - useful when the script's real
        dependency isn't this node's own wire-parent (e.g. two unrelated
        branches where one still needs to run after the other). When set,
        that chosen node's guide is built first instead of the graph
        parent's. A stale/deleted target (uuid no longer matches any node
        in the scene) falls back to the graph-parent behavior with a
        warning, rather than silently building nothing.
        """
        trigger_node = None
        if node.custom_script_trigger_node_uuid:
            trigger_node = next(
                (n for n in self.graph_view.scene.items()
                 if isinstance(n, RigNode) and n.uuid == node.custom_script_trigger_node_uuid),
                None,
            )
            if trigger_node is None:
                cmds.warning(
                    f"'{node.display_title}': its chosen trigger module no longer exists in the "
                    "graph - falling back to its own graph parent. Re-pick a trigger module in "
                    "Custom Script settings if this wasn't intended."
                )

        if trigger_node is not None:
            if not (trigger_node.maya_guide_root and cmds.objExists(trigger_node.maya_guide_root)):
                self.build_node_guide(trigger_node, mg_shifter, pm)
        else:
            parent_node = self.get_parent_node(node)
            if parent_node and not (parent_node.maya_guide_root and cmds.objExists(parent_node.maya_guide_root)):
                self.build_node_guide(parent_node, mg_shifter, pm)

        self.run_node_custom_script(node, "guides")
        return None

    # =====================================================
    # Real mGear guide / rig building, driven by the graph
    # =====================================================

    def build_node_guide(self, node, mg_shifter, pm):
        """Ensure `node`'s mGear component guide exists in the scene
        (recursively building its parent chain first), returning the long
        name of its guide root transform, or None on failure/cancel (or, for
        a Stage 26 Custom Script node, always - it has no guide of its own).

        This is the single source of truth used by both the graph editor's
        "Build Guides" button and the Rig Builder Workspace module panel's
        "Add from Graph Editor" bubbles.
        """
        if node.module_type == PLEBE_MODULE_TYPE:
            return self._build_plebe_guide(node)
        if node.module_type == CUSTOM_SGT_MODULE_TYPE:
            return self._build_custom_sgt_guide(node, mg_shifter, pm)
        if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            return self._build_custom_script_node(node, mg_shifter, pm)

        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        parent_node = self.get_parent_node(node)
        parent_pynode = None
        if parent_node:
            parent_root = parent_node.maya_guide_root or self.build_node_guide(parent_node, mg_shifter, pm)
            if parent_root and cmds.objExists(parent_root):
                # If a specific guide locator on the parent was chosen (the
                # Attach Under dropdown, or the popup shown right after
                # dragging a connection) - e.g. a "chest" locator rather than
                # the whole spine guide - attach there instead. Same effect
                # as dragging a component onto a specific locator in
                # Shifter's own Guide Manager outliner; the inheritance walk
                # just below climbs back up from whichever transform this is
                # to find the owning component's side/connector/etc.
                parent_pynode = self._resolve_attach_parent(node, parent_node, parent_root, pm)

        rig_guide = mg_shifter.guide.Rig()
        comp_guide = rig_guide.getComponentGuide(node.module_type)
        if not comp_guide:
            cmds.warning(f"Unknown mGear Shifter component type: {node.module_type}")
            return None

        if not parent_pynode:
            # "Build in Separate Guide Group" forces a brand-new top-level
            # guide even if one already exists in the scene, instead of
            # merging into it - Maya auto-numbers the new group (guide1,
            # guide2, ...) since the name "guide" is already taken.
            existing_root = None if node.build_separate_guide_group else _find_guide_root()
            if existing_root:
                rig_guide.model = pm.PyNode(existing_root)
                parent_pynode = rig_guide.model
            else:
                rig_guide.initialHierarchy()
                parent_pynode = rig_guide.model
        else:
            # Same inheritance Shifter's own "Draw Component" applies when a
            # component is dropped onto an existing one.
            walker = parent_pynode
            while walker:
                if walker.hasAttr("ismodel"):
                    break
                if walker.hasAttr("comp_type"):
                    p_type = walker.attr("comp_type").get()
                    if p_type in comp_guide.connectors:
                        comp_guide.setParamDefValue("connector", p_type)
                    comp_guide.setParamDefValue("comp_side", walker.attr("comp_side").get())
                    comp_guide.setParamDefValue("ui_host", walker.attr("ui_host").get())
                    comp_guide.setParamDefValue("ctlGrp", walker.attr("ctlGrp").get())
                    break
                walker = walker.getParent()

        # The side chosen on the graph node always wins over whatever was
        # just inherited (or the component's own default).
        comp_guide.setParamDefValue("comp_side", node.side)
        if node.custom_name and node.custom_name != node.module_type:
            comp_guide.setParamDefValue("comp_name", node.custom_name)

        # Stage 27: mGear's own "Main Settings" fields, fed in from the Node
        # tab exactly like mGear's own Settings dialog would set them, before
        # drawFromUI actually draws the guide. ui_host/ctlGrp only override
        # the just-inherited value above when the user actually set one on
        # this node - an empty field keeps the existing inherit-from-parent
        # behavior (unchanged since before Stage 27) rather than clearing it.
        comp_guide.setParamDefValue("comp_index", node.comp_index)
        comp_guide.setParamDefValue("connector", node.connector)
        comp_guide.setParamDefValue("useIndex", node.use_joint_index)
        comp_guide.setParamDefValue("parentJointIndex", node.parent_joint_index)
        comp_guide.setParamDefValue("joint_names", node.joint_names)
        comp_guide.setParamDefValue("joint_rot_offset_x", node.joint_rot_offset_x)
        comp_guide.setParamDefValue("joint_rot_offset_y", node.joint_rot_offset_y)
        comp_guide.setParamDefValue("joint_rot_offset_z", node.joint_rot_offset_z)
        if node.ui_host:
            comp_guide.setParamDefValue("ui_host", node.ui_host)
        if node.ctl_group:
            comp_guide.setParamDefValue("ctlGrp", node.ctl_group)
        comp_guide.setParamDefValue("Override_Color", node.override_colors)
        comp_guide.setParamDefValue("Use_RGB_Color", node.use_rgb_colors)
        comp_guide.setParamDefValue("color_fk", node.color_fk_index)
        comp_guide.setParamDefValue("color_ik", node.color_ik_index)
        comp_guide.setParamDefValue("RGB_fk", list(node.color_fk_rgb))
        comp_guide.setParamDefValue("RGB_ik", list(node.color_ik_rgb))

        try:
            ok = comp_guide.drawFromUI(parent_pynode, False)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to draw guide for '{node.module_type}' ({node.display_title}).")
            return None

        if not ok or not comp_guide.root:
            # User cancelled a modal step (e.g. chain section-count dialog).
            return None

        new_root = comp_guide.root.longName()
        node.maya_guide_root = new_root
        node.update_display()
        # This node's own new root, AND its parent's root (this guide just
        # became one more of the parent's descendants, so a fresh "Attach
        # Under" list on the parent needs to see it too).
        self._invalidate_attach_points_cache()
        self.apply_node_guide_positions(node)

        # Note: the Control Shapes Library is only applied for a Plebe biped
        # node (see _build_plebe_guide) - its "*_controlBuffer" curves are
        # named after biped UI controls (legUI_L0_ctl, spineUI_C0_ctl, ...)
        # that only exist on a full biped guide, so applying it here for an
        # arbitrary single Shifter component would just be a wasted import.
        self.run_node_custom_script(node, "guides")
        return new_root

    def apply_main_settings_live(self, node):
        """Stage 27: once a real Shifter component's guide already exists in
        the scene, editing one of the Main Settings fields in the Node tab
        should take effect immediately - same expectation as mGear's own
        Settings dialog, which edits the live guide attributes directly -
        instead of only being picked up on the NEXT full rebuild. No-ops
        silently if there's no guide yet (build_node_guide's
        comp_guide.setParamDefValue calls are what apply these on first
        build) or the node isn't a real component (Plebe/Custom Module/
        Custom Script nodes don't have any of these attributes)."""
        if node.module_type in (PLEBE_MODULE_TYPE, CUSTOM_SGT_MODULE_TYPE, CUSTOM_SCRIPT_MODULE_TYPE):
            return
        root = node.maya_guide_root
        if not root or not cmds.objExists(root):
            return
        try:
            cmds.setAttr(f"{root}.comp_index", node.comp_index)
            cmds.setAttr(f"{root}.connector", node.connector, type="string")
            cmds.setAttr(f"{root}.useIndex", node.use_joint_index)
            cmds.setAttr(f"{root}.parentJointIndex", node.parent_joint_index)
            cmds.setAttr(f"{root}.joint_names", node.joint_names, type="string")
            cmds.setAttr(f"{root}.joint_rot_offset_x", node.joint_rot_offset_x)
            cmds.setAttr(f"{root}.joint_rot_offset_y", node.joint_rot_offset_y)
            cmds.setAttr(f"{root}.joint_rot_offset_z", node.joint_rot_offset_z)
            if node.ui_host and cmds.attributeQuery("ui_host", node=root, exists=True):
                cmds.setAttr(f"{root}.ui_host", node.ui_host, type="string")
            if node.ctl_group and cmds.attributeQuery("ctlGrp", node=root, exists=True):
                cmds.setAttr(f"{root}.ctlGrp", node.ctl_group, type="string")
            cmds.setAttr(f"{root}.Override_Color", node.override_colors)
            cmds.setAttr(f"{root}.Use_RGB_Color", node.use_rgb_colors)
            cmds.setAttr(f"{root}.color_fk", node.color_fk_index)
            cmds.setAttr(f"{root}.color_ik", node.color_ik_index)
            cmds.setAttr(f"{root}.RGB_fk", *node.color_fk_rgb, type="double3")
            cmds.setAttr(f"{root}.RGB_ik", *node.color_ik_rgb, type="double3")
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Couldn't apply Main Settings live to '{node.display_title}' - "
                         "see Script Editor. The values are still saved and will apply on the next build.")

    def execute_graph_nodes(self, action):
        selected_items = self.workspace.rig_list.selectedItems()
        uuid_to_node = {item.uuid: item for item in self.graph_view.scene.items() if isinstance(item, RigNode)}

        if not selected_items:
            if action != "rig":
                # "Build Guides" still needs an explicit sidebar pick - there's
                # no sensible "build every guide in the graph" fallback for it
                # the way there is for "Build Modules" below.
                cmds.warning("No modules selected in the left sidebar to build!")
                return
            # "Build Modules (From Sidebar Selection)" with nothing actually
            # selected: instead of doing nothing, build every module whose
            # guide is currently built in the scene (i.e. everything sitting
            # under a guide group's "ismodel" root right now) - this mirrors
            # what Shifter's own "build from all guides in the scene" does,
            # just scoped to modules this graph already knows about.
            nodes = [n for n in uuid_to_node.values()
                     if n.maya_guide_root and cmds.objExists(n.maya_guide_root)]
            if not nodes:
                cmds.warning("Nothing selected in the left sidebar, and no modules have a "
                             "built guide in the scene to build from either.")
                return
            cmds.warning(f"No modules selected in the sidebar - building all {len(nodes)} "
                         "module(s) with an existing guide in the scene instead.")
        else:
            selected_uuids = {item.data(QtCore.Qt.UserRole) for item in selected_items}

            # Build in the order the modules were actually selected (tracked in
            # workspace.selection_order as selection changes), not scene/list
            # order - falling back to rig_list's own order for anything that
            # somehow isn't in the tracked history.
            ordered_uuids = [u for u in self.workspace.selection_order if u in selected_uuids]
            ordered_uuids += [u for u in selected_uuids if u not in ordered_uuids]

            nodes = [uuid_to_node[u] for u in ordered_uuids if u in uuid_to_node]

        if not nodes:
            cmds.warning("No matching module nodes found in the graph editor to build!")
            return

        try:
            from mgear import shifter as mg_shifter
            import mgear.pymaya as pm
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return

        # Still guarantees a parent is ever built before its selected child
        # (guides can't attach to a guide that doesn't exist yet) - but this
        # is a stable reorder, so two selected nodes with no hierarchy
        # relationship to each other keep the relative order you selected
        # them in.
        nodes = self._sorted_by_hierarchy(nodes)

        if action == "guides":
            cmds.undoInfo(openChunk=True)
            # Stage 31: hold the placement watcher while guides are actually
            # being drawn - a progress dialog's processEvents() can otherwise
            # fire a tick mid-build and flash red off a half-built guide.
            self._pos_watch_suspended = True
            try:
                for node in nodes:
                    self.build_node_guide(node, mg_shifter, pm)
            finally:
                self._pos_watch_suspended = False
                cmds.undoInfo(closeChunk=True)
            self.workspace.refresh_module_list()
            self.update_attr_editor()
            # Stage 31, request #3: any Guide Settings the rigger set before
            # a guide existed go onto the new guide FIRST - refresh_from_
            # scene() would otherwise pull mGear's freshly-built defaults
            # straight back over them.
            self.guide_settings_panel.push_pending_to_scene()
            self.guide_settings_panel.refresh_from_scene()
            # Freshly built = nothing has been moved since, so settle the
            # light immediately rather than waiting for the next tick.
            self._refresh_position_watch()

        elif action == "rig":
            # Stage 26: a Custom Script node has no guide by design, so it
            # never belongs in Shifter's own buildFromSelection() and was
            # never really "missing a guide" to begin with - it just runs
            # its own script (if set to fire at "modules") alongside
            # whatever real components get built this pass.
            script_only_nodes = [n for n in nodes if n.module_type == CUSTOM_SCRIPT_MODULE_TYPE]
            roots, missing = [], []
            for node in nodes:
                if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                    continue
                if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
                    roots.append(node.maya_guide_root)
                else:
                    missing.append(node.display_title)

            # Stage 30 fix: "i am checking in scene. the script havent run"
            # - a script-only node set to run "After Build Modules" WITH a
            # Trigger-after-module dependency was reporting a trigger note
            # that meant nothing in practice: this branch ran the script
            # for any selected script-only node unconditionally, whether or
            # not its chosen trigger module was actually part of THIS same
            # build pass. If the trigger module wasn't separately selected
            # (or its guide didn't even exist yet), the script still fired
            # right away - the "waits for X" label was aspirational, not
            # real. Force the trigger target's guide to exist and its root
            # into THIS pass's Shifter build selection (if it isn't there
            # already) before the script gets its turn below, so "waits
            # for X" is actually true - X gets built, in this exact same
            # pass, before the script runs.
            for node in script_only_nodes:
                if node.custom_script_when != "modules" or not node.custom_script_trigger_node_uuid:
                    continue
                target = self.get_node_by_uuid(node.custom_script_trigger_node_uuid)
                if not target:
                    cmds.warning(f"'{node.display_title}': its Trigger-after module no longer exists in "
                                 "the graph - its script will run without waiting on anything this pass.")
                    continue
                if target.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                    continue  # another script-only node has nothing to "build"
                target_root = target.maya_guide_root if (target.maya_guide_root and cmds.objExists(target.maya_guide_root)) \
                    else self.build_node_guide(target, mg_shifter, pm)
                if target_root and target_root not in roots:
                    roots.append(target_root)

            if missing:
                cmds.warning("Skipped (guide not built yet - run 'Build Guides' first): " + ", ".join(missing))
            if not roots and not script_only_nodes:
                cmds.warning("None of the selected modules have a built guide yet.")
                return

            if roots:
                cmds.select(roots, replace=True)
                try:
                    mg_shifter.Rig().buildFromSelection()
                except Exception:
                    traceback.print_exc()
                    cmds.error("Shifter build failed - see Script Editor for details.")
                    return

            for node in nodes:
                if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE or node.maya_guide_root in roots:
                    self.run_node_custom_script(node, "modules")
                    self.run_node_auto_scripts(node, "modules")
