# -*- coding: utf-8 -*-
"""
blender_finalise.py - runs inside headless Blender.
The "FINALISE FILE (Run Selected)" logic from the pipeline tool (copied from utils.py/operators.py).
"""
import re
import bpy

OBJECT_PREFIXES = {
    'MESH': 'geo_',
    'ARMATURE': 'rig_',
    'LIGHT': 'lgt_',
    'CAMERA': 'cam_',
}
INVALID_SUFFIX = re.compile(r"\.\d+$")
LOD_PATTERN = re.compile(r"(_lod_\d+|ai_lod)")

DEFAULT_OPTIONS = {
    "units": True,
    "modifiers": True,
    "collections": True,
    "objects": True,
    "materials": True,
    "purge_mats": True,
    "purge_all": True,
}


# --- naming helpers ----------------------------------------------------------
def normalize(name):
    name = INVALID_SUFFIX.sub("", name)
    name = name.lower()
    name = re.sub(r"[ .\-]+", "_", name)
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip("_")


def get_lod_suffix_recursive(col):
    match = LOD_PATTERN.search(col.name)
    if match:
        return match.group(1)
    for parent in bpy.data.collections:
        if col.name in parent.children:
            return get_lod_suffix_recursive(parent)
    return ""


def clean_pipeline_name(raw_name, lod_suffix, prefix="", is_mat=False):
    base = normalize(raw_name)
    base = LOD_PATTERN.sub("", base)
    base = re.sub(r"_mat$", "", base).strip("_")

    if prefix and not base.startswith(prefix):
        base = f"{prefix}{base}"

    if is_mat:
        new_name = f"{base}_{lod_suffix}_mat" if lod_suffix else f"{base}_mat"
    else:
        new_name = f"{base}_{lod_suffix}" if lod_suffix else base

    while "__" in new_name:
        new_name = new_name.replace("__", "_")
    return new_name.strip("_")


# --- individual finalise steps -----------------------------------------------
def run_unit_setup(scene):
    scene.unit_settings.scale_length = 1
    scene.unit_settings.length_unit = 'METERS'


def run_master_rename_logic(do_collections=True, do_objects=True, do_materials=True):
    count = 0
    if do_collections:
        for col in bpy.data.collections:
            lod_suffix = get_lod_suffix_recursive(col)
            if lod_suffix and not col.name.endswith(lod_suffix):
                clean_col = LOD_PATTERN.sub("", normalize(col.name)).strip("_")
                col.name = f"{clean_col}_{lod_suffix}".replace("__", "_")

    for obj in bpy.data.objects:
        lod_suffix = ""
        for col in obj.users_collection:
            suffix = get_lod_suffix_recursive(col)
            if suffix:
                lod_suffix = suffix
                break

        if not lod_suffix:
            continue

        if do_objects:
            prefix = OBJECT_PREFIXES.get(obj.type, "")
            obj.name = clean_pipeline_name(obj.name, lod_suffix, prefix=prefix)

            if obj.data:
                base_data_name = obj.name
                if not base_data_name.endswith("Shape"):
                    obj.data.name = f"{base_data_name}Shape"
                else:
                    obj.data.name = base_data_name

                if hasattr(obj.data, "shape_keys") and obj.data.shape_keys:
                    obj.data.shape_keys.name = f"{obj.name}_meshShape"

        if do_materials and obj.type == 'MESH':
            for slot in obj.material_slots:
                if slot.material:
                    mat = slot.material
                    target_name = clean_pipeline_name(mat.name, lod_suffix, is_mat=True)
                    if mat.name != target_name:
                        mat.name = target_name
        count += 1
    return count


def hide_mod_flags(mod):
    """Hide a modifier from edit mode / cage; mask modifiers off in viewport."""
    if hasattr(mod, "show_on_cage"):
        mod.show_on_cage = False
    if hasattr(mod, "show_in_edit"):
        mod.show_in_edit = False
    elif hasattr(mod, "show_in_editmode"):
        mod.show_in_editmode = False
    if mod.type == 'MASK':
        mod.show_viewport = False


def run_modifier_cleanup():
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            hide_mod_flags(mod)


def purge_unused_materials():
    n = 0
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)
            n += 1
    return n


def purge_all_orphans():
    try:
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    except Exception as e:
        print("orphans_purge operator failed (%s); using bpy.data.orphans_purge" % e)
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


# --- the button ---------------------------------------------------------------
def finalise(opts=None):
    """Same order as the FINALISE FILE button."""
    o = dict(DEFAULT_OPTIONS)
    o.update(opts or {})
    done = []

    if o["units"]:
        run_unit_setup(bpy.context.scene)
        done.append("units")

    if o["collections"] or o["objects"] or o["materials"]:
        run_master_rename_logic(do_collections=bool(o["collections"]),
                                do_objects=bool(o["objects"]),
                                do_materials=bool(o["materials"]))
        done.append("rename")

    if o["modifiers"]:
        run_modifier_cleanup()
        done.append("modifiers")

    if o["purge_mats"]:
        done.append("purged %d mats" % purge_unused_materials())

    if o["purge_all"]:
        purge_all_orphans()
        done.append("purged all")

    print("[finalise] " + ", ".join(done))
    return done
