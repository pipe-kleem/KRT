import maya.cmds as cmds
import maya.api.OpenMaya as om
import math

class JointOrientUI(object):
    def __init__(self):
        self.window_name = "JointOrientWindow"
        
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.window = cmds.window(self.window_name, title="Transfer Rotate to Orient", widthHeight=(320, 300))
        self.layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, margins=5)
        
        cmds.text(label="1. Select joints in Maya, then click Load:", align="left", font="boldLabelFont")
        cmds.button(label="Load Joints with Rotation", command=self.load_joints, height=30)
        
        cmds.text(label="2. Select joints below to convert:", align="left", font="boldLabelFont")
        
        self.joint_list = cmds.textScrollList(allowMultiSelection=True, height=180, selectCommand=self.select_in_viewport)
        
        cmds.button(label="Transfer Rotate to Joint Orient", command=self.convert_joints, backgroundColor=(0.2, 0.4, 0.2), height=40)
        
        cmds.showWindow(self.window)

    def select_in_viewport(self, *args):
        selected_in_ui = cmds.textScrollList(self.joint_list, query=True, selectItem=True)
        if selected_in_ui:
            cmds.select(selected_in_ui, replace=True)
        else:
            cmds.select(clear=True)

    def load_joints(self, *args):
        cmds.textScrollList(self.joint_list, edit=True, removeAll=True)
        sel = cmds.ls(selection=True, type="joint")
        
        if not sel:
            cmds.warning("Please select joints in the Maya viewport first.")
            return
            
        for jnt in sel:
            rot = cmds.getAttr(f"{jnt}.rotate")[0]
            if any(abs(val) > 0.0001 for val in rot):
                cmds.textScrollList(self.joint_list, edit=True, append=jnt)

    def convert_joints(self, *args):
        selected_in_ui = cmds.textScrollList(self.joint_list, query=True, selectItem=True)
        
        if not selected_in_ui:
            cmds.warning("Please select at least one joint from the UI list.")
            return
            
        for jnt in selected_in_ui:
            rot = cmds.getAttr(f"{jnt}.rotate")[0]
            jo = cmds.getAttr(f"{jnt}.jointOrient")[0]
            
            euler_rot = om.MEulerRotation(math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2]))
            euler_jo = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]))
            
            quat_rot = euler_rot.asQuaternion()
            quat_jo = euler_jo.asQuaternion()
            quat_combined = quat_rot * quat_jo 
            
            new_euler = quat_combined.asEulerRotation()
            new_jo = [math.degrees(new_euler.x), math.degrees(new_euler.y), math.degrees(new_euler.z)]
            
            cmds.setAttr(f"{jnt}.jointOrientX", new_jo[0])
            cmds.setAttr(f"{jnt}.jointOrientY", new_jo[1])
            cmds.setAttr(f"{jnt}.jointOrientZ", new_jo[2])
            
            cmds.setAttr(f"{jnt}.rotateX", 0)
            cmds.setAttr(f"{jnt}.rotateY", 0)
            cmds.setAttr(f"{jnt}.rotateZ", 0)
            
            # Remove only the processed joint from the UI list
            cmds.textScrollList(self.joint_list, edit=True, removeItem=jnt)
            print(f"Transferred rotation to jointOrient for: {jnt}")
            
        # FIXED: Explicitly force Maya to keep these exact joints selected in the viewport 
        # after they vanish from the UI menu, so you don't lose your place.
        cmds.select(selected_in_ui, replace=True)

JointOrientUI()