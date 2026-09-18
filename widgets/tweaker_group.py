"""Auto-split from widgets.py."""
from ._shared import *


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
