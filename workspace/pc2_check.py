"""CHECK PC2 IN BLENDER button logic (workspace side). The work is in PanelScripts/pc2_check.py."""
from ._shared import *


class WorkspacePc2Mixin(object):

    def _find_blend_panels(self):
        """Every 'Import 3D + LOD Organize (Blender)' panel: the current LOD first, then the others."""
        out = []
        try:
            n = self.lod_stack.count()
            cur = self.lod_stack.currentIndex()
            order = [cur] + [i for i in range(n) if i != cur]
            for i in order:
                w = self.lod_stack.widget(i)
                cont = getattr(w, "panels_container", None)
                if cont is None:
                    continue
                for k in range(cont.layout.count()):
                    p = cont.layout.itemAt(k).widget()
                    if p is not None and getattr(p, "p_type", "") == "IMPORT_BLEND" and hasattr(p, "blend_field"):
                        out.append(p)
        except Exception:
            pass
        return out

    def pc2_check_logic(self):
        try:
            from ..PanelScripts import pc2_check as _pc2
            if _pc2.session_active(self):          # a temporary Blender file is open: Delete / Save
                _pc2.session_dialog(self)
                return
        except Exception:
            pass
        panels = self._find_blend_panels()
        blend = ""
        for p in panels:
            b = (self.resolve_path(p.blend_field.text()) or "").strip()
            if b:
                blend = b
                break
        if not blend:
            cmds.confirmDialog(title="KRT - Check PC2 in Blender", button=["OK"],
                               message="Add an 'Import 3D + LOD Organize (Blender)' panel and set its Blender File first.")
            return
        try:
            from ..PanelScripts import pc2_check
            import importlib
            importlib.reload(pc2_check)
            pc2_check.run(self, blend)
        except Exception:
            import traceback
            traceback.print_exc()
            cmds.warning("[KRT] PC2 check failed - see the Script Editor.")
