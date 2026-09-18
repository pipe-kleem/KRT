"""Auto-split from widgets.py."""
from ._shared import *


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
