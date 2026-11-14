# -*- coding: utf-8 -*-
"""
blender_playblast.py - runs inside headless Blender (after the ABC export).

Makes a small face-only "playblast" (PNG sequence) to check the wrinkle maps:
  * all blendshapes are set to 0 and the drivers that connect them to the
    wrinkle shader are muted (so nothing animates the wrinkles)
  * then every wrinkle channel of the head material's 'rl_wrinkle_shader'
    ("Value 1AXL", "Value 1AYL" ... ) is switched to 1.0 ONE BY ONE
  * each channel is rendered at several strengths (0.25 / 0.5 / 0.75 / 1.0) so the
    Maya window can fade it in and out smoothly (not just on/off)
  * channels that change nothing visible are skipped (and reported)
The camera is framed on the face using the *_eye_* meshes.

Nothing is saved to the .blend.
"""
import os
import json
import math
import fnmatch

import bpy
from mathutils import Vector

DEFAULTS = {
    "engine": "CYCLES",       # CYCLES (the CC skin shader has too many textures for EEVEE) or EEVEE
    "resolution": 640,        # square render size in px
    "samples": 24,            # render samples
    "lens": 85.0,             # camera focal length (mm)
    "frame_scale": 2.0,       # visible face height = eye-bbox width * this
    "forward": "-Y",          # axis the face looks along (CC / Blender default is -Y)
    "diff_threshold": 0.0005, # fraction of pixels that must change to keep a frame
    "channel_value": 1.0,     # strength used for each wrinkle channel
    "ramp_steps": 4,          # renders per channel between 0 and full (4 = 0.25/0.5/0.75/1.0);
                              # Maya blends between them -> smooth fade in/out. 1 = plain on/off
    "channels": None,         # e.g. ["2XL", "3WL"] to test only some channels
}

EYE_PATTERN = "*_eye_*"
BODY_PATTERN = "*_cc_*_body*"
FACE_PATTERNS = ("*_cc_*", "*_eye_*")
SKIP_TOKENS = ("_lod_1", "_lod_2", "ai_lod")

_FORWARD = {"-Y": Vector((0, -1, 0)), "+Y": Vector((0, 1, 0)),
            "-X": Vector((-1, 0, 0)), "+X": Vector((1, 0, 0))}


def _match(obj, pattern):
    return fnmatch.fnmatch(obj.name.lower(), pattern)


def _is_lod0(obj):
    n = obj.name.lower()
    return not any(t in n for t in SKIP_TOKENS)


def _face_objects():
    return [o for o in bpy.data.objects
            if o.type == 'MESH' and _is_lod0(o)
            and any(_match(o, p) for p in FACE_PATTERNS)]


def _eye_objects():
    return [o for o in bpy.data.objects
            if o.type == 'MESH' and _is_lod0(o) and _match(o, EYE_PATTERN)]


# ---------------------------------------------------------------------------
# wrinkle setup
# ---------------------------------------------------------------------------
def find_wrinkle_node():
    """(material, group node) of the head material's rl_wrinkle_shader."""
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not _match(obj, BODY_PATTERN) or not _is_lod0(obj):
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            for n in mat.node_tree.nodes:
                if n.type == 'GROUP' and n.node_tree and 'wrinkle' in n.node_tree.name.lower():
                    return mat, n
    return None, None


def disable_blendshapes():
    """All shape keys -> 0 and every driver on materials/shape keys muted."""
    muted = 0
    for coll in (bpy.data.materials, bpy.data.shape_keys, bpy.data.node_groups):
        for idb in coll:
            holder = idb.node_tree if hasattr(idb, "node_tree") and idb.node_tree else idb
            for target in {idb, holder}:
                ad = getattr(target, "animation_data", None)
                if ad:
                    for fc in ad.drivers:
                        fc.mute = True
                        muted += 1
    zeroed = 0
    for key in bpy.data.shape_keys:
        for kb in key.key_blocks[1:]:
            if kb.value != 0.0:
                kb.value = 0.0
                zeroed += 1
    print("[playblast] muted %d drivers, zeroed %d shape keys" % (muted, zeroed))


def wrinkle_channels(node):
    return [i for i in node.inputs if i.name.startswith("Value ") and not i.is_linked]


