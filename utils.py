import maya.cmds as cmds
import maya.OpenMaya as om
import os
import json
import pickle
import re
import time
import traceback
import gc

def get_versioned_path(file_path, get_latest=False):
    directory = os.path.dirname(file_path)
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    base_name = re.sub(r'_v\d+$', '', base_name)
    
    if not os.path.exists(directory):
        if get_latest: return file_path 
        return os.path.join(directory, "{}_v001{}".format(base_name, ext)).replace('\\', '/')

    highest_version = 0
    pattern = re.compile(r"^{}_v(\d+){}$".format(re.escape(base_name), re.escape(ext)))

    if os.path.exists(directory):
        for f in os.listdir(directory):
            match = pattern.match(f)
            if match:
                version = int(match.group(1))
                if version > highest_version:
                    highest_version = version

    if get_latest:
        if highest_version == 0: return file_path
        latest_name = "{}_v{:03d}{}".format(base_name, highest_version, ext)
        return os.path.join(directory, latest_name).replace('\\', '/')
    else:
        next_version = highest_version + 1
        new_name = "{}_v{:03d}{}".format(base_name, next_version, ext)
        return os.path.join(directory, new_name).replace('\\', '/')

def export_control_shapes(file_path, controls=None, search_pattern=None):
    if search_pattern:
        found_controls = cmds.ls(search_pattern, type="transform")
        if not found_controls:
            cmds.warning("No controls found matching pattern: {}".format(search_pattern))
            return False
        controls = found_controls
    elif controls is None:
        controls = cmds.ls(selection=True)
        
    if not controls:
        cmds.warning("No controls selected or provided to export.")
        return False

    shape_dict = {}
    for ctrl in controls:
        shapes = cmds.listRelatives(ctrl, shapes=True, fullPath=True)
        if not shapes: continue 
        shape_dict[ctrl] = {}

        if cmds.attributeQuery("overrideEnabled", node=ctrl, exists=True) and cmds.getAttr(ctrl + ".overrideEnabled"):
            t_color_data = {'overrideEnabled': 1}
            if cmds.getAttr(ctrl + ".overrideRGBColors"):
                t_color_data['overrideRGBColors'] = 1
                t_color_data['overrideColorRGB'] = cmds.getAttr(ctrl + ".overrideColorRGB")[0]
            else:
                t_color_data['overrideRGBColors'] = 0
                t_color_data['overrideColor'] = cmds.getAttr(ctrl + ".overrideColor")
            shape_dict[ctrl]['__transform_color__'] = t_color_data

        for shape in shapes:
            # Support any shape type, not just mgear-style nurbsCurves:
            # meshes store vertices (.vtx[*]), curves/surfaces store CVs (.cv[*]).
            shp_type = cmds.nodeType(shape)
            comp = ".vtx[*]" if shp_type == "mesh" else ".cv[*]"
            pts = cmds.ls(shape + comp, flatten=True)
            if not pts:  # fall back to generic control points for exotic shapes
                pts = cmds.ls(shape + ".controlPoints[*]", flatten=True)
            point_positions = []
            for p in pts:
                pos = cmds.xform(p, query=True, translation=True, objectSpace=True)
                point_positions.append(pos)

            color_data = {}
            if cmds.attributeQuery("overrideEnabled", node=shape, exists=True) and cmds.getAttr(shape + ".overrideEnabled"):
                color_data['overrideEnabled'] = 1
                if cmds.getAttr(shape + ".overrideRGBColors"):
                    color_data['overrideRGBColors'] = 1
                    color_data['overrideColorRGB'] = cmds.getAttr(shape + ".overrideColorRGB")[0]
                else:
                    color_data['overrideRGBColors'] = 0
                    color_data['overrideColor'] = cmds.getAttr(shape + ".overrideColor")

            shape_dict[ctrl][shape.split('|')[-1]] = {
                'type': shp_type,
                'points': point_positions,
                'cvs': point_positions,  # legacy key kept for backward compatibility
                'color': color_data,
            }

    versioned_file_path = get_versioned_path(file_path, get_latest=False)
    directory = os.path.dirname(versioned_file_path)
    if directory and not os.path.exists(directory): os.makedirs(directory)

    with open(versioned_file_path, 'w') as f: json.dump(shape_dict, f, indent=4)
    cmds.warning("SUCCESS: Exported {} controls to '{}'".format(len(shape_dict), versioned_file_path))
    return versioned_file_path

def import_control_shapes(file_path):
    latest_file_path = get_versioned_path(file_path, get_latest=True)
    if not os.path.exists(latest_file_path):
        om.MGlobal.displayError(f"File does not exist: {latest_file_path}")
        return False

    with open(latest_file_path, 'r') as f: shape_dict = json.load(f)
    applied_count = 0

    for ctrl, shapes_data in shape_dict.items():
        if not cmds.objExists(ctrl):
            continue

        if '__transform_color__' in shapes_data:
            t_color = shapes_data['__transform_color__']
            cmds.setAttr(ctrl + ".overrideEnabled", 1)
            if t_color.get('overrideRGBColors'):
                cmds.setAttr(ctrl + ".overrideRGBColors", 1)
                rgb = t_color.get('overrideColorRGB', [0,0,0])
                cmds.setAttr(ctrl + ".overrideColorRGB", rgb[0], rgb[1], rgb[2])
            else:
                cmds.setAttr(ctrl + ".overrideRGBColors", 0)
                cmds.setAttr(ctrl + ".overrideColor", t_color.get('overrideColor', 0))

        shape_items = [(k, v) for k, v in shapes_data.items() if k != '__transform_color__']
        current_shapes = cmds.listRelatives(ctrl, shapes=True, fullPath=True) or []
        used_targets = set()

        for i, (old_shape_name, data) in enumerate(shape_items):
            # Match the saved shape to a live shape by short name first, then fall
            # back to positional order. This keeps multi-shape controls correct.
            target_shape = None
            for cs in current_shapes:
                if cs in used_targets:
                    continue
                if cs.split('|')[-1] == old_shape_name:
                    target_shape = cs
                    break
            if target_shape is None and i < len(current_shapes):
                cand = current_shapes[i]
                if cand not in used_targets:
                    target_shape = cand
            if target_shape is None:
                continue
            used_targets.add(target_shape)

            # Positions work for any point count and any shape type: meshes use
            # vertices, everything else uses CVs.
            positions = data.get('points')
            if positions is None:
                positions = data.get('cvs', [])
            shp_type = data.get('type') or cmds.nodeType(target_shape)
            comp = "vtx" if shp_type == "mesh" else "cv"

            for j, pos in enumerate(positions):
                cv_path = "{}.{}[{}]".format(target_shape, comp, j)
                if cmds.objExists(cv_path):
                    cmds.xform(cv_path, translation=pos, objectSpace=True)

            color_data = data.get('color', {})
            if color_data.get('overrideEnabled'):
                cmds.setAttr(target_shape + ".overrideEnabled", 1)
                if color_data.get('overrideRGBColors'):
                    cmds.setAttr(target_shape + ".overrideRGBColors", 1)
                    rgb = color_data.get('overrideColorRGB', [0,0,0])
                    cmds.setAttr(target_shape + ".overrideColorRGB", rgb[0], rgb[1], rgb[2])
                else:
                    cmds.setAttr(target_shape + ".overrideRGBColors", 0)
                    cmds.setAttr(target_shape + ".overrideColor", color_data.get('overrideColor', 0))
            applied_count += 1

    cmds.warning("SUCCESS: Imported shapes for {} controls from '{}'".format(applied_count, latest_file_path))
    return True


# ---------------------------------------------------------------------------
# Material / Shader export-import (KRT "Material" panel)
# ---------------------------------------------------------------------------
# Mirrors export_control_shapes/import_control_shapes above in shape and
# intent, but captures a mesh's assigned shading network instead of curve
# shapes: the shading engine(s) it's a member of (whole-object AND per-face
# assignment), every upstream node in that network (surface/displacement
# shaders, file textures, utility/ramp/layer nodes, place2dTexture, etc -
# any renderer, since none of this is renderer-specific), each node's
# writable attribute values (which is how ANY texture path - fileTextureName
# or a renderer-specific equivalent - gets captured, generically, wherever
# on disk it points), and every connection between those nodes. Texture
# paths are recorded exactly as-is (not copied anywhere) - reloading simply
# reconnects to whatever path was saved, same as the source scene had.

