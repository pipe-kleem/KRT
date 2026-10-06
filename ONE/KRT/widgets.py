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
import importlib.util
from .compat import QtWidgets, QtCore, QtGui, IS_PYSIDE6
from .utils import export_control_shapes, import_control_shapes, get_versioned_path
from .dialogs import BuildProgressDialog

# Per-type accent colours so each panel is visually identifiable at a glance.
# Applied as a coloured left border stripe and the title text colour.
PANEL_TYPE_ACCENTS = {
    "SCRIPT":    "#4fc3f7",   # light blue  - Python / MEL scripts
    "MA":        "#ffb74d",   # orange      - Maya .ma files
    "IMPORT_3D": "#ba68c8",   # purple      - imported 3D models
    "JSON":      "#81c784",   # green       - skin clusters
    "SHAPES":    "#f06292",   # pink        - control shapes
    "PUBLISH":   "#e57373",   # red         - publish path
    "MODULE":    "#2bb5a8",   # teal        - module bubble panels
}

def type_accent(p_type):
    return PANEL_TYPE_ACCENTS.get(p_type, "#2bb5a8")

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

class ModuleBubble(QtWidgets.QFrame):
    closed = QtCore.Signal(object)
    execute_req = QtCore.Signal(object) 

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
        self.btn_text.setToolTip("Click to execute only this module instantly")
        self.btn_text.clicked.connect(lambda: self.execute_req.emit(self))

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setFlat(True)
        self.close_btn.setToolTip("Remove this module")
        self.close_btn.setStyleSheet("color: transparent; font-weight: bold; border: none;") 
        self.close_btn.clicked.connect(lambda: self.closed.emit(self))
        
        layout.addWidget(self.checkbox)
        layout.addWidget(self.btn_text)
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
        super(ModuleBubble, self).enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.setStyleSheet("color: transparent; border: none; background: transparent;")
        super(ModuleBubble, self).leaveEvent(event)

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


