import maya.cmds as cmds
import json
import os

class SaveLoadAttributesUI:
    def __init__(self):
        self.window_name = "SaveLoadAttrsWindow_v3"
        self.build_ui()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        cmds.window(self.window_name, title="Attribute Manager", widthHeight=(400, 260), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=('both', 10))
        
        cmds.separator(height=10, style='none')

        # --- Controls Section ---
        cmds.text(label="1. Add Controls:", align='left', font='boldLabelFont')
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80), adjustableColumn=1)
        self.ctrl_tf = cmds.textField(placeholderText="Select controls and click '<< Selected'")
        cmds.button(label="<< Selected", command=lambda x: self.populate_field(self.ctrl_tf))
        cmds.setParent('..')

        # --- Groups Section ---
        cmds.text(label="2. Add Groups:", align='left', font='boldLabelFont')
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80), adjustableColumn=1)
        self.grp_tf = cmds.textField(placeholderText="Select groups and click '<< Selected'")
        cmds.button(label="<< Selected", command=lambda x: self.populate_field(self.grp_tf))
        cmds.setParent('..')

        # --- Save Location Section ---
        cmds.text(label="3. JSON File Path:", align='left', font='boldLabelFont')
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80), adjustableColumn=1)
        self.path_tf = cmds.textField(placeholderText="C:/path/to/save/pose.json")
        cmds.button(label="Browse", command=self.browse_save_path)
        cmds.setParent('..')

        cmds.separator(height=10, style='in')

        # --- Action Buttons ---
        cmds.button(label="Save Attributes to JSON", command=self.save_to_json, height=35, backgroundColor=(0.2, 0.6, 0.3))
        cmds.button(label="Load Attributes from JSON", command=self.load_from_json, height=35, backgroundColor=(0.2, 0.4, 0.6))
        
        cmds.separator(height=10, style='none')

        cmds.showWindow(self.window_name)

    def populate_field(self, tf_element):
        selection = cmds.ls(selection=True)
        if selection:
            cmds.textField(tf_element, edit=True, text=",".join(selection))
        else:
            cmds.warning("Nothing selected in the viewport.")

    def browse_save_path(self, *args):
        file_path = cmds.fileDialog2(
            fileFilter="JSON Files (*.json)", 
            dialogStyle=2, 
            fileMode=0, 
            caption="Choose JSON File Location"
        )
        if file_path:
            cmds.textField(self.path_tf, edit=True, text=file_path[0])

    def save_to_json(self, *args):
        ctrl_text = cmds.textField(self.ctrl_tf, query=True, text=True).strip()
        grp_text = cmds.textField(self.grp_tf, query=True, text=True).strip()
        file_path = cmds.textField(self.path_tf, query=True, text=True).strip()

        if not file_path:
            cmds.warning("Please specify a JSON File Path before saving.")
            return

        objects_to_save = []
        if ctrl_text:
            objects_to_save.extend([x.strip() for x in ctrl_text.split(',') if x.strip()])
        if grp_text:
            objects_to_save.extend([x.strip() for x in grp_text.split(',') if x.strip()])

        if not objects_to_save:
            cmds.warning("No controls or groups specified to save.")
            return

        data = {}
        for obj in objects_to_save:
            if not cmds.objExists(obj):
                cmds.warning(f"Object '{obj}' does not exist in scene. Skipping.")
                continue
                
            data[obj] = {}
            
            # 1. Keyable (Translate, Rotate, Scale, Vis, etc.)
            k_attrs = cmds.listAttr(obj, keyable=True) or []
            # 2. Channel Box (Visible but maybe non-keyable)
            cb_attrs = cmds.listAttr(obj, channelBox=True) or []
            # 3. User Defined (Any custom rig attributes)
            ud_attrs = cmds.listAttr(obj, userDefined=True) or []
            
            # Combine and remove duplicates using a set
            all_attrs = list(set(k_attrs + cb_attrs + ud_attrs))
            
            for attr in all_attrs:
                full_attr = f"{obj}.{attr}"
                try:
                    # Get the value
                    value = cmds.getAttr(full_attr)
                    
                    # Store it (ensure we are only storing standard data types, not complex matrix objects if they sneak in)
                    if isinstance(value, (int, float, bool, list, tuple)):
                        # Maya sometimes returns nested lists for certain compound attributes, flatten them to a simple list or tuple
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], tuple):
                            value = value[0] 
                        data[obj][attr] = value
                except Exception:
                    pass 

        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Success! Saved {len(data.keys())} objects to: {file_path}")
        except Exception as e:
            cmds.error(f"Failed to save file: {e}")

    def load_from_json(self, *args):
        file_path = cmds.textField(self.path_tf, query=True, text=True).strip()
        
        if not file_path or not os.path.exists(file_path):
            picked_path = cmds.fileDialog2(
                fileFilter="JSON Files (*.json)", 
                dialogStyle=2, 
                fileMode=1, 
                caption="Select JSON File to Load"
            )
            if not picked_path:
                return 
            file_path = picked_path[0]
            cmds.textField(self.path_tf, edit=True, text=file_path)

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            cmds.error(f"Failed to read file: {e}")
            return

        applied_count = 0
        for obj, attrs in data.items():
            if not cmds.objExists(obj):
                cmds.warning(f"Object '{obj}' not found in scene. Skipping.")
                continue

            for attr, value in attrs.items():
                full_attr = f"{obj}.{attr}"
                try:
                    # Apply value if the attribute exists and isn't locked/connected
                    if cmds.objExists(full_attr) and cmds.getAttr(full_attr, settable=True):
                        
                        # Handle compound attributes like color (which load as a list from JSON but need to be set unpacked)
                        if isinstance(value, list) or isinstance(value, tuple):
                            cmds.setAttr(full_attr, *value)
                        else:
                            cmds.setAttr(full_attr, value)
                            
                except Exception:
                    pass
            
            applied_count += 1

        print(f"Success! Loaded attributes for {applied_count} objects from: {file_path}")

# Run the UI
SaveLoadAttributesUI()