# -*- coding: utf-8 -*-
"""pc2_blender.py - runs INSIDE Blender (started by KRT's PC2 check).

  names mode (headless):  blender -b file.blend --python pc2_blender.py -- names <out.json>
      writes the names of every mesh object in the file.
  apply mode (window):    blender temp_copy.blend --python pc2_blender.py -- apply <pc2_folder> <start> <end>
      applies the PC2 caches to the meshes with the pipeline tool's own operator ("Apply PC2 Caches & Rotate"),
      falling back to an identical built-in version if the addon is not loaded. The artist then checks the file by hand.

The .blend it opens is always a temporary COPY; nothing is saved by this script.
"""
import os
import sys
import json
import math
import bpy


def _args():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _clean(name):
    return name.strip().lower().split(".")[0]


def _match(obj, pc2_files):
    """Same rule as the pipeline tool (ssd_tools utils.get_matching_pc2_for_object)."""
    n = _clean(obj.name)
    for f in pc2_files:
        base = os.path.splitext(f)[0].strip().lower()
        if n == base:
            return f
        if base.startswith("geo_") and n == base.replace("geo_", "", 1):
            return f
        if n.endswith(":" + base):
            return f
    return None


def _apply_builtin(folder, start):
    """Same behaviour as pipeline.import_pc2_cache (+ frame start), for when the addon is not available."""
    files = [f for f in os.listdir(folder) if f.lower().endswith(".pc2")]
    matched = 0
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        for m in [m for m in obj.modifiers if m.type == 'MESH_CACHE']:
            obj.modifiers.remove(m)
        f = _match(obj, files)
        mod = obj.modifiers.new(name="PC2_Cache", type='MESH_CACHE')
        mod.cache_format = 'PC2'
        mod.forward_axis = 'POS_Y'
        mod.up_axis = 'POS_Z'
        if f:
            mod.filepath = os.path.join(folder, f)
            mod.frame_start = start
            obj.rotation_euler[0] = math.radians(90)
            matched += 1
        else:
            mod.filepath = ""
        try:
            if obj.modifiers.find(mod.name) > 0:
                obj.modifiers.move(obj.modifiers.find(mod.name), 0)
        except Exception:
            pass
        if "_cc_" in obj.name.lower():
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_euler = (math.radians(90), 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)
    return matched


def _apply(folder, start, end):
    scene = bpy.context.scene
    used = "built-in copy of the pipeline code"
    try:
        scene.pc2_cache_folder = folder
        scene.remove_old_modifiers = True
        scene.pc2_selected_only = False
        scene.pc2_cc_reset_transform = True
        scene.pc2_frame_start = start
        r1 = bpy.ops.pipeline.import_pc2_cache()
        r2 = bpy.ops.pipeline.set_pc2_frame_start()
        if 'FINISHED' in r1 and 'FINISHED' in r2:
            used = "pipeline tool: Apply PC2 Caches & Rotate"
        else:
            raise RuntimeError("operator did not finish")
    except Exception as e:
        print("[KRT pc2] pipeline operator not usable (%s) - using built-in copy" % e)
        _apply_builtin(folder, start)
    scene.frame_start = start
    scene.frame_end = end
    scene.frame_set(start)
    n = sum(1 for o in scene.objects if o.type == 'MESH'
            and any(m.type == 'MESH_CACHE' and m.filepath for m in o.modifiers))
    print("[KRT pc2] applied with %s: %d meshes have a PC2 cache, frames %d-%d" % (used, n, start, end))


def main():
    a = _args()
    if not a:
        return
    if a[0] == "names":
        names = sorted({o.name for o in bpy.data.objects if o.type == 'MESH'})
        with open(a[1], "w") as f:
            json.dump(names, f)
        print("[KRT pc2] %d mesh names written" % len(names))
    elif a[0] == "apply":
        folder, start, end = a[1], int(float(a[2])), int(float(a[3]))

        def go():
            try:
                _apply(folder, start, end)
            except Exception:
                import traceback
                traceback.print_exc()
            return None            # run once
        # the addons are registered by now; wait a moment so the UI is fully up
        bpy.app.timers.register(go, first_interval=1.0)


main()
