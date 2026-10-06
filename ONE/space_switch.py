import maya.cmds as cmds

class FlexibleSpaceSwitchUI():
    def __init__(self):
        self.window_name = "FlexSpaceSwitchTool"
        
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.create_ui()

    def create_ui(self):
        self.window = cmds.window(self.window_name, title="Advanced Space Switcher", widthHeight=(450, 320), sizeable=True)
        
        main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=['both', 10])
        
        # --- SELECTION SECTION ---
        cmds.separator(height=10, style='none')
        cmds.frameLayout(label="Target Objects (Select and Load or Type)", collapsable=False, marginWidth=5)
        
        # Global Driver
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2, columnWidth3=(100, 200, 50))
        cmds.text(label=" Space 1 Driver:")
        self.global_field = cmds.textField(placeholderText="e.g. world_ctl")
        cmds.button(label="Load", command=lambda x: self.load_selection(self.global_field))
        cmds.setParent('..')

        # Spine Driver
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2, columnWidth3=(100, 200, 50))
        cmds.text(label=" Space 2 Driver:")
        self.spine_field = cmds.textField(placeholderText="e.g. spine_IK_ctl")
        cmds.button(label="Load", command=lambda x: self.load_selection(self.spine_field))
        cmds.setParent('..')

        # Driven Hand
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2, columnWidth3=(100, 200, 50))
        cmds.text(label=" Driven Control:")
        self.hand_field = cmds.textField(placeholderText="e.g. hand_L_ctl")
        cmds.button(label="Load", command=lambda x: self.load_selection(self.hand_field))
        cmds.setParent('..')
        cmds.setParent('..')

        # --- SETTINGS SECTION ---
        cmds.frameLayout(label="Naming Settings", collapsable=False, marginWidth=5)
        
        # Attribute Name
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=2, columnWidth2=(100, 100))
        cmds.text(label=" Attr Name:")
        self.attr_name_field = cmds.textField(text="space")
        cmds.setParent('..')

        # Enum Labels
        cmds.rowLayout(numberOfColumns=4, adjustableColumn=2, columnWidth4=(100, 100, 50, 100))
        cmds.text(label=" Enum Labels:")
        self.label1_field = cmds.textField(text="Global")
        cmds.text(label=" : ")
        self.label2_field = cmds.textField(text="Spine")
        cmds.setParent('..')
        cmds.setParent('..')

        # --- EXECUTE ---
        cmds.separator(height=10, style='in')
        cmds.button(label="BUILD SPACE SWITCH", height=45, backgroundColor=[0.2, 0.4, 0.6], command=self.execute_logic)
        cmds.separator(height=10, style='none')

        cmds.showWindow(self.window)

    def load_selection(self, field):
        sel = cmds.ls(selection=True)
        if sel:
            cmds.textField(field, edit=True, text=sel[0])
        else:
            cmds.warning("Please select an object in the viewport first.")

    def execute_logic(self, *args):
        # Pull data from UI
        global_drv = cmds.textField(self.global_field, query=True, text=True)
        spine_drv = cmds.textField(self.spine_field, query=True, text=True)
        driven_ctl = cmds.textField(self.hand_field, query=True, text=True)
        
        attr_name = cmds.textField(self.attr_name_field, query=True, text=True)
        label1 = cmds.textField(self.label1_field, query=True, text=True)
        label2 = cmds.textField(self.label2_field, query=True, text=True)

        # Basic Validation
        for obj in [global_drv, spine_drv, driven_ctl]:
            if not obj or not cmds.objExists(obj):
                cmds.error(f"Object '{obj}' is missing or does not exist in the scene.")
                return

        # 1. Setup Group
        space_grp = driven_ctl + "_space_GRP"
        if not cmds.objExists(space_grp):
            space_grp = cmds.group(empty=True, name=space_grp)
            cmds.delete(cmds.parentConstraint(driven_ctl, space_grp))
            parent = cmds.listRelatives(driven_ctl, parent=True)
            if parent:
                cmds.parent(space_grp, parent[0])
            cmds.parent(driven_ctl, space_grp)

        # 2. Setup Attribute
        enum_string = f"{label1}:{label2}"
        if not cmds.attributeQuery(attr_name, node=driven_ctl, exists=True):
            cmds.addAttr(driven_ctl, longName=attr_name, attributeType="enum", enumName=enum_string, keyable=True)
        else:
            # If it exists, update the enum strings just in case
            cmds.addAttr(f"{driven_ctl}.{attr_name}", edit=True, enumName=enum_string)

        # 3. Setup Constraints
        constraint = cmds.parentConstraint(global_drv, spine_drv, space_grp, maintainOffset=True)[0]
        weights = cmds.parentConstraint(constraint, q=True, weightAliasList=True)
        drivers = [global_drv, spine_drv]

        # 4. Setup Conditions
        for i, weight in enumerate(weights):
            clean_drv = drivers[i].split("|")[-1].split(":")[-1]
            cond_node = f"{driven_ctl}_{clean_drv}_cond"
            
            # Create node if it doesn't exist
            if not cmds.objExists(cond_node):
                cond_node = cmds.createNode("condition", name=cond_node)
            
            cmds.setAttr(f"{cond_node}.secondTerm", i)
            cmds.setAttr(f"{cond_node}.colorIfTrueR", 1)
            cmds.setAttr(f"{cond_node}.colorIfFalseR", 0)
            
            # Use try-except for connections to avoid errors if already connected
            try:
                cmds.connectAttr(f"{driven_ctl}.{attr_name}", f"{cond_node}.firstTerm", force=True)
                cmds.connectAttr(f"{cond_node}.outColorR", f"{constraint}.{weight}", force=True)
            except:
                pass

        print(f"Space switch '{attr_name}' build complete for {driven_ctl}!")

# Run
FlexibleSpaceSwitchUI()