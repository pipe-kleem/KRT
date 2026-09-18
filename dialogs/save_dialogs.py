"""Auto-split from dialogs.py."""
from ._shared import *


# ══════════════════════════════════════════════════════════════════════
# AdvancedSaveDialog
# ══════════════════════════════════════════════════════════════════════
class AdvancedSaveDialog(QtWidgets.QDialog):
    def __init__(self, workspace):
        super(AdvancedSaveDialog, self).__init__(workspace.main_window)
        self.workspace = workspace
        self.setWindowTitle("Save Session Configuration")
        self.setMinimumWidth(550)
        self.setStyleSheet("""
            QDialog { background-color: #252526; color: white; }
            QLabel { color: #cccccc; font-weight: bold; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit { background-color: #1e1e1e; border: 1px solid #555; color: white; padding: 5px; }
            QPushButton { background-color: #3e3e42; color: white; padding: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #555; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        dir_layout = QtWidgets.QHBoxLayout()
        dir_layout.addWidget(QtWidgets.QLabel("Folder Path:"))
        self.dir_edit = QtWidgets.QLineEdit()

        current_path = self.workspace.session_path
        if current_path and os.path.exists(os.path.dirname(current_path)):
            self.dir_edit.setText(os.path.dirname(current_path).replace("\\", "/"))
        else:
            self.dir_edit.setText(
                os.path.join(cmds.internalVar(userAppDir=True), "KRT", "Sessions").replace("\\", "/")
            )

        btn_browse = QtWidgets.QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(btn_browse)
        layout.addLayout(dir_layout)

        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("File Name:"))
        self.name_edit = QtWidgets.QLineEdit("New_Rig")

        if current_path:
            base = os.path.basename(current_path).replace(".json", "")
            base = re.sub(r'_v\d+$', '', base)
            self.name_edit.setText(base)

        name_layout.addWidget(self.name_edit)
        name_layout.addWidget(QtWidgets.QLabel("Variant:"))
        self.variant_combo = QtWidgets.QComboBox()
        self.variant_combo.setEditable(True)
        self.variant_combo.addItems(["A", "B", "C", "Default", "Test", "Final"])
        name_layout.addWidget(self.variant_combo)
        layout.addLayout(name_layout)

        ver_layout = QtWidgets.QHBoxLayout()
        ver_layout.addWidget(QtWidgets.QLabel("Version:"))
        self.version_spin = QtWidgets.QSpinBox()
        self.version_spin.setMinimum(1)
        self.version_spin.setMaximum(999)
        ver_layout.addWidget(self.version_spin)

        self.info_lbl = QtWidgets.QLabel("Existing versions: None")
        self.info_lbl.setStyleSheet("color: #2bb5a8; font-weight: normal;")
        ver_layout.addWidget(self.info_lbl)
        ver_layout.addStretch()
        layout.addLayout(ver_layout)

        layout.addWidget(QtWidgets.QLabel("Session Comments / Notes:"))
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setFixedHeight(80)
        layout.addWidget(self.comment_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QtWidgets.QPushButton("💾 Save Session")
        btn_save.setStyleSheet("background-color: #2bb5a8; color: white;")
        btn_save.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        self.dir_edit.textChanged.connect(self.update_version)
        self.name_edit.textChanged.connect(self.update_version)
        self.variant_combo.currentTextChanged.connect(self.update_version)
        self.update_version()

    def browse_dir(self):
        res = cmds.fileDialog2(fm=3, caption="Select Save Directory")
        if res:
            self.dir_edit.setText(res[0])

    def update_version(self):
        d = self.dir_edit.text()
        n = self.name_edit.text().strip()
        v = self.variant_combo.currentText().strip()

        if not os.path.exists(d) or not n:
            self.info_lbl.setText("Existing versions: N/A")
            self.version_spin.setValue(1)
            return

        prefix = f"{n}_{v}_v" if v else f"{n}_v"
        highest = 0
        existing = []
        for f in os.listdir(d):
            if f.startswith(prefix) and f.endswith(".json"):
                num_str = f[len(prefix):-5]
                if num_str.isdigit():
                    num = int(num_str)
                    existing.append(num)
                    if num > highest:
                        highest = num

        if existing:
            existing.sort()
            self.info_lbl.setText(f"Existing versions: {', '.join(map(str, existing))}")
        else:
            self.info_lbl.setText("Existing versions: None")

        self.version_spin.setValue(highest + 1)

    def accept(self):
        d = self.dir_edit.text()
        n = self.name_edit.text().strip()
        v = self.variant_combo.currentText().strip()
        ver = self.version_spin.value()

        if not os.path.exists(d):
            try:
                os.makedirs(d)
            except Exception as e:
                cmds.warning(f"Could not create directory: {e}")
                return

        filename = f"{n}_{v}_v{ver:03d}.json" if v else f"{n}_v{ver:03d}.json"
        filepath = os.path.join(d, filename).replace("\\", "/")

        data = self.workspace.get_current_pipeline_data()
        data["session_comment"] = self.comment_edit.toPlainText()

        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
            cmds.warning(f"Session saved successfully to: {filepath}")
            # Stage 35, Rule 2: this is also a KRT pipeline JSON save (just
            # via this dialog instead of the Save/Save All buttons) - keep
            # the standalone graph/guide JSON in sync with it too.
            if hasattr(self.workspace, "graph_widget") and hasattr(self.workspace.graph_widget, "save_all_guides"):
                self.workspace.graph_widget.save_all_guides(overwrite=True)
            self.workspace.set_session_path(filepath)
            self.workspace.session_manager.add_recent(filepath)
            self.workspace.main_window.refresh_all_session_lists()
            super(AdvancedSaveDialog, self).accept()
        except Exception as e:
            cmds.error(f"Failed to save session: {e}")


# ══════════════════════════════════════════════════════════════════════
# SaveCommentDialog
# ══════════════════════════════════════════════════════════════════════
class SaveCommentDialog(QtWidgets.QDialog):
    """Replaces QInputDialog.getMultiLineText for the Save Maya File /
    Save All / Save JSON File comment prompt. The built-in Qt dialog had
    no room for an Overwrite option and its OK button always said "OK" -
    this adds both: a checkbox to overwrite the existing published file
    in place instead of bumping to a new _vNNN version, and a button
    that actually says "Save"."""

    def __init__(self, parent, dialog_title, default_text=""):
        super(SaveCommentDialog, self).__init__(parent)
        self.setWindowTitle(dialog_title)
        self.setMinimumSize(380, 280)
        self.setStyleSheet("""
            QDialog { background-color: #252526; color: white; }
            QLabel { color: #cccccc; font-weight: bold; }
            QTextEdit { background-color: #1e1e1e; border: 1px solid #555; color: white; padding: 5px; }
            QCheckBox { color: #cccccc; font-weight: normal; }
            QPushButton { background-color: #3e3e42; color: white; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #555; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("Comment for this save (optional):"))
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlainText(default_text)
        layout.addWidget(self.comment_edit)

        self.chk_overwrite = QtWidgets.QCheckBox(
            "Overwrite existing file (instead of saving a new version)")
        self.chk_overwrite.setToolTip(
            "On: saves over the current latest _vNNN file.\n"
            "Off (default): saves a new, next-numbered _vNNN version, "
            "same as before.")
        layout.addWidget(self.chk_overwrite)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QtWidgets.QPushButton("💾 Save")
        btn_save.setStyleSheet("background-color: #2bb5a8; color: white;")
        btn_save.clicked.connect(self.accept)
        btn_save.setDefault(True)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        self.comment_edit.setFocus()
        self.comment_edit.selectAll()

    def result_values(self):
        """(comment_text, overwrite) - call after exec()/exec_() returns
        Accepted."""
        return self.comment_edit.toPlainText(), self.chk_overwrite.isChecked()


# ══════════════════════════════════════════════════════════════════════
# BuildProgressDialog
# ══════════════════════════════════════════════════════════════════════
class BuildProgressDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, total_steps=100):
        super(BuildProgressDialog, self).__init__(parent)
        self.setWindowTitle("Procedural Build Progress")
        self.setFixedSize(350, 140)
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        self.is_cancelled = False
        self.start_time = time.time()

        self.setStyleSheet("""
            QDialog { background-color: #252526; border: 2px solid #2bb5a8; border-radius: 5px; }
            QLabel { color: #cccccc; font-weight: bold; font-family: 'Consolas'; }
            QProgressBar { border: 1px solid #555; border-radius: 3px; background: #1e1e1e; text-align: center; color: white; font-weight: bold; }
            QProgressBar::chunk { background-color: #2bb5a8; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        self.lbl_status = QtWidgets.QLabel("Initializing Build...")
        layout.addWidget(self.lbl_status)

        self.lbl_time = QtWidgets.QLabel("Time Elapsed: 00:00")
        layout.addWidget(self.lbl_time)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, total_steps)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.btn_stop = QtWidgets.QPushButton("STOP BUILD")
        self.btn_stop.setStyleSheet(
            "background-color: #f44336; color: white; font-weight: bold; padding: 5px; border-radius: 3px;"
        )
        self.btn_stop.clicked.connect(self.cancel_build)
        layout.addWidget(self.btn_stop)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(100)

    def update_time(self):
        if not self.is_cancelled:
            elapsed = time.time() - self.start_time
            mins, secs = divmod(int(elapsed), 60)
            self.lbl_time.setText(f"Time Elapsed: {mins:02d}:{secs:02d}")

    def cancel_build(self):
        self.is_cancelled = True
        self.timer.stop()
        self.lbl_status.setText("Halting Process... Please wait.")
        self.lbl_status.setStyleSheet("color: #f44336; font-weight: bold;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("CANCELLING...")


# ══════════════════════════════════════════════════════════════════════
# SimpleCodeEditorDialog (Stage 17)
#
# Fallback editor for opening a script from the Rigging Workspace's script
# library (or the "Edit code in VS Code" action on a SCRIPT/GLOBAL_SCRIPT
# panel) when VS Code isn't found on this machine. Plain, no syntax
# highlighting - good enough to view/tweak a script without leaving Maya.
# ══════════════════════════════════════════════════════════════════════
class SimpleCodeEditorDialog(QtWidgets.QDialog):
    def __init__(self, file_path, parent=None):
        super(SimpleCodeEditorDialog, self).__init__(parent)
        self.file_path = file_path
        self.setWindowTitle("KRT - Script Editor - {}".format(os.path.basename(file_path)))
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.resize(900, 650)

        layout = QtWidgets.QVBoxLayout(self)
        lbl_path = QtWidgets.QLabel(file_path)
        lbl_path.setStyleSheet("color: #888; font-family: 'Consolas'; font-size: 11px;")
        lbl_path.setWordWrap(True)
        layout.addWidget(lbl_path)

        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border: 1px solid #333;"
            " font-family:'Consolas'; font-size:12px;")
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        try:
            with open(file_path, "r") as f:
                self.editor.setPlainText(f.read())
        except Exception as e:
            self.editor.setPlainText("# Could not read file: {}".format(e))
        layout.addWidget(self.editor)

        btn_row = QtWidgets.QHBoxLayout()
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: #888;")
        btn_save = QtWidgets.QPushButton("💾 Save (Ctrl+S)")
        btn_save.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold; padding: 6px 12px;")
        btn_save.clicked.connect(self.save_file)
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.setStyleSheet("padding: 6px 12px;")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.lbl_status)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        save_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_file)

    def save_file(self):
        try:
            with open(self.file_path, "w") as f:
                f.write(self.editor.toPlainText())
            self.lbl_status.setText("Saved.")
        except Exception as e:
            self.lbl_status.setText("Save failed: {}".format(e))
