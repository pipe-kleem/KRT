bl_info = {
    "name": "PC2 Mesh Scatter",
    "author": "Assistant",
    "version": (1, 7),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > PC2 Tools",
    "description": "Scatters multiple target meshes by matching the end of .pc2 filenames.",
    "category": "Object",
}

import bpy
import os

# --- 1. Properties ---
class PC2TargetItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Mesh Name")

class PC2ScatterProperties(bpy.types.PropertyGroup):
    target_meshes: bpy.props.CollectionProperty(type=PC2TargetItem)
    target_meshes_index: bpy.props.IntProperty(name="Active Target Index", default=0)
    
    pc2_folder_path: bpy.props.StringProperty(
        name="PC2 Folder",
        description="Choose the directory containing .pc2 files",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'
    )

# --- 2. Custom UI List ---
class PC2_UL_target_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon='MESH_DATA')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='MESH_DATA')

# --- 3. Operators (Add / Remove / Clear) ---
class OBJECT_OT_add_target_meshes(bpy.types.Operator):
    bl_idname = "object.add_target_meshes"
    bl_label = "Add Selected Targets"
    bl_description = "Add currently selected meshes to the target list"

    def execute(self, context):
        props = context.scene.pc2_scatter_props
        added = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                # Prevent duplicates
                if not any(item.name == obj.name for item in props.target_meshes):
                    item = props.target_meshes.add()
                    item.name = obj.name
                    added += 1
        
        props.target_meshes_index = len(props.target_meshes) - 1
        self.report({'INFO'}, f"Added {added} meshes to Targets.")
        return {'FINISHED'}

class OBJECT_OT_remove_target_mesh(bpy.types.Operator):
    bl_idname = "object.remove_target_mesh"
    bl_label = "Remove Selected Target"
    bl_description = "Remove the highlighted mesh from the list"

    def execute(self, context):
        props = context.scene.pc2_scatter_props
        idx = props.target_meshes_index
        
        if len(props.target_meshes) > 0 and idx >= 0:
            props.target_meshes.remove(idx)
            props.target_meshes_index = min(max(0, idx - 1), len(props.target_meshes) - 1)
            
        return {'FINISHED'}

class OBJECT_OT_clear_target_meshes(bpy.types.Operator):
    bl_idname = "object.clear_target_meshes"
    bl_label = "Clear All Targets"
    
    def execute(self, context):
        context.scene.pc2_scatter_props.target_meshes.clear()
        return {'FINISHED'}

# --- 4. Execute Operator ---
class OBJECT_OT_scatter_from_pc2(bpy.types.Operator):
    bl_idname = "object.scatter_from_pc2"
    bl_label = "Scatter Meshes"
    bl_description = "Scatter the target meshes by matching the end of .pc2 filenames"

    def execute(self, context):
        props = context.scene.pc2_scatter_props
        folder_path = bpy.path.abspath(props.pc2_folder_path)

        # Build list of valid objects from the scene
        valid_targets = [bpy.data.objects.get(item.name) for item in props.target_meshes if bpy.data.objects.get(item.name)]

        # Validation
        if not valid_targets:
            self.report({'ERROR'}, "No valid target meshes loaded in the list.")
            return {'CANCELLED'}

        if not os.path.exists(folder_path):
            self.report({'ERROR'}, f"Directory '{folder_path}' does not exist.")
            return {'CANCELLED'}

        # --- NEW: 63-Character Limit Check ---
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(".pc2"):
                pc2_base_name = os.path.splitext(filename)[0]
                if len(pc2_base_name) > 63:
                    self.report({'ERROR'}, f"Execution Halted: File name '{filename}' exceeds 63 characters.")
                    return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        
        count = 0
        last_created_obj = None
        
        # Priority reference for collection linking
        active_ref = valid_targets[0]
        current_collection = active_ref.users_collection[0] if active_ref.users_collection else context.scene.collection
        
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(".pc2"):
                
                pc2_base_name = os.path.splitext(filename)[0]
                source_obj = None
                
                # Check if pc2 base name ENDS WITH any loaded target mesh name
                for obj in valid_targets:
                    if pc2_base_name.endswith(obj.name):
                        source_obj = obj
                        break
                
                # If a matching object was found, scatter it
                if source_obj:
                    new_obj = source_obj.copy()
                    new_obj.data = source_obj.data.copy() 
                    
                    new_obj.name = pc2_base_name
                    new_obj.data.name = f"{pc2_base_name}_Mesh"
                    
                    current_collection.objects.link(new_obj)
                    new_obj.select_set(True)
                    last_created_obj = new_obj
                    
                    count += 1
                
        if last_created_obj:
            context.view_layer.objects.active = last_created_obj

        if count == 0:
            self.report({'WARNING'}, "No .pc2 filenames ended with any loaded mesh names.")
        else:
            self.report({'INFO'}, f"Scatter complete. Created and selected {count} new meshes.")
            
        return {'FINISHED'}

# --- 5. UI Panel ---
class VIEW3D_PT_pc2_scatter(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PC2 Tools"
    bl_label = "PC2 Scatter"

    def draw(self, context):
        layout = self.layout
        props = context.scene.pc2_scatter_props

        # Target Meshes Box with Scrollable List
        layout.label(text="Target Meshes:", icon='GROUP')
        
        row = layout.row()
        # The scrollable list
        row.template_list("PC2_UL_target_list", "", props, "target_meshes", props, "target_meshes_index", rows=5)
        
        # The +, -, and Clear buttons on the side
        col = row.column(align=True)
        col.operator("object.add_target_meshes", text="", icon='ADD')
        col.operator("object.remove_target_mesh", text="", icon='REMOVE')
        col.separator()
        col.operator("object.clear_target_meshes", text="", icon='TRASH')
        
        layout.separator()
        
        # Folder Path
        layout.prop(props, "pc2_folder_path")
        
        layout.separator()
        
        # Execute Button
        row = layout.row()
        row.scale_y = 1.5
        row.operator("object.scatter_from_pc2", text="Execute Scatter", icon='MOD_PARTICLES')

# --- 6. Registration ---
classes = (
    PC2TargetItem,
    PC2ScatterProperties,
    PC2_UL_target_list,
    OBJECT_OT_add_target_meshes,
    OBJECT_OT_remove_target_mesh,
    OBJECT_OT_clear_target_meshes,
    OBJECT_OT_scatter_from_pc2,
    VIEW3D_PT_pc2_scatter
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pc2_scatter_props = bpy.props.PointerProperty(type=PC2ScatterProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pc2_scatter_props

if __name__ == "__main__":
    register()