# Attributes that are pure Maya-internal bookkeeping (not shading data at
# all) and can differ or simply not exist between Maya versions/sessions -
# capturing them is pointless and, for cbId in particular, just produces a
# noisy "no attribute" warning on import for no benefit.
_NON_DATA_ATTRS = {"cbId"}

def _is_intermediate(node):
    try:
        return bool(cmds.getAttr(node + ".intermediateObject"))
    except Exception:
        return False

def _mesh_shapes_for_export(mesh):
    """(live_shapes, fallback_shapes) for a name the user put in the Meshes
    field. `mesh` may be a transform, a mesh shape, or even a group that only
    CONTAINS meshes - all three are handled, because a Meshes field is typed
    by a rigger, not generated. Live (non-intermediate) shapes are returned
    separately from "Orig"/intermediate history shapes: shading normally
    lives on the live shape, but a deformer/rebuild history can leave it on
    an Orig shape, so the caller tries live first and only then falls back."""
    if not cmds.objExists(mesh):
        return [], []
    if cmds.nodeType(mesh) == "mesh":
        shapes = cmds.ls(mesh, long=True) or [mesh]
    else:
        shapes = cmds.listRelatives(mesh, shapes=True, type="mesh", fullPath=True) or []
        if not shapes:
            # A group/transform with the real mesh nested deeper under it.
            shapes = cmds.listRelatives(mesh, allDescendents=True, type="mesh", fullPath=True) or []
    live = [s for s in shapes if not _is_intermediate(s)]
    others = [s for s in shapes if s not in live]
    return live, others

def _compress_face_ranges(indices):
    """[0,1,2,5,6,9] -> ['.f[0:2]', '.f[5:6]', '.f[9]'] - the same component
    syntax Maya itself uses, so these replay straight back through cmds.sets."""
    out = []
    indices = sorted(set(indices))
    if not indices:
        return out
    start = prev = indices[0]
    for i in indices[1:]:
        if i == prev + 1:
            prev = i
            continue
        out.append(".f[{}]".format(start) if start == prev else ".f[{}:{}]".format(start, prev))
        start = prev = i
    out.append(".f[{}]".format(start) if start == prev else ".f[{}:{}]".format(start, prev))
    return out

def _shading_engines_for_shape_api(shape):
    """{shading_engine_name: [component_suffix, ...]} for ONE mesh shape,
    via MFnMesh.getConnectedShaders() - Maya's own canonical per-face shading
    query, and the thing every serious shader/Alembic/USD exporter uses.

    It hands back, for EVERY face of the mesh, the index of the shading engine
    that face belongs to - so per-face (multi-shader) assignment, whole-object
    assignment, instances and namespaces all come out correct with no name
    matching of any kind. That matters: reading assignment by string-matching
    cmds.sets() members is what kept failing here, because those member names
    can come back short, partially-pathed, or as the TRANSFORM rather than the
    shape, none of which compare equal to a full shape path.

    Returns None (not {}) if this path can't be used at all, so the caller can
    fall back to the older string-matching method; returns {} when the API
    worked and the shape genuinely has no shading assigned."""
    try:
        import maya.api.OpenMaya as om2
    except Exception:
        return None
    try:
        sel = om2.MSelectionList()
        sel.add(shape)
        dag = sel.getDagPath(0)
        fn = om2.MFnMesh(dag)
        shaders, face_shader_idx = fn.getConnectedShaders(dag.instanceNumber())
    except Exception:
        return None

    sg_names = []
    for i in range(len(shaders)):
        try:
            sg_names.append(om2.MFnDependencyNode(shaders[i]).name())
        except Exception:
            sg_names.append(None)

    faces_by_sg = {}
    total_faces = len(face_shader_idx)
    for face, si in enumerate(face_shader_idx):
        # -1 means that face has no shader assigned at all.
        if si < 0 or si >= len(sg_names) or not sg_names[si]:
            continue
        faces_by_sg.setdefault(sg_names[si], []).append(face)

    result = {}
    for sg, faces in faces_by_sg.items():
        if total_faces and len(faces) == total_faces:
            # Every face on this shape - store it as a plain whole-object
            # assignment rather than one giant face range, so re-applying
            # doesn't create per-face objectGroups the mesh didn't have.
            result[sg] = [""]
        else:
            result[sg] = _compress_face_ranges(faces)
    return result

def _shading_engines_for_shape_fallback(shape):
    """Pre-API fallback for a shape MFnMesh can't read (a nurbsSurface, a
    subdiv, a mesh the API refused). Same idea, done by matching cmds.sets()
    members - tolerant now about members coming back short-named, partially
    pathed, or named after the transform instead of the shape."""
    result = {}
    sgs = sorted(set(cmds.listConnections(shape, type="shadingEngine", source=False, destination=True) or []))
    for sg in sgs:
        for m in (cmds.sets(sg, query=True) or []):
            obj = m.split('.')[0]
            resolved = cmds.ls(obj, long=True) or []
            # `obj` may name the shape itself OR its transform, and may be
            # ambiguous (several matches) - accept any of those spellings.
            match = shape in resolved
            if not match:
                for r in resolved:
                    if shape in (cmds.listRelatives(r, shapes=True, fullPath=True) or []):
                        match = True
                        break
            if match:
                result.setdefault(sg, []).append(m[len(obj):])
    return result

def _shading_engines_for_mesh(mesh):
    """{shading_engine_name: [component_suffix, ...]} for a mesh. A suffix is
    "" for whole-object membership or e.g. ".f[640:647]" for one face range of
    a per-face assignment - kept relative to the shape (not baked into a full
    path) so it replays onto whichever shape is live at import time."""
    live, others = _mesh_shapes_for_export(mesh)

    def _collect(shapes):
        found = {}
        for shape in shapes:
            per_shape = _shading_engines_for_shape_api(shape)
            if per_shape is None:
                per_shape = _shading_engines_for_shape_fallback(shape)
            for sg, suffixes in per_shape.items():
                found.setdefault(sg, []).extend(suffixes)
        return found

    result = _collect(live)
    if not result and others:
        # Nothing on the live shape(s) - the shading is sitting on an
        # "Orig"/intermediate history shape (some rebuild pipelines leave it
        # there). Face indices match across a mesh's Orig and deformed
        # shapes, so what's captured here still replays correctly.
        result = _collect(others)
    return result

def _walk_shader_network(shading_engine):
    """Every non-DAG (dependency graph) node upstream of a shading engine -
    shaders, textures, utility/ramp/layer nodes - via Maya's own history
    traversal (the allConnections + pruneDagObjects combination is the
    standard technique for 'select/duplicate this shading network'), plus
    the shading engine itself."""
    try:
        hist = cmds.listHistory(shading_engine, allConnections=True, pruneDagObjects=True) or []
    except Exception:
        hist = []
    nodes = set(hist)
    nodes.add(shading_engine)
    return nodes

