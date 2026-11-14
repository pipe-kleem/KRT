"""
wrap_to_bs_fast.py
==================
High-performance blendShape transfer via wrap deformer.

Transfers every blendShape target from a source mesh onto one or more target
meshes by wrapping the targets to the source, toggling each shape, and capturing
the resulting deformation.

Optimisations over the naive implementation:
  1.  Viewport is fully disabled for the duration of the batch (no redraws).
  2.  No per-target cmds.refresh() -- evaluation is forced via the DG only.
  3.  Undo queue disabled during the batch.
  4.  Evaluation manager forced to serial DG (predictable, no thread sync churn).
  5.  The classic `wrap` deformer is built by hand with speed-optimal settings
      (exclusiveBind, point influence, bounded maxDistance, volume falloff) and
      a SINGLE shared base mesh for all targets -- cmds.CreateWrap creates a new
      base duplicate per call and defaults to the slowest possible settings.
  6.  FAST mode: point positions read with OpenMaya 2.0 and injected directly
      into the blendShape node as deltas -- zero duplicate geometry created.
      SAFE mode (duplicate-based) retained as a fallback.

Usage
-----
    import wrap_to_bs_fast as w
    reload(w)

    w.wrapToBs("head_GEO", ["helmet_GEO", "hair_GEO"])

    # explicit blendshape node, subset of shapes, safe mode, looser bind
    w.wrapToBs(
        "head_GEO",
        ["helmet_GEO"],
        srcBs="blendShape1",
        onlyTargets=["browRaise_L", "browRaise_R"],
        mode="safe",
        maxDistance=0.0,      # 0 = unbounded search (slower, but never misses)
    )

Author: KLEEM RND
"""

import re
import time
import contextlib

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om2


# ============================================================
# CONSTANTS
# ============================================================

FAST = "fast"          # OpenMaya delta injection, no duplicate geometry
SAFE = "safe"          # duplicate geometry + cmds.blendShape

# ---- wrap deformer speed-optimal defaults -------------------------------
# exclusiveBind   1 -> each target point is bound to ONE driver point.
#                      Vastly cheaper than the default weighted/smooth bind
#                      and it is what you want for shape transfer anyway.
# inflType        1 -> point influence (2 = face influence, much slower).
# maxDistance     >0 -> bounds the spatial search. 0 means "search forever"
#                      and is the single biggest cost on dense meshes.
#                      Units are scene units; tune to your rig scale.
# falloffMode     0 -> volume (cheap). 1 = surface (walks topology, slow).
# autoWeightThreshold 1 -> lets Maya pick a sane threshold once at bind time.
WRAP_DEFAULTS = {
    "exclusiveBind": 1,
    "autoWeightThreshold": 1,
    "falloffMode": 0,
    "maxDistance": 1.0,
    "weightThreshold": 0.0,
    "dropoff": 4.0,
    "smoothness": 0.0,
    "inflType": 1,
}

# blendShape inputTargetItem index for a full-weight (1.0) target
FULL_WEIGHT_ITEM = 6000

# Deltas below this magnitude are discarded (per axis, object space units)
DELTA_EPSILON = 1e-6


# ============================================================
# NAME / ALIAS HELPERS
# ============================================================

def clean_maya_name(name):
    """Sanitise a string into a legal, unqualified Maya node name."""
    if "|" in name:
        name = name.split("|")[-1]
    if ":" in name:
        name = name.split(":")[-1]
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name and name[0].isdigit():
        name = "_" + name
    return name


def get_weight_index(attr_name):
    match = re.search(r"weight\[(\d+)\]", attr_name)
    return int(match.group(1)) if match else 999999


def get_blendshape_targets_in_correct_order(blendshape_node, only_targets=None):
    """Return [(weightIndex, aliasName, plug), ...] sorted by weight index."""
    aliases = cmds.aliasAttr(blendshape_node, q=True) or []
    only_set = set(only_targets) if only_targets else None
    targets = []

    for i in range(0, len(aliases), 2):
        bs_name = aliases[i]
        attr_name = aliases[i + 1]

        if not attr_name.startswith("weight["):
            continue
        if only_set and bs_name not in only_set:
            continue

        targets.append((
            get_weight_index(attr_name),
            bs_name,
            "{}.{}".format(blendshape_node, attr_name),
        ))

    targets.sort(key=lambda x: x[0])
    return targets


