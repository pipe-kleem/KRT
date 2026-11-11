import maya.cmds as cmds
import re
from .rig_lib import apply_custom_wrap   # KRT Stage 68: lived only in utils.py before -> NameError in create_temp_custom_wrap

# ============================================================
# BASIC HELPERS
# ============================================================

def clean_maya_name(name):
    # Strip namespace prefixes or trailing DAG paths if passed
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
    if match:
        return int(match.group(1))
    return 999999

def get_blendshape_targets_in_correct_order(blendshape_node, only_targets=None):
    aliases = cmds.aliasAttr(blendshape_node, q=True) or []
    targets = []
    only_set = set(only_targets) if only_targets else None

    for i in range(0, len(aliases), 2):
        bs_name = aliases[i]
        attr_name = aliases[i + 1]

        if not attr_name.startswith("weight["):
            continue

        if only_set and bs_name not in only_set:
            continue

        index = get_weight_index(attr_name)
        plug = "{}.{}".format(blendshape_node, attr_name)
        targets.append((index, bs_name, plug))

    targets.sort(key=lambda x: x[0])
    return targets

def reset_all_blendshapes(targets):
    for index, bs_name, plug in targets:
        try:
            if cmds.getAttr(plug) != 0:
                cmds.setAttr(plug, 0)
        except:
            pass

def store_current_weight_values(targets):
    values = {}
    for index, bs_name, plug in targets:
        try:
            values[plug] = cmds.getAttr(plug)
        except:
            pass
    return values

def restore_weight_values(values):
    for plug, value in values.items():
        try:
            cmds.setAttr(plug, value)
        except:
            pass

# ============================================================
# ALIAS MAP HELPERS
# ============================================================

def get_weight_alias_map(bs_node):
    if not cmds.objExists(bs_node):
        cmds.error("BlendShape node not found: {}".format(bs_node))

    result = {}
    aliases = cmds.aliasAttr(bs_node, q=True) or []

    for i in range(0, len(aliases), 2):
        alias_name = aliases[i]
        attr_name = aliases[i + 1]

        if not attr_name.startswith("weight["):
            continue

        full_plug = "{}.{}".format(bs_node, attr_name)
        result[alias_name] = full_plug

    return result

def get_plug_to_alias_map(bs_node):
    alias_map = get_weight_alias_map(bs_node)
    result = {}
    for alias_name, plug in alias_map.items():
        result[plug] = alias_name
    return result

# ============================================================
# CONNECTION STORE / BREAK / RESTORE
# ============================================================

def store_and_break_blendshape_weight_connections(targets):
    stored_connections = []
    for index, bs_name, plug in targets:
        incoming = cmds.listConnections(
            plug, source=True, destination=False, plugs=True
        ) or []

        for src_plug in incoming:
            try:
                if cmds.isConnected(src_plug, plug):
                    cmds.disconnectAttr(src_plug, plug)
                    stored_connections.append((src_plug, plug))
                    print("Disconnected:", src_plug, "->", plug)
            except Exception as e:
                print("Could not disconnect:", src_plug, "->", plug, "|", e)

    return stored_connections

def reconnect_blendshape_weight_connections(stored_connections):
    for src_plug, dst_plug in stored_connections:
        try:
            src_node = src_plug.split(".")[0]
            dst_node = dst_plug.split(".")[0]

            if cmds.objExists(src_node) and cmds.objExists(dst_node):
                if not cmds.isConnected(src_plug, dst_plug):
                    cmds.connectAttr(src_plug, dst_plug, force=True)
                    print("Reconnected:", src_plug, "->", dst_plug)
        except Exception as e:
            print("Could not reconnect:", src_plug, "->", dst_plug, "|", e)

# ============================================================
# WRAP CREATE / DELETE
# ============================================================

def get_wrap_nodes_from_targets(target_geos):
    wrap_nodes = set()
    for geo in target_geos:
        if not cmds.objExists(geo):
            continue
        history = cmds.listHistory(geo, pruneDagObjects=True) or []
        for node in history:
            if cmds.objExists(node) and cmds.nodeType(node) == "wrap":
                wrap_nodes.add(node)
    return list(wrap_nodes)