def _capture_node_data(node):
    """This node's type plus every writable, gettable, JSON-serializable
    attribute value. Multi/compound/message attrs and anything that fails
    to getAttr (renderer-specific or exotic attribute types) are silently
    skipped rather than aborting the whole export - same defensive style as
    the rest of this module."""
    data = {"type": cmds.nodeType(node), "attrs": {}}
    for attr in (cmds.listAttr(node, write=True) or []):
        if attr in _NON_DATA_ATTRS:
            continue
        plug = node + "." + attr
        try:
            if cmds.getAttr(plug, type=True) == "message":
                continue
            # NOTE: deliberately NOT gated on getAttr(..., settable=True) -
            # that flag is about whether the LIVE attribute could be WRITTEN
            # to right now (locked/connected), which has nothing to do with
            # whether we can READ its current value for export. Gating the
            # read on it was found to silently drop attributes (including a
            # plain, unconnected .color on a shader) on some setups.
            #
            # An attribute that currently has an INCOMING connection (e.g. a
            # shadingEngine's "surfaceShader", which is connection-only and
            # not really a plain value at all - Maya just lets getAttr read
            # a meaningless default off it) is skipped here too - the real
            # connection is captured separately by _capture_node_connections
            # and reconnecting it on import is what actually restores it.
            # Capturing a raw value here as well was found to actively
            # break things: re-applying a bogus [0,0,0] onto .surfaceShader
            # on import errors out ("Too much data was provided").
            if cmds.listConnections(plug, source=True, destination=False, plugs=True):
                continue
            val = cmds.getAttr(plug)
        except Exception:
            continue
        if isinstance(val, (int, float, bool, str)):
            data["attrs"][attr] = val
        elif isinstance(val, (list, tuple)) and val:
            try:
                if isinstance(val[0], (list, tuple)):
                    data["attrs"][attr] = [list(v) for v in val]
                elif isinstance(val[0], (int, float, str)):
                    data["attrs"][attr] = list(val)
            except Exception:
                pass
    return data

def _capture_node_connections(nodes):
    """Every connection where BOTH ends are in `nodes` - a connection to
    something outside the captured shading network (e.g. a place3dTexture,
    which is a DAG node) is left out since it isn't rebuilt on import."""
    node_set = set(nodes)
    conns = []
    seen = set()
    for node in nodes:
        pairs = cmds.listConnections(node, connections=True, plugs=True, source=True, destination=False) or []
        for i in range(0, len(pairs), 2):
            dst_plug, src_plug = pairs[i], pairs[i + 1]
            if src_plug.split('.')[0] not in node_set:
                continue
            key = (src_plug, dst_plug)
            if key in seen:
                continue
            seen.add(key)
            conns.append({"src": src_plug, "dst": dst_plug})
    return conns

def export_material_data(file_path, meshes=None):
    if meshes is None:
        meshes = cmds.ls(selection=True)
    if not meshes:
        cmds.warning("No meshes selected or provided to export material from.")
        return False

    mesh_data = {}
    all_nodes = set()
    for mesh in meshes:
        if not cmds.objExists(mesh):
            cmds.warning("Material export: '{}' does not exist in the scene - skipped.".format(mesh))
            continue
        sg_map = _shading_engines_for_mesh(mesh)
        if not sg_map:
            # Say WHY nothing was found, rather than only that nothing was:
            # which shapes were examined, and what (if anything) they're
            # actually connected to. Anything unexpected shows up right here.
            live, others = _mesh_shapes_for_export(mesh)
            seen_sgs = set()
            for s in (live + others):
                seen_sgs.update(cmds.listConnections(s, type="shadingEngine", source=False, destination=True) or [])
            cmds.warning(
                "Material export: '{}' -> NO shading found. live shape(s): {} | Orig/intermediate shape(s): {} |"
                " shadingEngine connections seen on them: {}".format(
                    mesh, live or "none", others or "none", sorted(seen_sgs) or "none"))
            continue
        mesh_data[mesh] = sg_map
        # Diagnostic: exactly what was found, per mesh/SG - so a multi-shader
        # (per-face) mesh's export can be checked against what actually shows
        # up here, instead of only finding out something's missing on load.
        parts = []
        for sg, suf in sg_map.items():
            if suf == [""]:
                parts.append("{} (whole object)".format(sg))
            else:
                sample = ", ".join(suf[:6]) + (" ..." if len(suf) > 6 else "")
                parts.append("{} ({} face group(s): {})".format(sg, len(suf), sample))
        cmds.warning("Material export: '{}' -> {}".format(mesh, "; ".join(parts)))
        for sg in sg_map:
            all_nodes.update(_walk_shader_network(sg))

    if not mesh_data:
        cmds.warning("No shading assignments found on the given mesh(es).")
        return False

    node_dump = {node: _capture_node_data(node) for node in all_nodes}
    connections = _capture_node_connections(all_nodes)

    out = {"meshes": mesh_data, "nodes": node_dump, "connections": connections}

    versioned_file_path = get_versioned_path(file_path, get_latest=False)
    directory = os.path.dirname(versioned_file_path)
    if directory and not os.path.exists(directory): os.makedirs(directory)

    with open(versioned_file_path, 'w') as f: json.dump(out, f, indent=4)
    cmds.warning("SUCCESS: Exported materials for {} mesh(es) to '{}'".format(len(mesh_data), versioned_file_path))
    return versioned_file_path

def _ensure_material_node(name, node_type):
    """Reuse a live node of the same name if it's already the right type;
    otherwise create one. A shadingEngine can't be made with createNode() -
    it has to go through cmds.sets(), same as Maya's own Hypershade does."""
    if not node_type:
        return None
    if cmds.objExists(name) and cmds.nodeType(name) == node_type:
        return name
    try:
        if node_type == "shadingEngine":
            return cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name)
        return cmds.createNode(node_type, name=name)
    except Exception:
        try:
            if node_type == "shadingEngine":
                return cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
            return cmds.createNode(node_type)
        except Exception:
            return None

def _set_material_attr(node, attr, val, warn_on_fail=False):
    plug = node + "." + attr
    try:
        if not cmds.attributeQuery(attr, node=node, exists=True):
            if warn_on_fail:
                cmds.warning("Material import: {} has no attribute '{}' - skipped.".format(node, attr))
            return False
        # No settable() pre-check here either (see _capture_node_data) - a
        # plain unconnected numeric/string attr should just setAttr cleanly;
        # if it genuinely can't be set (locked/connected), setAttr itself
        # raises and that's caught below.
        if isinstance(val, str):
            cmds.setAttr(plug, val, type="string")
        elif isinstance(val, list):
            if val and isinstance(val[0], list):
                cmds.setAttr(plug, *val[0])
            else:
                cmds.setAttr(plug, *val)
        else:
            cmds.setAttr(plug, val)
        return True
    except Exception as e:
        if warn_on_fail:
            cmds.warning("Material import: failed to set {}.{} = {} ({})".format(node, attr, val, e))
        return False

def _resolve_mesh_by_short_name(mesh_key, candidates=None):
    """Same 'match by short name if the exact path is gone' fallback
    import_control_shapes relies on for controls, applied to meshes."""
    short = mesh_key.split('|')[-1].split(':')[-1]
    if candidates:
        for c in candidates:
            if cmds.objExists(c) and c.split('|')[-1].split(':')[-1] == short:
                return c
    pool = cmds.ls(short, long=True) or cmds.ls("*:" + short, long=True)
    return pool[0] if pool else None

