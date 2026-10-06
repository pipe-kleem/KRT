import bpy
import json


class PIPELINE_OT_ImportMayaBlendshapes(bpy.types.Operator):
    """Import Maya blendshape animation from JSON"""
    bl_idname = "pipeline.import_maya_blendshapes"
    bl_label = "Load Maya JSON"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.active_object
        
        if not obj or not obj.data.shape_keys:
            self.report({'ERROR'}, "Active object must have shape keys.")
            return {'CANCELLED'}

        with open(self.filepath, 'r') as f:
            data = json.load(f)

        shape_keys = obj.data.shape_keys.key_blocks
        frames = data.get("frames", {})

        # Cache existing shape keys to match against JSON data
        valid_shapes = {sk.name: sk for sk in shape_keys}
        keys_found = 0
        frames_processed = 0

        for frame_str, weights in frames.items():
            frame_num = int(frame_str)
            frames_processed += 1
            
            # 1. Reset ALL keys to 0 for this frame (Ensures clean animation)
            for sk in valid_shapes.values():
                if sk.name != "Basis":
                    sk.value = 0.0
                    sk.keyframe_insert(data_path="value", frame=frame_num)

            # 2. Apply active JSON weights for this frame
            for shape_name, val in weights.items():
                if shape_name in valid_shapes:
                    valid_shapes[shape_name].value = val
                    valid_shapes[shape_name].keyframe_insert(data_path="value", frame=frame_num)
                    keys_found += 1

        if keys_found > 0:
            self.report({'INFO'}, f"Success: {keys_found} keys processed over {frames_processed} frames.")
            print(f"Blendshape Transfer Complete: Applied {keys_found} data points.")
        else:
            self.report({'WARNING'}, "No matching shape key names found between Maya JSON and Blender mesh.")
            
        return {'FINISHED'}

class PIPELINE_PT_MayaToBlender(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pipeline'
    bl_label = "Anim Transfer"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if obj and obj.type == 'MESH':
            layout.operator(PIPELINE_OT_ImportMayaBlendshapes.bl_idname, icon='IMPORT')
        else:
            layout.label(text="Select a mesh with shape keys.", icon='INFO')

classes = (
    PIPELINE_OT_ImportMayaBlendshapes,
    PIPELINE_PT_MayaToBlender,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()