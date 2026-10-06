import bpy
import json

def mute_heavy_blendshapes(selected_objects, threshold=50):
    """Helper function to mute heavy blendshapes ONLY on selected objects."""
    meshes_affected = 0
    
    for obj in selected_objects:
        if getattr(obj, 'type', '') == 'MESH' and getattr(obj.data, 'shape_keys', None):
            shape_key_count = len(obj.data.shape_keys.key_blocks)
            
            if shape_key_count > threshold:
                meshes_affected += 1
                print(f"Muting '{obj.name}' - Found {shape_key_count} shape keys.")
                
                for key_block in obj.data.shape_keys.key_blocks:
                    if key_block.name != "Basis":
                        key_block.mute = True
                        
    print(f"Done! Muted shape keys on {meshes_affected} heavy selected mesh(es).")


# --- NEW: Tool Settings for the UI ---
class WrinkleMapSettings(bpy.types.PropertyGroup):
    mute_heavy_shapes: bpy.props.BoolProperty(
        name="Mute Heavy Blendshapes (>50)",
        description="Automatically mute blendshapes if an object has more than 50 shape keys",
        default=True
    )
    
    use_frame_offset: bpy.props.BoolProperty(
        name="Override Start Frame",
        description="Slide the imported animation to start at a specific frame",
        default=True
    )
    
    target_start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="The frame where the animation should begin in Blender",
        default=1
    )


class PIPELINE_OT_ImportMayaBlendshapes(bpy.types.Operator):
    """Import Maya blendshape animation from JSON"""
    bl_idname = "pipeline.import_maya_blendshapes"
    bl_label = "Load Maya JSON"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected! Please select a mesh object first.")
            return {'CANCELLED'}
            
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'ERROR'}, "No object selected! Please select a mesh object.")
            return {'CANCELLED'}
            
        obj = context.active_object
        
        if not obj or getattr(obj, 'type', '') != 'MESH' or not getattr(obj.data, 'shape_keys', None):
            self.report({'ERROR'}, "Active selected object must be a mesh with shape keys.")
            return {'CANCELLED'}

        with open(self.filepath, 'r') as f:
            data = json.load(f)

        shape_keys = obj.data.shape_keys.key_blocks
        frames = data.get("frames", {})
        
        if not frames:
            self.report({'WARNING'}, "No frames found in the JSON file.")
            return {'CANCELLED'}

        # --- NEW: Calculate the frame offset ---
        settings = context.scene.wrinkle_map_settings
        offset = 0
        
        if settings.use_frame_offset:
            # Find the very first frame number in the JSON
            min_json_frame = min([int(f) for f in frames.keys()])
            # Calculate how much we need to shift it
            offset = settings.target_start_frame - min_json_frame

        valid_shapes = {sk.name: sk for sk in shape_keys}
        keys_found = 0
        frames_processed = 0

        for frame_str, weights in frames.items():
            original_frame = int(frame_str)
            # Apply the offset to find the actual destination frame in Blender
            target_frame = original_frame + offset 
            
            frames_processed += 1
            
            # 1. Reset ALL keys to 0 for this target frame
            for sk in valid_shapes.values():
                if sk.name != "Basis":
                    sk.value = 0.0
                    sk.keyframe_insert(data_path="value", frame=target_frame)

            # 2. Apply active JSON weights for this target frame
            for shape_name, val in weights.items():
                if shape_name in valid_shapes:
                    valid_shapes[shape_name].value = val
                    valid_shapes[shape_name].keyframe_insert(data_path="value", frame=target_frame)
                    keys_found += 1

        if keys_found > 0:
            self.report({'INFO'}, f"Success: {keys_found} keys processed over {frames_processed} frames.")
            print(f"Blendshape Transfer Complete: Applied {keys_found} data points.")
            
            # Trigger muting based on UI setting
            if settings.mute_heavy_shapes:
                mute_heavy_blendshapes(context.selected_objects, threshold=50)
                
        else:
            self.report({'WARNING'}, "No matching shape key names found between Maya JSON and Blender mesh.")
            
        return {'FINISHED'}


class WRINKLEMAP_PT_Panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Wrinkle Map'
    bl_label = "Wrinkle Map"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.wrinkle_map_settings
        
        # UI Options
        box = layout.box()
        box.label(text="Import Settings:")
        box.prop(settings, "mute_heavy_shapes")
        
        box.prop(settings, "use_frame_offset")
        
        # Only show the Start Frame number input if the offset checkbox is checked
        if settings.use_frame_offset:
            box.prop(settings, "target_start_frame")
            
        layout.separator()
        
        # Big Import Button
        layout.operator(PIPELINE_OT_ImportMayaBlendshapes.bl_idname, icon='IMPORT', text="Load Maya JSON")


classes = (
    WrinkleMapSettings,
    PIPELINE_OT_ImportMayaBlendshapes,
    WRINKLEMAP_PT_Panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Register the settings to the Blender Scene
    bpy.types.Scene.wrinkle_map_settings = bpy.props.PointerProperty(type=WrinkleMapSettings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # Clean up the scene property
    del bpy.types.Scene.wrinkle_map_settings

if __name__ == "__main__":
    register()