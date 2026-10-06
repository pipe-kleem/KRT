import os
import json
import shutil
import subprocess
import sys

try:
    from PySide2 import QtWidgets, QtCore
    import shiboken2 as shiboken
except ImportError:
    from PySide6 import QtWidgets, QtCore
    import shiboken6 as shiboken

import maya.cmds as cmds
import maya.OpenMayaUI as omui


def get_maya_main_window():
    """Find Maya's main window pointer to parent PySide widgets correctly."""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr:
        return shiboken.wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    return None


class DragDropLineEdit(QtWidgets.QLineEdit):
    """Custom QLineEdit that accepts Drag and Drop of Files or Folders."""
    file_dropped = QtCore.Signal(str)

    def __init__(self, is_folder=False, parent=None):
        super(DragDropLineEdit, self).__init__(parent)
        self.is_folder = is_folder
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            drop_path = os.path.normpath(urls[0].toLocalFile())
            
            if self.is_folder:
                if os.path.isfile(drop_path):
                    drop_path = os.path.dirname(drop_path)
                self.setText(drop_path)
                self.file_dropped.emit(drop_path)
            else:
                if os.path.isfile(drop_path):
                    self.setText(drop_path)
                    self.file_dropped.emit(drop_path)


class CopyWorker(QtCore.QThread):
    progress_signal = QtCore.Signal(int)
    status_signal = QtCore.Signal(str)
    # total, copied, missing, ignored
    finished_signal = QtCore.Signal(int, int, int, int) 
    error_signal = QtCore.Signal(str)

    def __init__(self, json_path, dest_root, package_name, ignore_rigutils):
        super(CopyWorker, self).__init__()
        self.json_path = json_path
        self.dest_root = dest_root
        self.package_name = package_name
        self.ignore_rigutils = ignore_rigutils
        self.final_target_dir = ""

    def run(self):
        try:
            # 1. Resolve Root Target Folder using rig_name / package_name
            self.final_target_dir = os.path.join(self.dest_root, self.package_name)
            os.makedirs(self.final_target_dir, exist_ok=True)

            # 2. Parse Original JSON
            with open(self.json_path, 'r') as f:
                json_data = json.load(f)

            # Extract file paths dynamically from JSON
            raw_file_paths = []
            def extract_paths_dynamically(obj):
                if isinstance(obj, str):
                    if ("/" in obj or "\\" in obj) and os.path.splitext(obj)[1]:
                        raw_file_paths.append(obj)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_paths_dynamically(item)
                elif isinstance(obj, dict):
                    for key, value in obj.items():
                        extract_paths_dynamically(value)

            extract_paths_dynamically(json_data)

            # 3. Filter existing files & RigUtils
            valid_paths = []
            ignored_count = 0
            missing_count = 0

            for p in raw_file_paths:
                norm_p = os.path.normpath(p)
                if os.path.isfile(norm_p):
                    # Check if 'RigUtils' is one of the folders in this path
                    path_parts = norm_p.replace("\\", "/").split("/")
                    if self.ignore_rigutils and "RigUtils" in path_parts:
                        ignored_count += 1
                        continue  # Skip copying this file
                    
                    valid_paths.append(norm_p)
                else:
                    missing_count += 1

            if not valid_paths and ignored_count == 0:
                self.error_signal.emit("No valid existing files found in the JSON file!")
                return

            total_files = len(valid_paths) + 1  # Assets + Updated JSON File
            copied_count = 0
            
            path_mapping = {}

            # 4. Copy Asset Files
            for idx, src_path in enumerate(valid_paths, start=1):
                file_name = os.path.basename(src_path)
                parent_folder_name = os.path.basename(os.path.dirname(src_path))
                
                self.status_signal.emit(f"Status: Copying ({idx}/{total_files}) - {file_name}")

                target_parent_dir = os.path.join(self.final_target_dir, parent_folder_name)
                target_path = os.path.join(target_parent_dir, file_name)

                os.makedirs(target_parent_dir, exist_ok=True)

                try:
                    shutil.copy2(src_path, target_path)
                    copied_count += 1
                    path_mapping[src_path] = os.path.normpath(target_path)
                except Exception as e:
                    print(f"Error copying {src_path}: {e}")

                self.progress_signal.emit(idx)

            # 5. Replace path strings in JSON recursively
            def replace_paths_in_json(obj):
                if isinstance(obj, str):
                    norm_str = os.path.normpath(obj)
                    if norm_str in path_mapping:
                        return path_mapping[norm_str].replace("\\", "/") # Standard slashes
                    return obj
                elif isinstance(obj, list):
                    return [replace_paths_in_json(item) for item in obj]
                elif isinstance(obj, dict):
                    return {key: replace_paths_in_json(val) for key, val in obj.items()}
                return obj

            updated_json_data = replace_paths_in_json(json_data)

            # 6. Create "Rig" subfolder & save updated JSON there
            rig_folder = os.path.join(self.final_target_dir, "Rig")
            os.makedirs(rig_folder, exist_ok=True)

            self.status_signal.emit("Status: Writing updated JSON to 'Rig' folder...")
            json_filename = os.path.basename(self.json_path)
            new_json_path = os.path.join(rig_folder, json_filename)

            with open(new_json_path, 'w') as f:
                json.dump(updated_json_data, f, indent=4)

            self.progress_signal.emit(total_files)
            self.finished_signal.emit(total_files, copied_count, missing_count, ignored_count)

        except Exception as e:
            self.error_signal.emit(str(e))


