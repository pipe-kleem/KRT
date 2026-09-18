import maya.cmds as cmds
import os
import re
import uuid
import time
import json
import shutil
import traceback
import ayon_api
from ayon_api.entity_hub import EntityHub
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6

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
# PathReplaceDialog — bulk find-and-replace paths across all panels
# ══════════════════════════════════════════════════════════════════════
class PathReplaceDialog(QtWidgets.QDialog):
    """
    Replaces a common path prefix across every panel field in every LOD.

    Use case: the project moved from  D:/Old/Project  to  E:/New/Project
    Type the old prefix, the new prefix, click Replace All — done.

    Covers: SCRIPT, MA, IMPORT_3D, JSON, SHAPES, PUBLISH panels
            and every bubble path inside MODULE panels.
    """

    _STYLE = """
        QDialog  { background-color: #252526; color: white; font-size: 13px; }
        QLabel   { color: #cccccc; font-weight: bold; }
        QLineEdit { background-color: #1e1e1e; border: 1px solid #555; color: white; padding: 5px; }
        QPushButton { background-color: #3e3e42; color: white; padding: 6px; font-weight: bold; }
        QPushButton:hover { background-color: #555; }
        QTextEdit { background-color: #1a1a1a; border: 1px solid #333; color: #aaa; font-size: 11px; font-family: Consolas; }
    """

    def __init__(self, workspace):
        super(PathReplaceDialog, self).__init__(workspace.main_window)
        self.workspace = workspace
        self.setWindowTitle("🔀 Replace All Paths — KRT")
        self.setMinimumWidth(620)
        self.setStyleSheet(self._STYLE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Info banner ───────────────────────────────────────────────
        info = QtWidgets.QLabel(
            "Replace a path prefix across ALL panels in ALL LODs.\n"
            "Works on: Script, MA, Import 3D, Skin JSON, Shapes, Publish, and Module bubble paths."
        )
        info.setStyleSheet("color: #999; font-weight: normal; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Find / Replace fields ─────────────────────────────────────
        form = QtWidgets.QFormLayout()

        self.edit_find = QtWidgets.QLineEdit()
        self.edit_find.setPlaceholderText("e.g.  D:/Old/Project  or  /old/mnt/")
        self.edit_find.setToolTip("Old path prefix to search for (case-insensitive on Windows, case-sensitive on Linux/Mac)")

        self.edit_replace = QtWidgets.QLineEdit()
        self.edit_replace.setPlaceholderText("e.g.  E:/New/Project  or  /new/mnt/")

        self.chk_case = QtWidgets.QCheckBox("Case-insensitive match")
        self.chk_case.setChecked(True)
        self.chk_case.setStyleSheet("color: #aaa; font-weight: normal;")

        # Browse buttons
        row_find = QtWidgets.QHBoxLayout()
        row_find.addWidget(self.edit_find)
        btn_browse_find = QtWidgets.QPushButton("📂")
        btn_browse_find.setFixedWidth(32)
        btn_browse_find.setToolTip("Browse for old root directory")
        btn_browse_find.clicked.connect(lambda: self._browse_into(self.edit_find))
        row_find.addWidget(btn_browse_find)

        row_replace = QtWidgets.QHBoxLayout()
        row_replace.addWidget(self.edit_replace)
        btn_browse_rep = QtWidgets.QPushButton("📂")
        btn_browse_rep.setFixedWidth(32)
        btn_browse_rep.setToolTip("Browse for new root directory")
        btn_browse_rep.clicked.connect(lambda: self._browse_into(self.edit_replace))
        row_replace.addWidget(btn_browse_rep)

        form.addRow("Find (old prefix):",    row_find)
        form.addRow("Replace (new prefix):", row_replace)
        form.addRow("",                      self.chk_case)
        layout.addLayout(form)

        # ── Preview / log ─────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Preview (changes will appear here):"))
        self.txt_preview = QtWidgets.QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setFixedHeight(160)
        layout.addWidget(self.txt_preview)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()

        btn_preview = QtWidgets.QPushButton("🔍 Preview Changes")
        btn_preview.clicked.connect(self._do_preview)

        btn_replace = QtWidgets.QPushButton("✅ Replace All")
        btn_replace.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        btn_replace.clicked.connect(self._do_replace)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_preview)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_replace)
        layout.addLayout(btn_row)

    # ──────────────────────────────────────────────────────────────────
    def _browse_into(self, line_edit):
        res = cmds.fileDialog2(fm=3, caption="Select Directory")
        if res:
            line_edit.setText(res[0].replace("\\", "/"))

    def _collect_all_path_targets(self):
        """
        Returns a list of (getter_fn, setter_fn, current_path) tuples
        covering every path field in every LOD panel.
        """
        ws = self.workspace
        targets = []

        FIELD_TYPES = {"SCRIPT", "MA", "IMPORT_3D", "JSON", "SHAPES", "PUBLISH"}

        for lod_idx in range(ws.lod_stack.count()):
            page      = ws.lod_stack.widget(lod_idx)
            container = page.panels_container

            for panel_idx in range(container.layout.count()):
                panel  = container.layout.itemAt(panel_idx).widget()
                p_type = getattr(panel, 'p_type', None)

                if p_type in FIELD_TYPES:
                    field = panel.field
                    current = field.text()
                    if current:
                        targets.append((lambda f=field: f.text(),
                                        lambda v, f=field: f.setText(v),
                                        current))

                elif p_type == "MODULE":
                    bubble_layout = getattr(panel, 'bubble_layout', None)
                    if not bubble_layout:
                        continue
                    for b in range(bubble_layout.count()):
                        bubble = bubble_layout.itemAt(b).widget()
                        if bubble is None:
                            continue
                        bp = getattr(bubble, 'full_path', None)
                        if bp:
                            # bubble.full_path is a plain string attribute;
                            # we also need to update the label displayed on the button
                            targets.append((
                                lambda bub=bubble: bub.full_path,
                                lambda v, bub=bubble: self._set_bubble_path(bub, v),
                                bp
                            ))
        return targets

    @staticmethod
    def _set_bubble_path(bubble, new_path):
        bubble.full_path = new_path
        # Update the visible button label to show the new filename
        bubble.btn_text.setText(os.path.basename(new_path))
        bubble.setToolTip(new_path)

    def _apply_replacement(self, old_path, find_str, replace_str, case_insensitive):
        if not find_str:
            return old_path, False
        if case_insensitive:
            if old_path.lower().replace("\\", "/").startswith(find_str.lower().replace("\\", "/")):
                new_path = replace_str.rstrip("/") + "/" + old_path[len(find_str):].lstrip("/\\")
                return new_path.replace("\\", "/"), True
        else:
            normalised = old_path.replace("\\", "/")
            find_norm  = find_str.replace("\\", "/")
            if normalised.startswith(find_norm):
                new_path = replace_str.rstrip("/") + "/" + normalised[len(find_norm):].lstrip("/")
                return new_path.replace("\\", "/"), True
        return old_path, False

    def _do_preview(self):
        find_str    = self.edit_find.text().strip()
        replace_str = self.edit_replace.text().strip()
        ci          = self.chk_case.isChecked()

        if not find_str:
            self.txt_preview.setPlainText("⚠  Please enter a 'Find' prefix first.")
            return

        targets = self._collect_all_path_targets()
        lines   = []
        matched = 0
        for getter, _, current in targets:
            new_path, changed = self._apply_replacement(current, find_str, replace_str, ci)
            if changed:
                lines.append(f"  OLD: {current}\n  NEW: {new_path}\n")
                matched += 1

        if matched:
            self.txt_preview.setPlainText(
                f"Found {matched} path(s) to replace:\n\n" + "\n".join(lines)
            )
        else:
            self.txt_preview.setPlainText("No paths matched the given prefix.")

    def _do_replace(self):
        find_str    = self.edit_find.text().strip()
        replace_str = self.edit_replace.text().strip()
        ci          = self.chk_case.isChecked()

        if not find_str:
            cmds.warning("[PathReplace] No 'Find' prefix entered.")
            return

        targets = self._collect_all_path_targets()
        replaced = 0
        log_lines = []
        for _, setter, current in targets:
            new_path, changed = self._apply_replacement(current, find_str, replace_str, ci)
            if changed:
                setter(new_path)
                log_lines.append(f"  ✓  {current}\n     → {new_path}")
                replaced += 1

        self.txt_preview.setPlainText(
            f"Replaced {replaced} path(s):\n\n" + "\n".join(log_lines)
            if replaced else "No paths matched — nothing was changed."
        )
        cmds.warning(f"[PathReplace] Replaced {replaced} path(s).")
        if replaced:
            self.accept()