# ---------------------------------------------------------------------------
# scene setup (camera / lights / render settings)
# ---------------------------------------------------------------------------
def _eye_frame(opts):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in _eye_objects():
        oe = o.evaluated_get(dg)
        pts += [oe.matrix_world @ Vector(c) for c in oe.bound_box]
    if not pts:
        raise RuntimeError("No *_eye_* meshes found to frame the face.")
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    return (mn + mx) * 0.5, (mx - mn)


def _aim(obj, direction):
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def setup_camera_and_lights(opts):
    scene = bpy.context.scene
    center, size = _eye_frame(opts)
    width = max(size.x, size.y, 0.05)
    fwd = _FORWARD[opts["forward"]]

    face_center = center + Vector((0, 0, -0.18 * width))
    frame_h = width * opts["frame_scale"]

    cam_data = bpy.data.cameras.new("pb_cam")
    cam_data.lens = opts["lens"]
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.01
    cam_data.clip_end = 100.0
    cam = bpy.data.objects.new("pb_cam", cam_data)
    scene.collection.objects.link(cam)
    dist = (frame_h / 2.0) / (18.0 / opts["lens"])
    cam.location = face_center + fwd * dist
    _aim(cam, face_center - cam.location)
    scene.camera = cam

    def sun(name, direction, strength):
        d = bpy.data.lights.new(name, 'SUN')
        d.energy = strength
        d.angle = math.radians(8)
        o = bpy.data.objects.new(name, d)
        scene.collection.objects.link(o)
        o.location = face_center
        _aim(o, direction)
        return o

    # raking key from the side (shows wrinkle normals), softer fill from the other side
    sun("pb_key", Vector((-0.55, 0.75, -0.40)) if fwd.y < 0 else Vector((-0.55, -0.75, -0.40)), 3.5)
    sun("pb_fill", Vector((0.50, 0.80, -0.15)) if fwd.y < 0 else Vector((0.50, -0.80, -0.15)), 1.2)

    world = bpy.data.worlds.new("pb_world")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
        bg.inputs[1].default_value = 0.6
    scene.world = world
    return face_center, frame_h


def setup_visibility():
    face = set(_face_objects())
    for o in bpy.data.objects:
        if o.type in {'MESH', 'CURVE', 'CURVES', 'POINTCLOUD', 'SURFACE', 'META', 'FONT'}:
            o.hide_render = o not in face
            if o in face:
                o.hide_viewport = False
                try:
                    o.hide_set(False)
                except Exception:
                    pass
    # a Mask modifier can cut the head away - keep it off for the check render
    for o in face:
        for m in o.modifiers:
            if m.type == 'MASK':
                m.show_render = False
                m.show_viewport = False
    return face


def _enable_cycles_gpu(scene):
    """Use a GPU for Cycles when one is available, otherwise CPU."""
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for kind in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
            except Exception:
                continue
            gpus = [d for d in prefs.devices if d.type == kind]
            if gpus:
                for d in prefs.devices:
                    d.use = (d.type == kind)
                scene.cycles.device = 'GPU'
                return "GPU (%s: %s)" % (kind, ", ".join(d.name for d in gpus))
    except Exception as e:
        print("[playblast] GPU setup failed: %s" % e)
    scene.cycles.device = 'CPU'
    return "CPU"


def setup_render(opts, out_dir):
    scene = bpy.context.scene
    r = scene.render
    if opts["engine"].upper().startswith("CYCLES"):
        r.engine = 'CYCLES'
        c = scene.cycles
        c.samples = int(opts["samples"])
        c.use_adaptive_sampling = True
        c.use_denoising = True
        try:
            c.denoiser = 'OPENIMAGEDENOISE'
        except Exception:
            pass
        c.max_bounces = 4
        c.seed = 0
        c.use_animated_seed = False
        r.use_persistent_data = True          # keep BVH/textures between the many renders
        print("[playblast] Cycles device: " + _enable_cycles_gpu(scene))
    else:
        for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
            try:
                r.engine = engine
                break
            except TypeError:
                continue
        try:
            scene.eevee.taa_render_samples = int(opts["samples"])
        except Exception:
            pass
    r.resolution_x = r.resolution_y = int(opts["resolution"])
    r.resolution_percentage = 100
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGB'
    r.film_transparent = False
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
    except Exception:
        pass
    # clean frames (no burned-in text): the Maya window shows the channel name + strength,
    # and blends between the rendered strengths to make the wrinkle fade in/out smoothly
    r.use_stamp = False


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _render(path):
    r = bpy.context.scene.render
    r.filepath = path
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)


