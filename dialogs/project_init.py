"""Initialize Project dialog (Stage 42).

Asks for the parent folder + rig name, shows exactly which folders will be
created, and lets the user opt out of the two side-effects (copying the
utils.py template, replacing the current LOD's panels).
"""
from ._shared import *
from ..utils.paths import DEFAULT_RIGS_ROOT


class ProjectInitDialog(QtWidgets.QDialog):

    def __init__(self, folders, parent=None, default_parent_dir="", default_name=""):
        super(ProjectInitDialog, self).__init__(parent)
        self.setWindowTitle("Initialize Rig Project")
        self.setMinimumWidth(560)
        self.folders = list(folders)

        lay = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QGridLayout()
        form.addWidget(QtWidgets.QLabel("<b>Rigs folder:</b>"), 0, 0)
        self.edit_parent = QtWidgets.QLineEdit(default_parent_dir or DEFAULT_RIGS_ROOT)
        self.edit_parent.setToolTip("Where all rigs live. The rig folder is created inside this.")
        form.addWidget(self.edit_parent, 0, 1)
        btn_browse = QtWidgets.QPushButton("📁")
        btn_browse.setFixedWidth(34)
        btn_browse.clicked.connect(self._browse)
        form.addWidget(btn_browse, 0, 2)

        form.addWidget(QtWidgets.QLabel("<b>Rig name:</b>"), 1, 0)
        self.edit_name = QtWidgets.QLineEdit(default_name)
        self.edit_name.setPlaceholderText("e.g. parshuram_a")
        self.edit_name.textChanged.connect(self._refresh_preview)
        form.addWidget(self.edit_name, 1, 1, 1, 2)
        lay.addLayout(form)

        self.lbl_preview = QtWidgets.QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet(
            "background:#1e1e1e; border:1px solid #333; color:#9ecfca; padding:8px; border-radius:3px;")
        lay.addWidget(self.lbl_preview)

        self.chk_utils = QtWidgets.QCheckBox("Copy the utils.py template into scripts/ (skipped if one is already there)")
        self.chk_utils.setChecked(True)
        lay.addWidget(self.chk_utils)

        self.chk_panels = QtWidgets.QCheckBox("Create the default panel stack (REPLACES the current LOD's panels)")
        self.chk_panels.setChecked(True)
        lay.addWidget(self.chk_panels)

        self.chk_open_folder = QtWidgets.QCheckBox("Open the rig folder in Explorer when done")
        lay.addWidget(self.chk_open_folder)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.button(QtWidgets.QDialogButtonBox.Ok).setText("Create Project")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.edit_name.setFocus()
        self._refresh_preview()

    def _browse(self):
        start = self.edit_parent.text().strip()
        kwargs = {"fm": 3, "caption": "Select the folder that holds all rigs"}
        if start and os.path.isdir(start):
            kwargs["dir"] = start
        res = cmds.fileDialog2(**kwargs)
        if res:
            self.edit_parent.setText(res[0].replace("\\", "/"))
            self._refresh_preview()

    def _refresh_preview(self):
        root = self.rig_root()
        if not root:
            self.lbl_preview.setText("Enter a rig name to see what will be created.")
            return
        exists = " (already exists - nothing is overwritten)" if os.path.isdir(root) else ""
        self.lbl_preview.setText(
            "<b>{}</b>{}<br>&nbsp;&nbsp;{}".format(root, exists, "&nbsp;&nbsp;".join(f + "/" for f in self.folders)))

    def rig_name(self):
        return self.edit_name.text().strip()

    def rig_root(self):
        parent = self.edit_parent.text().strip().replace("\\", "/").rstrip("/")
        name = self.rig_name()
        return "{}/{}".format(parent, name) if parent and name else ""
