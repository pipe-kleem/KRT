import maya.cmds as cmds
import maya.api.OpenMaya as om

def analyze_joints_x_bounds(joint_list, mesh_node):
    """
    Analyzes multiple joints against a target mesh to find their local +X and -X 
    boundary vertices and caches the distance spans.
    """
    sel_list = om.MSelectionList()
    try:
        sel_list.add(mesh_node)
    except Exception:
        cmds.error(f"Mesh '{mesh_node}' not found.")
        return {}

    mesh_dag = sel_list.getDagPath(0)
    if mesh_dag.node().hasFn(om.MFn.kTransform):
        mesh_dag.extendToShape()

    fn_mesh = om.MFnMesh(mesh_dag)
    points = fn_mesh.getPoints(om.MSpace.kWorld)

    cached_data = {}

    for j_name in joint_list:
        if not cmds.objExists(j_name):
            cmds.warning(f"Joint '{j_name}' does not exist. Skipping.")
            continue

        j_matrix = cmds.xform(j_name, q=True, ws=True, matrix=True)
        origin = om.MPoint(j_matrix[12], j_matrix[13], j_matrix[14])
        local_x = om.MVector(j_matrix[0], j_matrix[1], j_matrix[2]).normal()

        def march_along_axis(direction_vector):
            step_size = 0.05
            max_steps = 1000
            min_dist_to_mesh = min((pt - origin).length() for pt in points)
            hit_threshold = max(0.2, min_dist_to_mesh * 0.3) 

            for step in range(1, max_steps):
                sample_pos = origin + (direction_vector * (step * step_size))
                closest_idx = None
                closest_dist = float('inf')

                for i, pt in enumerate(points):
                    d = (pt - sample_pos).length()
                    if d < closest_dist:
                        closest_dist = d
                        closest_idx = i

                if closest_dist <= hit_threshold:
                    return closest_idx, points[closest_idx]

            return None, None

        vtx_up_idx, pos_up = march_along_axis(local_x)
        vtx_down_idx, pos_down = march_along_axis(-local_x)

        if vtx_up_idx is None or vtx_down_idx is None:
            cmds.warning(f"Could not calculate X bounds for joint '{j_name}'. Skipping.")
            continue

        dist_up = (om.MVector(pos_up) - om.MVector(origin)) * local_x
        dist_down = (om.MVector(pos_down) - om.MVector(origin)) * local_x

        cached_data[j_name] = {
            "origin": origin,
            "local_x": local_x,
            "dist_up": dist_up,
            "dist_down": dist_down,
            "vtx_up": f"{mesh_dag.fullPathName()}.vtx[{vtx_up_idx}]",
            "vtx_down": f"{mesh_dag.fullPathName()}.vtx[{vtx_down_idx}]"
        }

    print(f"Successfully calculated X bounds for {len(cached_data)} joints.")
    return cached_data


