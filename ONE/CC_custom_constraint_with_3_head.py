import maya.cmds as cmds

class CC3ToMGearStrictUI(object):
    def __init__(self):
        self.window_name = "CC3_mGear_Connector_Strict_UI"
        
        # Specific CC3 facial joints to skip when toggled
        self.facial_joints_to_skip = [
            "CC_Base_JawRoot", "CC_Base_FacialBone", "CC_Base_Teeth02", 
            "CC_Base_Tongue02", "CC_Base_Teeth01", "CC_Base_Tongue01", 
            "CC_Base_UpperJaw", "CC_Base_L_Eye", "CC_Base_Tongue03", "CC_Base_R_Eye"
        ]
        
        # Format: ("mGear_Driver", "CC3_Driven_Base_Name", ["constraintTypes"])
        self.exact_mapping = [
            # Root & Pelvis
            ("local_C0_ctl", "CC_Base_BoneRoot", ["parentConstraint", "scaleConstraint"]),
            ("spine_C0_0_jnt", "CC_Base_Hip", ["parentConstraint"]),
            ("spine_C0_0_jnt", "CC_Base_Pelvis", ["parentConstraint"]),
            
            # Spine & Head
            ("spine_C0_1_jnt", "CC_Base_Waist", ["parentConstraint"]),
            ("spine_C0_2_jnt", "CC_Base_Spine01", ["parentConstraint"]),
            ("spine_C0_4_jnt", "CC_Base_Spine02", ["parentConstraint"]),
            ("neck_C0_0_jnt", "CC_Base_NeckTwist01", ["parentConstraint"]),
            ("neck_C0_1_jnt", "CC_Base_NeckTwist02", ["parentConstraint"]),
            ("neck_C0_head_jnt", "CC_Base_Head", ["parentConstraint"]),
            
            # Face / Mouth
            ("mouth_C0_jaw_jnt", "CC_Base_JawRoot", ["parentConstraint"]),
            ("tongue_C0_1_jnt", "CC_Base_Tongue01", ["parentConstraint"]),
            ("tongue_C0_2_jnt", "CC_Base_Tongue02", ["parentConstraint"]),
            ("tongue_C0_3_jnt", "CC_Base_Tongue03", ["parentConstraint"]),
            ("mouth_C0_teethup_jnt", "CC_Base_Teeth01", ["parentConstraint"]),
            ("mouth_C0_teethlow_jnt", "CC_Base_Teeth02", ["parentConstraint"]),
            ("eye_L0_eye_jnt", "CC_Base_L_Eye", ["parentConstraint"]),
            ("eye_R0_eye_jnt", "CC_Base_R_Eye", ["parentConstraint"]),
            ("neck_C0_head_jnt", "CC_Base_FacialBone", ["parentConstraint"]),
            ("mouth_C0_jaw_jnt", "CC_Base_UpperJaw", ["parentConstraint"]),

            # Left Leg & Twist
            ("leg_L0_0_jnt", "CC_Base_L_Thigh", ["parentConstraint"]),
            ("leg_L0_1_jnt", "CC_Base_L_ThighTwist01", ["parentConstraint"]),
            ("leg_L0_1_jnt", "CC_Base_L_ThighTwist02", ["parentConstraint"]),
            ("leg_L0_3_jnt", "CC_Base_L_KneeShareBone", ["parentConstraint"]),
            ("leg_L0_4_jnt", "CC_Base_L_Calf", ["parentConstraint"]),
            ("leg_L0_5_jnt", "CC_Base_L_CalfTwist01", ["parentConstraint"]),
            ("leg_L0_5_jnt", "CC_Base_L_CalfTwist02", ["parentConstraint"]),
            ("leg_L0_end_jnt", "CC_Base_L_Foot", ["parentConstraint"]),
            
            # Left Toes
            ("foot_L0_0_jnt", "CC_Base_L_ToeBaseShareBone", ["orientConstraint"]),
            ("foot_L0_0_jnt", "CC_Base_L_ToeBase", ["orientConstraint"]),
            ("foot_L0_1_jnt", "CC_Base_L_BigToe1", ["orientConstraint"]),
            ("foot_L0_1_jnt", "CC_Base_L_IndexToe1", ["orientConstraint"]),
            ("foot_L0_1_jnt", "CC_Base_L_MidToe1", ["orientConstraint"]),
            ("foot_L0_1_jnt", "CC_Base_L_RingToe1", ["orientConstraint"]),
            ("foot_L0_1_jnt", "CC_Base_L_PinkyToe1", ["orientConstraint"]),

            # Right Leg & Twist
            ("leg_R0_0_jnt", "CC_Base_R_Thigh", ["parentConstraint"]),
            ("leg_R0_1_jnt", "CC_Base_R_ThighTwist01", ["parentConstraint"]),
            ("leg_R0_1_jnt", "CC_Base_R_ThighTwist02", ["parentConstraint"]),
            ("leg_R0_3_jnt", "CC_Base_R_KneeShareBone", ["parentConstraint"]),
            ("leg_R0_4_jnt", "CC_Base_R_Calf", ["parentConstraint"]),
            ("leg_R0_5_jnt", "CC_Base_R_CalfTwist01", ["parentConstraint"]),
            ("leg_R0_5_jnt", "CC_Base_R_CalfTwist02", ["parentConstraint"]),
            ("leg_R0_end_jnt", "CC_Base_R_Foot", ["parentConstraint"]),
            
            # Right Toes
            ("foot_R0_0_jnt", "CC_Base_R_ToeBaseShareBone", ["orientConstraint"]),
            ("foot_R0_0_jnt", "CC_Base_R_ToeBase", ["orientConstraint"]),
            ("foot_R0_1_jnt", "CC_Base_R_BigToe1", ["orientConstraint"]),
            ("foot_R0_1_jnt", "CC_Base_R_IndexToe1", ["orientConstraint"]),
            ("foot_R0_1_jnt", "CC_Base_R_MidToe1", ["orientConstraint"]),
            ("foot_R0_1_jnt", "CC_Base_R_RingToe1", ["orientConstraint"]),
            ("foot_R0_1_jnt", "CC_Base_R_PinkyToe1", ["orientConstraint"]),

            # Left Arm & Specialty Twist
            ("shoulder_L0_shoulder_jnt", "CC_Base_L_Clavicle", ["parentConstraint"]),
            ("arm_L0_0_jnt", "CC_Base_L_Upperarm", ["parentConstraint"]),
            ("arm_L0_1_jnt", "CC_Base_L_UpperarmTwist01", ["parentConstraint"]),
            ("arm_L0_1_jnt", "CC_Base_L_UpperarmTwist02", ["parentConstraint"]),
            ("arm_L0_3_jnt", "CC_Base_L_ElbowShareBone", ["parentConstraint"]),
            ("arm_L0_4_jnt", "CC_Base_L_Forearm", ["parentConstraint"]),
            ("arm_L0_5_jnt", "CC_Base_L_ForearmTwist01", ["parentConstraint"]),
            ("arm_L0_5_jnt", "CC_Base_L_ForearmTwist02", ["parentConstraint"]),
            ("arm_L0_end_jnt", "CC_Base_L_Hand", ["parentConstraint"]),
            ("spine_C0_4_jnt", "CC_Base_L_RibsTwist", ["parentConstraint"]),
            ("spine_C0_4_jnt", "CC_Base_L_Breast", ["parentConstraint"]),

            # Left Fingers
            ("thumb_L0_0_jnt", "CC_Base_L_Thumb1", ["orientConstraint"]),
            ("thumb_L0_1_jnt", "CC_Base_L_Thumb2", ["orientConstraint"]),
            ("thumb_L0_2_jnt", "CC_Base_L_Thumb3", ["orientConstraint"]),
            ("finger_L0_0_jnt", "CC_Base_L_Index1", ["orientConstraint"]),
            ("finger_L0_1_jnt", "CC_Base_L_Index2", ["orientConstraint"]),
            ("finger_L0_2_jnt", "CC_Base_L_Index3", ["orientConstraint"]),
            ("finger_L1_0_jnt", "CC_Base_L_Mid1", ["orientConstraint"]),
            ("finger_L1_1_jnt", "CC_Base_L_Mid2", ["orientConstraint"]),
            ("finger_L1_2_jnt", "CC_Base_L_Mid3", ["orientConstraint"]),
            ("finger_L2_0_jnt", "CC_Base_L_Ring1", ["orientConstraint"]),
            ("finger_L2_1_jnt", "CC_Base_L_Ring2", ["orientConstraint"]),
            ("finger_L2_2_jnt", "CC_Base_L_Ring3", ["orientConstraint"]),
            ("finger_L3_0_jnt", "CC_Base_L_Pinky1", ["orientConstraint"]),
            ("finger_L3_1_jnt", "CC_Base_L_Pinky2", ["orientConstraint"]),
            ("finger_L3_2_jnt", "CC_Base_L_Pinky3", ["orientConstraint"]),

            # Right Arm & Specialty Twist
            ("shoulder_R0_shoulder_jnt", "CC_Base_R_Clavicle", ["parentConstraint"]),
            ("arm_R0_0_jnt", "CC_Base_R_Upperarm", ["parentConstraint"]),
            ("arm_R0_1_jnt", "CC_Base_R_UpperarmTwist01", ["parentConstraint"]),
            ("arm_R0_1_jnt", "CC_Base_R_UpperarmTwist02", ["parentConstraint"]),
            ("arm_R0_3_jnt", "CC_Base_R_ElbowShareBone", ["parentConstraint"]),
            ("arm_R0_4_jnt", "CC_Base_R_Forearm", ["parentConstraint"]),
            ("arm_R0_5_jnt", "CC_Base_R_ForearmTwist01", ["parentConstraint"]),
            ("arm_R0_5_jnt", "CC_Base_R_ForearmTwist02", ["parentConstraint"]),
            ("arm_R0_end_jnt", "CC_Base_R_Hand", ["parentConstraint"]),
            ("spine_C0_4_jnt", "CC_Base_R_RibsTwist", ["parentConstraint"]),
            ("spine_C0_4_jnt", "CC_Base_R_Breast", ["parentConstraint"]),

            # Right Fingers
            ("thumb_R0_0_jnt", "CC_Base_R_Thumb1", ["orientConstraint"]),
            ("thumb_R0_1_jnt", "CC_Base_R_Thumb2", ["orientConstraint"]),
            ("thumb_R0_2_jnt", "CC_Base_R_Thumb3", ["orientConstraint"]),
            ("finger_R0_0_jnt", "CC_Base_R_Index1", ["orientConstraint"]),
            ("finger_R0_1_jnt", "CC_Base_R_Index2", ["orientConstraint"]),
            ("finger_R0_2_jnt", "CC_Base_R_Index3", ["orientConstraint"]),
            ("finger_R1_0_jnt", "CC_Base_R_Mid1", ["orientConstraint"]),
            ("finger_R1_1_jnt", "CC_Base_R_Mid2", ["orientConstraint"]),
            ("finger_R1_2_jnt", "CC_Base_R_Mid3", ["orientConstraint"]),
            ("finger_R2_0_jnt", "CC_Base_R_Ring1", ["orientConstraint"]),
            ("finger_R2_1_jnt", "CC_Base_R_Ring2", ["orientConstraint"]),
            ("finger_R2_2_jnt", "CC_Base_R_Ring3", ["orientConstraint"]),
            ("finger_R3_0_jnt", "CC_Base_R_Pinky1", ["orientConstraint"]),
            ("finger_R3_1_jnt", "CC_Base_R_Pinky2", ["orientConstraint"]),
            ("finger_R3_2_jnt", "CC_Base_R_Pinky3", ["orientConstraint"]),
        ]
        
        self.create_window()

    def find_strict_cc3_joint(self, target_name):
        """Strictly matches the exact joint name while safely tolerating namespaces."""
        # By filtering with a selective list loop, we prevent matching strings with B_ prefixes.
        found_nodes = cmds.ls(f"*{target_name}", type="joint")
        for node in found_nodes:
            # Extract just the base short name, stripping out any namespace colon dividers
            short_name = node.split(":")[-1]
            if short_name == target_name:
                return node
        return None

    def create_window(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        self.window = cmds.window(self.window_name, title="CC3 Strict Joint Matcher", widthHeight=(460, 480), sizeable=True)
        
        main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=["both", 10])
        
        cmds.separator(height=5, style="none")
        cmds.text(label="CC3 (Strict No-Prefix) to mGear Pipeline", font="boldLabelFont", align="center")
        cmds.separator(height=2, style="single")

        # Options Layout
        cmds.rowLayout(numberOfColumns=1, adjustableColumn=1)
        self.exclude_facial_cb = cmds.checkBox(
            label="Exclude Facial Joints (Eyes, Jaw, Tongue, Teeth)", 
            value=True,
            changeCommand=self.run_validation
        )
        cmds.setParent(main_layout)

        # Status Display Area
        self.status_text = cmds.text(label="Status: Click 'Check Scene' to validate elements.", font="obliqueLabelFont", align="left")
        
        # Missing Items List
        cmds.text(label="Missing Target Hierarchy Nodes (No B_ Allowed):", align="left", font="boldLabelFont")
        self.error_log = cmds.textScrollList(height=180, allowMultiSelection=False)

        # Action Buttons Layout
        cmds.separator(height=5, style="single")
        self.check_btn = cmds.button(label="🔎 Check Scene / Refresh Hierarchy", command=self.run_validation, height=35, backgroundColor=[0.25, 0.35, 0.45])
        
        self.constraint_btn = cmds.button(
            label="🔗 Reconstruct Constraints", 
            command=self.execute_constraints, 
            height=40, 
            backgroundColor=[0.3, 0.6, 0.3],
            manage=False 
        )
        
        cmds.separator(height=5, style="none")
        cmds.showWindow(self.window)
        
        self.run_validation()

    def run_validation(self, *args):
        """Strict validation sweep ensuring target components do not use prefixes."""
        cmds.textScrollList(self.error_log, edit=True, removeAll=True)
        exclude_facial = cmds.checkBox(self.exclude_facial_cb, query=True, value=True)
        
        missing_nodes = []
        
        for mgear_name, cc3_name, _ in self.exact_mapping:
            if exclude_facial and cc3_name in self.facial_joints_to_skip:
                continue

            mgear_found = cmds.ls("*" + mgear_name, type=["joint", "transform"])
            cc3_found = self.find_strict_cc3_joint(cc3_name)
            
            if not mgear_found:
                missing_nodes.append(f"Missing mGear Driver Component: '{mgear_name}'")
            if not cc3_found:
                missing_nodes.append(f"Missing Strict CC3 Driven Joint: '{cc3_name}'")

        missing_nodes = list(sorted(set(missing_nodes)))

        if missing_nodes:
            for node_error in missing_nodes:
                cmds.textScrollList(self.error_log, edit=True, append=node_error)
            
            cmds.text(self.status_text, edit=True, label=f"❌ Error: {len(missing_nodes)} elements missing. Clean joints required.", backgroundColor=[0.4, 0.1, 0.1])
            cmds.button(self.constraint_btn, edit=True, manage=False) 
        else:
            cmds.textScrollList(self.error_log, edit=True, append="✨ Strict target matching validated! Ready to bind.")
            cmds.text(self.status_text, edit=True, label="✅ System Validated: Ready to construct constraints safely.", backgroundColor=[0.1, 0.35, 0.1])
            cmds.button(self.constraint_btn, edit=True, manage=True) 

    def execute_constraints(self, *args):
        """Constructs constraints between driver/driven pairs."""
        exclude_facial = cmds.checkBox(self.exclude_facial_cb, query=True, value=True)
        success_count = 0
        
        for mgear_name, cc3_name, constraint_types in self.exact_mapping:
            if exclude_facial and cc3_name in self.facial_joints_to_skip:
                continue

            source_list = cmds.ls("*" + mgear_name, type=["joint", "transform"])
            target = self.find_strict_cc3_joint(cc3_name)
            
            if source_list and target:
                source = source_list[0]
                try:
                    if "parentConstraint" in constraint_types:
                        cmds.parentConstraint(source, target, maintainOffset=True, weight=1)
                    if "orientConstraint" in constraint_types:
                        cmds.orientConstraint(source, target, maintainOffset=True, weight=1)
                    if "scaleConstraint" in constraint_types:
                        cmds.scaleConstraint(source, target, maintainOffset=True, weight=1)
                    success_count += 1
                except Exception as e:
                    cmds.warning(f"Error binding pairing {target} to {source}: {e}")
                
        cmds.confirmDialog(title="Complete", message=f"Successfully built strict constraint setups across {success_count} components.", button=["OK"])
        self.run_validation() 

# Initialize UI Instance
CC3ToMGearStrictUI()