def create_temp_custom_wrap(source_model, target_models):
    if not cmds.objExists(source_model):
        cmds.error("Source model not found: {}".format(source_model))

    for geo in target_models:
        if not cmds.objExists(geo):
            cmds.error("Target model not found: {}".format(geo))

    before_wraps = set(cmds.ls(type="wrap") or [])
    before_target_wraps = set(get_wrap_nodes_from_targets(target_models))

    try:
        apply_custom_wrap(source_model, target_models)
    except NameError:
        print("Custom wrap function not found. Using standard Maya wrap instead.")
        cmds.select(target_models, r=True)
        cmds.select(source_model, add=True)
        cmds.CreateWrap()
    except Exception as e:
        cmds.error("Wrap creation failed: {}".format(e))

    cmds.refresh(force=True)

    after_wraps = set(cmds.ls(type="wrap") or [])
    after_target_wraps = set(get_wrap_nodes_from_targets(target_models))

    new_wraps = list((after_wraps - before_wraps) | (after_target_wraps - before_target_wraps))

    if not new_wraps:
        possible_wraps = list(after_target_wraps)
        if possible_wraps:
            new_wraps = possible_wraps
        else:
            cmds.error("Wrap was not created or could not be detected on target model.")

    # CHANGE 1: Explicitly set exclusiveBind to 1
    for wrap_node in new_wraps:
        if cmds.attributeQuery("exclusiveBind", node=wrap_node, exists=True):
            cmds.setAttr("{}.exclusiveBind".format(wrap_node), 1)
            print("Set exclusiveBind to 1 on node: {}".format(wrap_node))

    return new_wraps

def delete_temp_wrap(wrap_nodes):
    deleted = []
    for node in wrap_nodes:
        if cmds.objExists(node):
            try:
                cmds.delete(node)
                deleted.append(node)
                print("Deleted wrap:", node)
            except Exception as e:
                print("Could not delete wrap:", node, "|", e)
    return deleted

# ============================================================
# CONNECT BS LOGIC
# ============================================================

def disconnect_existing_inputs(dst_plug):
    existing_inputs = cmds.listConnections(
        dst_plug, source=True, destination=False, plugs=True
    ) or []

    disconnected = []
    for input_plug in existing_inputs:
        try:
            if cmds.isConnected(input_plug, dst_plug):
                cmds.disconnectAttr(input_plug, dst_plug)
                disconnected.append(input_plug)
        except Exception as e:
            cmds.warning("Could not disconnect existing input {} -> {} | {}".format(input_plug, dst_plug, e))

    return disconnected

def copy_blendshape_connections_from_stored(stored_connections, src_bs, dst_bs, force=True, only_targets=None):
    if not cmds.objExists(src_bs): return 0
    if not cmds.objExists(dst_bs): return 0

    src_plug_to_alias = get_plug_to_alias_map(src_bs)
    dst_alias_to_plug = get_weight_alias_map(dst_bs)
    only_set = set(only_targets) if only_targets else None

    connected_count = 0
    skipped_no_match, skipped_no_input, replaced_existing, failed = [], [], [], []
    used_destination_plugs = set()

    for src_driver_plug, src_weight_plug in stored_connections:
        if src_weight_plug not in src_plug_to_alias:
            skipped_no_input.append(src_weight_plug)
            continue

        target_name = src_plug_to_alias[src_weight_plug]

        if only_set and target_name not in only_set:
            continue
        if target_name not in dst_alias_to_plug:
            skipped_no_match.append(target_name)
            continue

        dst_plug = dst_alias_to_plug[target_name]

        if dst_plug in used_destination_plugs:
            continue
        used_destination_plugs.add(dst_plug)

        if not cmds.objExists(src_driver_plug.split(".")[0]):
            failed.append((target_name, src_driver_plug, dst_plug, "Driver node not found"))
            continue

        existing_dst_input = cmds.listConnections(dst_plug, source=True, destination=False, plugs=True) or []

        if existing_dst_input:
            if force:
                disconnect_existing_inputs(dst_plug)
                replaced_existing.append(target_name)
            else:
                continue

        try:
            cmds.connectAttr(src_driver_plug, dst_plug, force=True)
            connected_count += 1
        except Exception as e:
            failed.append((target_name, src_driver_plug, dst_plug, str(e)))

    print_connection_report("STORED BLENDSHAPE CONNECTION COPY DONE", src_bs, dst_bs, connected_count, replaced_existing, skipped_no_match, skipped_no_input, failed)
    return connected_count

