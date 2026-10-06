import maya.cmds as cmds

def set_override_state(state):
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        return cmds.warning("Please select at least one mesh or object.")
        
    # Collect both selected transforms and their shape nodes
    nodes_to_process = set(selected_objects)
    for obj in selected_objects:
        shapes = cmds.listRelatives(obj, shapes=True) or []
        nodes_to_process.update(shapes)
        
    for node in nodes_to_process:
        attr_enabled = f"{node}.overrideEnabled"
        attr_display_type = f"{node}.overrideDisplayType"
        
        if cmds.objExists(attr_enabled):
            try:
                cmds.setAttr(attr_enabled, state)
                if state == 1 and cmds.objExists(attr_display_type):
                    cmds.setAttr(attr_display_type, 2)
            except Exception as e:
                cmds.warning(f"Could not set attribute for '{node}': {e}")
                
    cmds.refresh()
    print("Viewport refreshed. Overrides applied to transforms and shapes.")

def enable_overrides_cmd(*args):
    set_override_state(1)

def disable_overrides_cmd(*args):
    set_override_state(0)

def show_override_ui():
    window_name = "OverrideManagerWindow"
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
        
    my_window = cmds.window(window_name, title="Drawing Overrides", widthHeight=(250, 140), sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=('both', 10))
    cmds.separator(style='none', height=5)
    cmds.text(label="1. Select your meshes\n2. Choose an action below")
    cmds.button(label="Enable Overrides (Ref Mode)", height=35, command=enable_overrides_cmd, backgroundColor=(0.3, 0.5, 0.4))
    cmds.button(label="Disable Overrides", height=35, command=disable_overrides_cmd, backgroundColor=(0.6, 0.3, 0.3))
    cmds.showWindow(my_window)

show_override_ui()