def get_weight_alias_map(bs_node):
    """{aliasName: plug} for every weight on a blendShape node."""
    if not cmds.objExists(bs_node):
        cmds.error("BlendShape node not found: {}".format(bs_node))

    result = {}
    aliases = cmds.aliasAttr(bs_node, q=True) or []
    for i in range(0, len(aliases), 2):
        if aliases[i + 1].startswith("weight["):
            result[aliases[i]] = "{}.{}".format(bs_node, aliases[i + 1])
    return result


def get_plug_to_alias_map(bs_node):
    return {plug: alias for alias, plug in get_weight_alias_map(bs_node).items()}


# ============================================================
# WEIGHT VALUE / CONNECTION STATE
# ============================================================

def store_current_weight_values(targets):
    values = {}
    for _, _, plug in targets:
        try:
            values[plug] = cmds.getAttr(plug)
        except Exception:
            pass
    return values


def restore_weight_values(values):
    for plug, value in values.items():
        try:
            if cmds.objExists(plug):
                cmds.setAttr(plug, value)
        except Exception:
            pass


def reset_all_blendshapes(targets):
    for _, _, plug in targets:
        try:
            if cmds.getAttr(plug) != 0:
                cmds.setAttr(plug, 0)
        except Exception:
            pass


def store_and_break_blendshape_weight_connections(targets, verbose=False):
    """Disconnect all incoming connections on the given weight plugs.

    Returns [(sourcePlug, destPlug), ...] so they can be restored later and
    re-used to drive the newly created target blendShapes.
    """
    stored = []
    for _, _, plug in targets:
        incoming = cmds.listConnections(
            plug, source=True, destination=False, plugs=True) or []

        for src_plug in incoming:
            try:
                if cmds.isConnected(src_plug, plug):
                    cmds.disconnectAttr(src_plug, plug)
                    stored.append((src_plug, plug))
                    if verbose:
                        print("  disconnected: {} -> {}".format(src_plug, plug))
            except Exception as e:
                cmds.warning("Could not disconnect {} -> {} | {}".format(src_plug, plug, e))
    return stored


def reconnect_blendshape_weight_connections(stored_connections, verbose=False):
    for src_plug, dst_plug in stored_connections:
        try:
            if not cmds.objExists(src_plug.split(".")[0]):
                continue
            if not cmds.objExists(dst_plug.split(".")[0]):
                continue
            if not cmds.isConnected(src_plug, dst_plug):
                cmds.connectAttr(src_plug, dst_plug, force=True)
                if verbose:
                    print("  reconnected: {} -> {}".format(src_plug, dst_plug))
        except Exception as e:
            cmds.warning("Could not reconnect {} -> {} | {}".format(src_plug, dst_plug, e))


# ============================================================
# PERFORMANCE CONTEXT MANAGERS
# ============================================================

@contextlib.contextmanager
def viewport_off():
    """Unmanage the main pane so Maya performs no viewport drawing at all.

    This is by far the single biggest win on high-poly meshes.
    """
    main_pane = None
    suspended = False
    try:
        try:
            main_pane = mel.eval('$tmp = $gMainPane')
        except Exception:
            main_pane = None

        if main_pane:
            cmds.paneLayout(main_pane, edit=True, manage=False)

        cmds.refresh(suspend=True)
        suspended = True
        yield
    finally:
        if suspended:
            try:
                cmds.refresh(suspend=False)
            except Exception:
                pass
        if main_pane:
            try:
                cmds.paneLayout(main_pane, edit=True, manage=True)
            except Exception:
                pass
        try:
            cmds.refresh(force=True)
        except Exception:
            pass


@contextlib.contextmanager
def undo_off():
    """Disable the undo queue -- every duplicate/setAttr would otherwise be recorded."""
    state = cmds.undoInfo(q=True, state=True)
    try:
        cmds.undoInfo(stateWithoutFlush=False)
        yield
    finally:
        cmds.undoInfo(stateWithoutFlush=state)