def print_connection_report(title, src_bs, dst_bs, connected_count, replaced_existing, skipped_no_match, skipped_no_input, failed):
    print("\n==============================")
    print(title)
    print("==============================")
    print("Source      :", src_bs)
    print("Destination :", dst_bs)
    print("Connected   :", connected_count)
    print("Replaced    :", len(replaced_existing))
    print("No Match    :", len(skipped_no_match))
    print("Failed      :", len(failed))

# ============================================================
# EXTRACTION SIMULTANEOUS LOGIC (WITH PREFIX FIXES)
# ============================================================

def build_target_blendshapes_simultaneous(source_model, target_models, source_blendshape, temp_group="extracted_BS", only_targets=None, delete_duplicate_targets=True, force_recreate_target_blendshape=True, copy_connections=True):
    
    if not cmds.objExists(source_model): cmds.error("Source model not found: {}".format(source_model))
    if not cmds.objExists(source_blendshape): cmds.error("Source blendShape not found: {}".format(source_blendshape))
    
    for tgt in target_models:
        if not cmds.objExists(tgt): cmds.error("Target model not found: {}".format(tgt))

    source_targets = get_blendshape_targets_in_correct_order(source_blendshape, only_targets)
    if not source_targets:
        cmds.error("No blendShape targets found on source blendShape node.")

    print("--------------------------------")
    print("STARTING SIMULTANEOUS BLENDSHAPE TRANSFER")
    print("Total source shapes to copy: {}".format(len(source_targets)))
    print("--------------------------------")

    stored_connections = []
    original_values = {}
    temp_wrap_nodes = []
    grp = None
    new_bs_nodes = []
    
    # Track created targets and map structural naming histories
    created_targets_map = {tgt: [] for tgt in target_models}
    original_names_map = {tgt: [] for tgt in target_models}

    try:
        # 1. Cache current values and break inputs temporarily
        original_values = store_current_weight_values(source_targets)
        stored_connections = store_and_break_blendshape_weight_connections(source_targets)

        # 2. Build our unified wrap modifier
        temp_wrap_nodes = create_temp_custom_wrap(source_model, target_models)

        # 3. Setup clean output group directories
        if cmds.objExists(temp_group):
            cmds.delete(temp_group)

        grp = cmds.group(empty=True, name=temp_group)
        tgt_subgroups = {}
        for tgt in target_models:
            safe_folder_name = clean_maya_name("{}_extracted_grp".format(tgt))
            tgt_subgroups[tgt] = cmds.group(empty=True, name=safe_folder_name, parent=grp)

        # 4. Flash clean baseline before recording deformations
        reset_all_blendshapes(source_targets)
        used_shape_aliases = set()

        # 5. Extract geometric states simultaneously 
        for count, (index, bs_name, plug) in enumerate(source_targets, start=1):
            clean_shape_alias = clean_maya_name(bs_name)
            if clean_shape_alias in used_shape_aliases:
                continue

            used_shape_aliases.add(clean_shape_alias)

            try:
                cmds.setAttr(plug, 1)
            except Exception as e:
                print("Skipped channel (locked/connected expression): {} | {}".format(bs_name, e))
                continue

            # Performance: Single update screen compute loop pass for all targets combined
            cmds.refresh(force=True)

            # Duplicate step for all active models
            for tgt in target_models:
                try:
                    # CHANGE 2: Combine target name and blendshape name to prevent global name clashes
                    safe_tgt_name = clean_maya_name(tgt)
                    unique_mesh_name = "{}_{}".format(safe_tgt_name, clean_shape_alias)
                    
                    dup = cmds.duplicate(tgt, rr=True)[0]
                    dup = cmds.parent(dup, tgt_subgroups[tgt])[0]
                    actual_name = cmds.rename(dup, unique_mesh_name)
                    
                    cmds.delete(actual_name, constructionHistory=True)
                    created_targets_map[tgt].append(actual_name)
                    original_names_map[tgt].append(clean_shape_alias)
                except Exception as e:
                    cmds.warning("Failed to duplicate frame data for target mesh: {} | {}".format(tgt, e))

            # Turn off channel immediately to prevent compound summation deformation errors
            try:
                cmds.setAttr(plug, 0)
            except:
                pass

        reset_all_blendshapes(source_targets)

        # 6. Reconstruct localized blendshape nodes across targets
        for tgt in target_models:
            extracted_geos = created_targets_map[tgt]
            shape_aliases = original_names_map[tgt]
            if not extracted_geos:
                continue

            target_blendshape = "bs_{}_faceTargets".format(clean_maya_name(tgt))
            if cmds.objExists(target_blendshape):
                if force_recreate_target_blendshape:
                    cmds.delete(target_blendshape)
                else:
                    cmds.error("Target blendShape node already exists: {}".format(target_blendshape))

            cmds.select(clear=True)
            cmds.select(extracted_geos, add=True)
            cmds.select(tgt, add=True)

            new_bs = cmds.blendShape(extracted_geos, tgt, name=target_blendshape, origin="world")[0]
            new_bs_nodes.append(new_bs)

            # DEBUG/FIX: Explicitly map target mesh prefixes back to original blendshape aliases
            for idx, orig_alias in enumerate(shape_aliases):
                cmds.aliasAttr(orig_alias, "{}.weight[{}]".format(new_bs, idx))

            # 7. Safe to hook driver links back into target shapes now that aliases match up
            if copy_connections:
                copy_blendshape_connections_from_stored(
                    stored_connections=stored_connections,
                    src_bs=source_blendshape,
                    dst_bs=new_bs,
                    force=True,
                    only_targets=only_targets
                )

        # Cleanup intermediate geometries if targeted
        if delete_duplicate_targets and grp and cmds.objExists(grp):
            cmds.delete(grp)

        return new_bs_nodes

    finally:
        # Strict context restoration guarantee
        if temp_wrap_nodes:
            delete_temp_wrap(temp_wrap_nodes)
        restore_weight_values(original_values)
        reconnect_blendshape_weight_connections(stored_connections)
        print(" Rig source configurations restored successfully.")

# ============================================================
# MAIN WRAPPER FUNCTION
# ============================================================

def wrapToBs(srcMesh, tgtMeshes, srcBs=None, tempGroup="extracted_BS", onlyTargets=None, deleteDuplicateTargets=True, forceRecreate=True, copyConnections=True):
    if isinstance(tgtMeshes, str):
        tgtMeshes = [tgtMeshes]

    if not srcBs:
        history = cmds.listHistory(srcMesh, pruneDagObjects=True) or []
        bs_nodes = cmds.ls(history, type="blendShape")
        if not bs_nodes:
            cmds.error("No blendShape detected on: {}".format(srcMesh))
        srcBs = bs_nodes[0]
        print("Auto-detected source blendShape: {}".format(srcBs))

    return build_target_blendshapes_simultaneous(
        source_model=srcMesh,
        target_models=tgtMeshes,
        source_blendshape=srcBs,
        temp_group=tempGroup,
        only_targets=onlyTargets,
        delete_duplicate_targets=deleteDuplicateTargets,
        force_recreate_target_blendshape=forceRecreate,
        copy_connections=copyConnections
    )