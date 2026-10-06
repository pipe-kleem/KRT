import maya.cmds as cmds

def reconstruct_cc3_constraints(exclude_facial_joints=True):
    """
    Reconstructs the CC3 to mGear connection based on the provided exact mapping.
    
    Args:
        exclude_facial_joints (bool): If True, skips constraining eyes, jaw, tongue, and teeth.
    """
    
    # List of specific CC3 facial joints to ignore
    facial_joints_to_skip = [
        "CC_Base_JawRoot", 
        "CC_Base_FacialBone", 
        "CC_Base_Teeth02", 
        "CC_Base_Tongue02", 
        "CC_Base_Teeth01", 
        "CC_Base_Tongue01", 
        "CC_Base_UpperJaw", 
        "CC_Base_L_Eye", 
        "CC_Base_Tongue03", 
        "CC_Base_R_Eye"
    ]

    # Format: ("mGear_Driver", "CC3_Driven", ["constraintTypes"])
    exact_mapping = [
        # Root & Pelvis
        ("local_C0_ctl", "CC_Base_BoneRoot", ["parentConstraint", "scaleConstraint"]),
        ("spine_C0_0_jnt", "CC_Base_Hip", ["parentConstraint"]),
        
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

        # Left Leg
        ("leg_L0_0_jnt", "CC_Base_L_Thigh", ["parentConstraint"]),
        ("leg_L0_1_jnt", "CC_Base_L_ThighTwist02", ["parentConstraint"]),
        ("leg_L0_3_jnt", "CC_Base_L_KneeShareBone", ["parentConstraint"]),
        ("leg_L0_4_jnt", "CC_Base_L_Calf", ["parentConstraint"]),
        ("leg_L0_5_jnt", "CC_Base_L_CalfTwist02", ["parentConstraint"]),
        ("leg_L0_end_jnt", "CC_Base_L_Foot", ["parentConstraint"]),
        
        # Left Toes
        ("foot_L0_0_jnt", "CC_Base_L_ToeBase", ["orientConstraint"]),
        ("foot_L0_1_jnt", "CC_Base_L_BigToe1", ["orientConstraint"]),
        ("foot_L0_1_jnt", "CC_Base_L_IndexToe1", ["orientConstraint"]),
        ("foot_L0_1_jnt", "CC_Base_L_MidToe1", ["orientConstraint"]),
        ("foot_L0_1_jnt", "CC_Base_L_RingToe1", ["orientConstraint"]),
        ("foot_L0_1_jnt", "CC_Base_L_PinkyToe1", ["orientConstraint"]),

        # Right Leg
        ("leg_R0_0_jnt", "CC_Base_R_Thigh", ["parentConstraint"]),
        ("leg_R0_1_jnt", "CC_Base_R_ThighTwist02", ["parentConstraint"]),
        ("leg_R0_3_jnt", "CC_Base_R_KneeShareBone", ["parentConstraint"]),
        ("leg_R0_4_jnt", "CC_Base_R_Calf", ["parentConstraint"]),
        ("leg_R0_5_jnt", "CC_Base_R_CalfTwist02", ["parentConstraint"]),
        ("leg_R0_end_jnt", "CC_Base_R_Foot", ["parentConstraint"]),
        
        # Right Toes
        ("foot_R0_0_jnt", "CC_Base_R_ToeBase", ["orientConstraint"]),
        ("foot_R0_1_jnt", "CC_Base_R_BigToe1", ["orientConstraint"]),
        ("foot_R0_1_jnt", "CC_Base_R_IndexToe1", ["orientConstraint"]),
        ("foot_R0_1_jnt", "CC_Base_R_MidToe1", ["orientConstraint"]),
        ("foot_R0_1_jnt", "CC_Base_R_RingToe1", ["orientConstraint"]),
        ("foot_R0_1_jnt", "CC_Base_R_PinkyToe1", ["orientConstraint"]),

        # Left Arm
        ("shoulder_L0_shoulder_jnt", "CC_Base_L_Clavicle", ["parentConstraint"]),
        ("arm_L0_0_jnt", "CC_Base_L_Upperarm", ["parentConstraint"]),
        ("arm_L0_1_jnt", "CC_Base_L_UpperarmTwist02", ["parentConstraint"]),
        ("arm_L0_3_jnt", "CC_Base_L_ElbowShareBone", ["parentConstraint"]),
        ("arm_L0_4_jnt", "CC_Base_L_Forearm", ["parentConstraint"]),
        ("arm_L0_5_jnt", "CC_Base_L_ForearmTwist02", ["parentConstraint"]),
        ("arm_L0_end_jnt", "CC_Base_L_Hand", ["parentConstraint"]),

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

        # Right Arm
        ("shoulder_R0_shoulder_jnt", "CC_Base_R_Clavicle", ["parentConstraint"]),
        ("arm_R0_0_jnt", "CC_Base_R_Upperarm", ["parentConstraint"]),
        ("arm_R0_1_jnt", "CC_Base_R_UpperarmTwist02", ["parentConstraint"]),
        ("arm_R0_3_jnt", "CC_Base_R_ElbowShareBone", ["parentConstraint"]),
        ("arm_R0_4_jnt", "CC_Base_R_Forearm", ["parentConstraint"]),
        ("arm_R0_5_jnt", "CC_Base_R_ForearmTwist02", ["parentConstraint"]),
        ("arm_R0_end_jnt", "CC_Base_R_Hand", ["parentConstraint"]),

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

    success_count = 0
    fail_list = []
    skipped_list = []

    for mgear_name, cc3_name, constraint_types in exact_mapping:
        
        # Check if we should skip this joint
        if exclude_facial_joints and cc3_name in facial_joints_to_skip:
            skipped_list.append(cc3_name)
            continue

        mgear_search = cmds.ls("*" + mgear_name, type=["joint", "transform"])
        cc3_search = cmds.ls("*" + cc3_name, type="joint")

        if mgear_search and cc3_search:
            source = mgear_search[0] 
            target = cc3_search[0]
            
            try:
                if "parentConstraint" in constraint_types:
                    cmds.parentConstraint(source, target, maintainOffset=True, weight=1)
                
                if "orientConstraint" in constraint_types:
                    cmds.orientConstraint(source, target, maintainOffset=True, weight=1)
                    
                if "scaleConstraint" in constraint_types:
                    cmds.scaleConstraint(source, target, maintainOffset=True, weight=1)
                
                success_count += 1
            except Exception as e:
                cmds.warning(f"Could not constrain {target} to {source}: {e}")
        else:
            if not mgear_search:
                fail_list.append(mgear_name)
            if not cc3_search:
                fail_list.append(cc3_name)

    print("\n--- Exact Constraint Reconstruction Complete ---")
    print(f"Successfully constrained {success_count} joint pairs.")
    
    if skipped_list:
        print(f"Skipped {len(skipped_list)} facial joints due to exclusion settings.")
    
    if fail_list:
        print("Note: The following objects were listed in your mapping but weren't found in the current scene:")
        print(list(set(fail_list)))

# Run the function, keeping facial joints EXCLUDED
reconstruct_cc3_constraints(exclude_facial_joints=True)

# If you ever decide you DO want to constrain the face, simply change it to False like this:
# reconstruct_cc3_constraints(exclude_facial_joints=False)