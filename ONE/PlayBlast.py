import maya.cmds as cmds
import datetime
import os
import subprocess

class RigQCPlayblastTool:
    def __init__(self):
        self.window_name = "RigQCPlayblastUI"
        self.hud_names = ["QC_HUD_Date", "QC_HUD_Rig", "QC_HUD_Frame"]
        self.active_camera = None
        self.cam_original_settings = {}
        self.build_ui()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        cmds.window(self.window_name, title="Rig QC Playblast (FFmpeg)", widthHeight=(600, 220), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=12, columnAttach=('both', 10))

        cmds.separator(style='none', height=10)

        # Save Path
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2)
        cmds.text(label="Save Path:", align="right", width=70)
        self.path_field = cmds.textField(placeholderText="Click browse to set path...")
        cmds.button(label="Browse", command=self.browse_path, width=60)
        cmds.setParent('..')

        # Frame Range
        start_time = cmds.playbackOptions(query=True, minTime=True)
        end_time = cmds.playbackOptions(query=True, maxTime=True)
        self.frame_grp = cmds.intFieldGrp(numberOfFields=2, label='Frame Range:', value1=start_time, value2=end_time, columnWidth3=(70, 70, 70))

        # Resolution
        self.res_menu = cmds.optionMenu(label='Resolution:', width=150)
        cmds.menuItem(label='HD 720 (1280x720)')
        cmds.menuItem(label='HD 1080 (1920x1080)')
        cmds.menuItem(label='VGA (640x480)')
        cmds.menuItem(label='Square (1024x1024)')

        cmds.separator(style='in', height=15)

        cmds.button(label="Generate QC Playblast", height=40, backgroundColor=(0.25, 0.5, 0.35), command=self.execute_playblast)
        cmds.showWindow(self.window_name)

    def browse_path(self, *args):
        rig_name = self.get_top_node()
        if rig_name == "No_Rig_Found":
            rig_name = "Rig"
            
        # FIXED: Defaulting directly to .mp4
        default_file_name = rig_name + "_QC.mp4"
        
        scene_path = cmds.file(query=True, sceneName=True)
        if scene_path:
            base_dir = os.path.dirname(scene_path)
        else:
            base_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            
        start_path = os.path.join(base_dir, default_file_name).replace("\\", "/")

        # FIXED: Strictly MP4 filter
        filepath = cmds.fileDialog2(fileMode=0, dialogStyle=1, startingDirectory=start_path, fileFilter="MP4 Video (*.mp4)")
        
        if filepath:
            cmds.textField(self.path_field, edit=True, text=filepath[0])

    def get_top_node(self):
        selection = cmds.ls(selection=True, long=True)
        
        if selection:
            top_node = selection[0].split('|')[1]
        else:
            assemblies = cmds.ls(assemblies=True)
            defaults = ['persp', 'top', 'front', 'side']
            valid_nodes = [node for node in assemblies if node not in defaults]
            
            if valid_nodes:
                top_node = valid_nodes[0]
            else:
                return "No_Rig_Found"
                
        if ':' in top_node:
            top_node = top_node.split(':')[-1]
            
        return top_node

    def get_active_camera(self):
        pan = cmds.getPanel(withFocus=True)
        if cmds.getPanel(typeOf=pan) != 'modelPanel':
            panels = cmds.getPanel(visiblePanels=True)
            for p in panels:
                if cmds.getPanel(typeOf=p) == 'modelPanel':
                    pan = p
                    break
        
        if cmds.getPanel(typeOf=pan) == 'modelPanel':
            cam = cmds.modelEditor(pan, q=True, camera=True)
            if cmds.objectType(cam) == 'transform':
                return cmds.listRelatives(cam, shapes=True)[0]
            return cam
        return None

    def setup_huds(self):
        self.remove_huds() 

        if cmds.headsUpDisplay('HUDFrameRate', exists=True):
            self.cam_original_settings['fpsVis'] = cmds.headsUpDisplay('HUDFrameRate', q=True, vis=True)
            cmds.headsUpDisplay('HUDFrameRate', edit=True, vis=False)

        if cmds.headsUpDisplay('HUDViewAxis', exists=True):
            self.cam_original_settings['viewAxisVis'] = cmds.headsUpDisplay('HUDViewAxis', q=True, vis=True)
            cmds.headsUpDisplay('HUDViewAxis', edit=True, vis=False)

        def get_free_block(sec):
            return cmds.headsUpDisplay(nextFreeBlock=sec)

        today = datetime.datetime.today().strftime('%Y-%m-%d')
        cmds.headsUpDisplay(self.hud_names[0], section=0, block=get_free_block(0), blockSize='large', label="Date:", 
                            labelFontSize='large', dataFontSize='large', command=lambda *args: today, event="timeChanged")

        rig_name = self.get_top_node()
        cmds.headsUpDisplay(self.hud_names[1], section=2, block=get_free_block(2), blockSize='large', label="Rig:", 
                            labelFontSize='large', dataFontSize='large', command=lambda *args: rig_name, event="timeChanged")

        cmds.headsUpDisplay(self.hud_names[2], section=8, block=get_free_block(8), blockSize='large', label="Frame:", 
                            labelFontSize='large', dataFontSize='large', command='maya.cmds.currentTime(q=True)', attachToRefresh=True)

        self.active_camera = self.get_active_camera()
        if self.active_camera:
            self.cam_original_settings['displayResolution'] = cmds.getAttr(self.active_camera + ".displayResolution")
            self.cam_original_settings['displayGateMaskOpacity'] = cmds.getAttr(self.active_camera + ".displayGateMaskOpacity")
            self.cam_original_settings['displayGateMaskColor'] = cmds.getAttr(self.active_camera + ".displayGateMaskColor")[0]
            self.cam_original_settings['overscan'] = cmds.getAttr(self.active_camera + ".overscan")
            self.cam_original_settings['filmFit'] = cmds.getAttr(self.active_camera + ".filmFit")

            cmds.setAttr(self.active_camera + ".displayResolution", 1)
            cmds.setAttr(self.active_camera + ".displayGateMaskOpacity", 1.0)
            cmds.setAttr(self.active_camera + ".displayGateMaskColor", 0, 0, 0, type="double3")
            cmds.setAttr(self.active_camera + ".filmFit", 1) 
            cmds.setAttr(self.active_camera + ".overscan", 1.08) 

    def remove_huds(self):
        for hud in self.hud_names:
            if cmds.headsUpDisplay(hud, exists=True):
                cmds.headsUpDisplay(hud, remove=True)
                
        if 'fpsVis' in self.cam_original_settings and cmds.headsUpDisplay('HUDFrameRate', exists=True):
            cmds.headsUpDisplay('HUDFrameRate', edit=True, vis=self.cam_original_settings['fpsVis'])

        if 'viewAxisVis' in self.cam_original_settings and cmds.headsUpDisplay('HUDViewAxis', exists=True):
            cmds.headsUpDisplay('HUDViewAxis', edit=True, vis=self.cam_original_settings['viewAxisVis'])

        if self.active_camera and self.cam_original_settings:
            try:
                cmds.setAttr(self.active_camera + ".displayResolution", self.cam_original_settings['displayResolution'])
                cmds.setAttr(self.active_camera + ".displayGateMaskOpacity", self.cam_original_settings['displayGateMaskOpacity'])
                cmds.setAttr(self.active_camera + ".displayGateMaskColor", *self.cam_original_settings['displayGateMaskColor'], type="double3")
                cmds.setAttr(self.active_camera + ".overscan", self.cam_original_settings['overscan'])
                cmds.setAttr(self.active_camera + ".filmFit", self.cam_original_settings['filmFit'])
            except:
                pass

    def execute_playblast(self, *args):
        final_filepath = cmds.textField(self.path_field, query=True, text=True)
        if not final_filepath:
            cmds.warning("Please browse and specify a save path first.")
            return

        # Ensure the user has an .mp4 extension
        if not final_filepath.lower().endswith('.mp4'):
            final_filepath += ".mp4"

        # Create a temporary AVI path in the same directory
        temp_avi_path = final_filepath.replace('.mp4', '_temp.avi')

        start_f = cmds.intFieldGrp(self.frame_grp, query=True, value1=True)
        end_f = cmds.intFieldGrp(self.frame_grp, query=True, value2=True)
        res_str = cmds.optionMenu(self.res_menu, query=True, value=True)

        if '720' in res_str: width, height = 1280, 720
        elif '1080' in res_str: width, height = 1920, 1080
        elif 'VGA' in res_str: width, height = 640, 480
        else: width, height = 1024, 1024

        self.setup_huds()

        try:
            # STEP 1: Playblast raw/standard AVI. 
            # viewer=False is CRITICAL so Maya doesn't lock the file!
            cmds.playblast(filename=temp_avi_path, format='avi', startTime=start_f, endTime=end_f,
                           width=width, height=height, showOrnaments=True, percent=100, 
                           viewer=False, clearCache=True, forceOverwrite=True)
            
            # STEP 2: Convert to MP4 using FFmpeg
            cmds.inViewMessage(amg="<hl>Converting via FFmpeg...</hl>", pos='midCenter', fade=True)
            
            # Subprocess logic to hide the black command prompt window on Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # The FFmpeg command: High quality H.264 encode
            ffmpeg_cmd = [
                'ffmpeg', '-y', 
                '-i', temp_avi_path, 
                '-c:v', 'libx264', 
                '-preset', 'fast', 
                '-crf', '18', 
                '-pix_fmt', 'yuv420p', 
                final_filepath
            ]

            try:
                subprocess.check_call(ffmpeg_cmd, startupinfo=startupinfo)
                
                # STEP 3: Cleanup the temporary AVI
                if os.path.exists(temp_avi_path):
                    os.remove(temp_avi_path)
                    
                cmds.inViewMessage(amg="<hl>MP4 Playblast Complete!</hl>", pos='midCenter', fade=True)
                
                # Automatically open the video for the user
                if os.name == 'nt':
                    os.startfile(final_filepath)
                    
            except FileNotFoundError:
                cmds.warning("FFmpeg is not installed or not in your System PATH! Cannot convert to MP4. Leaving as AVI.")
                # Rename the temp avi to final path but with .avi extension
                fallback_avi = final_filepath.replace('.mp4', '.avi')
                os.rename(temp_avi_path, fallback_avi)
                if os.name == 'nt':
                    os.startfile(fallback_avi)
            except subprocess.CalledProcessError as e:
                cmds.warning("FFmpeg conversion failed. Error: {}".format(e))
                
        except Exception as e:
            cmds.warning("Playblast execution failed. Error: {}".format(e))
        finally:
            self.remove_huds()

RigQCPlayblastTool()