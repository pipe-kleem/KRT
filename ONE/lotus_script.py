import maya.cmds as cmds

def create_bend_guide(source_petal):
    """Creates a bend deformer on the source petal to act as a setup guide."""
    if not cmds.objExists(source_petal):
        cmds.warning(f"Source geometry '{source_petal}' not found.")
        return
        
    guide_handle = "Lotus_Bend_Guide_Handle"
    guide_node = "Lotus_Bend_Guide_Node"
    
    if cmds.objExists(guide_handle):
        cmds.warning("Bend guide already exists. Please adjust the existing handle.")
        cmds.select(guide_handle)
        return

    bend_node, bend_handle = cmds.nonLinear(source_petal, type='bend')
    bend_node = cmds.rename(bend_node, guide_node)
    bend_handle = cmds.rename(bend_handle, guide_handle)
    
    cmds.setAttr(f"{bend_handle}.translateX", 0)
    cmds.setAttr(f"{bend_handle}.translateY", 0)
    cmds.setAttr(f"{bend_handle}.translateZ", 0)
    cmds.setAttr(f"{bend_handle}.rotateX", -114.233)
    cmds.setAttr(f"{bend_handle}.rotateY", 74.353)
    cmds.setAttr(f"{bend_handle}.rotateZ", -296.873)
    cmds.setAttr(f"{bend_handle}.scaleX", 0.039)
    cmds.setAttr(f"{bend_handle}.scaleY", 0.039)
    cmds.setAttr(f"{bend_handle}.scaleZ", 0.039)
    
    cmds.setAttr(f"{bend_node}.envelope", 1)
    cmds.setAttr(f"{bend_node}.curvature", 24)
    cmds.setAttr(f"{bend_node}.lowBound", -2.5)
    cmds.setAttr(f"{bend_node}.highBound", 0)
    
    cmds.select(bend_handle)
    print("Created Bend Guide with default values. Tweak if necessary, then Build.")


