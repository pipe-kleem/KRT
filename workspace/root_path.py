"""SessionWorkspace - Rig Root / relative-path support (Stage 41, mixin)."""
from ._shared import *
from ..utils import relpath


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

    def resolve_path(self, text):
        return relpath.resolve(self.rig_root(), text)

    def relativize_path(self, text):
        return relpath.relativize(self.rig_root(), text)

    # ── UI handlers ──────────────────────────────────────────────────────
    def on_rig_root_edited(self):
        self.set_rig_root(self.edit_rig_root.text(), relativize_existing=True)

    def browse_rig_root(self):
        start = self.rig_root()
        kwargs = {"fm": 3, "caption": "Select Rig Root Folder"}
        if start and os.path.isdir(start):
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

    def relativize_all_paths(self):
        """Shorten every absolute path under the root, everywhere in the UI:
        panel fields, module bubbles, graph node file paths."""
        root = self.rig_root()
        if not root:
            return 0
        changed = 0
        for panel in self._iter_all_panels():
            field = getattr(panel, "field", None)
            if field is not None:
                new = relpath.relativize(root, field.text())
                if new != field.text():
                    field.setText(new); changed += 1
            bl = getattr(panel, "bubble_layout", None)
            if bl is not None:
                for b in range(bl.count()):
                    bub = bl.itemAt(b).widget()
                    fp = getattr(bub, "full_path", None)
                    if fp:
                        new = relpath.relativize(root, fp)
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
                            new = relpath.relativize(root, v)
                            if new != v:
                                setattr(item, attr, new); changed += 1
                if hasattr(gw, "update_attr_editor"):
                    gw.update_attr_editor()
            except Exception:
                traceback.print_exc()
        if changed:
            print(f"[KRT] Rig Root '{root}': {changed} path(s) now shown relative to it.")
        return changed
