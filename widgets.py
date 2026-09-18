import maya.cmds as cmds
import maya.OpenMaya as om
import os
import shutil
import subprocess
import json
import time
import re
import uuid
import traceback
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from .utils import (
    export_control_shapes, import_control_shapes, get_versioned_path,
    find_mismatched_skinclusters, rename_mismatched_skinclusters, log_crash,
    export_material_data, import_material_data,
)
from .dialogs import BuildProgressDialog

# Per-type accent colours so each panel is visually identifiable at a glance.
# Applied as a coloured left border stripe and the title text colour.
# Stage 18: MA and IMPORT_3D are now ONE panel type (IMPORT_3D auto-detects
# the file's actual format on import - see SessionWorkspace.import_3d_logic
# and SortablePanel.execute) - there is no separate "MA" entry anymore.
PANEL_TYPE_ACCENTS = {
    "SCRIPT":        "#4fc3f7",   # light blue  - Python / MEL scripts (KRT-scoped)
    "GLOBAL_SCRIPT": "#9575cd",   # violet      - Python / MEL scripts (Maya-global, Stage 17)
    "IMPORT_3D":     "#ba68c8",   # purple      - imported 3D models (.ma/.mb/.fbx/.obj/.abc)
    "JSON":          "#81c784",   # green       - skin clusters
    "SHAPES":        "#f06292",   # pink        - control shapes
    "PUBLISH":       "#e57373",   # red         - publish path
    "MODULE":        "#2bb5a8",   # teal        - module bubble panels
    "TWEAKER":       "#4dd0e1",   # cyan        - tweaker setups
    "LOD_LOADER":    "#ffca28",   # amber/gold  - LOD Loader (build entire LODs), Stage 20
    "MATERIAL":      "#ff8a65",   # deep orange - shader/material + texture save-load
    "NOTE":          "#ffd54f",   # yellow      - sticky-note style, for a plain reminder panel
    "IMPORT_LOD":    "#9ccc65",   # light green - Import 3D Model + organize into LOD groups
    "DELETE_OBJ":    "#e53935",   # strong red  - deletes named object(s), deliberately alarming
    "ZERO_OUT":      "#64b5f6",   # sky blue    - resets named object(s)/control(s) to default
    "PARENT_OBJ":    "#ffa726",   # orange      - parents child object(s) under a parent
    "INSTANCE_OBJ":  "#ab47bc",   # purple      - creates preset-transform instances of an object
}

# Stage 17, request "different design per panel type", REVISED Stage 18
# (request "icons should be relatable to that panel, not random"): a small
# icon per type so panels are tellable apart at a glance without reading the
# title text. Each icon is picked to actually depict what that panel does:
# a snake for Python/MEL, a globe for "runs in Maya's global session", a
# cube for a 3D model import, a bone for a skinCluster/bind, a palette for
# control-shape curves, an outbox tray for "send this out" (publish), a
# puzzle piece for a module, and a level slider for "tweak" (weight nudging).
PANEL_TYPE_ICONS = {
    "SCRIPT":        "🐍",
    "GLOBAL_SCRIPT": "🌐",
    "IMPORT_3D":     "🧊",
    "JSON":          "🦴",
    "SHAPES":        "🎨",
    "PUBLISH":       "📤",
    "MODULE":        "🧩",
    "TWEAKER":       "🎚️",
    # Stage 20: LOD Loader builds an entire LOD's whole panel stack, so it
    # gets a "construction/assembly" icon distinct from every single-step type.
    "LOD_LOADER":    "🏗️",
    # Material panel: a paint bucket for "fills a mesh with its saved
    # shader/texture setup" - distinct from SHAPES' palette (that's curve
    # shapes, this is shading).
    "MATERIAL":      "🪣",
    # Note panel: a sticky note, for a plain free-text reminder - it isn't
    # a build step at all (see panel_run_label/SortablePanel.execute).
    "NOTE":          "🗒️",
    # Import 3D + LOD Organize: same cube as IMPORT_3D plus a building -
    # imports, then organizes the scene into LOD groups.
    "IMPORT_LOD":    "🏢",
    # Delete-by-name: a plain trash can - deliberately unambiguous.
    "DELETE_OBJ":    "🗑️",
    # Zero Out: a target/reset symbol for "back to default".
    "ZERO_OUT":      "🎯",
    # Parent: a link, for "attaches one thing under another".
    "PARENT_OBJ":    "🔗",
    # Instance Object: a cloning/duplication symbol - creates preset-
    # transform instances of a named object (see panel UI/execute below).
    "INSTANCE_OBJ":  "🧬",
}

# Stage 17: each panel type's DEFAULT background - a faint wash of its own
# accent colour blended into the old uniform #252526, instead of every panel
# type looking identical apart from the thin border stripe. Precomputed
# (base*0.84 + accent*0.16) rather than blended at runtime, to keep panel
# construction simple. A panel the user has manually recoloured (right-click
# -> Change Panel Color) keeps that choice - this is only ever the STARTING
# color for a newly created panel.
PANEL_TYPE_BG_TINT = {
    "SCRIPT":        "#2c3e47",
    "GLOBAL_SCRIPT": "#332e47",
    "IMPORT_3D":     "#3d3040",
    "JSON":          "#343f35",
    "SHAPES":        "#452f37",
    "PUBLISH":       "#443132",
    "MODULE":        "#263c3b",
    "TWEAKER":       "#2b4044",
    "LOD_LOADER":    "#463d20",
    "MATERIAL":      "#452f28",
    "NOTE":          "#252526",
    "IMPORT_LOD":    "#334a2c",
    "DELETE_OBJ":    "#452a29",
    "ZERO_OUT":      "#2a3c47",
    "PARENT_OBJ":    "#453b28",
    "INSTANCE_OBJ":  "#3a2f45",
}

# Stage 17, "these fields are where we're loading/saving a path, not typing
# one": the panel's main path field is made read-only for the types where
# the field is ALWAYS set by a button/menu action - Browse, Save Skin/
# Shapes, Switch Version - and never by hand. SCRIPT/GLOBAL_SCRIPT are
# excluded on purpose: that field can hold raw pasted code instead of a
# path. Stage 18 adds IMPORT_3D (now that MA/IMPORT_3D are one merged,
# always-Browse-set panel type - request #1).
READONLY_FIELD_TYPES = {"JSON", "SHAPES", "PUBLISH", "TWEAKER", "IMPORT_3D", "MATERIAL", "IMPORT_LOD"}

# Stage 18, request #4: every read-only field across the Rig Workspace uses
# this SAME colour, regardless of which panel type it belongs to - a single
# consistent "this is locked, set automatically" signal instead of Stage
# 17's per-type accent colouring (which made JSON's field green, SHAPES'
# pink, etc. - readable, but not "the same" the way the user asked for).
READONLY_FIELD_COLOR = "#a1887f"   # warm brown

def type_accent(p_type):
    return PANEL_TYPE_ACCENTS.get(p_type, "#2bb5a8")

def type_icon(p_type):
    return PANEL_TYPE_ICONS.get(p_type, "⚙️")

def type_bg_tint(p_type):
    return PANEL_TYPE_BG_TINT.get(p_type, "#252526")

def style_readonly_path_field(field, accent=None):
    """Give a read-only path field (JSON/SHAPES/PUBLISH/TWEAKER/IMPORT_3D's
    main field) a look that reads as 'loaded/saved automatically', distinct
    from a normal editable field. Stage 18: always uses READONLY_FIELD_COLOR
    now, the same brown for every panel type - the `accent` parameter is
    kept (unused) only so any external caller passing one doesn't break."""
    field.setReadOnly(True)
    field.setStyleSheet(
        f"background: #1a1a1a; border: 1px solid {READONLY_FIELD_COLOR}; color: {READONLY_FIELD_COLOR};"
        f" padding: 6px; font-family: 'Consolas';")
    field.setToolTip(
        "Set automatically by Browse, Save, or Switch Version - not typed by hand.")

def is_script_file_ref(text):
    """Stage 19: a SCRIPT/GLOBAL_SCRIPT panel's field can hold EITHER a path
    to a real .py/.mel file OR raw pasted code - only the first case should
    lock like the other path fields (there's a real file behind it, set by
    Browse, not typed by hand). Detected purely by the text ending in .py or
    .mel, same as the browse-file filters already assume."""
    t = (text or "").strip().lower()
    return t.endswith(".py") or t.endswith(".mel")

def panel_run_label(p_type):
    """The default label for a panel's main run/action button, per type.
    Shared by SortablePanel's init/execute/_normal_run_text and by
    SessionWorkspace.reset_scene_and_ui so every spot that decides this
    label agrees, instead of four separately hand-kept ternary chains."""
    if p_type in ("SCRIPT", "GLOBAL_SCRIPT"): return "RUN"
    if p_type == "PUBLISH": return "VALIDATE"
    if p_type == "TWEAKER": return "CREATE"
    # Stage 23: a LOD Loader panel runs in-sequence with every other panel
    # (ordered Build Till Here, etc) exactly like a normal step - "LOAD"
    # implied it was a separate, special action, so it now reads RUN too.
    if p_type == "LOD_LOADER": return "RUN"
    if p_type == "IMPORT_LOD": return "IMPORT & ORGANIZE"
    if p_type == "DELETE_OBJ": return "DELETE"
    if p_type == "ZERO_OUT": return "ZERO OUT"
    if p_type == "PARENT_OBJ": return "PARENT"
    if p_type == "INSTANCE_OBJ": return "🧬 CREATE INSTANCES"
    return "LOAD"


def prompt_skincluster_naming_check(parent, meshes=None, show_popup=True):
    """SkinCluster-naming check (Stage 16, request #1) - run right before a
    skin export or import, scoped to just the mesh(es) that save/import is
    actually about to touch, instead of scanning the whole scene at KRT
    launch the way this used to work. Warns if any of them has a
    skinCluster whose name doesn't match KRT's '<mesh>_SkinCluster'
    convention and offers to fix every mismatch in one click.

    Saving/importing skin never actually depends on this name - every
    lookup KRT does (find_mesh_skincluster, ensure_skin_ready_for_import,
    get_tweaker_target_meshes) resolves a skinCluster by construction
    history, never by name - so this is purely a keep-the-Outliner-tidy
    convenience. Cancel just proceeds with the save/import as normal.

    show_popup=False (the Rig Build workspace's "Show SkinCluster naming
    popup" checkbox, unchecked) skips the confirmation dialog entirely but
    keeps the check itself working exactly as before: any mismatch found
    is renamed right away, silently, and just logged to the script editor
    instead of interrupting the save/import with a window."""
    try:
        mismatches = find_mismatched_skinclusters(meshes=meshes)
    except Exception:
        traceback.print_exc()
        return
    if not mismatches:
        return

    if not show_popup:
        renamed = rename_mismatched_skinclusters(mismatches)
        cmds.warning("[KRT] Renamed {} skinCluster(s) to match convention (naming popup off).".format(renamed))
        return

    shown = mismatches[:20]
    lines = "\n".join("  {}  ->  {}".format(cur, can) for _, cur, can in shown)
    more = "" if len(mismatches) <= 20 else "\n  ...and {} more".format(len(mismatches) - 20)
    msg = (
        "{} mesh(es) involved in this save/import have a skinCluster whose name "
        "doesn't match KRT's naming convention (<mesh>_SkinCluster):\n\n{}{}\n\n"
        "Rename them now to match?"
    ).format(len(mismatches), lines, more)

    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("KRT - SkinCluster Naming")
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setText(msg)
    box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
    result = box.exec() if IS_PYSIDE6 else box.exec_()
    if result == QtWidgets.QMessageBox.Ok:
        renamed = rename_mismatched_skinclusters(mismatches)
        cmds.warning("[KRT] Renamed {} skinCluster(s) to match convention.".format(renamed))


