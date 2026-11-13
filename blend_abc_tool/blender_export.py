# -*- coding: utf-8 -*-
"""
blender_export.py - runs inside headless Blender.
The "Clean & Export ABC" logic from the pipeline tool, without the UI window
(there is no window in background mode).
"""
import os
import bpy

from blender_finalise import hide_mod_flags


def clean_export(abc_path):
    """Select all visible meshes, hide edit-mode/mask modifiers, export ABC.
    Returns (absolute_path, mesh_count)."""
    ctx = bpy.context
    if ctx.object and ctx.object.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    view_layer = ctx.view_layer
    for o in view_layer.objects:
        o.select_set(False)

    # Meshes that carry hair particle systems (eyebrows, hair cards, eyelashes) are skipped by the
    # Alembic exporter - they come out as an empty transform - when 'Show Instancer' (the emitter
    # mesh) is off. Turn it on in memory so the mesh itself is exported (file is never saved).
    for obj in view_layer.objects:
        if obj.type == 'MESH' and len(obj.particle_systems):
            obj.show_instancer_for_viewport = True
            obj.show_instancer_for_render = True

    meshes = []
    for obj in view_layer.objects:
        if obj.type != 'MESH':
            continue
        if obj.hide_viewport or obj.hide_get():
            continue
        obj.select_set(True)
        meshes.append(obj)
        for mod in obj.modifiers:
            hide_mod_flags(mod)

    if not meshes:
        raise RuntimeError("No visible meshes found to export.")
    view_layer.objects.active = meshes[0]

    abs_path = os.path.abspath(bpy.path.abspath(abc_path))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)   # local output folder only (checked by Maya side)

    print("[export] %d visible meshes selected, writing Alembic: %s" % (len(meshes), abs_path))
    result = bpy.ops.wm.alembic_export(
        filepath=abs_path, selected=True, flatten=False, apply_subdiv=False,
        vcolors=True, uvs=True, packuv=True, normals=True, orcos=True,
        face_sets=True, export_hair=False, export_particles=False,
        evaluation_mode='VIEWPORT',
    )
    if 'FINISHED' not in result or not os.path.isfile(abs_path):
        raise RuntimeError("Alembic export did not produce a file: %s" % (result,))
    return abs_path, len(meshes)
