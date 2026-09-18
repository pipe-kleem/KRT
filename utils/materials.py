"""Auto-split from utils.py."""
from ._shared import *
from .paths import get_versioned_path


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