class SortablePanel(CacheMixin, QtWidgets.QFrame):
    def __init__(self, title, p_type, default_val, workspace):
        super(SortablePanel, self).__init__()
        self.p_type = p_type
        self.workspace = workspace
        self.is_active = True
        self.last_error_msg = ""
        self.bg_color = "#252526"
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
        
        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox)
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
        btn_dots = QtWidgets.QPushButton("...")
        btn_dots.setFixedWidth(30)
        btn_dots.setToolTip("More Options, Adds, Copy & Paste")
        
        btn_txt = "RUN" if p_type == "SCRIPT" else "VALIDATE" if p_type == "PUBLISH" else "LOAD"
        self.btn_run = QtWidgets.QPushButton(btn_txt)
        self.btn_run.setFixedWidth(130) 
        self.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
        
        body_layout.addLayout(ctrl_layout)
        body_layout.addWidget(self.field)
        body_layout.addWidget(btn_dots)

        if self.p_type == "SCRIPT":
            self.func_field = QtWidgets.QLineEdit()
            self.func_field.setPlaceholderText("Function (e.g. utils())")
            self.func_field.setFixedWidth(130)
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
            
        if p_type == "SHAPES":
            shape_ext_layout = QtWidgets.QHBoxLayout()
            shape_ext_layout.setContentsMargins(25, 0, 0, 0)
            shape_ext_layout.addWidget(QtWidgets.QLabel("Pattern:"))
            self.pattern_field = QtWidgets.QLineEdit("*ctl")
            shape_ext_layout.addWidget(self.pattern_field)
            main_layout.addLayout(shape_ext_layout)

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
            om.MGlobal.displayError("Provide a valid path to save.")
            return
            
        save_path = current_path
        if not overwrite:
            save_path = get_versioned_path(current_path, get_latest=False)
            
        if self.p_type == "JSON":
            try:
                from mgear.core import skin
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
                try:
                    skin.exportSkin(save_path)
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

    def _add_new_panel(self, title, p_type, default_val, offset):
        container = self.workspace.get_current_lod_container()
        if not container: return
        idx = container.layout.indexOf(self) + offset
        if p_type == "MODULE":
            self.workspace.add_module_panel(title, index=idx)
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
            if self.p_type == "JSON": data["meshes"] = self.mesh_field.text()
            if self.p_type == "SCRIPT": data["func_call"] = self.func_field.text()
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

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
            if p_type == "JSON" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type == "SCRIPT" and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
        cmds.warning(f"Panel pasted.")

    def on_btn_run_clicked(self):
        if self.btn_run.text() == "SHOW ERROR":
            self.show_error_popup()
        else:
            self.execute(None)

    def _normal_run_text(self):
        return "RUN" if self.p_type == "SCRIPT" else "VALIDATE" if self.p_type == "PUBLISH" else "LOAD"

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

    def get_start_dir(self):
        current_path = self.field.text().strip()
        if os.path.isdir(current_path): return current_path
        elif os.path.isfile(current_path): return os.path.dirname(current_path)
        return ""

    def show_context_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: white; border: 1px solid #2bb5a8;")
        
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()

        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")
        
        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Maya .MA")] = ("CUSTOM .MA FILE", "MA", offset)
            actions_map[m.addAction("Add Import 3D")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            
        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
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

        if self.p_type == "SCRIPT":
            a_vs = menu.addAction("📝 Edit code in VS Code")
            a_load = menu.addAction("📂 Load any other file")
            a_comp = menu.addAction("⚖ Compare older script in VS Code")
        elif self.p_type == "MA":
            a_load = menu.addAction("📂 Load Maya file")
            a_rem = menu.addAction("❌ Remove file")
        elif self.p_type == "IMPORT_3D":
            a_load = menu.addAction("📂 Load 3D file")
            a_rem = menu.addAction("❌ Remove file")
        elif self.p_type == "JSON":
            a_load = menu.addAction("📂 Load new file")
            a_rem = menu.addAction("❌ Remove file")
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
        elif self.p_type == "PUBLISH":
            a_load = menu.addAction("📂 Load new path")
            a_rem = menu.addAction("❌ Remove path")

        action = menu.exec(QtGui.QCursor.pos()) if IS_PYSIDE6 else menu.exec_(QtGui.QCursor.pos())
        
        if not action: return
        
        if action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
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
                has_code = shutil.which("code") or shutil.which("code.cmd")
                if not has_code:
                    om.MGlobal.displayError("VS Code is not in your system PATH. Please restart Maya or reinstall VS Code.")
                else:
                    try: subprocess.Popen(f'code "{path}"', shell=True)
                    except Exception as e: om.MGlobal.displayError(f"Failed to launch VS Code: {e}")
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

    def browse_file(self):
        kwargs = {'fm': 1}
        # "All Files" is listed first so the dialog shows every file type by
        # default; the type-specific filters remain available as options.
        if self.p_type == "SCRIPT": kwargs['ff'] = "All Files (*.*);;Scripts (*.py *.mel);;Python (*.py);;MEL (*.mel)"
        elif self.p_type == "MA": kwargs['ff'] = "All Files (*.*);;Maya Files (*.ma *.mb)"
        elif self.p_type in ["JSON", "SHAPES"]: kwargs['ff'] = "All Files (*.*);;JSON (*.jSkin *.json)"
        elif self.p_type == "IMPORT_3D": kwargs['ff'] = "All Files (*.*);;3D Files (*.fbx *.obj *.abc *.ma *.mb);;FBX (*.fbx);;OBJ (*.obj);;Alembic (*.abc);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        elif self.p_type == "PUBLISH": kwargs['fm'] = 3; kwargs['caption'] = "Select Publish Directory"
        else: return
        
        sd = self.get_start_dir()
        if os.path.exists(sd): kwargs['dir'] = sd
        res = cmds.fileDialog2(**kwargs)
        if res: self.field.setText(res[0])

    def execute(self, progress_ui=None):
        if not self.is_active: return True
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
                elif self.p_type == "MA": 
                    success, error_msg = self.workspace.import_ma_logic(self.field.text())
                elif self.p_type == "IMPORT_3D": 
                    success, error_msg = self.workspace.import_3d_logic(self.field.text())
                elif self.p_type == "JSON": 
                    success, error_msg = self.workspace.load_skin_cluster_logic(self.field.text(), self.mesh_field.text())
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
                elif self.p_type == "PUBLISH":
                    if os.path.exists(self.field.text()):
                        success = True
                        cmds.warning("Publish Path Validated.")
                    else:
                        success = False
                        error_msg = "Publish Path does not exist!"
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
                btn_txt = "RUN" if self.p_type == "SCRIPT" else "VALIDATE" if self.p_type == "PUBLISH" else "LOAD"
                self.btn_run.setText(btn_txt)
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
        self.bg_color = "#252526"
        self.accent = type_accent("MODULE")
        self.uuid = uuid.uuid4().hex

        self.update_style()
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        header_layout = QtWidgets.QHBoxLayout()
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(self.toggle_active)
        
        self.title_edit = QtWidgets.QLineEdit(title)
        self.title_edit.setToolTip("Double-click to rename (Click and Drag here to reorder)")
        self.title_edit.setStyleSheet(f"background: transparent; border: none; font-weight: bold; color: {self.accent}; font-size: 13px;")
        self.title_edit.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.title_edit.editingFinished.connect(self.finish_editing_title)

        header_layout.addWidget(self.checkbox); header_layout.addWidget(self.title_edit); header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        body_layout = QtWidgets.QHBoxLayout()
        ctrl_layout = QtWidgets.QVBoxLayout()
        ctrl_layout.setSpacing(0)
        self.btn_del = QtWidgets.QPushButton("×"); self.btn_del.setFixedSize(20, 20)
        self.btn_del.setStyleSheet("color: #2bb5a8; font-weight: bold;")
        ctrl_layout.addWidget(self.btn_del)
        
        self.bubble_area = QtWidgets.QWidget()
        self.bubble_layout = QtWidgets.QHBoxLayout(self.bubble_area)
        self.bubble_layout.setAlignment(QtCore.Qt.AlignLeft)
        self.bubble_layout.setContentsMargins(0, 0, 0, 0)
        
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
        else:
            self.workspace.add_panel(title, p_type, default_val, index=idx)

    def copy_panel(self):
        data = {"type": self.p_type, "title": self.title_edit.text(), "active": self.is_active, "bg_color": self.bg_color}
        if self.p_type == "MODULE":
            mods = [{"path": self.bubble_layout.itemAt(b).widget().full_path, "active": self.bubble_layout.itemAt(b).widget().is_active} for b in range(self.bubble_layout.count())]
            data["modules"] = mods
        self.workspace.main_window.clipboard_panel_data = data
        cmds.warning(f"Panel '{self.title_edit.text()}' copied to clipboard.")

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
            if p_type == "JSON" and data.get("meshes"): pan.mesh_field.setText(data.get("meshes"))
            if p_type == "SHAPES" and data.get("pattern"): pan.pattern_field.setText(data.get("pattern"))
            if p_type == "SCRIPT" and data.get("func_call"): pan.func_field.setText(data.get("func_call"))
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
        
        a_color = menu.addAction("🎨 Change Panel Color")
        menu.addSeparator()
        
        add_above_menu = menu.addMenu("➕ Add Panel (Above)")
        add_below_menu = menu.addMenu("➕ Add Panel (Below)")
        
        actions_map = {}
        def _populate(m, offset):
            actions_map[m.addAction("Add Python/MEL Script")] = ("CUSTOM SCRIPT", "SCRIPT", offset)
            actions_map[m.addAction("Add Maya .MA")] = ("CUSTOM .MA FILE", "MA", offset)
            actions_map[m.addAction("Add Import 3D")] = ("IMPORT 3D MODEL", "IMPORT_3D", offset)
            actions_map[m.addAction("Add Module Bubbles")] = ("LOAD MODULE SCRIPTS", "MODULE", offset)
            actions_map[m.addAction("Add Skin JSON")] = ("CUSTOM SKIN JSON", "JSON", offset)
            actions_map[m.addAction("Add Control Shapes")] = ("CONTROL SHAPES", "SHAPES", offset)
            actions_map[m.addAction("Add Publish Path")] = ("PUBLISH PATH", "PUBLISH", offset)
            
        _populate(add_above_menu, 0)
        _populate(add_below_menu, 1)
        menu.addSeparator()

        a_copy = menu.addAction("📄 Copy Panel")
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
        
        if action == a_color: self.change_color()
        elif action in actions_map:
            p_title, p_t, offset = actions_map[action]
            self._add_new_panel(p_title, p_t, "", offset)
        elif action == a_copy: self.copy_panel()
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
                self.bubble_layout.addWidget(bubble)
                
            elif action == a_graph:
                selected_items = self.workspace.rig_list.selectedItems()
                if not selected_items:
                    cmds.warning("No modules selected in the left sidebar Graph Editor!")
                    return
                selected_uuids = [item.data(QtCore.Qt.UserRole) for item in selected_items]
                
                from .graph import RigNode 
                nodes = [item for item in self.workspace.graph_widget.graph_view.scene.items() 
                         if isinstance(item, RigNode) and item.uuid in selected_uuids]
                
                for node in reversed(nodes):
                    v_path = f"GRAPH::{node.uuid}"
                    v_name = node.display_title
                    bubble = ModuleBubble(v_name, v_path, is_active=is_active)
                    bubble.closed.connect(self.remove_bubble)
                    bubble.execute_req.connect(self.execute_single_module)
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
            self.bubble_layout.addWidget(bubble)

    def remove_bubble(self, widget):
        self.bubble_layout.removeWidget(widget)
        widget.deleteLater()

    def execute_single_module(self, bubble):
        if not self.is_active or not bubble.is_active: return True, ""
        path = bubble.full_path
        success = False
        error_msg = ""
        QtWidgets.QApplication.processEvents()
        
        try:
            if path.startswith("GRAPH::"):
                node_uuid = path.split("::")[1]
                node = self.workspace.graph_widget.get_node_by_uuid(node_uuid)
                if not node:
                    return False, f"Graph node with UUID {node_uuid} not found."

                mod_name = node.module_type
                side = node.side
                mod_path = self.workspace.graph_widget.graph_view.modules_path
                file_path = os.path.join(mod_path, f"{mod_name}.py")
                
                if not os.path.exists(file_path):
                    return False, f"Module file not found: {file_path}"
                    
                spec = importlib.util.spec_from_file_location(mod_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "build_guides"): module.build_guides(side)
                else: cmds.warning(f"Module '{mod_name}' missing 'build_guides(side)'.")
                
                json_path = self.workspace.graph_widget.path_field.text()
                if os.path.exists(json_path):
                    with open(json_path, 'r') as f:
                        guide_data = json.load(f)
                    for guide_name, pos in guide_data.items():
                        if cmds.objExists(guide_name):
                            cmds.xform(guide_name, translation=pos, worldSpace=True)
                
                if hasattr(module, "build_rig"):
                    module.build_rig(side)
                    success = True
                else:
                    success = False
                    error_msg = f"Module '{mod_name}' missing 'build_rig(side)'."

            elif path.endswith(".py"): 
                success, error_msg = self.workspace.run_script(path)
            elif path.endswith(".sgt"): 
                success, error_msg = self.workspace.run_mgear_sgt(path)
        except Exception as e:
            error_msg = traceback.format_exc()
            success = False

        if success: bubble.set_success()
        else: bubble.set_error()
        return success, error_msg

    def execute(self, progress_ui=None):
        if not self.is_active: return True
        all_success = True
        error_msgs = []
        
        self.btn_run.setText("RUNNING...")
        
        local_ui = False
        if progress_ui is None:
            self.workspace.main_window.setEnabled(False)
            progress_ui = BuildProgressDialog(self.workspace, total_steps=self.bubble_layout.count())
            progress_ui.lbl_status.setText(f"Executing: {self.title_edit.text()}")
            progress_ui.show()
            local_ui = True
            
        QtWidgets.QApplication.processEvents() 
        start_t = time.time()
        
        try:
            for i in range(self.bubble_layout.count()):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    all_success = False
                    error_msgs.append("Cancelled by user.")
                    break
                    
                bubble = self.bubble_layout.itemAt(i).widget()
                if bubble.is_active:
                    if local_ui:
                        progress_ui.lbl_status.setText(f"Executing: {bubble.text}")
                        progress_ui.progress_bar.setValue(i)
                        
                    success, err = self.execute_single_module(bubble)
                    if not success:
                        all_success = False
                        error_msgs.append(f"[{bubble.text}]:\n{err}")
                        break 
        finally:
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