# ══════════════════════════════════════════════════════════════════════
# CreateFolderStructureDialog
# ══════════════════════════════════════════════════════════════════════
class CreateFolderStructureDialog(QtWidgets.QDialog):
    """
    Creates the standard rigging project folder structure for a character.

    Structure (based on kartavirya_a layout):
      <root>/<char_name>/
        Scripts/           Python/MEL utility scripts
        Model/             Source geometry (ABC, FBX, OBJ, MA)
        CC_FBX/            Character Creator rig MA files
        module/            mGear guide templates (.sgt)
        controlShape/      Control shape JSON exports
        skinCluster/       Skin cluster .jSkin exports
        Rig/               Publish output (PUBLISH panel target)

    Also replaces all panel paths to point to the new location.
    """

    _STYLE = """
        QDialog  { background-color: #252526; color: white; font-size: 13px; }
        QLabel   { color: #cccccc; font-weight: bold; }
        QLineEdit { background-color: #1e1e1e; border: 1px solid #555; color: white; padding: 5px; }
        QPushButton { background-color: #3e3e42; color: white; padding: 6px; font-weight: bold; }
        QPushButton:hover { background-color: #555; }
        QListWidget { background-color: #1a1a1a; border: 1px solid #333; color: #aaa; font-size: 11px; }
        QCheckBox { color: #cccccc; }
    """

    STANDARD_FOLDERS = [
        ("Scripts",      "Python/MEL utility scripts (utils.py etc.)"),
        ("Model",        "Source geometry — ABC, FBX, OBJ, MA"),
        ("CC_FBX",       "Character Creator / CC4 rig MA files"),
        ("module",       "mGear guide templates (.sgt files)"),
        ("controlShape", "Control shape JSON exports"),
        ("skinCluster",  "Skin cluster .jSkin exports"),
        ("Rig",          "Publish output (set as PUBLISH panel target)"),
    ]

    def __init__(self, workspace, parent=None):
        super(CreateFolderStructureDialog, self).__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("Create Rig Folder Structure")
        self.setMinimumWidth(580)
        self.setStyleSheet(self._STYLE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        info = QtWidgets.QLabel(
            "Creates the standard rigging folder structure for a character. "
            "Optionally replaces all panel paths to point to the new location."
        )
        info.setStyleSheet("color: #888; font-weight: normal; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QtWidgets.QFormLayout()

        root_row = QtWidgets.QHBoxLayout()
        self.edit_root = QtWidgets.QLineEdit()
        self.edit_root.setPlaceholderText("e.g.  X:/VIshal_rig_ini/Vishal_workspace/")
        btn_browse = QtWidgets.QPushButton("...")
        btn_browse.setFixedWidth(32)
        btn_browse.clicked.connect(self._browse_root)
        root_row.addWidget(self.edit_root)
        root_row.addWidget(btn_browse)

        self.edit_char = QtWidgets.QLineEdit()
        self.edit_char.setPlaceholderText("e.g.  kartavirya_a")

        form.addRow("Project Root:", root_row)
        form.addRow("Character Name:", self.edit_char)
        layout.addLayout(form)

        layout.addWidget(QtWidgets.QLabel("Folders to create:"))
        self.folder_checks = []
        for folder, desc in self.STANDARD_FOLDERS:
            chk = QtWidgets.QCheckBox(f"  {folder}/   —   {desc}")
            chk.setChecked(True)
            chk.setProperty("folder_name", folder)
            layout.addWidget(chk)
            self.folder_checks.append(chk)

        self.chk_replace = QtWidgets.QCheckBox(
            "Replace all panel paths to use the new folder structure"
        )
        self.chk_replace.setChecked(True)
        layout.addWidget(self.chk_replace)

        self.txt_log = QtWidgets.QListWidget()
        self.txt_log.setFixedHeight(100)
        layout.addWidget(self.txt_log)

        btn_row = QtWidgets.QHBoxLayout()
        btn_preview = QtWidgets.QPushButton("Preview")
        btn_preview.clicked.connect(self._preview)
        btn_create = QtWidgets.QPushButton("Create Folders")
        btn_create.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        btn_create.clicked.connect(self._create)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_preview)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_create)
        layout.addLayout(btn_row)

        self._autofill()

    def _autofill(self):
        """Pre-fill root/char from the PUBLISH panel path."""
        container = self.workspace.get_current_lod_container()
        if not container:
            return
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if getattr(panel, 'p_type', None) == "PUBLISH":
                p = panel.field.text().strip().replace("\\", "/").rstrip("/")
                if p:
                    # PUBLISH panel = <char>/Rig  →  root=<workspace>, char=<char_name>
                    char_dir  = os.path.dirname(p)
                    root_dir  = os.path.dirname(char_dir)
                    char_name = os.path.basename(char_dir)
                    self.edit_root.setText(root_dir)
                    self.edit_char.setText(char_name)
                return

    def _browse_root(self):
        res = cmds.fileDialog2(fm=3, caption="Select Project Root Directory")
        if res:
            self.edit_root.setText(res[0].replace("\\", "/"))

    def _get_char_dir(self):
        root = self.edit_root.text().strip().replace("\\", "/").rstrip("/")
        name = self.edit_char.text().strip()
        if not root or not name:
            return None
        return f"{root}/{name}"

    def _preview(self):
        self.txt_log.clear()
        char_dir = self._get_char_dir()
        if not char_dir:
            self.txt_log.addItem("Fill in Project Root and Character Name first.")
            return
        self.txt_log.addItem(f"Root: {char_dir}/")
        for chk in self.folder_checks:
            if chk.isChecked():
                folder = chk.property("folder_name")
                exists = os.path.isdir(os.path.join(char_dir, folder))
                self.txt_log.addItem(f"  {'exists' if exists else 'create'}  {folder}/")

    def _create(self):
        char_dir = self._get_char_dir()
        if not char_dir:
            cmds.warning("[CreateFolders] Fill in Project Root and Character Name first.")
            return

        created, skipped = [], []
        for chk in self.folder_checks:
            if not chk.isChecked():
                continue
            folder   = chk.property("folder_name")
            full_dir = os.path.join(char_dir, folder).replace("\\", "/")
            if os.path.isdir(full_dir):
                skipped.append(folder)
            else:
                try:
                    os.makedirs(full_dir)
                    created.append(folder)
                except Exception as e:
                    cmds.warning(f"[CreateFolders] Could not create {full_dir}: {e}")

        self.txt_log.clear()
        for f in created:  self.txt_log.addItem(f"Created: {f}/")
        for f in skipped:  self.txt_log.addItem(f"Existed: {f}/")
        cmds.warning(f"[CreateFolders] Created {len(created)} folder(s) in {char_dir}")

        if self.chk_replace.isChecked() and created:
            old_prefix = self._guess_old_prefix()
            if old_prefix and old_prefix.lower() != char_dir.lower():
                self._replace_paths(old_prefix, char_dir)
            else:
                cmds.warning(
                    "[CreateFolders] Could not auto-detect old prefix. "
                    "Use Replace All Paths from a panel ... menu."
                )
        if created:
            self.accept()

    def _guess_old_prefix(self):
        """Return the common character-level ancestor of existing panel paths."""
        dirs = []
        for lod_idx in range(self.workspace.lod_stack.count()):
            page = self.workspace.lod_stack.widget(lod_idx)
            for pi in range(page.panels_container.layout.count()):
                panel = page.panels_container.layout.itemAt(pi).widget()
                pt = getattr(panel, 'p_type', None)
                if pt in {"SCRIPT", "MA", "JSON", "SHAPES", "IMPORT_3D"}:
                    p = panel.field.text().strip().replace("\\", "/")
                    if p and os.path.isfile(p):
                        dirs.append(os.path.dirname(p).replace("\\", "/"))
        if not dirs:
            return None
        try:
            common = os.path.commonpath(dirs).replace("\\", "/")
            # We want the character-folder level, so go up one more if
            # commonpath is a subfolder like Scripts/
            if len(dirs) > 1:
                return common
            return os.path.dirname(common)
        except Exception:
            return None

    def _replace_paths(self, old_prefix, new_prefix):
        old_norm = old_prefix.rstrip("/").lower()
        new_norm = new_prefix.rstrip("/")
        replaced = 0
        for lod_idx in range(self.workspace.lod_stack.count()):
            page = self.workspace.lod_stack.widget(lod_idx)
            for pi in range(page.panels_container.layout.count()):
                panel = page.panels_container.layout.itemAt(pi).widget()
                pt = getattr(panel, 'p_type', None)
                if pt in {"SCRIPT", "MA", "JSON", "SHAPES", "IMPORT_3D", "PUBLISH"}:
                    cur = panel.field.text().strip().replace("\\", "/")
                    if cur.lower().startswith(old_norm):
                        panel.field.setText(new_norm + cur[len(old_norm):])
                        replaced += 1
                elif pt == "MODULE":
                    bl = getattr(panel, 'bubble_layout', None)
                    if bl:
                        for b in range(bl.count()):
                            bubble = bl.itemAt(b).widget()
                            if bubble:
                                bp = getattr(bubble, 'full_path', '').replace("\\", "/")
                                if bp.lower().startswith(old_norm):
                                    bubble.full_path = new_norm + bp[len(old_norm):]
                                    bubble.btn_text.setText(os.path.basename(bubble.full_path))
                                    replaced += 1
        cmds.warning(f"[CreateFolders] Replaced {replaced} path(s): {old_prefix} → {new_prefix}")
        self.txt_log.addItem(f"Replaced {replaced} path(s).")



