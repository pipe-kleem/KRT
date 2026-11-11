import maya.cmds as cmds
import maya.OpenMaya as om
import maya.OpenMayaUI as omui
import os

def capture_viewport_api():
    # 1. Define file path
    downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    scene_path = cmds.file(query=True, sceneName=True)
    base_name = os.path.splitext(os.path.basename(scene_path))[0] if scene_path else "Untitled"
    save_path = os.path.join(downloads_dir, f"{base_name}.jpg")

    # 2. Locate the active model panel
    panel = cmds.getPanel(withFocus=True)
    if cmds.getPanel(typeOf=panel) != 'modelPanel':
        for p in cmds.getPanel(visiblePanels=True):
            if cmds.getPanel(typeOf=p) == 'modelPanel':
                panel = p
                break
                
    if not panel or cmds.getPanel(typeOf=panel) != 'modelPanel':
        cmds.warning("Could not find a visible 3D viewport to capture.")
        return

    # Ensure the panel we found is the actively focused one for the API
    cmds.setFocus(panel)
    viewcube_state = cmds.viewManip(query=True, visible=True)

    # 3. Apply Clean Viewport Settings 
    cmds.lookThru('front', panel)
    cmds.viewManip(visible=False) # Hide ViewCube
    
    cmds.modelEditor(
        panel, 
        edit=True, 
        grid=False, 
        displayAppearance='smoothShaded',
        displayTextures=True,
        headsUpDisplay=False,
        nurbsCurves=True,     
        joints=True           
    )

    # 4. Frame specific controllers ("F" key behavior)
    ctls = cmds.ls("*ctl*", "geo*")  
    if ctls:
        cmds.select(ctls, replace=True)
        cmds.viewFit('front')      
        cmds.select(clear=True)  
    else:
        cmds.warning("No objects containing 'ctl' found; skipping the focus step.")

    # 5. CRITICAL: Force Maya to redraw the screen with the new settings
    cmds.refresh(force=True)

    # 6. Capture the frame using Maya API (WYSIWYG)
    try:
        # Get the active 3D view
        view = omui.M3dView.active3dView()
        
        # Create an empty image object
        image = om.MImage()
        
        # Read the exact pixels from the viewport buffer
        view.readColorBuffer(image, True)
        
        # Save the image to disk
        image.writeToFile(save_path, 'jpg')
        
        print(f"Success: Perfect API screenshot saved to {save_path}")
    except Exception as e:
        cmds.warning(f"Failed to capture viewport via API: {e}")
    finally:
        # 7. Restore the ViewCube
        cmds.viewManip(visible=viewcube_state)

# Execute the capture
#capture_viewport_api()