class ErrorDialog(QtWidgets.QDialog):
    def __init__(self, title, msg, detail, parent=None, allow_retry=False):
        super(ErrorDialog, self).__init__(parent)
        self.retry = False
        self.setWindowTitle(title)
        self.setMinimumSize(600, 450)
        self.setStyleSheet("""
            QDialog { background-color: #252526; color: white; } 
            QTextEdit { color: #2bb5a8; font-family: Consolas; font-size: 13px; background: #1e1e1e; border: 1px solid #555; padding: 5px;} 
            QLabel { color: white; font-weight: bold; font-size: 14px; } 
            QPushButton { background-color: #3e3e42; color: white; font-weight: bold; padding: 8px 20px; font-size: 14px; border-radius: 4px;}
            QPushButton:hover { background-color: #555; }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(msg))
        
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(detail)
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        layout.addWidget(text_edit)
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        if allow_retry:
            btn_retry = QtWidgets.QPushButton("🔁 Retry")
            btn_retry.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
            btn_retry.clicked.connect(self._do_retry)
            btn_layout.addWidget(btn_retry)
        btn = QtWidgets.QPushButton("OK")
        btn.clicked.connect(self.accept)
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

    def _do_retry(self):
        self.retry = True
        self.accept()

class GraphNodeOrderDialog(QtWidgets.QDialog):
    """Pick any number of Graph Editor modules, and the exact order they
    should be added to a bubble panel in, in one popup - replaces having
    to select one module at a time in the sidebar and use 'Add from Graph
    Editor' repeatedly for a multi-module panel.

    Modules already in the target panel (existing_uuids, in their current
    bubble order) are pre-numbered here from the start, exactly reflecting
    "last time's" pick order, and are LOCKED - clicking one does nothing,
    since it's already a real bubble in the panel and this dialog only
    ever adds new ones. Any newly-clicked module is appended after all of
    those, so opening this dialog again to add just one more module never
    reshuffles what's already there; the caller only creates bubbles for
    the newly-clicked ones (see its own filtering against existing_uuids)."""

    def __init__(self, nodes, existing_uuids=None, parent=None):
        super(GraphNodeOrderDialog, self).__init__(parent)
        self.nodes = nodes  # list of RigNode, offered in graph/alphabetical order
        node_by_uuid = {n.uuid: n for n in self.nodes}
        # Pre-seed with whatever's already in the panel, in ITS current
        # order - "the order i selected last time" - so the numbering
        # picks up where it left off instead of starting over at 1 and
        # losing all prior work every time this dialog is reopened.
        self.locked_uuids = set(existing_uuids or [])
        self.order = [node_by_uuid[u] for u in (existing_uuids or []) if u in node_by_uuid]

        self.setWindowTitle("Add Modules from Graph Editor")
        self.setMinimumSize(380, 420)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QLabel { color: #cccccc; }
            QListWidget { background: #141414; border: 1px solid #333; color: white; }
            QListWidget::item { padding: 5px; }
            QPushButton { background: #333; color: white; padding: 6px 14px; border-radius: 3px; }
            QPushButton:hover { background: #444; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Click modules below in the order you want them added to this panel.\n"
            "Click an already-picked module again to remove it from the list.\n"
            "Modules already in this panel (\U0001F512, numbered from last time) are "
            "locked here - new picks are simply appended after them."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for node in self.nodes:
            item = QtWidgets.QListWidgetItem(node.display_title)
            item.setData(QtCore.Qt.UserRole, node.uuid)
            self.list_widget.addItem(item)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        btn_row = QtWidgets.QHBoxLayout()
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.setToolTip("Clears newly-picked modules only - modules already in the panel (locked) stay.")
        btn_clear.clicked.connect(self._clear_order)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QtWidgets.QPushButton("Add Selected")
        btn_ok.setStyleSheet("background-color: #2bb5a8; color: black; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._refresh_labels()

    def _on_item_clicked(self, item):
        node_uuid = item.data(QtCore.Qt.UserRole)
        if node_uuid in self.locked_uuids:
            return  # already a real bubble in the panel - not editable here
        node = next((n for n in self.nodes if n.uuid == node_uuid), None)
        if not node:
            return
        if node in self.order:
            self.order.remove(node)
        else:
            self.order.append(node)
        self._refresh_labels()

    def _clear_order(self):
        # Only drop the newly-picked (unlocked) modules - what's already
        # in the panel isn't touched by this dialog at all, so there's
        # nothing here to "clear" for it.
        self.order = [n for n in self.order if n.uuid in self.locked_uuids]
        self._refresh_labels()

    def _refresh_labels(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            node_uuid = item.data(QtCore.Qt.UserRole)
            node = next((n for n in self.nodes if n.uuid == node_uuid), None)
            if not node:
                continue
            locked = node_uuid in self.locked_uuids
            if node in self.order:
                idx = self.order.index(node) + 1
                if locked:
                    item.setText(f"{idx}. \U0001F512 {node.display_title}")
                    item.setBackground(QtGui.QColor("#2a2a2a"))
                    item.setForeground(QtGui.QColor("#888888"))
                else:
                    item.setText(f"{idx}. {node.display_title}")
                    item.setBackground(QtGui.QColor("#2bb5a8"))
                    item.setForeground(QtGui.QColor("black"))
            else:
                item.setText(node.display_title)
                item.setBackground(QtGui.QColor("#141414"))
                item.setForeground(QtGui.QColor("white"))

class ModuleBubble(QtWidgets.QFrame):
    closed = QtCore.Signal(object)
    execute_req = QtCore.Signal(object)
    # Stage 30: "if there are lot of modules so user can hilight that
    # module in graph" - a small locate/target button, shown on hover next
    # to the close "x", that asks the panel to select & center this
    # bubble's actual graph node in the Graph Editor. Left-clicking the
    # bubble's own text still runs it instantly, unchanged - this is a
    # separate, additional affordance, not a replacement for that.
    locate_req = QtCore.Signal(object)

    def __init__(self, text, full_path, parent=None, is_active=True):
        super(ModuleBubble, self).__init__(parent)
        self.text = text
        self.full_path = full_path
        self.is_active = is_active
        self.setContentsMargins(5, 2, 5, 2)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(5)
        
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(self.is_active)
        self.checkbox.setToolTip("Toggle to include or exclude this module from the build")
        self.checkbox.toggled.connect(self.toggle_active)

        self.btn_text = QtWidgets.QPushButton(text)
        self.btn_text.setFlat(True)
        self.btn_text.setToolTip("Click to execute only this module instantly - click and drag to reorder it")
        self.btn_text.clicked.connect(lambda: self.execute_req.emit(self))
        self._drag_start_pos = None
        self.btn_text.installEventFilter(self)

        # Stage 30: only meaningful for a GRAPH:: bubble (a real graph node)
        # - a plain file-path bubble (Browse from File) has no graph node to
        # locate, so this stays hidden for those (see toggle_active/below).
        self.locate_btn = QtWidgets.QPushButton("◎")
        self.locate_btn.setFixedSize(16, 16)
        self.locate_btn.setFlat(True)
        self.locate_btn.setToolTip("Select & center this module in the Graph Editor")
        self.locate_btn.setStyleSheet("color: transparent; font-weight: bold; border: none;")
        self.locate_btn.clicked.connect(lambda: self.locate_req.emit(self))
        self.locate_btn.setVisible(full_path.startswith("GRAPH::"))

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setFlat(True)
        self.close_btn.setToolTip("Remove this module")
        self.close_btn.setStyleSheet("color: transparent; font-weight: bold; border: none;")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))

        layout.addWidget(self.checkbox)
        layout.addWidget(self.btn_text)
        layout.addWidget(self.locate_btn)
        layout.addWidget(self.close_btn)

        self.toggle_active(self.is_active)

    def toggle_active(self, state):
        self.is_active = state
        if state:
            self.setStyleSheet("QFrame { background-color: #3e3e42; border-radius: 10px; border: 1px solid #555; color: #ccc; } QFrame:hover { border: 1px solid #2bb5a8; }")
            self.btn_text.setStyleSheet("color: #ccc; font-weight: normal; border: none; background: transparent; text-align: left; padding: 0px;")
        else:
            self.setStyleSheet("QFrame { background-color: #5a2a2a; border-radius: 10px; border: 1px solid #f44336; color: #ccc; }")
            self.btn_text.setStyleSheet("color: #ff9999; font-weight: normal; border: none; background: transparent; text-align: left; padding: 0px;")

    def set_success(self):
        self.setStyleSheet("QFrame { background-color: #2e4a2e; border-radius: 10px; border: 1px solid #4CAF50; color: #ccc; }")
        self.btn_text.setStyleSheet("color: #aaddaa; font-weight: bold; border: none; background: transparent; text-align: left; padding: 0px;")
        
    def set_error(self):
        self.setStyleSheet("QFrame { background-color: #5a2a2a; border-radius: 10px; border: 1px solid #f44336; color: #ccc; }")
        self.btn_text.setStyleSheet("color: #ff9999; font-weight: bold; border: none; background: transparent; text-align: left; padding: 0px;")

    def reset_style(self):
        self.toggle_active(self.is_active)

    def enterEvent(self, event):
        self.close_btn.setStyleSheet("color: #2bb5a8; font-weight: bold; border: none; background: transparent;")
        if self.locate_btn.isVisible():
            self.locate_btn.setStyleSheet("color: #4ec9ff; font-weight: bold; border: none; background: transparent;")
        super(ModuleBubble, self).enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.setStyleSheet("color: transparent; border: none; background: transparent;")
        self.locate_btn.setStyleSheet("color: transparent; border: none; background: transparent;")
        super(ModuleBubble, self).leaveEvent(event)

    def eventFilter(self, obj, event):
        # btn_text would otherwise swallow every mouse press for its own
        # click handling, so a plain mousePressEvent/mouseMoveEvent override
        # on this QFrame would never fire when the drag starts on top of the
        # button (which is almost the whole bubble). Watching the button's
        # own events here instead lets a short click still execute the
        # module (btn_text.clicked, untouched) while a press-and-drag past
        # the drag threshold reorders the bubble instead - swallowing the
        # move/release so the button never also fires a click for it.
        if obj is self.btn_text:
            et = event.type()
            if et == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self._drag_start_pos = event.pos()
            elif et == QtCore.QEvent.MouseMove and self._drag_start_pos is not None \
                    and (event.buttons() & QtCore.Qt.LeftButton):
                if (event.pos() - self._drag_start_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    self._drag_start_pos = None
                    self.btn_text.setDown(False)
                    self._start_drag()
                    return True
            elif et in (QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.Leave):
                self._drag_start_pos = None
        return super(ModuleBubble, self).eventFilter(obj, event)

    def _find_panel(self):
        p = self.parentWidget()
        while p is not None and not isinstance(p, SortableBubblePanel):
            p = p.parentWidget()
        return p

    def _start_drag(self):
        panel = self._find_panel()
        if panel is None:
            return
        panel.dragging_bubble = self
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText("krt_bubble_drag")
        drag.setMimeData(mime)
        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QtCore.QPoint(10, 10))
        # The real bubble stays put and visible in its old spot for the
        # whole drag - it used to be hidden here so FlowLayout would close
        # its hole immediately, but that hide/show toggle raced with the
        # layout's own (partly deferred) relayout during rapid drag-move
        # events and could leave a bubble stuck invisible, or overlapping
        # the live drop-gap placeholder, if the drag ended mid-relayout.
        # BubbleDropArea._target_index already excludes this bubble from
        # its own position/index math regardless of visibility, so leaving
        # it visible costs nothing functionally - it just means the drag
        # now looks like "old spot stays, dashed gap shows where it'll
        # land", which is also the more familiar drag-and-drop convention.
        try:
            if IS_PYSIDE6:
                drag.exec(QtCore.Qt.MoveAction)
            else:
                drag.exec_(QtCore.Qt.MoveAction)
        finally:
            panel._clear_drop_gap()
            panel.dragging_bubble = None

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

class _BubbleDropGap(QtWidgets.QFrame):
    """A dashed-outline pill shown live while a ModuleBubble is being
    dragged over its panel's BubbleDropArea - tracks the mouse and marks
    exactly where the bubble will land if dropped right now. Purely a
    visual stand-in: it's inserted into the real bubble_layout (so the
    other bubbles actually make room / wrap around it, not just an overlay
    drawn on top), but it's never a real module and is always removed the
    instant the drag ends, drop or not."""
    def __init__(self, size):
        super(_BubbleDropGap, self).__init__()
        self._size = size
        self.setFixedSize(size)
        self.setStyleSheet(
            "QFrame { background-color: rgba(43, 181, 168, 45); "
            "border: 2px dashed #2bb5a8; border-radius: 10px; }")

    def sizeHint(self):
        return self._size


class BubbleDropArea(QtWidgets.QWidget):
    """The horizontal strip of ModuleBubble pills inside one SortableBubblePanel.
    Accepts a bubble being dragged (see ModuleBubble._start_drag) and
    reorders it within this same panel - same left/right positioning idea as
    DragDropContainer above, just scoped to one panel's own bubbles instead
    of panels within a whole LOD.

    Rows wrap (FlowLayout, Stage 35), so figuring out "where will this drop"
    from the mouse position needs both axes: _target_index() below groups
    the panel's current bubbles into rows by their y-center, picks the row
    closest to the cursor, then finds the slot within that row by x. The
    previous version only ever compared x - fine for a single row, but once
    bubbles wrapped onto a second/third row it had no idea which row the
    cursor was actually over, so dragging into a later row could silently
    reorder into the wrong one. dragMoveEvent uses the same index to move a
    live dashed-outline gap (_BubbleDropGap) into place as you drag, so
    there's always a visible answer to "where can i drop it" instead of
    finding out only after releasing the mouse."""
    def __init__(self, panel):
        super(BubbleDropArea, self).__init__()
        self.panel = panel
        self.setAcceptDrops(True)

    def _target_index(self, pos, bubble):
        """Which REAL bubble (the dragged bubble itself, and the live
        drop-gap placeholder if one is currently shown, are both excluded)
        the drop should land BEFORE - returned as that widget itself, not
        a numeric count. It used to be a numeric "real bubbles only" count,
        but that count doesn't map back onto a raw layout.insertWidget()
        position once the dragged bubble is still sitting somewhere in the
        raw layout in between (it's excluded from the COUNT but not from
        the actual list) - the numeric index would silently drift off by
        however many excluded items came before it, which is exactly what
        could make the gap (and, after drop, the bubble itself) land one
        slot off and visually overlap a neighbour. Returning the target
        widget instead sidesteps that: _show_drop_gap and dropEvent below
        both resolve it with a fresh layout.indexOf() right before they
        act, so they always agree with wherever things actually are RIGHT
        NOW, however many hidden/excluded items sit in between. None means
        "after every real bubble" (append at the end)."""
        layout = self.panel.bubble_layout
        gap = getattr(self.panel, "drop_gap", None)
        rows = []  # [[row_y_center, [widget, ...]], ...] - real bubbles only
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is None or w is bubble or w is gap or not w.isVisible():
                continue
            cy = w.geometry().center().y()
            row = next((r for r in rows if abs(r[0] - cy) <= w.height() / 2), None)
            if row is None:
                rows.append([cy, []])
                row = rows[-1]
            row[1].append(w)
        if not rows:
            return None
        for row in rows:
            row[1].sort(key=lambda w: w.geometry().x())

        rows_sorted = sorted(rows, key=lambda r: r[0])
        target_row = min(rows_sorted, key=lambda r: abs(r[0] - pos.y()))
        for w in target_row[1]:
            if pos.x() < w.geometry().center().x():
                return w
        # Past every bubble on the closest row - land right after the last
        # one on THAT row (i.e. right before the first bubble of the NEXT
        # row, if any), not at the very end of the whole panel - that
        # mix-up is exactly what an x-only compare used to cause when
        # dragging into anything but the first row.
        row_idx = rows_sorted.index(target_row)
        if row_idx + 1 < len(rows_sorted):
            return rows_sorted[row_idx + 1][1][0]
        return None

    def dragEnterEvent(self, event):
        if getattr(self.panel, 'dragging_bubble', None) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        bubble = getattr(self.panel, 'dragging_bubble', None)
        if bubble is None:
            return
        event.acceptProposedAction()
        pos = event.pos() if hasattr(event, "pos") else event.position().toPoint()
        target_widget = self._target_index(pos, bubble)
        self.panel._show_drop_gap(self, bubble.size(), target_widget)

    def dragLeaveEvent(self, event):
        self.panel._clear_drop_gap()
        super(BubbleDropArea, self).dragLeaveEvent(event)

    def dropEvent(self, event):
        bubble = getattr(self.panel, 'dragging_bubble', None)
        if bubble is None:
            event.ignore()
            return

        pos = event.pos() if hasattr(event, "pos") else event.position().toPoint()
        # target_widget is the real bubble to land BEFORE (or None for "at
        # the end") - see _target_index's docstring for why this is a
        # widget reference rather than a numeric count. Resolved into an
        # actual raw layout index via indexOf() below, AFTER bubble is
        # removed from the layout, so it's always correct regardless of
        # where bubble or the gap placeholder currently sit underneath it.
        target_widget = self._target_index(pos, bubble)
        self.panel._clear_drop_gap()

        layout = self.panel.bubble_layout
        if layout.indexOf(bubble) != -1:
            layout.removeWidget(bubble)
        target_index = layout.indexOf(target_widget) if target_widget is not None else layout.count()
        if target_index == -1:
            target_index = layout.count()
        layout.insertWidget(target_index, bubble)

        self.panel.dragging_bubble = None
        event.acceptProposedAction()


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


class CacheMixin(object):
    """Per-step scene caching. A cache is a full Maya scene snapshot (.ma)
    saved AFTER this step runs, so loading it restores the accumulated state
    of every step up to and including this one."""

    def get_cache_path(self):
        try:
            cdir = self.workspace.get_cache_dir()
        except Exception:
            return ""
        if not getattr(self, "uuid", ""):
            self.uuid = uuid.uuid4().hex
        return os.path.join(cdir, self.uuid + ".ma").replace("\\", "/")

    def has_cache(self):
        p = self.get_cache_path()
        return bool(p) and os.path.isfile(p)

    def cache_marked(self):
        """True when this step is ticked for automatic caching during a build."""
        chk = getattr(self, "chk_cache", None)
        return bool(chk) and chk.isChecked()

    def set_cache_marked(self, on):
        chk = getattr(self, "chk_cache", None)
        if chk is not None:
            chk.setChecked(bool(on))

    def _build_cache_tick(self, layout):
        """The right-side 'Cache' tick: only ticked steps are auto-cached during
        a build. Separate from the left enable/disable checkbox."""
        self.chk_cache = QtWidgets.QCheckBox("Cache")
        self.chk_cache.setChecked(False)
        self.chk_cache.setToolTip(
            "Tick to cache this step during a build.\n"
            "Only ticked steps are auto-cached; the 💾 button still caches manually.")
        self.chk_cache.setStyleSheet("QCheckBox { color: #cccccc; font-size: 12px; margin-left: 6px; }")
        layout.addWidget(self.chk_cache)

    def _build_cache_controls(self, layout):
        self.btn_cache_rem = QtWidgets.QPushButton("🗑")
        self.btn_cache_rem.setFixedWidth(30)
        self.btn_cache_rem.setToolTip("Remove this step's cache")
        self.btn_cache_rem.clicked.connect(self.remove_cache)

        self.btn_cache_save = QtWidgets.QPushButton("💾")
        self.btn_cache_save.setFixedWidth(30)
        self.btn_cache_save.setToolTip("Cache this step (save current scene snapshot)")
        self.btn_cache_save.clicked.connect(lambda: self.cache_now())

        self.btn_cache_run = QtWidgets.QPushButton("⏩")
        self.btn_cache_run.setFixedWidth(30)
        self.btn_cache_run.setToolTip(
            "Load this step's cached scene.\n"
            "Right-click for 'Build from here' (load cache + continue building).")
        self.btn_cache_run.clicked.connect(self.run_from_cache)
        self.btn_cache_run.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_cache_run.customContextMenuRequested.connect(self._cache_run_menu)

        layout.addWidget(self.btn_cache_rem)
        layout.addWidget(self.btn_cache_save)
        layout.addWidget(self.btn_cache_run)
        self.refresh_cache_ui()

    def refresh_cache_ui(self):
        if not hasattr(self, "btn_cache_run"):
            return
        has = self.has_cache()
        self.btn_cache_run.setEnabled(has)
        self.btn_cache_rem.setEnabled(has)
        if has:
            self.btn_cache_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
            self.btn_cache_save.setToolTip("Cached ✓ - click to re-cache the current scene")
        else:
            self.btn_cache_save.setStyleSheet("")
            self.btn_cache_save.setToolTip("Cache this step (save current scene snapshot)")

    def cache_now(self, silent=False):
        path = self.get_cache_path()
        if not path:
            cmds.warning("Cache directory unavailable.")
            return False
        try:
            cmds.file(path, force=True, type="mayaAscii", exportAll=True,
                      preserveReferences=False, constructionHistory=True,
                      channels=True, constraints=True, expressions=True, shader=True)
            self.refresh_cache_ui()
            if not silent:
                cmds.warning(f"Cached step: {self.title_edit.text()}")
            return True
        except Exception:
            if not silent:
                cmds.warning(f"Cache failed for '{self.title_edit.text()}':\n{traceback.format_exc()}")
            return False

    def run_from_cache(self):
        """Left-click of the ⏩ button: just load this step's cached scene."""
        if not self.has_cache():
            cmds.warning("No cache exists for this step yet.")
            return False
        return self.workspace.load_cache_only(self)

    def build_from_cache(self):
        """Load this step's cache, then continue building the remaining steps."""
        if not self.has_cache():
            cmds.warning("No cache exists for this step yet.")
            return False
        return self.workspace.build_from_cache(self)

    def _cache_run_menu(self, pos):
        menu = QtWidgets.QMenu(self.btn_cache_run)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        a_load = menu.addAction("📂 Load cached scene")
        a_build = menu.addAction("⏩ Build from here (load cache + continue)")
        has = self.has_cache()
        a_load.setEnabled(has); a_build.setEnabled(has)
        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if action == a_load: self.run_from_cache()
        elif action == a_build: self.build_from_cache()

    def cache_on_manual_run(self):
        """After a manual RUN/LOAD click succeeds, (re)cache this step and drop the
        now-stale caches of every step after it. Respects the global cache toggle."""
        try:
            if not self.workspace.cache_steps_enabled():
                return
            if not self.cache_marked():
                return
            self.cache_now(silent=True)
            self.workspace.remove_caches_from(self, inclusive=False)
        except Exception:
            pass

    def remove_cache(self):
        # Removing a step's cache also invalidates every downstream cache,
        # so cascade the deletion to this step and all steps after it.
        n = self.workspace.remove_caches_from(self, inclusive=True)
        if n:
            cmds.warning(f"Removed {n} cache(s), from '{self.title_edit.text()}' onward.")
        else:
            cmds.warning("No cache files to remove.")
        self.refresh_cache_ui()