# ══════════════════════════════════════════════════════════════════════
# AYON publish — helpers shared by the dialog
# ══════════════════════════════════════════════════════════════════════
_PATH_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,8}$")


def _looks_like_file_path(value):
    """A JSON string is treated as a file path when it contains a path
    separator AND ends in a plausible file extension.

    The Kleem Folder Extractor's rule is just 'has a slash and a dot', which
    is too loose here: a SCRIPT panel keeps INLINE PYTHON in the very same
    'path' field a file path would live in, so whole code blocks were being
    picked up as files. Rejecting multi-line strings and anything carrying a
    quote character filters those out, and the extension has to look like a
    real extension rather than the tail of an expression.
    """
    if not isinstance(value, str):
        return False
    if len(value) > 1024:
        return False
    # Newlines / tabs / quotes ⇒ inline code, not a path.
    if any(ch in value for ch in "\n\r\t\"'"):
        return False
    text = value.strip()
    if not text or ("/" not in text and "\\" not in text):
        return False
    return bool(_PATH_EXT_RE.match(os.path.splitext(text)[1]))


def collect_json_file_paths(obj):
    """Recursively pull every file-path-looking string out of a JSON
    structure, de-duplicated, order preserved.

    Mirrors KleemTool_Folder_Extract_v02.extract_paths_dynamically().
    """
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, str):
            if _looks_like_file_path(node):
                key = os.path.normpath(node).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(obj)
    return found


def replace_json_file_paths(obj, path_mapping):
    """Return a copy of ``obj`` with every path found in ``path_mapping``
    swapped for its new location. Keys of ``path_mapping`` are normalised
    paths; values are the replacement paths.

    Mirrors KleemTool_Folder_Extract_v02.replace_paths_in_json().
    """
    if isinstance(obj, str):
        key = os.path.normpath(obj)
        if key in path_mapping:
            return path_mapping[key].replace("\\", "/")
        return obj
    if isinstance(obj, list):
        return [replace_json_file_paths(item, path_mapping) for item in obj]
    if isinstance(obj, dict):
        return {k: replace_json_file_paths(v, path_mapping) for k, v in obj.items()}
    return obj


def source_file_hash(path):
    """'op3'-style source hash used by ayon-core's integrator: name|size|mtime."""
    try:
        return "|".join([
            os.path.basename(path),
            str(os.path.getsize(path)),
            str(int(os.path.getmtime(path))),
        ]).replace(".", ",")
    except Exception:
        return ""


