import maya.cmds as cmds

def set_joint_draw_style(style_value):
    """Sets the drawStyle attribute for all joints in the scene."""
    all_joints = cmds.ls(type='joint')
    
    if not all_joints:
        cmds.warning("No joints found in the scene.")
        return

    count = 0
    for jnt in all_joints:
        attr = f"{jnt}.drawStyle"
        
        # Check if the attribute is locked before setting it
        if not cmds.getAttr(attr, lock=True):
            try:
                cmds.setAttr(attr, style_value)
                count += 1
            except RuntimeError as e:
                print(f"Warning: Could not set attribute for {jnt}. {e}")
        else:
            print(f"Skipping {jnt}: drawStyle attribute is locked.")
            
    # Print a success message to the script editor
    state = "Hidden (2)" if style_value == 2 else "Normal (0)"
    print(f"Successfully set drawStyle to {state} for {count} out of {len(all_joints)} joints.")

def create_joint_ui():
    """Creates the Maya UI."""
    window_name = "JointVisibilityUI"
    
    # Close the window if it's already open to avoid duplicates
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
        
    # Create the main window
    cmds.window(window_name, title="Joint Visibility", widthHeight=(250, 120), sizeable=False)
    
    # Create a layout to stack the buttons vertically
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=('both', 10))
    
    # Add a title text
    cmds.separator(height=10, style='none') # Padding
    cmds.text(label="Hide or Show Joint Bones", font="boldLabelFont")
    
    # Create the Enable and Disable buttons
    # We use a lambda function to pass the specific drawStyle value (2 or 0)
    cmds.button(label="Enable (Hide Bones)", height=35, backgroundColor=(0.8, 0.4, 0.4), 
                command=lambda *args: set_joint_draw_style(2))
                
    cmds.button(label="Disable (Show Bones)", height=35, backgroundColor=(0.4, 0.8, 0.4), 
                command=lambda *args: set_joint_draw_style(0))
    
    # Show the window
    cmds.showWindow(window_name)

# Launch the UI
create_joint_ui()