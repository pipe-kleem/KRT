import maya.cmds as cmds

class NormalConstraintTool(object):
    def __init__(self):
        self.window_name = "NormalConstraintWindow"
        self.build_ui()

    def build_ui(self):
        # Close the window if it already exists to prevent duplicates
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        # Create the main window
        self.window = cmds.window(self.window_name, title="Normal Constraint Tool", widthHeight=(450, 160))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=('both', 10))

        cmds.separator(height=10, style='none')

        # Source Object UI
        self.source_field = cmds.textFieldButtonGrp(
            label='Source Mesh:',
            text='',
            buttonLabel='Load Selected',
            buttonCommand=self.load_source
        )

        # Target Objects UI
        self.target_field = cmds.textFieldButtonGrp(
            label='Target Objects:',
            text='',
            buttonLabel='Load Selected',
            buttonCommand=self.load_targets
        )

        cmds.separator(height=10, style='in')

        # Apply Button
        cmds.button(label='Apply Script (Snap & Delete Constraints)', height=40, command=self.apply_script)

        # Display the window
        cmds.showWindow(self.window)

    def load_source(self, *args):
        """Loads the first selected object into the source text field."""
        selection = cmds.ls(selection=True)
        if selection:
            cmds.textFieldButtonGrp(self.source_field, edit=True, text=selection[0])
        else:
            cmds.warning("Please select a source mesh.")

    def load_targets(self, *args):
        """Loads all selected objects into the target text field as a comma-separated list."""
        selection = cmds.ls(selection=True)
        if selection:
            target_str = ",".join(selection)
            cmds.textFieldButtonGrp(self.target_field, edit=True, text=target_str)
        else:
            cmds.warning("Please select at least one target object.")

    def apply_script(self, *args):
        """Applies the normal constraint to all targets and deletes the constraints."""
        source = cmds.textFieldButtonGrp(self.source_field, query=True, text=True)
        targets_str = cmds.textFieldButtonGrp(self.target_field, query=True, text=True)

        # Validation
        if not source or not cmds.objExists(source):
            cmds.error("A valid source mesh is required. Please load it.")
            return

        if not targets_str:
            cmds.error("Target objects are required. Please load them.")
            return

        # Split the comma-separated string back into a list
        targets = targets_str.split(",")
        constraints_to_delete = []

        for target in targets:
            target = target.strip()
            if cmds.objExists(target):
                # Create the normal constraint (maintainOffset is not supported or needed here)
                # By default, it will snap the aimVector (X-axis) to the surface normal
                constraint = cmds.normalConstraint(
                    source, 
                    target, 
                    aimVector=(1, 0, 0), 
                    upVector=(0, 1, 0), 
                    worldUpType="vector", 
                    weight=1
                )
                
                if constraint:
                    constraints_to_delete.extend(constraint)
            else:
                cmds.warning("Target object '{}' does not exist. Skipping...".format(target))

        # Delete all constraints in one go
        if constraints_to_delete:
            cmds.delete(constraints_to_delete)
            print("Successfully aligned objects and cleaned up constraints.")

# Execute the tool
NormalConstraintTool()