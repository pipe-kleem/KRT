"""SessionWorkspace - build methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspaceBuildMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    def reset_scene_and_ui(self, wipe_scene=True):
        """wipe_scene=False (Stage 24): reset only the panel buttons'
        text/style, without touching the live Maya scene or the shared
        script namespace - used when a build needs to happen on TOP of
        whatever's already in the scene (see run_full_build's own
        reset_scene parameter) instead of starting from an empty file."""
        if wipe_scene:
            cmds.file(new=True, force=True)
            self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

        for i in range(self.lod_stack.count()):
            container = self.lod_stack.widget(i).panels_container
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if hasattr(panel, 'btn_run'):
                    panel.btn_run.setText(panel_run_label(getattr(panel, 'p_type', '')))
                    panel.btn_run.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold;")
                if getattr(panel, 'p_type', '') == "MODULE":
                    for b in range(panel.bubble_layout.count()): panel.bubble_layout.itemAt(b).widget().reset_style()
                if hasattr(panel, 'refresh_cache_ui'): panel.refresh_cache_ui()
        if wipe_scene:
            cmds.warning("Scene wiped. Memory Namespace Flushed. UI Buttons Reset.")
        else:
            cmds.warning("UI Buttons Reset. (Scene left as-is.)")

    def reset_namespace_only(self):
        self.shared_namespace = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}

    def restore_namespace_preamble(self, target_panel):
        """Rebuild the Python helper namespace after loading a cache, by re-running
        the leading run-of SCRIPT panels that point at an existing file (the util /
        function libraries at the top of the list). Inline-code and later scripts are
        skipped so scene edits already baked into the cache are not re-applied."""
        self.reset_namespace_only()
        container = self.get_current_lod_container()
        if not container: return
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if panel is target_panel: break
            if getattr(panel, 'p_type', '') != "SCRIPT": break
            path = self.resolve_path(panel.field.text()).strip()
            if not path or not os.path.isfile(path): break
            try: self.run_script(path, func_call=panel.func_field.text().strip())
            except Exception: pass

    def refresh_all_cache_ui(self):
        """Re-evaluate the cached (green) state of every step across all LODs.
        Called after opening a JSON or switching sessions so the UI reflects
        the caches that actually exist in the current pipeline's folder."""
        if not hasattr(self, 'lod_stack'):
            return
        for i in range(self.lod_stack.count()):
            page = self.lod_stack.widget(i)
            container = getattr(page, 'panels_container', None)
            if not container:
                continue
            for j in range(container.layout.count()):
                panel = container.layout.itemAt(j).widget()
                if hasattr(panel, 'refresh_cache_ui'):
                    panel.refresh_cache_ui()

    def clear_all_caches_current_pipeline(self):
        """Delete every step cache belonging to the currently open pipeline
        (all LODs). Only touches this JSON's own cache folder - other rigs are
        untouched."""
        removed = 0
        try:
            cdir = self.get_cache_dir()
        except Exception:
            cdir = ""
        try:
            if cdir and os.path.isdir(cdir):
                for fn in os.listdir(cdir):
                    if fn.lower().endswith(".ma"):
                        try:
                            os.remove(os.path.join(cdir, fn)); removed += 1
                        except Exception:
                            pass
        except Exception:
            pass
        self.refresh_all_cache_ui()
        return removed

    def on_delete_all_caches(self):
        """Confirm, then wipe all caches for the current pipeline."""
        name = os.path.basename(self.session_path) if self.session_path else "this unsaved pipeline"
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("Delete all caches")
        box.setText("Delete ALL step caches for {}?".format(name))
        box.setInformativeText(
            "This clears cached scene snapshots for every step across all LODs of\n"
            "the current pipeline. Other rigs are unaffected.")
        box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        box.setDefaultButton(QtWidgets.QMessageBox.No)
        res = box.exec() if IS_PYSIDE6 else box.exec_()
        if res == QtWidgets.QMessageBox.Yes:
            n = self.clear_all_caches_current_pipeline()
            cmds.warning("Deleted {} cache(s) for the current pipeline.".format(n))

    def clear_all_caches_current_lod(self):
        container = self.get_current_lod_container()
        if not container: return 0
        removed = 0
        for i in range(container.layout.count()):
            panel = container.layout.itemAt(i).widget()
            if hasattr(panel, 'get_cache_path'):
                p = panel.get_cache_path()
                try:
                    if p and os.path.isfile(p):
                        os.remove(p); removed += 1
                except Exception: pass
                if hasattr(panel, 'refresh_cache_ui'): panel.refresh_cache_ui()
        return removed

    def remove_caches_from(self, panel, inclusive=True):
        """Delete the cache of `panel` (if inclusive) and every step after it in the
        current LOD, since those downstream snapshots are now stale."""
        container = self.get_current_lod_container()
        if not container: return 0
        idx = -1
        for i in range(container.layout.count()):
            if container.layout.itemAt(i).widget() is panel:
                idx = i; break
        if idx < 0: return 0
        start = idx if inclusive else idx + 1
        removed = 0
        for i in range(start, container.layout.count()):
            p = container.layout.itemAt(i).widget()
            if hasattr(p, 'get_cache_path'):
                cp = p.get_cache_path()
                try:
                    if cp and os.path.isfile(cp):
                        os.remove(cp); removed += 1
                except Exception:
                    pass
                if hasattr(p, 'refresh_cache_ui'): p.refresh_cache_ui()
        return removed

    def _begin_fast_build(self):
        """Put Maya into a fast, non-interactive state for the duration of a build.
        All changes are restored in _end_fast_build."""
        state = {}
        try: state['undo'] = cmds.undoInfo(q=True, state=True)
        except Exception: state['undo'] = None
        try: cmds.undoInfo(state=False)
        except Exception: pass
        try: state['echo'] = cmds.commandEcho(q=True, state=True)
        except Exception: state['echo'] = None
        try: cmds.commandEcho(state=False)
        except Exception: pass
        try: cmds.refresh(suspend=True)
        except Exception: pass
        return state

    def _end_fast_build(self, state):
        try: cmds.refresh(suspend=False)
        except Exception: pass
        try:
            if state.get('undo') is not None: cmds.undoInfo(state=state['undo'])
        except Exception: pass
        try:
            if state.get('echo') is not None: cmds.commandEcho(state=state['echo'])
        except Exception: pass
        try: cmds.refresh(force=True)
        except Exception: pass

    def build_till_panel(self, target_panel):
        # print() as well as cmds.warning: warnings can be suppressed by
        # other tools (scriptEditorInfo), and a silent method looks like a
        # dead button. This line proves the method was entered.
        print("[KRT] build_till_panel: entered")
        cmds.warning("--- Starting Partial Procedural Build ---")
        container = self.get_current_lod_container()
        if not container:
            cmds.warning("[KRT] Build Till Here: no LOD is selected - pick a LOD in the LOD MANAGER first.")
            return
        total_panels = container.layout.count()
        if total_panels == 0:
            cmds.warning("[KRT] Build Till Here: this LOD has no panels.")
            return

        # Locate the target step.
        tgt = -1
        for i in range(total_panels):
            if container.layout.itemAt(i).widget() is target_panel:
                tgt = i; break
        if tgt < 0:
            cmds.warning("[KRT] Build Till Here: that panel is not in the LOD that's currently selected "
                         "(switch to its LOD, then try again).")
            return

        # Find the newest cached step BEFORE the target and resume from it,
        # instead of rebuilding everything from scratch.
        start_k = -1
        for i in range(tgt - 1, -1, -1):
            p = container.layout.itemAt(i).widget()
            if hasattr(p, 'has_cache') and p.has_cache():
                start_k = i; break

        if start_k >= 0:
            cached_panel = container.layout.itemAt(start_k).widget()
            cmds.warning(f"[KRT] Resuming from cache '{cached_panel.title_edit.text()}' "
                         f"(step {start_k + 1}), running through target.")
            if not self.load_cache_only(cached_panel):
                cmds.warning("[KRT] Cache load failed - falling back to full run.")
                start_k = -1
                self.reset_scene_and_ui()
        else:
            self.reset_scene_and_ui()

        begin = start_k + 1  # start_k == -1 -> begin at 0
        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        start_t = time.time()
        timings = []
        progress_ui = None
        fast = None
        # Everything from here is inside try/finally. Previously the
        # setEnabled(False) + dialog construction sat OUTSIDE it, so if
        # either raised, the whole KRT window stayed permanently disabled -
        # every button, including this one, silently did nothing afterwards.
        self.main_window.setEnabled(False)
        try:
            progress_ui = BuildProgressDialog(self, total_steps=total_panels)
            progress_ui.progress_bar.setValue(begin)
            progress_ui.show()
            fast = self._begin_fast_build()
            for i in range(begin, total_panels):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled: break
                panel = container.layout.itemAt(i).widget()
                if panel and hasattr(panel, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {panel.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = panel.execute(progress_ui=progress_ui)
                    if getattr(panel, 'is_active', True):
                        timings.append((time.time() - step_t, panel.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {panel.title_edit.text()}")
                        else:
                            break
                    elif do_cache and getattr(panel, 'is_active', True) and getattr(panel, 'cache_marked', lambda: False)() and hasattr(panel, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {panel.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        panel.cache_now(silent=True)
                    if panel == target_panel:
                        progress_ui.progress_bar.setValue(total_panels)
                        cmds.warning("Partial Build Finished.")
                        break
        except Exception:
            cmds.warning("[KRT] Build Till Here failed:\n{}".format(traceback.format_exc()))
            log_crash("Build Till Here", RuntimeError("build_till_panel"))
        finally:
            if fast is not None:
                self._end_fast_build(fast)
            elapsed = time.time() - start_t
            if progress_ui is not None:
                progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

    def cache_steps_enabled(self):
        chk = getattr(self, 'chk_cache_build', None)
        return chk.isChecked() if chk is not None else True

    def ignore_errors_enabled(self):
        chk = getattr(self, 'chk_ignore_errors', None)
        return chk.isChecked() if chk is not None else False

    def _open_scene_tolerant(self, path):
        """Open a scene, tolerating 'unknown node' warnings and missing plugins.
        Suppresses blocking file prompts so a build never halts on a dialog.
        Returns True if the file opened (even with warnings)."""
        try: prev_prompt = cmds.file(q=True, prompt=True)
        except Exception: prev_prompt = None
        try:
            cmds.file(prompt=False)              # no blocking "unknown node" dialogs
            cmds.file(new=True, force=True)
            cmds.file(path, open=True, force=True, ignoreVersion=True, prompt=False)
            return True
        except Exception:
            # File may still have opened with unknown nodes; honor the ignore toggle.
            cmds.warning(f"[KRT] Scene open reported issues:\n{traceback.format_exc()}")
            return self.ignore_errors_enabled()
        finally:
            try:
                if prev_prompt is not None: cmds.file(prompt=prev_prompt)
            except Exception: pass

    def run_full_build(self, reset_scene=True):
        """reset_scene=False (Stage 24): build this LOD's panel stack on top
        of whatever's currently in the scene, instead of wiping to a new
        file first - used when this LOD is being pulled in as one step of
        an already-in-progress build (a LOD Loader panel's RUN, whether
        clicked directly or reached mid-sequence via Build Till Here),
        rather than a standalone "Build Current LOD" from the toolbar."""
        cmds.warning("--- Starting Procedural Build for Current LOD ---")
        self.reset_scene_and_ui(wipe_scene=reset_scene)
        container = self.get_current_lod_container()
        if not container: return False
        total_panels = container.layout.count()
        if total_panels == 0: return False

        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        if do_cache:
            removed = self.clear_all_caches_current_lod()
            cmds.warning(f"Cleared {removed} old step cache(s). Fresh caches will be written during this build.")

        self.main_window.setEnabled(False)
        progress_ui = BuildProgressDialog(self, total_steps=total_panels)
        progress_ui.show(); start_t = time.time()
        build_ok = True
        timings = []

        fast = self._begin_fast_build()
        try:
            for i in range(total_panels):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    build_ok = False
                    break
                panel = container.layout.itemAt(i).widget()
                if panel and hasattr(panel, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {panel.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = panel.execute(progress_ui=progress_ui)
                    step_elapsed = time.time() - step_t
                    if getattr(panel, 'is_active', True):
                        timings.append((step_elapsed, panel.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {panel.title_edit.text()}")
                            continue
                        build_ok = False
                        break
                    if do_cache and getattr(panel, 'is_active', True) and getattr(panel, 'cache_marked', lambda: False)() and hasattr(panel, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {panel.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        panel.cache_now(silent=True)
        finally:
            self._end_fast_build(fast)
            progress_ui.progress_bar.setValue(total_panels)
            elapsed = time.time() - start_t
            mins, secs = divmod(int(elapsed), 60)
            progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

        return build_ok

    def _report_build_timings(self, timings, elapsed):
        try:
            mins, secs = divmod(int(elapsed), 60)
            cmds.warning(f"[BUILD] Total Execution Time: {mins:02d}:{secs:02d}")
            slowest = sorted(timings, reverse=True)[:5]
            if slowest:
                cmds.warning("[BUILD] Slowest steps:")
                for dur, title in slowest:
                    cmds.warning(f"    {dur:7.2f}s  -  {title}")
        except Exception:
            pass

    def load_cache_only(self, panel):
        """Just open this step's cached scene (no further building)."""
        if not hasattr(panel, 'has_cache') or not panel.has_cache():
            cmds.warning("No cache exists for this step yet.")
            return False
        ok = self._open_scene_tolerant(panel.get_cache_path())
        if not ok:
            cmds.warning(f"Failed to load cache: {panel.title_edit.text()}")
            return False
        try:
            self.restore_namespace_preamble(panel)
        except Exception:
            cmds.warning(f"[KRT] Namespace preamble issue (continuing):\n{traceback.format_exc()}")
        cmds.warning(f"Loaded cached scene: {panel.title_edit.text()}")
        return True

    def build_from_cache(self, panel):
        """Load this step's cache, then continue executing the remaining steps."""
        if not hasattr(panel, 'has_cache') or not panel.has_cache():
            cmds.warning("No cache for this step to build from.")
            return False
        container = self.get_current_lod_container()
        if not container: return False
        idx = -1
        for i in range(container.layout.count()):
            if container.layout.itemAt(i).widget() is panel:
                idx = i; break
        if idx < 0: return False

        cmds.warning(f"--- Building FROM cache: {panel.title_edit.text()} ---")
        if not self.load_cache_only(panel):
            return False

        total = container.layout.count()
        do_cache = self.cache_steps_enabled()
        ignore = self.ignore_errors_enabled()
        self.main_window.setEnabled(False)
        progress_ui = BuildProgressDialog(self, total_steps=total)
        progress_ui.progress_bar.setValue(idx + 1)
        progress_ui.show(); start_t = time.time()
        timings = []; build_ok = True

        fast = self._begin_fast_build()
        try:
            for i in range(idx + 1, total):
                QtWidgets.QApplication.processEvents()
                if progress_ui.is_cancelled:
                    build_ok = False; break
                p = container.layout.itemAt(i).widget()
                if p and hasattr(p, 'execute'):
                    progress_ui.lbl_status.setText(f"Executing: {p.title_edit.text()}")
                    progress_ui.progress_bar.setValue(i)
                    QtWidgets.QApplication.processEvents()
                    step_t = time.time()
                    success = p.execute(progress_ui=progress_ui)
                    if getattr(p, 'is_active', True):
                        timings.append((time.time() - step_t, p.title_edit.text()))
                    QtWidgets.QApplication.processEvents()
                    if not success:
                        if ignore:
                            cmds.warning(f"[KRT] Step failed, continuing (ignore errors ON): {p.title_edit.text()}")
                            continue
                        build_ok = False; break
                    if do_cache and getattr(p, 'is_active', True) and getattr(p, 'cache_marked', lambda: False)() and hasattr(p, 'cache_now'):
                        progress_ui.lbl_status.setText(f"Caching: {p.title_edit.text()}")
                        QtWidgets.QApplication.processEvents()
                        p.cache_now(silent=True)
        finally:
            self._end_fast_build(fast)
            progress_ui.progress_bar.setValue(total)
            elapsed = time.time() - start_t
            progress_ui.close()
            self.main_window.setEnabled(True)
            self._report_build_timings(timings, elapsed)

        return build_ok