def _pixels(path, crop_top=0.0):
    """Return the rendered image as a float array (rows start at the bottom)."""
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    arr = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(arr)
    bpy.data.images.remove(img)
    arr = arr.reshape(h, w, 4)
    return arr[:int(h * (1.0 - crop_top))]     # rows start at the BOTTOM of the image


def _check_textures(mat):
    missing = []
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and 'rinkle' in (n.image.name + n.name).lower():
            if n.image.source == 'FILE' and not n.image.packed_file:
                p = bpy.path.abspath(n.image.filepath)
                if not os.path.isfile(p):
                    missing.append(n.image.name)
    return missing


def make_wrinkle_playblast(out_dir, options=None):
    import numpy as np
    opts = dict(DEFAULTS)
    opts.update(options or {})
    os.makedirs(out_dir, exist_ok=True)

    mat, node = find_wrinkle_node()
    if not node:
        raise RuntimeError("No wrinkle shader found on a *_cc_*_body* mesh.")
    channels = wrinkle_channels(node)
    if not channels:
        raise RuntimeError("Wrinkle shader has no 'Value ...' channels.")

    missing = _check_textures(mat)
    if missing:
        print("[playblast] WARNING missing wrinkle textures: %s" % ", ".join(missing))

    only = set(opts.get("channels") or [])           # optional: limit to some channels (testing)
    total = len(channels)
    print("[playblast] starting: %d wrinkle channels found in material '%s'" % (total, mat.name))
    disable_blendshapes()
    setup_visibility()
    setup_render(opts, out_dir)
    setup_camera_and_lights(opts)

    # neutral reference (everything at 0)
    for ch in channels:
        ch.default_value = 0.0
    neutral_file = "neutral.png"
    neutral_path = os.path.join(out_dir, neutral_file)
    print("[playblast] (0/%d) rendering NEUTRAL reference (blendshapes off) ..." % total)
    _render(neutral_path)
    neutral = _pixels(neutral_path)

    steps = max(1, int(opts["ramp_steps"]))
    peak = float(opts["channel_value"])
    out_channels, skipped = [], []
    for n_ch, ch in enumerate(channels, 1):
        name = ch.name.replace("Value ", "")
        if only and name not in only:
            continue
        idx = len(out_channels) + 1
        full_file = "c%03d_s%d.png" % (idx, steps)
        full_path = os.path.join(out_dir, full_file)

        # 1) full strength first: if nothing changes, skip the whole channel
        print("[playblast] (%d/%d) %s: rendering full strength ..." % (n_ch, total, name))
        ch.default_value = peak
        _render(full_path)
        delta = np.abs(_pixels(full_path)[..., :3] - neutral[..., :3]).max(axis=2)
        diff = float((delta > 0.02).mean())          # fraction of pixels that visibly changed
        if diff < opts["diff_threshold"]:
            ch.default_value = 0.0
            skipped.append(name)
            os.remove(full_path)
            print("[playblast]    -> %s no visible change (skipped)" % name)
            continue

        # 2) in-between strengths so the wrinkle can ease in/out smoothly
        files = []
        for k in range(1, steps):
            ch.default_value = peak * k / float(steps)
            print("[playblast] (%d/%d) %s: ramp step %d/%d (strength %.2f) ..."
                  % (n_ch, total, name, k, steps, ch.default_value))
            f = "c%03d_s%d.png" % (idx, k)
            _render(os.path.join(out_dir, f))
            files.append(f)
        files.append(full_file)
        ch.default_value = 0.0

        out_channels.append({"name": name, "label": "Wrinkle %s" % name,
                             "frames": files, "diff": round(diff, 5)})
        print("[playblast]    -> %s changes %.2f%% of the face (kept, %d frames)"
              % (name, diff * 100, len(files)))

    manifest = {"version": 2, "neutral": neutral_file, "steps": steps, "peak": peak,
                "channels": out_channels, "skipped": skipped,
                "missing_textures": missing}
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("[playblast] DONE: %d wrinkle channels kept, %d with no visible change"
          % (len(out_channels), len(skipped)))
    return manifest