class TweakerVertexGroup(QtWidgets.QFrame):
    """Stage 21, request #1: one independent vertex group inside a Tweaker
    panel. A Tweaker panel can hold several of these (SortablePanel's
    "+ Add Vertex Group" button) - each one targets its OWN vertex names
    (which can come from an entirely different source mesh than another
    group in the same panel), has its own Additional Meshes list, and its
    own Use Bind Scale / Influence Radius / Full Weight Radius / Falloff
    settings - and each runs as its own independent tweaker setup when the
    panel's CREATE button fires (see SortablePanel._execute_tweaker)."""

    removed = QtCore.Signal(object)

    def __init__(self, parent=None):
        super(TweakerVertexGroup, self).__init__(parent)
        self.setStyleSheet(
            "TweakerVertexGroup { background: #202225; border: 1px solid #3a3a3a; border-radius: 4px; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        vtx_row = QtWidgets.QHBoxLayout()
        vtx_row.addWidget(QtWidgets.QLabel("Vertices:"))
        self.vertex_field = QtWidgets.QLineEdit()
        self.vertex_field.setPlaceholderText("mesh.vtx[123], mesh.vtx[456], ... - leave empty for selection")
        btn_get_vtx = QtWidgets.QPushButton("Get Selected")
        btn_get_vtx.setToolTip("Store the currently selected vertices into this field.")
        btn_get_vtx.clicked.connect(self.get_selection_for_vertices)
        btn_select_vtx = QtWidgets.QPushButton("🎯 Select")
        btn_select_vtx.setToolTip("Select the vertices listed in this field in the viewport.")
        btn_select_vtx.clicked.connect(self.select_vertices)
        vtx_row.addWidget(self.vertex_field)
        vtx_row.addWidget(btn_get_vtx)
        vtx_row.addWidget(btn_select_vtx)
        self.btn_remove = QtWidgets.QPushButton("×")
        self.btn_remove.setFixedSize(20, 20)
        self.btn_remove.setToolTip("Remove this vertex group")
        self.btn_remove.setStyleSheet("color: #e57373; font-weight: bold;")
        self.btn_remove.clicked.connect(lambda: self.removed.emit(self))
        vtx_row.addWidget(self.btn_remove)
        layout.addLayout(vtx_row)

        mesh_row = QtWidgets.QHBoxLayout()
        mesh_row.addWidget(QtWidgets.QLabel("Additional Meshes:"))
        self.mesh_field = QtWidgets.QLineEdit()
        self.mesh_field.setPlaceholderText("Extra meshes (cloth/hair/jewelry/etc) to bind to the same tweaker offsets...")
        btn_get_mesh = QtWidgets.QPushButton("Get Selected")
        btn_get_mesh.setToolTip("Store the currently selected meshes into this field.")
        btn_get_mesh.clicked.connect(self.get_selection_for_meshes)
        btn_select_mesh = QtWidgets.QPushButton("🎯 Select")
        btn_select_mesh.setToolTip("Select the meshes listed in this field in the viewport.")
        btn_select_mesh.clicked.connect(self.select_meshes)
        mesh_row.addWidget(self.mesh_field)
        mesh_row.addWidget(btn_get_mesh)
        mesh_row.addWidget(btn_select_mesh)
        layout.addLayout(mesh_row)

        opt_row = QtWidgets.QHBoxLayout()
        self.chk_use_bind_scale = QtWidgets.QCheckBox("Use Bind Scale")
        self.chk_use_bind_scale.setChecked(True)
        self.chk_use_bind_scale.setToolTip(
            "On: the tweaker mesh is built at the Bind Scale value below (matches "
            "a rig scaled down to real-world size).\n"
            "Off: the tweaker mesh keeps the source mesh's own current scale - "
            "Bind Scale is ignored.")
        opt_row.addWidget(self.chk_use_bind_scale)
        self.field_bind_scale = QtWidgets.QLineEdit("0.01")
        self.field_bind_scale.setFixedWidth(50)
        self.field_bind_scale.setToolTip(
            "The fixed scale the tweaker mesh is built at when Use Bind Scale is on "
            "(TweakerMain's own bind_scale).")
        opt_row.addWidget(self.field_bind_scale)
        opt_row.addWidget(QtWidgets.QLabel("Influence Radius:"))
        self.field_influence_radius = QtWidgets.QLineEdit("0.08")
        self.field_influence_radius.setFixedWidth(55)
        opt_row.addWidget(self.field_influence_radius)
        opt_row.addWidget(QtWidgets.QLabel("Full Weight Radius:"))
        self.field_full_weight_radius = QtWidgets.QLineEdit("0.0001")
        self.field_full_weight_radius.setFixedWidth(60)
        opt_row.addWidget(self.field_full_weight_radius)
        opt_row.addWidget(QtWidgets.QLabel("Falloff:"))
        self.field_falloff = QtWidgets.QLineEdit("2.0")
        self.field_falloff.setFixedWidth(45)
        opt_row.addWidget(self.field_falloff)
        opt_row.addStretch()
        layout.addLayout(opt_row)

    def get_selection_for_vertices(self):
        sel = cmds.ls(sl=True, flatten=True) or []
        verts = [v for v in sel if ".vtx[" in v]
        if verts: self.vertex_field.setText(",".join(verts))
        else: cmds.warning("No vertices selected.")

    def select_vertices(self):
        verts = [v.strip() for v in self.vertex_field.text().split(",") if v.strip()]
        if not verts:
            cmds.warning("No vertices listed - use 'Get Selected' first, or type vertex names.")
            return
        existing = [v for v in verts if ".vtx[" in v and cmds.objExists(v.split(".vtx[")[0])]
        if not existing:
            cmds.warning("None of the listed vertices' meshes exist in the scene.")
            return
        cmds.select(existing, replace=True)
        cmds.warning("Selected {} vertex(es).".format(len(existing)))

    def get_selection_for_meshes(self):
        sel = cmds.ls(sl=True)
        if sel: self.mesh_field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def select_meshes(self):
        meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
        if not meshes:
            cmds.warning("No meshes listed - use 'Get Selected' first, or type mesh names.")
            return
        existing = [m for m in meshes if cmds.objExists(m)]
        missing = [m for m in meshes if not cmds.objExists(m)]
        if not existing:
            cmds.warning("None of the listed meshes exist in the scene: {}".format(", ".join(meshes)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} mesh(es). Not found: {}".format(len(existing), ", ".join(missing)))
        else:
            cmds.warning("Selected {} mesh(es).".format(len(existing)))

    def to_dict(self):
        return {
            "vertices": self.vertex_field.text(),
            "meshes": self.mesh_field.text(),
            "use_bind_scale": self.chk_use_bind_scale.isChecked(),
            "bind_scale": self.field_bind_scale.text(),
            "influence_radius": self.field_influence_radius.text(),
            "full_weight_radius": self.field_full_weight_radius.text(),
            "falloff": self.field_falloff.text(),
        }

    def from_dict(self, d):
        if not d:
            return
        if d.get("vertices"): self.vertex_field.setText(d.get("vertices"))
        if d.get("meshes"): self.mesh_field.setText(d.get("meshes"))
        if "use_bind_scale" in d: self.chk_use_bind_scale.setChecked(d.get("use_bind_scale"))
        if d.get("bind_scale") is not None: self.field_bind_scale.setText(str(d.get("bind_scale")))
        if d.get("influence_radius"): self.field_influence_radius.setText(str(d.get("influence_radius")))
        if d.get("full_weight_radius"): self.field_full_weight_radius.setText(str(d.get("full_weight_radius")))
        if d.get("falloff"): self.field_falloff.setText(str(d.get("falloff")))


class _NoteVerticalResizeHandle(QtWidgets.QFrame):
    """A thin drag handle below a NOTE panel's text box - lets the user
    resize the note's HEIGHT only by dragging it up/down, never its width
    (the panel's width is always dictated by the Rig Build Workspace
    column it sits in, so a horizontal grip wouldn't do anything useful
    anyway). Drives note_edit.setFixedHeight() directly, clamped to a
    sane range."""
    def __init__(self, note_edit, min_height=40, max_height=1200, on_resize=None):
        super(_NoteVerticalResizeHandle, self).__init__()
        self.note_edit = note_edit
        self.min_height = min_height
        self.max_height = max_height
        # Called with the new height on every drag step, so the owning
        # panel can keep its own note_height attribute (saved/loaded with
        # the pipeline JSON) in sync with whatever the user drags to.
        self.on_resize = on_resize
        self._dragging = False
        self._drag_start_y = 0
        self._start_height = 0
        self.setFixedHeight(8)
        self.setCursor(QtCore.Qt.SizeVerCursor)
        self.setStyleSheet("QFrame { background: #3a3a3a; border-radius: 2px; }"
                            " QFrame:hover { background: #2bb5a8; }")
        self.setToolTip("Drag to resize the note's height (vertical only).")

    def _event_global_y(self, event):
        # PySide6 deprecated globalPos() in favor of globalPosition(); this
        # keeps the handle working under either binding, same reasoning as
        # the pos()/position() compat checks used elsewhere in this file.
        if hasattr(event, "globalPosition"):
            return event.globalPosition().y()
        return event.globalPos().y()

    def mousePressEvent(self, event):
        self._dragging = True
        self._drag_start_y = self._event_global_y(event)
        self._start_height = self.note_edit.height()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = self._event_global_y(event) - self._drag_start_y
        new_height = max(self.min_height, min(self.max_height, int(self._start_height + delta)))
        self.note_edit.setFixedHeight(new_height)
        if self.on_resize:
            self.on_resize(new_height)

    def mouseReleaseEvent(self, event):
        self._dragging = False


class SortablePanel(CacheMixin, QtWidgets.QFrame):
    def __init__(self, title, p_type, default_val, workspace):
        super(SortablePanel, self).__init__()
        self.p_type = p_type
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint(p_type)
        self.accent = type_accent(p_type)
        self.uuid = uuid.uuid4().hex

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Toggle to include or exclude this panel from the main build")
        self.checkbox.toggled.connect(self.toggle_active)

        # Stage 17: a per-type icon, separate from the (renamable) title text
        # itself, so panel type reads at a glance even after a custom title.
        self.icon_label = QtWidgets.QLabel(type_icon(p_type))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip(p_type.replace("_", " ").title())

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox)
        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_edit)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        self.btn_del.setToolTip("Delete this panel completely")
        ctrl_layout.addWidget(self.btn_del)

        self.field = QtWidgets.QLineEdit(default_val)
        self.field.setToolTip("Path to the file, directory, or direct Python code")
        if p_type in READONLY_FIELD_TYPES:
            style_readonly_path_field(self.field, self.accent)
        elif p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ"):
            # Stage 19: this field locks itself the moment it holds a real
            # .py/.mel file path (same "set automatically, not typed by
            # hand" reasoning as the other read-only fields) but stays
            # editable for raw pasted code - see is_script_file_ref() and
            # _update_script_field_lock() below. INSTANCE_OBJ (Stage 40)
            # reuses this same field as its OPTIONAL custom transform
            # script - see the p_type == "INSTANCE_OBJ" block further down
            # for its own target_field/Delete All Instances UI.
            self.field.textChanged.connect(self._update_script_field_lock)
            self._update_script_field_lock()
        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.setToolTip("More Options, Adds, Copy & Paste")

        btn_txt = panel_run_label(p_type)
        self.btn_run = QtWidgets.QPushButton(btn_txt)
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")

        if p_type in ("NOTE", "DELETE_OBJ", "ZERO_OUT", "PARENT_OBJ"):
            # None of these types show the generic path/code field (see
            # below - it's hidden for all of them, they each have their
            # own dedicated name field instead), so Delete/More-Options go
            # up into the header row instead of sitting in a body row with
            # no field to anchor them - same top-right corner every other
            # card-style UI puts them in, and it's what keeps the cache/
            # RUN row below from looking lopsided with no field widget to
            # give it its usual shape.
            header_layout.addLayout(ctrl_layout)
            header_layout.addWidget(btn_dots)
        else:
            body_layout.addLayout(ctrl_layout)
            body_layout.addWidget(self.field)
            body_layout.addWidget(btn_dots)

        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT", "INSTANCE_OBJ"):
            self.func_field = QtWidgets.QLineEdit()
            self.func_field.setPlaceholderText("Function (e.g. utils())")
            self.func_field.setFixedWidth(130)
            if self.p_type == "INSTANCE_OBJ":
                self.func_field.setToolTip(
                    "Optional - exec'd after the custom script above; leave "
                    "a 'transforms' list behind (same variable the script "
                    "itself can also set directly).")
            body_layout.addWidget(self.func_field)

        self._build_cache_controls(body_layout)
        body_layout.addWidget(self.btn_run)

        # Small reset button shown only when the panel is in the SHOW ERROR state.
        # Clicking it restores the run button to normal WITHOUT re-running.
        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        body_layout.addWidget(self.btn_reset_err)

        # Per-panel "Popup" tick: only JSON/Tweaker panels ever trigger the
        # SkinCluster-naming confirmation (prompt_skincluster_naming_check),
        # on both Save and Load - this lives right on the panel itself
        # (same row as the Cache tick) instead of a single workspace-wide
        # setting, so a rig with a lot of pre-existing mismatched names can
        # be silenced panel-by-panel without turning the popup off
        # everywhere. Unticking it does NOT skip the check itself - any
        # mismatch found is still renamed automatically, just without the
        # confirmation window (see naming_popup_enabled()).
        if p_type in ("JSON", "TWEAKER"):
            self.chk_naming_popup = QtWidgets.QCheckBox("Popup")
            self.chk_naming_popup.setChecked(True)
            self.chk_naming_popup.setToolTip(
                "When on, saving or loading a skin on this panel that finds "
                "skinCluster(s)\nnamed off KRT's '<mesh>_SkinCluster' convention pops up "
                "a confirmation\nbefore renaming them. Turn off to stop the popup on this "
                "panel - any\nmismatch found is still renamed automatically, just "
                "silently (logged to\nthe script editor instead).")
            self.chk_naming_popup.setStyleSheet("QCheckBox { color: #cccccc; font-size: 12px; margin-left: 6px; }")
            body_layout.addWidget(self.chk_naming_popup)

        self._build_cache_tick(body_layout)
        main_layout.addLayout(body_layout)

        if p_type == "JSON":
            skin_ext_layout = QtWidgets.QHBoxLayout()
            skin_ext_layout.setContentsMargins(25, 0, 0, 0)
            skin_ext_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText("Leave empty for selection...")
            btn_get_sel = QtWidgets.QPushButton("Get Selected")
            btn_get_sel.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes.clicked.connect(self.select_skin_meshes)
            skin_ext_layout.addWidget(self.mesh_field)
            skin_ext_layout.addWidget(btn_get_sel)
            skin_ext_layout.addWidget(btn_select_meshes)
            main_layout.addLayout(skin_ext_layout)

            joints_layout = QtWidgets.QHBoxLayout()
            joints_layout.setContentsMargins(25, 0, 0, 0)
            joints_layout.addWidget(QtWidgets.QLabel("Joints:"))
            self.joints_field = QtWidgets.QLineEdit()
            self.joints_field.setPlaceholderText("Influences for Bind All - auto-filled from the current skin on Save if left empty...")
            btn_get_sel_j = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_j.setToolTip("Store the currently selected joints into this field.")
            btn_get_sel_j.clicked.connect(self.get_selection_for_joints)
            btn_select_joints = QtWidgets.QPushButton("🎯 Select")
            btn_select_joints.setToolTip("Select the joints listed in this field in the viewport.")
            btn_select_joints.clicked.connect(self.select_skin_joints)
            joints_layout.addWidget(self.joints_field)
            joints_layout.addWidget(btn_get_sel_j)
            joints_layout.addWidget(btn_select_joints)
            main_layout.addLayout(joints_layout)

            # Stage 31 / 32 / 33: the studio's own re-skin (unbind keeping
            # weights, clear the stale bind pose, rebind to the same
            # influences - straight from the shipped RGreSkin MEL tool),
            # optionally performed with one or more controls temporarily
            # scaled up so the rebind's rest pose is computed at that scale.
            #
            # Stage 33: Scale Control(s) is now the gate for the whole
            # feature, not a separate checkbox - if it's empty, re-skin does
            # NOT run at all (Load Skin behaves exactly as before). Fill it
            # in (one or more controls, comma-separated) and re-skin runs
            # automatically after every successful load: every listed
            # control is scaled to Scale, the mesh(es) are re-bound, then
            # every control is restored - all with no button to press.
            reskin_row = QtWidgets.QHBoxLayout()
            reskin_row.setContentsMargins(25, 0, 0, 0)
            reskin_row.addWidget(QtWidgets.QLabel("Re-Skin after Load - Scale Control(s):"))
            self.reskin_ctl_field = QtWidgets.QLineEdit()
            self.reskin_ctl_field.setPlaceholderText(
                "Control(s) to scale during the rebind, comma-separated - leave empty to skip re-skin entirely...")
            self.reskin_ctl_field.setToolTip(
                "One or more controls (comma-separated) to temporarily scale while the "
                "mesh(es) are re-bound, then restore.\n\n"
                "This field is also the on/off switch for the whole Re-Skin feature: "
                "leave it EMPTY and Load Skin does nothing extra (no re-skin, no "
                "scaling) - fill in at least one control and re-skin runs automatically "
                "every time this panel loads its skin weights.")
            reskin_row.addWidget(self.reskin_ctl_field)
            btn_get_reskin_ctl = QtWidgets.QPushButton("Get Selected")
            btn_get_reskin_ctl.setToolTip("Store all currently selected controls into this field.")
            btn_get_reskin_ctl.clicked.connect(self.get_selection_for_reskin_control)
            reskin_row.addWidget(btn_get_reskin_ctl)

            reskin_row.addWidget(QtWidgets.QLabel("Scale:"))
            self.reskin_scale_field = QtWidgets.QLineEdit("1.0")
            self.reskin_scale_field.setFixedWidth(55)
            self.reskin_scale_field.setToolTip(
                "The scale every listed control is set to (uniformly) for the duration "
                "of the rebind, then restored from. This is a TARGET value, not a "
                "multiplier - and it only does anything for a control if it's DIFFERENT "
                "from that control's current scale. Entering a control's current scale "
                "here changes nothing for it (it never visibly moves), which looks "
                "exactly like 'nothing happened'.")
            reskin_row.addWidget(self.reskin_scale_field)
            main_layout.addLayout(reskin_row)

            bind_layout = QtWidgets.QHBoxLayout()
            bind_layout.setContentsMargins(25, 0, 0, 0)
            btn_bind_all = QtWidgets.QPushButton("🦴 Bind All (Meshes -> Joints)")
            btn_bind_all.setToolTip(
                "Default-bind every mesh in the Meshes field (or the current "
                "selection if that field is empty) to every joint in the "
                "Joints field. Meshes that already have a skinCluster are "
                "skipped, not overwritten.")
            btn_bind_all.clicked.connect(self.bind_all_meshes)
            bind_layout.addWidget(btn_bind_all)
            bind_layout.addStretch()
            main_layout.addLayout(bind_layout)

        if p_type == "TWEAKER":
            # Stage 21, request #1: a Tweaker panel can hold several
            # independent vertex groups - each with its own vertex names
            # (from a different source mesh if needed), its own additional
            # meshes, and its own bind-scale/influence-radius/full-weight-
            # radius/falloff settings. Every group runs as its own tweaker
            # setup when the panel's CREATE button is clicked. See
            # TweakerVertexGroup, add_tweaker_group()/remove_tweaker_group().
            groups_label = QtWidgets.QLabel("Vertex Groups (each targets its own vertices/mesh + settings):")
            groups_label.setStyleSheet("color: #888; font-size: 10px; margin-left: 25px;")
            main_layout.addWidget(groups_label)

            self.tweaker_groups_widget = QtWidgets.QWidget()
            self.tweaker_groups_box = QtWidgets.QVBoxLayout(self.tweaker_groups_widget)
            self.tweaker_groups_box.setContentsMargins(25, 0, 0, 0)
            self.tweaker_groups_box.setSpacing(4)
            self.tweaker_groups = []
            main_layout.addWidget(self.tweaker_groups_widget)

            add_row = QtWidgets.QHBoxLayout()
            add_row.setContentsMargins(25, 0, 0, 0)
            btn_add_group = QtWidgets.QPushButton("+ Add Vertex Group")
            btn_add_group.setToolTip(
                "Add another independent vertex group - different vertices "
                "(from a different mesh if needed), its own additional "
                "meshes, and its own bind-scale/influence/falloff settings.")
            btn_add_group.clicked.connect(lambda: self.add_tweaker_group())
            add_row.addWidget(btn_add_group)
            add_row.addStretch()
            main_layout.addLayout(add_row)

            # Same Meshes/Joints rows as the JSON skinCluster panel (reuses
            # get_selection_for_skin/select_skin_meshes/
            # get_selection_for_joints/select_skin_joints as-is - all four
            # are already generic over self.mesh_field/self.joints_field,
            # not skin-panel-specific). Meshes is auto-filled with the
            # Tweaker-created mesh(es) when CREATE succeeds (_execute_
            # tweaker), and Save Skin uses it as the authoritative target
            # list instead of recomputing from the vertex groups every time.
            # Joints is auto-filled with every joint actually influencing
            # those meshes' skinClusters the moment Save Skin succeeds -
            # same "auto-filled ... on Save if left empty" behavior as JSON.
            tw_mesh_layout = QtWidgets.QHBoxLayout()
            tw_mesh_layout.setContentsMargins(25, 0, 0, 0)
            tw_mesh_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText(
                "Auto-filled with the Tweaker mesh(es) when CREATE succeeds...")
            btn_get_sel_tw = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_tw.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel_tw.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes_tw = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes_tw.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes_tw.clicked.connect(self.select_skin_meshes)
            tw_mesh_layout.addWidget(self.mesh_field)
            tw_mesh_layout.addWidget(btn_get_sel_tw)
            tw_mesh_layout.addWidget(btn_select_meshes_tw)
            main_layout.addLayout(tw_mesh_layout)

            tw_joints_layout = QtWidgets.QHBoxLayout()
            tw_joints_layout.setContentsMargins(25, 0, 0, 0)
            tw_joints_layout.addWidget(QtWidgets.QLabel("Joints:"))
            self.joints_field = QtWidgets.QLineEdit()
            self.joints_field.setPlaceholderText(
                "Auto-filled with the influencing joints when Save Skin succeeds...")
            btn_get_sel_j_tw = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_j_tw.setToolTip("Store the currently selected joints into this field.")
            btn_get_sel_j_tw.clicked.connect(self.get_selection_for_joints)
            btn_select_joints_tw = QtWidgets.QPushButton("🎯 Select")
            btn_select_joints_tw.setToolTip("Select the joints listed in this field in the viewport.")
            btn_select_joints_tw.clicked.connect(self.select_skin_joints)
            tw_joints_layout.addWidget(self.joints_field)
            tw_joints_layout.addWidget(btn_get_sel_j_tw)
            tw_joints_layout.addWidget(btn_select_joints_tw)
            main_layout.addLayout(tw_joints_layout)

            self.add_tweaker_group()

        if p_type == "SHAPES":
            shape_ext_layout = QtWidgets.QHBoxLayout()
            shape_ext_layout.setContentsMargins(25, 0, 0, 0)
            shape_ext_layout.addWidget(QtWidgets.QLabel("Pattern:"))
            self.pattern_field = QtWidgets.QLineEdit("*ctl")
            shape_ext_layout.addWidget(self.pattern_field)
            main_layout.addLayout(shape_ext_layout)

        if p_type == "MATERIAL":
            # Same "Meshes" row as JSON's skinCluster panel (reuses
            # get_selection_for_skin/select_skin_meshes as-is - both are
            # already generic over self.mesh_field, not skin-specific).
            mat_mesh_layout = QtWidgets.QHBoxLayout()
            mat_mesh_layout.setContentsMargins(25, 0, 0, 0)
            mat_mesh_layout.addWidget(QtWidgets.QLabel("Meshes:"))
            self.mesh_field = QtWidgets.QLineEdit()
            self.mesh_field.setPlaceholderText("Leave empty for selection...")
            btn_get_sel_mat = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_mat.setToolTip("Store the currently selected meshes into this field.")
            btn_get_sel_mat.clicked.connect(self.get_selection_for_skin)
            btn_select_meshes_mat = QtWidgets.QPushButton("🎯 Select")
            btn_select_meshes_mat.setToolTip("Select the meshes listed in this field in the viewport.")
            btn_select_meshes_mat.clicked.connect(self.select_skin_meshes)
            mat_mesh_layout.addWidget(self.mesh_field)
            mat_mesh_layout.addWidget(btn_get_sel_mat)
            mat_mesh_layout.addWidget(btn_select_meshes_mat)
            main_layout.addLayout(mat_mesh_layout)

        if p_type == "IMPORT_LOD":
            # Same file field/Browse/Import as IMPORT_3D (reuses self.field,
            # browse_file(), workspace.import_3d_logic - see execute()
            # below), plus the one extra input organize_lod_logic() needs:
            # the asset's name, used to build <AssetName>/<AssetName>_geo/
            # <AssetName>_lod_<N> groups. *_ai_lod-named objects are always
            # deleted (delete_ai_lod=True, matching the original script's
            # own default) rather than offering a checkbox for it.
            lod_asset_layout = QtWidgets.QHBoxLayout()
            lod_asset_layout.setContentsMargins(25, 0, 0, 0)
            lod_asset_layout.addWidget(QtWidgets.QLabel("Asset Name:"))
            self.asset_name_field = QtWidgets.QLineEdit()
            self.asset_name_field.setPlaceholderText("e.g. char_gurudattatreya_a")
            self.asset_name_field.setToolTip(
                "Used to build <AssetName>/<AssetName>_geo/<AssetName>_lod_<N> "
                "groups after import - organizes whatever meshes are "
                "currently in the scene, not just this import.")
            lod_asset_layout.addWidget(self.asset_name_field)
            main_layout.addLayout(lod_asset_layout)

        if p_type in ("DELETE_OBJ", "ZERO_OUT"):
            # One name field, reused for both types - Delete removes
            # whatever's listed, Zero Out builds an offset group above
            # each one and resets its own transform - see execute() below.
            # self.field (the generic path/code field built above) means
            # nothing for either type, so it's hidden.
            self.field.setVisible(False)
            target_layout = QtWidgets.QHBoxLayout()
            target_layout.setContentsMargins(25, 0, 0, 0)
            label_txt = "Object(s) to Delete:" if p_type == "DELETE_OBJ" else "Object(s)/Control(s) to Zero:"
            target_layout.addWidget(QtWidgets.QLabel(label_txt))
            self.target_field = QtWidgets.QLineEdit()
            self.target_field.setPlaceholderText("Comma-separated object/control names...")
            if p_type == "ZERO_OUT":
                self.target_field.setToolTip(
                    "For each object: creates an offset group ('<name>_offset') "
                    "that holds its current position/rotation/scale, parents "
                    "the object under it, then resets the object's own "
                    "translate/rotate/scale to 0/0/0, 0/0/0, 1/1/1 - the "
                    "object doesn't move, but its channels read clean "
                    "defaults again, same as a freshly-built control.")
            btn_get_sel_tgt = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_tgt.setToolTip("Store the currently selected object(s) into this field.")
            btn_get_sel_tgt.clicked.connect(lambda: self._get_selection_into(self.target_field))
            btn_select_tgt = QtWidgets.QPushButton("🎯 Select")
            btn_select_tgt.setToolTip("Select the object(s) listed in this field in the viewport.")
            btn_select_tgt.clicked.connect(lambda: self._select_field_objects(self.target_field))
            target_layout.addWidget(self.target_field)
            target_layout.addWidget(btn_get_sel_tgt)
            target_layout.addWidget(btn_select_tgt)
            main_layout.addLayout(target_layout)

        if p_type == "PARENT_OBJ":
            # Two name fields - self.field (the generic path/code field
            # built above) means nothing here either, so it's hidden too.
            self.field.setVisible(False)
            child_layout = QtWidgets.QHBoxLayout()
            child_layout.setContentsMargins(25, 0, 0, 0)
            child_layout.addWidget(QtWidgets.QLabel("Child(ren):"))
            self.child_field = QtWidgets.QLineEdit()
            self.child_field.setPlaceholderText("Comma-separated object name(s) to parent...")
            btn_get_sel_child = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_child.setToolTip("Store the currently selected object(s) into this field.")
            btn_get_sel_child.clicked.connect(lambda: self._get_selection_into(self.child_field))
            btn_select_child = QtWidgets.QPushButton("🎯 Select")
            btn_select_child.setToolTip("Select the object(s) listed in this field in the viewport.")
            btn_select_child.clicked.connect(lambda: self._select_field_objects(self.child_field))
            child_layout.addWidget(self.child_field)
            child_layout.addWidget(btn_get_sel_child)
            child_layout.addWidget(btn_select_child)
            main_layout.addLayout(child_layout)

            parent_layout = QtWidgets.QHBoxLayout()
            parent_layout.setContentsMargins(25, 0, 0, 0)
            parent_layout.addWidget(QtWidgets.QLabel("Parent:"))
            self.parent_field = QtWidgets.QLineEdit()
            self.parent_field.setPlaceholderText("Object to parent the child(ren) under...")
            btn_get_sel_parent = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_parent.setToolTip("Store the currently selected object into this field.")
            btn_get_sel_parent.clicked.connect(lambda: self._get_selection_into(self.parent_field))
            btn_select_parent = QtWidgets.QPushButton("🎯 Select")
            btn_select_parent.setToolTip("Select the object listed in this field in the viewport.")
            btn_select_parent.clicked.connect(lambda: self._select_field_objects(self.parent_field))
            parent_layout.addWidget(self.parent_field)
            parent_layout.addWidget(btn_get_sel_parent)
            parent_layout.addWidget(btn_select_parent)
            main_layout.addLayout(parent_layout)

        if p_type == "INSTANCE_OBJ":
            # Instances the object below at a set of preset transform
            # offsets (see workspace.create_instances_logic -
            # INSTANCE_DEFAULT_TRANSFORMS - ported from the user's own
            # create_and_transform_instances_by_name script). self.field/
            # func_field above (shown - NOT hidden, unlike DELETE_OBJ/
            # ZERO_OUT/PARENT_OBJ) double as an OPTIONAL custom script
            # override, same convention as a SCRIPT panel.
            self.field.setPlaceholderText(
                "Optional: custom script/path that sets a 'transforms' list "
                "- leave empty for the built-in 3-instance preset...")
            self.field.setToolTip(
                "Optional custom Python script (a .py path, or raw pasted "
                "code) that leaves a 'transforms' variable behind - a list "
                "of {'tx','ty','tz','rx','ry','rz'} dicts, one per instance "
                "to create - used instead of the built-in 3-instance preset "
                "when given. Leave empty to just use the preset.")

            inst_target_layout = QtWidgets.QHBoxLayout()
            inst_target_layout.setContentsMargins(25, 0, 0, 0)
            inst_target_layout.addWidget(QtWidgets.QLabel("Object to Instance:"))
            self.target_field = QtWidgets.QLineEdit()
            self.target_field.setPlaceholderText("Object name to instance (e.g. parshuram_a_geo)...")
            btn_get_sel_inst = QtWidgets.QPushButton("Get Selected")
            btn_get_sel_inst.setToolTip("Store the currently selected object into this field.")
            btn_get_sel_inst.clicked.connect(lambda: self._get_selection_into(self.target_field))
            btn_select_inst = QtWidgets.QPushButton("🎯 Select")
            btn_select_inst.setToolTip("Select the object listed in this field in the viewport.")
            btn_select_inst.clicked.connect(lambda: self._select_field_objects(self.target_field))
            inst_target_layout.addWidget(self.target_field)
            inst_target_layout.addWidget(btn_get_sel_inst)
            inst_target_layout.addWidget(btn_select_inst)
            main_layout.addLayout(inst_target_layout)

            inst_del_layout = QtWidgets.QHBoxLayout()
            inst_del_layout.setContentsMargins(25, 0, 0, 0)
            self.btn_delete_instances = QtWidgets.QPushButton("🗑 Delete All Instances")
            self.btn_delete_instances.setToolTip(
                "Deletes every instance THIS panel has created, however many "
                "times it's been run - each instance is tagged with a "
                "hidden attribute when created, so this finds them all even "
                "after a save/reload, not just the most recent Run.")
            self.btn_delete_instances.setStyleSheet("background-color: #452a29; color: white;")
            self.btn_delete_instances.clicked.connect(self.delete_created_instances)
            inst_del_layout.addWidget(self.btn_delete_instances)
            inst_del_layout.addStretch()
            main_layout.addLayout(inst_del_layout)

        if p_type == "NOTE":
            # Purely informational - not a build step at all (execute()
            # below no-ops for NOTE). The common file/run/cache widgets
            # built above stay alive (never removed) so every other method
            # on this class, and every generic per-panel save/load/copy/
            # paste call elsewhere (workspace.py's get_current_pipeline_data/
            # load_pipeline_from_file, copy_panel/paste_panel below), still
            # finds real objects to work with instead of needing its own
            # NOTE special-case for them - they're just hidden here, since
            # none of them mean anything for a note.
            self.field.setVisible(False)
            self.btn_run.setVisible(False)
            self.btn_reset_err.setVisible(False)
            self.btn_cache_rem.setVisible(False)
            self.btn_cache_save.setVisible(False)
            self.btn_cache_run.setVisible(False)
            self.chk_cache.setVisible(False)

            # Defaults ("in default also you can decide") - text/background
            # color and text size are all still fully user-adjustable per
            # note, just from the "..." (More Options) menu now rather
            # than a dedicated toolbar row - see show_context_menu below.
            self.note_text_color = "#ffffff"
            self.note_bg_color = "#1a1a2e"
            self.note_font_size = 20
            self.note_height = 90

            self.note_edit = QtWidgets.QPlainTextEdit()
            self.note_edit.setPlaceholderText(
                "Write a note here for anyone reading this Rig Build Workspace - "
                "what's happening, what's left, anything worth flagging...")
            self.note_edit.setFixedHeight(self.note_height)
            self.note_edit.setToolTip(
                "Free-text note - purely informational, never part of the build.")
            main_layout.addWidget(self.note_edit)

            # Drag to resize this note's height - vertical only, never the
            # panel's width (that's always fixed to the workspace column).
            self.note_resize_handle = _NoteVerticalResizeHandle(self.note_edit, on_resize=self._set_note_height)
            main_layout.addWidget(self.note_resize_handle)

            self._apply_note_style()

        btn_dots.clicked.connect(self.show_context_menu)
        self.btn_run.clicked.connect(self.on_btn_run_clicked)
        self.btn_del.clicked.connect(lambda: self.workspace.delete_panel(self))

    def update_style(self):
        accent = getattr(self, 'accent', '#2bb5a8')
        self.setStyleSheet(
            f"SortablePanel {{ background: {self.bg_color}; border: 1px solid #333;"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" SortablePanel:hover {{ border: 1px solid #555; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

    def _apply_note_style(self):
        """NOTE panels only: (re)style the note's own text box from
        self.note_text_color/note_bg_color/note_font_size - separate from
        update_style() above, which only ever touches the panel's outer
        QFrame chrome (background/border), not anything inside it."""
        if not hasattr(self, "note_edit"):
            return
        self.note_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: {self.note_bg_color}; color: {self.note_text_color};"
            f" border: 1px solid #333; border-radius: 3px; padding: 6px;"
            f" font-size: {self.note_font_size}px; }}")

    def change_note_text_color(self):
        current_color = QtGui.QColor(self.note_text_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Note Text Color")
        if color.isValid():
            self.note_text_color = color.name()
            self._apply_note_style()

    def change_note_bg_color(self):
        current_color = QtGui.QColor(self.note_bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Note Background Color")
        if color.isValid():
            self.note_bg_color = color.name()
            self._apply_note_style()

    def change_note_font_size(self, value):
        self.note_font_size = value
        self._apply_note_style()

    def _set_note_height(self, height):
        self.note_height = height

    def populate_versions_menu(self, switch_menu):
        v_actions = {}
        base_path = self.field.text().strip()
        if not base_path:
            switch_menu.setEnabled(False)
            return v_actions
            
        dir_name = os.path.dirname(base_path)
        if not os.path.exists(dir_name):
            switch_menu.setEnabled(False)
            return v_actions
            
        base_name, ext = os.path.splitext(os.path.basename(base_path))
        base_name_no_v = re.sub(r'_v\d+$', '', base_name)
        pattern = re.compile(r"^" + re.escape(base_name_no_v) + r"(?:_v(\d+))?" + re.escape(ext) + r"$")
        
        versions = []
        for f in os.listdir(dir_name):
            match = pattern.match(f)
            if match:
                versions.append(os.path.join(dir_name, f).replace('\\', '/'))
                
        versions.sort()
        if not versions:
            switch_menu.setEnabled(False)
        else:
            for v in versions:
                v_name = os.path.basename(v)
                v_actions[switch_menu.addAction(v_name)] = v
                
        return v_actions

    def save_versioned_data(self, overwrite=False):
        current_path = self.field.text().strip()
        if not current_path:
            # First save on this panel (Stage 16, request #3): ask where,
            # instead of just erroring - and make sure whatever's picked
            # ends up with the right extension for this panel's data.
            current_path = self.prompt_first_save_path()
            if not current_path:
                return  # user cancelled the Save As dialog
            self.field.setText(current_path)

        if self.p_type in ("JSON", "TWEAKER"):
            # mgear.core.skin.exportSkin() hard-rejects any extension other
            # than .gSkin/.jSkin (it will warn "Not valid file extension for:
            # ..." and silently not write the file). Panels saved/typed with
            # a plain .json - which the Save dialog's own filter offers as a
            # choice - would otherwise pass that check and fail on export, and
            # keep failing on every subsequent versioned save. Normalize here,
            # before computing the versioned path, so the corrected extension
            # is what get_versioned_path() and the field both use from now on.
            root, ext = os.path.splitext(current_path)
            if ext.lower() not in (".jskin", ".gskin"):
                current_path = root + ".jSkin"
                self.field.setText(current_path)

        save_path = current_path
        if not overwrite:
            save_path = get_versioned_path(current_path, get_latest=False)

        if self.p_type == "JSON":
            try:
                from .utils import find_mesh_skincluster, fast_export_skin
                meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                sel = meshes if meshes else cmds.ls(sl=True)
                if not sel:
                    om.MGlobal.displayError("Select a skinned mesh (or fill the Meshes field) before saving skin.")
                    return
                # Use cmds.select (not pm.select): pymel's select can trigger a
                # spurious "Cannot find Maya documentation" error on installs
                # without the docs package.
                missing = [m for m in sel if not cmds.objExists(m)]
                if missing:
                    om.MGlobal.displayError("These objects don't exist in the scene: {}".format(", ".join(missing)))
                    return
                cmds.select(sel, replace=True)

                # Stage 16, request #1: the naming-convention check used to
                # run once at KRT launch, scanning the whole scene. It's
                # scoped here to just the mesh(es) this export is actually
                # about to touch instead.
                prompt_skincluster_naming_check(
                    self.workspace.main_window, sel,
                    show_popup=self.naming_popup_enabled())

                # If Joints was left empty, capture the influences that are
                # actually bound right now, so this panel remembers the
                # intended influence set for future Bind All / re-import.
                if hasattr(self, 'joints_field') and not self.joints_field.text().strip():
                    captured = []
                    seen = set()
                    for m in sel:
                        skc = find_mesh_skincluster(m)
                        if not skc:
                            continue
                        for j in (cmds.skinCluster(skc, query=True, influence=True) or []):
                            if j not in seen:
                                seen.add(j); captured.append(j)
                    if captured:
                        self.joints_field.setText(",".join(captured))

                try:
                    # fast_export_skin() (utils.py) - same .jSkin file mgear's
                    # own exportSkin() would write, just fast on heavy meshes
                    # (see the "Fast SkinCluster save/import" section there);
                    # falls back to mgear's exporter itself on any error.
                    fast_export_skin(save_path)
                except Exception as ex:
                    # The "Cannot find Maya documentation" message is non-fatal;
                    # if the skin file was actually written, accept the export.
                    if "documentation" not in str(ex).lower() or not os.path.isfile(save_path):
                        raise
                    cmds.warning("[KRT] Ignored a non-fatal Maya docs warning during skin export.")
                if not os.path.isfile(save_path):
                    raise RuntimeError(
                        "Skin file was not written. Make sure the selected mesh(es) actually have a skinCluster.")
                self.field.setText(save_path)
                cmds.warning(f"Skin exported successfully to: {save_path}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export skin: {e}")

        elif self.p_type == "SHAPES":
            pattern = self.pattern_field.text()
            try:
                export_control_shapes(save_path, search_pattern=pattern)
                self.field.setText(save_path)
                cmds.warning(f"Shapes exported successfully to: {save_path}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export shapes: {e}")

        elif self.p_type == "MATERIAL":
            meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
            try:
                result = export_material_data(save_path, meshes=meshes if meshes else None)
                if result:
                    self.field.setText(save_path)
                    cmds.warning(f"Material exported successfully to: {save_path}")
                else:
                    om.MGlobal.displayError("Failed to export material - nothing to save (select mesh(es) or fill the Meshes field first).")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export material: {e}")

        elif self.p_type == "TWEAKER":
            try:
                from .utils import find_mesh_skincluster, fast_export_skin
                # The panel-level Meshes field is the authoritative target
                # list once it's filled (auto-filled by _execute_tweaker on
                # a successful Create, or set by hand / Get Selected). Only
                # fall back to re-deriving it from the vertex groups when
                # it's empty, e.g. an older session/panel that never ran
                # Create through this version of the panel yet.
                meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                if meshes:
                    targets = meshes
                else:
                    # Stage 21: aggregate vertex names/additional meshes across
                    # EVERY vertex group on this panel, so Save Skin covers
                    # every group's tweaker meshes in one export, not just the
                    # first group.
                    vertex_names = []
                    additional_meshes = []
                    for group in self.tweaker_groups:
                        vertex_names.extend(v.strip() for v in group.vertex_field.text().split(",") if v.strip())
                        additional_meshes.extend(m.strip() for m in group.mesh_field.text().split(",") if m.strip())
                    targets = self.workspace.get_tweaker_target_meshes(vertex_names, additional_meshes)
                if not targets:
                    om.MGlobal.displayError(
                        "No Tweaker mesh(es) found for the current Vertices/Additional Meshes "
                        "- run Create first.")
                    return
                missing = [t for t in targets if not cmds.objExists(t)]
                if missing:
                    om.MGlobal.displayError("These Tweaker meshes don't exist: {}".format(", ".join(missing)))
                    return
                cmds.select(targets, replace=True)
                prompt_skincluster_naming_check(
                    self.workspace.main_window, targets,
                    show_popup=self.naming_popup_enabled())
                try:
                    fast_export_skin(save_path)
                except Exception as ex:
                    if "documentation" not in str(ex).lower() or not os.path.isfile(save_path):
                        raise
                    cmds.warning("[KRT] Ignored a non-fatal Maya docs warning during skin export.")
                if not os.path.isfile(save_path):
                    raise RuntimeError("Skin file was not written.")
                self.field.setText(save_path)
                if not meshes:
                    # Keep the Meshes field in sync with whatever was
                    # actually exported, same as the auto-fill on Create.
                    self.mesh_field.setText(",".join(targets))
                # Joints is auto-filled with every joint actually influencing
                # the exported meshes' skinClusters, same "auto-filled ... on
                # Save if left empty" behavior as the JSON panel.
                if not self.joints_field.text().strip():
                    captured = []
                    seen = set()
                    for m in targets:
                        skc = find_mesh_skincluster(m)
                        if not skc:
                            continue
                        for j in (cmds.skinCluster(skc, query=True, influence=True) or []):
                            if j not in seen:
                                seen.add(j); captured.append(j)
                    if captured:
                        self.joints_field.setText(",".join(captured))
                cmds.warning(f"Tweaker skin exported successfully to: {save_path}")
            except Exception as e:
                om.MGlobal.displayError(f"Failed to export Tweaker skin: {e}")

    def prompt_first_save_path(self):
        """Stage 16, request #3: the first time a skinCluster/Tweaker/
        Control-Shapes panel is saved and it has no path yet, ask where to
        save instead of just erroring - and make sure the chosen path ends
        up with the right extension for what's being saved, appending one
        if the user typed a bare name without it. Returns the chosen path,
        or "" if the dialog was cancelled."""
        if self.p_type in ("JSON", "TWEAKER"):
            default_ext = ".jSkin"
            ff = "Skin (*.jSkin *.gSkin *.json);;All Files (*.*)"
            caption = "Save Skin As"
            default_name = "skinCluster" + default_ext
        elif self.p_type == "SHAPES":
            default_ext = ".json"
            ff = "Control Shapes (*.json);;All Files (*.*)"
            caption = "Save Control Shapes As"
            default_name = "controlShapes" + default_ext
        elif self.p_type == "MATERIAL":
            default_ext = ".json"
            ff = "Material (*.json);;All Files (*.*)"
            caption = "Save Material As"
            default_name = "material" + default_ext
        else:
            return ""

        start_dir = self.get_start_dir()
        if not start_dir:
            # Nothing typed in the field yet to derive a folder from -
            # default next to wherever this session's own KRT json lives,
            # same convenience the auto-managed Guide Path already gets.
            session_path = getattr(self.workspace, "session_path", "") or ""
            if session_path:
                start_dir = os.path.dirname(session_path)
        if not start_dir or not os.path.exists(start_dir):
            start_dir = os.path.expanduser("~")

        res = cmds.fileDialog2(
            fileFilter=ff, dialogStyle=2, fileMode=0, caption=caption,
            startingDirectory=os.path.join(start_dir, default_name).replace("\\", "/"))
        if not res:
            return ""
        path = res[0]
        if not os.path.splitext(path)[1]:
            path += default_ext
        elif self.p_type in ("JSON", "TWEAKER") and os.path.splitext(path)[1].lower() not in (".jskin", ".gskin"):
            # The Save dialog's own filter offers ".json" as a pickable
            # option for skin panels, but mgear.core.skin.exportSkin() only
            # accepts .gSkin/.jSkin - swap it here too so a fresh pick never
            # needs the save_versioned_data() fallback to catch it.
            path = os.path.splitext(path)[0] + default_ext
        return path

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
        elif p_type == "LOD_LOADER":
            self.workspace.add_lod_loader_panel(title, index=idx)
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active, "bg_color": self.bg_color}
        if self.p_type == "MODULE":
            mods = [{"path": self.bubble_layout.itemAt(b).widget().full_path, "active": self.bubble_layout.itemAt(b).widget().is_active} for b in range(self.bubble_layout.count())]
            data["modules"] = mods
        else:
            data["path"] = self.field.text()
            if self.p_type == "SHAPES": data["pattern"] = self.pattern_field.text()
            if self.p_type == "JSON":
                data["meshes"] = self.mesh_field.text()
                data["joints"] = self.joints_field.text()
                data["reskin_control"] = self.reskin_ctl_field.text()
                data["reskin_scale"] = self.reskin_scale_field.text()
                data["naming_popup"] = self.naming_popup_enabled()
            if self.p_type == "MATERIAL":
                data["meshes"] = self.mesh_field.text()
            if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"): data["func_call"] = self.func_field.text()
            if self.p_type == "TWEAKER":
                data["groups"] = self.get_tweaker_groups_data()
                data["meshes"] = self.mesh_field.text()
                data["joints"] = self.joints_field.text()
                data["naming_popup"] = self.naming_popup_enabled()
            if self.p_type == "NOTE":
                data["note_text"] = self.note_edit.toPlainText()
                data["note_text_color"] = self.note_text_color
                data["note_bg_color"] = self.note_bg_color
                data["note_font_size"] = self.note_font_size
                data["note_height"] = self.note_height
            if self.p_type == "IMPORT_LOD":
                data["asset_name"] = self.asset_name_field.text()
            if self.p_type in ("DELETE_OBJ", "ZERO_OUT"):
                data["target"] = self.target_field.text()
            if self.p_type == "PARENT_OBJ":
                data["child"] = self.child_field.text()
                data["parent"] = self.parent_field.text()
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

    def cut_panel(self):
        """Stage 22, request #1: Copy Panel, then delete this panel -
        delete_panel() itself pushes the removed panel onto the workspace's
        undo stack, so a Cut can still be undone same as a plain Delete."""
        self.copy_panel()
        self.workspace.delete_panel(self)

    def paste_panel(self, offset):
        data = getattr(self.workspace.main_window, 'clipboard_panel_data', None)
        if not data: return
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset

        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.workspace.add_module_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            for m in data.get("modules", []):
                pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
            if not is_act: pan.checkbox.setChecked(False)
        else:
            pan = self.workspace.add_panel(title, p_type, data.get("path", ""), index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            if not is_act: pan.checkbox.setChecked(False)
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                if data.get("asset_name"): pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT") and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))
            if p_type == "INSTANCE_OBJ" and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
                if data.get("func_call") and hasattr(pan, 'func_field'): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            self.execute(None)

    def _normal_run_text(self):
        return panel_run_label(self.p_type)

    def reset_run_button(self):
        """Restore the run button to its normal state after an error, without
        re-executing the panel. Triggered by the small ↺ button."""
        self.btn_run.setText(self._normal_run_text())
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #2bb5a8; font-weight: bold; color: white; font-size: 13px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(SortablePanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {getattr(self, 'accent', '#2bb5a8')}; font-size: 13px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(SortablePanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton): 
            return super(SortablePanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(SortablePanel, self).mouseMoveEvent(event)
            
        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance(): 
            return super(SortablePanel, self).mouseMoveEvent(event)

        self.workspace.dragged_panel = self
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText("panel_drag")
        drag.setMimeData(mime_data)
        
        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        if IS_PYSIDE6: drag.exec(QtCore.Qt.MoveAction)
        else: drag.exec_(QtCore.Qt.MoveAction)
            
        self.workspace.dragged_panel = None
        super(SortablePanel, self).mouseMoveEvent(event)

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)

    def _get_selection_into(self, field):
        """Generic 'Get Selected' for the Delete/Zero Out/Parent panels'
        name field(s) - same idea as get_selection_for_skin()/
        get_selection_for_joints() below, just not hardcoded to one
        specific field, since these panel types have more than one."""
        sel = cmds.ls(sl=True)
        if sel: field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def _select_field_objects(self, field):
        """Generic '🎯 Select' for the Delete/Zero Out/Parent panels' name
        field(s) - same idea as select_skin_meshes()/select_skin_joints()
        below, just not hardcoded to one specific field."""
        names = [n.strip() for n in field.text().split(",") if n.strip()]
        if not names:
            cmds.warning("Nothing listed - use 'Get Selected' first, or type object names.")
            return
        existing = [n for n in names if cmds.objExists(n)]
        missing = [n for n in names if not cmds.objExists(n)]
        if not existing:
            cmds.warning("None of these objects exist in the scene: {}".format(", ".join(names)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} object(s); not found, skipped: {}".format(len(existing), ", ".join(missing)))

    def delete_created_instances(self):
        """Instance Object panel's Delete All Instances button - removes
        every instance this specific panel has created (tracked by the
        krtInstancePanel tag - see workspace.delete_instances_by_panel_logic),
        not just the ones from the last Run."""
        success, error_msg = self.workspace.delete_instances_by_panel_logic(self.uuid)
        if not success:
            cmds.warning("[KRT] {}".format(error_msg))

    def get_selection_for_skin(self):
        sel = cmds.ls(sl=True)
        if sel: self.mesh_field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def select_skin_meshes(self):
        """Select the meshes listed in the Meshes field in the viewport."""
        meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
        if not meshes:
            cmds.warning("No meshes listed - use 'Get Selected' first, or type mesh names.")
            return
        existing = [m for m in meshes if cmds.objExists(m)]
        missing = [m for m in meshes if not cmds.objExists(m)]
        if not existing:
            cmds.warning("None of the listed meshes exist in the scene: {}".format(", ".join(meshes)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} mesh(es). Not found: {}".format(len(existing), ", ".join(missing)))
        else:
            cmds.warning("Selected {} mesh(es).".format(len(existing)))

    def get_selection_for_reskin_control(self):
        """Stores every currently selected object into the Scale Control(s)
        field, comma-separated - Stage 33 supports scaling more than one
        control during the re-bind."""
        sel = cmds.ls(sl=True) or []
        if not sel:
            cmds.warning("Nothing selected.")
            return
        cmds.warning("Using {} selected object(s) as the Re-Skin scale control(s).".format(len(sel)))
        self.reskin_ctl_field.setText(", ".join(sel))

    def reskin_settings(self):
        """(controls, scale) as entered on this panel - `controls` is a list
        (possibly empty; an empty list means "no re-skin should run at all",
        checked by the caller). A scale that isn't a number falls back to
        1.0 (no scaling) rather than failing the run."""
        raw = self.reskin_ctl_field.text() if hasattr(self, 'reskin_ctl_field') else ""
        controls = [c.strip() for c in raw.split(",") if c.strip()]
        try:
            scale = float(self.reskin_scale_field.text().strip())
        except (ValueError, AttributeError):
            if hasattr(self, 'reskin_scale_field') and self.reskin_scale_field.text().strip():
                cmds.warning("Re-Skin Scale '{}' isn't a number - using 1.0 (no scaling).".format(
                    self.reskin_scale_field.text().strip()))
            scale = 1.0
        return controls, scale

    def get_selection_for_joints(self):
        sel = cmds.ls(sl=True, type="joint") or cmds.ls(sl=True)
        if sel: self.joints_field.setText(",".join(sel))
        else: cmds.warning("Nothing selected.")

    def select_skin_joints(self):
        """Select the joints listed in the Joints field in the viewport."""
        joints = [j.strip() for j in self.joints_field.text().split(",") if j.strip()]
        if not joints:
            cmds.warning("No joints listed - use 'Get Selected' first, or type joint names.")
            return
        existing = [j for j in joints if cmds.objExists(j)]
        missing = [j for j in joints if not cmds.objExists(j)]
        if not existing:
            cmds.warning("None of the listed joints exist in the scene: {}".format(", ".join(joints)))
            return
        cmds.select(existing, replace=True)
        if missing:
            cmds.warning("Selected {} joint(s). Not found: {}".format(len(existing), ", ".join(missing)))
        else:
            cmds.warning("Selected {} joint(s).".format(len(existing)))

    def bind_all_meshes(self):
        """Default-bind every mesh in the Meshes field (or the current
        selection) to every joint in the Joints field. A mesh that already
        has a skinCluster is left alone - this only ever creates new binds,
        it never overwrites an existing one."""
        meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
        if not meshes:
            meshes = cmds.ls(sl=True, type="transform") or []
        joints = [j.strip() for j in self.joints_field.text().split(",") if j.strip()]

        if not meshes:
            om.MGlobal.displayError("List meshes in the Meshes field (or select some) before Bind All.")
            return
        if not joints:
            om.MGlobal.displayError("List joints in the Joints field (or use 'Get Selected') before Bind All.")
            return

        from .utils import find_mesh_skincluster, canonical_skincluster_name
        bound, skipped, failed = [], [], []
        for mesh in meshes:
            if not cmds.objExists(mesh):
                failed.append(mesh)
                continue
            if find_mesh_skincluster(mesh):
                skipped.append(mesh)
                continue
            existing_joints = [j for j in joints if cmds.objExists(j)]
            if not existing_joints:
                failed.append(mesh)
                continue
            try:
                cmds.skinCluster(
                    existing_joints, mesh, toSelectedBones=True,
                    name=canonical_skincluster_name(mesh),
                    bindMethod=0, skinMethod=0, normalizeWeights=1,
                    maximumInfluences=max(1, min(8, len(existing_joints))),
                    obeyMaxInfluences=False)
                bound.append(mesh)
            except Exception:
                traceback.print_exc()
                failed.append(mesh)

        msg = "Bind All: {} bound".format(len(bound))
        if skipped: msg += ", {} skipped (already skinned)".format(len(skipped))
        if failed: msg += ", {} failed".format(len(failed))
        cmds.warning(msg)

    # -- Tweaker vertex groups (Stage 21, request #1) -----------------------
    def add_tweaker_group(self, data=None):
        """Add one more independent TweakerVertexGroup row to this panel -
        the "+ Add Vertex Group" button. `data`, if given, seeds it (used
        when loading/pasting/duplicating a panel)."""
        group = TweakerVertexGroup(self.tweaker_groups_widget)
        group.removed.connect(self.remove_tweaker_group)
        self.tweaker_groups_box.addWidget(group)
        self.tweaker_groups.append(group)
        if data:
            group.from_dict(data)
        return group

    def remove_tweaker_group(self, group):
        if len(self.tweaker_groups) <= 1:
            cmds.warning("A Tweaker panel needs at least one vertex group.")
            return
        if group in self.tweaker_groups:
            self.tweaker_groups.remove(group)
        self.tweaker_groups_box.removeWidget(group)
        group.deleteLater()

    def get_tweaker_groups_data(self):
        return [g.to_dict() for g in self.tweaker_groups]

    def load_tweaker_groups_data(self, groups, legacy_item=None):
        """Restore this panel's vertex groups from saved/copied data.
        `groups` is the Stage 21 list-of-dicts form. `legacy_item`, if
        given, is a pre-Stage-21 flat dict (single vertices/meshes/
        use_bind_scale/influence_radius/full_weight_radius/falloff set) -
        used as a one-group fallback when `groups` isn't present, so an
        older pipeline JSON or clipboard copy still loads correctly."""
        if not groups and legacy_item:
            legacy = {
                "vertices": legacy_item.get("vertices", ""),
                "meshes": legacy_item.get("meshes", ""),
                "use_bind_scale": legacy_item.get("use_bind_scale", True),
                "bind_scale": legacy_item.get("bind_scale", "0.01"),
                "influence_radius": legacy_item.get("influence_radius", "0.08"),
                "full_weight_radius": legacy_item.get("full_weight_radius", "0.0001"),
                "falloff": legacy_item.get("falloff", "2.0"),
            }
            if legacy["vertices"] or legacy["meshes"]:
                groups = [legacy]
        if not groups:
            return
        # First saved group goes onto the default group this panel was
        # created with; any additional ones get their own new row.
        first, rest = groups[0], groups[1:]
        if self.tweaker_groups:
            self.tweaker_groups[0].from_dict(first)
        else:
            self.add_tweaker_group(first)
        for g_data in rest:
            self.add_tweaker_group(g_data)

    def _execute_tweaker(self):
        """Run the Tweaker setup (create_tweaker_setup + add_additional_
        tweaker_meshes, from PanelScripts/Tweaker.py) once per vertex group
        on this panel. Called from execute(). Stops at the first group that
        fails and reports which one."""
        if not self.tweaker_groups:
            return False, "No vertex groups on this panel."

        for i, group in enumerate(self.tweaker_groups):
            vertex_names = [v.strip() for v in group.vertex_field.text().split(",") if v.strip()]
            if not vertex_names and len(self.tweaker_groups) == 1:
                # Single-group panels keep the old "fall back to the current
                # viewport selection" convenience - ambiguous with more than
                # one group, so it's only offered when there's just one.
                sel = cmds.ls(sl=True, flatten=True) or []
                vertex_names = [v for v in sel if ".vtx[" in v]
            if not vertex_names:
                return False, "Vertex Group {}: no vertices provided - fill its Vertices field (or select some in the viewport first, single-group panels only).".format(i + 1)

            additional_meshes = [m.strip() for m in group.mesh_field.text().split(",") if m.strip()]
            try:
                bind_scale = float(group.field_bind_scale.text())
                influence_radius = float(group.field_influence_radius.text())
                full_weight_radius = float(group.field_full_weight_radius.text())
                falloff = float(group.field_falloff.text())
            except ValueError:
                return False, "Vertex Group {}: Bind Scale / Influence Radius / Full Weight Radius / Falloff must be numbers.".format(i + 1)

            ok, err = self.workspace.run_tweaker_logic(
                vertex_names, additional_meshes,
                use_bind_scale=group.chk_use_bind_scale.isChecked(),
                bind_scale=bind_scale,
                influence_radius=influence_radius,
                full_weight_radius=full_weight_radius,
                falloff=falloff)
            if not ok:
                return False, "Vertex Group {}:\n{}".format(i + 1, err)

        # All groups created successfully - auto-fill the panel-level Meshes
        # field with the real Tweaker-created mesh name(s) so Save Skin has
        # an authoritative target list without re-deriving it from the
        # vertex groups every time.
        try:
            all_vertex_names = []
            all_additional_meshes = []
            for group in self.tweaker_groups:
                all_vertex_names.extend(
                    v.strip() for v in group.vertex_field.text().split(",") if v.strip())
                all_additional_meshes.extend(
                    m.strip() for m in group.mesh_field.text().split(",") if m.strip())
            targets = self.workspace.get_tweaker_target_meshes(all_vertex_names, all_additional_meshes)
            if targets:
                self.mesh_field.setText(",".join(targets))
        except Exception:
            # Non-fatal - the panel still works with Meshes left blank;
            # Save Skin falls back to recomputing the targets itself.
            pass

        # A freshly (re)created Tweaker mesh has no weights of its own yet -
        # if this panel's path field already points at a previously saved
        # skin (Save Skin writes it there), load it back onto the new
        # mesh(es) right away instead of leaving them unskinned until the
        # user remembers to hit Load separately. Same lookup the JSON
        # panel's Load action already uses; a missing/blank path or a
        # load failure is silently non-fatal - Create itself still
        # succeeded either way.
        try:
            skin_path = self.field.text().strip()
            if skin_path and os.path.exists(skin_path) and self.mesh_field.text().strip():
                load_ok, load_err = self.workspace.load_skin_cluster_logic(
                    skin_path, self.mesh_field.text(),
                    show_popup=self.naming_popup_enabled())
                if load_ok:
                    cmds.warning(f"[KRT] Tweaker created and previously saved skin re-applied from: {skin_path}")
                else:
                    cmds.warning(f"[KRT] Tweaker created, but auto-loading the saved skin failed: {load_err}")
        except Exception:
            pass

        return True, ""

    def naming_popup_enabled(self):
        """Whether this panel's own 'Popup' tick (JSON/Tweaker only) wants
        the SkinCluster-naming confirmation shown. True for any panel type
        that doesn't have the tick at all, so callers can use this
        unconditionally without an extra hasattr check."""
        chk = getattr(self, 'chk_naming_popup', None)
        return chk.isChecked() if chk is not None else True

    def get_start_dir(self):
        current_path = self.field.text().strip()
        if os.path.isdir(current_path): return current_path
        elif os.path.isfile(current_path): return os.path.dirname(current_path)
        return ""

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        
        a_undo = menu.addAction("↩ Undo Delete/Cut")
        if not getattr(self.workspace, 'panel_undo_stack', None):
            a_undo.setEnabled(False)
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")
        
        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Default Script (Maya Global)")] = ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", offset)
            actions_map[m.addAction("Add Import 3D Model (.ma/.mb/.fbx/.obj/.abc)")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Material Panel")] = ("MATERIAL PANEL", "MATERIAL", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            actions_map[m.addAction("Add Tweaker Panel")] = ("TWEAKER SETUP", "TWEAKER", offset)
            actions_map[m.addAction("Add LOD Loader Panel (build entire LODs)")] = ("LOD LOADER", "LOD_LOADER", offset)
            actions_map[m.addAction("Add Note Panel (free-text, not a build step)")] = ("NOTE", "NOTE", offset)
            actions_map[m.addAction("Add Import 3D Model + LOD Organize")] = ("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", offset)
            actions_map[m.addAction("Add Delete-by-Name Panel")] = ("DELETE", "DELETE_OBJ", offset)
            actions_map[m.addAction("Add Zero Out Panel")] = ("ZERO OUT", "ZERO_OUT", offset)
            actions_map[m.addAction("Add Parent Panel")] = ("PARENT", "PARENT_OBJ", offset)
            actions_map[m.addAction("Add Instance Panel")] = ("INSTANCE", "INSTANCE_OBJ", offset)

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
        a_cut = menu.addAction("✂ Cut Panel")
        paste_above = menu.addAction("📋 Paste Panel (Above)")
        paste_below = menu.addAction("📋 Paste Panel (Below)")

        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)

        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here")
        a_load_cache = menu.addAction("📂 Load Cached Scene")
        a_build_from = menu.addAction("⏩ Build FROM Here (load cache + continue)")
        if not self.has_cache():
            a_load_cache.setEnabled(False)
            a_build_from.setEnabled(False)
        a_replace_paths = menu.addAction("🔀 Replace All Paths...")
        # Duplicate is available for every panel type, not just SCRIPT.
        a_dup = menu.addAction("📋 Duplicate Panel")
        menu.addSeparator()

        a_vs = a_load = a_comp = a_rem = a_save_over = a_save_new = None
        v_actions = {}

        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"):
            a_vs = menu.addAction("📝 Edit code in VS Code")
            a_load = menu.addAction("📂 Load any other file")
            a_comp = menu.addAction("⚖ Compare older script in VS Code")
            if is_script_file_ref(self.field.text()):
                # Stage 19: the field is currently locked to a .py/.mel file
                # path - this is the only way back to a normal, editable,
                # type-your-own-code field.
                a_rem = menu.addAction("❌ Clear (type code instead)")
        elif self.p_type in ("IMPORT_3D", "IMPORT_LOD"):
            a_load = menu.addAction("📂 Load 3D file (.ma/.mb/.fbx/.obj/.abc)")
            a_rem = menu.addAction("❌ Remove file")
        elif self.p_type == "JSON":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Skin (Overwrite)")
            a_save_new = menu.addAction("💾 Save Skin (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "TWEAKER":
            a_load = menu.addAction("📂 Set Skin Save Path")
            a_rem = menu.addAction("❌ Remove path")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Skin (Overwrite)")
            a_save_new = menu.addAction("💾 Save Skin (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "SHAPES":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Shapes (Overwrite)")
            a_save_new = menu.addAction("💾 Save Shapes (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "MATERIAL":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
            menu.addSeparator()
            a_save_over = menu.addAction("💾 Save Material (Overwrite)")
            a_save_new = menu.addAction("💾 Save Material (New Version)")
            switch_menu = menu.addMenu("🔄 Switch Version")
            v_actions = self.populate_versions_menu(switch_menu)
        elif self.p_type == "PUBLISH":
            a_load = menu.addAction("📂 Load new path")
            a_rem = menu.addAction("❌ Remove path")

        a_note_text_color = a_note_bg_color = a_note_size = None
        if self.p_type == "NOTE":
            a_note_text_color = menu.addAction("🎨 Change Note Text Color")
            a_note_bg_color = menu.addAction("🖌 Change Note Background Color")
            a_note_size = menu.addAction("🔠 Change Note Text Size...")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        
        if not action: return
        
        if action == a_undo: self.workspace.undo_last_panel_delete()
        elif action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
        elif action == a_cut: self.cut_panel()
        elif action == paste_above: self.paste_panel(0)
        elif action == paste_below: self.paste_panel(1)
        elif action == a_build_till: self.workspace.build_till_panel(self)
        elif action == a_load_cache: self.run_from_cache()
        elif action == a_build_from: self.build_from_cache()
        elif action == a_replace_paths: self.workspace.open_path_replace_dialog()
        elif action == a_vs:
            path = self.field.text()
            if not os.path.exists(path) and not path.endswith(".py") and not path.endswith(".mel"):
                om.MGlobal.displayError("Cannot open raw code in VS Code. Please save as a file first.")
            else:
                # Stage 17: falls back to KRT's own simple editor if VS Code
                # isn't found, instead of just erroring.
                self.workspace.open_script_externally(path)
        elif action == a_load: self.browse_file()
        elif action == a_dup: self.workspace.duplicate_panel(self)
        elif action == a_comp:
            kwargs = {'fm': 1, 'ff': "Python (*.py)", 'caption': "Select Older File to Compare"}
            sd = self.get_start_dir()
            if os.path.exists(sd): kwargs['dir'] = sd
            old_file = cmds.fileDialog2(**kwargs)
            if old_file: subprocess.Popen(f'code -d "{self.field.text()}" "{old_file[0]}"', shell=True)
        elif action == a_rem: self.field.setText("")
        elif action == a_save_over: self.save_versioned_data(overwrite=True)
        elif action == a_save_new: self.save_versioned_data(overwrite=False)
        elif action in v_actions: self.field.setText(v_actions[action])
        elif action == a_note_text_color: self.change_note_text_color()
        elif action == a_note_bg_color: self.change_note_bg_color()
        elif action == a_note_size:
            new_size, ok = QtWidgets.QInputDialog.getInt(
                self, "Note Text Size", "Size:", self.note_font_size, 8, 96)
            if ok:
                self.change_note_font_size(new_size)

    def _update_script_field_lock(self):
        """Stage 19: called on every edit to a SCRIPT/GLOBAL_SCRIPT panel's
        field (and once up front, for a value set by the constructor/Browse/
        Load that never fired textChanged). Locks the field, styled like the
        other read-only path fields, the moment it holds a real .py/.mel
        file path - stays a normal editable field for raw pasted code."""
        if self.p_type not in ("SCRIPT", "GLOBAL_SCRIPT"):
            return
        if is_script_file_ref(self.field.text()):
            style_readonly_path_field(self.field, self.accent)
        else:
            self.field.setReadOnly(False)
            self.field.setStyleSheet("")
            self.field.setToolTip(
                "Path to a .py/.mel script file (locks automatically once set), "
                "or paste raw Python/MEL code directly.")

    def browse_file(self):
        kwargs = {'fm': 1}
        # "All Files" is listed first so the dialog shows every file type by
        # default; the type-specific filters remain available as options.
        if self.p_type in ("SCRIPT", "GLOBAL_SCRIPT"): kwargs['ff'] = "All Files (*.*);;Scripts (*.py *.mel);;Python (*.py);;MEL (*.mel)"
        elif self.p_type in ["JSON", "SHAPES", "TWEAKER", "MATERIAL"]: kwargs['ff'] = "All Files (*.*);;JSON (*.jSkin *.json)"
        elif self.p_type in ("IMPORT_3D", "IMPORT_LOD"): kwargs['ff'] = "All Files (*.*);;3D Files (*.fbx *.obj *.abc *.ma *.mb);;FBX (*.fbx);;OBJ (*.obj);;Alembic (*.abc);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        elif self.p_type == "PUBLISH": kwargs['fm'] = 3; kwargs['caption'] = "Select Publish Directory"
        else: return
        
        sd = self.get_start_dir()
        if os.path.exists(sd): kwargs['dir'] = sd
        res = cmds.fileDialog2(**kwargs)
        if res: self.field.setText(res[0])

    def execute(self, progress_ui=None):
        if not self.is_active: return True
        # A NOTE panel is never a build step - it has no RUN button to
        # click (hidden in __init__) and nothing to run even if something
        # called this directly, so always succeed without doing anything.
        if self.p_type == "NOTE": return True
        success = False
        error_msg = ""
        self.btn_run.setText("RUNNING...")

        local_ui = False
        if progress_ui is None:
            self.workspace.main_window.setEnabled(False)
            progress_ui = BuildProgressDialog(self.workspace, total_steps=1)
            progress_ui.lbl_status.setText(f"Executing: {self.title_edit.text()}")
            progress_ui.show()
            local_ui = True

        QtWidgets.QApplication.processEvents()
        start_t = time.time()

        try:
            if progress_ui.is_cancelled:
                success = False
                error_msg = "Cancelled by user."
            else:
                if self.p_type == "SCRIPT":
                    func_call_txt = self.func_field.text().strip()
                    success, error_msg = self.workspace.run_script(self.field.text(), func_call=func_call_txt)
                elif self.p_type == "GLOBAL_SCRIPT":
                    func_call_txt = self.func_field.text().strip()
                    success, error_msg = self.workspace.run_script_global(self.field.text(), func_call=func_call_txt)
                elif self.p_type == "IMPORT_3D":
                    # Stage 18: MA and IMPORT_3D merged into one panel type -
                    # import_3d_logic already auto-detects by extension
                    # (.abc/.fbx/.obj get their dedicated importer, anything
                    # else - including .ma/.mb - falls back to cmds.file()).
                    success, error_msg = self.workspace.import_3d_logic(self.field.text())
                elif self.p_type == "JSON":
                    success, error_msg = self.workspace.load_skin_cluster_logic(
                        self.field.text(), self.mesh_field.text(),
                        show_popup=self.naming_popup_enabled())
                    # Stage 33: re-skin runs automatically after a
                    # successful load, but ONLY if at least one Scale
                    # Control is listed - an empty Scale Control(s) field
                    # means "no re-skin at all", not "re-skin with no
                    # scaling". It also only runs if the weights actually
                    # loaded, since re-binding on top of a failed load would
                    # just bake in whatever wrong state the mesh was left in.
                    meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                    controls, scale = self.reskin_settings()
                    if success and meshes and controls:
                        success, error_msg = self.workspace.run_reskin_logic(meshes, controls, scale)
                elif self.p_type == "TWEAKER":
                    success, error_msg = self._execute_tweaker()
                elif self.p_type == "SHAPES":
                    if os.path.exists(self.field.text()) or os.path.exists(get_versioned_path(self.field.text(), True)):
                        try:
                            success = import_control_shapes(self.field.text())
                            if not success: error_msg = "Failed to import shapes."
                        except Exception as e:
                            success = False; error_msg = traceback.format_exc()
                    else:
                        success = False
                        error_msg = f"Shape file not found: {self.field.text()}"
                elif self.p_type == "MATERIAL":
                    if os.path.exists(self.field.text()) or os.path.exists(get_versioned_path(self.field.text(), True)):
                        try:
                            meshes = [m.strip() for m in self.mesh_field.text().split(",") if m.strip()]
                            success = import_material_data(self.field.text(), meshes=meshes if meshes else None)
                            if not success: error_msg = "Failed to import material."
                        except Exception as e:
                            success = False; error_msg = traceback.format_exc()
                    else:
                        success = False
                        error_msg = f"Material file not found: {self.field.text()}"
                elif self.p_type == "PUBLISH":
                    if os.path.exists(self.field.text()):
                        success = True
                        cmds.warning("Publish Path Validated.")
                    else:
                        success = False
                        error_msg = "Publish Path does not exist!"
                elif self.p_type == "IMPORT_LOD":
                    # Same import_3d_logic() as IMPORT_3D, then
                    # organize_lod_logic() runs over the scene the import
                    # just landed in. A blank file path is allowed (the
                    # rigger may just want to re-organize a scene that's
                    # already been imported/assembled by hand) - only the
                    # organize step is required to have run.
                    path = self.field.text().strip()
                    if path:
                        success, error_msg = self.workspace.import_3d_logic(path)
                        if not success:
                            pass  # don't attempt to organize on a failed import
                        else:
                            success, error_msg = self.workspace.organize_lod_logic(
                                self.asset_name_field.text())
                    else:
                        success, error_msg = self.workspace.organize_lod_logic(
                            self.asset_name_field.text())
                elif self.p_type == "DELETE_OBJ":
                    success, error_msg = self.workspace.delete_by_name_logic(self.target_field.text())
                elif self.p_type == "ZERO_OUT":
                    success, error_msg = self.workspace.zero_out_logic(self.target_field.text())
                elif self.p_type == "PARENT_OBJ":
                    success, error_msg = self.workspace.parent_logic(
                        self.child_field.text(), self.parent_field.text())
                elif self.p_type == "INSTANCE_OBJ":
                    success, error_msg = self.workspace.create_instances_logic(
                        self.target_field.text(), self.field.text(),
                        self.func_field.text(), panel_uuid=self.uuid)
        finally:
            QtWidgets.QApplication.processEvents() 
            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)

            if local_ui:
                progress_ui.progress_bar.setValue(1)
                progress_ui.close()
                self.workspace.main_window.setEnabled(True)

            if success:
                self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
                self.btn_run.setText(panel_run_label(self.p_type))
                self.last_error_msg = ""
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(False)
                # Manual click (not part of a build): cache this step too.
                if local_ui and self.p_type != "PUBLISH":
                    self.cache_on_manual_run()
            else:
                self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
                self.btn_run.setText("SHOW ERROR")
                self.last_error_msg = error_msg if error_msg else "Unknown execution failure."
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(True)

        return success


class SortableBubblePanel(CacheMixin, QtWidgets.QFrame):
    def __init__(self, title, workspace):
        super(SortableBubblePanel, self).__init__()
        self.p_type = "MODULE"
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint("MODULE")
        self.accent = type_accent("MODULE")
        self.uuid = uuid.uuid4().hex
        # Bubble currently being dragged for in-panel reordering (see
        # ModuleBubble._start_drag / BubbleDropArea) - None the rest of the time.
        self.dragging_bubble = None
        # Live dashed-outline placeholder (_BubbleDropGap) shown while
        # dragging_bubble is set, tracking where it would land right now -
        # see _show_drop_gap/_clear_drop_gap below. None the rest of the time.
        self.drop_gap = None
        self._drop_gap_target = None

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(self.toggle_active)

        self.icon_label = QtWidgets.QLabel(type_icon("MODULE"))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip("Module")

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox); header_layout.addWidget(self.icon_label); header_layout.addWidget(self.title_edit); header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        ctrl_layout.addWidget(self.btn_del)
        
        self.bubble_area = BubbleDropArea(self)
        # Stage 35: wraps onto additional rows instead of running module
        # bubbles off the edge of the panel once there are enough of them.
        self.bubble_layout = FlowLayout(self.bubble_area, margin=0, h_spacing=4, v_spacing=4)
        
        btn_add_mod = QtWidgets.QPushButton("+ Add Module")
        btn_add_mod.setFixedWidth(100)
        btn_add_mod.clicked.connect(self.add_module_bubble)
        
        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.clicked.connect(self.show_context_menu)

        self.btn_run = QtWidgets.QPushButton("LOAD")
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.on_btn_run_clicked)
        
        body_layout.addLayout(ctrl_layout)
        body_layout.addWidget(self.bubble_area)
        body_layout.addWidget(btn_add_mod)
        body_layout.addWidget(btn_dots)
        self._build_cache_controls(body_layout)
        body_layout.addWidget(self.btn_run)

        # Reset-error button (hidden until this panel is in the SHOW ERROR state).
        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        body_layout.addWidget(self.btn_reset_err)

        self._build_cache_tick(body_layout)

        # Stage 35: now that self.bubble_area can be several rows tall (the
        # FlowLayout wrap fix above), a plain QHBoxLayout centers every
        # OTHER widget in the row on the full height of that tall block -
        # "+ Add Module" / LOAD / etc. drift down into empty space to the
        # right instead of lining up the way they do on every other panel
        # type (where the row is always exactly one line tall). Pinning
        # everything except the bubble area itself to the top keeps them
        # level with the FIRST row of bubbles, same as before there was
        # ever more than one row.
        for i in range(body_layout.count()):
            item = body_layout.itemAt(i)
            target = item.widget() or item.layout()
            if target is not None and target is not self.bubble_area:
                body_layout.setAlignment(target, QtCore.Qt.AlignTop)

        main_layout.addLayout(body_layout)
        self.btn_del.clicked.connect(lambda: self.workspace.delete_panel(self))

    def reset_run_button(self):
        """Restore the LOAD button to normal after an error, without re-running."""
        self.btn_run.setText("LOAD")
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def update_style(self):
        accent = getattr(self, 'accent', '#2bb5a8')
        self.setStyleSheet(
            f"SortableBubblePanel {{ background: {self.bg_color}; border: 1px solid #333;"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" SortableBubblePanel:hover {{ border: 1px solid #555; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
        elif p_type == "LOD_LOADER":
            self.workspace.add_lod_loader_panel(title, index=idx)
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active, "bg_color": self.bg_color}
        if self.p_type == "MODULE":
            mods = [{"path": self.bubble_layout.itemAt(b).widget().full_path, "active": self.bubble_layout.itemAt(b).widget().is_active} for b in range(self.bubble_layout.count())]
            data["modules"] = mods
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

    def cut_panel(self):
        """Stage 22, request #1: Copy Panel, then delete this panel -
        delete_panel() itself pushes the removed panel onto the workspace's
        undo stack, so a Cut can still be undone same as a plain Delete."""
        self.copy_panel()
        self.workspace.delete_panel(self)

    def paste_panel(self, offset):
        data = getattr(self.workspace.main_window, 'clipboard_panel_data', None)
        if not data: return
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset

        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.workspace.add_module_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            for m in data.get("modules", []):
                pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
            if not is_act: pan.checkbox.setChecked(False)
        else:
            pan = self.workspace.add_panel(title, p_type, data.get("path", ""), index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            if not is_act: pan.checkbox.setChecked(False)
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                if data.get("asset_name"): pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT") and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))
            if p_type == "INSTANCE_OBJ" and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
                if data.get("func_call") and hasattr(pan, 'func_field'): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            self.execute(None)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #2bb5a8; font-weight: bold; color: white; font-size: 13px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(SortableBubblePanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {getattr(self, 'accent', '#2bb5a8')}; font-size: 13px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(SortableBubblePanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton): 
            return super(SortableBubblePanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(SortableBubblePanel, self).mouseMoveEvent(event)
            
        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance(): 
            return super(SortableBubblePanel, self).mouseMoveEvent(event)

        self.workspace.dragged_panel = self
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText("panel_drag")
        drag.setMimeData(mime_data)
        
        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        if IS_PYSIDE6: drag.exec(QtCore.Qt.MoveAction)
        else: drag.exec_(QtCore.Qt.MoveAction)
            
        self.workspace.dragged_panel = None
        super(SortableBubblePanel, self).mouseMoveEvent(event)

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")

        a_undo = menu.addAction("↩ Undo Delete/Cut")
        if not getattr(self.workspace, 'panel_undo_stack', None):
            a_undo.setEnabled(False)
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")

        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Default Script (Maya Global)")] = ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", offset)
            actions_map[m.addAction("Add Import 3D Model (.ma/.mb/.fbx/.obj/.abc)")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Material Panel")] = ("MATERIAL PANEL", "MATERIAL", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            actions_map[m.addAction("Add Tweaker Panel")] = ("TWEAKER SETUP", "TWEAKER", offset)
            actions_map[m.addAction("Add LOD Loader Panel (build entire LODs)")] = ("LOD LOADER", "LOD_LOADER", offset)
            actions_map[m.addAction("Add Note Panel (free-text, not a build step)")] = ("NOTE", "NOTE", offset)
            actions_map[m.addAction("Add Import 3D Model + LOD Organize")] = ("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", offset)
            actions_map[m.addAction("Add Delete-by-Name Panel")] = ("DELETE", "DELETE_OBJ", offset)
            actions_map[m.addAction("Add Zero Out Panel")] = ("ZERO OUT", "ZERO_OUT", offset)
            actions_map[m.addAction("Add Parent Panel")] = ("PARENT", "PARENT_OBJ", offset)
            actions_map[m.addAction("Add Instance Panel")] = ("INSTANCE", "INSTANCE_OBJ", offset)

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
        a_cut = menu.addAction("✂ Cut Panel")
        paste_above = menu.addAction("📋 Paste Panel (Above)")
        paste_below = menu.addAction("📋 Paste Panel (Below)")

        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)

        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here")
        a_dup = menu.addAction("📋 Duplicate Panel")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())

        if not action: return

        if action == a_undo: self.workspace.undo_last_panel_delete()
        elif action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
        elif action == a_cut: self.cut_panel()
        elif action == paste_above: self.paste_panel(0)
        elif action == paste_below: self.paste_panel(1)
        elif action == a_build_till: self.workspace.build_till_panel(self)
        elif action == a_dup: self.workspace.duplicate_panel(self)

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)

    def _show_drop_gap(self, drop_area, size, target_widget):
        """Move the live drop-placeholder to sit immediately before
        `target_widget` (or at the very end if `target_widget` is None) -
        resolved via a fresh layout.indexOf() lookup every call, so it's
        always correct regardless of where the dragged bubble (still a
        real item in the layout, just excluded from _target_index's own
        count) or the gap itself currently happen to sit in the raw
        layout. A plain numeric index couldn't make that same guarantee -
        see _target_index's docstring for the off-by-one this replaced.
        This is a no-op when it's already exactly there, so hovering in
        place during a drag doesn't thrash the layout on every single
        mouse-move event."""
        if self.drop_gap is not None and self._drop_gap_target is target_widget:
            return
        layout = self.bubble_layout
        if self.drop_gap is None:
            self.drop_gap = _BubbleDropGap(size)
            self.drop_gap.setParent(drop_area)
            self.drop_gap.show()
        else:
            layout.removeWidget(self.drop_gap)
        index = layout.indexOf(target_widget) if target_widget is not None else layout.count()
        if index == -1:
            index = layout.count()
        layout.insertWidget(index, self.drop_gap)
        self._drop_gap_target = target_widget

    def _clear_drop_gap(self):
        """Remove the live drop-placeholder, if one is currently shown.
        Called on drop, on the drag leaving the panel without dropping, and
        as a safety net once ModuleBubble._start_drag's blocking drag.exec_()
        call returns no matter how it ended, so a cancelled/failed drag can
        never leave a stray placeholder bubble sitting in the layout (which
        would otherwise corrupt this panel's saved build order - every other
        bubble_layout reader assumes every item is a real ModuleBubble with
        a .full_path)."""
        if self.drop_gap is None:
            return
        self.bubble_layout.removeWidget(self.drop_gap)
        # removeWidget() (a QLayout base-class method, not FlowLayout's own
        # insertWidget) only posts a deferred relayout - force it now so the
        # remaining bubbles snap back to their real slots immediately
        # instead of momentarily overlapping the spot the gap just vacated.
        self.bubble_layout.activate()
        self.drop_gap.setParent(None)
        self.drop_gap.deleteLater()
        self.drop_gap = None
        self._drop_gap_target = None

    def add_module_bubble(self, pre_path=None, is_active=True):
        if not pre_path:
            menu = QtWidgets.QMenu(self)
            menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
            a_file = menu.addAction("📂 Browse from File")
            a_graph = menu.addAction("🔌 Add from Graph Editor")
            action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
            
            if action == a_file:
                kwargs = {'fm': 1, 'ff': "All Files (*.*);;Module Files (*.py *.sgt);;Python (*.py);;mGear Guide (*.sgt)"}
                if self.bubble_layout.count() > 0:
                    last_path = self.bubble_layout.itemAt(self.bubble_layout.count()-1).widget().full_path
                    sd = os.path.dirname(last_path)
                    if os.path.exists(sd): kwargs['dir'] = sd

                res = cmds.fileDialog2(**kwargs)
                if not res: return
                pre_path = res[0]
                
                bubble = ModuleBubble(os.path.basename(pre_path), pre_path, is_active=is_active)
                bubble.closed.connect(self.remove_bubble)
                bubble.execute_req.connect(self.execute_single_module)
                bubble.locate_req.connect(self.locate_bubble_in_graph)
                self.bubble_layout.addWidget(bubble)
                
            elif action == a_graph:
                from .graph import RigNode, CUSTOM_SCRIPT_MODULE_TYPE
                # Stage 30: "we don't need to call it in bubble module panel
                # as well just to run it. it is just a script which will
                # automatically trigger when some specific module will
                # build" - a Custom Script node has no guide of its own
                # (build_node_guide always returns None for it), so adding
                # one here would only ever show up as a build failure in
                # this panel's LOAD flow. It already runs on its own, via
                # its own trigger dependency (graph parent, or the "Trigger
                # after module" pick in its Custom Script settings) - never
                # by being included in a bubble panel's batch.
                all_nodes = [item for item in self.workspace.graph_widget.graph_view.scene.items()
                             if isinstance(item, RigNode) and item.module_type != CUSTOM_SCRIPT_MODULE_TYPE]
                if not all_nodes:
                    cmds.warning("No modules exist in the Graph Editor yet!")
                    return
                all_nodes.sort(key=lambda n: n.display_title.lower())

                # Modules already in THIS panel, in their current bubble
                # order - GraphNodeOrderDialog pre-numbers and locks these
                # ("last time's" order), so reopening this dialog just to
                # add one more module doesn't lose or reshuffle what's
                # already here; only genuinely new picks come back needing
                # a bubble below.
                existing_uuids = [b.full_path.split("::")[1]
                                   for i in range(self.bubble_layout.count())
                                   for b in [self.bubble_layout.itemAt(i).widget()]
                                   if b.full_path.startswith("GRAPH::")]

                # A popup to multi-select modules AND set the order they're
                # added in, instead of one at a time via sidebar selection.
                dialog = GraphNodeOrderDialog(all_nodes, existing_uuids, self.workspace.main_window)
                result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
                if result != QtWidgets.QDialog.Accepted:
                    return

                new_nodes = [n for n in dialog.order if n.uuid not in dialog.locked_uuids]
                for node in new_nodes:
                    v_path = f"GRAPH::{node.uuid}"
                    v_name = node.display_title
                    bubble = ModuleBubble(v_name, v_path, is_active=is_active)
                    bubble.closed.connect(self.remove_bubble)
                    bubble.execute_req.connect(self.execute_single_module)
                    bubble.locate_req.connect(self.locate_bubble_in_graph)
                    self.bubble_layout.addWidget(bubble)
            return
        else:
            name = os.path.basename(pre_path)
            if pre_path.startswith("GRAPH::"):
                node_uuid = pre_path.split("::")[1]
                n = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
                if n: name = n.display_title
                else: name = "Graph Node (Not Found)"
                
            bubble = ModuleBubble(name, pre_path, is_active=is_active)
            bubble.closed.connect(self.remove_bubble)
            bubble.execute_req.connect(self.execute_single_module)
            bubble.locate_req.connect(self.locate_bubble_in_graph)
            self.bubble_layout.addWidget(bubble)

    def remove_bubble(self, widget):
        self.bubble_layout.removeWidget(widget)
        widget.deleteLater()

    def locate_bubble_in_graph(self, bubble):
        """Stage 30: the bubble's own locate button ('select & highlight
        that module in graph', for when a panel has a lot of bubbles and
        it's hard to tell which graph node a given one actually is) -
        switches to the Graph Editor tab, selects just that node, and
        centers the view on it. Only meaningful for a GRAPH:: bubble; the
        button is hidden for a plain file-path bubble (see ModuleBubble),
        so this shouldn't normally be reached for one, but still guards
        against it just in case."""
        path = bubble.full_path
        if not path.startswith("GRAPH::"):
            cmds.warning("This module points at a file on disk, not a Graph Editor module.")
            return
        node_uuid = path.split("::")[1]
        node = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
        if not node:
            cmds.warning("That module no longer exists in the Graph Editor.")
            return

        self.workspace.switch_tab(2)  # Graph Editor page
        scene = self.workspace.graph_widget.graph_view.scene
        scene.clearSelection()
        node.setSelected(True)
        self.workspace.graph_widget.graph_view.centerOn(node)
        self.workspace.graph_widget.update_attr_editor()
        if hasattr(self.workspace, 'sync_graph_to_list'):
            self.workspace.sync_graph_to_list()

    def _build_bubble_guide(self, bubble):
        """Resolve a GRAPH:: bubble to its graph node and draw (or reuse) its
        guide. Does NOT build the rig or touch the scene otherwise - that's
        left to _finish_graph_batch so a panel's LOAD button can draw every
        guide first before building anything.
        Returns (ok, error_msg, node, root)."""
        path = bubble.full_path
        node_uuid = path.split("::")[1]
        node = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
        if not node:
            return False, f"Graph node with UUID {node_uuid} not found.", None, None

        # Stage 30: a Custom Script node has no guide of its own by design
        # (it runs off its own trigger dependency instead) - this bubble
        # can only be here from before that node type was excluded from
        # "Add from Graph Editor", so say so plainly instead of the generic
        # "could not build guide" a caller would otherwise see below.
        from .graph import CUSTOM_SCRIPT_MODULE_TYPE
        if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            return (False,
                    f"'{node.display_title}' is a Custom Script module - it has no guide to build "
                    "and doesn't belong in a Module Bubbles panel. Remove this bubble; the script "
                    "already runs on its own via its Trigger dependency.",
                    None, None)

        try:
            from mgear import shifter as mg_shifter
            import mgear.pymaya as pm
        except ImportError:
            return False, "mGear is not installed/loaded in this Maya session.", None, None

        # Draws the guide (if it isn't already built) and recursively builds
        # any parent components wired above it in the graph.
        root = self.workspace.graph_widget.build_node_guide(node, mg_shifter, pm)
        if not root:
            return False, f"Could not build guide for '{node.display_title}' - see Script Editor.", None, None

        return True, "", node, root

    def _finish_graph_batch(self, pending):
        """Second half of a GRAPH:: bubble LOAD: given [(bubble, node, root), ...]
        whose guides are ALL already drawn, build every one of them in a
        single Shifter build (not one build per bubble), run each node's
        "after Build Modules" custom script, then delete every guide this
        batch touched - including the shared top-level guide group(s), not
        just each component's own root, since the whole batch is done with
        them once the build succeeds.
        Returns (ok, [error_msg, ...])."""
        if not pending:
            return True, []

        try:
            from mgear import shifter as mg_shifter
        except ImportError:
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["mGear is not installed/loaded in this Maya session."]

        roots = [root for (_, _, root) in pending if root and cmds.objExists(root)]
        if not roots:
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["None of the drawn guides still exist in the scene - nothing to build."]

        try:
            cmds.select(roots, replace=True)
            mg_shifter.Rig().buildFromSelection()
        except Exception as e:
            err = traceback.format_exc()
            log_crash("Build Modules ({} node(s))".format(len(pending)), e)
            for bubble, node, root in pending:
                bubble.set_error()
            return False, ["[Build Modules]:\n" + err]

        for bubble, node, root in pending:
            self.workspace.graph_widget.run_node_custom_script(node, "modules")
            self.workspace.graph_widget.run_node_auto_scripts(node, "modules")
            bubble.set_success()

        self._delete_batch_guides(pending)
        return True, []

    def _delete_batch_guides(self, pending):
        """Delete every guide a just-built batch consumed, including the
        shared top-level guide group(s) they hang off of (mGear's "ismodel"
        marker), not just each component's own root. Safe to call once a
        build from `pending`'s roots has already succeeded."""
        guide_groups = set()
        for bubble, node, root in pending:
            if not root or not cmds.objExists(root):
                continue
            try:
                walker = root
                while walker:
                    if cmds.attributeQuery("ismodel", node=walker, exists=True):
                        guide_groups.add(walker)
                        break
                    parents = cmds.listRelatives(walker, parent=True, fullPath=True)
                    walker = parents[0] if parents else None
            except Exception:
                pass

        to_delete = guide_groups or {root for (_, _, root) in pending if root and cmds.objExists(root)}
        for grp in to_delete:
            try:
                if cmds.objExists(grp):
                    cmds.delete(grp)
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Could not auto-delete guide group '{grp}' - see Script Editor.")

        for bubble, node, root in pending:
            node.maya_guide_root = None
            node.update_display()

        gw = self.workspace.graph_widget
        if hasattr(gw, "_invalidate_attach_points_cache"):
            gw._invalidate_attach_points_cache()
        gw.update_attr_editor()
        if hasattr(gw, "guide_settings_panel"):
            gw.guide_settings_panel.refresh_from_scene()
        self.workspace.refresh_module_list()

    def execute_single_module(self, bubble):
        if not self.is_active or not bubble.is_active: return True, ""
        path = bubble.full_path
        success = False
        error_msg = ""
        QtWidgets.QApplication.processEvents()

        try:
            if path.startswith("GRAPH::"):
                ok, err, node, root = self._build_bubble_guide(bubble)
                if not ok:
                    bubble.set_error()
                    return False, err
                success, errs = self._finish_graph_batch([(bubble, node, root)])
                error_msg = "\n\n".join(errs)
                return success, error_msg

            elif path.endswith(".py"):
                success, error_msg = self.workspace.run_script(path)
            elif path.endswith(".sgt"):
                success, error_msg = self.workspace.run_mgear_sgt(path)
        except Exception as e:
            error_msg = traceback.format_exc()
            log_crash("Module bubble ({})".format(path), e)
            success = False

        if success: bubble.set_success()
        else: bubble.set_error()
        return success, error_msg

    def execute(self, progress_ui=None):
        if not self.is_active: return True
        all_success = True
        error_msgs = []

        self.btn_run.setText("RUNNING...")

        # Same fix graph.py's own "Build Guides" button already has: hold the
        # Graph Editor's live guide-placement watcher (the red/green dot)
        # while this panel is actually drawing guides below. Its QTimer
        # ticks every 1.5s and reads guide positions off the live scene - the
        # progress dialog's own QApplication.processEvents() calls further
        # down (needed to keep the UI responsive/cancellable during a long
        # batch) can let that timer fire mid-build, catching a guide that's
        # only half-drawn or not yet repositioned to its saved placement and
        # flashing the dot red for no real reason. Suspended here for the
        # whole batch, not just the "guides" sub-step, since GRAPH:: bubbles
        # draw guides interleaved with non-graph bubbles (scripts/.sgt) in
        # this same loop.
        graph_widget = getattr(self.workspace, "graph_widget", None)
        if graph_widget is not None:
            graph_widget._pos_watch_suspended = True

        local_ui = False
        if progress_ui is None:
            self.workspace.main_window.setEnabled(False)
            progress_ui = BuildProgressDialog(self.workspace, total_steps=self.bubble_layout.count())
            progress_ui.lbl_status.setText(f"Executing: {self.title_edit.text()}")
            progress_ui.show()
            local_ui = True

        QtWidgets.QApplication.processEvents()
        start_t = time.time()

        # GRAPH:: bubbles are batched: every guide in this panel is drawn
        # first (in bubble order, so a later bubble can attach onto an
        # earlier one's freshly-drawn guide), THEN every module is built in
        # one Shifter build, and only THEN are the guides deleted - see
        # _finish_graph_batch/_delete_batch_guides. Non-graph bubbles (a raw
        # .py script or a .sgt guide template added via "Browse from File")
        # aren't part of that and still just run in place, same as before.
        #
        # "Bubble order" for the GRAPH:: ones specifically means the same
        # hierarchy-stable order the Graph Editor's own "Build Guides (From
        # Sidebar Selection)"/"Build Modules (From Sidebar Selection)"
        # buttons use (_sorted_by_hierarchy: a node's graph parent, when
        # also present in this build, always comes before it) - not
        # whatever order the pills happen to be dragged/dropped into in
        # this panel, which is purely a display/organizing convenience (see
        # the bubble reorder/gap feature above). build_node_guide already
        # recurses upward to build a missing parent guide regardless, so
        # this reordering isn't required for correctness, but it makes this
        # panel's build behave identically to selecting the same modules in
        # the Graph Editor and building them there - which is the one thing
        # this panel is meant to add on top of (batching every guide draw,
        # then one combined rig build, then deleting the guide group -
        # everything else should match the Graph Editor's own flow exactly,
        # per spec). Non-GRAPH:: bubbles (.py scripts / .sgt templates) have
        # no graph hierarchy and keep their original panel-order slot.
        bubble_order = [self.bubble_layout.itemAt(i).widget() for i in range(self.bubble_layout.count())]
        if graph_widget is not None:
            graph_slots = [(pos, b) for pos, b in enumerate(bubble_order)
                            if b.full_path.startswith("GRAPH::")]
            node_of = {}
            for pos, b in graph_slots:
                n = graph_widget.get_node_by_uuid(b.full_path.split("::")[1])
                if n is not None:
                    node_of[b] = n
            if node_of:
                sorted_nodes = graph_widget._sorted_by_hierarchy(list(node_of.values()))
                bubble_of_node = {n: b for b, n in node_of.items()}
                sorted_bubbles = [bubble_of_node[n] for n in sorted_nodes]
                # Only the slots whose bubble actually resolved to a graph
                # node get reassigned, and in that same relative order they
                # already held (positions is built from graph_slots, which
                # is in original panel order) - so if raw slot 1 resolved
                # and raw slot 3 resolved, slot 1 gets whichever of the two
                # comes first in hierarchy order and slot 3 gets the other,
                # rather than shifting either one into a completely
                # different position in the panel. A bubble whose graph
                # node couldn't be resolved (a stale UUID) is simply never
                # in `positions` here, so its slot in bubble_order is left
                # untouched - it stays exactly where it was, and
                # _build_bubble_guide still runs on it below and reports
                # its own "not found" error, same as it always has.
                positions = [pos for pos, b in graph_slots if b in node_of]
                for pos, b in zip(positions, sorted_bubbles):
                    bubble_order[pos] = b

        pending_graph = []

        try:
            for i, bubble in enumerate(bubble_order):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    all_success = False
                    error_msgs.append("Cancelled by user.")
                    break

                if bubble.is_active:
                    if local_ui:
                        progress_ui.lbl_status.setText(f"Building guide: {bubble.text}")
                        progress_ui.progress_bar.setValue(i)

                    path = bubble.full_path
                    if path.startswith("GRAPH::"):
                        # _build_bubble_guide (and the mgear guide-drawing
                        # calls under it) previously had nothing catching an
                        # exception here - it would bubble all the way out
                        # of this panel's LOAD click uncaught. Wrapped so a
                        # guide-build failure becomes a normal SHOW ERROR
                        # like every other panel type, and gets durably
                        # logged for check_last_session_health() either way.
                        try:
                            ok, err, node, root = self._build_bubble_guide(bubble)
                        except Exception as e:
                            ok, err, node, root = False, traceback.format_exc(), None, None
                            log_crash("Build guide: {}".format(bubble.text), e)
                        if not ok:
                            all_success = False
                            error_msgs.append(f"[{bubble.text}]:\n{err}")
                            bubble.set_error()
                            break
                        pending_graph.append((bubble, node, root))
                    else:
                        success, err = self.execute_single_module(bubble)
                        if not success:
                            all_success = False
                            error_msgs.append(f"[{bubble.text}]:\n{err}")
                            break

            if all_success and pending_graph:
                if local_ui:
                    progress_ui.lbl_status.setText(f"Building {len(pending_graph)} module(s)...")
                QtWidgets.QApplication.processEvents()
                ok, errs = self._finish_graph_batch(pending_graph)
                if not ok:
                    all_success = False
                    error_msgs.extend(errs)
        finally:
            if graph_widget is not None:
                graph_widget._pos_watch_suspended = False
                # Settle the dot immediately off the now-finished (guides
                # deleted post-build, or left in place on a failure/cancel)
                # scene state, instead of waiting up to 1.5s for the next
                # timer tick.
                if hasattr(graph_widget, "_refresh_position_watch"):
                    graph_widget._refresh_position_watch()

            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)

            if local_ui:
                progress_ui.progress_bar.setValue(self.bubble_layout.count())
                progress_ui.close()
                self.workspace.main_window.setEnabled(True)

            if all_success and self.bubble_layout.count() > 0:
                self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
                self.btn_run.setText("LOAD")
                self.last_error_msg = ""
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(False)
                if local_ui:
                    self.cache_on_manual_run()
            else:
                self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
                self.btn_run.setText("SHOW ERROR")
                self.last_error_msg = "\n\n".join(error_msgs) if error_msgs else "Unknown execution failure."
                if hasattr(self, 'btn_reset_err'):
                    self.btn_reset_err.setVisible(True)

        return all_success