@contextlib.contextmanager
def serial_evaluation():
    """Force serial DG evaluation.

    Parallel/EM mode adds graph-scheduling overhead every time a single attribute
    is toggled from script, and makes dgeval() unreliable. DG mode is faster and
    deterministic for this batch pattern.
    """
    try:
        mode = cmds.evaluationManager(q=True, mode=True)[0]
    except Exception:
        mode = None
    try:
        if mode and mode != "off":
            cmds.evaluationManager(mode="off")
        yield
    finally:
        if mode and mode != "off":
            try:
                cmds.evaluationManager(mode=mode)
            except Exception:
                pass


@contextlib.contextmanager
def performance_mode(enabled=True):
    """Combined viewport / undo / evaluation optimisation context."""
    if not enabled:
        yield
        return
    with viewport_off():
        with undo_off():
            with serial_evaluation():
                yield


# ============================================================
# GEOMETRY QUERY (OpenMaya 2.0)
# ============================================================

def get_shape(transform):
    """Return the first non-intermediate mesh shape under a transform."""
    if cmds.nodeType(transform) == "mesh":
        return transform
    shapes = cmds.listRelatives(transform, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
    if not shapes:
        cmds.error("No mesh shape found under: {}".format(transform))
    return shapes[0]


def get_mfn_mesh(node):
    """MFnMesh for a transform or shape."""
    sel = om2.MSelectionList()
    sel.add(get_shape(node))
    return om2.MFnMesh(sel.getDagPath(0))


def get_points(mfn_mesh):
    """Object-space point array. C++ speed -- no Python per-vertex loop."""
    return mfn_mesh.getPoints(om2.MSpace.kObject)


def force_evaluate(nodes):
    """Force DG evaluation of the deformed output without touching the viewport.

    cmds.refresh() would trigger a full redraw; this pulls only the mesh data.
    """
    for node in nodes:
        try:
            cmds.dgeval(get_shape(node) + ".outMesh")
        except Exception:
            try:
                cmds.getAttr(node + ".boundingBox.boundingBoxMin")
            except Exception:
                pass


# ============================================================
# WRAP CREATION
# ============================================================

def get_wrap_nodes_from_targets(target_geos):
    found = set()
    for geo in target_geos:
        if not cmds.objExists(geo):
            continue
        for node in cmds.listHistory(geo, pruneDagObjects=True) or []:
            if cmds.objExists(node) and cmds.nodeType(node) == "wrap":
                found.add(node)
    return list(found)


def _ensure_driver_attrs(driver_transform, settings):
    """CreateWrap normally adds dropoff / smoothness / inflType to the influence.

    We add them ourselves so we control the values instead of inheriting the
    slow MEL defaults (inflType 2 = face influence).
    """
    specs = (
        ("dropoff", "double", settings["dropoff"]),
        ("smoothness", "double", settings["smoothness"]),
        ("inflType", "short", settings["inflType"]),
    )
    for attr, attr_type, value in specs:
        if not cmds.attributeQuery(attr, node=driver_transform, exists=True):
            if attr_type == "short":
                cmds.addAttr(driver_transform, longName=attr, attributeType="short",
                             defaultValue=value, min=1, max=2)
            else:
                cmds.addAttr(driver_transform, longName=attr, attributeType="double",
                             defaultValue=value, min=0.0)
            cmds.setAttr("{}.{}".format(driver_transform, attr), keyable=True)
        try:
            cmds.setAttr("{}.{}".format(driver_transform, attr), value)
        except Exception:
            pass


def _make_wrap_base(source_transform, source_shape):
    """Create ONE shared, hidden base (rest) mesh for the wrap.

    cmds.CreateWrap duplicates a fresh base per invocation. Sharing a single
    base across all targets removes a full high-poly duplicate per target and
    keeps every wrap referencing the same rest state.
    """
    base = cmds.duplicate(source_transform, returnRootsOnly=True,
                          name=clean_maya_name(source_transform) + "_wrapBase")[0]

    # Strip everything that could make the base evaluate or draw.
    cmds.delete(base, constructionHistory=True)
    for child in cmds.listRelatives(base, children=True, fullPath=True) or []:
        if cmds.nodeType(child) != "mesh":
            cmds.delete(child)

    base_shape = get_shape(base)
    cmds.setAttr(base + ".visibility", 0)
    cmds.setAttr(base_shape + ".intermediateObject", 0)

    return base, base_shape


def create_wrap(source_model, target_models, settings=None, verbose=True):
    """Build the classic `wrap` deformer by hand with speed-optimal settings.

    Returns (wrapNodes, cleanupNodes) -- cleanupNodes are the temporary base
    meshes that must be deleted afterwards.
    """
    if not cmds.objExists(source_model):
        cmds.error("Source model not found: {}".format(source_model))
    for geo in target_models:
        if not cmds.objExists(geo):
            cmds.error("Target model not found: {}".format(geo))

    cfg = dict(WRAP_DEFAULTS)
    if settings:
        cfg.update({k: v for k, v in settings.items() if v is not None})

    # A user-supplied custom wrap wins if one is defined in the session.
    custom = globals().get("apply_custom_wrap")
    if callable(custom):
        before = set(get_wrap_nodes_from_targets(target_models))
        custom(source_model, target_models)
        after = set(get_wrap_nodes_from_targets(target_models))
        nodes = list(after - before) or list(after)
        for node in nodes:
            _apply_wrap_settings(node, cfg)
        if not nodes:
            cmds.error("apply_custom_wrap did not produce a wrap node.")
        return nodes, []

    src_shape = get_shape(source_model)
    base, base_shape = _make_wrap_base(source_model, src_shape)

    wrap_nodes = []
    for tgt in target_models:
        wrap = cmds.deformer(tgt, type="wrap")[0]
        _apply_wrap_settings(wrap, cfg)

        # Driver (live) and base (rest) geometry.
        cmds.connectAttr("{}.worldMesh[0]".format(src_shape),
                         "{}.driverPoints[0]".format(wrap), force=True)
        cmds.connectAttr("{}.worldMesh[0]".format(base_shape),
                         "{}.basePoints[0]".format(wrap), force=True)

        # Target's own matrix, so the deformation is computed in the right space.
        cmds.connectAttr("{}.worldMatrix[0]".format(get_shape(tgt)),
                         "{}.geomMatrix".format(wrap), force=True)

        # Per-influence attributes live on the driver transform.
        _ensure_driver_attrs(source_model, cfg)
        for attr, plug in (("dropoff", "dropoff[0]"),
                           ("smoothness", "smoothness[0]"),
                           ("inflType", "inflType[0]")):
            try:
                cmds.connectAttr("{}.{}".format(source_model, attr),
                                 "{}.{}".format(wrap, plug), force=True)
            except Exception:
                # Older Maya builds expose these as plain multi-attrs.
                try:
                    cmds.setAttr("{}.{}".format(wrap, plug), cfg[attr])
                except Exception:
                    pass

        wrap_nodes.append(wrap)
        if verbose:
            print("  wrap created: {} <- {}  (exclusiveBind={}, maxDistance={}, "
                  "inflType={})".format(tgt, source_model, cfg["exclusiveBind"],
                                        cfg["maxDistance"], cfg["inflType"]))

    return wrap_nodes, [base]


def _apply_wrap_settings(wrap_node, cfg):
    """Set the node-level wrap attributes that actually drive bind cost."""
    for attr in ("exclusiveBind", "autoWeightThreshold", "falloffMode",
                 "maxDistance", "weightThreshold"):
        plug = "{}.{}".format(wrap_node, attr)
        if cmds.objExists(plug):
            try:
                cmds.setAttr(plug, cfg[attr])
            except Exception as e:
                cmds.warning("Could not set {} | {}".format(plug, e))


def delete_wrap_nodes(wrap_nodes, cleanup_nodes=None):
    deleted = []
    for node in list(wrap_nodes) + list(cleanup_nodes or []):
        if cmds.objExists(node):
            try:
                cmds.delete(node)
                deleted.append(node)
            except Exception as e:
                cmds.warning("Could not delete {} | {}".format(node, e))
    return deleted


# ============================================================
# BLENDSHAPE CONSTRUCTION -- FAST PATH (delta injection)
# ============================================================

def compute_deltas(base_points, target_points, epsilon=DELTA_EPSILON):
    """Return (MPointArray of deltas, [vertexIndices]) for verts that moved.

    Both are built as OpenMaya types so they can be pushed to the blendShape
    plug through the API -- no string setAttr, which mis-parses negative /
    scientific-notation values ("Error reading data element number 2").
    """
    deltas = om2.MPointArray()
    indices = []

    for i in range(len(base_points)):
        b = base_points[i]
        t = target_points[i]
        dx = t.x - b.x
        dy = t.y - b.y
        dz = t.z - b.z
        if abs(dx) > epsilon or abs(dy) > epsilon or abs(dz) > epsilon:
            deltas.append(om2.MPoint(dx, dy, dz, 1.0))
            indices.append(i)

    return deltas, indices


def create_empty_blendshape(target_mesh, node_name):
    """Create a blendShape deformer on target_mesh with no targets."""
    return cmds.blendShape(target_mesh, name=node_name,
                           frontOfChain=False, origin="local")[0]


def _get_plug(plug_name):
    sel = om2.MSelectionList()
    sel.add(plug_name)
    return sel.getPlug(0)


def _set_points_target(plug_name, deltas):
    """Write an MPointArray of deltas into inputPointsTarget via the API."""
    plug = _get_plug(plug_name)
    fn = om2.MFnPointArrayData()
    plug.setMObject(fn.create(deltas))


def _set_components_target(plug_name, indices):
    """Write the affected vertex indices into inputComponentsTarget via the API."""
    plug = _get_plug(plug_name)

    comp_fn = om2.MFnSingleIndexedComponent()
    comp_obj = comp_fn.create(om2.MFn.kMeshVertComponent)
    if indices:
        comp_fn.addElements(indices)

    list_fn = om2.MFnComponentListData()
    list_obj = list_fn.create()
    list_fn.add(comp_obj)
    plug.setMObject(list_obj)


def inject_target(bs_node, weight_index, alias_name, deltas, indices):
    """Write a target's deltas straight into the blendShape node.

    Avoids creating any duplicate geometry -- the single largest source of
    time and memory in the naive approach. Uses the OpenMaya API rather than
    string setAttr so negative / tiny delta values can never mis-parse.
    """
    item = ("{}.inputTarget[0].inputTargetGroup[{}].inputTargetItem[{}]"
            .format(bs_node, weight_index, FULL_WEIGHT_ITEM))

    # Even a zero-movement shape gets a channel so target order stays 1:1
    # with the source (empty deltas / empty component list are both valid).
    _set_points_target("{}.inputPointsTarget".format(item), deltas)
    _set_components_target("{}.inputComponentsTarget".format(item), indices)

    # Instantiate + name the weight attribute.
    cmds.setAttr("{}.weight[{}]".format(bs_node, weight_index), 0.0)
    cmds.aliasAttr(alias_name, "{}.weight[{}]".format(bs_node, weight_index))


# ============================================================
# BLENDSHAPE CONNECTION COPYING
# ============================================================

def disconnect_existing_inputs(dst_plug):
    disconnected = []
    for input_plug in cmds.listConnections(dst_plug, source=True,
                                           destination=False, plugs=True) or []:
        try:
            if cmds.isConnected(input_plug, dst_plug):
                cmds.disconnectAttr(input_plug, dst_plug)
                disconnected.append(input_plug)
        except Exception as e:
            cmds.warning("Could not disconnect {} -> {} | {}".format(input_plug, dst_plug, e))
    return disconnected


def copy_blendshape_connections_from_stored(stored_connections, src_bs, dst_bs,
                                            force=True, only_targets=None,
                                            verbose=True):
    """Re-drive the new blendShape's weights from the source rig's drivers."""
    if not cmds.objExists(src_bs) or not cmds.objExists(dst_bs):
        return 0

    src_plug_to_alias = get_plug_to_alias_map(src_bs)
    dst_alias_to_plug = get_weight_alias_map(dst_bs)
    only_set = set(only_targets) if only_targets else None

    connected = 0
    no_match, no_input, replaced, failed = [], [], [], []
    used_dst = set()

    for src_driver_plug, src_weight_plug in stored_connections:
        alias = src_plug_to_alias.get(src_weight_plug)
        if alias is None:
            no_input.append(src_weight_plug)
            continue
        if only_set and alias not in only_set:
            continue

        dst_plug = dst_alias_to_plug.get(alias)
        if dst_plug is None:
            no_match.append(alias)
            continue
        if dst_plug in used_dst:
            continue
        used_dst.add(dst_plug)

        if not cmds.objExists(src_driver_plug.split(".")[0]):
            failed.append((alias, "driver node missing"))
            continue

        if cmds.listConnections(dst_plug, source=True, destination=False, plugs=True):
            if not force:
                continue
            disconnect_existing_inputs(dst_plug)
            replaced.append(alias)

        try:
            cmds.connectAttr(src_driver_plug, dst_plug, force=True)
            connected += 1
        except Exception as e:
            failed.append((alias, str(e)))

    if verbose:
        print("  connections -> {}: connected={} replaced={} noMatch={} failed={}".format(
            dst_bs, connected, len(replaced), len(no_match), len(failed)))
        for alias, reason in failed:
            print("     FAILED {} : {}".format(alias, reason))

    return connected


# ============================================================
# CORE EXTRACTION
# ============================================================

def _extract_fast(source_targets, target_models, target_bs_nodes,
                  base_points, progress_every):
    """FAST path: capture points per shape and inject deltas. No duplicates."""
    mfn = {tgt: get_mfn_mesh(tgt) for tgt in target_models}
    weight_index = {tgt: 0 for tgt in target_models}
    used_aliases = set()
    processed = 0

    for count, (_, bs_name, plug) in enumerate(source_targets, start=1):
        alias = clean_maya_name(bs_name)
        if alias in used_aliases:
            cmds.warning("Duplicate target alias skipped: {}".format(bs_name))
            continue
        used_aliases.add(alias)

        try:
            cmds.setAttr(plug, 1.0)
        except Exception as e:
            cmds.warning("Skipped locked/connected channel {} | {}".format(bs_name, e))
            continue

        force_evaluate(target_models)

        for tgt in target_models:
            try:
                deltas, indices = compute_deltas(base_points[tgt],
                                                 get_points(mfn[tgt]))
                idx = weight_index[tgt]
                inject_target(target_bs_nodes[tgt], idx, alias, deltas, indices)
                weight_index[tgt] = idx + 1
            except Exception as e:
                cmds.warning("Extraction failed [{} / {}] | {}".format(tgt, bs_name, e))

        try:
            cmds.setAttr(plug, 0.0)
        except Exception:
            pass

        processed += 1
        if progress_every and count % progress_every == 0:
            print("  ... {}/{} shapes".format(count, len(source_targets)))

    return processed


def _extract_safe(source_targets, target_models, temp_group, progress_every):
    """SAFE path: duplicate geometry per shape, then build blendShapes from it.

    Slower and heavier than FAST, but uses only stock commands.
    Returns (groupNode, {target: [dupMesh, ...]}, {target: [alias, ...]}).
    """
    if cmds.objExists(temp_group):
        cmds.delete(temp_group)

    grp = cmds.group(empty=True, name=temp_group)
    subgroups = {}
    for tgt in target_models:
        subgroups[tgt] = cmds.group(
            empty=True, parent=grp,
            name=clean_maya_name("{}_extracted_grp".format(tgt)))

    created = {tgt: [] for tgt in target_models}
    aliases = {tgt: [] for tgt in target_models}
    used_aliases = set()

    for count, (_, bs_name, plug) in enumerate(source_targets, start=1):
        alias = clean_maya_name(bs_name)
        if alias in used_aliases:
            cmds.warning("Duplicate target alias skipped: {}".format(bs_name))
            continue
        used_aliases.add(alias)

        try:
            cmds.setAttr(plug, 1.0)
        except Exception as e:
            cmds.warning("Skipped locked/connected channel {} | {}".format(bs_name, e))
            continue

        force_evaluate(target_models)

        for tgt in target_models:
            try:
                unique = "{}_{}".format(clean_maya_name(tgt), alias)
                dup = cmds.duplicate(tgt, returnRootsOnly=True)[0]
                dup = cmds.parent(dup, subgroups[tgt])[0]
                dup = cmds.rename(dup, unique)
                cmds.delete(dup, constructionHistory=True)
                created[tgt].append(dup)
                aliases[tgt].append(alias)
            except Exception as e:
                cmds.warning("Duplicate failed [{} / {}] | {}".format(tgt, bs_name, e))

        try:
            cmds.setAttr(plug, 0.0)
        except Exception:
            pass

        if progress_every and count % progress_every == 0:
            print("  ... {}/{} shapes".format(count, len(source_targets)))

    return grp, created, aliases


# ============================================================
# MAIN BUILD
# ============================================================

def build_target_blendshapes(source_model,
                             target_models,
                             source_blendshape,
                             mode=FAST,
                             wrap_settings=None,
                             temp_group="extracted_BS",
                             only_targets=None,
                             delete_duplicate_targets=True,
                             force_recreate=True,
                             copy_connections=True,
                             optimise=True,
                             progress_every=25,
                             bs_name_template="bs_{}_faceTargets"):
    """Transfer all blendShape targets from source_model onto target_models.

    Returns a list of the new blendShape node names.
    """
    if not cmds.objExists(source_model):
        cmds.error("Source model not found: {}".format(source_model))
    if not cmds.objExists(source_blendshape):
        cmds.error("Source blendShape not found: {}".format(source_blendshape))
    for tgt in target_models:
        if not cmds.objExists(tgt):
            cmds.error("Target model not found: {}".format(tgt))

    source_targets = get_blendshape_targets_in_correct_order(source_blendshape,
                                                             only_targets)
    if not source_targets:
        cmds.error("No blendShape targets found on: {}".format(source_blendshape))

    print("=" * 60)
    print("BLENDSHAPE TRANSFER")
    print("  source     : {} ({})".format(source_model, source_blendshape))
    print("  targets    : {}".format(", ".join(target_models)))
    print("  shapes     : {}".format(len(source_targets)))
    print("  mode       : {}".format(mode))
    print("=" * 60)

    start_time = time.time()

    stored_connections = []
    original_values = {}
    wrap_nodes = []
    wrap_cleanup = []
    new_bs_nodes = []
    grp = None

    try:
        with performance_mode(optimise):
            # --- freeze the source rig -------------------------------------
            original_values = store_current_weight_values(source_targets)
            stored_connections = store_and_break_blendshape_weight_connections(source_targets)
            reset_all_blendshapes(source_targets)

            # --- bind ------------------------------------------------------
            wrap_nodes, wrap_cleanup = create_wrap(source_model, target_models,
                                                   settings=wrap_settings)
            force_evaluate(target_models)

            # --- extract ---------------------------------------------------
            if mode == FAST:
                # Baseline captured WITH the wrap live and all weights at 0, so
                # any wrap-induced drift cancels out of every delta.
                base_points = {tgt: get_points(get_mfn_mesh(tgt))
                               for tgt in target_models}

                target_bs_nodes = {}
                for tgt in target_models:
                    node_name = bs_name_template.format(clean_maya_name(tgt))
                    if cmds.objExists(node_name):
                        if not force_recreate:
                            cmds.error("blendShape already exists: {}".format(node_name))
                        cmds.delete(node_name)
                    target_bs_nodes[tgt] = create_empty_blendshape(tgt, node_name)

                _extract_fast(source_targets, target_models, target_bs_nodes,
                              base_points, progress_every)

                new_bs_nodes = [target_bs_nodes[t] for t in target_models]

            else:
                grp, created, aliases = _extract_safe(source_targets, target_models,
                                                      temp_group, progress_every)

                for tgt in target_models:
                    geos = created[tgt]
                    if not geos:
                        continue

                    node_name = bs_name_template.format(clean_maya_name(tgt))
                    if cmds.objExists(node_name):
                        if not force_recreate:
                            cmds.error("blendShape already exists: {}".format(node_name))
                        cmds.delete(node_name)

                    bs = cmds.blendShape(geos, tgt, name=node_name, origin="world")[0]
                    for i, alias in enumerate(aliases[tgt]):
                        cmds.aliasAttr(alias, "{}.weight[{}]".format(bs, i))
                    new_bs_nodes.append(bs)

            # --- rehook drivers --------------------------------------------
            if copy_connections and stored_connections:
                for bs in new_bs_nodes:
                    copy_blendshape_connections_from_stored(
                        stored_connections, source_blendshape, bs,
                        force=True, only_targets=only_targets)

            # --- tidy -------------------------------------------------------
            if mode == SAFE and delete_duplicate_targets and grp and cmds.objExists(grp):
                cmds.delete(grp)

    finally:
        delete_wrap_nodes(wrap_nodes, wrap_cleanup)
        restore_weight_values(original_values)
        reconnect_blendshape_weight_connections(stored_connections)
        print("-" * 60)
        print("Source rig state restored.")
        print("Elapsed: {:.2f}s  ({} shapes x {} targets)".format(
            time.time() - start_time, len(source_targets), len(target_models)))
        print("=" * 60)

    return new_bs_nodes


# ============================================================
# PUBLIC WRAPPER
# ============================================================

def wrapToBs(srcMesh,
             tgtMeshes,
             srcBs=None,
             mode=FAST,
             tempGroup="extracted_BS",
             onlyTargets=None,
             deleteDuplicateTargets=True,
             forceRecreate=True,
             copyConnections=True,
             optimise=True,
             progressEvery=25,
             exclusiveBind=None,
             maxDistance=None,
             falloffMode=None,
             dropoff=None,
             smoothness=None,
             inflType=None,
             autoWeightThreshold=None,
             weightThreshold=None):
    """Convenience entry point.

    srcMesh        : mesh carrying the source blendShape
    tgtMeshes      : str or list of meshes to receive the transferred shapes
    srcBs          : blendShape node name; auto-detected from history if None
    mode           : "fast" (delta injection) or "safe" (duplicate geometry)
    onlyTargets    : optional list of target alias names to restrict the transfer
    optimise       : disable viewport / undo / EM for the batch

    Wrap tuning (all default to WRAP_DEFAULTS -- override only if the bind is
    wrong, since every one of these trades accuracy against speed):
    exclusiveBind  : 1 = one driver point per target point (fast). 0 = weighted.
    maxDistance    : bound on the search radius. 0 = unbounded (slow but safe).
                     Raise it if outer parts of the target fail to follow.
    falloffMode    : 0 = volume (fast), 1 = surface (topology-aware, slow).
    inflType       : 1 = point influence (fast), 2 = face influence (slow).
    """
    if isinstance(tgtMeshes, str):
        tgtMeshes = [tgtMeshes]

    wrap_settings = {
        "exclusiveBind": exclusiveBind,
        "maxDistance": maxDistance,
        "falloffMode": falloffMode,
        "dropoff": dropoff,
        "smoothness": smoothness,
        "inflType": inflType,
        "autoWeightThreshold": autoWeightThreshold,
        "weightThreshold": weightThreshold,
    }

    if not srcBs:
        history = cmds.listHistory(srcMesh, pruneDagObjects=True) or []
        bs_nodes = cmds.ls(history, type="blendShape") or []
        if not bs_nodes:
            cmds.error("No blendShape found in history of: {}".format(srcMesh))
        srcBs = bs_nodes[0]
        print("Auto-detected source blendShape: {}".format(srcBs))

    return build_target_blendshapes(
        source_model=srcMesh,
        target_models=tgtMeshes,
        source_blendshape=srcBs,
        mode=mode,
        wrap_settings=wrap_settings,
        temp_group=tempGroup,
        only_targets=onlyTargets,
        delete_duplicate_targets=deleteDuplicateTargets,
        force_recreate=forceRecreate,
        copy_connections=copyConnections,
        optimise=optimise,
        progress_every=progressEvery,
    )


# ============================================================
# SELECTION HELPER
# ============================================================

def wrapToBsFromSelection(**kwargs):
    """Select the target meshes first, then the source mesh LAST."""
    sel = cmds.ls(selection=True, long=False) or []
    if len(sel) < 2:
        cmds.error("Select one or more target meshes, then the source mesh last.")
    return wrapToBs(sel[-1], sel[:-1], **kwargs)
