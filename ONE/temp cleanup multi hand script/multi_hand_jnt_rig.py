import maya.cmds as cmds
import maya.api.OpenMaya as om
import PySide6.QtWidgets as QtWidgets
import PySide6.QtCore as QtCore
import math

class EphemeralRigTool(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ephemeral Rig Manager v3")
        self.setFixedSize(320, 420)
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        self.rig_root_name = "EPHEMERAL_RIG_META_GRP"
        self.create_ui()
        
    def create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        gen_group = QtWidgets.QGroupBox("Skeletal Generation (Arm + Fingers)")
        gen_layout = QtWidgets.QFormLayout(gen_group)
        self.rows_input, self.cols_input = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        self.rows_input.setValue(2); self.cols_input.setValue(3)
        self.spacing_input = QtWidgets.QDoubleSpinBox()
        self.spacing_input.setValue(30.0)
        
        gen_layout.addRow("Rows:", self.rows_input)
        gen_layout.addRow("Columns:", self.cols_input)
        gen_layout.addRow("Spacing:", self.spacing_input)
        
        btn_gen = QtWidgets.QPushButton("Generate Arm/Hand Grid")
        btn_gen.clicked.connect(self.generate_joint_grid)
        gen_layout.addRow(btn_gen)
        layout.addWidget(gen_group)
        
        rig_group = QtWidgets.QGroupBox("Dynamic Rigging & Extraction")
        rig_layout = QtWidgets.QVBoxLayout(rig_group)
        
        btn_build = QtWidgets.QPushButton("Attach Rig & Extract Anim")
        btn_build.setStyleSheet("background-color: #2b5c2b; font-weight: bold; padding: 10px;")
        btn_build.clicked.connect(self.attach_rig)
        
        btn_bake = QtWidgets.QPushButton("Bake Anim & Detach Rig")
        btn_bake.setStyleSheet("background-color: #5c2b2b; font-weight: bold; padding: 10px;")
        btn_bake.clicked.connect(self.bake_and_detach)
        
        rig_layout.addWidget(btn_build)
        rig_layout.addWidget(btn_bake)
        layout.addWidget(rig_group)
        layout.addStretch()

    def set_color(self, ctrl, color_index):
        shapes = cmds.listRelatives(ctrl, shapes=True) or []
        for shape in shapes:
            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            cmds.setAttr(f"{shape}.overrideColor", color_index)

    def get_distance(self, j1, j2):
        p1 = cmds.xform(j1, q=True, ws=True, t=True)
        p2 = cmds.xform(j2, q=True, ws=True, t=True)
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

    def calculate_pole_vector(self, shoulder, elbow, wrist, distance=10):
        p1 = om.MVector(cmds.xform(shoulder, q=True, ws=True, t=True))
        p2 = om.MVector(cmds.xform(elbow, q=True, ws=True, t=True))
        p3 = om.MVector(cmds.xform(wrist, q=True, ws=True, t=True))
        
        arm_len = (p2 - p1).length() + (p3 - p2).length()
        proj_vector = p3 - p1
        proj_vector.normalize()
        
        mid_point = p1 + (proj_vector * ((p2 - p1).length() / arm_len) * proj_vector.length())
        pv_dir = p2 - mid_point
        pv_dir.normalize()
        return p2 + (pv_dir * distance)

    def generate_joint_grid(self):
        cmds.select(cl=True)
        grid_grp = cmds.group(em=True, name="Skeletal_Grid_Root")
        r, c, s = self.rows_input.value(), self.cols_input.value(), self.spacing_input.value()
        
        for i in range(r):
            for j in range(c):
                cmds.select(cl=True)
                shldr = cmds.joint(name=f"arm_{i}_{j}_shldr_JNT", p=(j*s, 15, i*s))
                elbow = cmds.joint(name=f"arm_{i}_{j}_elbw_JNT", p=(j*s + 10, 15, i*s - 2))
                wrist = cmds.joint(name=f"arm_{i}_{j}_wrst_JNT", p=(j*s + 20, 15, i*s))
                for f in range(3):
                    cmds.select(wrist)
                    cmds.joint(name=f"arm_{i}_{j}_f{f}_01_JNT", p=(j*s + 23, 15, i*s + (f*2 - 2)))
                    cmds.joint(name=f"arm_{i}_{j}_f{f}_02_JNT", p=(j*s + 26, 15, i*s + (f*2 - 2)))
                cmds.parent(shldr, grid_grp)
        cmds.select(cl=True)

    def attach_rig(self):
        sel = cmds.ls(sl=True, type="joint")
        if not sel: return cmds.warning("Select the shoulder/root joint.")
        if cmds.objExists(self.rig_root_name): return cmds.warning("Active rig exists. Bake first.")
        
        shldr_jnt = sel[0]
        children = cmds.listRelatives(shldr_jnt, ad=True, type="joint") or []
        children.reverse()
        if len(children) < 2: return cmds.warning("Hierarchy too short for IK arm.")
        
        elbw_jnt, wrst_jnt = children[0], children[1]
        fingers = children[2:]
        all_jnts = [shldr_jnt, elbw_jnt, wrst_jnt] + fingers
        arm_scale = self.get_distance(shldr_jnt, elbw_jnt) * 0.3
        
        # Build Rig Root
        rig_root = cmds.group(em=True, name=self.rig_root_name)
        cmds.addAttr(rig_root, ln="targetJnt", at="message")
        cmds.connectAttr(f"{shldr_jnt}.message", f"{rig_root}.targetJnt")
        
        # 1. BUILD SHOULDER FK
        shldr_ctrl = cmds.circle(nr=(1,0,0), r=arm_scale*1.2, name="shoulder_CTRL")[0]
        self.set_color(shldr_ctrl, 13) # Red
        shldr_grp = cmds.group(shldr_ctrl, name="shoulder_GRP")
        cmds.matchTransform(shldr_grp, shldr_jnt, pos=True, rot=True)
        cmds.parent(shldr_grp, rig_root)

        # 2. BUILD IK WRIST
        ik_ctrl = cmds.curve(d=1, p=[(-1,1,-1),(1,1,-1),(1,1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1),(1,-1,-1),(1,-1,1),(-1,-1,1),(-1,-1,-1),(-1,1,-1),(1,1,-1),(1,-1,-1),(1,-1,1),(1,1,1),(-1,1,1),(-1,-1,1)], k=range(17), name="wrist_IK_CTRL")
        cmds.scale(arm_scale, arm_scale, arm_scale, ik_ctrl)
        cmds.makeIdentity(ik_ctrl, apply=True, t=1, r=1, s=1)
        self.set_color(ik_ctrl, 17) # Yellow
        ik_grp = cmds.group(ik_ctrl, name="wrist_IK_GRP")
        cmds.matchTransform(ik_grp, wrst_jnt, pos=True, rot=True)
        cmds.parent(ik_grp, rig_root)
        
        # 3. BUILD POLE VECTOR
        pv_pos = self.calculate_pole_vector(shldr_jnt, elbw_jnt, wrst_jnt, distance=arm_scale*4)
        pv_ctrl = cmds.circle(nr=(0,1,0), r=arm_scale*0.5, name="elbow_PV_CTRL")[0]
        self.set_color(pv_ctrl, 18) # Light Blue
        pv_grp = cmds.group(pv_ctrl, name="elbow_PV_GRP")
        cmds.xform(pv_grp, ws=True, t=(pv_pos.x, pv_pos.y, pv_pos.z))
        cmds.parent(pv_grp, rig_root)
        
        # 4. BUILD FK FINGERS
        fk_pairs = []
        for fj in fingers:
            if not cmds.listRelatives(fj, children=True, type="joint"): continue 
            f_ctrl = cmds.circle(nr=(1,0,0), r=arm_scale*0.4, name=fj.replace("_JNT", "_CTRL"))[0]
            self.set_color(f_ctrl, 14) # Green
            f_grp = cmds.group(f_ctrl, name=f_ctrl+"_GRP")
            cmds.matchTransform(f_grp, fj, pos=True, rot=True)
            
            parent_jnt = cmds.listRelatives(fj, parent=True)[0]
            if parent_jnt == wrst_jnt: cmds.parent(f_grp, ik_ctrl)
            else:
                parent_ctrl = parent_jnt.replace("_JNT", "_CTRL")
                if cmds.objExists(parent_ctrl): cmds.parent(f_grp, parent_ctrl)
                else: cmds.parent(f_grp, ik_ctrl)
            fk_pairs.append((f_ctrl, fj))

        # --- ANIMATION EXTRACTION (REVERSE BAKE) ---
        all_ctrls = [shldr_ctrl, ik_ctrl, pv_ctrl] + [c for c, j in fk_pairs]
        has_anim = any(cmds.keyframe(j, q=True, kc=True) for j in all_jnts)

        if has_anim:
            print("Animation detected on joints. Extracting to controls...")
            start = int(cmds.playbackOptions(q=True, min=True))
            end = int(cmds.playbackOptions(q=True, max=True))
            curr = cmds.currentTime(q=True)
            
            cmds.refresh(suspend=True) # Speed up extraction
            try:
                for f in range(start, end + 1):
                    cmds.currentTime(f, edit=True, update=True)
                    # Snap Shoulder
                    cmds.matchTransform(shldr_ctrl, shldr_jnt, pos=True, rot=True)
                    # Snap IK
                    cmds.matchTransform(ik_ctrl, wrst_jnt, pos=True, rot=True)
                    # Snap PV
                    cur_pv = self.calculate_pole_vector(shldr_jnt, elbw_jnt, wrst_jnt, distance=arm_scale*4)
                    cmds.xform(pv_ctrl, ws=True, t=(cur_pv.x, cur_pv.y, cur_pv.z))
                    # Snap FKs
                    for c, j in fk_pairs: cmds.matchTransform(c, j, pos=True, rot=True)
                    # Keyframe
                    cmds.setKeyframe(all_ctrls)
            finally:
                cmds.refresh(suspend=False)
                
            cmds.currentTime(curr)
            cmds.filterCurve(all_ctrls) # Fix euler flips
            cmds.cutKey(all_jnts, clear=True) # Delete keys from joints

        # --- APPLY RIG CONSTRAINTS ---
        # IK Handle
        ik_nodes = cmds.ikHandle(sj=shldr_jnt, ee=wrst_jnt, sol="ikRPsolver", name="arm_IKH")
        cmds.parent(ik_nodes[0], rig_root)
        cmds.setAttr(f"{ik_nodes[0]}.visibility", 0)
        
        # Constraints
        cmds.pointConstraint(shldr_ctrl, shldr_jnt, mo=False)
        cmds.orientConstraint(shldr_ctrl, shldr_jnt, mo=False)
        cmds.pointConstraint(ik_ctrl, ik_nodes[0], mo=False)
        cmds.orientConstraint(ik_ctrl, wrst_jnt, mo=True)
        cmds.poleVectorConstraint(pv_ctrl, ik_nodes[0])
        for c, j in fk_pairs: cmds.orientConstraint(c, j, mo=False)

        cmds.select(ik_ctrl)
        print("Rig successfully attached and driving joints.")

    def bake_and_detach(self):
        if not cmds.objExists(self.rig_root_name): return cmds.warning("No active rig found.")
        
        target_jnt = cmds.listConnections(f"{self.rig_root_name}.targetJnt")
        if not target_jnt: return
        
        chain = cmds.listRelatives(target_jnt[0], ad=True, type="joint") or []
        chain.append(target_jnt[0])
        
        start_frame = cmds.playbackOptions(q=True, min=True)
        end_frame = cmds.playbackOptions(q=True, max=True)
        
        cmds.bakeResults(
            chain, simulation=True, time=(start_frame, end_frame), sampleBy=1,
            disableImplicitControl=True, preserveOutsideKeys=True,
            sparseAnimCurveBake=False, minimizeRotation=True,
            shape=False, attribute=["tx", "ty", "tz", "rx", "ry", "rz"]
        )
        
        cmds.delete(self.rig_root_name)
        cmds.select(target_jnt[0])
        print("Animation baked to joints. Rig detached.")

try:
    ephemeral_ui.close()
    ephemeral_ui.deleteLater()
except: pass

ephemeral_ui = EphemeralRigTool()
ephemeral_ui.show()