def build_lotus_rig(source_petal, num_petals=5, num_rows=1, bloom_axis='Y', twist_axis='Z', spread_axis='Y', spacing_axis='Z', ctrl_size=0.03, row_spacing_y=0.021, row_scale_step=0.15):
    """Core rigging logic for the Lotus Tool."""
    if not cmds.objExists(source_petal):
        cmds.warning(f"Source geometry '{source_petal}' not found.")
        return

    bloom_axis = bloom_axis.upper()
    twist_axis = twist_axis.upper()
    spread_axis = spread_axis.upper()
    spacing_axis = spacing_axis.upper()

    has_bend = cmds.objExists("Lotus_Bend_Guide_Handle")
    guide_node = "Lotus_Bend_Guide_Node"
    guide_handle = "Lotus_Bend_Guide_Handle"
    
    orig_curvature = 0
    if has_bend:
        orig_curvature = cmds.getAttr(f"{guide_node}.curvature")
        cmds.setAttr(f"{guide_node}.curvature", 0)

    # 1. Master Hierarchy
    rig_top_grp = cmds.group(empty=True, name="Lotus_Rig_Grp")
    petals_global_grp = cmds.group(empty=True, name="Lotus_petals_Grp")
    
    others_grp = cmds.group(empty=True, name="Lotus_Others_Grp")
    cmds.hide(others_grp) 
    
    cmds.parent(petals_global_grp, rig_top_grp)
    cmds.parent(others_grp, rig_top_grp)
    
    main_ctrl = cmds.circle(name="Lotus_Main_Ctrl", normal=(0, 1, 0), radius=5.0 * ctrl_size)[0]
    cmds.parent(main_ctrl, rig_top_grp)
    
    cmds.addAttr(main_ctrl, longName='globalScale', attributeType='float', min=0.001, defaultValue=1.0, keyable=True)
    cmds.addAttr(main_ctrl, longName='openAllRows', attributeType='float', defaultValue=10, keyable=True)
    cmds.addAttr(main_ctrl, longName='bloomAngleMax', attributeType='float', defaultValue=90, keyable=True) 
    cmds.addAttr(main_ctrl, longName='twistAmplitude', attributeType='float', defaultValue=10, keyable=True)
    
    cmds.addAttr(main_ctrl, longName='rotatePetalsX', attributeType='float', defaultValue=0, keyable=True)
    cmds.addAttr(main_ctrl, longName='rotatePetalsY', attributeType='float', defaultValue=-85, keyable=True)
    cmds.addAttr(main_ctrl, longName='rotatePetalsZ', attributeType='float', defaultValue=0, keyable=True)

    cmds.connectAttr(f'{main_ctrl}.globalScale', f'{main_ctrl}.scaleX')
    cmds.connectAttr(f'{main_ctrl}.globalScale', f'{main_ctrl}.scaleY')
    cmds.connectAttr(f'{main_ctrl}.globalScale', f'{main_ctrl}.scaleZ')

    for attr in ['sx', 'sy', 'sz', 'v']:
        cmds.setAttr(f"{main_ctrl}.{attr}", lock=True, keyable=False, channelBox=False)

    normalize_math = cmds.createNode('multiplyDivide', name='Lotus_Normalize_Math')
    cmds.setAttr(f'{normalize_math}.operation', 2)
    cmds.connectAttr(f'{main_ctrl}.bloomAngleMax', f'{normalize_math}.input1X')
    cmds.setAttr(f'{normalize_math}.input2X', 10.0)

    row_colors = [13, 14, 15, 17, 18, 20, 22] 
    angle_step = 360.0 / num_petals

    for r in range(num_rows):
        row_idx = str(r + 1).zfill(2)
        
        # Build at exact zero to avoid constraint snapping issues
        row_ctrl, make_circle = cmds.circle(name=f"Lotus_Row_{row_idx}_Ctrl", normal=(0, 1, 0), radius=3.5 * ctrl_size, ch=True)
        cmds.parent(row_ctrl, main_ctrl)
        
        color_index = row_colors[r % len(row_colors)]
        cmds.setAttr(f"{row_ctrl}.overrideEnabled", 1)
        cmds.setAttr(f"{row_ctrl}.overrideColor", color_index)
        
        for attr in ['tx', 'tz', 'rx', 'rz', 'sx', 'sy', 'sz', 'v']:
            cmds.setAttr(f"{row_ctrl}.{attr}", lock=True, keyable=False, channelBox=False)
        
        cmds.addAttr(row_ctrl, longName='openRow', attributeType='float', min=0, max=10, defaultValue=0, keyable=True)
        cmds.addAttr(row_ctrl, longName='scalePetals', attributeType='float', min=0.01, defaultValue=1.0, keyable=True)
        cmds.addAttr(row_ctrl, longName='spacing', attributeType='float', min=0, defaultValue=0, keyable=True)
        
        if has_bend:
            cmds.addAttr(row_ctrl, longName='bendCurvature', attributeType='float', defaultValue=orig_curvature, keyable=True)
            cmds.setAttr(f"{row_ctrl}.bendCurvature", orig_curvature)
            
        ctrl_scale_math = cmds.createNode('multiplyDivide', name=f'Lotus_Ctrl_Scale_Math_R{row_idx}')
        cmds.connectAttr(f'{row_ctrl}.scalePetals', f'{ctrl_scale_math}.input1X')
        cmds.setAttr(f'{ctrl_scale_math}.input2X', 3.5 * ctrl_size)
        cmds.connectAttr(f'{ctrl_scale_math}.outputX', f'{make_circle}.radius')
            
        open_sum_math = cmds.createNode('plusMinusAverage', name=f'Lotus_Open_Sum_R{row_idx}')
        cmds.connectAttr(f'{main_ctrl}.openAllRows', f'{open_sum_math}.input1D[0]')
        cmds.connectAttr(f'{row_ctrl}.openRow', f'{open_sum_math}.input1D[1]')
        
        bloom_math = cmds.createNode('multiplyDivide', name=f'Lotus_Bloom_Math_R{row_idx}')
        cmds.connectAttr(f'{open_sum_math}.output1D', f'{bloom_math}.input1X')
        cmds.connectAttr(f'{normalize_math}.outputX', f'{bloom_math}.input2X')

        twist_math = cmds.createNode('multiplyDivide', name=f'Lotus_Twist_Math_R{row_idx}')
        cmds.connectAttr(f'{open_sum_math}.output1D', f'{twist_math}.input1X')
        cmds.connectAttr(f'{main_ctrl}.twistAmplitude', f'{twist_math}.input2X')
        
        spacing_math = cmds.createNode('multiplyDivide', name=f'Lotus_Spacing_Math_R{row_idx}')
        cmds.connectAttr(f'{row_ctrl}.spacing', f'{spacing_math}.input1X')
        cmds.setAttr(f'{spacing_math}.input2X', 0.1) 

        row_grp = cmds.group(empty=True, name=f"Lotus_Row_{row_idx}_Grp")
        cmds.parent(row_grp, petals_global_grp)
        
        row_offset_angle = (angle_step / 2.0) if r % 2 != 0 else 0.0

        # --- STEP 1: Parent geometry to 1,1,1 scale group to avoid scale compensation ---
        for i in range(num_petals):
            petal_idx = str(i + 1).zfill(2)
            full_idx = f"R{row_idx}_{petal_idx}"
            
            # UPDATED: Lowercase 'p' for petal nodes
            new_petal = cmds.duplicate(source_petal, name=f"petal_geo_{full_idx}")[0]
            
            radial_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Radial_Grp")
            spacing_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Spacing_Grp")
            bloom_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Bloom_Grp")
            twist_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Twist_Grp")
            rotate_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Rotate_Grp")
            scale_grp = cmds.group(empty=True, name=f"petal_{full_idx}_Scale_Grp")
            
            cmds.parent(new_petal, scale_grp)
            cmds.parent(scale_grp, rotate_grp)
            cmds.parent(rotate_grp, twist_grp)
            cmds.parent(twist_grp, bloom_grp)
            cmds.parent(bloom_grp, spacing_grp)
            cmds.parent(spacing_grp, radial_grp)
            cmds.parent(radial_grp, row_grp) 
            
            if has_bend:
                new_bend_node, new_bend_handle = cmds.nonLinear(new_petal, type='bend')
                new_bend_node = cmds.rename(new_bend_node, f"petal_{full_idx}_Bend_Node")
                new_bend_handle = cmds.rename(new_bend_handle, f"petal_{full_idx}_Bend_Handle")
                
                cmds.delete(cmds.parentConstraint(guide_handle, new_bend_handle))
                cmds.delete(cmds.scaleConstraint(guide_handle, new_bend_handle))
                
                cmds.setAttr(f"{new_bend_node}.lowBound", cmds.getAttr(f"{guide_node}.lowBound"))
                cmds.setAttr(f"{new_bend_node}.highBound", cmds.getAttr(f"{guide_node}.highBound"))
                cmds.setAttr(f"{new_bend_node}.envelope", cmds.getAttr(f"{guide_node}.envelope"))
                
                cmds.parent(new_bend_handle, others_grp)
                cmds.parentConstraint(scale_grp, new_bend_handle, maintainOffset=True)
                cmds.scaleConstraint(scale_grp, new_bend_handle, maintainOffset=True)
                
                cmds.connectAttr(f"{row_ctrl}.bendCurvature", f"{new_bend_node}.curvature")
            
            cmds.connectAttr(f"{row_ctrl}.scalePetals", f"{scale_grp}.scaleX")
            cmds.connectAttr(f"{row_ctrl}.scalePetals", f"{scale_grp}.scaleY")
            cmds.connectAttr(f"{row_ctrl}.scalePetals", f"{scale_grp}.scaleZ")
            
            cmds.connectAttr(f"{main_ctrl}.rotatePetalsX", f"{rotate_grp}.rotateX")
            cmds.connectAttr(f"{main_ctrl}.rotatePetalsY", f"{rotate_grp}.rotateY")
            cmds.connectAttr(f"{main_ctrl}.rotatePetalsZ", f"{rotate_grp}.rotateZ")
            
            cmds.connectAttr(f"{spacing_math}.outputX", f"{spacing_grp}.translate{spacing_axis}")
            
            final_spread_angle = (angle_step * i) + row_offset_angle
            cmds.setAttr(f"{radial_grp}.rotate{spread_axis}", final_spread_angle)
            
            cmds.connectAttr(f"{bloom_math}.outputX", f"{bloom_grp}.rotate{bloom_axis}")
            cmds.connectAttr(f"{twist_math}.outputX", f"{twist_grp}.rotate{twist_axis}")

        # --- STEP 2: Scale the group globally without breaking child scales ---
        scale_factor = max(0.01, 1.0 - (r * row_scale_step)) 
        cmds.setAttr(f"{row_grp}.scaleX", scale_factor)
        cmds.setAttr(f"{row_grp}.scaleY", scale_factor)
        cmds.setAttr(f"{row_grp}.scaleZ", scale_factor)

        # --- STEP 3: Constrain row group to control (bakes current neutral position) ---
        cmds.parentConstraint(row_ctrl, row_grp, maintainOffset=True)
        cmds.scaleConstraint(row_ctrl, row_grp, maintainOffset=True)

        # --- STEP 4: Spacing translation applied to control drags geometry automatically ---
        y_offset = (num_rows - 1 - r) * row_spacing_y
        cmds.setAttr(f"{row_ctrl}.translateY", y_offset) 

    if has_bend:
        cmds.delete(guide_handle)
    
    cmds.hide(source_petal)
    cmds.select(main_ctrl)
    print(f"Success: Built Final Lotus Rig. Nodes named using lowercase 'petal'.")