def import_material_data(file_path, meshes=None):
    latest_file_path = get_versioned_path(file_path, get_latest=True)
    if not os.path.exists(latest_file_path):
        om.MGlobal.displayError(f"File does not exist: {latest_file_path}")
        return False

    with open(latest_file_path, 'r') as f: data = json.load(f)

    node_dump = data.get("nodes", {})
    name_map = {name: _ensure_material_node(name, nd.get("type", "")) for name, nd in node_dump.items()}
    missing_nodes = [name for name, live in name_map.items() if not live]
    if missing_nodes:
        cmds.warning("Material import: could not create/reuse these nodes, skipped: {}".format(", ".join(missing_nodes)))

    # Attrs that are really connection destinations (captured in
    # "connections" below) get skipped here even on an OLDER exported JSON
    # that still has a bogus static value baked in for one (e.g. a
    # shadingEngine's "surfaceShader", from before this was fixed at export
    # time) - the connectAttr below is what actually restores it correctly,
    # and setAttr-ing the stale placeholder value first only risks erroring.
    connected_plugs = set()
    for c in data.get("connections", []):
        dst = c.get("dst", "")
        if "." in dst:
            connected_plugs.add(tuple(dst.split(".", 1)))

    attrs_ok, attrs_failed = 0, 0
    for name, nd in node_dump.items():
        live_name = name_map.get(name)
        if not live_name:
            continue
        for attr, val in (nd.get("attrs") or {}).items():
            if attr in _NON_DATA_ATTRS or (name, attr) in connected_plugs:
                continue
            if _set_material_attr(live_name, attr, val, warn_on_fail=True):
                attrs_ok += 1
            else:
                attrs_failed += 1
    cmds.warning("Material import: applied {} attribute(s), {} failed/skipped.".format(attrs_ok, attrs_failed))

    for c in data.get("connections", []):
        try:
            src_node, src_attr = c["src"].split(".", 1)
            dst_node, dst_attr = c["dst"].split(".", 1)
        except Exception:
            continue
        live_src, live_dst = name_map.get(src_node), name_map.get(dst_node)
        if not live_src or not live_dst:
            continue
        try:
            cmds.connectAttr(live_src + "." + src_attr, live_dst + "." + dst_attr, force=True)
        except Exception:
            continue

    applied = 0
    for mesh_key, sg_map in data.get("meshes", {}).items():
        live_mesh = mesh_key if cmds.objExists(mesh_key) else _resolve_mesh_by_short_name(mesh_key, meshes)
        if not live_mesh:
            cmds.warning("Material import: mesh not found, skipped: {}".format(mesh_key))
            continue
        # Always re-apply onto the LIVE (non-intermediate, actually rendered)
        # shape, even if the export happened to read the assignment off an
        # Orig shape - face indices match across them, and the live shape is
        # the one the rigger actually wants shaded.
        live_shapes, other_shapes = _mesh_shapes_for_export(live_mesh)
        shapes = live_shapes or other_shapes or [live_mesh]
        shape = shapes[0]
        # Whole-object entries ("" suffix) go first: applied after a per-face
        # range they would forceElement the ENTIRE shape into that one shading
        # engine and wipe the face assignments just made. Ordering them first
        # makes a mixed whole-object + per-face file land correctly whatever
        # order the JSON happens to list them in.
        ordered_sgs = sorted(sg_map.items(), key=lambda kv: 0 if ("" in (kv[1] or [])) else 1)
        for sg_name, suffixes in ordered_sgs:
            live_sg = name_map.get(sg_name)
            if not live_sg or not cmds.objExists(live_sg):
                cmds.warning("Material import: shading engine '{}' (for '{}') could not be created/found - skipped {} group(s): {}".format(sg_name, mesh_key, len(suffixes), suffixes))
                continue
            members = [shape + suf for suf in suffixes] if suffixes else [shape]
            try:
                cmds.sets(members, edit=True, forceElement=live_sg)
                applied += 1
                # Keep this readable when a per-face assignment has dozens of
                # ranges - the count is what matters, plus a sample to eyeball.
                sample = ", ".join(suffixes[:6]) + (" ..." if len(suffixes) > 6 else "")
                cmds.warning("Material import: '{}' -> {} assigned to {} group(s) [{}]".format(
                    mesh_key, live_sg, len(members), sample if suffixes else "whole object"))
            except Exception as e:
                cmds.warning("Material import: failed to assign {} on {} ({}): {}".format(sg_name, mesh_key, members, e))

    cmds.warning("SUCCESS: Imported materials for {} assignment(s) from '{}'".format(applied, latest_file_path))
    return True


def find_guide_model(start_node):
    """Walk up from any node inside an mGear guide to the top-level guide
    model transform (mGear marks it with an "ismodel" attribute - this is
    the same node mGear's own guide.model points to). Returns the long name,
    or None if start_node isn't (inside) a guide at all."""
    walker = start_node
    while walker:
        if cmds.attributeQuery("ismodel", node=walker, exists=True):
            return walker
        parents = cmds.listRelatives(walker, parent=True, fullPath=True)
        walker = parents[0] if parents else None
    return None


def apply_control_shapes_library(library_path, guide_model):
    """Merge the '*_controlBuffer' curves found in an external Maya scene
    file into `guide_model`'s own "controllers_org" group, so mGear's own
    build step (Component.addCtl) shapes each matching control from them
    automatically - this is exactly mGear's native hand-authored control
    buffer mechanism (see shifter/__init__.py addCtl: it looks up
    "<control_name>_controlBuffer" in the guide's controllers dict and, if
    found, moves that buffer curve's shape onto the freshly built control
    instead of using the component's default icon shape). This function
    just sources those buffer curves from a shared external file instead of
    requiring them to be hand-authored in every guide.

    Must be called AFTER the guide (and its controllers_org group, created
    by mGear's initialHierarchy) exists, and BEFORE buildFromSelection()/
    build() runs for it - mGear only reads controllers_org once, right at
    the start of the build.

    Args:
        library_path (str): path to a .ma/.mb file containing one or more
            transforms named "<something>_controlBuffer" (anywhere in its
            hierarchy - everything else in the file is ignored and discarded).
        guide_model (str): long name of the guide's top-level model
            transform (e.g. from find_guide_model() or mgear's rig_guide.model).

    Returns:
        int: number of buffer curves applied (0 if nothing happened).
    """
    if not library_path or not os.path.exists(library_path):
        if library_path:
            cmds.warning("Control Shapes Library not found: {}".format(library_path))
        return 0
    if not guide_model or not cmds.objExists(guide_model):
        return 0

    controllers_org = None
    for child in cmds.listRelatives(guide_model, children=True, fullPath=True) or []:
        if child.split("|")[-1] == "controllers_org":
            controllers_org = child
            break
    if not controllers_org:
        # mGear always creates this in initialHierarchy(); guard anyway so a
        # hand-built or unusual guide doesn't just silently no-op.
        controllers_org = cmds.group(name="controllers_org", empty=True, parent=guide_model)
        cmds.setAttr(controllers_org + ".visibility", 0)

    ns = "KRT_CTLSHAPES_TMP"
    n = 1
    while cmds.namespace(exists=ns):
        ns = "KRT_CTLSHAPES_TMP{}".format(n)
        n += 1

    try:
        imported = cmds.file(library_path, i=True, namespace=ns, ignoreVersion=True,
                              mergeNamespacesOnClash=False, preserveReferences=False,
                              returnNewNodes=True) or []
    except Exception:
        traceback.print_exc()
        cmds.warning("Failed to import Control Shapes Library '{}' - see Script Editor.".format(library_path))
        return 0

    applied = 0
    try:
        existing = {c.split("|")[-1]: c for c in
                    (cmds.listRelatives(controllers_org, children=True, fullPath=True) or [])}

        for node in imported:
            if not cmds.objExists(node) or cmds.nodeType(node) != "transform":
                continue
            short = node.split("|")[-1].split(":")[-1]
            if not short.endswith("_controlBuffer"):
                continue

            # Drop any buffer of the same name already sitting under
            # controllers_org BEFORE renaming the incoming one into its
            # place, so Maya doesn't auto-uniquify the new name instead.
            old = existing.get(short)
            if old and cmds.objExists(old):
                try:
                    cmds.delete(old)
                except Exception:
                    pass

            try:
                clean = cmds.rename(node, short)
                clean = cmds.parent(clean, controllers_org)[0]
                applied += 1
            except Exception:
                continue
    finally:
        # Anything left behind from the import - the library file's own
        # "guide"/"controllers_org" grouping, unrelated locators/roots, etc -
        # isn't a buffer curve and was never moved out, so it's still sitting
        # under its original namespaced name: sweep it away, then the
        # now-empty temp namespace.
        leftovers = [n for n in imported if cmds.objExists(n)]
        if leftovers:
            try:
                cmds.delete(leftovers)
            except Exception:
                pass
        try:
            if cmds.namespace(exists=ns):
                cmds.namespace(removeNamespace=ns, mergeNamespaceWithRoot=True)
        except Exception:
            pass

    if applied:
        cmds.warning("Control Shapes Library: applied {} buffer curve(s) from '{}'.".format(applied, library_path))
    return applied


######################################
# SkinCluster helpers (KRT-owned, cmds-only - no PyMEL dependency)
#
# These back the skinCluster panel's "always add missing influences on
# import" and "own canonical skinCluster name" behavior. Everything here
# finds a mesh's skinCluster by walking its construction HISTORY, never by
# a stored/expected name, so it stays correct even after a user manually
# renames a skinCluster in the Outliner - exactly the case that used to
# desync KRT's naming from the scene.
######################################

