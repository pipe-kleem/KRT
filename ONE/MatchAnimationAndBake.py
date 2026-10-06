import maya.cmds as cmds
import json

class SmartConstraintUI:
    def __init__(self):
        self.window_name = "SmartConstraintWindow"
        self.title = "Smart Constraint & Bake Tool"
        self.size = (420, 560)
        
        # Background Data (Stores the actual long names/namespaces to prevent clashing)
        self.source_data = []
        self.target_data = []
        
        self.build_ui()
        self.load_defaults()
        
    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name, window=True)
            
        cmds.window(self.window_name, title=self.title, widthHeight=self.size, sizeable=True)
        
        main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=10, margins=10)
        
        # --- TOP SECTION: Source & Target ---
        cmds.text(label="1. Define Source(s) and Target(s)", font="boldLabelFont", align="left")
        cmds.text(label="Tip: Double-click any item to manually edit its text.", font="smallPlainLabelFont", align="left")
        
        list_layout = cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 200), adjustableColumn=2)
        
        # Source Column
        cmds.columnLayout(adjustableColumn=True)
        cmds.text(label="SOURCE", font="boldLabelFont", bgc=(0.2, 0.3, 0.4), height=20)
        
        self.source_list_ui = cmds.textScrollList(allowMultiSelection=True, height=180,
                                                  selectCommand=lambda *args: self.select_in_viewport(self.source_list_ui, self.source_data),
                                                  doubleClickCommand=lambda *args: self.edit_item(self.source_list_ui, self.source_data),
                                                  dragCallback=self.drag_cb,
                                                  dropCallback=self.drop_cb)
        
        cmds.button(label="Add Selected", command=lambda x: self.add_to_list(self.source_list_ui, self.source_data))
        cmds.button(label="Remove Paired", command=lambda x: self.remove_paired_items(self.source_list_ui))
        cmds.button(label="Clear All", command=lambda x: self.clear_both_lists())
        cmds.setParent("..")
        
        # Target Column
        cmds.columnLayout(adjustableColumn=True)
        cmds.text(label="TARGET", font="boldLabelFont", bgc=(0.4, 0.3, 0.2), height=20)
        
        self.target_list_ui = cmds.textScrollList(allowMultiSelection=True, height=180,
                                                  selectCommand=lambda *args: self.select_in_viewport(self.target_list_ui, self.target_data),
                                                  doubleClickCommand=lambda *args: self.edit_item(self.target_list_ui, self.target_data),
                                                  dragCallback=self.drag_cb,
                                                  dropCallback=self.drop_cb)
        
        cmds.button(label="Add Selected", command=lambda x: self.add_to_list(self.target_list_ui, self.target_data))
        cmds.button(label="Remove Paired", command=lambda x: self.remove_paired_items(self.target_list_ui))
        cmds.button(label="Clear All", command=lambda x: self.clear_both_lists())
        cmds.setParent("..")
        
        cmds.setParent(main_layout)
        
        # --- PRESET MANAGEMENT ---
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 200), adjustableColumn=2)
        cmds.button(label="Load Preset (JSON)", height=30, bgc=(0.2, 0.4, 0.3), command=self.load_preset)
        cmds.button(label="Save Preset (JSON)", height=30, bgc=(0.2, 0.3, 0.4), command=self.save_preset)
        cmds.setParent("..")
        
        cmds.separator(height=10, style="in")
        
        # --- BOTTOM SECTION: Actions ---
        cmds.text(label="2. Actions", font="boldLabelFont", align="left")
        
        cmds.button(label="Constraint (Without Offset)", height=35, bgc=(0.25, 0.35, 0.45), 
                    command=lambda x: self.apply_constraints(maintain_offset=False))
                    
        cmds.button(label="Constraint (With Offset)", height=35, bgc=(0.35, 0.45, 0.55), 
                    command=lambda x: self.apply_constraints(maintain_offset=True))
                    
        cmds.button(label="Delete Constraints", height=30, bgc=(0.6, 0.3, 0.3), 
                    command=self.delete_constraints)
                    
        cmds.separator(height=10, style="none")
        
        cmds.button(label="Bake Animation", height=40, bgc=(0.7, 0.5, 0.2), 
                    command=self.bake_animation)
        
        cmds.showWindow(self.window_name)

    # --- JSON PRESET LOGIC ---
    def save_preset(self, *args):
        if not self.source_data and not self.target_data:
            cmds.warning("Lists are empty. Nothing to save.")
            return
            
        file_path = cmds.fileDialog2(fileFilter="JSON Files (*.json)", dialogStyle=2, fileMode=0, caption="Save Constraints Preset")
        if file_path:
            data_to_save = {
                "sources": self.source_data,
                "targets": self.target_data
            }
            try:
                with open(file_path[0], 'w') as f:
                    json.dump(data_to_save, f, indent=4)
                print(f"Preset successfully saved to: {file_path[0]}")
            except Exception as e:
                cmds.error(f"Failed to save preset. Error: {e}")

    def load_preset(self, *args):
        file_path = cmds.fileDialog2(fileFilter="JSON Files (*.json)", dialogStyle=2, fileMode=1, caption="Load Constraints Preset")
        if file_path:
            try:
                with open(file_path[0], 'r') as f:
                    loaded_data = json.load(f)
                
                if "sources" in loaded_data and "targets" in loaded_data:
                    self.clear_both_lists() 
                    
                    for src in loaded_data["sources"]:
                        self.source_data.append(src)
                        cmds.textScrollList(self.source_list_ui, edit=True, append=self.get_clean_name(src))
                        
                    for tgt in loaded_data["targets"]:
                        self.target_data.append(tgt)
                        cmds.textScrollList(self.target_list_ui, edit=True, append=self.get_clean_name(tgt))
                        
                    print(f"Preset successfully loaded from: {file_path[0]}")
                else:
                    cmds.warning("Invalid JSON format. Make sure it was generated by this tool.")
            except Exception as e:
                cmds.error(f"Failed to load preset. Error: {e}")

    # --- DRAG AND DROP LOGIC ---
    def drag_cb(self, dragControl, x, y, modifiers):
        return [dragControl]

    def drop_cb(self, dragControl, dropControl, messages, x, y, dragType):
        if dragControl == dropControl:
            return 
            
        if dragControl.endswith(self.source_list_ui.split('|')[-1]) and dropControl.endswith(self.target_list_ui.split('|')[-1]):
            from_ui, from_data = self.source_list_ui, self.source_data
            to_ui, to_data = self.target_list_ui, self.target_data
        elif dragControl.endswith(self.target_list_ui.split('|')[-1]) and dropControl.endswith(self.source_list_ui.split('|')[-1]):
            from_ui, from_data = self.target_list_ui, self.target_data
            to_ui, to_data = self.source_list_ui, self.source_data
        else:
            return

        selected_indices = cmds.textScrollList(from_ui, query=True, selectIndexedItem=True)
        if not selected_indices:
            return
            
        for i in sorted(selected_indices, reverse=True):
            item_data = from_data[i - 1]
            cmds.textScrollList(from_ui, edit=True, removeIndexedItem=i)
            from_data.pop(i - 1)
            
            to_data.append(item_data)
            cmds.textScrollList(to_ui, edit=True, append=self.get_clean_name(item_data))
            
        cmds.select(clear=True)

    # --- DEFAULTS ---
    def load_defaults(self):
        default_pairs = [
            # Original mappings
            ("kartaviryaarjuna:forearmFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_R0_mid_ctl"),
            ("kartaviryaarjuna:neck", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:neck_C0_fk0_ctl"),
            ("kartaviryaarjuna:handFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_R0_ik_ctl"),
            ("kartaviryaarjuna:handFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_R0_ikRot_ctl"),
            ("kartaviryaarjuna:neck", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:neck_C0_fk1_ctl"),
            ("kartaviryaarjuna:footFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:leg_R0_ik_ctl"),
            ("kartaviryaarjuna:spine", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:body_C0_ctl"),
            
            # First batch of additions (Fixed L0 targets)
            ("kartaviryaarjuna:forearmFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_L0_mid_ctl"),
            ("kartaviryaarjuna:handFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_L0_ik_ctl"),
            ("kartaviryaarjuna:handFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:arm_L0_ikRot_ctl"),
            ("kartaviryaarjuna:footFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:leg_L0_ik_ctl"),
            
            # Second batch of additions
            ("kartaviryaarjuna:shoulderFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:shoulder_R0_ctl"),
            ("kartaviryaarjuna:shoulderFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:shoulder_L0_shoulder_jnt"),
            ("kartaviryaarjuna:upper_armFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:shoulder_L0_orbit_ctl"),
            ("kartaviryaarjuna:upper_armFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:shoulder_R0_orbit_ctl"),
            ("kartaviryaarjuna:shinFBXASC046R", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:leg_R0_mid_ctl"),
            ("kartaviryaarjuna:shinFBXASC046L", "KLIB_char_kartaviryaarjuna_a_rigMain_v001:leg_L0_mid_ctl")
        ]
        
        for src, tgt in default_pairs:
            self.source_data.append(src)
            self.target_data.append(tgt)
            cmds.textScrollList(self.source_list_ui, edit=True, append=self.get_clean_name(src))
            cmds.textScrollList(self.target_list_ui, edit=True, append=self.get_clean_name(tgt))

    # --- LIST MANAGEMENT & SELECTION ---
    def get_clean_name(self, long_name):
        return long_name.split('|')[-1].split(':')[-1]

    def select_in_viewport(self, list_widget, data_list):
        selected_indices = cmds.textScrollList(list_widget, query=True, selectIndexedItem=True)
        if not selected_indices:
            cmds.select(clear=True)
            return
            
        objects_to_select = []
        for i in selected_indices:
            obj = data_list[i - 1]
            if cmds.objExists(obj):
                objects_to_select.append(obj)
            else:
                cmds.warning(f"Cannot select: '{self.get_clean_name(obj)}' no longer exists in the scene.")
                
        if objects_to_select:
            cmds.select(objects_to_select, replace=True)

    def edit_item(self, list_widget, data_list):
        selected_indices = cmds.textScrollList(list_widget, query=True, selectIndexedItem=True)
        if not selected_indices:
            return
            
        index = selected_indices[0] - 1 
        current_text = data_list[index]

        result = cmds.promptDialog(
            title='Manual Edit',
            message='Edit the full name/path:',
            text=current_text,
            button=['Save', 'Cancel'],
            defaultButton='Save',
            cancelButton='Cancel',
            dismissString='Cancel'
        )

        if result == 'Save':
            new_text = cmds.promptDialog(query=True, text=True)
            if new_text:
                data_list[index] = new_text
                cmds.textScrollList(list_widget, edit=True, removeIndexedItem=index+1)
                cmds.textScrollList(list_widget, edit=True, appendPosition=[index+1, self.get_clean_name(new_text)])
                cmds.textScrollList(list_widget, edit=True, selectIndexedItem=index+1)

    def add_to_list(self, list_widget, data_list):
        selection = cmds.ls(selection=True, long=True) 
        if not selection:
            cmds.warning("Please select an object in the scene first.")
            return
            
        for sel in selection:
            data_list.append(sel)
            cmds.textScrollList(list_widget, edit=True, append=self.get_clean_name(sel))

    def remove_paired_items(self, active_ui):
        selected_indices = cmds.textScrollList(active_ui, query=True, selectIndexedItem=True)
        if not selected_indices:
            return
            
        for i in sorted(selected_indices, reverse=True):
            if i <= cmds.textScrollList(self.source_list_ui, query=True, numberOfItems=True):
                cmds.textScrollList(self.source_list_ui, edit=True, removeIndexedItem=i)
                if (i - 1) < len(self.source_data):
                    self.source_data.pop(i - 1)
                    
            if i <= cmds.textScrollList(self.target_list_ui, query=True, numberOfItems=True):
                cmds.textScrollList(self.target_list_ui, edit=True, removeIndexedItem=i)
                if (i - 1) < len(self.target_data):
                    self.target_data.pop(i - 1)

    def clear_both_lists(self):
        cmds.textScrollList(self.source_list_ui, edit=True, removeAll=True)
        cmds.textScrollList(self.target_list_ui, edit=True, removeAll=True)
        del self.source_data[:]
        del self.target_data[:]

    # --- LOGIC ---
    def is_channel_available(self, node, transform_type):
        axes = ['X', 'Y', 'Z']  
        for axis in axes:
            attr = f"{node}.{transform_type}{axis}"
            try:
                is_locked = cmds.getAttr(attr, lock=True)
                is_keyable = cmds.getAttr(attr, keyable=True)
                is_channel_box = cmds.getAttr(attr, channelBox=True)
                if not is_locked and (is_keyable or is_channel_box):
                    return True
            except:
                pass
        return False

    def apply_constraints(self, maintain_offset):
        sources = self.source_data
        targets = self.target_data
        
        if not sources or not targets:
            cmds.warning("You need at least one Source and one Target populated in the lists.")
            return
            
        if len(sources) != len(targets):
            cmds.warning("Source and Target lists must have the exact same number of items for 1-to-1 constraint.")
            return

        for source, target in zip(sources, targets):
            if not cmds.objExists(source):
                cmds.warning(f"Source '{self.get_clean_name(source)}' does not exist. Skipping pair.")
                continue
            if not cmds.objExists(target):
                cmds.warning(f"Target '{self.get_clean_name(target)}' does not exist. Skipping pair.")
                continue
                
            has_t = self.is_channel_available(target, 'translate')
            has_r = self.is_channel_available(target, 'rotate')

            clean_target = self.get_clean_name(target)
            clean_source = self.get_clean_name(source)

            try:
                if has_t and has_r:
                    cmds.parentConstraint(source, target, maintainOffset=maintain_offset)
                    print(f"Success: Parent Constraint applied from {clean_source} to {clean_target}")
                elif has_r and not has_t:
                    cmds.orientConstraint(source, target, maintainOffset=maintain_offset)
                    print(f"Success: Orient Constraint applied from {clean_source} to {clean_target}")
                elif has_t and not has_r:
                    cmds.pointConstraint(source, target, maintainOffset=maintain_offset)
                    print(f"Success: Point Constraint applied from {clean_source} to {clean_target}")
                else:
                    cmds.warning(f"Skipped '{clean_target}': Translation and Rotation are both locked.")
            except Exception as e:
                cmds.error(f"Failed to constrain {clean_target}. Error: {e}")

    def delete_constraints(self, *args):
        targets = self.target_data
        if not targets:
            cmds.warning("No targets specified.")
            return
            
        for target in targets:
            if cmds.objExists(target):
                constraints = cmds.listRelatives(target, type='constraint', fullPath=True)
                clean_target = self.get_clean_name(target)
                if constraints:
                    cmds.delete(constraints)
                    print(f"Deleted constraints on {clean_target}")
                else:
                    print(f"No constraints found on {clean_target}")

    def bake_animation(self, *args):
        targets = self.target_data
        valid_targets = [tgt for tgt in targets if cmds.objExists(tgt)]
        
        if not valid_targets:
            cmds.warning("No valid targets available to bake.")
            return
            
        start_time = cmds.playbackOptions(query=True, minTime=True)
        end_time = cmds.playbackOptions(query=True, maxTime=True)
        
        cmds.bakeResults(valid_targets, 
                         simulation=True, 
                         time=(start_time, end_time), 
                         sampleBy=1, 
                         disableImplicitControl=True, 
                         preserveOutsideKeys=True, 
                         sparseAnimCurveBake=False, 
                         removeBakedAttributeFromLayer=False, 
                         removeBakedAnimFromLayer=False, 
                         bakeOnOverrideLayer=False, 
                         minimizeRotation=True, 
                         controlPoints=False, 
                         shape=True)
                         
        print(f"Successfully baked animation from frame {start_time} to {end_time}")

# Execute the UI
SmartConstraintUI()