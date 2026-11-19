# -*- coding: utf-8 -*-
"""pc2_blender.py - runs INSIDE Blender (started by KRT's PC2 check).

  names  (headless): blender -b file.blend --python pc2_blender.py -- names <out.json>
  apply  (window)  : blender copy.blend   --python pc2_blender.py -- apply <pc2_folder> <start> <end>
                     applies the PC2 caches with the pipeline tool's own operator ("Apply PC2 Caches & Rotate"),
                     sets the scene range + current frame, makes sure a Timeline is visible, shows a result popup.
  render (headless): blender -b copy.blend --python pc2_blender.py -- render <pc2_folder> <start> <end> <out_dir> <step>
                     applies the PC2 and renders a quick preview sequence (Workbench) to <out_dir>/frame_0001.png ...

The .blend it opens is always a temporary COPY; nothing is saved by this script.
"""
import os
import sys
import json
import math
import traceback
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
    """-> (how, matched_count, no_cache_names)"""
    scene = bpy.context.scene
    how = "built-in copy of the pipeline code"
    try:
        scene.pc2_cache_folder = folder
        scene.remove_old_modifiers = True
        scene.pc2_selected_only = False
        scene.pc2_cc_reset_transform = True
        scene.pc2_frame_start = start
        r1 = bpy.ops.pipeline.import_pc2_cache()
        r2 = bpy.ops.pipeline.set_pc2_frame_start()
        if 'FINISHED' in r1 and 'FINISHED' in r2:
            how = "pipeline tool: Apply PC2 Caches & Rotate"
        else:
            raise RuntimeError("operator did not finish")
    except Exception as e:
        print("[KRT pc2] pipeline operator not usable (%s) - using built-in copy" % e)
        _apply_builtin(folder, start)
    scene.use_preview_range = False
    scene.frame_start = start
    scene.frame_end = end
    scene.frame_set(start)
    ok = [o.name for o in scene.objects if o.type == 'MESH'
          and any(m.type == 'MESH_CACHE' and m.filepath for m in o.modifiers)]
    none = [o.name for o in scene.objects if o.type == 'MESH' and o.name not in ok]
    print("[KRT pc2] applied with %s: %d meshes have a PC2 cache, frames %d-%d" % (how, len(ok), start, end))
    return how, len(ok), none


# ── window helpers ───────────────────────────────────────────────────────────
def _ensure_timeline():
    """Make sure a Timeline editor is visible and shows the whole frame range, so the artist can just scrub."""
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if win is None:
        return
    screen = win.screen

    def is_tl(a):
        return a.type == 'DOPESHEET_EDITOR' and getattr(a, "ui_type", "") == 'TIMELINE'
    area = next((a for a in screen.areas if is_tl(a)), None)
    if area is None:
        cands = [a for a in screen.areas if a.type != 'VIEW_3D']
        if not cands:
            return
        area = sorted(cands, key=lambda a: a.height)[0]      # the smallest non-viewport area becomes the timeline
        area.ui_type = 'TIMELINE'
    try:
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.action.view_all()
    except Exception as e:
        print("[KRT pc2] timeline view_all failed: %s" % e)
    try:
        area.spaces.active.show_seconds = False       # frames, not seconds
    except Exception:
        pass
    area.tag_redraw()


def _popup(title, lines, icon='INFO'):
    def draw(self, _context):
        for ln in lines:
            self.layout.label(text=ln)
    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
    except Exception as e:
        print("[KRT pc2] popup failed: %s" % e)


# ── commands from Maya (Delete / Save) ───────────────────────────────────────
_STATE = {"initial": "", "waiting_save": False, "pc2": "", "cmd": ""}


class KRT_OT_close_prompt(bpy.types.Operator):
    bl_idname = "krt.close_prompt"
    bl_label = "KRT - file saved"
    message: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        wm = context.window_manager
        try:
            return wm.invoke_props_dialog(self, width=520, confirm_text="Close Blender")
        except TypeError:
            return wm.invoke_props_dialog(self, width=520)

    def draw(self, context):
        for ln in self.message.split("|"):
            self.layout.label(text=ln)
        self.layout.label(text="OK = close Blender.   Click outside the box = stay in Blender.")

    def execute(self, context):
        bpy.ops.wm.quit_blender()
        return {'FINISHED'}


