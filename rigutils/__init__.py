"""KRT rig library - generic studio rig scripts that ship WITH KRT (Stage 68).

Before: every rig's scripts/utils.py did sys.path.append("P:/.../RigUtils")
and imported UniUtils / wrapToBs from the share, and each rig carried its own
copy of ~25 generic helpers. Now they live here and are loaded with KRT:

    UniUtils.py            UniUtils.* (run_Fan, run_stretchy, updateEpicSpine,
                           switchFix, space_switch, EpicSpineConstraint,
                           auto_skincluster_top_all_meshes, finalize_grouping_N_parent, ...)
    rig_lib.py             the generic half of the old utils.py (replace_and_rename_mesh,
                           create_curve_on_joints, organize_and_convert_lod, ...)
    Fan.py stretchy.py Tweaker.py wrapToBs.py capture_viewport_api.py
    extraSliders.mel teethCtrlAdded.mel   (sourced when UniUtils loads)

install() runs when KRT's window opens:
  - `import UniUtils` / `import wrapToBs` anywhere in Maya now get these
    copies (sys.modules aliases), so old rigs' utils.py keep working, and
    the P: share is no longer needed;
  - every public name (replace_and_rename_mesh, UniUtils, run_Fan, ...) is put
    into Maya's Script Editor namespace (only where that name is still free).
namespace() is what each KRT script panel's namespace starts with, so
typing replace_and_rename_mesh(...) in a panel just works.
"""
import sys
import types

ALIASES = ("UniUtils", "wrapToBs")
_cache = {}


def _load():
    if "modules" in _cache:
        return _cache["modules"]
    from . import UniUtils, wrapToBs, Fan, stretchy, Tweaker, capture_viewport_api
    from ..utils import breathing
    mods = {"UniUtils": UniUtils, "wrapToBs": wrapToBs, "Fan": Fan, "stretchy": stretchy,
            "Tweaker": Tweaker, "capture_viewport_api": capture_viewport_api,
            "breathing": breathing}
    _cache["modules"] = mods
    return mods


def namespace():
    """Name -> object for every rig helper: the modules above plus every
    public function/constant of UniUtils (which includes rig_lib)."""
    mods = _load()
    ns = {}
    for k, v in vars(mods["UniUtils"]).items():
        if k.startswith("_") or isinstance(v, types.ModuleType):
            continue
        ns[k] = v
    ns.update(mods)
    return ns


def install(seed_maya_globals=True):
    """Load the library, alias the old module names, seed Maya's globals.
    Returns True on success; never raises (KRT must open regardless)."""
    try:
        mods = _load()
        for name in ALIASES:
            sys.modules[name] = mods[name]
        if seed_maya_globals:
            import __main__
            for k, v in namespace().items():
                __main__.__dict__.setdefault(k, v)
        return True
    except Exception:
        import traceback
        try:
            import maya.cmds as cmds
            cmds.warning("[KRT] rig library failed to load:\n" + traceback.format_exc())
        except Exception:
            print(traceback.format_exc())
        return False


def reload_library():
    """Re-import every rig library module (after editing one of the files)."""
    import importlib
    _cache.clear()
    from . import (capture_viewport_api, Fan, stretchy, Tweaker, wrapToBs,
                   rig_lib, UniUtils)
    for m in (capture_viewport_api, Fan, stretchy, Tweaker, wrapToBs, rig_lib, UniUtils):
        importlib.reload(m)
    return install()
