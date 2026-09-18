"""Auto-split from widgets.py."""
from ._shared import *


def type_accent(p_type):
    return PANEL_TYPE_ACCENTS.get(p_type, "#2bb5a8")

def type_icon(p_type):
    return PANEL_TYPE_ICONS.get(p_type, "⚙️")

def type_bg_tint(p_type):
    return PANEL_TYPE_BG_TINT.get(p_type, "#252526")

def style_readonly_path_field(field, accent=None):
    """Give a read-only path field (JSON/SHAPES/PUBLISH/TWEAKER/IMPORT_3D's
    main field) a look that reads as 'loaded/saved automatically', distinct
    from a normal editable field. Stage 18: always uses READONLY_FIELD_COLOR
    now, the same brown for every panel type - the `accent` parameter is
    kept (unused) only so any external caller passing one doesn't break."""
    field.setReadOnly(True)
    field.setStyleSheet(
        f"background: #1a1a1a; border: 1px solid {READONLY_FIELD_COLOR}; color: {READONLY_FIELD_COLOR};"
        f" padding: 6px; font-family: 'Consolas';")
    field.setToolTip(
        "Set automatically by Browse, Save, or Switch Version - not typed by hand.")

def is_script_file_ref(text):
    """Stage 19: a SCRIPT/GLOBAL_SCRIPT panel's field can hold EITHER a path
    to a real .py/.mel file OR raw pasted code - only the first case should
    lock like the other path fields (there's a real file behind it, set by
    Browse, not typed by hand). Detected purely by the text ending in .py or
    .mel, same as the browse-file filters already assume."""
    t = (text or "").strip().lower()
    return t.endswith(".py") or t.endswith(".mel")

def panel_run_label(p_type):
    """The default label for a panel's main run/action button, per type.
    Shared by SortablePanel's init/execute/_normal_run_text and by
    SessionWorkspace.reset_scene_and_ui so every spot that decides this
    label agrees, instead of four separately hand-kept ternary chains."""
    if p_type in ("SCRIPT", "GLOBAL_SCRIPT"): return "RUN"
    if p_type == "PUBLISH": return "VALIDATE"
    if p_type == "TWEAKER": return "CREATE"
    # Stage 23: a LOD Loader panel runs in-sequence with every other panel
    # (ordered Build Till Here, etc) exactly like a normal step - "LOAD"
    # implied it was a separate, special action, so it now reads RUN too.
    if p_type == "LOD_LOADER": return "RUN"
    if p_type == "IMPORT_LOD": return "IMPORT & ORGANIZE"
    if p_type == "DELETE_OBJ": return "DELETE"
    if p_type == "ZERO_OUT": return "ZERO OUT"
    if p_type == "PARENT_OBJ": return "PARENT"
    if p_type == "INSTANCE_OBJ": return "🧬 CREATE INSTANCES"
    return "LOAD"


def prompt_skincluster_naming_check(parent, meshes=None, show_popup=True):
    """SkinCluster-naming check (Stage 16, request #1) - run right before a
    skin export or import, scoped to just the mesh(es) that save/import is
    actually about to touch, instead of scanning the whole scene at KRT
    launch the way this used to work. Warns if any of them has a
    skinCluster whose name doesn't match KRT's '<mesh>_SkinCluster'
    convention and offers to fix every mismatch in one click.

    Saving/importing skin never actually depends on this name - every
    lookup KRT does (find_mesh_skincluster, ensure_skin_ready_for_import,
    get_tweaker_target_meshes) resolves a skinCluster by construction
    history, never by name - so this is purely a keep-the-Outliner-tidy
    convenience. Cancel just proceeds with the save/import as normal.

    show_popup=False (the Rig Build workspace's "Show SkinCluster naming
    popup" checkbox, unchecked) skips the confirmation dialog entirely but
    keeps the check itself working exactly as before: any mismatch found
    is renamed right away, silently, and just logged to the script editor
    instead of interrupting the save/import with a window."""
    try:
        mismatches = find_mismatched_skinclusters(meshes=meshes)
    except Exception:
        traceback.print_exc()
        return
    if not mismatches:
        return

    if not show_popup:
        renamed = rename_mismatched_skinclusters(mismatches)
        cmds.warning("[KRT] Renamed {} skinCluster(s) to match convention (naming popup off).".format(renamed))
        return

    shown = mismatches[:20]
    lines = "\n".join("  {}  ->  {}".format(cur, can) for _, cur, can in shown)
    more = "" if len(mismatches) <= 20 else "\n  ...and {} more".format(len(mismatches) - 20)
    msg = (
        "{} mesh(es) involved in this save/import have a skinCluster whose name "
        "doesn't match KRT's naming convention (<mesh>_SkinCluster):\n\n{}{}\n\n"
        "Rename them now to match?"
    ).format(len(mismatches), lines, more)

    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("KRT - SkinCluster Naming")
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setText(msg)
    box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
    result = box.exec() if IS_PYSIDE6 else box.exec_()
    if result == QtWidgets.QMessageBox.Ok:
        renamed = rename_mismatched_skinclusters(mismatches)
        cmds.warning("[KRT] Renamed {} skinCluster(s) to match convention.".format(renamed))