def _ctx():
    win = bpy.context.window_manager.windows[0]
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), win.screen.areas[0])
    return win, area


def _start_save():
    """Maya asked to SAVE: open Blender's own Save As window; after saving, the PC2 files are copied next to the file."""
    try:
        win, area = _ctx()
        _STATE["initial"] = bpy.data.filepath
        _STATE["waiting_save"] = True
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
    except Exception:
        traceback.print_exc()
        _STATE["waiting_save"] = False


def _after_save():
    """The artist saved: copy the PC2 files next to the .blend and repoint the caches, save again, then ask stay / close."""
    import shutil
    msg = ["Saved: " + bpy.data.filepath]
    try:
        src = _STATE["pc2"]
        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        dst = os.path.join(os.path.dirname(bpy.data.filepath), stem + "_pc2")
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
            n = 0
            for o in bpy.data.objects:
                for m in o.modifiers:
                    if m.type == 'MESH_CACHE' and m.filepath:
                        m.filepath = os.path.join(dst, os.path.basename(bpy.path.abspath(m.filepath)))
                        n += 1
            bpy.ops.wm.save_mainfile()
            msg.append("PC2 files copied to: " + dst)
            msg.append("%d cache modifiers now point there." % n)
    except Exception:
        traceback.print_exc()
        msg.append("(could not copy the PC2 files - see the Blender console)")
    try:
        win, area = _ctx()
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.krt.close_prompt('INVOKE_DEFAULT', message="|".join(msg))
    except Exception:
        traceback.print_exc()


def _poll():
    try:
        cmd = _STATE["cmd"]
        if cmd and os.path.isfile(cmd):
            with open(cmd) as f:
                word = f.read().strip().lower()
            os.remove(cmd)
            if word == "save":
                _start_save()
        if _STATE["waiting_save"] and bpy.data.filepath and \
                os.path.normcase(bpy.data.filepath) != os.path.normcase(_STATE["initial"]):
            _STATE["waiting_save"] = False
            _after_save()
    except Exception:
        traceback.print_exc()
    return 0.5


def _gui_apply(folder, start, end):
    lines, icon = [], 'INFO'
    try:
        how, n, none = _apply(folder, start, end)
        lines.append("PC2 applied to %d mesh(es), frames %d-%d." % (n, start, end))
        lines.append("Method: " + how)
        if none:
            icon = 'ERROR' if n == 0 else 'INFO'
            lines.append("%d mesh(es) have no PC2 file, e.g.: %s" % (len(none), ", ".join(none[:4])))
        lines.append("The timeline is set - drag the playhead to check.")
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        icon = 'ERROR'
        lines = ["PC2 apply FAILED - copy this and send it:"] + tb.strip().splitlines()[-8:]
    try:
        _ensure_timeline()
    except Exception:
        print(traceback.format_exc())
    _popup("KRT PC2 check", lines, icon)
    return None


# ── render ───────────────────────────────────────────────────────────────────
def _bounds():
    """World bounding box (min, max) of every visible mesh at the current frame."""
    from mathutils import Vector
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    cached = [o for o in objs if any(m.type == 'MESH_CACHE' and m.filepath for m in o.modifiers)]
    for o in (cached or objs):            # frame the animated (cached) meshes, ignore far-away helper objects
        eo = o.evaluated_get(dg)
        for c in eo.bound_box:
            w = eo.matrix_world @ Vector(c)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def _show_all():
    """Make every mesh visible in viewport and render (objects, collections, view-layer excludes)."""
    def walk(lc):
        lc.exclude = False
        try:
            lc.hide_viewport = False
        except Exception:
            pass
        for c in lc.children:
            walk(c)
    try:
        walk(bpy.context.view_layer.layer_collection)
    except Exception:
        pass
    for c in bpy.data.collections:
        c.hide_viewport = False
        c.hide_render = False
    for o in bpy.context.scene.objects:
        if o.type == 'MESH':
            o.hide_render = False
            o.hide_viewport = False
            try:
                o.hide_set(False)
            except Exception:
                pass
    bpy.context.view_layer.update()


