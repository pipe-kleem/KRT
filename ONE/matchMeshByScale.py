import maya.cmds as cmds
import math

class AutoVertexMatcherMatrixUI:
    def __init__(self):
        self.window_name = "AutoVertexMatcherMatrixWin"
        self.build_ui()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        self.win = cmds.window(
            self.window_name, 
            title="Matrix Precision Vertex Matcher", 
            widthHeight=(380, 260), 
            sizeable=True
        )
        
        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=["both", 12])
        
        cmds.separator(height=8, style='none')
        cmds.text(label="3D Space Matrix Scale Matcher", font="boldLabelFont", align="center")
        cmds.separator(height=10, style='single')

        # 1. Scalable Object
        self.driver_grp = cmds.textFieldButtonGrp(
            label="Scalable Object: ",
            buttonLabel="Load",
            columnWidth3=[110, 170, 60],
            buttonCommand=lambda: self.load_element(self.driver_grp, target_type="object")
        )

        # 2. Driven Vertex 1
        self.vtx1_grp = cmds.textFieldButtonGrp(
            label="Driven Vertex 1: ",
            buttonLabel="Load",
            columnWidth3=[110, 170, 60],
            buttonCommand=lambda: self.load_element(self.vtx1_grp, target_type="vertex")
        )

        # 3. Target Vertex 2
        self.vtx2_grp = cmds.textFieldButtonGrp(
            label="Target Vertex 2: ",
            buttonLabel="Load",
            columnWidth3=[110, 170, 60],
            buttonCommand=lambda: self.load_element(self.vtx2_grp, target_type="vertex")
        )

        cmds.separator(height=10, style='single')

        # Distance Feedback
        self.dist_text = cmds.text(label="3D Matrix Distance: -- units", align="center", font="boldLabelFont")
        
        cmds.separator(height=5, style='none')

        # MAIN RUN BUTTON
        cmds.button(
            label="🎯 SOLVE & MATCH VERTICES EXACTLY",
            height=42,
            backgroundColor=[0.15, 0.5, 0.35],
            command=lambda x: self.solve_matrix_precision()
        )

        cmds.showWindow(self.win)

    def load_element(self, grp, target_type="object"):
        """Loads selected item into UI field."""
        sel = cmds.ls(selection=True, flatten=True)
        if not sel:
            cmds.warning("Nothing selected! Select an item in Maya and click Load.")
            return

        item = sel[0]
        if target_type == "object":
            obj_name = item.split('.')[0]
            cmds.textFieldButtonGrp(grp, edit=True, text=obj_name)
        elif target_type == "vertex":
            if ".vtx[" in item:
                cmds.textFieldButtonGrp(grp, edit=True, text=item)
            else:
                cmds.warning("Selected item is not a vertex! Select a single vertex (e.g., mesh.vtx[5]).")

        self.get_distance()

    def get_vtx_pos(self, vtx_name):
        """Forces DG evaluation to get exact, updated world space position."""
        if not vtx_name or not cmds.objExists(vtx_name):
            return None
        # Force Maya to update vertex matrix position in world space
        cmds.dgeval(vtx_name)
        return cmds.xform(vtx_name, query=True, worldSpace=True, translation=True)

    def get_distance(self):
        """Calculates distance between Vertex 1 and Vertex 2."""
        v1 = cmds.textFieldButtonGrp(self.vtx1_grp, query=True, text=True)
        v2 = cmds.textFieldButtonGrp(self.vtx2_grp, query=True, text=True)
        
        p1 = self.get_vtx_pos(v1)
        p2 = self.get_vtx_pos(v2)

        if p1 and p2:
            dist = math.sqrt(sum((a - b)**2 for a, b in zip(p1, p2)))
            cmds.text(self.dist_text, edit=True, label=f"3D Matrix Distance: {dist:.6f} units")
            return dist
        else:
            cmds.text(self.dist_text, edit=True, label="3D Matrix Distance: -- units")
            return None

    def set_scale(self, driver, scale_factor):
        """Applies uniform scale factor to X, Y, and Z axes."""
        for ax in ['X', 'Y', 'Z']:
            cmds.setAttr(f"{driver}.scale{ax}", scale_factor)

    def solve_matrix_precision(self):
        """Uses Binary Search to solve for the exact scale matching vertex 1 to vertex 2 in 3D matrix."""
        driver = cmds.textFieldButtonGrp(self.driver_grp, query=True, text=True)
        v1 = cmds.textFieldButtonGrp(self.vtx1_grp, query=True, text=True)
        v2 = cmds.textFieldButtonGrp(self.vtx2_grp, query=True, text=True)

        if not (driver and v1 and v2 and cmds.objExists(driver) and cmds.objExists(v1) and cmds.objExists(v2)):
            cmds.warning("Ensure Object, Driven Vertex 1, and Target Vertex 2 are all loaded!")
            return

        current_scale = cmds.getAttr(f"{driver}.scaleX")
        initial_dist = self.get_distance()

        if initial_dist < 0.00001:
            cmds.inViewMessage(amg="<hl>Vertices are already at the exact same position!</hl>", pos='topCenter', fade=True)
            return

        # 1. Determine direction (Is scale UP or DOWN reducing distance?)
        test_scale_up = current_scale * 1.05
        self.set_scale(driver, test_scale_up)
        dist_up = self.get_distance()

        test_scale_down = current_scale * 0.95
        self.set_scale(driver, test_scale_down)
        dist_down = self.get_distance()

        # Revert back to original
        self.set_scale(driver, current_scale)

        if dist_up < initial_dist:
            # Scaling UP brings vertices closer
            low_scale = current_scale
            high_scale = current_scale * 50.0  # Upper bound search limit
        elif dist_down < initial_dist:
            # Scaling DOWN brings vertices closer
            low_scale = current_scale * 0.0001  # Lower bound search limit
            high_scale = current_scale
        else:
            cmds.warning("Scaling this object does not reduce distance to target vertex!")
            return

        # 2. High-Precision Binary Search Loop (50 Iterations for 0.00001 Unit Accuracy)
        best_scale = current_scale
        min_dist = initial_dist

        for _ in range(60):
            mid_scale = (low_scale + high_scale) / 2.0
            self.set_scale(driver, mid_scale)
            cmds.refresh()  # Force viewport render refresh
            
            mid_dist = self.get_distance()

            if mid_dist is None:
                break

            if mid_dist < min_dist:
                min_dist = mid_dist
                best_scale = mid_scale

            # Bracket narrowing logic
            self.set_scale(driver, mid_scale * 1.0001)
            dist_slightly_larger = self.get_distance()

            if dist_slightly_larger < mid_dist:
                low_scale = mid_scale
            else:
                high_scale = mid_scale

            if min_dist < 0.00001:  # Target precision reached
                break

        # Apply optimal solved scale
        self.set_scale(driver, best_scale)
        final_dist = self.get_distance()

        cmds.inViewMessage(
            amg=f"<hl>Position Matched!</hl> Final Distance: <b>{final_dist:.6f}</b> | Scale set to: <b>{best_scale:.4f}</b>", 
            pos='topCenter', 
            fade=True
        )

# Run the UI
AutoVertexMatcherMatrixUI()