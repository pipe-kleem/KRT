"""SessionWorkspace - Initialize Project (Stage 42, mixin).

One button that turns a rig NAME into a working session:
    <all_Rigs>/<rig_name>/{cc_rig,controlShape,guides,model,module,
                           playblasts,rig,scripts,skinCluster}
plus the utils.py template copied into scripts/, the Rig Root set to that
folder, and the default panel stack created with paths already filled in
RELATIVE to the root (scripts/utils.py, model/export.abc, ...).
"""
from ._shared import *
from ..dialogs import ProjectInitDialog
from ..utils.paths import DEFAULT_RIGS_ROOT


class WorkspaceProjectInitMixin(object):

    # Folder layout, taken from the user's existing rigs (parshuram_a) plus
    # guides/ and playblasts/. Order is alphabetical = how Explorer shows it.
    PROJECT_FOLDERS = [
        "cc_rig", "controlShape", "guides", "model", "module",
        "playblasts", "rig", "scripts", "skinCluster",
    ]

    # (panel title, panel type, path relative to the rig root)
    # A path is pre-filled even when the file doesn't exist yet: it is where
    # that step will read from, and where its "Save (New Version)" writes to.
    DEFAULT_PANELS = [
        ("MAYA GLOBAL SCRIPT", "GLOBAL_SCRIPT", ""),
        ("LOAD SCRIPT PANEL",  "SCRIPT",        "scripts/utils.py"),
        ("LOAD MODEL (3D file)", "IMPORT_3D",   "model/export.abc"),
        ("LOAD MODULE",        "MODULE",        None),        # bubble panel
        ("LOAD SKINCLUSTER",   "JSON",          "skinCluster/skinCluster.jSkin"),
        ("CONTROL SHAPES",     "SHAPES",        "controlShape/controlShapes.json"),
        ("PUBLISH PATH",       "PUBLISH",       "rig"),
    ]

    def _krt_package_dir(self):
        """KRT/ itself - this file sits in KRT/workspace/, so go up two."""
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def open_project_init_dialog(self):
        dlg = ProjectInitDialog(
            self.PROJECT_FOLDERS,
            parent=self.main_window,
            default_parent_dir=os.path.dirname(self.rig_root()) if self.rig_root() else DEFAULT_RIGS_ROOT,
        )
        accepted = dlg.exec() if IS_PYSIDE6 else dlg.exec_()
        if not accepted:
            return
        name = dlg.rig_name()
        root = dlg.rig_root()
        if not name or not root:
            cmds.warning("[KRT] Initialize Project: no rig name given.")
            return
        self.initialize_project(
            root, name,
            copy_utils=dlg.chk_utils.isChecked(),
            make_panels=dlg.chk_panels.isChecked(),
            open_folder=dlg.chk_open_folder.isChecked(),
        )

    def initialize_project(self, root, rig_name, copy_utils=True,
                           make_panels=True, open_folder=False):
        """Create the folder structure, seed scripts/utils.py, point the Rig
        Root at it and (optionally) build the default panel stack.

        Nothing here overwrites: an existing folder is left alone, and an
        existing scripts/utils.py is never replaced.
        """
        root = root.replace("\\", "/").rstrip("/")
        created, existing = [], []
        try:
            for folder in [""] + self.PROJECT_FOLDERS:
                path = os.path.join(root, folder).replace("\\", "/") if folder else root
                if os.path.isdir(path):
                    if folder:
                        existing.append(folder)
                else:
                    os.makedirs(path)
                    if folder:
                        created.append(folder)
        except Exception:
            cmds.warning("[KRT] Initialize Project failed while creating folders:\n{}".format(
                traceback.format_exc()))
            return False

        # scripts/utils.py from the bundled template
        if copy_utils:
            dest = os.path.join(root, "scripts", "utils.py").replace("\\", "/")
            src = os.path.join(self._krt_package_dir(), "templates", "utils.py")
            if os.path.isfile(dest):
                cmds.warning("[KRT] scripts/utils.py already exists - left untouched.")
            elif not os.path.isfile(src):
                cmds.warning("[KRT] utils.py template not found at {} - skipped.".format(src))
            else:
                try:
                    shutil.copy2(src, dest)
                    cmds.warning("[KRT] Copied utils.py template -> scripts/utils.py")
                except Exception:
                    cmds.warning("[KRT] Could not copy utils.py template:\n{}".format(
                        traceback.format_exc()))

        # Rig Root: from here on every panel path is stored relative to it.
        self.set_rig_root(root, relativize_existing=False)

        if hasattr(self, "edit_rig_name") and not self.edit_rig_name.text().strip().startswith(rig_name):
            self.edit_rig_name.setText("{}_rig".format(rig_name))

        if make_panels:
            self._create_default_project_panels()
        self._refresh_path_mode_button()

        # Playblast output, if that tab has been built in this session.
        if hasattr(self, "pb_output_field") and not self.pb_output_field.text().strip():
            self.pb_output_field.setText("playblasts")

        cmds.warning("[KRT] Project ready: {}  (created: {} | already there: {})".format(
            root, ", ".join(created) or "none", ", ".join(existing) or "none"))

        if open_folder:
            try:
                os.startfile(root.replace("/", "\\"))
            except Exception:
                pass
        return True

    def _create_default_project_panels(self):
        """Replace the current LOD's panels with the standard stack."""
        container = self.get_current_lod_container()
        if not container:
            cmds.warning("[KRT] No LOD selected - panels not created. Add a LOD, then run Initialize Project again.")
            return
        while container.layout.count():
            item = container.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for title, p_type, rel in self.DEFAULT_PANELS:
            if p_type == "MODULE":
                self.add_module_panel(title)
            else:
                self.add_panel(title, p_type, rel)
        cmds.warning("[KRT] Default panel stack created ({} panels), paths relative to the Rig Root.".format(
            len(self.DEFAULT_PANELS)))
