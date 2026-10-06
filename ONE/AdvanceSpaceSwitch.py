import maya.cmds as cmds

class AdvancedSpaceSwitchUI(object):
    def __init__(self):
        self.window_name = "AdvSpaceSwitchWindow"
        self.space_fields = []  # Stores tuples of (driver_tf, enum_label_tf)
        self.target_field = None
        self.attr_name_field = None
        self.spaces_layout = None
        self.show()

    def show(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        # Main Window
        self.window = cmds.window(self.window_name, title="Professional Space Switcher", widthHeight=(450, 400))
        self.main_layout = cmds.columnLayout(adjustableColumn=True)

        # --- 1. TARGET CONTROL FRAME ---
        cmds.frameLayout(label="1. Target Controls (Driven)", marginHeight=8, marginWidth=8, backgroundColor=(0.15, 0.15, 0.15))
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 80), adjustableColumn=1)
        self.target_field = cmds.textField(placeholderText="Select controls to be driven (comma separated)...")
        cmds.button(label="<<< Set", backgroundColor=(0.25, 0.25, 0.25), command=self.set_target)
        cmds.setParent('..') # Exit rowLayout
        cmds.setParent('..') # Exit frameLayout

        # --- 2. ATTRIBUTE SETTINGS FRAME ---
        cmds.frameLayout(label="2. Attribute Settings", marginHeight=8, marginWidth=8, backgroundColor=(0.15, 0.15, 0.15))
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 300), adjustableColumn=2)
        cmds.text(label="Attribute Name: ", align="right")
        self.attr_name_field = cmds.textField(text="Space", annotation="The name of the Enum attribute that will appear in the Channel Box")
        cmds.setParent('..')
        cmds.setParent('..')

        # --- 3. SPACE DRIVERS FRAME ---
        cmds.frameLayout(label="3. Space Drivers (Parents)", marginHeight=8, marginWidth=8, backgroundColor=(0.15, 0.15, 0.15))
        
        # Container specifically for dynamic rows
        self.spaces_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.add_space_field() # Add the first default row
        cmds.setParent('..') # Exit spaces_layout
        
        cmds.separator(height=10, style='none')
        # The button is outside spaces_layout, so it will always stay at the bottom
        cmds.button(label="+ Add New Space Driver", height=30, backgroundColor=(0.2, 0.35, 0.45), command=lambda *args: self.add_space_field())
        cmds.setParent('..') # Exit frameLayout

        # --- 4. EXECUTION & UNDO SECTION ---
        cmds.separator(height=10, style='none')
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 100), adjustableColumn=1, columnAttach=[(1, 'both', 5), (2, 'both', 5)])
        cmds.button(label="CREATE SPACE SWITCH", height=45, backgroundColor=(0.3, 0.5, 0.3), command=self.run_setup)
        cmds.button(label="Undo", height=45, backgroundColor=(0.5, 0.3, 0.3), command=self.undo_action)
        cmds.setParent('..')

        cmds.showWindow(self.window)

    def set_target(self, *args):
        sel = cmds.ls(selection=True)
        if sel:
            cmds.textField(self.target_field, edit=True, text=", ".join(sel))
        else:
            cmds.warning("Please select at least one target control first.")

    def add_space_field(self):
        # Explicitly set the parent to the container above the button
        cmds.setParent(self.spaces_layout)
        
        row = cmds.rowLayout(numberOfColumns=4, columnWidth4=(180, 50, 120, 60), adjustableColumn=1)
        
        driver_tf = cmds.textField(placeholderText="Driver Object...")
        cmds.button(label="<<< Set", backgroundColor=(0.25, 0.25, 0.25), command=lambda *args, f=driver_tf: self.set_space_field(f))
        
        enum_tf = cmds.textField(placeholderText="Enum Label (e.g. Head)")
        cmds.button(label="Remove", backgroundColor=(0.4, 0.2, 0.2), command=lambda *args, r=row, d_tf=driver_tf, e_tf=enum_tf: self.remove_space_field(r, d_tf, e_tf))
        
        # CRITICAL FIX: Step out of the rowLayout so the hierarchy stays clean
        cmds.setParent('..') 
        
        self.space_fields.append((driver_tf, enum_tf))

    def set_space_field(self, text_field):
        sel = cmds.ls(selection=True)
        if sel:
            obj_name = sel[0]
            cmds.textField(text_field, edit=True, text=obj_name)
            
            for d_tf, e_tf in self.space_fields:
                if d_tf == text_field:
                    current_enum = cmds.textField(e_tf, query=True, text=True)
                    if not current_enum:
                        clean_label = obj_name.split('_')[0]
                        cmds.textField(e_tf, edit=True, text=clean_label)
                    break
        else:
            cmds.warning("Please select a space driver first.")

    def remove_space_field(self, row_layout, driver_tf, enum_tf):
        if len(self.space_fields) > 1:
            cmds.deleteUI(row_layout)
            self.space_fields.remove((driver_tf, enum_tf))
        else:
            cmds.warning("You must have at least one space driver.")

    def undo_action(self, *args):
        try:
            cmds.undo()
            print("Successfully undid the last action.")
        except:
            cmds.warning("Nothing to undo.")

    def run_setup(self, *args):
        target_str = cmds.textField(self.target_field, query=True, text=True)
        attr_name = cmds.textField(self.attr_name_field, query=True, text=True).strip()
        
        targets = [t.strip() for t in target_str.replace(' ', ',').split(',') if t.strip()]

        spaces_data = []
        for d_tf, e_tf in self.space_fields:
            driver = cmds.textField(d_tf, query=True, text=True).strip()
            label = cmds.textField(e_tf, query=True, text=True).strip()
            if driver:
                if not label: 
                    label = driver.split('_')[0]
                spaces_data.append((driver, label))

        if not targets:
            cmds.error("At least one valid Target Control is required.")
            return
        if not attr_name:
            cmds.error("Attribute Name cannot be empty.")
            return
        if not spaces_data:
            cmds.error("At least one valid Space Driver is required.")
            return
            
        for t in targets:
            if not cmds.objExists(t):
                cmds.error(f"Target Control '{t}' does not exist in the scene.")
                return

        drivers = [data[0] for data in spaces_data]
        enum_labels = [data[1] for data in spaces_data]

        for driver in drivers:
            if not cmds.objExists(driver):
                cmds.error(f"Space driver '{driver}' does not exist in the scene.")
                return

        cmds.undoInfo(openChunk=True, chunkName="CreateSpaceSwitch")
        try:
            for target in targets:
                buffer_grp = cmds.group(empty=True, name=f"{target}_{attr_name}_grp")
                cmds.matchTransform(buffer_grp, target)
                
                target_parent = cmds.listRelatives(target, parent=True)
                if target_parent:
                    cmds.parent(buffer_grp, target_parent[0])
                
                cmds.parent(target, buffer_grp)

                enum_string = ":".join(enum_labels)
                
                if not cmds.attributeQuery(attr_name, node=target, exists=True):
                    cmds.addAttr(target, longName=attr_name, attributeType='enum', enumName=enum_string, keyable=True)
                else:
                    cmds.warning(f"Attribute '{attr_name}' already exists on {target}. Overwriting connections.")

                constraint = cmds.parentConstraint(drivers, buffer_grp, maintainOffset=True)[0]
                weight_aliases = cmds.parentConstraint(constraint, query=True, weightAliasList=True)

                for i, driver in enumerate(drivers):
                    for j, weight_attr in enumerate(weight_aliases):
                        val = 1 if i == j else 0
                        cmds.setDrivenKeyframe(
                            f"{constraint}.{weight_attr}",
                            currentDriver=f"{target}.{attr_name}",
                            driverValue=i,
                            value=val
                        )

            cmds.select(targets)
            print(f"Success! '{attr_name}' space switch created for: {', '.join(targets)}.")
            
        except Exception as e:
            cmds.error(f"An error occurred during creation: {e}")
        finally:
            cmds.undoInfo(closeChunk=True)

# Run the UI
AdvancedSpaceSwitchUI()