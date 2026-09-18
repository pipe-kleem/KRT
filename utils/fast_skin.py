"""Auto-split from utils.py."""
from ._shared import *


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
