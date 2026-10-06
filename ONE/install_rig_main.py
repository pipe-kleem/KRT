import maya.cmds as cmds
import maya.mel as mel

# https://gemini.google.com/app/fe7fd22604183fac?utm_source=gemini&utm_medium=web&utm_campaign=gemini_veo2_lp_deeplink&hl=en-IN&_gl=1*qchbiv*_gcl_au*MTI4ODYxNTkzMy4xNzU4NzkzNTc3*_ga*MTU4MDUwNjU3My4xNzU4NzkzNTc3*_ga_WC57KJ50ZZ*czE3NjU1NjgzMjUkbzckZzEkdDE3NjU1NjgzODIkajMkbDAkaDA.

# The UI code is stored as a string so it can be injected directly into the shelf button's command.
UI_CODE = """
import maya.cmds as cmds
import os

SCRIPT_DIR = r"P:\\pipeline_database\\Maya\\Scripts\\ONE"

def open_script_editor(filepath, filename):
    win_name = "scriptViewWin_" + filename.replace(".", "_")
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)
        
    # Create the window mimicking a script editor
    cmds.window(win_name, title=f"Script Editor: {filename}", widthHeight=(700, 500))
    form = cmds.formLayout()
    
    # Read file content
    content = ""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except Exception as e:
            content = f"# Error reading file:\\n{str(e)}"
    
    editor_field = cmds.scrollField(text=content, wordWrap=False, font="fixedWidthFont")
    
    # Save button functionality to make it a true editor
    def save_script(*args):
        new_text = cmds.scrollField(editor_field, query=True, text=True)
        try:
            with open(filepath, 'w') as f:
                f.write(new_text)
            cmds.warning(f"Successfully saved: {filepath}")
        except Exception as e:
            cmds.error(f"Failed to save: {str(e)}")

    save_btn = cmds.button(label="Save Script", command=save_script, height=35, backgroundColor=(0.2, 0.4, 0.2))
    
    # Dynamic form layout positioning
    cmds.formLayout(form, edit=True,
                    attachForm=[(editor_field, 'top', 5), (editor_field, 'left', 5), (editor_field, 'right', 5),
                                (save_btn, 'left', 5), (save_btn, 'right', 5), (save_btn, 'bottom', 5)],
                    attachControl=[(editor_field, 'bottom', 5, save_btn)],
                    attachNone=[(save_btn, 'top')])
                    
    cmds.showWindow(win_name)

def build_script_launcher():
    win_name = "RigMainLauncherUI"
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)
        
    cmds.window(win_name, title="RigMain - Script Launcher", widthHeight=(350, 500))
    
    main_layout = cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnAttach=('both', 5))
    
    cmds.separator(height=10, style='none')
    cmds.text(label="Available Scripts in ONE:", font="boldLabelFont", align="center")
    cmds.separator(height=10, style='in')
    
    if not os.path.exists(SCRIPT_DIR):
        cmds.text(label=f"Path not found:\\n{SCRIPT_DIR}", align="left", wordWrap=True)
        cmds.showWindow(win_name)
        return
        
    # Fetch all files from the directory
    files = [f for f in os.listdir(SCRIPT_DIR) if os.path.isfile(os.path.join(SCRIPT_DIR, f))]
    
    if not files:
        cmds.text(label="No files found in directory.")
        
    # Generate buttons dynamically for each file
    for f in files:
        filepath = os.path.join(SCRIPT_DIR, f)
        cmds.button(label=f, height=35, 
                   command=lambda x, p=filepath, n=f: open_script_editor(p, n))
                   
    cmds.showWindow(win_name)

build_script_launcher()
"""

def install_rigmain_shelf():
    """Builds the shelf and attaches the embedded UI script to the button."""
    shelf_name = "RigMain"
    
    # Grab the top-level shelf layout from Maya via MEL
    gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
    
    # Create the shelf if it doesn't already exist
    if not cmds.shelfLayout(shelf_name, exists=True):
        cmds.shelfLayout(shelf_name, parent=gShelfTopLevel)
    
    # Bring the shelf into focus
    cmds.tabLayout(gShelfTopLevel, edit=True, selectTab=shelf_name)
    
    # Remove existing 'start' button to prevent duplicates if installed multiple times
    buttons = cmds.shelfLayout(shelf_name, query=True, childArray=True) or []
    for btn in buttons:
        if cmds.objectType(btn) == "shelfButton":
            if cmds.shelfButton(btn, query=True, annotation=True) == "RigMain Start":
                cmds.deleteUI(btn)
                
    # Create the new shelf button
    cmds.shelfButton(
        parent=shelf_name,
        label="start",
        annotation="RigMain Start",
        image1="pythonFamily.png",  # Default Maya python icon
        command=UI_CODE,
        sourceType="python",
        imageOverlayLabel="start",
        overlayLabelColor=(1, 1, 1),
        overlayLabelBackColor=(0, 0, 0, 0.5)
    )
    
    cmds.inViewMessage(amg="<hl>RigMain shelf</hl> and <hl>start</hl> button installed successfully.", pos='midCenter', fade=True)

# This specific function name is executed by Maya when the file is dragged into the viewport
def onMayaDroppedPythonFile(*args, **kwargs):
    install_rigmain_shelf()