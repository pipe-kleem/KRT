"""Auto-split from dialogs.py."""
from ._shared import *


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
                # Stage 47: panel fields hold RELATIVE paths now (PUBLISH is
                # often just "."), so resolve before deriving folders from it.
                p = self.workspace.resolve_path(panel.field.text()).strip().replace("\\", "/").rstrip("/")
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
                    p = self.workspace.resolve_path(panel.field.text()).strip().replace("\\", "/")
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
                    # Match on the ABSOLUTE path (the field may hold a
                    # relative one), then write back through relativize_path
                    # so the field keeps the tab's current display style.
                    cur = self.workspace.resolve_path(panel.field.text()).strip().replace("\\", "/")
                    if cur.lower().startswith(old_norm):
                        panel.field.setText(
                            self.workspace.relativize_path(new_norm + cur[len(old_norm):]))
                        replaced += 1
                elif pt == "MODULE":
                    bl = getattr(panel, 'bubble_layout', None)
                    if bl:
                        for b in range(bl.count()):
                            bubble = bl.itemAt(b).widget()
                            if bubble:
                                raw = getattr(bubble, 'full_path', '')
                                bp = self.workspace.resolve_path(raw).replace("\\", "/")
                                if bp.lower().startswith(old_norm):
                                    bubble.full_path = self.workspace.relativize_path(
                                        new_norm + bp[len(old_norm):])
                                    bubble.btn_text.setText(os.path.basename(bubble.full_path))
                                    replaced += 1
        cmds.warning(f"[CreateFolders] Replaced {replaced} path(s): {old_prefix} → {new_prefix}")
        self.txt_log.addItem(f"Replaced {replaced} path(s).")


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