class JSONFolderCollector(QtWidgets.QDialog):
    def __init__(self, parent=get_maya_main_window()):
        super(JSONFolderCollector, self).__init__(parent)
        self.setWindowTitle("JSON Asset Collector")
        self.resize(550, 320)
        
        self.setWindowFlags(QtCore.Qt.Window)

        self.last_target_dir = ""
        self.worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Select JSON File (Drag & Drop)
        json_layout = QtWidgets.QHBoxLayout()
        self.json_input = DragDropLineEdit(is_folder=False)
        self.json_input.setPlaceholderText("Select or Drag & Drop JSON File Here...")
        self.json_input.file_dropped.connect(self.auto_read_rig_name)
        json_btn = QtWidgets.QPushButton("Browse JSON")
        json_btn.clicked.connect(self.browse_json)

        json_layout.addWidget(self.json_input)
        json_layout.addWidget(json_btn)
        layout.addLayout(json_layout)

        # 2. Target Base Folder (Drag & Drop)
        dest_layout = QtWidgets.QHBoxLayout()
        self.dest_input = DragDropLineEdit(is_folder=True)
        self.dest_input.setPlaceholderText("Select or Drag & Drop Destination Folder Here...")
        dest_btn = QtWidgets.QPushButton("Browse Folder")
        dest_btn.clicked.connect(self.browse_dest)

        dest_layout.addWidget(self.dest_input)
        dest_layout.addWidget(dest_btn)
        layout.addLayout(dest_layout)

        # 3. New Output Package Name
        folder_layout = QtWidgets.QHBoxLayout()
        folder_label = QtWidgets.QLabel("Package Name (from rig_name):")
        self.subfolder_input = QtWidgets.QLineEdit()
        self.subfolder_input.setPlaceholderText("e.g. ravana_a_Rig")

        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.subfolder_input)
        layout.addLayout(folder_layout)

        # 4. Checkbox Option for RigUtils
        self.ignore_rigutils_cb = QtWidgets.QCheckBox("Ignore 'RigUtils' folder (Keep original server paths)")
        self.ignore_rigutils_cb.setChecked(True) # Checked by default
        layout.addWidget(self.ignore_rigutils_cb)

        # 5. Progress Bar & Status Text
        self.status_label = QtWidgets.QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        # Action Buttons Layout
        btn_layout = QtWidgets.QHBoxLayout()

        self.process_btn = QtWidgets.QPushButton("Copy JSON & Collect Assets")
        self.process_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.process_btn.clicked.connect(self.start_collection)

        self.reveal_btn = QtWidgets.QPushButton("Reveal Output Folder")
        self.reveal_btn.setStyleSheet("background-color: #4A4A4A; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self.reveal_folder)

        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.reveal_btn)
        layout.addLayout(btn_layout)

    def browse_json(self):
        json_file, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select JSON File", "", "JSON Files (*.json)")
        if json_file:
            self.json_input.setText(json_file)
            self.auto_read_rig_name(json_file)

    def auto_read_rig_name(self, json_path):
        try:
            if not os.path.exists(json_path):
                return
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            rig_name = data.get("rig_name")
            if rig_name:
                self.subfolder_input.setText(str(rig_name))
        except Exception as e:
            print(f"Could not read rig_name from JSON: {e}")

    def browse_dest(self):
        selected_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if selected_folder:
            self.dest_input.setText(selected_folder)

    def reveal_folder(self):
        if self.last_target_dir and os.path.exists(self.last_target_dir):
            path = os.path.normpath(self.last_target_dir)
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

    def start_collection(self):
        json_path = self.json_input.text().strip()
        dest_root = self.dest_input.text().strip()
        package_name = self.subfolder_input.text().strip()
        ignore_rigutils = self.ignore_rigutils_cb.isChecked()

        if not json_path or not os.path.exists(json_path):
            cmds.confirmDialog(title="Error", message="Please select or drag a valid JSON file!", button=["OK"])
            return

        if not dest_root or not os.path.isdir(dest_root):
            cmds.confirmDialog(title="Error", message="Please select or drag a valid destination folder!", button=["OK"])
            return

        if not package_name:
            package_name = "Collected_Rig_Package"

        self.process_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(0)

        self.worker = CopyWorker(json_path, dest_root, package_name, ignore_rigutils)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.status_signal.connect(self.update_status)
        self.worker.finished_signal.connect(self.collection_finished)
        self.worker.error_signal.connect(self.collection_error)
        
        self.worker.start()

    def update_progress(self, val):
        self.progress_bar.setValue(val)

    def update_status(self, text):
        self.status_label.setText(text)

    def collection_finished(self, total, copied, missing, ignored):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(total)
        self.status_label.setText("Status: Copying Completed!")
        
        self.process_btn.setEnabled(True)
        self.reveal_btn.setEnabled(True)
        self.last_target_dir = self.worker.final_target_dir

        cmds.confirmDialog(
            title="Success",
            message=f"Assets collected successfully!\n\nLocation: {self.last_target_dir}\n\n• JSON Paths Updated: Yes\n• Files Copied: {copied}\n• RigUtils Files Ignored: {ignored}\n• Missing Files Skipped: {missing}",
            button=["OK"]
        )

    def collection_error(self, err_msg):
        self.status_label.setText("Status: Error encountered.")
        self.process_btn.setEnabled(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        cmds.confirmDialog(title="Error", message=f"An error occurred:\n{err_msg}", button=["OK"])


# Launch Tool
dialog = JSONFolderCollector()
dialog.show()