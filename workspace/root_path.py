"""SessionWorkspace - Rig Root / relative-path support (Stage 41, mixin)."""
from ._shared import *
from ..utils import relpath
from ..utils.paths import DEFAULT_RIGS_ROOT


class WorkspaceRootPathMixin(object):
    """One root folder per rig; every path field stores only what's below it.

    Everything funnels through two methods so the rest of KRT never has to
    know whether a field holds a relative or absolute path:
        self.resolve_path(text)     -> absolute path to actually open/run
        self.relativize_path(text)  -> what to SHOW in a field / SAVE to JSON
    Non-path text (inline code, GRAPH:: ids) passes through both unchanged.
    """

    # ── state ────────────────────────────────────────────────────────────
    def rig_root(self):
        field = getattr(self, "edit_rig_root", None)
        return relpath.norm(field.text()) if field is not None else relpath.norm(getattr(self, "_rig_root", ""))

    def set_rig_root(self, root, relativize_existing=True):
        """Set the root. With relativize_existing, every panel/bubble/graph
        path already under the new root is shortened on screen right away."""
        root = relpath.norm(root)
        self._rig_root = root
        field = getattr(self, "edit_rig_root", None)
        if field is not None and field.text() != root:
            field.blockSignals(True); field.setText(root); field.blockSignals(False)
        if root and relativize_existing:
            self.relativize_all_paths()
        self._refresh_path_mode_button()

    def default_browse_dir(self):
        """Where a file/folder browser should open when it has nothing better.

        Rig Root first (you are almost always picking a file inside the rig
        you're working on), then the studio-wide rigs folder. Never an empty
        string if that folder exists - an empty 'dir' makes Maya reopen
        wherever it happened to be last, anywhere on the machine."""
        root = self.rig_root()
        if root and os.path.isdir(root):
            return root
        if os.path.isdir(DEFAULT_RIGS_ROOT):
            return DEFAULT_RIGS_ROOT
        return ""

    def resolve_path(self, text):
        return relpath.resolve(self.rig_root(), text)

    def relativize_path(self, text):
        return relpath.relativize(self.rig_root(), text)

    # ── UI handlers ──────────────────────────────────────────────────────
    def on_rig_root_edited(self):
        self.set_rig_root(self.edit_rig_root.text(), relativize_existing=True)

    def browse_rig_root(self):
        start = self.default_browse_dir()
        kwargs = {"fm": 3, "caption": "Select Rig Root Folder"}
        if start:
            kwargs["dir"] = start
        res = cmds.fileDialog2(**kwargs)
        if res:
            self.set_rig_root(res[0], relativize_existing=True)

    def infer_rig_root_from_panels(self):
        """Legacy JSON (no root_path): use the active PUBLISH panel's folder
        as the root, since that is where the rig's files live anyway."""
        for panel in self._iter_all_panels():
            if getattr(panel, "p_type", "") == "PUBLISH" and getattr(panel, "is_active", True):
                p = relpath.norm(panel.field.text())
                if p and relpath.is_absolute(p):
                    return p
        return ""

    # ── bulk relativize ──────────────────────────────────────────────────
    def _iter_all_panels(self):
        stack = getattr(self, "lod_stack", None)
        if stack is None:
            return
        for i in range(stack.count()):
            page = stack.widget(i)
            container = getattr(page, "panels_container", None)
            if container is None:
                continue
            for j in range(container.layout.count()):
                w = container.layout.itemAt(j).widget()
                if w is not None:
                    yield w

    def _convert_all_paths(self, convert):
        """Apply `convert` (relativize_path or resolve_path) to every path in
        the UI: panel fields, module bubbles, graph node file paths.
        Non-path text (inline script code, GRAPH:: ids) is untouched by both
        conversions, so this can run blindly over every field."""
        changed = 0
        for panel in self._iter_all_panels():
            field = getattr(panel, "field", None)
            if field is not None:
                new = convert(field.text())
                if new != field.text():
                    field.setText(new); changed += 1
            bl = getattr(panel, "bubble_layout", None)
            if bl is not None:
                for b in range(bl.count()):
                    bub = bl.itemAt(b).widget()
                    fp = getattr(bub, "full_path", None)
                    if fp:
                        new = convert(fp)
                        if new != fp:
                            bub.full_path = new; changed += 1
        gw = getattr(self, "graph_widget", None)
        if gw is not None:
            try:
                from ..graph import RigNode
                for item in gw.graph_view.scene.items():
                    if not isinstance(item, RigNode):
                        continue
                    for attr in ("custom_sgt_path", "plebe_template_path", "control_shapes_library"):
                        v = getattr(item, attr, None)
                        if v:
                            new = convert(v)
                            if new != v:
                                setattr(item, attr, new); changed += 1
                if hasattr(gw, "update_attr_editor"):
                    gw.update_attr_editor()
            except Exception:
                traceback.print_exc()
        return changed

    def relativize_all_paths(self):
        """Shorten every absolute path that lives under the Rig Root."""
        root = self.rig_root()
        if not root:
            cmds.warning("[KRT] Set a Rig Root first - there is nothing to make paths relative to.")
            return 0
        changed = self._convert_all_paths(self.relativize_path)
        print(f"[KRT] Rig Root '{root}': {changed} path(s) now shown relative to it.")
        self._refresh_path_mode_button()
        return changed

    def absolutize_all_paths(self):
        """Expand every relative path back to its full path under the root.
        Paths that were already absolute (outside the root) are untouched."""
        root = self.rig_root()
        if not root:
            cmds.warning("[KRT] Set a Rig Root first - a relative path needs a root to expand against.")
            return 0
        changed = self._convert_all_paths(self.resolve_path)
        print(f"[KRT] {changed} path(s) expanded to full paths under '{root}'.")
        self._refresh_path_mode_button()
        return changed

    # ── relative/absolute toggle ─────────────────────────────────────────
    def paths_are_relative(self):
        """True when the fields are currently SHOWING relative paths.

        Decided by what is actually in the fields rather than by a stored
        flag, so the button stays honest after a JSON load, an Initialize
        Project, or the user typing a path in by hand.
        """
        for panel in self._iter_all_panels():
            field = getattr(panel, "field", None)
            if field is not None and relpath.looks_like_relative_path(field.text()):
                return True
            bl = getattr(panel, "bubble_layout", None)
            if bl is not None:
                for b in range(bl.count()):
                    fp = getattr(bl.itemAt(b).widget(), "full_path", "") or ""
                    if not fp.startswith("GRAPH::") and relpath.looks_like_relative_path(fp):
                        return True
        return False

    def toggle_path_mode(self):
        """The Rig Root row's ⇄ button: relative <-> absolute, in place."""
        if self.paths_are_relative():
            self.absolutize_all_paths()
        else:
            self.relativize_all_paths()

    def _refresh_path_mode_button(self):
        """Label the button with the state the paths are in NOW, so it reads
        like a switch rather than a command with an unknown effect."""
        btn = getattr(self, "btn_path_mode", None)
        if btn is None:
            return
        if self.paths_are_relative():
            btn.setText("⇄ Paths: Relative")
            btn.setToolTip(
                "Paths are shown relative to the Rig Root (scripts/utils.py).\n"
                "Click to show full paths instead.\n\n"
                "Display only - the pipeline JSON always saves paths relative to the\n"
                "Rig Root, so it keeps working when the rig folder moves.")
        else:
            btn.setText("⇄ Paths: Absolute")
            btn.setToolTip(
                "Paths are shown in full (P:/.../rig/scripts/utils.py).\n"
                "Click to shorten the ones under the Rig Root.\n\n"
                "Display only - the pipeline JSON always saves paths relative to the\n"
                "Rig Root, so it keeps working when the rig folder moves.")
