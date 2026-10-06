import maya.cmds as cmds
import re
import difflib

class AnimCopyMirrorUI(object):
    def __init__(self):
        self.window_name = "animCopyMirrorWindow"
        
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.window = cmds.window(self.window_name, title="Smart Copy & Mirror Keys", widthHeight=(500, 380))
        self.main_layout = cmds.formLayout()
        
        # --- TAB LAYOUT ---
        self.tabs = cmds.tabLayout(innerMarginWidth=5, innerMarginHeight=5)
        
        # ==========================================
        # TAB 1: COPY KEYS
        # ==========================================
        self.tab_copy = cmds.formLayout()
        self.pane_copy = cmds.paneLayout(configuration='vertical2')
        
        self.col_copy_L = cmds.columnLayout(adjustableColumn=True)
        cmds.button(label="Reload Left (Sources)", backgroundColor=(0.3, 0.3, 0.3), command=lambda x: self.load_list(self.list_copy_src))
        self.list_copy_src = cmds.textScrollList(allowMultiSelection=True, height=200, selectCommand=lambda: self.on_select(self.list_copy_src))
        cmds.setParent('..')
        
        self.col_copy_R = cmds.columnLayout(adjustableColumn=True)
        cmds.button(label="Reload Right (Targets)", backgroundColor=(0.3, 0.3, 0.3), command=lambda x: self.load_list(self.list_copy_tgt))
        self.list_copy_tgt = cmds.textScrollList(allowMultiSelection=True, height=200, selectCommand=lambda: self.on_select(self.list_copy_tgt))
        cmds.setParent('..')
        
        cmds.setParent(self.tab_copy)
        self.btn_copy = cmds.button(label="Smart Auto-Copy Animation >>", height=40, backgroundColor=(0.2, 0.4, 0.2), command=self.execute_copy)
        
        cmds.formLayout(self.tab_copy, edit=True,
                        attachForm=[(self.pane_copy, 'top', 5), (self.pane_copy, 'left', 5), (self.pane_copy, 'right', 5),
                                    (self.btn_copy, 'left', 5), (self.btn_copy, 'right', 5), (self.btn_copy, 'bottom', 5)],
                        attachControl=[(self.pane_copy, 'bottom', 5, self.btn_copy)])
        cmds.setParent(self.tabs)
        
        # ==========================================
        # TAB 2: MIRROR KEYS
        # ==========================================
        self.tab_mirror = cmds.formLayout()
        
        self.frame_mirror = cmds.frameLayout(label="Mirror Settings", marginHeight=5)
        self.radio_plane = cmds.radioButtonGrp(label='Mirror Plane: ', labelArray3=['XY (Front/Back)', 'YZ (Left/Right)', 'XZ (Top/Bottom)'], numberOfRadioButtons=3, select=2)
        cmds.setParent(self.tab_mirror)
        
        self.pane_mirror = cmds.paneLayout(configuration='vertical2')
        
        self.col_mirror_L = cmds.columnLayout(adjustableColumn=True)
        cmds.button(label="Reload Left (Sources)", backgroundColor=(0.3, 0.3, 0.4), command=lambda x: self.load_list(self.list_mirror_src))
        self.list_mirror_src = cmds.textScrollList(allowMultiSelection=True, height=200, selectCommand=lambda: self.on_select(self.list_mirror_src))
        cmds.setParent('..')
        
        self.col_mirror_R = cmds.columnLayout(adjustableColumn=True)
        cmds.button(label="Reload Right (Targets)", backgroundColor=(0.3, 0.3, 0.4), command=lambda x: self.load_list(self.list_mirror_tgt))
        self.list_mirror_tgt = cmds.textScrollList(allowMultiSelection=True, height=200, selectCommand=lambda: self.on_select(self.list_mirror_tgt))
        cmds.setParent('..')
        
        cmds.setParent(self.tab_mirror)
        self.btn_mirror = cmds.button(label="Smart Auto-Mirror Animation >>", height=40, backgroundColor=(0.2, 0.3, 0.5), command=self.execute_mirror)
        
        cmds.formLayout(self.tab_mirror, edit=True,
                        attachForm=[(self.frame_mirror, 'top', 5), (self.frame_mirror, 'left', 5), (self.frame_mirror, 'right', 5),
                                    (self.pane_mirror, 'left', 5), (self.pane_mirror, 'right', 5),
                                    (self.btn_mirror, 'left', 5), (self.btn_mirror, 'right', 5), (self.btn_mirror, 'bottom', 5)],
                        attachControl=[(self.pane_mirror, 'top', 5, self.frame_mirror),
                                       (self.pane_mirror, 'bottom', 5, self.btn_mirror)])
        cmds.setParent(self.tabs)
        
        cmds.tabLayout(self.tabs, edit=True, tabLabel=((self.tab_copy, 'Copy Keys'), (self.tab_mirror, 'Mirror Keys')))
        cmds.formLayout(self.main_layout, edit=True, attachForm=[(self.tabs, 'top', 0), (self.tabs, 'left', 0), (self.tabs, 'right', 0), (self.tabs, 'bottom', 0)])
        cmds.showWindow(self.window)
        
    def load_list(self, list_ui):
        sel = cmds.ls(selection=True)
        cmds.textScrollList(list_ui, edit=True, removeAll=True)
        if sel: cmds.textScrollList(list_ui, edit=True, append=sel)

    def on_select(self, list_ui):
        items = cmds.textScrollList(list_ui, query=True, selectItem=True)
        if items:
            valid = [obj for obj in items if cmds.objExists(obj)]
            if valid: cmds.select(valid, replace=True)

    def _create_skeleton(self, core_name):
        skel = re.sub(r'\d+', '#', core_name)
        skel = re.sub(r'(^|_)[LR](_|#|$)', r'\1@\2', skel)
        return skel

    def _smart_match(self, src, target_list):
        # 1. Strip DAG path ('|') and Namespace (':') to get the clean core name
        src_core = src.split('|')[-1].split(':')[-1]
        src_skeleton = self._create_skeleton(src_core)
        
        valid_candidates = []
        for tgt in target_list:
            # 2. Strip DAG path and Namespace for the targets as well
            tgt_core = tgt.split('|')[-1].split(':')[-1]
            tgt_skeleton = self._create_skeleton(tgt_core)
            
            if tgt_skeleton == src_skeleton:
                valid_candidates.append(tgt)
                
        if not valid_candidates: return None
        if len(valid_candidates) == 1: return valid_candidates[0]
            
        best_match = None
        highest_ratio = -1.0
        for candidate in valid_candidates:
            candidate_core = candidate.split('|')[-1].split(':')[-1]
            # 3. Fuzzy match using ONLY the core name so namespaces don't skew the results
            ratio = difflib.SequenceMatcher(None, src_core, candidate_core).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = candidate
                
        return best_match

    def _copy_trs_data(self, source_obj, target_obj, attributes):
        for attr in attributes:
            target_plug = f"{target_obj}.{attr}"
            if not cmds.objExists(target_plug) or not cmds.getAttr(target_plug, settable=True):
                continue
                
            if cmds.keyframe(source_obj, attribute=attr, query=True, keyframeCount=True):
                cmds.copyKey(source_obj, attribute=attr, option="keys")
                try: cmds.pasteKey(target_obj, attribute=attr, option="replace")
                except RuntimeError as e: cmds.warning(f"Skipped {target_plug}: {e}")

    def _mirror_trs_data(self, source_obj, target_obj, attributes, plane_index):
        self._copy_trs_data(source_obj, target_obj, attributes)
        
        invert_attrs = []
        if plane_index == 1:   invert_attrs = ['tz', 'rx', 'ry']
        elif plane_index == 2: invert_attrs = ['tx', 'ry', 'rz']
        elif plane_index == 3: invert_attrs = ['ty', 'rx', 'rz']
            
        for attr in invert_attrs:
            target_plug = f"{target_obj}.{attr}"
            if cmds.objExists(target_plug) and cmds.getAttr(target_plug, settable=True):
                if cmds.keyframe(target_obj, attribute=attr, query=True, keyframeCount=True):
                    cmds.scaleKey(target_obj, attribute=attr, valueScale=-1)

    def execute_copy(self, *args):
        source_objs = cmds.textScrollList(self.list_copy_src, query=True, selectItem=True) or cmds.textScrollList(self.list_copy_src, query=True, allItems=True)
        target_objs = cmds.textScrollList(self.list_copy_tgt, query=True, selectItem=True) or cmds.textScrollList(self.list_copy_tgt, query=True, allItems=True)
        self._run_transfer(source_objs, target_objs, is_mirror=False)

    def execute_mirror(self, *args):
        source_objs = cmds.textScrollList(self.list_mirror_src, query=True, selectItem=True) or cmds.textScrollList(self.list_mirror_src, query=True, allItems=True)
        target_objs = cmds.textScrollList(self.list_mirror_tgt, query=True, selectItem=True) or cmds.textScrollList(self.list_mirror_tgt, query=True, allItems=True)
        self._run_transfer(source_objs, target_objs, is_mirror=True)

    def _run_transfer(self, source_objs, target_objs, is_mirror):
        if not source_objs or not target_objs:
            cmds.warning("Please load objects into both the Left and Right lists.")
            return
            
        attributes = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz']
        success_count = 0
        plane_idx = cmds.radioButtonGrp(self.radio_plane, query=True, select=True) if is_mirror else None
        
        if len(source_objs) == 1:
            src = source_objs[0]
            for tgt in target_objs:
                if tgt != src:
                    if is_mirror: self._mirror_trs_data(src, tgt, attributes, plane_idx)
                    else: self._copy_trs_data(src, tgt, attributes)
                    success_count += 1
        else:
            for src in source_objs:
                tgt = self._smart_match(src, target_objs)
                if tgt and tgt != src:
                    if is_mirror: self._mirror_trs_data(src, tgt, attributes, plane_idx)
                    else: self._copy_trs_data(src, tgt, attributes)
                    success_count += 1
                else:
                    cmds.warning(f"Could not guess a target match for '{src}'. Skipped.")
                    
        op_name = "mirrored" if is_mirror else "copied"
        print(f"Successfully {op_name} TRS animation to {success_count} target control(s).")

AnimCopyMirrorUI()