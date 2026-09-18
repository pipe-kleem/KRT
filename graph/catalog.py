"""Auto-split from graph.py."""
from ._shared import *


_MGEAR_COMPONENT_CACHE = None


def list_mgear_components(force_refresh=False):
    """Return a sorted list of every available mGear Shifter component type
    (e.g. 'arm_2jnt_01', 'chain_01', ...), matching the Component List shown
    in Shifter's own Guide Manager window.

    Results are cached for the Maya session; pass force_refresh=True (or
    call clear_mgear_component_cache()) after installing new custom
    components at runtime.
    """
    global _MGEAR_COMPONENT_CACHE
    if _MGEAR_COMPONENT_CACHE is not None and not force_refresh:
        return _MGEAR_COMPONENT_CACHE

    try:
        from mgear import shifter as mg_shifter
    except ImportError:
        cmds.warning("mGear is not installed/loaded - cannot list Shifter components.")
        return []

    try:
        comp_dirs = mg_shifter.getComponentDirectories()
        names = set()
        for directory, entries in comp_dirs.items():
            for entry in entries:
                if entry.startswith("__"):
                    continue
                full = os.path.join(directory, entry)
                if os.path.isdir(full) and os.path.exists(os.path.join(full, "guide.py")):
                    names.add(entry)
        _MGEAR_COMPONENT_CACHE = sorted(names)
    except Exception:
        traceback.print_exc()
        cmds.warning("Failed to gather mGear Shifter component list - see Script Editor.")
        _MGEAR_COMPONENT_CACHE = []

    return _MGEAR_COMPONENT_CACHE


def clear_mgear_component_cache():
    global _MGEAR_COMPONENT_CACHE
    _MGEAR_COMPONENT_CACHE = None


def list_plebe_templates():
    """Every character-generator template mGear's own "Rig Plebe" tool would
    list in its "Choose a Character Template" menu (mgear.shifter.plebes.
    Plebes.populate_template_menu), as {display_name: json_path}.

    Reads mgear/shifter/plebes_templates/*.json plus any extra directories
    named in the PLEBE_TEMPLATES_DIR environment variable.
    """
    entries = {}
    try:
        from mgear.shifter import plebes as mg_plebes
    except ImportError:
        return entries

    search_dirs = []
    env_dirs = os.environ.get("PLEBE_TEMPLATES_DIR", "")
    if env_dirs:
        # Plebe's own code splits on ':', which breaks on Windows drive
        # letters (C:\...) - os.pathsep is correct on every platform.
        search_dirs.extend(p for p in env_dirs.split(os.pathsep) if p)
    search_dirs.append(os.path.join(os.path.dirname(mg_plebes.__file__), "plebes_templates"))

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not fname.lower().endswith(".json"):
                continue
            display = fname[:-5].replace("_", " ").title()
            entries[display] = os.path.join(directory, fname)
    return entries


def _find_guide_root():
    """Return the long name of the scene's mGear guide root ("ismodel"
    transform), or None if no guide has been built yet.

    Defensive against attributeQuery raising on odd/ambiguous nodes (default
    cameras, referenced duplicates, etc.) - one bad node must never silently
    kill the whole Guide Settings panel.
    """
    for n in cmds.ls(type="transform") or []:
        try:
            if cmds.attributeQuery("ismodel", node=n, exists=True):
                long_names = cmds.ls(n, long=True)
                if long_names:
                    return long_names[0]
        except Exception:
            continue
    return None
