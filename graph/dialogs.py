"""Auto-split from graph.py."""
from ._shared import *


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