class LotusRigUI(object):
    def __init__(self):
        self.window_name = "LotusRigGeneratorUI"
        self.title = "Lotus Rigger Pro v16.3"
        self.size = (440, 630) 
        
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name, window=True)
            
        self.build_ui()
        
    def build_ui(self):
        self.window = cmds.window(self.window_name, title=self.title, widthHeight=self.size, sizeable=False)
        self.main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        label_w = 150 
        field_w = 50
        slider_w = 200

        cmds.frameLayout(label="1. Geometry Setup", collapsable=False, marginWidth=15, marginHeight=10, borderVisible=True)
        
        self.mesh_field = cmds.textFieldButtonGrp(
            label='Source petal: ', text='', buttonLabel=' <<< Load Selected ', 
            buttonCommand=self.load_mesh, 
            columnWidth3=(90, 190, 100), adjustableColumn=2
        )
        cmds.separator(height=10, style='none')
        cmds.button(label="Create Bend Guide", command=self.trigger_bend_guide, height=35, backgroundColor=(0.25, 0.35, 0.45))
        cmds.text(label="Position the handle. Autodeletes after build.", align="center", font="smallPlainLabelFont")
        
        cmds.setParent('..')

        cmds.frameLayout(label="2. Rig Parameters", collapsable=False, marginWidth=15, marginHeight=10, borderVisible=True)
        
        self.num_rows_ctrl = cmds.intSliderGrp(label='Number of Rows:', field=True, minValue=1, maxValue=10, value=3, 
                                               columnWidth3=(label_w, field_w, slider_w))
        self.num_petals_ctrl = cmds.intSliderGrp(label='petals per Row:', field=True, minValue=3, maxValue=36, value=5, 
                                                 columnWidth3=(label_w, field_w, slider_w))
        self.ctrl_size_ctrl = cmds.floatSliderGrp(label='Control Size:', field=True, minValue=0.01, maxValue=5.0, value=0.03, step=0.01, 
                                                  columnWidth3=(label_w, field_w, slider_w))
        self.row_spacing_ctrl = cmds.floatSliderGrp(label='Row Vertical Spacing:', field=True, minValue=0.0, maxValue=2.0, value=0.021, step=0.001, 
                                                    columnWidth3=(label_w, field_w, slider_w))
        
        self.row_scale_ctrl = cmds.floatSliderGrp(label='Row Scale Dropoff:', field=True, minValue=0.0, maxValue=1.0, value=0.15, step=0.01, 
                                                  columnWidth3=(label_w, field_w, slider_w))
        
        cmds.setParent('..')

        cmds.frameLayout(label="3. Axes Configuration", collapsable=False, marginWidth=15, marginHeight=10, borderVisible=True)
        
        self.bloom_axis_ctrl = cmds.optionMenuGrp(label='Bloom Axis:', columnWidth2=(label_w, 100))
        cmds.menuItem(label='X'); cmds.menuItem(label='Y'); cmds.menuItem(label='Z')
        cmds.optionMenuGrp(self.bloom_axis_ctrl, edit=True, value='Y') 
        
        self.twist_axis_ctrl = cmds.optionMenuGrp(label='Twist Axis:', columnWidth2=(label_w, 100))
        cmds.menuItem(label='X'); cmds.menuItem(label='Y'); cmds.menuItem(label='Z')
        cmds.optionMenuGrp(self.twist_axis_ctrl, edit=True, value='Z') 
        
        self.spread_axis_ctrl = cmds.optionMenuGrp(label='Spread Axis (Radial):', columnWidth2=(label_w, 100))
        cmds.menuItem(label='X'); cmds.menuItem(label='Y'); cmds.menuItem(label='Z')
        cmds.optionMenuGrp(self.spread_axis_ctrl, edit=True, value='Y')
        
        self.spacing_axis_ctrl = cmds.optionMenuGrp(label='Spacing Axis (Outward):', columnWidth2=(label_w, 100))
        cmds.menuItem(label='X'); cmds.menuItem(label='Y'); cmds.menuItem(label='Z')
        cmds.optionMenuGrp(self.spacing_axis_ctrl, edit=True, value='Z')
        
        cmds.setParent('..')

        cmds.separator(height=10, style='none')
        cmds.button(label="BUILD LOTUS RIG", command=self.execute_build, height=50, backgroundColor=(0.3, 0.6, 0.4))
        
        cmds.showWindow(self.window)
        
    def load_mesh(self, *args):
        selection = cmds.ls(selection=True, transforms=True)
        if selection:
            cmds.textFieldButtonGrp(self.mesh_field, edit=True, text=selection[0])
        else:
            cmds.warning("Please select a geometry object in the viewport to load.")
            
    def trigger_bend_guide(self, *args):
        source_petal = cmds.textFieldButtonGrp(self.mesh_field, query=True, text=True)
        if not source_petal or not cmds.objExists(source_petal):
            cmds.warning("Load a valid source petal first.")
            return
        create_bend_guide(source_petal)
            
    def execute_build(self, *args):
        source_petal = cmds.textFieldButtonGrp(self.mesh_field, query=True, text=True)
        if not source_petal or not cmds.objExists(source_petal):
            cmds.warning("Valid source petal not found. Please load a mesh first.")
            return
            
        num_rows = cmds.intSliderGrp(self.num_rows_ctrl, query=True, value=True)
        num_petals = cmds.intSliderGrp(self.num_petals_ctrl, query=True, value=True)
        ctrl_size = cmds.floatSliderGrp(self.ctrl_size_ctrl, query=True, value=True)
        row_spacing_y = cmds.floatSliderGrp(self.row_spacing_ctrl, query=True, value=True)
        row_scale_step = cmds.floatSliderGrp(self.row_scale_ctrl, query=True, value=True)
        
        bloom_axis = cmds.optionMenuGrp(self.bloom_axis_ctrl, query=True, value=True)
        twist_axis = cmds.optionMenuGrp(self.twist_axis_ctrl, query=True, value=True)
        spread_axis = cmds.optionMenuGrp(self.spread_axis_ctrl, query=True, value=True)
        spacing_axis = cmds.optionMenuGrp(self.spacing_axis_ctrl, query=True, value=True)
        
        build_lotus_rig(source_petal, num_petals, num_rows, bloom_axis, twist_axis, spread_axis, spacing_axis, ctrl_size, row_spacing_y, row_scale_step)

LotusRigUI()