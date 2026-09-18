"""Auto-split from graph.py."""
from ._shared import *
from .guide_settings import GuideSettingsPanel
from .items import RigNode, RigWire
from .view import NodeGraphView


from .widget_positions import GraphPositionsMixin
from .widget_component_settings import GraphComponentSettingsMixin
from .widget_scripts import GraphScriptsMixin
from .widget_io import GraphIoMixin
from .widget_undo import GraphUndoMixin
from .widget_build import GraphBuildMixin
class ModuleGraphWidget(GraphPositionsMixin, GraphComponentSettingsMixin, GraphScriptsMixin, GraphIoMixin, GraphUndoMixin, GraphBuildMixin, QtWidgets.QWidget):
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

    def _on_side_tab_changed(self, index):
        if self.side_tabs.widget(index) is self.guide_settings_panel:
            self.guide_settings_panel.refresh_from_scene()

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