SKINCLUSTER_SUFFIX = "_SkinCluster"


def canonical_skincluster_name(mesh):
    """The one canonical skinCluster name KRT expects for `mesh`: its own
    short (namespace/hierarchy-stripped) name plus '_SkinCluster'. A
    skinCluster named this way never has to be located by name - it's just
    what KRT creates and what the naming-convention check looks for."""
    short = mesh.split("|")[-1]
    short = short.split(":")[-1]
    return "{}{}".format(short, SKINCLUSTER_SUFFIX)


def find_mesh_skincluster(mesh):
    """Find the skinCluster actually deforming `mesh`, via construction
    history - NOT by name. Returns None if the mesh has no skinCluster."""
    if not mesh or not cmds.objExists(mesh):
        return None
    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape in shapes:
        try:
            skins = cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []
        except Exception:
            skins = []
        if not skins:
            continue
        for skin in skins:
            try:
                geo = cmds.skinCluster(skin, query=True, geometry=True) or []
            except Exception:
                geo = []
            if shape in (cmds.ls(geo, long=True) or []):
                return skin
        # Fallback: didn't find an exact geometry match above (unusual
        # multi-shape setups) - the first skinCluster in this shape's own
        # history is still the best guess.
        return skins[0]
    return None


def ensure_skin_influences(mesh, joints, skin_name=None):
    """Make sure `mesh`'s skinCluster (found by history, not name) has
    every joint in `joints` as an influence, adding any missing ones at 0
    weight. If the mesh has no skinCluster yet, creates one (named
    canonically, or `skin_name` if given) bound to exactly `joints`.

    Returns the skinCluster's name, or None if nothing could be done.

    This is the fix for saved skin breaking a mesh on reapply: mgear's own
    skin.importSkin() silently DROPS the stored weight for any influence
    that isn't already on the target skinCluster (see
    setInfluenceWeights() in mgear/core/skin.py) instead of adding it -
    which leaves that vertex's weights not summing to 1.0 and visibly
    distorts the mesh. Calling this before importSkin() so every stored
    influence is already present avoids that entirely.
    """
    joints = [j for j in (joints or []) if j and cmds.objExists(j)]
    skin = find_mesh_skincluster(mesh)

    if not skin:
        if not joints:
            return None
        name = skin_name or canonical_skincluster_name(mesh)
        try:
            result = cmds.skinCluster(
                joints, mesh, toSelectedBones=True, name=name,
                bindMethod=0, skinMethod=0, normalizeWeights=1,
                maximumInfluences=max(1, min(8, len(joints))),
                obeyMaxInfluences=False)
            return result[0] if result else None
        except Exception:
            traceback.print_exc()
            return None

    current = cmds.skinCluster(skin, query=True, influence=True) or []
    current_short = set(c.split("|")[-1] for c in current)
    missing = []
    for jnt in joints:
        short = jnt.split("|")[-1]
        if short in current_short:
            continue
        missing.append(jnt)
        current_short.add(short)  # guards against dupes inside `joints` itself

    if missing:
        try:
            # One call for every missing influence, not one call PER
            # missing influence (-addInfluence/-ai is a multi-use flag -
            # cmds accepts a list here and issues it as a single command).
            # A skinCluster covering a heavy mesh reallocates its WHOLE
            # weight array on every -addInfluence edit, so adding
            # influences one at a time (as this used to) meant one full
            # reallocation - and, with undo left on, one full undo-queue
            # snapshot of that array - PER missing joint. On a file with
            # hundreds of stored influences (a full character body/face
            # rig easily has 500+) that's hundreds of full-size
            # reallocations and undo snapshots for a single import, which
            # is the kind of thing that can run a machine out of memory.
            # Batching into one call cuts that to a single reallocation/
            # undo entry for the whole missing set.
            cmds.skinCluster(skin, edit=True, addInfluence=missing, weight=0, lockWeights=False)
        except Exception:
            traceback.print_exc()
    return skin


def _load_skin_file_data(file_path):
    """Raw read of a .jSkin/.gSkin/.json skin export - json for everything
    except mgear's own pickle-based .gSkin format. Raises on failure;
    callers decide how to handle that."""
    if file_path.endswith(".gSkin"):
        with open(file_path, "rb") as fp:
            return pickle.load(fp)
    with open(file_path, "r") as fp:
        return json.load(fp)


def read_skin_file_meshes(file_path):
    """Every mesh name a saved skin file covers (that still exists in the
    scene), read from its objDDic - the same set mgear's own
    skin.importSkin() will process regardless of any Meshes-field filter
    (see ensure_skin_ready_for_import). Shared by that pre-import influence
    fix and the pre-import naming check (Stage 16) so both agree on exactly
    what an import is about to touch. Returns [] on any read failure rather
    than raising - a caller can still attempt the real import even if this
    couldn't read the file."""
    try:
        data_pack = _load_skin_file_data(file_path)
    except Exception:
        traceback.print_exc()
        return []
    meshes = []
    for obj_data in data_pack.get("objDDic", []) or []:
        mesh = obj_data.get("objName")
        if mesh and cmds.objExists(mesh) and mesh not in meshes:
            meshes.append(mesh)
    return meshes


def ensure_skin_ready_for_import(file_path, meshes=None):
    """Read a .jSkin/.gSkin export and, for every mesh it covers (or just
    the ones in `meshes` if given), make sure that mesh's CURRENT
    skinCluster already has every influence joint the file expects - see
    ensure_skin_influences(). Call this BEFORE mgear.core.skin.importSkin()
    runs. Any failure here is swallowed (printed, not raised) so the
    actual import can still be attempted even if this pre-pass couldn't
    read the file."""
    try:
        data_pack = _load_skin_file_data(file_path)
    except Exception:
        traceback.print_exc()
        return

    wanted = set(m for m in (meshes or []) if m) or None
    for obj_data in data_pack.get("objDDic", []) or []:
        mesh = obj_data.get("objName")
        if not mesh or not cmds.objExists(mesh):
            continue
        if wanted and mesh not in wanted:
            continue
        joints = list((obj_data.get("weights") or {}).keys())
        if not joints:
            continue
        try:
            ensure_skin_influences(mesh, joints)
        except Exception:
            traceback.print_exc()


def find_mismatched_skinclusters(meshes=None):
    """Meshes whose skinCluster's name doesn't match KRT's
    '<mesh>_SkinCluster' convention (canonical_skincluster_name). Returns a
    list of (mesh, current_skin_name, canonical_name) tuples.

    With `meshes` given, only THOSE specific meshes are checked (via
    find_mesh_skincluster - construction history, not name) - this is how
    the Stage 16 naming check is scoped to just the mesh(es) actually
    involved in the save/import that's about to happen, instead of the
    whole scene. Leave `meshes` as None to scan every skinCluster in the
    scene instead (the original, scene-wide behavior)."""
    mismatches = []
    if meshes is not None:
        seen = set()
        for mesh in meshes:
            if not mesh or mesh in seen or not cmds.objExists(mesh):
                continue
            seen.add(mesh)
            skin = find_mesh_skincluster(mesh)
            if not skin:
                continue
            canonical = canonical_skincluster_name(mesh)
            if skin != canonical:
                mismatches.append((mesh, skin, canonical))
        return mismatches

    seen_skins = set()
    for skin in cmds.ls(type="skinCluster") or []:
        if skin in seen_skins:
            continue
        seen_skins.add(skin)
        try:
            geo = cmds.skinCluster(skin, query=True, geometry=True) or []
        except Exception:
            geo = []
        for shape in geo:
            if not cmds.objExists(shape):
                continue
            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            if not parents:
                continue
            mesh = parents[0]
            canonical = canonical_skincluster_name(mesh)
            if skin != canonical:
                mismatches.append((mesh, skin, canonical))
    return mismatches


