"""Auto-split from dialogs.py."""
from ._shared import *
from .path_tools import CreateFolderStructureDialog, collect_json_file_paths, replace_json_file_paths


from ayon_api.entity_hub import EntityHub
import ayon_api


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

    # Stage 46 - the reviewable. product_type "review" is what ayon-maya and
    # ayon-core use for QC media; the representation also carries the
    # "review" tag, which is what marks it reviewable for downstream
    # integrations. On top of that the file is uploaded through
    # ayon_api.upload_reviewable() so it plays in the AYON web player.
    DEFAULT_REVIEW_PRODUCT = "reviewRigging"
    DEFAULT_REVIEW_TYPE    = "review"
    # AYON's player wants H.264 MP4 (yuv420p); PNG/JPEG for stills. It does
    # NOT transcode on upload - an unsupported file shows as unplayable.
    REVIEW_MOVIE_EXTS = (".mp4", ".mov", ".avi")
    REVIEW_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

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

        # 3 — the reviewable (QC movie or a still), from the Playblast tab
        self.chk_publish_review = QtWidgets.QCheckBox("Publish Review (QC):")
        self.chk_publish_review.setChecked(False)
        self.chk_publish_review.setToolTip(
            "product_type: review  —  publishes QC media and uploads it as a\n"
            "reviewable, so it plays in the AYON web player."
        )
        self.cmb_prod_review = QtWidgets.QComboBox()
        self.cmb_prod_review.setEditable(True)
        self.cmb_prod_review.setCurrentText(self.DEFAULT_REVIEW_PRODUCT)

        prod_form.addRow(self.chk_publish_rig,  self.cmb_prod_rig)
        prod_form.addRow(self.chk_publish_work, self.cmb_prod_work)
        prod_form.addRow(self.chk_publish_review, self.cmb_prod_review)

        review_row = QtWidgets.QHBoxLayout()
        self.cmb_review_kind = QtWidgets.QComboBox()
        self.cmb_review_kind.addItems(["QC Movie (playblast)", "Image (still)"])
        self.cmb_review_kind.setFixedWidth(170)
        self.cmb_review_kind.currentIndexChanged.connect(self._on_review_kind_changed)
        review_row.addWidget(self.cmb_review_kind)

        self.edit_review_path = QtWidgets.QLineEdit()
        self.edit_review_path.setPlaceholderText(
            "QC media to publish - leave empty to use the newest file in the rig's playblasts/ folder")
        review_row.addWidget(self.edit_review_path, 1)

        btn_review_browse = QtWidgets.QPushButton("📁")
        btn_review_browse.setFixedWidth(34)
        btn_review_browse.clicked.connect(self._browse_review_media)
        review_row.addWidget(btn_review_browse)

        self.btn_make_qc = QtWidgets.QPushButton("🎬 Make QC Now")
        self.btn_make_qc.setToolTip(
            "Run a playblast with the Playblast tab's current settings and use\n"
            "the result as the reviewable.")
        self.btn_make_qc.clicked.connect(self._make_qc_now)
        review_row.addWidget(self.btn_make_qc)
        prod_form.addRow("", review_row)

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

    # ── Reviewable helpers ────────────────────────────────────────────
    def _review_is_movie(self):
        return self.cmb_review_kind.currentIndex() == 0

    def _on_review_kind_changed(self, _idx):
        # "Make QC Now" produces a movie - meaningless in image mode.
        self.btn_make_qc.setEnabled(self._review_is_movie())

    def _browse_review_media(self):
        if self._review_is_movie():
            ff = "Movies (*.mp4 *.mov *.avi);;All Files (*.*)"
        else:
            ff = "Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)"
        start = self.edit_review_path.text().strip()
        start = os.path.dirname(start) if start else self.workspace.get_playblast_dir()
        kwargs = {"fm": 1, "ff": ff, "caption": "Choose QC media to publish"}
        if start and os.path.isdir(start):
            kwargs["dir"] = start
        res = cmds.fileDialog2(**kwargs)
        if res:
            self.edit_review_path.setText(res[0].replace("\\", "/"))

    def _make_qc_now(self):
        """Run a playblast from the Playblast tab's settings, right here."""
        self._set_status("Creating QC playblast …", color="#f4a261")
        QtWidgets.QApplication.processEvents()
        try:
            ok, err, out_path = self.workspace.pb_run_playblast()
        except Exception:
            traceback.print_exc()
            self._set_status("QC playblast failed - see Script Editor.", color="#e76f51")
            return
        if not ok or not out_path:
            cmds.warning("[AYON PUBLISH] QC playblast failed: {}".format(err))
            self._set_status("QC playblast failed - see Script Editor.", color="#e76f51")
            return
        self.edit_review_path.setText(out_path.replace("\\", "/"))
        self.chk_publish_review.setChecked(True)
        self._set_status("QC playblast ready: {}".format(os.path.basename(out_path)), color="#2bb5a8")

    def _resolve_review_media(self):
        """The file to publish as the reviewable: whatever is typed, else the
        newest matching file in the rig's playblasts/ folder."""
        typed = self.edit_review_path.text().strip().replace("\\", "/")
        if typed:
            return typed if os.path.isfile(typed) else ""
        exts = self.REVIEW_MOVIE_EXTS if self._review_is_movie() else self.REVIEW_IMAGE_EXTS
        d = self.workspace.get_playblast_dir()
        if not d or not os.path.isdir(d):
            return ""
        cands = [os.path.join(d, f).replace("\\", "/") for f in os.listdir(d)
                 if f.lower().endswith(exts)]
        if not cands:
            return ""
        return max(cands, key=os.path.getmtime)

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
          Step 7  Publish reviewRigging    — copy the QC movie/still and
                  upload it as an AYON reviewable
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

        do_rig    = self.chk_publish_rig.isChecked()
        do_work   = self.chk_publish_work.isChecked()
        do_review = self.chk_publish_review.isChecked()
        prod_review = self.cmb_prod_review.currentText().strip() or self.DEFAULT_REVIEW_PRODUCT
        if not (do_rig or do_work or do_review):
            cmds.warning("[AYON PUBLISH] No products selected for publishing.")
            self._set_status("⚠️ Nothing selected to publish.", color="#f4a261")
            return

        # Resolve the QC media BEFORE anything is written to the server, so a
        # missing file stops the publish instead of leaving a half-done one.
        review_media = ""
        if do_review:
            review_media = self._resolve_review_media()
            if not review_media:
                cmds.warning("[AYON PUBLISH] Review is ticked but no QC media was found - "
                             "pick a file, or use 'Make QC Now'.")
                self._set_status("⚠️ No QC media for the review product.", color="#f4a261")
                return
            print(f"[AYON PUBLISH] Review  : {review_media}")

        self.btn_publish.setEnabled(False)
        self.progress_bar.setRange(0, 6)
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

        # ── Step 7: Publish the reviewable ─────────────────────────────
        if do_review:
            self._set_status(f"Publishing {prod_review} (QC) …")
            QtWidgets.QApplication.processEvents()
            results[prod_review] = self._publish_review(ctx, prod_review, review_media)
        self.progress_bar.setValue(6)
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
    # ══════════════════════════════════════════════════════════════════
    # Product 3 — the reviewable (QC movie or still)
    # ══════════════════════════════════════════════════════════════════
    def _publish_review(self, ctx, prod_name, media_path):
        """Publish QC media as a 'review' product and upload it as an AYON
        reviewable. Returns the version number, or None on failure.

        Two separate things happen here, and both matter:
          * the file is copied to the publish path and registered as a
            representation tagged "review" - that is the pipeline record
            other integrations read;
          * it is ALSO uploaded via ayon_api.upload_reviewable(), which is
            what makes it play in the AYON web player. The server does not
            transcode, so an unsupported codec uploads but shows as
            unplayable - H.264 MP4 (yuv420p) is the safe choice, which is
            what the Playblast tab produces when FFmpeg is available.
        """
        print(f"\n[AYON PUBLISH] → {prod_name} ({self.DEFAULT_REVIEW_TYPE})")
        if not media_path or not os.path.isfile(media_path):
            print(f"  [warn] QC media not found: {media_path}")
            return None

        project_name = ctx["project_name"]
        ext = os.path.splitext(media_path)[1].lstrip(".").lower()
        try:
            hub = EntityHub(project_name)
            prod_id = self._get_or_create_product(
                hub, project_name, ctx["folder_id"], prod_name, self.DEFAULT_REVIEW_TYPE
            )
            ver_id, ver_num = self._create_version(
                hub, project_name, prod_id, ctx["task_id"], ctx["comment"], ctx["author"]
            )

            server_dir = self._build_server_path(
                ctx, self.DEFAULT_REVIEW_TYPE, prod_name, ver_num
            )
            dest = self._copy_file(media_path, server_dir)

            self._patch_version_attribs(
                project_name, ver_id, self.DEFAULT_REVIEW_TYPE, ctx["comment"], media_path
            )
            self._attach_representation(
                ctx, ver_id, ext, [dest], prod_name,
                self.DEFAULT_REVIEW_TYPE, ver_num, tags=["review"]
            )

            # Upload for the web player. Guarded: older ayon_api builds have
            # no upload_reviewable(), and a failed upload must not undo a
            # publish that has already been registered.
            if hasattr(ayon_api, "upload_reviewable"):
                try:
                    label = f"{prod_name} v{ver_num:03d}"
                    ayon_api.upload_reviewable(project_name, ver_id, dest, label=label)
                    print(f"  [review] Uploaded reviewable: {os.path.basename(dest)}")
                except Exception:
                    traceback.print_exc()
                    cmds.warning("[AYON PUBLISH] Published, but the reviewable upload failed - "
                                 "the file can still be dropped onto the version in the web UI.")
            else:
                cmds.warning("[AYON PUBLISH] This ayon_api has no upload_reviewable() - the review "
                             "product was published, but not uploaded to the web player.")

            print(f"  [ok] {prod_name} → v{ver_num:03d}")
            return ver_num
        except Exception:
            traceback.print_exc()
            return None

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
                    candidate = self.workspace.resolve_path(panel.field.text()).strip()
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
                               prod_name, prod_type, ver_num, primary=None,
                               tags=None):
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
            tags=list(tags or []),
        )
        print(f"  [repr] Attached '{repre_name}' ({len(api_files)} file(s))")

    # ══════════════════════════════════════════════════════════════════
    def _set_status(self, text, color="#aaa"):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 11px;")
        QtWidgets.QApplication.processEvents()