class AyonPublishDialog(QtWidgets.QDialog):
    """
    Publishes TWO products to AYON from the Kleem Rigging Tool:

      1. rigMain          (product_type: rig)       → the built .ma scene
      2. workfileRigging  (product_type: workfile)  → the rigging work
                                                      folder, extracted the
                                                      same way the Kleem
                                                      Folder Extractor does

    Work-folder layout (identical to KleemTool_Folder_Extract_v02):

        <publish version dir>/<RigName>/<parent folder name>/<file>
        <publish version dir>/<RigName>/Rig/<RigName>.json

    …where the JSON is the pipeline config with every copied path rewritten
    to its new location, so loading it on another machine resolves without
    any manual re-mapping. Files living under a ``RigUtils`` folder are
    optionally left in place and keep their original server path.

    API patterns adopted from ayon_batch_folder_publisher:
      • EntityHub for product / version creation (avoids 409 conflicts)
      • ayon_api.post() with attrib / data / files payload for representations
      • get_last_version_by_product_id() for correct next-version increment
      • rootless '{root[...]}/…' file paths so publishes resolve on any site
    """

    # ── Defaults ──────────────────────────────────────────────────────
    DEFAULT_RIG_PRODUCT  = "rigMain"
    DEFAULT_RIG_TYPE     = "rig"
    RIG_REPRE_NAME       = "ma"

    DEFAULT_WORK_PRODUCT = "workfileRigging"
    DEFAULT_WORK_TYPE    = "workfile"
    WORK_REPRE_NAME      = "json"

    # ── Stylesheet ────────────────────────────────────────────────────
    _STYLE = """
        QDialog  { background-color: #252526; color: white; font-size: 13px; }
        QLabel   { color: #cccccc; font-weight: bold; }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #1e1e1e; border: 1px solid #555;
            color: white; padding: 5px;
        }
        QPushButton {
            background-color: #3e3e42; color: white;
            padding: 6px; font-weight: bold;
        }
        QPushButton:hover { background-color: #555; }
        QGroupBox {
            border: 1px solid #444; border-radius: 4px;
            margin-top: 10px; color: #aaa; font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin; padding: 0 6px;
        }
        QListWidget {
            background-color: #1e1e1e; border: 1px solid #444;
            color: #cccccc; font-size: 11px;
        }
        QProgressBar {
            border: 1px solid #444; border-radius: 3px;
            background: #1e1e1e; color: white; text-align: center;
        }
        QProgressBar::chunk { background-color: #2196F3; }
        QCheckBox { color: #cccccc; font-weight: normal; font-size: 13px; }
    """

    def __init__(self, workspace):
        super(AyonPublishDialog, self).__init__(workspace.main_window)
        self.workspace   = workspace
        self.rig_name    = workspace.edit_rig_name.text().strip() or "Unnamed_Rig"
        self.folder_data = {}   # { folder_path: folder_id }

        # Filled by _resolve_root() at publish time
        self._root_name  = None
        self._root_value = None
        self.last_work_folder = ""

        self.setWindowTitle("Publish Rig to AYON — KRT")
        self.setMinimumWidth(620)
        self.setStyleSheet(self._STYLE)

        # ── Root layout ───────────────────────────────────────────────
        root = QtWidgets.QVBoxLayout(self)

        # Check AYON connectivity once at open
        try:
            ayon_api.get_base_url()
        except Exception:
            cmds.warning(
                "AYON API is not connected. "
                "Make sure AYON_SERVER_URL and AYON_API_KEY env vars are set."
            )

        # ── Section 1: AYON Context ───────────────────────────────────
        grp_ctx = QtWidgets.QGroupBox("AYON Context")
        ctx_form = QtWidgets.QFormLayout(grp_ctx)

        self.cmb_project  = QtWidgets.QComboBox()
        self.cmb_folder   = QtWidgets.QComboBox()
        self.cmb_folder.setEditable(True)
        self.cmb_task     = QtWidgets.QComboBox()

        ctx_form.addRow("Project:",             self.cmb_project)
        ctx_form.addRow("Folder (Asset Path):", self.cmb_folder)
        ctx_form.addRow("Task:",                self.cmb_task)
        root.addWidget(grp_ctx)

        # ── Section 2: Products and Build Options ─────────────────────
        grp_prod = QtWidgets.QGroupBox("Publish & Build Options")
        prod_form = QtWidgets.QFormLayout(grp_prod)

        self.chk_rebuild_scene = QtWidgets.QCheckBox("Rebuild entire scene before publishing")
        self.chk_rebuild_scene.setChecked(True)
        self.chk_rebuild_scene.setStyleSheet("color: #ffb74d; font-weight: bold; margin-bottom: 5px;")
        self.chk_rebuild_scene.setToolTip(
            "Wipes the scene and re-runs every step before publishing.\n"
            "This window hides while the build runs so the build progress\n"
            "window and any script prompts stay clickable.\n\n"
            "Untick to publish the scene exactly as it is right now."
        )
        prod_form.addRow(self.chk_rebuild_scene)

        # 1 — the built rig scene
        self.chk_publish_rig = QtWidgets.QCheckBox("Publish Rig (.ma):")
        self.chk_publish_rig.setChecked(True)
        self.chk_publish_rig.setToolTip("product_type: rig  —  publishes the built Maya scene")
        self.cmb_prod_rig = QtWidgets.QComboBox()
        self.cmb_prod_rig.setEditable(True)
        self.cmb_prod_rig.setCurrentText(self.DEFAULT_RIG_PRODUCT)

        # 2 — the extracted rigging work folder
        self.chk_publish_work = QtWidgets.QCheckBox("Publish Rigging Work Folder:")
        self.chk_publish_work.setChecked(True)
        self.chk_publish_work.setToolTip(
            "product_type: workfile  —  collects every file referenced by the "
            "pipeline JSON into <RigName>/<parent folder>/<file> and writes the "
            "re-pathed JSON to <RigName>/Rig/"
        )
        self.cmb_prod_work = QtWidgets.QComboBox()
        self.cmb_prod_work.setEditable(True)
        self.cmb_prod_work.setCurrentText(self.DEFAULT_WORK_PRODUCT)

        prod_form.addRow(self.chk_publish_rig,  self.cmb_prod_rig)
        prod_form.addRow(self.chk_publish_work, self.cmb_prod_work)

        self.chk_ignore_rigutils = QtWidgets.QCheckBox(
            "Ignore 'RigUtils' folder  (keep original server paths)"
        )
        self.chk_ignore_rigutils.setChecked(True)
        self.chk_ignore_rigutils.setToolTip(
            "Files under a RigUtils folder are shared studio utilities. When "
            "ticked they are not copied into the package and the JSON keeps "
            "pointing at the original server location."
        )
        self.chk_ignore_rigutils.stateChanged.connect(self.refresh_package_files)
        prod_form.addRow(self.chk_ignore_rigutils)

        root.addWidget(grp_prod)

        # ── Section 3: Work folder preview ────────────────────────────
        grp_pkg = QtWidgets.QGroupBox("Rigging Work Folder — files scanned from the pipeline JSON")
        pkg_layout = QtWidgets.QVBoxLayout(grp_pkg)

        self.list_pkg_files = QtWidgets.QListWidget()
        self.list_pkg_files.setFixedHeight(120)
        pkg_layout.addWidget(self.list_pkg_files)

        pkg_btn_row = QtWidgets.QHBoxLayout()
        btn_refresh = QtWidgets.QPushButton("🔄 Re-scan Pipeline")
        btn_refresh.clicked.connect(self.refresh_package_files)

        btn_create_folders = QtWidgets.QPushButton("📁 Create Folder Structure")
        btn_create_folders.setToolTip(
            "Create the standard rigging folder structure for this character "
            "(Scripts, Model, skinCluster, controlShape, module, Rig)"
        )
        btn_create_folders.clicked.connect(self.open_create_folder_dialog)

        pkg_btn_row.addWidget(btn_refresh)
        pkg_btn_row.addWidget(btn_create_folders)
        pkg_layout.addLayout(pkg_btn_row)
        root.addWidget(grp_pkg)

        # ── Section 4: Comment ────────────────────────────────────────
        root.addWidget(QtWidgets.QLabel("Publish Comment:"))
        self.edit_comment = QtWidgets.QTextEdit()
        self.edit_comment.setFixedHeight(55)
        root.addWidget(self.edit_comment)

        # ── Section 5: Progress ───────────────────────────────────────
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 5)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        self.btn_publish = QtWidgets.QPushButton("🚀  Auto-Save & Publish Selected")
        self.btn_publish.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 10px; font-size: 14px;"
        )
        self.btn_publish.clicked.connect(self.execute_publish)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_publish)
        root.addLayout(btn_row)

        # ── Wire up change signals ────────────────────────────────────
        self.cmb_project.currentTextChanged.connect(self.on_project_changed)
        self.cmb_folder.currentTextChanged.connect(self.on_folder_changed)

        # ── Populate ──────────────────────────────────────────────────
        self.populate_projects()
        self.refresh_package_files()

    # ══════════════════════════════════════════════════════════════════
    # Populate helpers
    # ══════════════════════════════════════════════════════════════════
    def populate_projects(self):
        try:
            projects = [p["name"] for p in ayon_api.get_projects()]
            self.cmb_project.addItems(projects)
        except Exception as e:
            cmds.warning(f"[AYON] Could not load projects: {e}")
            self.cmb_project.addItem("No connection")

    def on_project_changed(self, project_name):
        self.cmb_folder.clear()
        self.folder_data.clear()
        if not project_name or project_name == "No connection":
            return
        try:
            for f in ayon_api.get_folders(project_name, fields=["path", "id"]):
                path = f.get("path")
                if path:
                    self.folder_data[path] = f["id"]
            self.cmb_folder.addItems(sorted(self.folder_data.keys()))
        except Exception as e:
            cmds.warning(f"[AYON] Could not load folders: {e}")

    def on_folder_changed(self, folder_path):
        self.cmb_task.clear()
        self.cmb_prod_rig.clear()
        self.cmb_prod_work.clear()

        project_name = self.cmb_project.currentText()
        folder_id    = self.folder_data.get(folder_path)
        if not project_name or not folder_id:
            self.cmb_prod_rig.setCurrentText(self.DEFAULT_RIG_PRODUCT)
            self.cmb_prod_work.setCurrentText(self.DEFAULT_WORK_PRODUCT)
            return

        try:
            tasks = list(
                ayon_api.get_tasks(project_name, folder_ids=[folder_id], fields=["name", "id"])
            )
            self.cmb_task.addItems([t["name"] for t in tasks])

            # Offer existing product names for convenience, then reset defaults
            products = list(
                ayon_api.get_products(project_name, folder_ids=[folder_id], fields=["name"])
            )
            prod_names = [p["name"] for p in products]

            for cmb, default in [
                (self.cmb_prod_rig,  self.DEFAULT_RIG_PRODUCT),
                (self.cmb_prod_work, self.DEFAULT_WORK_PRODUCT),
            ]:
                cmb.addItems(prod_names)
                cmb.setCurrentText(default)

        except Exception as e:
            cmds.warning(f"[AYON] Could not load tasks/products: {e}")

    # ══════════════════════════════════════════════════════════════════
    # Work-folder preview
    # ══════════════════════════════════════════════════════════════════
    def refresh_package_files(self):
        """Show exactly what the work-folder extraction will do, using the
        same JSON scan the extraction itself runs."""
        self.list_pkg_files.clear()
        try:
            pipeline_data = self.workspace.get_current_pipeline_data()
        except Exception as e:
            self.list_pkg_files.addItem(f"(could not read pipeline data: {e})")
            return

        paths = collect_json_file_paths(pipeline_data)
        if not paths:
            self.list_pkg_files.addItem("(no file paths found in the pipeline JSON)")
            return

        ignore_rigutils = self.chk_ignore_rigutils.isChecked()
        copied = ignored = missing = 0

        for path in paths:
            norm   = os.path.normpath(path)
            parts  = norm.replace("\\", "/").split("/")
            parent = os.path.basename(os.path.dirname(norm))
            label  = f"{parent}/{os.path.basename(norm)}"

            if not os.path.isfile(norm):
                missing += 1
                item = QtWidgets.QListWidgetItem(f"⚠️  {label}   — missing, skipped")
                item.setForeground(QtGui.QColor("#f44336"))
            elif ignore_rigutils and "RigUtils" in parts:
                ignored += 1
                item = QtWidgets.QListWidgetItem(f"⏭️  {label}   — RigUtils, left in place")
                item.setForeground(QtGui.QColor("#ffb74d"))
            else:
                copied += 1
                item = QtWidgets.QListWidgetItem(f"✅  {label}   → {self.rig_name}/{parent}/")
            item.setToolTip(path)
            self.list_pkg_files.addItem(item)

        summary = QtWidgets.QListWidgetItem(
            f"── {len(paths)} path(s):  {copied} to copy  ·  "
            f"{ignored} RigUtils kept  ·  {missing} missing"
        )
        summary.setForeground(QtGui.QColor("#888"))
        self.list_pkg_files.addItem(summary)

    def open_create_folder_dialog(self):
        """Open the folder structure creation dialog."""
        dlg = CreateFolderStructureDialog(self.workspace, self)
        if IS_PYSIDE6:
            dlg.exec()
        else:
            dlg.exec_()

    # ══════════════════════════════════════════════════════════════════
    # Core publish
    # ══════════════════════════════════════════════════════════════════
    def execute_publish(self):
        """
        Full publish sequence:

          Step 1  Validate context (project / folder / task)
          Step 2  Resolve the local staging dir + save the pipeline JSON
          Step 3  Run the full rig build (optional)
          Step 4  Save the built Maya scene locally
          Step 5  Publish rigMain          — copy the .ma to the server
          Step 6  Publish workfileRigging  — extract the work folder onto
                  the server publish path and register it
        """
        print("\n" + "=" * 60)
        print("[AYON PUBLISH] INITIATING KRT PUBLISH SEQUENCE")
        print("=" * 60)

        # ── Step 1: Validate context ───────────────────────────────────
        project_name = self.cmb_project.currentText()
        folder_path  = self.cmb_folder.currentText()
        folder_id    = self.folder_data.get(folder_path)
        task_name    = self.cmb_task.currentText()
        prod_rig     = self.cmb_prod_rig.currentText().strip() or self.DEFAULT_RIG_PRODUCT
        prod_work    = self.cmb_prod_work.currentText().strip() or self.DEFAULT_WORK_PRODUCT
        comment      = self.edit_comment.toPlainText().strip()

        print(f"[AYON PUBLISH] Project : {project_name}")
        print(f"[AYON PUBLISH] Folder  : {folder_path}  (id={folder_id})")
        print(f"[AYON PUBLISH] Task    : {task_name}")

        if not folder_id:
            cmds.error("[AYON PUBLISH] A valid AYON folder must be selected. Aborting.")
            return

        do_rig  = self.chk_publish_rig.isChecked()
        do_work = self.chk_publish_work.isChecked()
        if not (do_rig or do_work):
            cmds.warning("[AYON PUBLISH] No products selected for publishing.")
            self._set_status("⚠️ Nothing selected to publish.", color="#f4a261")
            return

        self.btn_publish.setEnabled(False)
        self.progress_bar.setRange(0, 5)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        QtWidgets.QApplication.processEvents()

        # ── Step 2: Local staging dir + pipeline JSON ──────────────────
        staging_dir = self._resolve_publish_dir()
        if not staging_dir:
            self.btn_publish.setEnabled(True)
            return

        json_name = f"{self.rig_name}.json"
        json_path = os.path.join(staging_dir, json_name).replace("\\", "/")
        self._set_status("Saving pipeline JSON config …")
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.workspace.get_current_pipeline_data(), f, indent=4)
            # Stage 35, Rule 2: an AYON publish also writes a KRT pipeline
            # JSON - keep the standalone graph/guide JSON in sync with it.
            if hasattr(self.workspace, "graph_widget") and hasattr(self.workspace.graph_widget, "save_all_guides"):
                self.workspace.graph_widget.save_all_guides(overwrite=True)
            print(f"[AYON PUBLISH] Pipeline JSON saved: {json_path}")
        except Exception as e:
            cmds.error(f"[AYON PUBLISH] Failed to save JSON config: {e}")
            self.btn_publish.setEnabled(True)
            return
        self.progress_bar.setValue(1)
        QtWidgets.QApplication.processEvents()

        # ── Step 3: Run the full rig build (optional) ──────────────────
        if self.chk_rebuild_scene.isChecked():
            self._set_status("🔨 Running full rig build …  (this may take a while)")
            QtWidgets.QApplication.processEvents()
            try:
                build_ok = self._run_build_unblocked()
            except Exception:
                traceback.print_exc()
                build_ok = False
            if not build_ok:
                cmds.warning(
                    "[AYON PUBLISH] Rig build failed or was cancelled. "
                    "Fix build errors before publishing."
                )
                self._set_status("❌ Build failed — publish aborted.", color="#f44336")
                self.btn_publish.setEnabled(True)
                return
            print("[AYON PUBLISH] Full rig build completed successfully.")
        else:
            self._set_status("⏭️ Skipping rig rebuild, capturing current scene …")
            print("[AYON PUBLISH] Skipping rebuild; publishing current scene state.")

        self.progress_bar.setValue(2)
        QtWidgets.QApplication.processEvents()

        # ── Step 4: Save the built Maya scene locally ──────────────────
        ma_path = ""
        if do_rig:
            ma_name = f"{self.rig_name}_built.ma"
            ma_path = os.path.join(staging_dir, ma_name).replace("\\", "/")
            self._set_status(f"Saving built Maya scene → {ma_name} …")
            try:
                cmds.file(rename=ma_path)
                cmds.file(save=True, type="mayaAscii", force=True)
                print(f"[AYON PUBLISH] Built scene saved: {ma_path}")
            except Exception as e:
                cmds.error(f"[AYON PUBLISH] Failed to save built Maya scene: {e}")
                self.btn_publish.setEnabled(True)
                return
        self.progress_bar.setValue(3)
        QtWidgets.QApplication.processEvents()

        # Update session tracking
        self.workspace.set_session_path(json_path)
        self.workspace.session_manager.add_published(json_path)
        self.workspace.main_window.refresh_all_session_lists()

        # ── Resolve server side context ────────────────────────────────
        self._set_status("Resolving AYON server publish path …")
        server_root = self._resolve_root(project_name)

        folder_entity = None
        try:
            folder_entity = ayon_api.get_folder_by_id(project_name, folder_id)
        except Exception as e:
            print(f"[AYON PUBLISH] Warning: could not fetch folder entity: {e}")

        task_id = None
        if task_name:
            try:
                task = ayon_api.get_task_by_name(project_name, folder_id, task_name)
                task_id = task["id"] if task else None
            except Exception as e:
                print(f"[AYON PUBLISH] Warning: could not resolve task id: {e}")

        author = None
        try:
            author = (ayon_api.get_user() or {}).get("name")
        except Exception:
            pass

        project_code = ""
        try:
            project_code = (ayon_api.get_project(project_name) or {}).get("code") or ""
        except Exception:
            pass

        variant = task_name or "main"

        ctx = {
            "project_name":  project_name,
            "project_code":  project_code,
            "folder_id":     folder_id,
            "folder_entity": folder_entity,
            "task_id":       task_id,
            "task_name":     task_name,
            "author":        author,
            "comment":       comment,
            "variant":       variant,
            "server_root":   server_root,
        }

        results = {}

        # ── Step 5: Publish rigMain ────────────────────────────────────
        if do_rig:
            self._set_status(f"Publishing {prod_rig} …")
            QtWidgets.QApplication.processEvents()
            results[prod_rig] = self._publish_rig(ctx, prod_rig, ma_path)
        self.progress_bar.setValue(4)
        QtWidgets.QApplication.processEvents()

        # ── Step 6: Publish the rigging work folder ────────────────────
        if do_work:
            self._set_status(f"Publishing {prod_work} (extracting work folder) …")
            QtWidgets.QApplication.processEvents()
            results[prod_work] = self._publish_work_folder(
                ctx, prod_work, json_name, staging_dir
            )
        self.progress_bar.setValue(5)
        QtWidgets.QApplication.processEvents()

        # ── Result ────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        success_msgs, failed = [], []
        for prod_name, ver in results.items():
            if ver:
                success_msgs.append(f"  {prod_name} → v{ver:03d}")
            else:
                failed.append(prod_name)

        if not failed and success_msgs:
            msg = "✅ AYON Publish SUCCESS\n" + "\n".join(success_msgs)
            print(msg)
            if self.last_work_folder:
                print(f"  work folder: {self.last_work_folder}")
            cmds.warning(msg.replace("\n", " | "))
            self._set_status("✅ Publish complete!", color="#00c49a")
            self.accept()
        else:
            err = f"[AYON PUBLISH] Failed: {', '.join(failed)}. Check Script Editor."
            print(err)
            cmds.error(err)
            self._set_status("❌ Some products failed — see Script Editor.", color="#f44336")
            self.btn_publish.setEnabled(True)

    def _run_build_unblocked(self):
        """Run workspace.run_full_build() with THIS dialog hidden.

        Why this matters: the dialog is opened with exec(), which makes it
        APPLICATION MODAL — while it is visible, every other window in Maya
        is input-blocked. The build opens its own BuildProgressDialog, and
        build scripts routinely raise prompts of their own (confirmDialog,
        Maya's file-not-found dialog, third-party rig UIs). Under the modal
        those windows appear but accept no clicks, so the build stops dead
        and even STOP BUILD does nothing — the whole publish hangs with no
        way out but killing Maya.

        Hiding the dialog releases the modal block for the duration of the
        build; exec()'s event loop keeps running the whole time, so the
        dialog comes straight back afterwards.
        """
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
        QtWidgets.QApplication.processEvents()
        try:
            return self.workspace.run_full_build()
        finally:
            if was_visible:
                self.show()
                self.raise_()
                self.activateWindow()
            QtWidgets.QApplication.processEvents()

    # ══════════════════════════════════════════════════════════════════
    # Product 1 — rigMain
    # ══════════════════════════════════════════════════════════════════
    def _publish_rig(self, ctx, prod_name, ma_path):
        """Publish the built .ma as a single-file 'rig' product.
        Returns the version number, or None on failure."""
        print(f"\n[AYON PUBLISH] → {prod_name} ({self.DEFAULT_RIG_TYPE})")
        if not ma_path or not os.path.isfile(ma_path):
            print(f"  [warn] Maya scene not found: {ma_path}")
            return None

        project_name = ctx["project_name"]
        try:
            hub = EntityHub(project_name)
            prod_id = self._get_or_create_product(
                hub, project_name, ctx["folder_id"], prod_name, self.DEFAULT_RIG_TYPE
            )
            ver_id, ver_num = self._create_version(
                hub, project_name, prod_id, ctx["task_id"], ctx["comment"], ctx["author"]
            )

            server_dir = self._build_server_path(
                ctx, self.DEFAULT_RIG_TYPE, prod_name, ver_num
            )
            dest = self._copy_file(ma_path, server_dir)

            self._patch_version_attribs(
                project_name, ver_id, self.DEFAULT_RIG_TYPE, ctx["comment"], ma_path
            )
            self._attach_representation(
                ctx, ver_id, self.RIG_REPRE_NAME, [dest], prod_name,
                self.DEFAULT_RIG_TYPE, ver_num
            )
            print(f"  [ok] {prod_name} → v{ver_num:03d}")
            return ver_num
        except Exception:
            traceback.print_exc()
            return None

    # ══════════════════════════════════════════════════════════════════
    # Product 2 — the rigging work folder
    # ══════════════════════════════════════════════════════════════════
    def _publish_work_folder(self, ctx, prod_name, json_name, staging_dir):
        """Extract the rigging work folder onto the AYON publish path and
        register it as one representation. Returns the version number, or
        None on failure."""
        print(f"\n[AYON PUBLISH] → {prod_name} ({self.DEFAULT_WORK_TYPE})")
        project_name = ctx["project_name"]

        try:
            pipeline_data = self.workspace.get_current_pipeline_data()

            hub = EntityHub(project_name)
            prod_id = self._get_or_create_product(
                hub, project_name, ctx["folder_id"], prod_name, self.DEFAULT_WORK_TYPE
            )
            ver_id, ver_num = self._create_version(
                hub, project_name, prod_id, ctx["task_id"], ctx["comment"], ctx["author"]
            )

            # Where the extracted folder lands. Prefer the AYON publish path;
            # fall back to the local staging dir when no roots are configured.
            dest_root = self._build_server_path(
                ctx, self.DEFAULT_WORK_TYPE, prod_name, ver_num
            ) or staging_dir

            # Record the AYON context inside the published JSON
            ayon_context = {
                "project":       project_name,
                "folder_path":   (ctx["folder_entity"] or {}).get("path", ""),
                "folder_id":     ctx["folder_id"],
                "task":          ctx["task_name"],
                "prod_rig":      self.cmb_prod_rig.currentText().strip(),
                "prod_workfile": prod_name,
                "version":       ver_num,
            }
            pipeline_data["ayon_publish_context"] = ayon_context

            folder_root, out_json, files, stats = self._extract_work_folder(
                pipeline_data, dest_root, json_name,
                self.chk_ignore_rigutils.isChecked()
            )
            self.last_work_folder = folder_root

            print(
                f"  [extract] {stats['copied']} copied  ·  "
                f"{stats['ignored']} RigUtils kept  ·  "
                f"{stats['missing']} missing  →  {folder_root}"
            )

            self._patch_version_attribs(
                project_name, ver_id, self.DEFAULT_WORK_TYPE, ctx["comment"], folder_root
            )
            # One representation for the whole folder; the re-pathed JSON is
            # the primary file, every collected file rides along with it.
            self._attach_representation(
                ctx, ver_id, self.WORK_REPRE_NAME, files, prod_name,
                self.DEFAULT_WORK_TYPE, ver_num, primary=out_json
            )
            print(f"  [ok] {prod_name} → v{ver_num:03d}  ({len(files)} file(s))")
            return ver_num
        except Exception:
            traceback.print_exc()
            return None

    def _extract_work_folder(self, pipeline_data, dest_root, json_name, ignore_rigutils):
        """Build the rigging work folder exactly the way
        KleemTool_Folder_Extract_v02 does.

            <dest_root>/<RigName>/<parent folder name>/<file>
            <dest_root>/<RigName>/Rig/<json_name>

        Returns (folder_root, json_path, all_files, stats).
        """
        folder_root = os.path.join(dest_root, self.rig_name).replace("\\", "/")
        os.makedirs(folder_root, exist_ok=True)

        raw_paths = collect_json_file_paths(pipeline_data)

        path_mapping = {}
        collected    = []
        taken        = {}          # dest path (lower) → source, collision guard
        copied = ignored = missing = 0

        for src in raw_paths:
            norm = os.path.normpath(src)
            if not os.path.isfile(norm):
                missing += 1
                print(f"  [pkg] SKIP (missing): {src}")
                continue

            parts = norm.replace("\\", "/").split("/")
            if ignore_rigutils and "RigUtils" in parts:
                ignored += 1
                print(f"  [pkg] SKIP (RigUtils): {src}")
                continue

            parent_name = os.path.basename(os.path.dirname(norm))
            target_dir  = os.path.join(folder_root, parent_name).replace("\\", "/")
            target      = os.path.join(target_dir, os.path.basename(norm)).replace("\\", "/")

            clash = taken.get(target.lower())
            if clash and os.path.normcase(clash) != os.path.normcase(norm):
                cmds.warning(
                    f"[AYON PUBLISH] Name clash in work folder: '{target}' is "
                    f"written by both '{clash}' and '{norm}'. The second one wins."
                )

            try:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(norm, target)
                copied += 1
                taken[target.lower()] = norm
                path_mapping[norm] = target
                collected.append(target)
                print(f"  [pkg] {parent_name}/{os.path.basename(norm)}  →  {target}")
            except Exception as e:
                print(f"  [pkg] WARNING copy failed for {norm}: {e}")

        # Rewrite every collected path in the JSON, then park it in Rig/
        updated = replace_json_file_paths(pipeline_data, path_mapping)

        rig_dir = os.path.join(folder_root, "Rig").replace("\\", "/")
        os.makedirs(rig_dir, exist_ok=True)
        out_json = os.path.join(rig_dir, json_name).replace("\\", "/")
        with open(out_json, 'w', encoding='utf-8') as fh:
            json.dump(updated, fh, indent=4)
        print(f"  [json] Re-pathed pipeline JSON → {out_json}")

        # JSON first so it becomes the representation's primary file
        all_files = [out_json] + collected
        stats = {"copied": copied, "ignored": ignored, "missing": missing}
        return folder_root, out_json, all_files, stats

    # ══════════════════════════════════════════════════════════════════
    # Path helpers
    # ══════════════════════════════════════════════════════════════════
    def _resolve_publish_dir(self):
        """
        Local staging directory priority:
          1. Active PUBLISH panel in the current LOD
          2. Directory of the current session JSON
          3. Maya user app dir fallback (auto-created)
        """
        publish_dir = None
        container = self.workspace.get_current_lod_container()
        if container:
            for i in range(container.layout.count()):
                panel = container.layout.itemAt(i).widget()
                if getattr(panel, 'p_type', '') == "PUBLISH" and getattr(panel, 'is_active', True):
                    candidate = panel.field.text().strip()
                    if candidate and os.path.isdir(candidate):
                        publish_dir = candidate
                        break

        if not publish_dir:
            if self.workspace.session_path:
                publish_dir = os.path.dirname(self.workspace.session_path)
            else:
                publish_dir = os.path.join(
                    cmds.internalVar(userAppDir=True), "KRT", "AutoPublish"
                ).replace("\\", "/")

        if not os.path.exists(publish_dir):
            try:
                os.makedirs(publish_dir)
            except Exception as e:
                cmds.error(f"[AYON PUBLISH] Cannot create publish directory: {e}")
                return None

        print(f"[AYON PUBLISH] Local staging directory: {publish_dir}")
        return publish_dir

    def _resolve_root(self, project_name):
        """Pick a project root and remember its name + value, so published
        file paths can be stored root-templated ('{root[work]}/…') the way
        ayon-core's integrator does. Without this the representation stores
        a machine-specific absolute path and other artists cannot load it.

        Returns the root value, or None when no roots are configured.
        """
        self._root_name = self._root_value = None
        try:
            roots = ayon_api.get_project_roots_by_site_id(project_name)
        except Exception as e:
            print(f"[AYON PUBLISH] Warning: could not get server roots: {e}")
            return None

        if not roots:
            print(f"[AYON PUBLISH] Warning: no roots defined for '{project_name}'; "
                  f"falling back to local paths.")
            return None

        for key in ("publish", "work", "root"):
            if key in roots:
                self._root_name, self._root_value = key, roots[key]
                break
        else:
            self._root_name = list(roots.keys())[0]
            self._root_value = roots[self._root_name]

        self._root_value = (self._root_value or "").replace("\\", "/")
        print(f"[AYON PUBLISH] AYON root '{self._root_name}': {self._root_value}")
        return self._root_value

    def _rootless(self, path):
        """Absolute path → '{root[<name>]}/…' template path."""
        if not path:
            return path
        p = path.replace("\\", "/")
        if not self._root_value:
            return p
        rv = self._root_value.rstrip("/")
        if p.lower().startswith(rv.lower()):
            return "{root[%s]}%s" % (self._root_name, p[len(rv):])
        return p

    def _build_server_path(self, ctx, prod_type, prod_name, ver_num):
        """
        Server-side version directory for a product:

          <root>/<project>/<asset folder path>/publish/
              <prod_type>/<prod_name>/<variant>/<v###>

        Returns None when the root or the folder entity is unavailable, in
        which case the caller falls back to the local staging directory.
        """
        if not self._root_value or not ctx.get("folder_entity"):
            return None
        asset_path = (ctx["folder_entity"].get("path") or "").strip("/")
        return os.path.join(
            self._root_value, ctx["project_name"], asset_path,
            "publish", prod_type, prod_name, ctx["variant"], f"v{ver_num:03d}"
        ).replace("\\", "/")

    def _copy_file(self, local_path, dest_dir):
        """Copy one file into dest_dir. Returns the destination path, or the
        original path when no destination is available / the copy fails."""
        if not dest_dir:
            return local_path
        dest_path = os.path.join(dest_dir, os.path.basename(local_path)).replace("\\", "/")
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(local_path, dest_path)
            print(f"  [copy] {os.path.basename(local_path)} → {dest_path}")
            return dest_path
        except Exception as e:
            print(f"  [copy] WARNING — server copy failed: {e}. Using local path.")
            return local_path

    # ══════════════════════════════════════════════════════════════════
    # AYON entity helpers
    # ══════════════════════════════════════════════════════════════════
    def _get_or_create_product(self, hub, project_name, folder_id, prod_name, prod_type):
        """Case-insensitive get-or-create via EntityHub. Returns product id."""
        existing = list(ayon_api.get_products(project_name, folder_ids=[folder_id]))
        match = next((p for p in existing if p["name"].lower() == prod_name.lower()), None)
        if match:
            print(f"  [product] Found existing: '{match['name']}' (id={match['id']})")
            return match["id"]

        new_product = hub.add_new_product(
            product_type=prod_type, name=prod_name, folder_id=folder_id
        )
        hub.commit_changes()
        print(f"  [product] Created new: '{prod_name}' (id={new_product['id']})")
        return new_product["id"]

    def _create_version(self, hub, project_name, prod_id, task_id, comment, author=None):
        """Create the next version via EntityHub. Returns (version_id, number)."""
        last_ver     = ayon_api.get_last_version_by_product_id(project_name, prod_id)
        next_ver_num = (last_ver["version"] + 1) if last_ver else 1

        vkw = {"version": next_ver_num, "product_id": prod_id}
        if task_id:
            vkw["task_id"] = task_id

        ver_entity = hub.add_new_version(**vkw)
        if author:
            try:
                ver_entity["author"] = author
            except Exception:
                pass
        if comment:
            try:
                ver_entity.attribs["comment"] = comment
            except Exception:
                pass
        hub.commit_changes()
        return ver_entity["id"], next_ver_num

    def _patch_version_attribs(self, project_name, ver_id, prod_type, comment, source):
        """Set the version attributes loaders read (families / comment / source)."""
        attribs = {
            "families": [prod_type],
            "source":   (source or "").replace("\\", "/"),
        }
        if comment:
            attribs["comment"] = comment
        try:
            ayon_api.patch(
                f"projects/{project_name}/versions/{ver_id}", attrib=attribs
            )
        except Exception as e:
            print(f"  [version] Warning: could not set version attribs: {e}")

    def _attach_representation(self, ctx, ver_id, repre_name, file_list,
                               prod_name, prod_type, ver_num, primary=None):
        """
        Register ONE representation covering every file in ``file_list``.

        File paths and the template are stored rootless ('{root[work]}/…')
        so the publish resolves on any workstation or site; ``attrib.path``
        keeps the resolved absolute path for convenience, matching what
        ayon-core's integrator writes.
        """
        file_list = [f for f in file_list if f and os.path.isfile(f)]
        if not file_list:
            print(f"  [repr] WARNING: no files for '{repre_name}' — skipped.")
            return

        primary = primary if (primary and os.path.isfile(primary)) else file_list[0]
        ext     = os.path.splitext(primary)[1].lstrip(".").lower()
        project_name = ctx["project_name"]

        api_files = [
            {
                "id":        uuid.uuid4().hex,
                "name":      os.path.basename(f),
                "path":      self._rootless(f),
                "size":      os.path.getsize(f),
                "hash":      source_file_hash(f),
                "hash_type": "op3",
            }
            for f in file_list
        ]

        folder_entity = ctx.get("folder_entity") or {}
        context = {
            "project":        {"name": project_name, "code": ctx.get("project_code", "")},
            "folder":         {"name": folder_entity.get("name", ""),
                               "path": folder_entity.get("path", "")},
            "product":        {"name": prod_name, "type": prod_type},
            "version":        ver_num,
            "user":           {"name": ctx.get("author") or ""},
            "representation": repre_name,
            "ext":            ext,
        }
        if ctx.get("task_name"):
            context["task"] = {"name": ctx["task_name"]}

        ayon_api.post(
            f"projects/{project_name}/representations",
            versionId=ver_id,
            name=repre_name,
            attrib={
                "ext":      ext,
                "path":     primary.replace("\\", "/"),
                "template": self._rootless(primary),
            },
            data={"context": context},
            files=api_files,
        )
        print(f"  [repr] Attached '{repre_name}' ({len(api_files)} file(s))")

    # ══════════════════════════════════════════════════════════════════
    def _set_status(self, text, color="#aaa"):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 11px;")
        QtWidgets.QApplication.processEvents()


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