def rename_mismatched_skinclusters(mismatches):
    """Rename every (mesh, current_skin_name, canonical_name) triple from
    find_mismatched_skinclusters() to its canonical name. Returns the
    number successfully renamed."""
    renamed = 0
    for mesh, current, canonical in mismatches:
        if not cmds.objExists(current):
            continue
        if cmds.objExists(canonical) and canonical != current:
            # Extremely unlikely (two meshes sharing a short name) - don't
            # clobber an unrelated node, just skip it.
            cmds.warning("[KRT] Can't rename '{}' to '{}': a node with that "
                         "name already exists.".format(current, canonical))
            continue
        try:
            cmds.rename(current, canonical)
            renamed += 1
        except Exception:
            traceback.print_exc()
    return renamed


# ---------------------------------------------------------------------------
# Re-skin (unbind + rebind, keeping weights) - KRT SkinCluster panel
# ---------------------------------------------------------------------------
# A direct port of the studio's own "RGreSkin" MEL tool, supplied as working
# Python by the rigger. The command sequence is kept deliberately faithful -
# skinCluster -e -ubk (unbind but KEEP history, so the weights survive),
# clear the stale bind-pose node(s), then rebind to the same influences -
# because that exact sequence is what the studio relies on and none of it can
# be verified from outside Maya.
#
# The ONE deliberate change from the original: it deleted every node in the
# scene matching "*bindPose*", which in a scene holding more than one
# character would also wipe unrelated rigs' bind poses. This scopes the
# delete to the dagPose nodes actually connected to the influences being
# rebound, which is the same set in a single-character scene and strictly
# safer in any other.

def _bind_poses_for_joints(joints):
    """dagPose (bindPose) nodes connected to any of these influences."""
    poses = set()
    for jnt in joints or []:
        try:
            poses.update(cmds.listConnections(jnt, type="dagPose", source=False, destination=True) or [])
        except Exception:
            continue
    return sorted(poses)

def re_skin_meshes(meshes=None):
    """Unbind and re-bind each mesh to its own existing skinCluster
    influences, keeping the weights. Returns (count, errors)."""
    try:
        import maya.mel as mel
    except Exception:
        mel = None

    # An empty list means the same thing as None here ("nothing was given"),
    # so both fall back to the selection rather than one silently erroring.
    if not meshes:
        meshes = cmds.ls(selection=True) or []
    meshes = [m for m in meshes if m]
    if not meshes:
        return 0, ["Nothing selected/listed to re-skin - select a skinned mesh first."]

    done, errors = 0, []
    for obj in meshes:
        if not cmds.objExists(obj):
            errors.append("'{}' does not exist in the scene.".format(obj))
            continue

        skin_cluster = None
        if mel is not None:
            try:
                skin_cluster = mel.eval('findRelatedSkinCluster("{}")'.format(obj)) or None
            except Exception:
                skin_cluster = None
        if not skin_cluster:
            # Same answer, found through construction history instead of
            # mGear/Maya's MEL helper (which needs the transform name and
            # can come back empty for a shape or a namespaced node).
            skin_cluster = find_mesh_skincluster(obj)
        if not skin_cluster:
            errors.append("'{}' has no skinCluster - skipped.".format(obj))
            continue

        shapes = cmds.ls(obj, dag=True, shapes=True, noIntermediate=True) or []
        if not shapes:
            errors.append("'{}' has no shape node - skipped.".format(obj))
            continue
        shape = shapes[0]

        try:
            joints = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
            if not joints:
                errors.append("'{}' skinCluster has no influences - skipped.".format(obj))
                continue

            # Unbind but keep the history, so the weights survive.
            cmds.skinCluster(shape, edit=True, unbindKeepHistory=True)

            for pose in _bind_poses_for_joints(joints):
                try:
                    cmds.delete(pose)
                except Exception:
                    pass

            cmds.skinCluster(joints, shape)
            done += 1
        except Exception as e:
            errors.append("'{}' failed to re-skin: {}".format(obj, e))
    return done, errors


######################################
# Crash logging / last-session recovery (Stage 16)
#
# Two independent signals, both read once at launch by
# check_last_session_health() and then combined by main.py into one
# "here's what happened last time" popup:
#
#   1. An actual logged error - anything KRT's own top-level exception
#      handlers (tool launch, a rig build batch, a custom script) caught
#      and passed to log_crash(). This is the specific, readable case:
#      "here's exactly what went wrong."
#   2. An unclean exit - a small marker file written at the START of every
#      run (mark_session_start) and only ever removed at a NORMAL close
#      (mark_session_clean_exit, from KRT_Tool.closeEvent). If that marker
#      is still there the next time KRT opens, the previous run never
#      reached a normal close - almost always Maya itself going down
#      (a hard crash), since a plain Python exception inside KRT still
#      leaves the window open to be closed normally afterward.
#
# Neither of these can catch a true native crash while it happens (nothing
# running inside the process can log after Maya itself dies) - the marker
# file is what stands in for that case, at the cost of only being able to
# say "something ended badly", not why.
######################################

def _krt_log_dir():
    base = os.path.join(cmds.internalVar(userAppDir=True), "KRT").replace("\\", "/")
    if not os.path.exists(base):
        try:
            os.makedirs(base)
        except Exception:
            pass
    return base


def _crash_log_path():
    return os.path.join(_krt_log_dir(), "crash_log.txt")


def _session_marker_path():
    return os.path.join(_krt_log_dir(), "session_active.json")