def _make_camera():
    from mathutils import Vector
    lo, hi = _bounds()
    if lo.x > hi.x:
        lo, hi = Vector((-1, -1, -1)), Vector((1, 1, 1))
    centre = (lo + hi) / 2.0
    size = max((hi - lo).x, (hi - lo).y, (hi - lo).z, 0.1)
    print("[KRT pc2] render bounds", tuple(lo), tuple(hi))
    cam_data = bpy.data.cameras.new("krt_pc2_cam")
    cam = bpy.data.objects.new("krt_pc2_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam_data.lens = 50
    cam_data.sensor_width = 36
    # the tallest side of the bounding box is the character's height: look at it from the front, never from the top
    ext = hi - lo
    if ext.y > ext.z * 1.2 and ext.y >= ext.x:           # Y-up scene (Maya orientation): look along -Z
        dist = max(ext.x, ext.y) * 2.2
        cam.location = centre + Vector((0.0, 0.0, dist))
        cam.rotation_euler = (0.0, 0.0, 0.0)
    else:                                               # Z-up scene: look along +Y
        dist = max(ext.x, ext.z) * 2.2
        cam.location = centre + Vector((0.0, -dist, 0.0))
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    print("[KRT pc2] camera at", tuple(cam.location), "extent", tuple(ext))
    cam_data.clip_start = size * 0.01
    cam_data.clip_end = size * 50
    return cam


def _render(folder, start, end, out_dir, step):
    scene = bpy.context.scene
    _apply(folder, start, end)
    os.makedirs(out_dir, exist_ok=True)
    scene.render.engine = 'BLENDER_WORKBENCH'
    try:
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.color_type = 'TEXTURE'
    except Exception:
        pass
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 960, 540, 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    _show_all()
    # only meshes that received a PC2 cache are rendered: the others would stay static (e.g. another LOD / duplicate set)
    hidden = []
    for o in scene.objects:
        if o.type == 'MESH' and not any(m.type == 'MESH_CACHE' and m.filepath for m in o.modifiers):
            o.hide_render = True
            hidden.append(o.name)
    print("[KRT pc2] render: %d meshes without a PC2 cache are hidden: %s" % (len(hidden), ", ".join(hidden[:30])))
    scene.frame_set(start)
    scene.camera = _make_camera()          # always our own camera, framed on the whole model
    frames = list(range(start, end + 1, max(1, step)))
    if frames[-1] != end:
        frames.append(end)
    for i, fr in enumerate(frames, 1):
        scene.frame_set(fr)
        bpy.context.view_layer.update()
        scene.render.filepath = os.path.join(out_dir, "frame_%04d.png" % fr)
        bpy.ops.render.render(write_still=True)
        print("KRT_RENDER %d/%d" % (i, len(frames)))
        sys.stdout.flush()
    print("KRT_RENDER_DONE")


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
        _STATE["pc2"] = folder
        _STATE["cmd"] = os.path.join(a[4], "cmd.txt") if len(a) > 4 else ""
        try:
            bpy.utils.register_class(KRT_OT_close_prompt)
        except Exception:
            pass
        # the addons are registered by now; wait a moment so the UI is fully up
        bpy.app.timers.register(lambda: _gui_apply(folder, start, end), first_interval=1.5)
        bpy.app.timers.register(_poll, first_interval=2.0)
    elif a[0] == "render":
        folder, start, end, out_dir, step = a[1], int(float(a[2])), int(float(a[3])), a[4], int(a[5])
        try:
            _render(folder, start, end, out_dir, step)
        except Exception:
            traceback.print_exc()
            sys.stdout.flush()
            sys.exit(1)


main()
