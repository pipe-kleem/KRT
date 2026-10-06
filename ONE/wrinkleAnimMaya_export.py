import maya.cmds as cmds
import json
import os

class MayaBlendshapeExporter:
    def __init__(self):
        self.window_name = "MayaToBlenderBSExport"
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.window = cmds.window(self.window_name, title="Export Anim Data", widthHeight=(320, 200))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=('both', 10))
        
        cmds.separator(height=5, style='none')
        cmds.text(label="1. Target Node Setup", font="boldLabelFont", align="left")
        
        # Load Node UI
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 90))
        self.node_field = cmds.textField(editable=False, text="No node loaded...", width=195)
        cmds.button(label="Load Selected", command=self.load_node, width=90, backgroundColor=(0.3, 0.4, 0.5))
        cmds.setParent('..')
        
        cmds.separator(height=10)
        cmds.text(label="2. Export Settings", font="boldLabelFont", align="left")
        
        # Frame Range
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(150, 150))
        self.start_frame = cmds.intFieldGrp(label='Start:', value1=cmds.playbackOptions(q=True, min=True), columnWidth2=[40, 60])
        self.end_frame = cmds.intFieldGrp(label='End:', value1=cmds.playbackOptions(q=True, max=True), columnWidth2=[40, 60])
        cmds.setParent('..')
        
        # File Path
        self.path_field = cmds.textFieldButtonGrp(label='Path:', buttonLabel='Browse', columnWidth3=[40, 200, 50], buttonCommand=self.browse_file)
        
        cmds.separator(height=10, style='none')
        cmds.button(label="Export All Shapes to JSON", command=self.export_data, height=35, backgroundColor=(0.2, 0.5, 0.3))
        
        cmds.showWindow(self.window)

    def load_node(self, *args):
        selection = cmds.ls(selection=True)
        if not selection:
            cmds.warning("Please select your character mesh first.")
            return

        target_node = selection[0]
        node_to_load = None

        # Check if selected node is already a blendshape
        if cmds.nodeType(target_node) == 'blendShape':
            node_to_load = target_node
        else:
            # Auto-detect blendshape node from mesh history
            history = cmds.listHistory(target_node) or []
            blendshapes = cmds.ls(history, type='blendShape')
            if blendshapes:
                node_to_load = blendshapes[0]

        if node_to_load:
            cmds.textField(self.node_field, edit=True, text=node_to_load)
            print(f"Successfully loaded: {node_to_load}")
        else:
            cmds.warning(f"No blendshape node found attached to {target_node}.")

    def browse_file(self):
        file_path = cmds.fileDialog2(fileFilter="JSON Files (*.json)", dialogStyle=2, fileMode=0)
        if file_path:
            cmds.textFieldButtonGrp(self.path_field, edit=True, text=file_path[0])

    def export_data(self, *args):
        target_node = cmds.textField(self.node_field, query=True, text=True)
        
        if target_node == "No node loaded..." or not cmds.objExists(target_node):
            cmds.warning("Please load a valid Blendshape node first.")
            return
            
        start = cmds.intFieldGrp(self.start_frame, query=True, value1=True)
        end = cmds.intFieldGrp(self.end_frame, query=True, value1=True)
        export_path = cmds.textFieldButtonGrp(self.path_field, query=True, text=True)
        
        if not export_path:
            cmds.warning("Please specify a valid export path.")
            return

        # Safely get all blendshape aliases (returns list like [name, index, name, index...])
        aliases = cmds.aliasAttr(target_node, query=True)
        if not aliases:
            cmds.warning(f"Could not find any blendshape targets on {target_node}.")
            return
            
        # Extract just the string names to ensure WE GET ALL SHAPES
        bs_names = aliases[0::2]

        anim_data = {"frames": {}}
        total_keys_recorded = 0

        # Background bake loop
        for frame in range(start, end + 1):
            frame_data = {}
            
            for name in bs_names:
                attr_path = f"{target_node}.{name}"
                
                try:
                    # Query value at specific time (bypasses UI playback issues)
                    val = cmds.getAttr(attr_path, time=frame)
                    
                    # Optimization: Only log if the shape is actively affecting the face (> 0)
                    # The Blender script will safely zero-out anything not listed here.
                    if val is not None and abs(val) > 0.0001: 
                        frame_data[name] = round(val, 4)
                        total_keys_recorded += 1
                except Exception:
                    pass
            
            if frame_data:
                anim_data["frames"][str(frame)] = frame_data

        with open(export_path, 'w') as f:
            json.dump(anim_data, f, indent=4)
            
        print(f"Success: Exported {total_keys_recorded} active shape values across {len(anim_data['frames'])} frames.")

MayaBlendshapeExporter()