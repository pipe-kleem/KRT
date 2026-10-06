import json
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

def get_skin_cluster(mesh):
    """Finds and returns the skinCluster node attached to the given mesh."""
    if not cmds.objExists(mesh):
        cmds.error(f"Object '{mesh}' does not exist in the scene.")
        return None

    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or [mesh]
    
    for shape in shapes:
        history = cmds.listHistory(shape) or []
        skin_clusters = cmds.ls(history, type='skinCluster')
        if skin_clusters:
            return skin_clusters[0]

    for shape in shapes:
        connections = cmds.listConnections(shape, type='objectSet') or []
        for conn in connections:
            cluster = cmds.listConnections(conn, type='skinCluster')
            if cluster:
                return cluster[0]

    return None


def export_skin_weights(mesh_name, file_path):
    """Exports per-vertex skin weight data for a given mesh to a JSON file."""
    skin_cluster = get_skin_cluster(mesh_name)
    if not skin_cluster:
        cmds.error(f"No skinCluster found on '{mesh_name}'.")
        return

    influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
    vertex_count = cmds.polyEvaluate(mesh_name, vertex=True)
    
    skin_data = {
        "mesh": mesh_name,
        "joints": influences,
        "weights": {}
    }

    for i in range(vertex_count):
        vtx = f"{mesh_name}.vtx[{i}]"
        weights = cmds.skinPercent(skin_cluster, vtx, query=True, value=True)
        
        vtx_weights = {
            inf: round(weight, 6) 
            for inf, weight in zip(influences, weights) 
            if weight > 0.000001
        }
        skin_data["weights"][str(i)] = vtx_weights

    with open(file_path, 'w') as f:
        json.dump(skin_data, f, indent=4)

    print(f"Successfully exported skin weights to: {file_path}")


def import_skin_weights(mesh_name, file_path, create_skin_cluster=True, auto_add_joints=True):
    """
    Imports per-vertex skin weight data from a JSON file using Maya API 2.0.
    
    :param mesh_name: Name of the target mesh transform.
    :param file_path: Absolute path to the JSON weight file.
    :param create_skin_cluster: Automatically create a skinCluster if none exists.
    :param auto_add_joints: Automatically add missing joints as influences to the skinCluster.
    """
    if not cmds.objExists(mesh_name):
        cmds.error(f"Mesh '{mesh_name}' does not exist in the scene.")
        return

    with open(file_path, 'r') as f:
        skin_data = json.load(f)

    json_joints = skin_data.get("joints", [])
    weights_data = skin_data.get("weights", {})

    # Check which joints from JSON exist in the current scene
    existing_joints = [j for j in json_joints if cmds.objExists(j)]
    missing_scene_joints = [j for j in json_joints if not cmds.objExists(j)]

    if missing_scene_joints:
        cmds.warning(f"The following joints from JSON are missing in the scene and will be skipped: {missing_scene_joints}")

    if not existing_joints:
        cmds.error("None of the required joints exist in the scene. Aborting import.")
        return

    # Find existing skinCluster or create one
    skin_cluster = get_skin_cluster(mesh_name)
    
    if not skin_cluster:
        if create_skin_cluster:
            print(f"Creating new skinCluster on '{mesh_name}'...")
            skin_cluster = cmds.skinCluster(
                existing_joints, 
                mesh_name, 
                toSelectedBones=True, 
                maximumInfluences=4, 
                normalizeWeights=1
            )[0]
        else:
            cmds.error(f"Target mesh '{mesh_name}' has no skinCluster.")
            return
    elif auto_add_joints:
        # Automatically add missing influence joints
        current_influences = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
        joints_to_add = [j for j in existing_joints if j not in current_influences]
        
        if joints_to_add:
            print(f"Automatically adding {len(joints_to_add)} missing joints to '{skin_cluster}'...")
            cmds.skinCluster(skin_cluster, edit=True, addInfluence=joints_to_add, weight=0.0)

    # Use Maya API 2.0 (OpenMaya) to set weights in a single fast execution
    sel = om.MSelectionList()
    sel.add(mesh_name)
    sel.add(skin_cluster)
    
    mesh_dag = sel.getDagPath(0)
    skin_obj = sel.getDependNode(1)
    
    mfn_skin = oma.MFnSkinCluster(skin_obj)
    
    # Map influence names to their API index using partialPathName()
    influence_paths = mfn_skin.influenceObjects()
    inf_map = {path.partialPathName(): i for i, path in enumerate(influence_paths)}
    num_influences = len(influence_paths)

    # Get single mesh component selection for all vertices
    vtx_count = cmds.polyEvaluate(mesh_name, vertex=True)
    fn_single_indexed = om.MFnSingleIndexedComponent()
    vtx_components = fn_single_indexed.create(om.MFn.kMeshVertComponent)
    fn_single_indexed.addElements(list(range(vtx_count)))

    # Construct the array of weights
    flat_weights = [0.0] * (vtx_count * num_influences)

    for vtx_str, vtx_weights in weights_data.items():
        vtx_idx = int(vtx_str)
        if vtx_idx >= vtx_count:
            continue
            
        base_idx = vtx_idx * num_influences
        for joint, weight in vtx_weights.items():
            if joint in inf_map:
                inf_idx = inf_map[joint]
                flat_weights[base_idx + inf_idx] = weight

    # Batch apply all weights directly via API
    weight_array = om.MDoubleArray(flat_weights)
    influence_indices = om.MIntArray(list(range(num_influences)))

    mfn_skin.setWeights(
        mesh_dag,
        vtx_components,
        influence_indices,
        weight_array,
        normalize=True
    )

    print(f"Successfully imported skin weights onto: {mesh_name}")


export_path = "C:/Users/vishal3/Downloads/skinExport/belt.json"
# Export skin weights of selected mesh or explicit name
export_skin_weights("geo_ravana_belt_lod_0", export_path)




import_path = "C:/Users/vishal3/Downloads/skinExport/belt.json"
# Automatically adds missing joints and imports weights instantly
import_skin_weights("geo_ravana_belt_lod_0", import_path)