import os
import shutil
import json
import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore, QtGui

# presets path : C:\Users\<YourName>\Documents\maya\2025\prefs\my_folder_presets.json
# link : https://gemini.google.com/u/1/app/5f17e21257f30a93?pageId=none

class DragDropLineEdit(QtWidgets.QLineEdit):
    """Custom QLineEdit that accepts drag and drop files."""
    def __init__(self, parent=None):
        super(DragDropLineEdit, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drag & drop a file here (Optional)...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super(DragDropLineEdit, self).dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super(DragDropLineEdit, self).dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            self.setText(filepath)
            event.acceptProposedAction()

class FileDirectoryTool(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(FileDirectoryTool, self).__init__(parent)
        self.setObjectName("MyUniqueFileDirectoryTool_2025")
        
        self.setWindowTitle("File & Directory Manager (Maya 2025)")
        self.setMinimumWidth(650)
        self.setMinimumHeight(550)
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        
        self.root_item = None
        self.folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        
        pref_dir = cmds.internalVar(userPrefDir=True)
        self.preset_file = os.path.join(pref_dir, "my_folder_presets.json")
        self.presets = self.load_presets()
        
        self.build_ui()
        self.connect_signals()
        self.populate_preset_combo()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15)

        # --- Section 1: Directory Setup ---
        dir_group = QtWidgets.QGroupBox("1. Base Path")
        dir_layout = QtWidgets.QHBoxLayout(dir_group)

        self.base_path_edit = QtWidgets.QLineEdit()
        self.base_path_edit.setPlaceholderText("Select your root working directory...")
        self.browse_btn = QtWidgets.QPushButton("Browse")

        dir_layout.addWidget(self.base_path_edit)
        dir_layout.addWidget(self.browse_btn)

        # --- Section 2: File Source ---
        file_group = QtWidgets.QGroupBox("2. Source File (Drag & Drop)")
        file_layout = QtWidgets.QVBoxLayout(file_group)

        self.source_file_edit = DragDropLineEdit()
        self.source_file_edit.setMinimumHeight(40)
        file_layout.addWidget(self.source_file_edit)

        # --- Section 3: Visualizer & Presets ---
        viz_group = QtWidgets.QGroupBox("3. Directory Visualizer & Presets")
        viz_layout = QtWidgets.QVBoxLayout(viz_group)
        
        preset_layout = QtWidgets.QHBoxLayout()
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setMinimumWidth(150)
        
        self.apply_preset_btn = QtWidgets.QPushButton("Apply Preset")
        self.save_preset_btn = QtWidgets.QPushButton("Save Selected as Preset")
        
        preset_layout.addWidget(QtWidgets.QLabel("Presets:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(self.apply_preset_btn)
        preset_layout.addWidget(self.save_preset_btn)
        
        viz_layout.addLayout(preset_layout)
        
        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setMinimumHeight(250)
        viz_layout.addWidget(self.tree_widget)

        self.new_folder_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+N"), self.tree_widget)
        self.new_folder_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)

        self.del_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Delete"), self.tree_widget)
        self.del_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        
        self.bksp_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Backspace"), self.tree_widget)
        self.bksp_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)

        # --- Section 4: Action Button ---
        self.execute_btn = QtWidgets.QPushButton("Build Folders & Save File")
        self.execute_btn.setMinimumHeight(40)
        self.execute_btn.setStyleSheet("background-color: #3a5f43; font-weight: bold; font-size: 14px;")

        main_layout.addWidget(dir_group)
        main_layout.addWidget(file_group)
        main_layout.addWidget(viz_group)
        main_layout.addWidget(self.execute_btn)

    def connect_signals(self):
        self.browse_btn.clicked.connect(self.browse_base_path)
        self.base_path_edit.textChanged.connect(self.update_tree_root)
        self.tree_widget.itemExpanded.connect(self.on_item_expanded)
        self.new_folder_shortcut.activated.connect(self.create_virtual_folder)
        self.del_shortcut.activated.connect(self.delete_selected_item)
        self.bksp_shortcut.activated.connect(self.delete_selected_item)
        self.execute_btn.clicked.connect(self.execute_action)
        self.save_preset_btn.clicked.connect(self.save_preset_action)
        self.apply_preset_btn.clicked.connect(self.apply_preset_action)

    # --- Deletion Logic ---
    def delete_selected_item(self):
        selected = self.tree_widget.selectedItems()
        if not selected: return
        item = selected[0]

        if item == self.root_item:
            cmds.warning("You cannot delete the root base path folder.")
            return

        is_virtual = item.data(0, QtCore.Qt.UserRole + 1)
        is_file = item.data(0, QtCore.Qt.UserRole + 2)

        if is_virtual:
            item.parent().removeChild(item)
        else:
            path = item.data(0, QtCore.Qt.UserRole)
            obj_type = "file" if is_file else "folder"
            reply = QtWidgets.QMessageBox.question(self, "Confirm Delete", 
                                                   f"Permanently delete this {obj_type} from your hard drive?\n\n{path}",
                                                   QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                try:
                    if is_file:
                        os.remove(path)
                    else:
                        shutil.rmtree(path)
                    item.parent().removeChild(item)
                    print(f"Deleted {obj_type}: {path}")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    # --- Preset Logic ---
    def load_presets(self):
        if os.path.exists(self.preset_file):
            try:
                with open(self.preset_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                cmds.warning(f"Could not load presets: {e}")
        return {}

    def save_presets_to_disk(self):
        try:
            with open(self.preset_file, 'w') as f:
                json.dump(self.presets, f, indent=4)
        except Exception as e:
            cmds.error(f"Failed to save presets: {e}")

    def populate_preset_combo(self):
        self.preset_combo.clear()
        self.preset_combo.addItem("--- Select Preset ---")
        for preset_name in sorted(self.presets.keys()):
            self.preset_combo.addItem(preset_name)

    def _tree_to_dict(self, item):
        result = {}
        for i in range(item.childCount()):
            child = item.child(i)
            if child.text(0) == "..." or child.data(0, QtCore.Qt.UserRole + 2):
                continue
            
            clean_name = child.text(0).replace("/", "").replace("\\", "").strip()
            result[clean_name] = self._tree_to_dict(child)
        return result

    def save_preset_action(self):
        selected = self.tree_widget.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a custom folder to save as a preset.")
            return

        parent_item = selected[0]

        if parent_item == self.root_item:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a specific folder you created inside the visualizer, not the Base Path.")
            return
            
        if parent_item.data(0, QtCore.Qt.UserRole + 2):
            QtWidgets.QMessageBox.warning(self, "Warning", "You cannot create a preset from a file. Select a folder.")
            return

        clean_parent_name = parent_item.text(0).replace("/", "").replace("\\", "").strip()
        structure = {clean_parent_name: self._tree_to_dict(parent_item)}

        name, ok = QtWidgets.QInputDialog.getText(self, "Save Preset", "Enter a name for this folder structure preset:")
        if ok and name.strip():
            name = name.strip()
            self.presets[name] = structure
            self.save_presets_to_disk()
            self.populate_preset_combo()
            
            index = self.preset_combo.findText(name)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
            cmds.confirmDialog(title="Success", message=f"Preset '{name}' saved successfully!")

    def _dict_to_tree(self, parent_item, data_dict):
        for folder_name, sub_dict in data_dict.items():
            folder_name = folder_name.replace("/", "").replace("\\", "").strip()
            
            existing_item = None
            for i in range(parent_item.childCount()):
                if parent_item.child(i).text(0) == folder_name and not parent_item.child(i).data(0, QtCore.Qt.UserRole + 2):
                    existing_item = parent_item.child(i)
                    break
            
            if existing_item:
                new_item = existing_item
            else:
                new_item = QtWidgets.QTreeWidgetItem([folder_name])
                new_item.setIcon(0, self.folder_icon)
                new_item.setFlags(new_item.flags() | QtCore.Qt.ItemIsEditable)
                new_item.setForeground(0, QtGui.QColor("#a5d6a7"))
                new_item.setData(0, QtCore.Qt.UserRole + 1, True)
                new_item.setData(0, QtCore.Qt.UserRole + 2, False)
                parent_item.addChild(new_item)
                
            self._dict_to_tree(new_item, sub_dict)

    def apply_preset_action(self):
        preset_name = self.preset_combo.currentText()
        if preset_name == "--- Select Preset ---" or preset_name not in self.presets:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please select a valid preset from the dropdown.")
            return

        selected = self.tree_widget.selectedItems()
        if not selected:
            if not self.root_item:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please set a Base Path or select a folder first.")
                return
            target_item = self.root_item
        else:
            target_item = selected[0]
            
        if target_item.data(0, QtCore.Qt.UserRole + 2):
            target_item = target_item.parent()

        target_item.setExpanded(True)
        self._dict_to_tree(target_item, self.presets[preset_name])

    # --- Standard File/Tree Logic ---
    def browse_base_path(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Base Directory")
        if directory:
            abs_dir = os.path.abspath(directory).replace("\\", "/")
            self.base_path_edit.setText(abs_dir)

    def update_tree_root(self):
        self.tree_widget.clear()
        self.root_item = None
        path = self.base_path_edit.text().strip()
        
        if path and os.path.isdir(path):
            abs_path = os.path.abspath(path).replace("\\", "/")
            self.root_item = QtWidgets.QTreeWidgetItem([abs_path])
            self.root_item.setIcon(0, self.folder_icon)
            self.root_item.setData(0, QtCore.Qt.UserRole, abs_path)
            self.root_item.setData(0, QtCore.Qt.UserRole + 1, False)
            self.root_item.setData(0, QtCore.Qt.UserRole + 2, False)
            
            self.tree_widget.addTopLevelItem(self.root_item)
            self.populate_tree(self.root_item, abs_path)
            self.root_item.setExpanded(True)

    def populate_tree(self, parent_item, path):
        try:
            with os.scandir(path) as it:
                entries = list(it)
                
            dirs = sorted([e for e in entries if e.is_dir()], key=lambda e: e.name)
            files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name)

            for d in dirs:
                full_path = d.path.replace("\\", "/")
                item = QtWidgets.QTreeWidgetItem([d.name])
                item.setIcon(0, self.folder_icon)
                item.setData(0, QtCore.Qt.UserRole, full_path)
                item.setData(0, QtCore.Qt.UserRole + 1, False)
                item.setData(0, QtCore.Qt.UserRole + 2, False)
                
                try:
                    with os.scandir(full_path) as sub_it:
                        if any(True for _ in sub_it):
                            item.addChild(QtWidgets.QTreeWidgetItem(["..."]))
                except PermissionError:
                    pass
                parent_item.addChild(item)

            for f in files:
                full_path = f.path.replace("\\", "/")
                item = QtWidgets.QTreeWidgetItem([f.name])
                item.setIcon(0, self.file_icon)
                item.setData(0, QtCore.Qt.UserRole, full_path)
                item.setData(0, QtCore.Qt.UserRole + 1, False)
                item.setData(0, QtCore.Qt.UserRole + 2, True)
                parent_item.addChild(item)

        except Exception:
            pass

    def on_item_expanded(self, item):
        is_virtual = item.data(0, QtCore.Qt.UserRole + 1)
        if is_virtual: return

        if item.childCount() > 0 and item.child(0).text(0) == "...":
            item.removeChild(item.child(0))
            path = item.data(0, QtCore.Qt.UserRole)
            self.populate_tree(item, path)

    def create_virtual_folder(self):
        selected = self.tree_widget.selectedItems()
        if not selected:
            if not self.root_item: return
            parent_item = self.root_item
        else:
            parent_item = selected[0]
            
        if parent_item.data(0, QtCore.Qt.UserRole + 2): 
            parent_item = parent_item.parent()

        if not parent_item.isExpanded():
            parent_item.setExpanded(True)
            
        new_item = QtWidgets.QTreeWidgetItem(["New Folder"])
        new_item.setIcon(0, self.folder_icon)
        new_item.setFlags(new_item.flags() | QtCore.Qt.ItemIsEditable)
        new_item.setForeground(0, QtGui.QColor("#a5d6a7"))
        new_item.setData(0, QtCore.Qt.UserRole + 1, True)
        new_item.setData(0, QtCore.Qt.UserRole + 2, False)
        
        parent_item.addChild(new_item)
        self.tree_widget.setCurrentItem(new_item)
        self.tree_widget.editItem(new_item, 0)

    def get_target_directory(self, item):
        parts = []
        current = item
        while current is not None:
            if current == self.root_item:
                break
            clean_name = current.text(0).replace("/", "").replace("\\", "").strip()
            parts.insert(0, clean_name)
            current = current.parent()
            
        base = self.base_path_edit.text().strip()
        base_abs = os.path.abspath(base).replace("\\", "/") if base else ""
        return os.path.join(base_abs, *parts).replace("\\", "/")

    def _commit_virtual_folders(self, parent_item, parent_path):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.text(0) == "..." or child.data(0, QtCore.Qt.UserRole + 2):
                continue
            
            folder_name = child.text(0).replace("/", "").replace("\\", "").strip()
            if not folder_name:
                folder_name = "Untitled_Folder"
                
            if child.text(0) != folder_name:
                child.setText(0, folder_name)

            current_path = os.path.join(parent_path, folder_name).replace("\\", "/")
            
            if child.data(0, QtCore.Qt.UserRole + 1):
                os.makedirs(current_path, exist_ok=True)
                child.setData(0, QtCore.Qt.UserRole + 1, False) 
                child.setData(0, QtCore.Qt.ForegroundRole, None) 
                child.setData(0, QtCore.Qt.UserRole, current_path) 
            
            self._commit_virtual_folders(child, current_path)

    def execute_action(self):
        source_file = self.source_file_edit.text().strip()
        has_file = False
        
        if source_file:
            if not os.path.isfile(source_file):
                cmds.warning("The provided source file path is invalid.")
                return
            has_file = True

        if not self.root_item:
            cmds.warning("Please set a base path first.")
            return

        base_path = os.path.abspath(self.base_path_edit.text().strip()).replace("\\", "/")

        try:
            # 1. Sweep and build ALL virtual folders safely
            self._commit_virtual_folders(self.root_item, base_path)

            # 2. Save File Logic
            if has_file:
                selected = self.tree_widget.selectedItems()
                sel_item = self.root_item
                if selected:
                    sel_item = selected[0]
                    if sel_item.data(0, QtCore.Qt.UserRole + 2): # if file, get parent
                        sel_item = sel_item.parent()
                
                target_dir = sel_item.data(0, QtCore.Qt.UserRole)
                if not target_dir:
                    target_dir = self.get_target_directory(sel_item) # Emergency fallback
                    
                os.makedirs(target_dir, exist_ok=True)

                filename = os.path.basename(source_file)
                target_file = os.path.join(target_dir, filename).replace("\\", "/")
                
                shutil.copy2(source_file, target_file)
                
                # Update UI Tree
                if sel_item.childCount() == 1 and sel_item.child(0).text(0) == "...":
                    sel_item.removeChild(sel_item.child(0))
                    
                for i in range(sel_item.childCount()):
                    if sel_item.child(i).text(0) == filename:
                        sel_item.removeChild(sel_item.child(i))
                        break
                        
                new_file_item = QtWidgets.QTreeWidgetItem([filename])
                new_file_item.setIcon(0, self.file_icon)
                new_file_item.setData(0, QtCore.Qt.UserRole, target_file)
                new_file_item.setData(0, QtCore.Qt.UserRole + 1, False)
                new_file_item.setData(0, QtCore.Qt.UserRole + 2, True) 
                
                sel_item.addChild(new_file_item)
                sel_item.setExpanded(True)
                
                # Silent Success Message (Fades in Maya UI)
                print(f"Success! Structure built and file saved: {target_file}")
                try:
                    cmds.inViewMessage(amg='<hl>Success:</hl> File Saved & Folders Built', pos='botCenter', fade=True)
                except:
                    pass
            else:
                # Silent Success Message for Folders Only
                print("Success! Folder structure built successfully.")
                try:
                    cmds.inViewMessage(amg='<hl>Success:</hl> Folder Structure Built', pos='botCenter', fade=True)
                except:
                    pass
                
        except Exception as e:
            cmds.error(f"An error occurred: {str(e)}")
            # Keeping the error pop-up just in case something breaks so you are warned!
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to process:\n{str(e)}")


# --- Launch Logic (Safely close duplicates) ---
def show_tool():
    global my_file_tool_window
    
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == "MyUniqueFileDirectoryTool_2025":
            widget.close()
            widget.deleteLater()
    
    maya_main_window = next((w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == 'MayaWindow'), None)
    
    my_file_tool_window = FileDirectoryTool(parent=maya_main_window)
    my_file_tool_window.show()

# --- Drag and Drop Logic for Maya ---
def onMayaDroppedPythonFile(*args, **kwargs):
    show_tool()

if __name__ == "__main__":
    show_tool()