def apply_joint_x_positions(cached_data, position_values, fallback_mapping=None):
    """
    Repositions joints while updating skinCluster.bindPreMatrix and preserving direct children.
    
    :param cached_data: Dictionary output from analyze_joints_x_bounds()
    :param position_values: Dictionary mapping joint names to scale floats (1.00 to 10.00)
    :param fallback_mapping: Optional dict mapping an uncached joint to a cached source joint
                             e.g. {'CC_Base_L_Index4': 'CC_Base_L_Index3'}
    """
    if fallback_mapping is None:
        fallback_mapping = {}

    selected_vtx = []

    for j_name, val in position_values.items():
        # Determine source data joint (direct match or mapped fallback)
        source_j_name = j_name if j_name in cached_data else fallback_mapping.get(j_name)

        if not source_j_name or source_j_name not in cached_data:
            cmds.warning(f"No cached data or valid fallback found for '{j_name}'. Skipping.")
            continue

        if not cmds.objExists(j_name):
            cmds.warning(f"Joint '{j_name}' does not exist in the scene. Skipping.")
            continue

        clamped_val = max(1.0, min(10.0, float(val)))
        bounds_data = cached_data[source_j_name]

        # Fetch actual current transform and local X axis for target joint
        j_matrix = cmds.xform(j_name, q=True, ws=True, matrix=True)
        origin = om.MPoint(j_matrix[12], j_matrix[13], j_matrix[14])
        local_x = om.MVector(j_matrix[0], j_matrix[1], j_matrix[2]).normal()

        # 1. Store original world matrices of direct child transform/joint nodes
        children = cmds.listRelatives(j_name, children=True, type="transform") or []
        child_world_matrices = {}
        for child in children:
            child_world_matrices[child] = cmds.xform(child, query=True, worldSpace=True, matrix=True)

        # 2. Compute new target position along target joint's local X-axis using source joint bounds
        t = (clamped_val - 1.0) / 9.0 
        target_offset = bounds_data["dist_up"] + t * (bounds_data["dist_down"] - bounds_data["dist_up"])
        new_pos = origin + (local_x * target_offset)

        # 3. Move Joint to target position
        cmds.xform(j_name, ws=True, t=(new_pos.x, new_pos.y, new_pos.z))

        # 4. Restore direct child world matrices
        for child, original_matrix in child_world_matrices.items():
            cmds.xform(child, worldSpace=True, matrix=original_matrix)

        # 5. Update skinCluster bindPreMatrix to prevent mesh distortion
        connections = cmds.listConnections(f"{j_name}.worldMatrix[0]", type="skinCluster", connections=True, plugs=True) or []
        for i in range(0, len(connections), 2):
            dst_plug = connections[i + 1]
            
            if ".matrix[" in dst_plug:
                skin_node, attr_name = dst_plug.split(".")
                index = attr_name.split("[")[1].split("]")[0]
                
                world_inv_mat = cmds.getAttr(f"{j_name}.worldInverseMatrix[0]")
                cmds.setAttr(f"{skin_node}.bindPreMatrix[{index}]", world_inv_mat, type="matrix")

        selected_vtx.extend([bounds_data["vtx_up"], bounds_data["vtx_down"]])

    if selected_vtx:
        cmds.select(selected_vtx, replace=True)

    print("Batch joint positioning completed with fallback mapping support.")


# --- EXECUTION EXAMPLE ---

# 1. Base joint list to calculate (version 2 and 3 joints)
my_joints = [
    "CC_Base_L_Thumb2", "CC_Base_L_Thumb3", 
    "CC_Base_L_Index2", "CC_Base_L_Index3", 
    "CC_Base_L_Mid2",   "CC_Base_L_Mid3", 
    "CC_Base_L_Ring2",  "CC_Base_L_Ring3", 
    "CC_Base_L_Pinky2", "CC_Base_L_Pinky3"
]
my_mesh = "CC_Base_Body"

# Step 1: Analyze and cache bounds for base joints
joint_data_cache = analyze_joints_x_bounds(joint_list=my_joints, mesh_node=my_mesh)

# Step 2: Set values for both cached joints AND uncached tip joints (version 4)
joint_settings = {
    # Cached Joints
    "CC_Base_L_Thumb2": 7.0, 
    "CC_Base_L_Thumb3": 7.0, 
    "CC_Base_L_Index2": 7.0, 
    "CC_Base_L_Index3": 7.0, 
    "CC_Base_L_Mid2":   7.0, 
    "CC_Base_L_Mid3":   7.0, 
    "CC_Base_L_Ring2":  7.0, 
    "CC_Base_L_Ring3":  7.0, 
    "CC_Base_L_Pinky2": 7.0, 
    "CC_Base_L_Pinky3": 7.0, 
    
    # Uncached Joints (Version 4)
    "CC_Base_L_Thumb4": 4.0,
    "CC_Base_L_Index4": 4.0,
    "CC_Base_L_Mid4":   4.0,
    "CC_Base_L_Ring4":  4.0,
    "CC_Base_L_Pinky4": 4.0
}

# Step 3: Map version 4 uncached joints to use version 3 cached boundaries
joint_fallback_map = {
    "CC_Base_L_Thumb4": "CC_Base_L_Thumb3",
    "CC_Base_L_Index4": "CC_Base_L_Index3",
    "CC_Base_L_Mid4":   "CC_Base_L_Mid3",
    "CC_Base_L_Ring4":  "CC_Base_L_Ring3",
    "CC_Base_L_Pinky4": "CC_Base_L_Pinky3"
}

# Step 4: Apply position updates using cached bounds + fallback mapping
apply_joint_x_positions(
    cached_data=joint_data_cache, 
    position_values=joint_settings, 
    fallback_mapping=joint_fallback_map
)