def log_crash(context, exc=None, extra=""):
    """Append one timestamped entry to KRT's crash log. Call this from
    KRT's own top-level exception handlers - tool launch (main.py),
    a module/rig build batch (widgets.py), custom script execution
    (workspace.py) - anywhere an error is already being caught and shown
    in KRT's own UI, so it's ALSO durably saved for
    check_last_session_health() to surface next time KRT opens. Never
    raises itself - a failure to log must never mask the original error,
    so any problem writing the log file is just swallowed."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = ["=" * 70, "[{}] {}".format(ts, context)]
        if exc is not None:
            lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())
        elif extra:
            lines.append(str(extra).rstrip())
        lines.append("")
        with open(_crash_log_path(), "a") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def mark_session_start():
    """Call once, right as KRT starts opening (before anything risky runs).
    See the module-level note above for how this pairs with
    mark_session_clean_exit()/check_last_session_health()."""
    try:
        with open(_session_marker_path(), "w") as f:
            json.dump({"started_readable": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except Exception:
        pass


def mark_session_clean_exit():
    """Call from KRT_Tool.closeEvent - a normal close, so the marker
    mark_session_start() wrote no longer means anything and shouldn't be
    reported as a crash next launch."""
    try:
        p = _session_marker_path()
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


def check_last_session_health():
    """Call once, right when KRT opens, BEFORE mark_session_start()
    overwrites the marker for this new run. Reads (and, for the crash log,
    CONSUMES - clears it after reading) whatever the previous run left
    behind, so the same old error only ever gets reported once.

    Returns {"unclean_exit": bool, "started_readable": str_or_None,
    "last_error": str_or_None}."""
    result = {"unclean_exit": False, "started_readable": None, "last_error": None}

    marker = _session_marker_path()
    if os.path.exists(marker):
        result["unclean_exit"] = True
        try:
            with open(marker, "r") as f:
                result["started_readable"] = json.load(f).get("started_readable")
        except Exception:
            pass

    log_path = _crash_log_path()
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                content = f.read()
            blocks = [b.strip() for b in content.split("=" * 70) if b.strip()]
            if blocks:
                result["last_error"] = blocks[-1]
        except Exception:
            pass
        finally:
            try:
                os.remove(log_path)
            except Exception:
                pass

    return result

######################################################################
# Fast SkinCluster save/import (performance)
######################################################################
# mgear.core.skin's exportSkin()/importSkin() are what actually run
# behind KRT's SkinCluster (JSON) and Tweaker panels' "Save Skin" /
# skin-file import. Both already read/write the WHOLE weight buffer in
# a single bulk OpenMaya call (getWeights/setWeights), so that part was
# never the slow part. The slow part is the plain Python loop on either
# side of that buffer that walks EVERY vertex for EVERY influence to
# build (export) or apply (import) the per-influence weight dict, even
# though the file format itself only stores non-zero weights. For a
# mesh with, say, 40k vertices and 80 influences that's ~3.2 million
# individual Python-level dict lookups / MDoubleArray.set() calls -
# each one carrying real interpreter + SWIG-call overhead - which is
# what actually makes Save/Import Skin slow on heavy meshes. On export,
# mgear also always writes the JSON pretty-printed and key-sorted
# (`indent=4, sort_keys=True`), which forces Python's pure-Python JSON
# encoder instead of the C-accelerated one for a large nested dict like
# a dense weights export - a second, separate slowdown on top of the
# loop.
#
# fast_export_skin()/fast_import_skin() below are drop-in replacements
# for mgear.core.skin.exportSkin()/importSkin() that KRT's Save Skin /
# skin-import call sites now use instead. They produce/consume the
# EXACT same .jSkin/.gSkin schema - a file saved here opens fine in
# vanilla mgear, and a file saved by vanilla mgear (or an older KRT
# session) imports fine here - only the hot per-vertex loop and the
# JSON formatting are different:
#   - When numpy is importable (it ships with Maya's own Python since
#     2022) the whole per-influence sparse extraction/scatter is done
#     with vectorized numpy calls instead of a Python-level loop.
#   - Without numpy, a still-meaningfully-faster pure-Python path is
#     used: it converts the OpenMaya weight buffer to a plain list ONCE
#     (avoiding repeated SWIG-wrapped indexing) and, on import, zeroes
#     each replaced influence's column with a single slice assignment
#     instead of one MDoubleArray.set() call per vertex.
# Everything else - skinCluster lookup/creation, blend weights,
# skinningMethod/normalizeWeights attributes, and (on import) any
# vertex-count MISMATCH - is delegated straight to mgear.core.skin,
# completely unchanged, so every edge case mgear already handles keeps
# working exactly as before. If anything in the fast path raises for
# any reason, both functions fall back to calling mgear.core.skin's own
# exportSkin()/importSkin(), so a bug here can only make a save/import
# slower, never break it.
#
# NOT tested live in Maya (this sandbox cannot run Maya) - verified via
# py_compile, an AST duplicate-method scan, and stub tests that replay
# this exact logic against hand-built stand-ins for the OpenMaya calls.
# Please try it on a real heavy mesh before relying on it, and report
# back if Save/Import Skin still feels slow or anything looks off.
try:
    import numpy as _np
except Exception:
    _np = None


def _fast_collect_influence_weights(skin_fn, dag_path, components, influence_paths, num_influences):
    """Fast equivalent of mgear.core.skin.collectInfluenceWeights() - same
    output shape ({influenceName: {vtxIdx: weight, ...}, ...}, non-zero
    entries only), built via vectorized nonzero-extraction (or, without
    numpy, a single flat-list conversion up front) instead of a
    per-vertex-per-influence Python loop that indexes the raw OpenMaya
    array twice per vertex. Returns (weights_dict, num_verts, influence_names)."""
    weights = om.MDoubleArray()
    util = om.MScriptUtil()
    util.createFromInt(0)
    p_uint = util.asUintPtr()
    skin_fn.getWeights(dag_path, components, weights, p_uint)

    total = weights.length()
    num_verts = int(total / num_influences) if num_influences else 0

    influence_names = [
        om.MFnDependencyNode(influence_paths[i].node()).name().split(":")[-1]
        for i in range(influence_paths.length())
    ]

    out = {}
    if _np is not None and total:
        flat = _np.fromiter((weights[i] for i in range(total)), dtype=_np.float64, count=total)
        arr = flat.reshape(num_verts, num_influences)
        for ii, name in enumerate(influence_names):
            col = arr[:, ii]
            nz = _np.flatnonzero(col)
            out[name] = dict(zip(nz.tolist(), col[nz].tolist())) if nz.size else {}
    else:
        flat = [weights[i] for i in range(total)]
        for ii, name in enumerate(influence_names):
            inf_w = {}
            base = ii
            for jj in range(num_verts):
                w = flat[base]
                if w != 0.0:
                    inf_w[jj] = w
                base += num_influences
            out[name] = inf_w

    return out, num_verts, influence_names


def _fast_apply_influence_weights(skin_fn, dag_path, components, weights_dict, num_influences, influence_paths):
    """Fast equivalent of mgear.core.skin.setInfluenceWeights() - same net
    effect (every vertex of every imported influence is replaced,
    defaulting to 0.0 for vertices missing from that influence's sparse
    entry; influences not present in the file keep their current
    weight), but the scatter is vectorized (numpy) or done via a single
    strided slice-assignment per influence (pure-Python fallback)
    instead of one MDoubleArray.set() call per vertex per influence.
    Returns the list of imported influence names not found on this
    skinCluster (skipped, matching mgear's own behavior)."""
    weights = om.MDoubleArray()
    util = om.MScriptUtil()
    util.createFromInt(0)
    p_uint = util.asUintPtr()
    skin_fn.getWeights(dag_path, components, weights, p_uint)

    total = weights.length()
    num_verts = int(total / num_influences) if num_influences else 0

    influence_map = {
        om.MFnDependencyNode(influence_paths[ii].node()).name().split(":")[-1]: ii
        for ii in range(influence_paths.length())
    }

    unused_imports = []

    if _np is not None and total:
        flat = _np.fromiter((weights[i] for i in range(total)), dtype=_np.float64, count=total)
        arr = flat.reshape(num_verts, num_influences)
        for name, wt_values in weights_dict.items():
            ii = influence_map.get(name)
            if ii is None:
                unused_imports.append(name)
                continue
            arr[:, ii] = 0.0
            if wt_values:
                keys = list(wt_values.keys())
                idx = _np.fromiter((int(k) for k in keys), dtype=_np.int64, count=len(keys))
                vals = _np.fromiter((float(wt_values[k]) for k in keys), dtype=_np.float64, count=len(keys))
                arr[idx, ii] = vals
        new_flat = arr.reshape(-1).tolist()
    else:
        new_flat = [weights[i] for i in range(total)]
        for name, wt_values in weights_dict.items():
            ii = influence_map.get(name)
            if ii is None:
                unused_imports.append(name)
                continue
            new_flat[ii::num_influences] = [0.0] * num_verts
            for k, wt in wt_values.items():
                new_flat[int(k) * num_influences + ii] = wt

    try:
        new_weights = om.MDoubleArray(new_flat)
    except Exception:
        # Some Maya/SWIG versions don't accept a plain Python list in the
        # MDoubleArray constructor - fall back to the same element-by-
        # element approach mgear's own code uses (still correct, just no
        # faster than before for this one call).
        new_weights = om.MDoubleArray()
        new_weights.setLength(total)
        for i, v in enumerate(new_flat):
            new_weights.set(v, i)

    influence_indices = om.MIntArray()
    influence_indices.setLength(num_influences)
    for i in range(num_influences):
        influence_indices[i] = i

    skin_fn.setWeights(dag_path, components, influence_indices, new_weights, False)
    return unused_imports


def fast_export_skin(file_path, objs=None):
    """Fast drop-in replacement for mgear.core.skin.exportSkin() - same
    .jSkin/.gSkin file, same schema, only the influence-weight collection
    loop and (for .jSkin) the JSON write are different - see the module
    docstring above. Falls back to mgear's own exportSkin() on any
    error, so a bug here can only make a save slower, never break it.
    NOT tested live in Maya."""
    try:
        import mgear.pymaya as pm
        from mgear.core import skin as mgear_skin

        if not objs:
            objs = pm.selected()
        if not objs:
            cmds.warning("[KRT] Please select one or more skinned meshes.")
            return False

        if not (file_path.endswith(mgear_skin.FILE_EXT) or file_path.endswith(mgear_skin.FILE_JSON_EXT)):
            cmds.warning("[KRT] Not a valid skin file extension: {}".format(file_path))
            return False

        pack_dic = {"objs": [], "objDDic": [], "bypassObj": []}

        for obj in objs:
            skin_cls = mgear_skin.getSkinCluster(obj)
            if not skin_cls:
                cmds.warning("[KRT] {}: skipped, no skinCluster.".format(obj.name()))
                continue

            skin_fn = mgear_skin.get_skin_cluster_fn(skin_cls.name())
            dag_path, components = mgear_skin.getGeometryComponents(skin_cls)

            influence_paths = om.MDagPathArray()
            num_influences = skin_fn.influenceObjects(influence_paths)

            weights_dict, num_verts, _names = _fast_collect_influence_weights(
                skin_fn, dag_path, components, influence_paths, num_influences)

            blend_weights = om.MDoubleArray()
            skin_fn.getBlendWeights(dag_path, components, blend_weights)
            blend_dict = {
                i: round(blend_weights[i], 6)
                for i in range(blend_weights.length())
                if round(blend_weights[i], 6) != 0.0
            }

            data_dic = {
                "weights": weights_dict,
                "blendWeights": blend_dict,
                "skinClsName": skin_cls.name(),
                "objName": obj.name(),
                "nameSpace": obj.namespace(),
                "vertexCount": num_verts,
                "skinDataFormat": "compressed",
                "skinningMethod": skin_cls.attr("skinningMethod").get(),
                "normalizeWeights": skin_cls.attr("normalizeWeights").get(),
            }

            pack_dic["objs"].append(obj.name())
            pack_dic["objDDic"].append(data_dic)
            cmds.warning(
                "[KRT] Exported skinCluster {} ({} influences, {} verts) {}".format(
                    skin_cls.name(), len(weights_dict), num_verts, obj.name()))

        if not pack_dic["objs"]:
            return False

        if file_path.endswith(mgear_skin.FILE_EXT):
            with open(file_path, "wb") as fp:
                pickle.dump(pack_dic, fp, pickle.HIGHEST_PROTOCOL)
        else:
            # Compact, not pretty - see module docstring: indent/sort_keys
            # is its own separate slowdown on a large weights export.
            with open(file_path, "w") as fp:
                json.dump(pack_dic, fp, separators=(",", ":"))

        return True
    except Exception as e:
        traceback.print_exc()
        cmds.warning("[KRT] Fast skin export failed ({}) - falling back to mgear's exporter...".format(e))
        try:
            from mgear.core import skin as mgear_skin
            return mgear_skin.exportSkin(file_path, objs)
        except Exception as e2:
            om.MGlobal.displayError("Skin export failed: {}".format(e2))
            return False


def fast_import_skin(file_path, vertex_mismatch_mode="auto"):
    """Fast drop-in replacement for mgear.core.skin.importSkin() for the
    common case where vertex counts match (no closest-point/volume
    transfer needed) - only the influence-weight scatter loop is
    different, see the module docstring above. skinCluster lookup/
    creation, blend weights, skinningMethod/normalizeWeights, and any
    vertex-count MISMATCH are all delegated straight to
    mgear.core.skin's own importSkin(), per-object, unchanged. Falls
    back to mgear's importSkin() for the whole file on any error.
    NOT tested live in Maya."""
    try:
        import mgear.pymaya as pm
        from mgear.core import skin as mgear_skin

        if file_path.endswith(mgear_skin.FILE_EXT):
            with open(file_path, "rb") as fp:
                data_pack = pickle.load(fp)
        else:
            with open(file_path, "r") as fp:
                data_pack = json.load(fp)

        volume_imported = []

        for data in data_pack.get("objDDic", []) or []:
            compressed = data.get("skinDataFormat") == "compressed"
            obj_name = data.get("objName")
            if not obj_name or not cmds.objExists(obj_name):
                cmds.warning("[KRT] Object: {} skipped, not found in the scene.".format(obj_name))
                continue

            try:
                obj_node = pm.PyNode(obj_name)
                is_mesh = isinstance(obj_node.getShape(), pm.nodetypes.Mesh)
                mesh_vertices = cmds.polyEvaluate(obj_name, vertex=True) if is_mesh else None
                imported_vertices = data.get("vertexCount") if compressed else len(data.get("blendWeights") or [])
                vertex_mismatch = (not is_mesh) or (mesh_vertices != imported_vertices)
            except Exception:
                vertex_mismatch = True

            if vertex_mismatch:
                # Not the case this fast path optimizes for (nurbs, or a
                # real vertex-count mismatch needing closest-point
                # matching). IMPORTANT: this calls mgear's PER-OBJECT
                # volume importer directly with the data already in
                # memory, not mgear_skin.importSkin(file_path, ...) -
                # that reads and reprocesses EVERY object in the file
                # again, so on a multi-mesh file (a body + teeth + eyes,
                # say) one mismatched object used to mean re-importing
                # the whole file, including meshes already handled above,
                # once per mismatch - a real memory/time multiplier on a
                # heavy file, and a likely contributor to imports
                # ballooning Maya's memory and crashing the machine.
                if vertex_mismatch_mode == "skip":
                    cmds.warning("[KRT] {}: vertex count mismatch, skipped.".format(obj_name))
                    continue
                skin_cls = mgear_skin.getSkinCluster(obj_node)
                if not skin_cls:
                    try:
                        joints = list((data.get("weights") or {}).keys())
                        skin_name = (data.get("skinClsName") or "").replace("|", "")
                        skin_cls = pm.skinCluster(joints, obj_node, tsb=True, nw=2, n=skin_name)
                        if isinstance(skin_cls, list):
                            skin_cls = skin_cls[0]
                    except Exception:
                        cmds.warning(
                            "[KRT] {}: vertex mismatch, and couldn't create a skinCluster for volume import.".format(obj_name))
                        continue
                success = mgear_skin._importSkinVolumeMethod(obj_node, skin_cls, data, compressed)
                if success:
                    volume_imported.append(obj_name)
                data["weights"] = None
                data["blendWeights"] = None
                gc.collect()
                continue

            skin_cls = mgear_skin.getSkinCluster(obj_node)
            if not skin_cls:
                try:
                    joints = list((data.get("weights") or {}).keys())
                    skin_name = (data.get("skinClsName") or "").replace("|", "")
                    skin_cls = pm.skinCluster(joints, obj_node, tsb=True, nw=2, n=skin_name)
                    if isinstance(skin_cls, list):
                        skin_cls = skin_cls[0]
                except Exception:
                    scene_joints = set(j.name() for j in pm.ls(type="joint"))
                    not_found = [j for j in (data.get("weights") or {}).keys() if j not in scene_joints]
                    cmds.warning("[KRT] Object: {} skipped, missing joints: {}".format(obj_name, not_found))
                    continue

            skin_fn = mgear_skin.get_skin_cluster_fn(skin_cls.name())
            dag_path, components = mgear_skin.getGeometryComponents(skin_cls)
            influence_paths = om.MDagPathArray()
            num_influences = skin_fn.influenceObjects(influence_paths)

            unused = _fast_apply_influence_weights(
                skin_fn, dag_path, components, data.get("weights") or {},
                num_influences, influence_paths)
            if unused:
                cmds.warning("[KRT] {}: influences in file not on this skinCluster (skipped): {}".format(
                    obj_name, unused))

            for attr in ("skinningMethod", "normalizeWeights"):
                if attr in data:
                    try:
                        skin_cls.attr(attr).set(data[attr])
                    except Exception:
                        pass

            try:
                mgear_skin.setBlendWeights(skin_cls, dag_path, components, data, compressed)
            except Exception:
                traceback.print_exc()

            cmds.warning("[KRT] Imported skin for: {}".format(obj_name))

            # A file can cover several heavy meshes in one go (a body plus
            # teeth/eyes, say) - data_pack keeps every object's parsed
            # weight dict alive for the whole function otherwise, even
            # ones already applied. Drop this object's now-unneeded data
            # and force a collection before moving to the next one, so
            # peak memory tracks ONE mesh's weight data at a time instead
            # of accumulating across the whole file.
            data["weights"] = None
            data["blendWeights"] = None
            gc.collect()

        return volume_imported
    except Exception as e:
        traceback.print_exc()
        cmds.warning("[KRT] Fast skin import failed ({}) - falling back to mgear's importer...".format(e))
        try:
            from mgear.core import skin as mgear_skin
            return mgear_skin.importSkin(file_path, vertexMismatchMode=vertex_mismatch_mode)
        except Exception as e2:
            om.MGlobal.displayError("Skin import failed: {}".format(e2))
            return []
