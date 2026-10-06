import os
import maya.cmds as cmds

class ReferenceToolkitUI(object):
    def __init__(self):
        self.win_name = "RefMeshToolkitWin"
        self.win_title = "🛠️ Reference & QC Toolkit"
        self.tol = 0.001 # Tolerance for float comparisons
        
        self.comparer_log = "" 
        self.qc_log = ""       
        
        if cmds.window(self.win_name, exists=True):
            cmds.deleteUI(self.win_name)
            
        self.build_ui()
        self.populate_references()

    def build_ui(self):
        cmds.window(self.win_name, title=self.win_title, widthHeight=(600, 830), sizeable=True)
        self.main_layout = cmds.columnLayout(adjustableColumn=True)
        
        # --- TAB LAYOUT ---
        self.tabs = cmds.tabLayout(innerMarginWidth=5, innerMarginHeight=5, parent=self.main_layout)
        
        # ==========================================
        # TAB 1: MESH COMPARER
        # ==========================================
        self.tab_comparer = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, parent=self.tabs)
        
        cmds.frameLayout(label="⚙️ Comparer Setup", bgc=(0.2, 0.2, 0.2), collapsable=False, marginHeight=5, marginWidth=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        # Reference File Button
        cmds.button(label="📁 Reference New File...", height=28, bgc=(0.25, 0.35, 0.45), command=self.reference_file)
        cmds.separator(height=5, style="single")

        # Old Ref Line (Stretches)
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.text(label="   🟥 Old: ")
        self.opt_old = cmds.optionMenu()
        cmds.button(label="🔄 Swap", width=80, bgc=(0.3, 0.3, 0.3), command=self.swap_references)
        cmds.setParent("..")
        
        # New Ref Line (Stretches)
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.text(label="   🟩 New: ")
        self.opt_new = cmds.optionMenu()
        cmds.button(label="↻ Refresh", width=80, command=self.populate_references)
        cmds.setParent("..")
        
        cmds.setParent("..")
        cmds.setParent("..")
        
        cmds.separator(height=10, style="none")
        cmds.button(label="🚀 RUN COMPARISON", height=40, bgc=(0.3, 0.6, 0.4), command=self.run_comparison)
        cmds.button(label="📋 Copy Comparer Report", height=30, bgc=(0.3, 0.5, 0.7), command=self.copy_comparer_results)
        cmds.separator(height=10, style="none")
        
        cmds.frameLayout(label="📊 Analysis Results (Side by Side)", bgc=(0.15, 0.15, 0.15), collapsable=False)
        self.scroll_results_comparer = cmds.scrollLayout(height=500, childResizable=True)
        self.result_column_comparer = cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
        cmds.setParent("..") # Close scroll
        cmds.setParent("..") # Close frame
        cmds.setParent("..") # Close tab comparer
        
        # ==========================================
        # TAB 2: MODEL QC
        # ==========================================
        self.tab_qc = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, parent=self.tabs)
        
        cmds.frameLayout(label="🛠️ QC Setup", bgc=(0.2, 0.2, 0.2), collapsable=False, marginHeight=5, marginWidth=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        # Reference File Button
        cmds.button(label="📁 Reference New File...", height=28, bgc=(0.25, 0.35, 0.45), command=self.reference_file)
        cmds.separator(height=5, style="single")

        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.text(label="   🔎 Target Reference: ")
        self.opt_qc = cmds.optionMenu()
        cmds.button(label="↻ Refresh List", width=100, command=self.populate_references)
        cmds.setParent("..")
        
        # New Selection Checkbox
        cmds.rowLayout(numberOfColumns=1)
        self.cb_qc_selected = cmds.checkBox(label=" Run QC on Selected Meshes Only (Ignores Reference Dropdown)", value=False)
        cmds.setParent("..")
        
        cmds.setParent("..")
        cmds.setParent("..")
        
        cmds.separator(height=10, style="none")
        cmds.button(label="🩺 RUN MODEL QC", height=40, bgc=(0.6, 0.4, 0.2), command=self.run_qc)
        cmds.button(label="📋 Copy QC Report", height=30, bgc=(0.3, 0.5, 0.7), command=self.copy_qc_results)
        cmds.separator(height=10, style="none")
        
        cmds.frameLayout(label="📋 QC Results", bgc=(0.15, 0.15, 0.15), collapsable=False)
        self.scroll_results_qc = cmds.scrollLayout(height=500, childResizable=True)
        self.result_column_qc = cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
        cmds.setParent("..") # Close scroll
        cmds.setParent("..") # Close frame
        cmds.setParent("..") # Close tab qc
        
        # Attach tabs securely
        cmds.tabLayout(self.tabs, edit=True, tabLabel=((self.tab_comparer, '🔄 Mesh Comparer'), (self.tab_qc, '🛠️ Model QC')))
        
        cmds.showWindow(self.win_name)

    # ==========================================
    # SHARED METHODS
    # ==========================================
    def reference_file(self, *args):
        """Opens Maya's file dialog to choose and reference a file into the scene."""
        file_paths = cmds.fileDialog2(
            fileFilter="Maya Files (*.ma *.mb);;FBX Files (*.fbx);;OBJ Files (*.obj);;All Files (*.*)",
            dialogStyle=2,
            fileMode=1,
            caption="Select File to Reference"
        )
        
        if file_paths:
            file_path = file_paths[0]
            filename = os.path.basename(file_path)
            namespace_name = os.path.splitext(filename)[0]
            
            try:
                cmds.file(file_path, reference=True, namespace=namespace_name, ignoreVersion=True)
                cmds.warning(f"✅ Successfully referenced: {filename} (Namespace: '{namespace_name}')")
                self.populate_references()
            except Exception as e:
                cmds.warning(f"❌ Failed to reference file: {e}")

    def populate_references(self, *args):
        for opt in [self.opt_old, self.opt_new, self.opt_qc]:
            items = cmds.optionMenu(opt, q=True, itemListLong=True)
            if items:
                cmds.deleteUI(items)
                
        refs = cmds.file(q=True, reference=True) or []
        namespaces = []
        for ref in refs:
            try:
                ns = cmds.file(ref, q=True, namespace=True)
                namespaces.append(ns)
            except:
                pass
                
        if not namespaces:
            for opt in [self.opt_old, self.opt_new, self.opt_qc]:
                cmds.menuItem(label="No References Found", parent=opt)
            return

        for ns in namespaces:
            cmds.menuItem(label=ns, parent=self.opt_old)
            cmds.menuItem(label=ns, parent=self.opt_new)
            cmds.menuItem(label=ns, parent=self.opt_qc)
            
        if len(namespaces) >= 2:
            cmds.optionMenu(self.opt_new, edit=True, select=2)

    def floats_are_close(self, list_a, list_b):
        if not list_a or not list_b or len(list_a) != len(list_b): return False
        for a, b in zip(list_a, list_b):
            if abs(a - b) > self.tol: return False
        return True

    def _copy_to_clipboard(self, text_data):
        try:
            try:
                from PySide2.QtWidgets import QApplication
            except ImportError:
                from PySide6.QtWidgets import QApplication
            
            cb = QApplication.clipboard()
            cb.setText(text_data)
            cmds.warning("✅ Report successfully copied to Clipboard!")
        except Exception as e:
            print(text_data)
            cmds.warning("Could not access OS clipboard. Report printed to Script Editor instead.")

    # ==========================================
    # COMPARER TAB METHODS
    # ==========================================
    def swap_references(self, *args):
        old_val = cmds.optionMenu(self.opt_old, q=True, value=True)
        new_val = cmds.optionMenu(self.opt_new, q=True, value=True)
        cmds.optionMenu(self.opt_old, edit=True, value=new_val)
        cmds.optionMenu(self.opt_new, edit=True, value=old_val)

    def clear_comparer_results(self):
        self.comparer_log = "--- MESH COMPARISON REPORT ---\n\n"
        children = cmds.columnLayout(self.result_column_comparer, q=True, childArray=True)
        if children: cmds.deleteUI(children)

        form = cmds.formLayout(parent=self.result_column_comparer)
        t1 = cmds.text(label="   🟥 OLD REFERENCE STATE", font="boldLabelFont", bgc=(0.8, 0.5, 0.5), height=25, align="left")
        t2 = cmds.text(label="   🟩 NEW REFERENCE STATE", font="boldLabelFont", bgc=(0.5, 0.8, 0.5), height=25, align="left")
        cmds.formLayout(form, edit=True,
            attachForm=[(t1, 'left', 0), (t1, 'top', 0), (t1, 'bottom', 0),
                        (t2, 'right', 0), (t2, 'top', 0), (t2, 'bottom', 0)],
            attachPosition=[(t1, 'right', 0, 50), (t2, 'left', 0, 50)]
        )
        cmds.setParent("..")

    def add_comparer_header(self, title):
        self.comparer_log += f"\n[{title}]\n"
        cmds.separator(height=10, style="none", parent=self.result_column_comparer)
        cmds.text(label=f"  {title}", font="boldLabelFont", align="left", bgc=(0.6, 0.6, 0.6), height=25, parent=self.result_column_comparer)

    def add_comparer_row(self, old_text, new_text, bg_color):
        self.comparer_log += f"OLD: {old_text}  |  NEW: {new_text}\n"
        form = cmds.formLayout(parent=self.result_column_comparer, bgc=bg_color)
        t1 = cmds.textField(text=f" {old_text}", editable=True, bgc=bg_color)
        t2 = cmds.textField(text=f" {new_text}", editable=True, bgc=bg_color)
        cmds.formLayout(form, edit=True,
            attachForm=[(t1, 'left', 1), (t1, 'top', 1), (t1, 'bottom', 1),
                        (t2, 'right', 1), (t2, 'top', 1), (t2, 'bottom', 1)],
            attachPosition=[(t1, 'right', 1, 50), (t2, 'left', 1, 50)]
        )
        cmds.setParent("..")

    def add_comparer_full_row(self, text, bg_color):
        self.comparer_log += f"{text}\n"
        cmds.columnLayout(adjustableColumn=True, parent=self.result_column_comparer, bgc=bg_color)
        cmds.textField(text=f"  {text}", editable=True, bgc=bg_color, font="plainLabelFont")
        cmds.setParent("..")

    def copy_comparer_results(self, *args):
        self._copy_to_clipboard(self.comparer_log)

    def get_comparer_data(self, namespace):
        """Used strictly for the Comparer to strip namespaces for 1:1 cross-namespace matching"""
        mesh_shapes = cmds.ls(f"{namespace}:*", type="mesh", long=True)
        data = {}
        for shape in mesh_shapes:
            if cmds.getAttr(shape + ".intermediateObject"): continue
            parent_transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
            
            base_transform = parent_transform.split(":")[-1].split("|")[-1]
            base_shape = shape.split(":")[-1].split("|")[-1]
            vtx_count = cmds.polyEvaluate(parent_transform, vertex=True)
            
            t = cmds.xform(parent_transform, q=True, t=True, os=True)
            r = cmds.xform(parent_transform, q=True, ro=True, os=True)
            s = cmds.xform(parent_transform, q=True, s=True, os=True)
            bb = cmds.xform(parent_transform, q=True, bb=True, os=True)
            bb_size = [bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]]
            
            data[base_transform] = {
                "shape": base_shape, "vtx": vtx_count,
                "t": t, "r": r, "s": s, "bb_size": bb_size
            }
        return data

    def run_comparison(self, *args):
        self.clear_comparer_results()
        ns_old = cmds.optionMenu(self.opt_old, q=True, value=True)
        ns_new = cmds.optionMenu(self.opt_new, q=True, value=True)
        
        if not ns_old or not ns_new or ns_old == "No References Found":
            self.add_comparer_row("⚠️ Invalid selection", "⚠️ Invalid selection", (0.9, 0.7, 0.4))
            return
            
        old_data = self.get_comparer_data(ns_old)
        new_data = self.get_comparer_data(ns_new)
        
        old_meshes = set(old_data.keys())
        new_meshes = set(new_data.keys())
        
        missing_in_new = old_meshes - new_meshes
        added_in_new = new_meshes - old_meshes
        common_meshes = old_meshes.intersection(new_meshes)
        
        error_found = False

        if missing_in_new or added_in_new:
            self.add_comparer_header("❌ MESH HIERARCHY MISMATCH")
            error_found = True
            for m in missing_in_new: self.add_comparer_row(f"➖ {ns_old}:{m}", "❌ (Deleted / Missing)", (0.9, 0.6, 0.6))
            for m in added_in_new: self.add_comparer_row("❌ (Did not exist)", f"➕ {ns_new}:{m}", (0.6, 0.85, 0.6))

        vtx_issues, shape_issues, transform_issues, bbox_issues = [], [], [], []

        for mesh in sorted(common_meshes):
            d_old = old_data[mesh]
            d_new = new_data[mesh]
            
            expected_shape = mesh + "Shape"
            if d_new["shape"] != expected_shape or d_old["shape"] != expected_shape:
                shape_issues.append((mesh, d_old["shape"], d_new["shape"], expected_shape))
                
            if d_old["vtx"] != d_new["vtx"]:
                vtx_issues.append((mesh, d_old["vtx"], d_new["vtx"]))
                
            trs_changed = []
            if not self.floats_are_close(d_old["t"], d_new["t"]): trs_changed.append("T")
            if not self.floats_are_close(d_old["r"], d_new["r"]): trs_changed.append("R")
            if not self.floats_are_close(d_old["s"], d_new["s"]): trs_changed.append("S")
            if trs_changed: transform_issues.append((mesh, ", ".join(trs_changed)))
                
            if not self.floats_are_close(d_old["bb_size"], d_new["bb_size"]):
                bbox_issues.append(mesh)

        if vtx_issues:
            self.add_comparer_header("🔢 VERTEX COUNT MISMATCH")
            error_found = True
            for mesh, old_v, new_v in vtx_issues: self.add_comparer_row(f"⚠️ {ns_old}:{mesh}: {old_v} vtx", f"⚠️ {ns_new}:{mesh}: {new_v} vtx", (0.9, 0.8, 0.5))

        if transform_issues:
            self.add_comparer_header("📐 TRANSFORM VALUES MODIFIED")
            error_found = True
            for mesh, changes in transform_issues: self.add_comparer_row(f"🔄 {ns_old}:{mesh} (Original)", f"🔄 {ns_new}:{mesh} ({changes} modified)", (0.7, 0.7, 0.9))

        if bbox_issues:
            self.add_comparer_header("📦 BOUNDING BOX SCALE / VOLUME CHANGED")
            error_found = True
            for mesh in bbox_issues: self.add_comparer_row(f"📏 {ns_old}:{mesh} (Base Size)", f"📏 {ns_new}:{mesh} (Changed)", (0.6, 0.8, 0.9))

        if shape_issues:
            self.add_comparer_header("📛 SHAPE NAMING ISSUES")
            error_found = True
            for mesh, old_sh, new_sh, expected in shape_issues:
                self.add_comparer_row(f"❗ {ns_old}:{mesh} -> '{old_sh}'", f"❗ {ns_new}:{mesh} -> '{new_sh}'", (0.9, 0.7, 0.9))

        if not error_found:
            self.add_comparer_header("✅ ALL CLEAR")
            self.add_comparer_row("🌟 Hierarchy & Transforms Match", "🌟 Hierarchy & Transforms Match", (0.6, 0.9, 0.6))

        self.add_comparer_header("📊 TOTAL MESH COUNT SUMMARY")
        self.add_comparer_row(f"Total Old Meshes: {len(old_meshes)}", f"Total New Meshes: {len(new_meshes)}", (0.8, 0.8, 0.85))

        self.add_comparer_header("✅ SCRIPT EXECUTION CHECKLIST")
        check_bg = (0.75, 0.85, 0.75)
        self.add_comparer_full_row("✔️ Reference validity and namespaces confirmed", check_bg)
        self.add_comparer_full_row("✔️ Mesh hierarchy compared (Missing/Added checks)", check_bg)
        self.add_comparer_full_row("✔️ Shape naming conventions verified", check_bg)
        self.add_comparer_full_row("✔️ Vertex counts matched across versions", check_bg)
        self.add_comparer_full_row("✔️ Transform values (Translate, Rotate, Scale) checked", check_bg)
        self.add_comparer_full_row("✔️ Bounding box sizes / volumes calculated and compared", check_bg)


    # ==========================================
    # QC TAB METHODS
    # ==========================================
    def clear_qc_results(self):
        self.qc_log = "--- MODEL QC REPORT ---\n\n"
        children = cmds.columnLayout(self.result_column_qc, q=True, childArray=True)
        if children: cmds.deleteUI(children)

    def add_qc_header(self, title):
        self.qc_log += f"\n[{title}]\n"
        cmds.separator(height=10, style="none", parent=self.result_column_qc)
        cmds.text(label=f"  {title}", font="boldLabelFont", align="left", bgc=(0.4, 0.5, 0.6), height=25, parent=self.result_column_qc)

    def add_qc_row(self, message, bg_color):
        self.qc_log += f"{message}\n"
        cmds.columnLayout(adjustableColumn=True, parent=self.result_column_qc, bgc=bg_color)
        cmds.textField(text=f"  {message}", editable=True, bgc=bg_color)
        cmds.setParent("..")

    def copy_qc_results(self, *args):
        self._copy_to_clipboard(self.qc_log)

    def run_qc(self, *args):
        self.clear_qc_results()
        
        run_selected = cmds.checkBox(self.cb_qc_selected, q=True, value=True)
        mesh_data = {}
        target_info = ""

        # --- GATHER DATA LOGIC ---
        if run_selected:
            target_info = "User Selection (Ignored Reference Dropdown)"
            sel_shapes = cmds.ls(selection=True, dag=True, type="mesh", long=True) or []
            
            if not sel_shapes:
                self.add_qc_row("⚠️ No meshes selected in the viewport.", (0.9, 0.7, 0.4))
                return
                
            for shape in sel_shapes:
                if cmds.getAttr(shape + ".intermediateObject"): continue
                
                parent_transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
                
                short_transform = parent_transform.split("|")[-1] 
                short_shape = shape.split("|")[-1]
                
                t = cmds.xform(parent_transform, q=True, t=True, os=True)
                r = cmds.xform(parent_transform, q=True, ro=True, os=True)
                s = cmds.xform(parent_transform, q=True, s=True, os=True)
                
                mesh_data[short_transform] = {"shape": short_shape, "t": t, "r": r, "s": s}

        else:
            ns_qc = cmds.optionMenu(self.opt_qc, q=True, value=True)
            if not ns_qc or ns_qc == "No References Found":
                self.add_qc_row("⚠️ Invalid reference selected. Please select a reference or check 'Run on Selected'.", (0.9, 0.7, 0.4))
                return
                
            target_info = f"Namespace Reference: {ns_qc}"
            ref_shapes = cmds.ls(f"{ns_qc}:*", type="mesh", long=True) or []
            
            if not ref_shapes:
                self.add_qc_row(f"⚠️ No meshes found in namespace '{ns_qc}'.", (0.9, 0.7, 0.4))
                return
                
            for shape in ref_shapes:
                if cmds.getAttr(shape + ".intermediateObject"): continue
                
                parent_transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
                short_transform = parent_transform.split("|")[-1] 
                short_shape = shape.split("|")[-1]
                
                t = cmds.xform(parent_transform, q=True, t=True, os=True)
                r = cmds.xform(parent_transform, q=True, ro=True, os=True)
                s = cmds.xform(parent_transform, q=True, s=True, os=True)
                
                mesh_data[short_transform] = {"shape": short_shape, "t": t, "r": r, "s": s}

        # --- EVALUATE QC LOGIC ---
        dirty_transforms = []
        bad_shapes = []
        
        zero_vec = [0.0, 0.0, 0.0]
        one_vec = [1.0, 1.0, 1.0]

        for mesh, data in mesh_data.items():
            dirty_attrs = []
            
            if not self.floats_are_close(data["t"], zero_vec): dirty_attrs.append("Translate")
            if not self.floats_are_close(data["r"], zero_vec): dirty_attrs.append("Rotate")
            if not self.floats_are_close(data["s"], one_vec): dirty_attrs.append("Scale")
            
            if dirty_attrs:
                dirty_transforms.append((mesh, ", ".join(dirty_attrs)))
                
            expected = mesh + "Shape"
            if data["shape"] != expected:
                bad_shapes.append((mesh, data["shape"], expected))

        error_found = False

        if dirty_transforms:
            self.add_qc_header("⚠️ UN-FROZEN TRANSFORMS DETECTED")
            error_found = True
            for mesh, attrs in dirty_transforms:
                self.add_qc_row(f"🧊 {mesh} | Values not frozen on: {attrs}", (0.9, 0.8, 0.5))

        if bad_shapes:
            self.add_qc_header("📛 INCORRECT SHAPE NAMES DETECTED")
            error_found = True
            for mesh, current, expected in bad_shapes:
                self.add_qc_row(f"❗ {mesh} | Shape is '{current}' (Expected: '{expected}')", (0.9, 0.7, 0.7))

        if not error_found:
            self.add_qc_header("✅ QC PASSED")
            self.add_qc_row("🌟 All checked meshes have frozen transforms and correct shape names!", (0.6, 0.9, 0.6))
            
        self.add_qc_header("📋 QC EXECUTION SUMMARY")
        self.add_qc_row(f"✔️ Target: {target_info}", (0.8, 0.8, 0.85))
        self.add_qc_row(f"✔️ Total Meshes Scanned: {len(mesh_data.keys())}", (0.8, 0.8, 0.85))
        self.add_qc_row("✔️ Checked: Translates & Rotates == [0,0,0]", (0.75, 0.85, 0.75))
        self.add_qc_row("✔️ Checked: Scales == [1,1,1]", (0.75, 0.85, 0.75))
        self.add_qc_row("✔️ Checked: Shape == TransformName + 'Shape'", (0.75, 0.85, 0.75))

# Execute the UI
ReferenceToolkitUI()