class LodLoaderBubble(QtWidgets.QFrame):
    """Stage 21: one bubble in a LOD Loader panel - a single LOD picked to
    be included in this panel's LOAD build, in the order it was added.
    Click the name to jump to that LOD's own panels; × removes it from
    this panel (it stays a real LOD, of course - this only removes it from
    THIS panel's build list)."""

    closed = QtCore.Signal(object)
    jump_req = QtCore.Signal(str)

    def __init__(self, name):
        super(LodLoaderBubble, self).__init__()
        self.name = name
        self.setStyleSheet(
            "LodLoaderBubble { background:#3e3e42; border-radius: 10px; border:1px solid #555; }")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.btn_text = QtWidgets.QPushButton(name)
        self.btn_text.setFlat(True)
        self.btn_text.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_text.setStyleSheet("background: transparent; border: none; color: #ccc; font-weight: bold;")
        self.btn_text.setToolTip("Click to jump to this LOD's panels")
        self.btn_text.clicked.connect(lambda: self.jump_req.emit(self.name))
        layout.addWidget(self.btn_text)

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setToolTip("Remove from this panel")
        self.close_btn.setStyleSheet("background: transparent; border: none; color: #e57373; font-weight: bold;")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))
        layout.addWidget(self.close_btn)


class LodLoaderPanel(QtWidgets.QFrame):
    """A panel type that builds ENTIRE LODs, one RUN click at a time - the
    corrected form of Stage 19's "LOD Build Manager" request (Stage 20).
    Stage 23: its button reads RUN, not LOAD - it's a normal step that
    participates in ordered runs (Build Till Here, etc) same as any other
    panel, not a special separate action.
    Lives inside a LOD's own panel stack in the Rig Build Workspace,
    addable the same way Control Shapes / Module Bubbles panels are (the
    "+Add New Panel" dropdown and the right-click "Add Panel" submenus),
    and is visually distinct via its own PANEL_TYPE_ACCENTS/ICONS/BG_TINT
    entry ("LOD_LOADER").

    Stage 21 revision: sized and laid out exactly like a Module Bubbles
    panel instead of the taller, list-based Stage 20 layout - a "+ Add LOD"
    button opens a menu of real LODs not already in this panel (pick which
    ones you want, instead of starting with every LOD pre-added), each
    picked LOD becomes a small bubble (LodLoaderBubble) in the order
    added, and there's no manual Sync button anymore - this panel listens
    directly to the real LOD list (self.workspace.lod_list) and prunes any
    bubble whose LOD gets deleted or renamed elsewhere, automatically.

    Does not use CacheMixin: caching one step doesn't compose meaningfully
    when the "step" is itself a full multi-panel LOD build.
    """

    def __init__(self, title, workspace):
        super(LodLoaderPanel, self).__init__()
        self.p_type = "LOD_LOADER"
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = type_bg_tint("LOD_LOADER")
        self.accent = type_accent("LOD_LOADER")
        self.uuid = uuid.uuid4().hex
        self.lod_bubbles = []

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(self.toggle_active)

        self.icon_label = QtWidgets.QLabel(type_icon("LOD_LOADER"))
        self.icon_label.setStyleSheet("font-size: 14px;")
        self.icon_label.setToolTip("LOD Loader - builds entire LODs")

        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox); header_layout.addWidget(self.icon_label); header_layout.addWidget(self.title_edit); header_layout.addStretch()
        main_layout.addLayout(header_layout)

        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        ctrl_layout.addWidget(self.btn_del)

        self.bubble_area = QtWidgets.QWidget()
        # Stage 35: same wrapping fix as the Module Bubbles panel - enough
        # LOD bubbles added here used to run off the edge the same way.
        self.bubble_layout = FlowLayout(self.bubble_area, margin=0, h_spacing=4, v_spacing=4)

        btn_add_lod = QtWidgets.QPushButton("+ Add LOD")
        btn_add_lod.setFixedWidth(100)
        btn_add_lod.setToolTip("Pick which LOD to add to this panel's build list.")
        btn_add_lod.clicked.connect(self.add_lod_bubble_picker)

        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.clicked.connect(self.show_context_menu)

        self.btn_run = QtWidgets.QPushButton("🚀 RUN")
        self.btn_run.setFixedWidth(130)
        self.btn_run.setStyleSheet("background-color: #ffca28; color: #1a1a1a; font-weight: bold;")
        self.btn_run.clicked.connect(self.on_btn_run_clicked)

        body_layout.addLayout(ctrl_layout)
        body_layout.addWidget(self.bubble_area)
        body_layout.addWidget(btn_add_lod)
        body_layout.addWidget(btn_dots)
        body_layout.addWidget(self.btn_run)

        self.btn_reset_err = QtWidgets.QPushButton("↺")
        self.btn_reset_err.setFixedWidth(28)
        self.btn_reset_err.setToolTip("Reset error - restore this button to normal (does not re-run).")
        self.btn_reset_err.setStyleSheet("background-color: #3e3e42; color: #ffcc66; font-weight: bold;")
        self.btn_reset_err.setVisible(False)
        self.btn_reset_err.clicked.connect(self.reset_run_button)
        body_layout.addWidget(self.btn_reset_err)

        # Stage 35: same top-alignment fix as the Module Bubbles panel - once
        # self.bubble_area can be several rows tall, a plain QHBoxLayout
        # centers every other widget on the full height of that block.
        for i in range(body_layout.count()):
            item = body_layout.itemAt(i)
            target = item.widget() or item.layout()
            if target is not None and target is not self.bubble_area:
                body_layout.setAlignment(target, QtCore.Qt.AlignTop)

        main_layout.addLayout(body_layout)
        self.btn_del.clicked.connect(self._on_delete_clicked)

        # Stage 21: no more manual "Sync" button - listen directly to the
        # real LOD list so a LOD deleted or renamed elsewhere automatically
        # drops out of this panel instead of sitting there stale until a
        # button click. (A rename shows up as a delete of the old name -
        # the renamed LOD itself just needs picking again via + Add LOD,
        # since there's no reliable way to tell "renamed" apart from
        # "removed, unrelated one added" from the list signals alone.)
        if hasattr(self.workspace, "lod_list"):
            self.workspace.lod_list.itemChanged.connect(self._on_lod_manager_changed)
            self.workspace.lod_list.model().rowsRemoved.connect(self._on_lod_manager_changed)

    # -- bubble management -------------------------------------------------
    def add_lod_bubble_picker(self):
        if not hasattr(self.workspace, "lod_list"):
            cmds.warning("No LODs available yet.")
            return
        existing = {b.name for b in self.lod_bubbles}
        available = [self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())
                     if self.workspace.lod_list.item(i).text() not in existing]
        if not available:
            cmds.warning("No more LODs available to add (or none exist yet).")
            return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        actions = {}
        for name in available:
            actions[menu.addAction(name)] = name
        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if action and action in actions:
            self._add_lod_bubble(actions[action])

    def _add_lod_bubble(self, name):
        bubble = LodLoaderBubble(name)
        bubble.closed.connect(self._remove_lod_bubble)
        bubble.jump_req.connect(self.jump_to_lod_by_name)
        self.bubble_layout.addWidget(bubble)
        self.lod_bubbles.append(bubble)
        return bubble

    def _remove_lod_bubble(self, bubble):
        if bubble in self.lod_bubbles:
            self.lod_bubbles.remove(bubble)
        self.bubble_layout.removeWidget(bubble)
        bubble.deleteLater()

    def _on_lod_manager_changed(self, *args):
        try:
            self._prune_stale_bubbles()
        except RuntimeError:
            pass

    def _prune_stale_bubbles(self):
        if not hasattr(self.workspace, "lod_list"):
            return
        real_names = {self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())}
        for bubble in list(self.lod_bubbles):
            if bubble.name not in real_names:
                self._remove_lod_bubble(bubble)

    def sync_from_lod_manager(self):
        """Stage 21: bubbles are now added one at a time via '+ Add LOD',
        not auto-populated from the full LOD list - this just prunes any
        bubble whose LOD no longer exists. Kept as the entry point
        workspace.py already calls right after construction/on load."""
        self._prune_stale_bubbles()

    def checked_lod_names(self):
        return [b.name for b in self.lod_bubbles]

    def set_checked_lod_names(self, names):
        for b in list(self.lod_bubbles):
            self._remove_lod_bubble(b)
        if not names:
            return
        real_names = None
        if hasattr(self.workspace, "lod_list"):
            real_names = {self.workspace.lod_list.item(i).text() for i in range(self.workspace.lod_list.count())}
        for name in names:
            if real_names is None or name in real_names:
                self._add_lod_bubble(name)

    def jump_to_lod_by_name(self, name):
        idx = self.workspace._find_lod_row_by_name(name)
        if idx is None:
            cmds.warning("LOD '{}' not found anymore.".format(name))
            return
        self.workspace.lod_list.setCurrentRow(idx)

    # -- appearance / rename / drag (same pattern as the other panel types) --
    def reset_run_button(self):
        self.btn_run.setText("🚀 RUN")
        self.btn_run.setStyleSheet("background-color: #ffca28; color: #1a1a1a; font-weight: bold;")
        self.last_error_msg = ""
        if hasattr(self, 'btn_reset_err'):
            self.btn_reset_err.setVisible(False)

    def update_style(self):
        accent = getattr(self, 'accent', type_accent("LOD_LOADER"))
        self.setStyleSheet(
            f"LodLoaderPanel {{ background: {self.bg_color}; border: 1px solid #333;"
            f" border-left: 4px solid {accent}; border-radius: 5px; margin-top: 5px; }}"
            f" LodLoaderPanel:hover {{ border: 1px solid #555; border-left: 4px solid {accent}; }}")

    def change_color(self):
        current_color = QtGui.QColor(self.bg_color)
        color = QtWidgets.QColorDialog.getColor(current_color, self.workspace.main_window, "Choose Panel Color")
        if color.isValid():
            self.bg_color = color.name()
            self.update_style()

    def toggle_active(self, state):
        self.is_active = state
        opacity = 1.0 if state else 0.4
        op_effect = QtWidgets.QGraphicsOpacityEffect(self)
        op_effect.setOpacity(opacity)
        self.setGraphicsEffect(op_effect)

    def mouseDoubleClickEvent(self, event):
        if self.title_edit.geometry().contains(event.pos()):
            self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
            self.title_edit.setStyleSheet("background: #1e1e1e; border: 1px solid #ffca28; font-weight: bold; color: white; font-size: 13px; padding: 2px;")
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        super(LodLoaderPanel, self).mouseDoubleClickEvent(event)

    def finish_editing_title(self):
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {getattr(self, 'accent', type_accent('LOD_LOADER'))}; font-size: 13px;")
        self.title_edit.clearFocus()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super(LodLoaderPanel, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton):
            return super(LodLoaderPanel, self).mouseMoveEvent(event)
        if not hasattr(self, 'drag_start_pos'):
            return super(LodLoaderPanel, self).mouseMoveEvent(event)

        if (event.pos() - self.drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return super(LodLoaderPanel, self).mouseMoveEvent(event)

        self.workspace.dragged_panel = self
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText("panel_drag")
        drag.setMimeData(mime_data)

        pixmap = QtGui.QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        if IS_PYSIDE6: drag.exec(QtCore.Qt.MoveAction)
        else: drag.exec_(QtCore.Qt.MoveAction)

        self.workspace.dragged_panel = None
        super(LodLoaderPanel, self).mouseMoveEvent(event)

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
        elif p_type == "LOD_LOADER":
            self.workspace.add_lod_loader_panel(title, index=idx)
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")

        a_undo = menu.addAction("↩ Undo Delete/Cut")
        if not getattr(self.workspace, 'panel_undo_stack', None):
            a_undo.setEnabled(False)
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")

        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Default Script (Maya Global)")] = ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", offset)
            actions_map[m.addAction("Add Import 3D Model (.ma/.mb/.fbx/.obj/.abc)")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Material Panel")] = ("MATERIAL PANEL", "MATERIAL", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            actions_map[m.addAction("Add Tweaker Panel")] = ("TWEAKER SETUP", "TWEAKER", offset)
            actions_map[m.addAction("Add LOD Loader Panel (build entire LODs)")] = ("LOD LOADER", "LOD_LOADER", offset)
            actions_map[m.addAction("Add Note Panel (free-text, not a build step)")] = ("NOTE", "NOTE", offset)
            actions_map[m.addAction("Add Import 3D Model + LOD Organize")] = ("IMPORT 3D + LOD ORGANIZE", "IMPORT_LOD", offset)
            actions_map[m.addAction("Add Delete-by-Name Panel")] = ("DELETE", "DELETE_OBJ", offset)
            actions_map[m.addAction("Add Zero Out Panel")] = ("ZERO OUT", "ZERO_OUT", offset)
            actions_map[m.addAction("Add Parent Panel")] = ("PARENT", "PARENT_OBJ", offset)
            actions_map[m.addAction("Add Instance Panel")] = ("INSTANCE", "INSTANCE_OBJ", offset)

        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        # Stage 22, request #4: the same Copy/Cut/Paste and Build Till Here
        # options every other panel type's "..." menu has - everything that
        # is actually meaningful for this panel type. Left out on purpose:
        # Load Cached Scene / Build FROM Here (this panel doesn't use
        # CacheMixin - caching one step doesn't compose meaningfully when
        # the "step" is itself a full multi-panel LOD build) and Replace
        # All Paths (this panel has no file-path field for that dialog to
        # touch).
        a_copy = menu.addAction("📄 Copy Panel")
        a_cut = menu.addAction("✂ Cut Panel")
        paste_above = menu.addAction("📋 Paste Panel (Above)")
        paste_below = menu.addAction("📋 Paste Panel (Below)")
        if not hasattr(self.workspace.main_window, 'clipboard_panel_data') or not self.workspace.main_window.clipboard_panel_data:
            paste_above.setEnabled(False)
            paste_below.setEnabled(False)
        menu.addSeparator()

        a_build_till = menu.addAction("🚀 Build Till Here")
        a_dup = menu.addAction("📋 Duplicate Panel")
        a_del = menu.addAction("❌ Delete Panel")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        if not action: return

        if action == a_undo: self.workspace.undo_last_panel_delete()
        elif action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
        elif action == a_cut: self.cut_panel()
        elif action == paste_above: self.paste_panel(0)
        elif action == paste_below: self.paste_panel(1)
        elif action == a_build_till: self.workspace.build_till_panel(self)
        elif action == a_dup: self.workspace.duplicate_panel(self)
        elif action == a_del: self._on_delete_clicked()

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active,
                "bg_color": self.bg_color, "lod_names": self.checked_lod_names()}
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

    def cut_panel(self):
        self.copy_panel()
        self._on_delete_clicked()

    def paste_panel(self, offset):
        data = getattr(self.workspace.main_window, 'clipboard_panel_data', None)
        if not data: return
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset

        p_type = data.get("type")
        is_act = data.get("active", True)
        title = data.get("title", "Copied Panel")
        bg_col = data.get("bg_color", "#252526")

        if p_type == "MODULE":
            pan = self.workspace.add_module_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            for m in data.get("modules", []):
                pan.add_module_bubble(pre_path=m.get("path"), is_active=m.get("active", True))
            if not is_act: pan.checkbox.setChecked(False)
        elif p_type == "LOD_LOADER":
            pan = self.workspace.add_lod_loader_panel(title, index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            pan.set_checked_lod_names(data.get("lod_names", []))
            if not is_act: pan.checkbox.setChecked(False)
        else:
            pan = self.workspace.add_panel(title, p_type, data.get("path", ""), index=idx)
            pan.bg_color = bg_col
            pan.update_style()
            if not is_act: pan.checkbox.setChecked(False)
            if p_type == "JSON":
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if data.get("reskin_control"): pan.reskin_ctl_field.setText(data.get("reskin_control"))
                if data.get("reskin_scale"): pan.reskin_scale_field.setText(data.get("reskin_scale"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "MATERIAL" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type in ("SCRIPT", "GLOBAL_SCRIPT") and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
            if p_type == "TWEAKER":
                pan.load_tweaker_groups_data(data.get("groups"), legacy_item=data)
                if data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
                if data.get("joints"): pan.joints_field.setText(data.get("joints"))
                if "naming_popup" in data and hasattr(pan, 'chk_naming_popup'):
                    pan.chk_naming_popup.setChecked(bool(data.get("naming_popup")))
            if p_type == "NOTE" and hasattr(pan, 'note_edit'):
                if data.get("note_text"): pan.note_edit.setPlainText(data.get("note_text"))
                pan.note_text_color = data.get("note_text_color", pan.note_text_color)
                pan.note_bg_color = data.get("note_bg_color", pan.note_bg_color)
                pan.note_font_size = data.get("note_font_size", pan.note_font_size)
                pan.note_height = data.get("note_height", pan.note_height)
                pan.note_edit.setFixedHeight(pan.note_height)
                pan._apply_note_style()
            if p_type == "IMPORT_LOD" and hasattr(pan, 'asset_name_field'):
                if data.get("asset_name"): pan.asset_name_field.setText(data.get("asset_name"))
            if p_type in ("DELETE_OBJ", "ZERO_OUT") and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
            if p_type == "PARENT_OBJ" and hasattr(pan, 'child_field'):
                if data.get("child"): pan.child_field.setText(data.get("child"))
                if data.get("parent"): pan.parent_field.setText(data.get("parent"))
            if p_type == "INSTANCE_OBJ" and hasattr(pan, 'target_field'):
                if data.get("target"): pan.target_field.setText(data.get("target"))
                if data.get("func_call") and hasattr(pan, 'func_field'): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")

    def _on_delete_clicked(self):
        """Stop listening to the real LOD list before this panel is torn
        down, so a later add/remove/rename elsewhere never calls back into
        a deleted Qt widget."""
        if hasattr(self.workspace, "lod_list"):
            try:
                self.workspace.lod_list.itemChanged.disconnect(self._on_lod_manager_changed)
            except (RuntimeError, TypeError):
                pass
            try:
                self.workspace.lod_list.model().rowsRemoved.disconnect(self._on_lod_manager_changed)
            except (RuntimeError, TypeError):
                pass
        self.workspace.delete_panel(self)

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            self.execute(None)

    def show_error_popup(self):
        msg = f"Panel: {self.title_edit.text()}"
        dialog = ErrorDialog("Execution Error", msg, self.last_error_msg,
                             self.workspace.main_window, allow_retry=True)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()
        if getattr(dialog, "retry", False):
            self.execute(None)

    def execute(self, progress_ui=None):
        if not self.is_active: return True
        names = self.checked_lod_names()
        if not names:
            cmds.warning("No LODs added to this LOD Loader panel yet - use + Add LOD.")
            return True

        self.btn_run.setText("RUNNING...")
        QtWidgets.QApplication.processEvents()

        try:
            all_ok, msg = self.workspace.build_lod_sequence(names)
        except Exception:
            all_ok = False
            msg = traceback.format_exc()

        if all_ok:
            self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            self.btn_run.setText("🚀 RUN")
            self.last_error_msg = ""
            if hasattr(self, 'btn_reset_err'):
                self.btn_reset_err.setVisible(False)
        else:
            self.btn_run.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
            self.btn_run.setText("SHOW ERROR")
            self.last_error_msg = msg
            if hasattr(self, 'btn_reset_err'):
                self.btn_reset_err.setVisible(True)
        return all_ok


# ==========================================================================
# PBCameraViewWidget (Playblast tab, request #1): a LIVE embedded Maya
# viewport, adapted from Studio Library's own mutils/gui/modelpanelwidget.py
# (ModelPanelWidget) - see that file for the reference implementation this
# is based on. Embeds a real native Maya modelPanel inside this Qt widget by
# parenting into this widget's own layout via cmds.setParent(...) right
# before creating the modelPanel, then strips it down to a clean 3D view
# (no menu bar/toolbar/HUD) and locks it onto whichever camera the
# Playblast tab's Camera field names.
#
# IMPORTANT / NOT VERIFIABLE IN THIS SANDBOX: embedding a native Maya
# modelPanel into a Qt layout via cmds.setParent + cmds.modelPanel(...) is
# a Maya-UI-bridge operation with no Python-level simulation possible
# outside real Maya + Qt - unlike the rest of KRT's logic, this class's
# core embedding/camera-lock/live-navigation behavior could NOT be
# exercised against stubs and has only been checked for syntax
# (py_compile) and by close reading against Studio Library's own proven
# implementation. Please verify by opening the Playblast tab in real Maya.
# ==========================================================================
class PBCameraViewWidget(QtWidgets.QWidget):
    """Live embedded Maya viewport for the Playblast tab's preview area.
    Navigate with the normal Maya viewport controls (Alt+LMB tumble,
    Alt+MMB pan, Alt+RMB/scroll zoom) once this widget has focus/the mouse
    is over it - Maya's own modelPanel handles that natively, nothing
    special is done here for it. A small 🔒/🔓 lock button sits in the
    top-left corner; when locked, the camera's translate/rotate channels
    are Maya-attribute-locked so tumble/pan/dolly can't move it by
    accident. While unlocked, a QTimer polls the camera's live
    position/rotation and pushes them into the Playblast tab's Position/
    Rotation fields in real time (skipping any field the user is actively
    typing into)."""

    POLL_INTERVAL_MS = 200

    def __init__(self, parent=None, on_transform_changed=None):
        super(PBCameraViewWidget, self).__init__(parent)
        self._camera = None
        self._locked = False
        self._on_transform_changed = on_transform_changed
        self._model_panel = None
        self._last_pushed = None

        uniqueName = "KRT_pbCamView" + str(id(self))
        self._panel_name = uniqueName

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        self._viewport_container = QtWidgets.QWidget(self)
        vlayout = QtWidgets.QVBoxLayout(self._viewport_container)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setObjectName(uniqueName + "Layout")
        self._viewport_container.setLayout(vlayout)
        outer.addWidget(self._viewport_container)

        self._built = False
        try:
            self._build_model_panel(vlayout)
        except Exception as e:
            self._built = False
            fallback = QtWidgets.QLabel(
                "Live camera view unavailable ({}).\n"
                "Generate or set a camera, then re-open this tab.".format(e))
            fallback.setAlignment(QtCore.Qt.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setStyleSheet("color:#888; padding:30px;")
            vlayout.addWidget(fallback)

        # ── Lock toggle button, small, top-left corner of the black
        # screen (per the user's request) ───────────────────────────────
        self.btn_lock = QtWidgets.QPushButton("🔓", self)
        self.btn_lock.setFixedSize(22, 22)
        self.btn_lock.setToolTip("Lock/unlock the camera (prevents accidental tumble/pan/dolly).")
        self.btn_lock.setStyleSheet(
            "QPushButton { background-color: rgba(30,30,30,180); color:white; "
            "border: 1px solid #555; border-radius: 3px; font-size: 11px; } "
            "QPushButton:hover { background-color: rgba(60,60,60,220); }")
        self.btn_lock.clicked.connect(self.toggle_lock)
        self.btn_lock.move(6, 6)
        self.btn_lock.raise_()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_camera_transform)
        self._timer.start()

    # -- construction -----------------------------------------------------
    def _build_model_panel(self, vlayout):
        cmds.setParent(vlayout.objectName())
        self._model_panel = cmds.modelPanel(self._panel_name, label="KRT Playblast Camera View")
        self._configure_model_panel()
        self._disable_cached_playback()
        self._built = True

    def _disable_cached_playback(self):
        """A second live viewport (this one) makes Maya's Cached Playback
        system evaluate/cache the scene for one more panel at once, which
        is what was producing the 'Cached Playback: Out of memory... "
        caching has stopped' warnings once this tab's live view opened.
        Cached Playback only speeds up scrubbing/looping in the Time
        Slider - it isn't needed for playblasting or for this tumble/pan
        preview - so it's turned off for the session the moment this
        widget is created, freeing that memory back up rather than
        letting Maya keep fighting for it. Uses Maya's own documented
        toggle (maya.plugin.evaluator.cache_preferences); if that module
        isn't available (older Maya), this is a harmless no-op."""
        try:
            import maya.plugin.evaluator.cache_preferences as cache_preferences
            cache_preferences.CachePreferenceEnabled().set_value(False)
        except Exception:
            try:
                cmds.evaluator(name="cache", enable=False)
            except Exception:
                pass

    def _configure_model_panel(self):
        panel = self._model_panel
        if not panel:
            return
        for flag, value in (
            ("allObjects", False), ("grid", False), ("dynamics", False),
            ("activeOnly", False), ("manipulators", False),
            ("headsUpDisplay", False), ("selectionHiliteDisplay", False),
            ("polymeshes", True), ("nurbsSurfaces", True),
            ("subdivSurfaces", True), ("displayTextures", True),
        ):
            try:
                cmds.modelEditor(panel, edit=True, **{flag: value})
            except Exception:
                pass
        try:
            cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded")
        except Exception:
            pass
        try:
            cmds.modelPanel(panel, edit=True, menuBarVisible=False)
        except Exception:
            pass
        self._hide_bar_layout()

    def _hide_bar_layout(self):
        """Hides the modelPanel's own toolbar (the row of icons above the
        viewport, including the camera-name dropdown) by wrapping its
        native Maya UI control as a Qt WIDGET (not a bare QObject - a
        QObject has no .hide(), so this silently no-op'd before, leaving
        the toolbar visible) and calling .hide() on it - the exact
        technique Studio Library's own ModelPanelWidget.hideBarLayout()
        uses (MQtUtil.findControl + wrapInstance(..., QWidget)). This is
        also the likely fix for the 'updateModelPanelBar ... Syntax
        error' spam some users saw on camera-change/lock - Maya tries to
        refresh that toolbar's camera-name dropdown on those events, and
        with the toolbar actually hidden (this bug fixed) there should be
        nothing left for it to refresh."""
        try:
            import maya.OpenMayaUI as omui
            from .compat import wrapInstance
            bar_name = cmds.modelPanel(self._model_panel, query=True, barLayout=True)
            ptr = omui.MQtUtil.findControl(bar_name)
            if ptr:
                bar_widget = wrapInstance(int(ptr), QtWidgets.QWidget)
                bar_widget.hide()
        except Exception:
            pass

    @staticmethod
    def _quiet_script_editor(fn, *args, **kwargs):
        """Belt-and-suspenders for the 'updateModelPanelBar ... Syntax
        error' spam some Maya installs print on a camera-name refresh for
        this deeply-Qt-nested embedded panel (QStackedWidget/QSplitter/
        tab layers between this modelPanel and KRT's main window, unlike
        Studio Library's own much shallower embedding) - temporarily
        silences the Script Editor's error/warning output only around the
        one call that triggers it, so a harmless internal refresh
        hiccup doesn't spam the user's console. Restores the previous
        suppress state afterward either way, and never swallows a real
        Python exception raised by `fn` itself."""
        prev_err = prev_warn = None
        try:
            prev_err = cmds.scriptEditorInfo(query=True, suppressErrors=True)
            prev_warn = cmds.scriptEditorInfo(query=True, suppressWarnings=True)
            cmds.scriptEditorInfo(suppressErrors=True, suppressWarnings=True)
        except Exception:
            prev_err = prev_warn = None
        try:
            return fn(*args, **kwargs)
        finally:
            if prev_err is not None or prev_warn is not None:
                try:
                    cmds.scriptEditorInfo(
                        suppressErrors=bool(prev_err), suppressWarnings=bool(prev_warn))
                except Exception:
                    pass

    # -- camera control -----------------------------------------------------
    def set_camera(self, camera_name):
        """Points this embedded viewport at `camera_name` (a transform or
        shape). Safe to call repeatedly (e.g. right after Generate
        Camera, or whenever the Camera field changes)."""
        self._camera = camera_name or None
        if not self._built or not self._camera:
            return
        if not cmds.objExists(self._camera):
            return
        try:
            self._quiet_script_editor(
                cmds.modelPanel, self._model_panel, edit=True, camera=self._camera)
        except Exception:
            pass
        self._apply_lock_state()

    def current_camera(self):
        return self._camera

    def _camera_transform(self):
        if not self._camera or not cmds.objExists(self._camera):
            return None
        if cmds.objectType(self._camera) == "camera":
            parents = cmds.listRelatives(self._camera, parent=True, fullPath=True) or []
            return parents[0] if parents else None
        return self._camera

    def _camera_shape(self):
        tfm = self._camera_transform()
        if not tfm:
            return None
        if cmds.objectType(tfm) == "camera":
            return tfm
        shapes = cmds.listRelatives(tfm, shapes=True, type="camera", fullPath=True) or []
        return shapes[0] if shapes else None

    # -- lock ---------------------------------------------------------------
    def is_locked(self):
        return self._locked

    def toggle_lock(self):
        self.set_locked(not self._locked)

    def set_locked(self, locked):
        self._locked = bool(locked)
        self.btn_lock.setText("🔒" if self._locked else "🔓")
        self.btn_lock.setToolTip(
            "Camera is LOCKED - click to unlock." if self._locked
            else "Camera is unlocked - click to lock (prevents accidental tumble/pan/dolly).")
        self._apply_lock_state()

    def _apply_lock_state(self):
        """Locking just the camera transform's translate/rotate ATTRIBUTES
        (what this used to do) does NOT stop Maya's own tumble/track/dolly
        tools - the viewport navigation manipulator writes the camera's
        transformation matrix as a whole, which isn't blocked by locking
        individual channels the same way a Channel Box edit would be. The
        actual fix is Maya's own per-camera 'lockTransform' flag on the
        camera SHAPE (cmds.camera(..., lockTransform=True)) - that's the
        real 'stop the viewport from moving this camera at all' switch
        or-drag Maya itself uses. Both are applied here: lockTransform
        does the real work, and the plain attribute lock is kept as a
        secondary guard against an accidental Channel Box/Attribute
        Editor edit while lockTransform isn't available (older Maya)."""
        tfm = self._camera_transform()
        shape = self._camera_shape()
        if shape:
            try:
                self._quiet_script_editor(
                    cmds.camera, shape, edit=True, lockTransform=self._locked)
            except Exception:
                pass
        if not tfm:
            return
        for attr in ("translateX", "translateY", "translateZ",
                     "rotateX", "rotateY", "rotateZ"):
            plug = "{}.{}".format(tfm, attr)
            if cmds.objExists(plug):
                try:
                    cmds.setAttr(plug, lock=self._locked)
                except Exception:
                    pass

    # -- real-time position/rotation sync -----------------------------------
    def _poll_camera_transform(self):
        if self._locked:
            return
        tfm = self._camera_transform()
        if not tfm or not cmds.objExists(tfm):
            return
        try:
            pos = cmds.xform(tfm, query=True, translation=True, worldSpace=True)
            rot = cmds.xform(tfm, query=True, rotation=True, worldSpace=True)
        except Exception:
            return
        values = tuple(round(v, 4) for v in (pos + rot))
        if values == self._last_pushed:
            return
        self._last_pushed = values
        if self._on_transform_changed:
            try:
                self._on_transform_changed(pos, rot)
            except Exception:
                pass

    # -- cleanup --------------------------------------------------------------
    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def closeEvent(self, event):
        self.stop()
        super(PBCameraViewWidget, self).closeEvent(event)

    def resizeEvent(self, event):
        super(PBCameraViewWidget, self).resizeEvent(event)
        # Keep the lock button pinned to the top-left corner as the widget
        # resizes (it's a child of self, not of the layout, so it doesn't
        # reflow automatically).
        self.btn_lock.move(6, 6)


# ==========================================================================
# PBWipeCompareWidget (Playblast tab, request #6): two playblasts played
# back-to-back with a draggable vertical divider - everything left of the
# line shows clip A, everything right shows clip B, so scrubbing/dragging
# the line back and forth over the same moment shows exactly what changed
# between two versions of the same shot.
#
# PySide6/Qt6-only: this needs raw decoded video FRAMES (QVideoSink's
# videoFrameChanged) to paint two clips clipped against each other in one
# widget - a plain QVideoWidget is a native window that always draws on
# top of everything else regardless of Qt stacking order, so it can't be
# masked/overlaid this way. Qt5/PySide2 has no public equivalent of
# QVideoSink, so this widget shows a plain explanation message there
# instead of a video (see is_available()) - pb_toggle_compare_mode() in
# workspace.py falls back to the existing side-by-side compare page in
# that case.
# ==========================================================================
class PBWipeCompareWidget(QtWidgets.QWidget):
    HANDLE_GRAB_PX = 18

    def __init__(self, parent=None):
        super(PBWipeCompareWidget, self).__init__(parent)
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#000;")
        self._slider_frac = 0.5
        self._pix_a = None
        self._pix_b = None
        self._dragging = False
        self._player_a = None
        self._player_b = None
        self._sink_a = None
        self._sink_b = None
        self._built = False
        self._label_a = "A"
        self._label_b = "B"
        try:
            self._build_players()
            self._built = True
        except Exception:
            self._built = False

    def is_available(self):
        return self._built

    def _build_players(self):
        from .compat import QMediaPlayer, QVideoSink, HAS_VIDEO_SINK
        if not HAS_VIDEO_SINK or QMediaPlayer is None:
            raise RuntimeError("QVideoSink not available (needs PySide6/Qt6 multimedia)")

        self._player_a = QMediaPlayer(self)
        self._sink_a = QVideoSink(self)
        self._player_a.setVideoSink(self._sink_a)
        self._sink_a.videoFrameChanged.connect(self._on_frame_a)

        self._player_b = QMediaPlayer(self)
        self._sink_b = QVideoSink(self)
        self._player_b.setVideoSink(self._sink_b)
        self._sink_b.videoFrameChanged.connect(self._on_frame_b)

    def _on_frame_a(self, frame):
        try:
            img = frame.toImage()
        except Exception:
            return
        if img is not None and not img.isNull():
            self._pix_a = QtGui.QPixmap.fromImage(img)
            self.update()

    def _on_frame_b(self, frame):
        try:
            img = frame.toImage()
        except Exception:
            return
        if img is not None and not img.isNull():
            self._pix_b = QtGui.QPixmap.fromImage(img)
            self.update()

    def load(self, path_a, path_b, label_a="A", label_b="B"):
        self._label_a = label_a or "A"
        self._label_b = label_b or "B"
        self._pix_a = None
        self._pix_b = None
        if not self._built:
            self.update()
            return
        self._player_a.setSource(QtCore.QUrl.fromLocalFile(path_a))
        self._player_b.setSource(QtCore.QUrl.fromLocalFile(path_b))
        self.update()

    def play(self):
        if self._built:
            self._player_a.play()
            self._player_b.play()

    def pause(self):
        if self._built:
            self._player_a.pause()
            self._player_b.pause()

    def stop(self):
        if self._built:
            self._player_a.stop()
            self._player_b.stop()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#000"))

        if not self._built:
            painter.setPen(QtGui.QColor("#ffcc66"))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "Wipe compare needs PySide6/Qt6 multimedia (QVideoSink),\n"
                "which isn't available in this Maya's Qt install.\n"
                "Use Side-by-Side compare mode instead.")
            painter.end()
            return

        w, h = self.width(), self.height()
        divider_x = int(w * self._slider_frac)

        if self._pix_a is not None:
            scaled_a = self._pix_a.scaled(
                w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            ax = (w - scaled_a.width()) // 2
            ay = (h - scaled_a.height()) // 2
            painter.setClipRect(0, 0, max(0, divider_x), h)
            painter.drawPixmap(ax, ay, scaled_a)
            painter.setClipping(False)

        if self._pix_b is not None:
            scaled_b = self._pix_b.scaled(
                w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            bx = (w - scaled_b.width()) // 2
            by = (h - scaled_b.height()) // 2
            painter.setClipRect(divider_x, 0, max(0, w - divider_x), h)
            painter.drawPixmap(bx, by, scaled_b)
            painter.setClipping(False)

        # Divider line + drag handle
        painter.setPen(QtGui.QPen(QtGui.QColor("#2bb5a8"), 2))
        painter.drawLine(divider_x, 0, divider_x, h)
        painter.setBrush(QtGui.QColor("#2bb5a8"))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPoint(divider_x, h // 2), 8, 8)

        # A/B labels, top-left / top-right of each side
        painter.setPen(QtGui.QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(6, 4, 200, 20), QtCore.Qt.AlignLeft, self._label_a)
        painter.drawText(QtCore.QRect(w - 206, 4, 200, 20), QtCore.Qt.AlignRight, self._label_b)
        painter.end()

    def _divider_px(self):
        return int(self.width() * self._slider_frac)

    def mousePressEvent(self, event):
        if abs(event.pos().x() - self._divider_px()) <= self.HANDLE_GRAB_PX:
            self._dragging = True
        else:
            # Click-anywhere-to-move, same convenience as most wipe-compare
            # UIs (Delta/Before-After sliders) - not just drag-from-the-line.
            self._set_slider_from_x(event.pos().x())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._set_slider_from_x(event.pos().x())

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def _set_slider_from_x(self, x):
        self._slider_frac = min(1.0, max(0.0, x / float(max(1, self.width()))))
        self.update()
