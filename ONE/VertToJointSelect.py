import maya.cmds as cmds

class VertexInfluenceTool:
    def __init__(self):
        self.window_name = "VertexInfluenceWin"
        self.window_title = "Vertex Skin Influences"
        self.build_ui()

    def build_ui(self):
        # Close the window if it already exists to avoid duplicates
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name, window=True)

        # Create the window
        self.window = cmds.window(self.window_name, title=self.window_title, widthHeight=(300, 350), sizeable=True)
        
        # Main layout
        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=('both', 5))
        
        cmds.text(label="1. Select a single vertex\n2. Click the button below", align="center")
        
        # Button to trigger the weight calculation
        cmds.button(label="Get Influences", height=40, backgroundColor=(0.2, 0.5, 0.8), command=self.get_influences)
        
        # List to display joints
        cmds.text(label="Influencing Joints (Highest to Lowest):", align="left")
        self.joint_list = cmds.textScrollList(
            numberOfRows=12, 
            allowMultiSelection=False, 
            selectCommand=self.select_joint_in_scene,
            font="plainLabelFont"
        )

        cmds.showWindow(self.window)

    def get_influences(self, *args):
        # Clear the current list
        cmds.textScrollList(self.joint_list, edit=True, removeAll=True)

        # Get current selection
        sel = cmds.ls(selection=True, flatten=True)
        
        if not sel or ".vtx[" not in sel[0]:
            cmds.warning("Please select at least one vertex.")
            return

        # Use the first selected vertex
        vertex = sel[0]
        mesh = vertex.split('.')[0]

        # Find the skin cluster attached to the mesh
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        skin_clusters = cmds.ls(history, type="skinCluster")

        if not skin_clusters:
            cmds.warning(f"No skin cluster found on {mesh}.")
            return

        skin_cluster = skin_clusters[0]

        # Get all joints and their corresponding weights for this vertex
        joints = cmds.skinCluster(skin_cluster, query=True, influence=True)
        weights = cmds.skinPercent(skin_cluster, vertex, query=True, value=True)

        # Pair joints with their weights and filter out zero-weight influences
        joint_weights = list(zip(joints, weights))
        active_influences = [(j, w) for j, w in joint_weights if w > 0.0]

        # Sort by weight in descending order (highest influence first)
        active_influences.sort(key=lambda x: x[1], reverse=True)

        if not active_influences:
            cmds.warning("No active influences found for this vertex.")
            return

        # Populate the UI list
        for joint, weight in active_influences:
            # Format: JointName (0.9500)
            display_text = f"{joint}  ({weight:.4f})"
            cmds.textScrollList(self.joint_list, edit=True, append=display_text)

    def select_joint_in_scene(self):
        # Get the selected item from the UI
        selected_items = cmds.textScrollList(self.joint_list, query=True, selectItem=True)
        
        if selected_items:
            # Extract just the joint name by splitting at the first space
            # (Maya node names cannot contain spaces, so this is safe)
            joint_name = selected_items[0].split("  (")[0]
            
            # Select the joint in the scene
            if cmds.objExists(joint_name):
                cmds.select(joint_name, replace=True)
            else:
                cmds.warning(f"Joint '{joint_name}' no longer exists in the scene.")

# Run the tool
VertexInfluenceTool()