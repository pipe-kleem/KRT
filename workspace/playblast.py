"""SessionWorkspace - playblast methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspacePlayblastMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    # =====================================================
    # Playblast review (Stage 17): create a playblast (with a given camera,
    # or an auto-built one framing a group's bounding box if no camera is
    # given), and play it back right here via an embedded video player.
    #
    # The "animation JSON" field/pattern are wired up and saved but the
    # actual apply-animation step is a placeholder (see create_playblast) -
    # it needs a sample of the user's actual anim-JSON format before it can
    # do anything real with it.
    # =====================================================

    def get_playblast_dir(self):
        """Where playblasts land: a 'playblasts' subfolder next to the
        current session's own KRT json (same auto-pathed-beside-the-json
        convention as the Guide Path field and step caches), or the user's
        home folder if this session hasn't been saved anywhere yet."""
        # Stage 46: prefer <Rig Root>/playblasts - that folder is part of the
        # project structure Initialize Project creates, so QC media sits with
        # the rig instead of beside whichever json happened to be open.
        root = self.rig_root()
        if root and os.path.isdir(root):
            base_dir = root
        else:
            base_dir = os.path.dirname(self.session_path) if self.session_path else os.path.expanduser("~")
        d = os.path.join(base_dir, "playblasts").replace("\\", "/")
        if not os.path.exists(d):
            try:
                os.makedirs(d)
            except Exception:
                pass
        return d

    def create_auto_camera_from_group(self, group):
        """No camera given - build one that frames `group`'s bounding box.
        Creates a temporary camera, points it at the group's center from
        far enough away (based on the bbox diagonal and the camera's own
        field of view, plus some padding) to fit the whole thing in frame,
        aimed via a throwaway aimConstraint. The caller is responsible for
        deleting this camera once the playblast is done."""
        if not group or not cmds.objExists(group):
            return None
        try:
            bbox = cmds.exactWorldBoundingBox(group)
        except Exception:
            bbox = cmds.xform(group, query=True, boundingBox=True, worldSpace=True)
        cx, cy, cz = (bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0, (bbox[2] + bbox[5]) / 2.0
        sx, sy, sz = bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]
        diag = (sx * sx + sy * sy + sz * sz) ** 0.5
        if diag <= 0.0001:
            diag = 10.0

        cam_tfm, _cam_shape = cmds.camera()
        cam_tfm = cmds.rename(cam_tfm, "KRT_playblast_cam#")
        hfov = cmds.camera(cam_tfm, query=True, horizontalFieldOfView=True) or 54.4
        distance = (diag * 0.7) / max(0.01, math.tan(math.radians(hfov / 2.0)))
        distance = max(distance, diag)

        cmds.setAttr(cam_tfm + ".translate", cx, cy, cz + distance, type="double3")
        aim = cmds.aimConstraint(group, cam_tfm, aimVector=(0, 0, -1), upVector=(0, 1, 0),
                                  worldUpType="vector", worldUpVector=(0, 1, 0))
        cmds.delete(aim)
        return cam_tfm

    # ------------------------------------------------------------------
    # Generate Camera (Stage 38): a second, fully manual way to get a
    # camera to playblast through when there's no existing one - full
    # control over position plus the same lens settings the Attribute
    # Editor's Camera Shape tab shows, instead of only the automatic
    # frame-a-group's-bounding-box option above.
    # ------------------------------------------------------------------
    def pb_compute_angle_of_view(self, focal_length, horizontal_film_aperture_mm=36.0):
        """Angle of View (degrees) for a given focal length (mm), assuming
        Maya's default 36mm (1.41732in) horizontal film aperture - the
        same relationship the Attribute Editor's Camera Shape tab keeps
        Angle of View synced to Focal Length with. Returns None for a
        non-positive focal length (can't compute, avoid a ZeroDivisionError)."""
        try:
            focal_length = float(focal_length)
        except (TypeError, ValueError):
            return None
        if focal_length <= 0:
            return None
        return 2.0 * math.degrees(math.atan(horizontal_film_aperture_mm / (2.0 * focal_length)))

    def pb_update_gen_camera_aov(self, *_args):
        """Wired to the Focal Length field's textChanged - keeps the
        read-only Angle of View field in sync, live, the same way Maya's
        own Camera Shape tab keeps the two in sync with each other."""
        if not hasattr(self, "pb_gen_aov_display"):
            return
        aov = self.pb_compute_angle_of_view(self.pb_gen_focal_length.text().strip())
        self.pb_gen_aov_display.setText("{:.2f}".format(aov) if aov is not None else "")

    def pb_generate_camera(self, pos_x, pos_y, pos_z, focal_length, camera_scale,
                            near_clip, far_clip, auto_render_clip_planes,
                            rot_x=0.0, rot_y=0.0, rot_z=0.0):
        """Creates a camera at the given position/rotation with the given
        lens settings (all straight off the Generate Camera UI's fields)
        and returns its transform name. rot_x/y/z default to 0 (looking
        down -Z, same as a plain new Maya camera) when not given, so
        existing callers keep working unchanged."""
        cam_tfm, cam_shape = cmds.camera()
        cam_tfm = cmds.rename(cam_tfm, "KRT_generated_cam#")
        cam_shape = (cmds.listRelatives(cam_tfm, shapes=True, fullPath=True) or [cam_shape])[0]

        cmds.setAttr(cam_tfm + ".translate", float(pos_x), float(pos_y), float(pos_z), type="double3")
        cmds.setAttr(cam_tfm + ".rotate", float(rot_x), float(rot_y), float(rot_z), type="double3")
        cmds.setAttr(cam_shape + ".focalLength", float(focal_length))
        cmds.setAttr(cam_shape + ".cameraScale", float(camera_scale))
        cmds.setAttr(cam_shape + ".nearClipPlane", float(near_clip))
        cmds.setAttr(cam_shape + ".farClipPlane", float(far_clip))
        if cmds.attributeQuery("autoRenderClipPlanes", node=cam_shape, exists=True):
            cmds.setAttr(cam_shape + ".autoRenderClipPlanes", bool(auto_render_clip_planes))

        return cam_tfm

    def pb_generate_camera_clicked(self):
        try:
            pos_x = float(self.pb_gen_pos_x.text().strip() or 0)
            pos_y = float(self.pb_gen_pos_y.text().strip() or 0)
            pos_z = float(self.pb_gen_pos_z.text().strip() or 0)
            rot_x = float(self.pb_gen_rot_x.text().strip() or 0) if hasattr(self, "pb_gen_rot_x") else 0.0
            rot_y = float(self.pb_gen_rot_y.text().strip() or 0) if hasattr(self, "pb_gen_rot_y") else 0.0
            rot_z = float(self.pb_gen_rot_z.text().strip() or 0) if hasattr(self, "pb_gen_rot_z") else 0.0
            focal_length = float(self.pb_gen_focal_length.text().strip() or 35.0)
            camera_scale = float(self.pb_gen_camera_scale.text().strip() or 1.0)
            near_clip = float(self.pb_gen_near_clip.text().strip() or 0.1)
            far_clip = float(self.pb_gen_far_clip.text().strip() or 10000.0)
        except ValueError:
            cmds.warning("[KRT] Generate Camera: one of the fields isn't a valid number.")
            return

        if near_clip <= 0:
            cmds.warning("[KRT] Generate Camera: Near Clip Plane must be greater than zero.")
            return
        if far_clip <= near_clip:
            cmds.warning("[KRT] Generate Camera: Far Clip Plane must be greater than Near Clip Plane.")
            return

        try:
            cam_tfm = self.pb_generate_camera(
                pos_x, pos_y, pos_z, focal_length, camera_scale, near_clip, far_clip,
                self.pb_gen_auto_clip_chk.isChecked(), rot_x=rot_x, rot_y=rot_y, rot_z=rot_z)
        except Exception as e:
            log_crash("Generate Camera", e)
            cmds.warning("[KRT] Generate Camera failed: {}".format(e))
            return

        self.pb_camera_field.setText(cam_tfm)
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Generated camera: {}".format(cam_tfm))
        # Request #1: the live camera-view screen should immediately show
        # the newly generated camera, not stay pointed at whatever it had
        # before (or nothing).
        self.pb_set_live_view_camera(cam_tfm)

    # ------------------------------------------------------------------
    # Playblast QC helpers (Stage 36): ported from the studio's standalone
    # "Mahavatar Parshuram QC Playblast" script into KRT's own embedded
    # Playblast tab. Everything below is pure/self-contained (no Qt), so
    # it can run - and be stub-tested - without a UI. See create_playblast()
    # for how these get wired together.
    # ------------------------------------------------------------------
    def pb_clean_display_name(self, value):
        value = re.sub(r"[_\-.]+", " ", value or "")
        value = re.sub(r"\s+", " ", value).strip()
        return value.title() if value else ""

    def pb_is_version_or_task_token(self, token):
        token = (token or "").lower()
        exact_task_tokens = {
            "qc", "rig", "model", "mod", "texture", "tex", "lookdev",
            "look", "anim", "animation", "layout", "blocking",
            "publish", "playblast", "final", "wip", "scene", "shot",
            "asset", "ma", "mb"
        }
        if token in exact_task_tokens:
            return True
        patterns = (
            r"v\d+", r"ver\d+", r"version\d+", r"rev\d+", r"r\d+",
            r"take\d+", r"tk\d+", r"wip\d*", r"final\d*",
            r"\d{3,4}to\d{3,4}", r"\d{3,4}-\d{3,4}", r"\d{6,8}"
        )
        return any(re.fullmatch(pattern, token) for pattern in patterns)

    def pb_parse_artist_from_filename(self, scene_stem):
        tokens = [t for t in re.split(r"[_\-.]+", scene_stem or "") if t]
        lower_tokens = [t.lower() for t in tokens]
        for marker in ("artist", "by"):
            if marker in lower_tokens:
                idx = lower_tokens.index(marker)
                if idx + 1 < len(tokens):
                    return self.pb_clean_display_name(tokens[idx + 1])
        return self.pb_clean_display_name(getpass.getuser())

    def pb_parse_character_from_filename(self, scene_stem, project_name=""):
        """Same heuristic as the studio script's parse_character_from_filename,
        generalized for KRT's multi-project pipeline: instead of a
        hardcoded project-name ignore-list, the CURRENT project name's own
        words are ignored (so "CHR_Jamadagni_v003.ma" under project "Mahavatar
        Parshuram" doesn't mistake "Mahavatar"/"Parshuram" for the
        character on some other show's scene)."""
        tokens = [t for t in re.split(r"[_\-.]+", scene_stem or "") if t]
        lower_tokens = [t.lower() for t in tokens]

        for marker in ("character", "char", "chr"):
            if marker in lower_tokens:
                index = lower_tokens.index(marker) + 1
                character_tokens = []
                for token in tokens[index:]:
                    lower = token.lower()
                    if lower in ("artist", "by"):
                        break
                    if self.pb_is_version_or_task_token(lower):
                        break
                    character_tokens.append(token)
                    if len(character_tokens) >= 3:
                        break
                if character_tokens:
                    return self.pb_clean_display_name(" ".join(character_tokens))

        project_words = set(re.split(r"[_\-.\s]+", (project_name or "").lower()))
        ignored_tokens = {"project", "artist", "by"} | project_words
        ignored_tokens.discard("")

        candidate_tokens = []
        for token in tokens:
            lower = token.lower()
            if lower in ignored_tokens:
                continue
            if self.pb_is_version_or_task_token(lower):
                continue
            if re.fullmatch(r"\d+", lower):
                continue
            candidate_tokens.append(token)

        if candidate_tokens:
            return self.pb_clean_display_name(" ".join(candidate_tokens[:3]))
        return "Character"

    def pb_get_scene_fps(self):
        time_unit = cmds.currentUnit(query=True, time=True)
        standard_units = {
            "game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0,
            "show": 48.0, "palf": 50.0, "ntscf": 60.0
        }
        if time_unit in standard_units:
            return standard_units[time_unit]
        match = re.match(r"([0-9]+(?:\.[0-9]+)?)fps$", time_unit)
        if match:
            return float(match.group(1))
        return 24.0

    def pb_format_fps(self, fps):
        if abs(float(fps) - round(float(fps))) < 0.0001:
            return str(int(round(float(fps))))
        return "{:.3f}".format(float(fps)).rstrip("0").rstrip(".")

    def pb_detect_ffmpeg(self):
        """No hardcoded studio machine path (the source script's own
        C:\\ffmpeg\\ffmpeg.exe default) - checks the system PATH first,
        then falls back to the same common Windows install locations.
        Returns None (not a guessed, possibly-nonexistent path) if
        nothing is actually found, so callers can cleanly fall back to
        the native (non-MP4) playblast path instead of crashing on a
        missing exe."""
        found = shutil.which("ffmpeg")
        if found:
            return found.replace("\\", "/")
        common_paths = [
            r"C:\ffmpeg\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path
        return None

    def pb_get_font_path(self):
        font_paths = (
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arial.ttf"
        )
        for font_path in font_paths:
            if os.path.isfile(font_path):
                return font_path
        return ""

    def pb_escape_ffmpeg_filter_path(self, path):
        return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

    def pb_create_metadata_file(self, output_root, project_name, character_name,
                                 artist_name, start_frame, end_frame, fps):
        metadata_path = output_root + "_metadata.txt"
        metadata_text = (
            "PROJECT: {}    |    CHARACTER: {}    |    ARTIST: {}    |    "
            "FRAME RANGE: {} - {}    |    FPS: {}"
        ).format(project_name, character_name, artist_name, start_frame, end_frame,
                  self.pb_format_fps(fps))
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(metadata_text)
        return metadata_path, metadata_text

    def pb_build_metadata_filter(self, width, height, metadata_path, metadata_text,
                                  start_frame):
        # Keep enough room on the right for the live frame counter.
        available_left_width = width * 0.79
        estimated_font_from_width = int(available_left_width / max(len(metadata_text) * 0.55, 1))
        preferred_font = int(height * 0.026)
        font_size = max(16, min(preferred_font, estimated_font_from_width))
        strip_height = max(54, int(font_size * 2.45))
        if strip_height % 2:
            strip_height += 1
        horizontal_padding = max(18, int(width * 0.012))
        text_y = height + max(5, int((strip_height - font_size) * 0.40))
        metadata_path_filter = self.pb_escape_ffmpeg_filter_path(metadata_path)

        font_path = self.pb_get_font_path()
        font_option = "fontfile='{}':".format(self.pb_escape_ffmpeg_filter_path(font_path)) if font_path else ""

        filters = [
            "pad=iw:ih+{}:0:0:color=black".format(strip_height),
            "drawbox=x=0:y={}:w=iw:h={}:color=0xE9ECEC@0.96:t=fill".format(height, strip_height),
            "drawtext={}textfile='{}':fontcolor=black@0.98:fontsize={}:x={}:y={}".format(
                font_option, metadata_path_filter, font_size, horizontal_padding, text_y),
            "drawtext={}text='FRAME\\: %{{frame_num}}':start_number={}:"
            "fontcolor=black@0.98:fontsize={}:x=w-tw-{}:y={}".format(
                font_option, int(start_frame), font_size, horizontal_padding, text_y),
        ]
        return ",".join(filters)

    def pb_hide_all_huds(self):
        self.pb_hud_original_visibility = {}
        huds = cmds.headsUpDisplay(listHeadsUpDisplays=True) or []
        for hud in huds:
            try:
                visible = bool(cmds.headsUpDisplay(hud, query=True, visible=True))
                self.pb_hud_original_visibility[hud] = visible
                if visible:
                    cmds.headsUpDisplay(hud, edit=True, visible=False)
            except Exception:
                pass

    def pb_restore_all_huds(self):
        for hud, visible in self.pb_hud_original_visibility.items():
            if not cmds.headsUpDisplay(hud, exists=True):
                continue
            try:
                cmds.headsUpDisplay(hud, edit=True, visible=visible)
            except Exception:
                pass
        self.pb_hud_original_visibility = {}

    def pb_hide_camera_gates(self, camera_shape_or_transform):
        """Hides film/resolution gate, safe action/title, field chart and
        gate mask on whichever camera the playblast is actually shooting
        through (the same `cam` create_playblast() already resolved -
        NOT necessarily the active viewport camera)."""
        self.pb_gate_camera = None
        self.pb_gate_original_values = {}
        cam = camera_shape_or_transform
        if not cam or not cmds.objExists(cam):
            return
        if cmds.nodeType(cam) == "transform":
            shapes = cmds.listRelatives(cam, shapes=True, fullPath=True, type="camera") or []
            cam = shapes[0] if shapes else None
        if not cam:
            return
        self.pb_gate_camera = cam

        gate_attributes = (
            "displayFilmGate", "displayResolution", "displaySafeAction",
            "displaySafeTitle", "displayFieldChart", "displayGateMask",
            "displayFilmOrigin", "displayFilmPivot"
        )
        for attribute in gate_attributes:
            if not cmds.attributeQuery(attribute, node=cam, exists=True):
                continue
            plug = "{}.{}".format(cam, attribute)
            try:
                self.pb_gate_original_values[attribute] = cmds.getAttr(plug)
                cmds.setAttr(plug, 0)
            except Exception:
                pass

    def pb_restore_camera_gates(self):
        if not self.pb_gate_camera or not cmds.objExists(self.pb_gate_camera):
            self.pb_gate_camera = None
            self.pb_gate_original_values = {}
            return
        for attribute, original_value in self.pb_gate_original_values.items():
            try:
                cmds.setAttr("{}.{}".format(self.pb_gate_camera, attribute), original_value)
            except Exception:
                pass
        self.pb_gate_camera = None
        self.pb_gate_original_values = {}

    def pb_run_ffmpeg_encode(self, ffmpeg_path, frames_dir, expected_frame_count,
                              fps, metadata_filter, final_mp4_path):
        """Encodes the exact captured JPG sequence (frame_%06d.jpg, 0-based,
        in `frames_dir`) into the final H.264 MP4 with the metadata filter
        chain burned in. Returns (success, error_message)."""
        ffmpeg_input_pattern = os.path.join(frames_dir, "frame_%06d.jpg").replace("\\", "/")

        startup_info = None
        creation_flags = 0
        if os.name == "nt":
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        ffmpeg_command = [
            ffmpeg_path, "-y",
            "-framerate", self.pb_format_fps(fps),
            "-start_number", "0",
            "-i", ffmpeg_input_pattern,
            "-frames:v", str(expected_frame_count),
            "-vf", metadata_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            final_mp4_path
        ]

        process = subprocess.run(
            ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, startupinfo=startup_info, creationflags=creation_flags
        )

        if process.returncode != 0:
            error = process.stderr[-6000:] if process.stderr else "Unknown FFmpeg error."
            return False, "FFmpeg could not create the final MP4.\n\n{}".format(error)
        if not os.path.isfile(final_mp4_path):
            return False, "FFmpeg finished, but the final MP4 was not created:\n{}".format(final_mp4_path)
        return True, ""

    # ------------------------------------------------------------------
    # Studio Library animation clip loading (Stage 37): the Playblast
    # tab's "Animation (.anim)" field loads a Studio Library clip straight
    # onto whatever controls match the Controls Filter, reusing Studio
    # Library's OWN animation-curve transfer code (the "mutils" package,
    # from the studio's shared install at DEFAULT_STUDIOLIBRARY_SRC_PATH)
    # rather than KRT re-implementing curve pasting/matching from scratch.
    # ------------------------------------------------------------------
    def pb_ensure_studiolibrary(self):
        """Makes Studio Library's "mutils" package importable. Tries a
        plain import first (already on sys.path via some other tool this
        session); falls back to the studio's shared network install (or
        the KRT_STUDIOLIBRARY_SRC env var, if someone's install lives
        somewhere else). Returns the imported `mutils` module, or None
        if it truly isn't reachable."""
        try:
            import mutils
            return mutils
        except ImportError:
            pass

        for candidate in (os.environ.get("KRT_STUDIOLIBRARY_SRC", ""), DEFAULT_STUDIOLIBRARY_SRC_PATH):
            if candidate and os.path.isdir(candidate) and candidate not in sys.path:
                sys.path.insert(0, candidate)

        try:
            import mutils
            return mutils
        except ImportError:
            return None

    def pb_is_studiolibrary_anim_path(self, path):
        """True if `path` looks like a Studio Library .anim item - a
        FOLDER (not a single file) ending in .anim, containing pose.json
        and an animation.ma/.mb - matching mutils.Animation's own
        mayaPath()/poseJsonPath() layout."""
        if not path:
            return False
        path = path.rstrip("/\\")
        if not path.lower().endswith(".anim"):
            return False
        if not os.path.isdir(path):
            return False
        if not os.path.isfile(os.path.join(path, "pose.json")):
            return False
        return (os.path.isfile(os.path.join(path, "animation.ma")) or
                os.path.isfile(os.path.join(path, "animation.mb")))

    def pb_get_anim_frame_range(self, anim_path):
        """(startFrame, endFrame) stored in a Studio Library .anim clip's
        own pose.json metadata, or (None, None) if unavailable. Used to
        auto-fill the Start/End fields when Browse picks a clip, so the
        Playblast's capture range matches the clip by default."""
        mutils_mod = self.pb_ensure_studiolibrary()
        if not mutils_mod:
            return None, None
        try:
            anim = mutils_mod.Animation.fromPath(anim_path)
            return anim.startFrame(), anim.endFrame()
        except Exception:
            return None, None

    def pb_load_anim_on_filtered_controls(self, anim_path, ctl_pattern, start_frame=None):
        """Loads a Studio Library .anim clip's animation curves onto
        whatever controls in the CURRENT scene match `ctl_pattern` (the
        Playblast tab's existing Controls Filter field, e.g. "*_ctl") -
        the actual feature: load the clip straight onto the filtered rig
        controls instead of requiring a plain baked-value JSON.
        `start_frame`, if given, shifts the clip so its first frame lands
        there (mutils.Animation.load's own startFrame semantics);
        left as None, the clip loads at its own original frame numbers.

        Returns (success, error_msg, matched_control_count)."""
        mutils_mod = self.pb_ensure_studiolibrary()
        if not mutils_mod:
            return False, (
                "Studio Library's 'mutils' package could not be found/imported "
                "(checked sys.path, then {}). Animation clip loading needs "
                "it.".format(DEFAULT_STUDIOLIBRARY_SRC_PATH)), 0

        if not self.pb_is_studiolibrary_anim_path(anim_path):
            return False, (
                "'{}' doesn't look like a Studio Library .anim item - expected "
                "a folder ending in .anim containing pose.json and "
                "animation.ma/.mb.".format(anim_path)), 0

        pattern = (ctl_pattern or "*").strip() or "*"
        matched = cmds.ls(pattern, type="transform") or []
        if not matched:
            return False, "No controls in the scene match the filter '{}'.".format(pattern), 0

        try:
            anim = mutils_mod.Animation.fromPath(anim_path)
            anim.load(
                objects=matched,
                option="replace all",
                startFrame=start_frame,
                currentTime=False,
            )
            return True, "", len(matched)
        except Exception as e:
            log_crash("Load Studio Library animation", e)
            return False, str(e), 0

    def create_playblast(self, camera_name, group_name, anim_json_path, ctl_pattern,
                          start_frame=None, end_frame=None, width=None, height=None,
                          fps=None, project_name="", character_name="", artist_name="",
                          output_path_override=None):
        """Returns (success, error_msg, output_path).

        Stage 36: when FFmpeg is available, this now does what the studio's
        standalone QC Playblast script does - hides HUDs/camera gates,
        captures an exact-frame-count JPG sequence, and encodes it to an
        H.264 MP4 with a burned-in metadata strip (project/character/
        artist/frame range/fps) and a live per-frame counter. When FFmpeg
        can't be found, it falls back to KRT's original native
        cmds.playblast QuickTime capture (still with HUDs/gates hidden),
        so the tool keeps working either way."""
        created_cam = None
        out_dir = self.get_playblast_dir()
        temporary_sequence_dir = None
        metadata_path = None
        conversion_succeeded = False
        try:
            cam = (camera_name or "").strip()
            if cam and not cmds.objExists(cam):
                cmds.warning("[KRT] Camera '{}' not found - falling back to a bounding-box camera.".format(cam))
                cam = ""

            if not cam:
                group = (group_name or "").strip()
                if not group or not cmds.objExists(group):
                    return False, "No valid camera given, and no valid group to build one from.", None
                cam = self.create_auto_camera_from_group(group)
                if not cam:
                    return False, "Could not build a camera from '{}'.".format(group), None
                created_cam = cam

            # Stage 37: load a Studio Library .anim clip onto whatever
            # controls match ctl_pattern, before capturing - see
            # pb_load_anim_on_filtered_controls(). A bad/missing clip
            # aborts the playblast entirely (rather than silently
            # capturing the scene's un-animated current state), since
            # the whole point of this run was to review that animation.
            if anim_json_path and anim_json_path.strip():
                ok_anim, anim_err, matched_count = self.pb_load_anim_on_filtered_controls(
                    anim_json_path.strip(), ctl_pattern, start_frame=start_frame)
                if not ok_anim:
                    return False, "Could not load animation clip: {}".format(anim_err), None
                cmds.warning(
                    "[KRT] Loaded animation clip onto {} matching control(s) "
                    "(filter: '{}').".format(matched_count, ctl_pattern or "*"))

            cmds.lookThru(cam)

            ts = time.strftime("%Y%m%d_%H%M%S")
            ffmpeg_path = self.pb_detect_ffmpeg()

            self.pb_hide_all_huds()
            self.pb_hide_camera_gates(cam)
            cmds.refresh(force=True)

            if ffmpeg_path:
                # ---- QC MP4 pipeline (FFmpeg found) --------------------
                if output_path_override and output_path_override.strip():
                    out_path = output_path_override.strip().replace("\\", "/")
                    if not out_path.lower().endswith(".mp4"):
                        out_path += ".mp4"
                    override_dir = os.path.dirname(out_path)
                    if override_dir and not os.path.isdir(override_dir):
                        os.makedirs(override_dir)
                else:
                    out_path = os.path.join(out_dir, "playblast_{}.mp4".format(ts)).replace("\\", "/")
                output_root = os.path.splitext(out_path)[0]

                effective_start = int(start_frame) if start_frame is not None else int(cmds.playbackOptions(query=True, minTime=True))
                effective_end = int(end_frame) if end_frame is not None else int(cmds.playbackOptions(query=True, maxTime=True))
                effective_fps = float(fps) if fps else self.pb_get_scene_fps()
                expected_frame_count = (effective_end - effective_start) + 1
                if expected_frame_count <= 0:
                    return False, "Start frame must be lower than or equal to end frame.", None

                w = int(width) if width else 1920
                h = int(height) if height else 1080

                temporary_sequence_dir = tempfile.mkdtemp(prefix="KRT_qc_frames_").replace("\\", "/")
                maya_sequence_prefix = os.path.join(temporary_sequence_dir, "maya_capture").replace("\\", "/")

                cmds.playblast(
                    filename=maya_sequence_prefix, format="image", compression="jpg",
                    quality=100, startTime=effective_start, endTime=effective_end,
                    framePadding=6, width=w, height=h, showOrnaments=False,
                    percent=100, viewer=False, clearCache=True, forceOverwrite=True,
                    offScreen=True
                )

                generated_frames = []
                for filename in os.listdir(temporary_sequence_dir):
                    if filename.lower().endswith((".jpg", ".jpeg")):
                        generated_frames.append(os.path.join(temporary_sequence_dir, filename))

                def frame_number_from_path(path):
                    match = re.search(r"(-?\d+)(?=\.[^.]+$)", os.path.basename(path))
                    return int(match.group(1)) if match else 0

                generated_frames.sort(key=frame_number_from_path)

                if len(generated_frames) != expected_frame_count:
                    return False, (
                        "Maya captured {} images, but {} were expected.\n\n"
                        "Frame range: {} - {}\nTemporary sequence:\n{}".format(
                            len(generated_frames), expected_frame_count,
                            effective_start, effective_end, temporary_sequence_dir)
                    ), None

                # Rename to a guaranteed zero-based continuous FFmpeg
                # sequence (staged through a throwaway prefix first, so a
                # renumber never collides with a still-original filename).
                staged_paths = []
                for index, source_path in enumerate(generated_frames):
                    staged_path = os.path.join(temporary_sequence_dir, "_stage_{:06d}.jpg".format(index))
                    os.rename(source_path, staged_path)
                    staged_paths.append(staged_path)
                for index, staged_path in enumerate(staged_paths):
                    normalized_path = os.path.join(temporary_sequence_dir, "frame_{:06d}.jpg".format(index))
                    os.rename(staged_path, normalized_path)

                metadata_path, metadata_text = self.pb_create_metadata_file(
                    output_root=output_root,
                    project_name=project_name or "Untitled Project",
                    character_name=character_name or "Character",
                    artist_name=artist_name or "Artist",
                    start_frame=effective_start, end_frame=effective_end, fps=effective_fps
                )
                metadata_filter = self.pb_build_metadata_filter(
                    width=w, height=h, metadata_path=metadata_path,
                    metadata_text=metadata_text, start_frame=effective_start
                )

                ok, err = self.pb_run_ffmpeg_encode(
                    ffmpeg_path, temporary_sequence_dir, expected_frame_count,
                    effective_fps, metadata_filter, out_path
                )
                if not ok:
                    return False, err, None

                conversion_succeeded = True
                return True, "", out_path

            else:
                # ---- Native fallback (no FFmpeg found) ------------------
                cmds.warning(
                    "[KRT] FFmpeg not found - playblasting without the MP4/"
                    "metadata-strip QC pipeline. Install FFmpeg (or put "
                    "ffmpeg.exe on PATH) to get burned-in metadata + a "
                    "true H.264 MP4.")
                if output_path_override and output_path_override.strip():
                    out_path = os.path.splitext(output_path_override.strip())[0].replace("\\", "/")
                    override_dir = os.path.dirname(out_path)
                    if override_dir and not os.path.isdir(override_dir):
                        os.makedirs(override_dir)
                else:
                    out_path = os.path.join(out_dir, "playblast_{}".format(ts)).replace("\\", "/")
                kwargs = dict(filename=out_path, format="qt", forceOverwrite=True, viewer=False,
                              percent=100, clearCache=True, offScreen=True, showOrnaments=False)
                if start_frame is not None: kwargs["startTime"] = start_frame
                if end_frame is not None: kwargs["endTime"] = end_frame
                if width: kwargs["width"] = int(width)
                if height: kwargs["height"] = int(height)
                result_path = cmds.playblast(**kwargs)
                return True, "", result_path

        except Exception as e:
            log_crash("Create playblast", e)
            return False, traceback.format_exc(), None
        finally:
            self.pb_restore_camera_gates()
            self.pb_restore_all_huds()
            try:
                cmds.refresh(force=True)
            except Exception:
                pass
            if created_cam and cmds.objExists(created_cam):
                cmds.delete(created_cam)
            if metadata_path:
                try:
                    if os.path.isfile(metadata_path):
                        os.remove(metadata_path)
                except Exception:
                    pass
            # Keep a failed capture's temp sequence around for diagnosis;
            # clean it up once it's been successfully encoded.
            if conversion_succeeded and temporary_sequence_dir:
                try:
                    shutil.rmtree(temporary_sequence_dir)
                except Exception:
                    pass

    def page_playblast(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)

        header_row = QtWidgets.QHBoxLayout()
        header = QtWidgets.QLabel("<b>🎬 PLAYBLAST</b>")
        header.setStyleSheet("font-size: 15px; color: #2bb5a8;")
        header_row.addWidget(header)
        header_row.addStretch()
        # ── Collapse Settings (fix: the preview screen was reading too
        # small with every settings row stacked above it) - hides the
        # whole Playblast Settings box down to just its title bar, and the
        # splitter below lets the settings/preview split be dragged to any
        # size in between, instead of a fixed layout either way. ─────────
        self.btn_pb_collapse_settings = QtWidgets.QPushButton("▲ Collapse Settings")
        self.btn_pb_collapse_settings.setCheckable(True)
        self.btn_pb_collapse_settings.setToolTip(
            "Hide the settings box so the preview screen gets more room - "
            "or just drag the horizontal bar between them to resize "
            "either one to whatever size you want.")
        self.btn_pb_collapse_settings.setStyleSheet(
            "QPushButton { background-color: #2bb5a8; color: #101010; font-weight: bold; padding: 4px 10px; border-radius: 3px; } "
            "QPushButton:hover { background-color: #33cbbd; } "
            "QPushButton:checked { background-color: #3e3e42; color: white; }")
        self.btn_pb_collapse_settings.clicked.connect(self.pb_toggle_settings_collapsed)
        header_row.addWidget(self.btn_pb_collapse_settings)
        layout.addLayout(header_row)

        # ── Compact settings bar (request #3: keep this small so the video
        # preview below gets the bulk of the tab) ──────────────────────────
        settings_group = QtWidgets.QGroupBox("Playblast Settings")
        settings_group.setStyleSheet(
            "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 8px; "
            "font-weight: bold; color: #aaa; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        grid = QtWidgets.QGridLayout(settings_group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # ── Scene/QC info row (Stage 36, ported from the studio QC
        # Playblast script): Project/Character/Artist, auto-detected from
        # the scene filename, burned into the MP4's metadata strip below.
        # Refresh From Scene re-runs the detection (e.g. after Save As). ──
        info_row = QtWidgets.QHBoxLayout()
        info_row.addWidget(QtWidgets.QLabel("Project:"))
        self.pb_project_field = QtWidgets.QLineEdit()
        self.pb_project_field.setFixedWidth(140)
        info_row.addWidget(self.pb_project_field)
        info_row.addWidget(QtWidgets.QLabel("Character:"))
        self.pb_character_field = QtWidgets.QLineEdit()
        self.pb_character_field.setFixedWidth(140)
        info_row.addWidget(self.pb_character_field)
        info_row.addWidget(QtWidgets.QLabel("Artist:"))
        self.pb_artist_field = QtWidgets.QLineEdit()
        self.pb_artist_field.setFixedWidth(120)
        info_row.addWidget(self.pb_artist_field)
        info_row.addStretch()
        btn_refresh_scene = QtWidgets.QPushButton("🔄 Refresh From Scene")
        btn_refresh_scene.setToolTip(
            "Re-detects Project/Character/Artist from the scene's filename, "
            "and Start/End/FPS from the scene itself.")
        btn_refresh_scene.clicked.connect(lambda: self.pb_refresh_from_scene(update_status=True))
        info_row.addWidget(btn_refresh_scene)
        grid.addLayout(info_row, 0, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Camera:"), 1, 0)
        self.pb_camera_field = QtWidgets.QLineEdit()
        self.pb_camera_field.setPlaceholderText("Existing camera - leave empty to auto-build one from Group")
        grid.addWidget(self.pb_camera_field, 1, 1)
        btn_cam_sel = QtWidgets.QPushButton("🎯 Use Selected")
        btn_cam_sel.clicked.connect(self.pb_use_selected_camera)
        grid.addWidget(btn_cam_sel, 1, 2)

        grid.addWidget(QtWidgets.QLabel("Group (if no camera):"), 2, 0)
        self.pb_group_field = QtWidgets.QLineEdit()
        self.pb_group_field.setPlaceholderText("A group/node - its bounding box auto-builds a camera to frame it")
        grid.addWidget(self.pb_group_field, 2, 1)
        btn_grp_sel = QtWidgets.QPushButton("🎯 Use Selected")
        btn_grp_sel.clicked.connect(self.pb_use_selected_group)
        grid.addWidget(btn_grp_sel, 2, 2)

        # ── Generate Camera (Stage 38): when there's no existing camera to
        # playblast through, this builds one - full manual control over
        # position and the same lens settings the Attribute Editor's Camera
        # Shape tab shows (Angle of View/Focal Length/Camera Scale/Auto
        # Render Clip Plane/Near+Far Clip Plane), instead of only the
        # existing auto-frame-a-group option above. ────────────────────────
        gen_cam_group = QtWidgets.QGroupBox("Generate Camera (if none exists)")
        gen_cam_group.setStyleSheet(
            "QGroupBox { border: 1px solid #3e3e42; border-radius: 4px; margin-top: 6px; "
            "font-weight: bold; color: #888; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
        gen_cam_layout = QtWidgets.QVBoxLayout(gen_cam_group)
        gen_cam_layout.setSpacing(4)

        gen_row1 = QtWidgets.QHBoxLayout()
        gen_row1.addWidget(QtWidgets.QLabel("Position X:"))
        self.pb_gen_pos_x = QtWidgets.QLineEdit("0.0")
        self.pb_gen_pos_x.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_x)
        gen_row1.addWidget(QtWidgets.QLabel("Y:"))
        self.pb_gen_pos_y = QtWidgets.QLineEdit("0.0")
        self.pb_gen_pos_y.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_y)
        gen_row1.addWidget(QtWidgets.QLabel("Z:"))
        self.pb_gen_pos_z = QtWidgets.QLineEdit("24.0")
        self.pb_gen_pos_z.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_pos_z)
        gen_row1.addSpacing(12)
        # ── Rotation X/Y/Z (request #1): so the live camera view's real-
        # time tumble/pan sync has somewhere to write the camera's live
        # rotation - also editable by hand, same as Position. ──────────
        gen_row1.addWidget(QtWidgets.QLabel("Rotation X:"))
        self.pb_gen_rot_x = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_x.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_x)
        gen_row1.addWidget(QtWidgets.QLabel("Y:"))
        self.pb_gen_rot_y = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_y.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_y)
        gen_row1.addWidget(QtWidgets.QLabel("Z:"))
        self.pb_gen_rot_z = QtWidgets.QLineEdit("0.0")
        self.pb_gen_rot_z.setFixedWidth(60)
        gen_row1.addWidget(self.pb_gen_rot_z)
        gen_row1.addSpacing(12)
        gen_row1.addWidget(QtWidgets.QLabel("Focal Length:"))
        self.pb_gen_focal_length = QtWidgets.QLineEdit("35.000")
        self.pb_gen_focal_length.setFixedWidth(70)
        self.pb_gen_focal_length.setToolTip("Drives Angle of View below (same coupling as the Attribute Editor's Camera Shape tab).")
        self.pb_gen_focal_length.textChanged.connect(self.pb_update_gen_camera_aov)
        gen_row1.addWidget(self.pb_gen_focal_length)
        gen_row1.addWidget(QtWidgets.QLabel("Angle of View:"))
        self.pb_gen_aov_display = QtWidgets.QLineEdit()
        self.pb_gen_aov_display.setFixedWidth(60)
        self.pb_gen_aov_display.setReadOnly(True)
        self.pb_gen_aov_display.setToolTip("Computed from Focal Length (assumes Maya's default 36mm horizontal film aperture) - read-only, matching how the two stay in sync in Maya's own Camera Shape tab.")
        gen_row1.addWidget(self.pb_gen_aov_display)
        gen_row1.addStretch()
        gen_cam_layout.addLayout(gen_row1)

        gen_row2 = QtWidgets.QHBoxLayout()
        gen_row2.addWidget(QtWidgets.QLabel("Camera Scale:"))
        self.pb_gen_camera_scale = QtWidgets.QLineEdit("1.000")
        self.pb_gen_camera_scale.setFixedWidth(60)
        gen_row2.addWidget(self.pb_gen_camera_scale)
        self.pb_gen_auto_clip_chk = QtWidgets.QCheckBox("Auto Render Clip Plane")
        self.pb_gen_auto_clip_chk.setChecked(True)
        self.pb_gen_auto_clip_chk.setToolTip(
            "Maps to the camera's own autoRenderClipPlanes attribute - on: "
            "Maya manages the RENDER clip planes automatically; the Near/Far "
            "Clip Plane fields still set the regular viewport clip planes "
            "either way.")
        gen_row2.addWidget(self.pb_gen_auto_clip_chk)
        gen_row2.addWidget(QtWidgets.QLabel("Near Clip Plane:"))
        self.pb_gen_near_clip = QtWidgets.QLineEdit("0.100")
        self.pb_gen_near_clip.setFixedWidth(70)
        gen_row2.addWidget(self.pb_gen_near_clip)
        gen_row2.addWidget(QtWidgets.QLabel("Far Clip Plane:"))
        self.pb_gen_far_clip = QtWidgets.QLineEdit("10000.000")
        self.pb_gen_far_clip.setFixedWidth(70)
        gen_row2.addWidget(self.pb_gen_far_clip)
        gen_row2.addStretch()
        btn_gen_camera = QtWidgets.QPushButton("🎥 Generate Camera")
        btn_gen_camera.setStyleSheet("background-color: #3e3e42; color: white; font-weight: bold;")
        btn_gen_camera.setToolTip("Creates a camera at the position/lens settings above and puts it straight into the Camera field.")
        btn_gen_camera.clicked.connect(self.pb_generate_camera_clicked)
        gen_row2.addWidget(btn_gen_camera)
        gen_cam_layout.addLayout(gen_row2)

        grid.addWidget(gen_cam_group, 3, 0, 1, 3)
        self.pb_update_gen_camera_aov()

        grid.addWidget(QtWidgets.QLabel("Animation (.anim):"), 4, 0)
        # Default animation clip (request): a new Playblast tab starts
        # pointed at the studio's standard Biped QC clip instead of empty -
        # still fully editable/clearable/Browse-able same as any other
        # field, and a pipeline JSON's own saved anim_path (if it has one)
        # always overrides this the moment it's loaded (see
        # pb_apply_settings_dict/load_pipeline_from_file).
        PB_DEFAULT_ANIM_PATH = "P:/rigging_team/Rigging_local_share/QC/Rig_QC_animation/playblast/Biped QC.anim"
        self.pb_anim_field = QtWidgets.QLineEdit(PB_DEFAULT_ANIM_PATH)
        self.pb_anim_field.setPlaceholderText("Studio Library .anim clip folder - leave empty to playblast as-is")
        self.pb_anim_field.setToolTip(
            "A Studio Library animation clip (the '<name>.anim' FOLDER, "
            "containing pose.json + animation.ma/.mb) - loaded onto whatever "
            "controls in the scene match the Controls Filter below, right "
            "before capturing. Needs the studio's Studio Library install to "
            "be reachable (see the Docs tab).")
        grid.addWidget(self.pb_anim_field, 4, 1)
        btn_anim_browse = QtWidgets.QPushButton("📂 Browse")
        btn_anim_browse.clicked.connect(self.pb_browse_anim_json)
        grid.addWidget(btn_anim_browse, 4, 2)

        # ── Output MP4 path (Stage 36): optional - leave blank to keep the
        # existing auto-timestamped-into-the-playblasts-folder behavior. ──
        grid.addWidget(QtWidgets.QLabel("Save MP4 As (optional):"), 5, 0)
        self.pb_output_field = QtWidgets.QLineEdit()
        self.pb_output_field.setPlaceholderText(
            "Leave empty to auto-name into this session's playblasts folder...")
        grid.addWidget(self.pb_output_field, 5, 1)
        btn_output_browse = QtWidgets.QPushButton("📂 Browse")
        btn_output_browse.clicked.connect(self.pb_browse_output_path)
        grid.addWidget(btn_output_browse, 5, 2)

        tail_row = QtWidgets.QHBoxLayout()
        tail_row.addWidget(QtWidgets.QLabel("Controls Filter:"))
        self.pb_pattern_field = QtWidgets.QLineEdit("*_ctl")
        self.pb_pattern_field.setFixedWidth(100)
        self.pb_pattern_field.setToolTip("Only nodes matching this pattern are affected by the animation JSON above.")
        tail_row.addWidget(self.pb_pattern_field)
        tail_row.addSpacing(12)
        tail_row.addWidget(QtWidgets.QLabel("Start:"))
        self.pb_start_field = QtWidgets.QLineEdit(str(int(cmds.playbackOptions(query=True, minTime=True))))
        self.pb_start_field.setFixedWidth(50)
        tail_row.addWidget(self.pb_start_field)
        tail_row.addWidget(QtWidgets.QLabel("End:"))
        self.pb_end_field = QtWidgets.QLineEdit(str(int(cmds.playbackOptions(query=True, maxTime=True))))
        self.pb_end_field.setFixedWidth(50)
        tail_row.addWidget(self.pb_end_field)
        tail_row.addWidget(QtWidgets.QLabel("FPS:"))
        self.pb_fps_field = QtWidgets.QLineEdit(self.pb_format_fps(self.pb_get_scene_fps()))
        self.pb_fps_field.setFixedWidth(50)
        self.pb_fps_field.setToolTip("Frame rate baked into the encoded MP4. Refresh From Scene re-reads this from the scene.")
        tail_row.addWidget(self.pb_fps_field)
        tail_row.addStretch()
        grid.addLayout(tail_row, 6, 0, 1, 3)

        # ── Resolution + Create Playblast (Stage 36: resolution presets,
        # ported from the studio script; "Current Viewport" (KRT's original
        # default) keeps the native viewport size instead of forcing one. ──
        final_row = QtWidgets.QHBoxLayout()
        final_row.addWidget(QtWidgets.QLabel("Resolution:"))
        self.pb_resolution_menu = QtWidgets.QComboBox()
        self.pb_resolution_menu.addItems([
            "Current Viewport",
            "HD 720 (1280x720)",
            "HD 1080 (1920x1080)",
            "VGA (640x480)",
            "Square (1024x1024)",
        ])
        self.pb_resolution_menu.setFixedWidth(180)
        final_row.addWidget(self.pb_resolution_menu)
        final_row.addStretch()
        btn_create = QtWidgets.QPushButton("🎬 Create Playblast")
        btn_create.setStyleSheet("background-color: #2bb5a8; color: white; font-weight: bold; padding: 6px 14px;")
        btn_create.clicked.connect(self.pb_create_clicked)
        final_row.addWidget(btn_create)
        grid.addLayout(final_row, 7, 0, 1, 3)

        # ── Compare (requests #5/#6): every playblast is already saved as
        # its own timestamped version (never overwritten - see the ts =
        # time.strftime(...) naming in create_playblast), so "versions to
        # compare" already exist on disk; this row is what makes picking
        # two of them from a version LIST convenient (instead of only
        # browsing to a path by hand every time), and adds a proper
        # wipe/slider overlay mode on top of the existing side-by-side one. ─
        grid.addWidget(QtWidgets.QLabel("Compare A:"), 8, 0)
        compare_a_row = QtWidgets.QHBoxLayout()
        compare_a_row.setSpacing(4)
        self.pb_compare_a_combo = QtWidgets.QComboBox()
        self.pb_compare_a_combo.setToolTip(
            "Pick any saved version of this playblast (newest first) - "
            "Compare uses this as the LEFT / 'before' side.")
        compare_a_row.addWidget(self.pb_compare_a_combo, 1)
        grid.addLayout(compare_a_row, 8, 1)

        grid.addWidget(QtWidgets.QLabel("Compare B:"), 9, 0)
        compare_b_row = QtWidgets.QHBoxLayout()
        compare_b_row.setSpacing(4)
        self.pb_compare_b_combo = QtWidgets.QComboBox()
        self.pb_compare_b_combo.setToolTip(
            "Pick any saved version of this playblast (newest first) - "
            "Compare uses this as the RIGHT / 'after' side.")
        compare_b_row.addWidget(self.pb_compare_b_combo, 1)
        btn_compare_b_browse = QtWidgets.QPushButton("📂 Other...")
        btn_compare_b_browse.setToolTip("Browse to an older playblast video that isn't in this session's own list.")
        btn_compare_b_browse.clicked.connect(self.pb_browse_compare_path)
        compare_b_row.addWidget(btn_compare_b_browse)
        grid.addLayout(compare_b_row, 9, 1)

        # Kept for JSON persistence / backward compatibility with anything
        # already saved from before Compare A/B existed - not shown, see
        # pb_browse_compare_path/pb_get_settings_dict/pb_apply_settings_dict.
        self.pb_compare_field = QtWidgets.QLineEdit()
        self.pb_compare_field.setVisible(False)

        compare_mode_row = QtWidgets.QHBoxLayout()
        compare_mode_row.setSpacing(4)
        compare_mode_row.addWidget(QtWidgets.QLabel("Mode:"))
        self.pb_compare_mode_combo = QtWidgets.QComboBox()
        self.pb_compare_mode_combo.addItems(["Wipe / Slider", "Side-by-Side"])
        self.pb_compare_mode_combo.setToolTip(
            "Wipe/Slider - one screen, drag the line to reveal A vs B at "
            "the same moment (needs PySide6/Qt6 - falls back to Side-by-"
            "Side automatically if that's not available). Side-by-Side - "
            "two independent players next to each other.")
        compare_mode_row.addWidget(self.pb_compare_mode_combo)
        self.btn_pb_compare_toggle = QtWidgets.QPushButton("🆚 Compare")
        self.btn_pb_compare_toggle.setCheckable(True)
        self.btn_pb_compare_toggle.setToolTip("Compare Compare A against Compare B in the mode selected above.")
        self.btn_pb_compare_toggle.clicked.connect(self.pb_toggle_compare_mode)
        compare_mode_row.addWidget(self.btn_pb_compare_toggle)
        grid.addLayout(compare_mode_row, 9, 2)

        grid.setColumnStretch(1, 1)

        # ── Settings box / preview screen split (fix: preview was reading
        # too small with this many settings rows stacked above it) - a
        # draggable QSplitter instead of a fixed stack, so the divider
        # between them can be pulled to whatever size the user wants,
        # on top of the Collapse Settings button above for one-click
        # "give the preview all the room" too. ─────────────────────────
        self.pb_main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.pb_main_splitter.setChildrenCollapsible(False)
        # request #4 fix: the handle at #3e3e42/6px was reading as
        # invisible - it blended into the settings box's own border color
        # with barely any width. Made it thicker and a bright, unmistakable
        # color with a hover highlight, same as Maya's own splitter grips.
        self.pb_main_splitter.setHandleWidth(10)
        self.pb_main_splitter.setStyleSheet(
            "QSplitter::handle { background: #55555c; border-top: 1px solid #6e6e78; "
            "border-bottom: 1px solid #222; } "
            "QSplitter::handle:hover { background: #2bb5a8; }")
        self.pb_main_splitter.addWidget(settings_group)

        # ── Big preview screen (request #3: this is the main event - it
        # gets almost all the remaining vertical space). Stage 39, requests
        # #1/#3: this is now a QStackedWidget with three pages instead of a
        # single fixed frame:
        #   0 - live embedded Maya camera view (shown by default / whenever
        #       nothing has been picked to review yet - "the blank screen"
        #       from the user's request now shows the live camera instead)
        #   1 - the existing single-video playback (a picked playblast)
        #   2 - side-by-side compare mode (current vs. an older playblast)
        # ────────────────────────────────────────────────────────────────
        self.pb_preview_stack = QtWidgets.QStackedWidget()
        self.pb_preview_stack.setStyleSheet("background:#000; border: 1px solid #333;")
        self.pb_preview_stack.setMinimumHeight(360)

        # -- page 0: live camera view -----------------------------------
        self.pb_camera_view = PBCameraViewWidget(
            self.pb_preview_stack, on_transform_changed=self.pb_on_live_camera_transform)
        self.pb_preview_stack.addWidget(self.pb_camera_view)

        # -- page 1: single-video playback (unchanged from before) ------
        preview_frame = QtWidgets.QFrame()
        preview_frame.setStyleSheet("background:#000;")
        preview_layout = QtWidgets.QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        if HAS_MULTIMEDIA:
            self.pb_media_player = QMediaPlayer(preview_frame)
            self.pb_video_widget = QVideoWidget(preview_frame)
            self.pb_video_widget.setMinimumHeight(360)
            if IS_PYSIDE6 and QAudioOutput is not None:
                self._pb_audio_output = QAudioOutput(preview_frame)
                self.pb_media_player.setAudioOutput(self._pb_audio_output)
                self.pb_media_player.setVideoOutput(self.pb_video_widget)
            else:
                self.pb_media_player.setVideoOutput(self.pb_video_widget)
            preview_layout.addWidget(self.pb_video_widget)
        else:
            self.pb_media_player = None
            self.pb_video_widget = None
            warn = QtWidgets.QLabel(
                "Embedded playback isn't available in this Maya's Qt install "
                "(QtMultimedia not found) - pick a playblast below to open it "
                "in your default video player instead.")
            warn.setAlignment(QtCore.Qt.AlignCenter)
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #ffcc66; padding: 40px;")
            preview_layout.addWidget(warn)
        self.pb_preview_stack.addWidget(preview_frame)

        # -- page 2: compare mode (request #3) - current playblast on the
        # left, an older one (from the Compare Path field) on the right --
        compare_frame = QtWidgets.QFrame()
        compare_frame.setStyleSheet("background:#000;")
        compare_layout = QtWidgets.QHBoxLayout(compare_frame)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.setSpacing(2)

        self.pb_compare_media_player = None
        self.pb_compare_video_widget = None
        if HAS_MULTIMEDIA:
            left_lbl = QtWidgets.QLabel("Current")
            left_lbl.setAlignment(QtCore.Qt.AlignCenter)
            left_lbl.setStyleSheet("color:#2bb5a8; background:#111; font-weight:bold;")
            # Re-use pb_video_widget itself for the "current" side so there's
            # only one media player driving the current clip either way -
            # it just gets reparented between pages 1 and 2's layouts.
            self.pb_compare_current_container = QtWidgets.QWidget()
            cur_layout = QtWidgets.QVBoxLayout(self.pb_compare_current_container)
            cur_layout.setContentsMargins(0, 0, 0, 0)
            cur_layout.addWidget(left_lbl)
            compare_layout.addWidget(self.pb_compare_current_container, 1)

            right_col = QtWidgets.QVBoxLayout()
            right_lbl = QtWidgets.QLabel("Older / Compare")
            right_lbl.setAlignment(QtCore.Qt.AlignCenter)
            right_lbl.setStyleSheet("color:#ffcc66; background:#111; font-weight:bold;")
            self.pb_compare_media_player = QMediaPlayer(compare_frame)
            self.pb_compare_video_widget = QVideoWidget(compare_frame)
            self.pb_compare_video_widget.setMinimumHeight(300)
            if IS_PYSIDE6 and QAudioOutput is not None:
                self._pb_compare_audio_output = QAudioOutput(compare_frame)
                self.pb_compare_media_player.setAudioOutput(self._pb_compare_audio_output)
                self.pb_compare_media_player.setVideoOutput(self.pb_compare_video_widget)
            else:
                self.pb_compare_media_player.setVideoOutput(self.pb_compare_video_widget)
            right_col.addWidget(right_lbl)
            right_col.addWidget(self.pb_compare_video_widget, 1)
            compare_layout.addLayout(right_col, 1)
        else:
            warn2 = QtWidgets.QLabel(
                "Compare mode needs embedded playback (QtMultimedia), which "
                "isn't available in this Maya's Qt install.")
            warn2.setAlignment(QtCore.Qt.AlignCenter)
            warn2.setWordWrap(True)
            warn2.setStyleSheet("color: #ffcc66; padding: 40px;")
            compare_layout.addWidget(warn2)
        self.pb_preview_stack.addWidget(compare_frame)

        # -- page 3: wipe/slider compare (request #6) --------------------
        self.pb_wipe_compare = PBWipeCompareWidget(self.pb_preview_stack)
        self.pb_preview_stack.addWidget(self.pb_wipe_compare)

        self.pb_preview_stack.setCurrentIndex(0)   # default: live camera view

        preview_and_bottom = QtWidgets.QWidget()
        preview_and_bottom_layout = QtWidgets.QVBoxLayout(preview_and_bottom)
        preview_and_bottom_layout.setContentsMargins(0, 0, 0, 0)
        preview_and_bottom_layout.setSpacing(8)
        preview_and_bottom_layout.addWidget(self.pb_preview_stack, 1)

        # ── Bottom bar (request #3): loading a past playblast AND the
        # transport (play/pause/stop) controls live together here, below the
        # big screen, laid out as one clean toolbar-style row instead of a
        # side list competing with the preview for width. ─────────────────
        bottom_bar = QtWidgets.QFrame()
        bottom_bar.setStyleSheet("background:#2d2d30; border: 1px solid #3e3e42; border-radius: 4px;")
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 8, 10, 8)
        bottom_layout.setSpacing(10)

        bottom_layout.addWidget(QtWidgets.QLabel("📂 Playblast:"))
        self.pb_combo = QtWidgets.QComboBox()
        self.pb_combo.setMinimumWidth(260)
        self.pb_combo.setStyleSheet(
            "background:#1e1e1e; border:1px solid #444; color:white; padding: 4px;")
        self.pb_combo.currentIndexChanged.connect(self.pb_on_combo_changed)
        bottom_layout.addWidget(self.pb_combo, 1)

        btn_refresh_pb = QtWidgets.QPushButton("🔄")
        btn_refresh_pb.setToolTip("Refresh the list of playblasts")
        btn_refresh_pb.setFixedWidth(34)
        btn_refresh_pb.clicked.connect(self.refresh_playblast_list)
        bottom_layout.addWidget(btn_refresh_pb)

        sep0 = QtWidgets.QFrame(); sep0.setFrameShape(QtWidgets.QFrame.VLine); sep0.setStyleSheet("color:#555;")
        bottom_layout.addWidget(sep0)

        # ── Copy/Paste Settings (request #2): copy every Playblast tab
        # field from this rig's session and one-click paste them into
        # another rig's/session's Playblast tab. Goes through a class-level
        # clipboard shared by every open type(self). ────────────────
        btn_pb_copy = QtWidgets.QPushButton("📋 Copy Settings")
        btn_pb_copy.setToolTip("Copy all Playblast tab settings to paste into another rig's Playblast tab.")
        btn_pb_copy.clicked.connect(self.pb_copy_settings)
        bottom_layout.addWidget(btn_pb_copy)

        btn_pb_paste = QtWidgets.QPushButton("📥 Paste Settings")
        btn_pb_paste.setToolTip("Paste the last-copied Playblast tab settings into this rig's Playblast tab.")
        btn_pb_paste.clicked.connect(self.pb_paste_settings)
        bottom_layout.addWidget(btn_pb_paste)

        sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.VLine); sep.setStyleSheet("color:#555;")
        bottom_layout.addWidget(sep)

        btn_play = QtWidgets.QPushButton("▶")
        btn_play.setToolTip("Play")
        btn_pause = QtWidgets.QPushButton("⏸")
        btn_pause.setToolTip("Pause")
        btn_stop = QtWidgets.QPushButton("⏹")
        btn_stop.setToolTip("Stop")
        for b in (btn_play, btn_pause, btn_stop):
            b.setFixedSize(34, 28)
            b.setStyleSheet("background-color: #3e3e42; color: white; font-weight: bold;")
            bottom_layout.addWidget(b)
        if HAS_MULTIMEDIA:
            # Dispatchers (not the player directly) so these three buttons
            # also drive whichever compare page (side-by-side or wipe) is
            # currently active, not just the single-video page.
            btn_play.clicked.connect(self.pb_transport_play)
            btn_pause.clicked.connect(self.pb_transport_pause)
            btn_stop.clicked.connect(self.pb_transport_stop)
        else:
            btn_play.clicked.connect(self.pb_play_current_selection)
            btn_pause.setEnabled(False)
            btn_stop.setEnabled(False)

        self.lbl_pb_status = QtWidgets.QLabel("")
        self.lbl_pb_status.setStyleSheet("color: #888;")
        bottom_layout.addWidget(self.lbl_pb_status, 1)

        preview_and_bottom_layout.addWidget(bottom_bar)

        self.pb_main_splitter.addWidget(preview_and_bottom)
        self.pb_main_splitter.setStretchFactor(0, 0)
        self.pb_main_splitter.setStretchFactor(1, 1)
        # Initial split favors the preview screen (fix: it was reading too
        # small) - still fully draggable afterward, and Collapse Settings
        # above gives it the rest of the space in one click.
        self.pb_main_splitter.setSizes([260, 640])
        layout.addWidget(self.pb_main_splitter, 1)

        self.refresh_playblast_list()
        self.pb_refresh_from_scene(update_status=False)

        # Request #1: keep the live camera view pointed at whatever's in
        # the Camera field, live, as the user types/browses/selects.
        self.pb_camera_field.textChanged.connect(self.pb_on_camera_field_changed)
        self.pb_on_camera_field_changed(self.pb_camera_field.text())

        return page

    def pb_toggle_settings_collapsed(self, checked=None):
        """Collapse Settings button - fix for the preview screen reading
        too small with every settings row stacked above it. Shrinks the
        settings pane of the splitter down to just its title bar (not a
        hide - the splitter handle stays usable to pull it back open, and
        clicking the button again restores the previous split)."""
        if checked is None:
            checked = self.btn_pb_collapse_settings.isChecked()
        if not hasattr(self, "pb_main_splitter"):
            return
        sizes = self.pb_main_splitter.sizes()
        total = sum(sizes) or 900
        if checked:
            self._pb_settings_split_before_collapse = sizes
            self.pb_main_splitter.setSizes([28, total - 28])
            self.btn_pb_collapse_settings.setText("▼ Expand Settings")
        else:
            restore = getattr(self, "_pb_settings_split_before_collapse", None)
            self.pb_main_splitter.setSizes(restore if restore else [260, total - 260])
            self.btn_pb_collapse_settings.setText("▲ Collapse Settings")

    # ------------------------------------------------------------------
    # Live camera view wiring (Stage 39, request #1)
    # ------------------------------------------------------------------
    def pb_set_live_view_camera(self, camera_name):
        """Points the embedded live camera view (preview page 0) at
        `camera_name` and switches the preview screen to show it."""
        if not hasattr(self, "pb_camera_view"):
            return
        self.pb_camera_view.set_camera(camera_name)
        if hasattr(self, "pb_preview_stack") and not self.btn_pb_compare_toggle.isChecked():
            self.pb_preview_stack.setCurrentIndex(0)

    def pb_on_camera_field_changed(self, text):
        text = (text or "").strip()
        if text and cmds.objExists(text):
            self.pb_set_live_view_camera(text)

    def pb_on_live_camera_transform(self, pos, rot):
        """Called (via QTimer polling inside PBCameraViewWidget) whenever
        the live view's camera has moved - pushes the new position/
        rotation into the Generate Camera group's fields in real time, as
        requested, unless the user is actively typing in one of them."""
        fields = (
            (self.pb_gen_pos_x, pos[0]), (self.pb_gen_pos_y, pos[1]), (self.pb_gen_pos_z, pos[2]),
            (self.pb_gen_rot_x, rot[0]), (self.pb_gen_rot_y, rot[1]), (self.pb_gen_rot_z, rot[2]),
        )
        for field, value in fields:
            if field.hasFocus():
                continue
            field.setText("{:.3f}".format(value))

    # ------------------------------------------------------------------
    # Compare mode (Stage 39/40, requests #3/#5/#6): every playblast is
    # already saved as a distinct timestamped version (create_playblast's
    # ts = time.strftime(...) naming - nothing here ever overwrites an
    # older one unless "Save MP4 As" is set to the exact same path by
    # hand), so Compare A/B just need to let the user PICK two of those
    # versions instead of typing/browsing a path every time.
    # ------------------------------------------------------------------
    def pb_refresh_compare_combos(self):
        """Repopulates Compare A/B from the same playblast folder listing
        refresh_playblast_list already builds for the bottom bar's combo -
        newest first. Defaults A to the newest version and B to the
        second-newest, so 'compare the last two versions' works with zero
        clicks beyond hitting Compare. A manually browsed 'Other...' path
        (pb_browse_compare_path) is appended as its own entry in B so it
        doesn't get lost the next time this refreshes."""
        if not hasattr(self, "pb_compare_a_combo"):
            return
        d = self.get_playblast_dir()
        prev_a = self.pb_compare_a_combo.currentData()
        prev_b = self.pb_compare_b_combo.currentData()
        other_path = self.pb_compare_field.text().strip()

        entries = []
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.lower().endswith((".mov", ".avi", ".mp4"))]
            files.sort(reverse=True)
            entries = [(f, os.path.join(d, f).replace("\\", "/")) for f in files]

        entry_paths = {full for _label, full in entries}
        for combo, prev in ((self.pb_compare_a_combo, prev_a), (self.pb_compare_b_combo, prev_b)):
            combo.blockSignals(True)
            combo.clear()
            for label, full in entries:
                combo.addItem(label, full)
            if other_path and other_path not in entry_paths:
                combo.addItem("Other: {}".format(os.path.basename(other_path)), other_path)
            if combo.count() == 0:
                combo.addItem("(no playblasts yet)", "")
            combo.blockSignals(False)

        # Restore the previous picks if they still exist, otherwise default
        # to "newest" for A and "second-newest" for B.
        def _select(combo, prev, default_index):
            idx = combo.findData(prev) if prev else -1
            if idx < 0:
                idx = default_index if default_index < combo.count() else 0
            combo.setCurrentIndex(max(0, idx))

        _select(self.pb_compare_a_combo, prev_a, 0)
        _select(self.pb_compare_b_combo, prev_b, 1)

    def pb_browse_compare_path(self):
        current = self.pb_compare_field.text().strip()
        start_dir = os.path.dirname(current) if current else self.get_playblast_dir()
        res = cmds.fileDialog2(
            fileMode=1, caption="Select an Older Playblast to Compare Against",
            startingDirectory=start_dir if os.path.exists(start_dir) else "",
            fileFilter="Video (*.mp4 *.mov *.avi)")
        if not res:
            return
        self.pb_compare_field.setText(res[0])
        self.pb_refresh_compare_combos()
        # Select the just-browsed path in Compare B straight away.
        idx = self.pb_compare_b_combo.findData(res[0])
        if idx >= 0:
            self.pb_compare_b_combo.setCurrentIndex(idx)

    def pb_resolve_compare_paths(self):
        """Returns (path_a, path_b, label_a, label_b) from Compare A/B,
        falling back to the current/last-played clip for A and the legacy
        freeform Compare field for B if either combo has nothing usable -
        keeps old saved settings (from before A/B existed) working."""
        path_a = self.pb_compare_a_combo.currentData() if hasattr(self, "pb_compare_a_combo") else None
        path_b = self.pb_compare_b_combo.currentData() if hasattr(self, "pb_compare_b_combo") else None
        if not path_a or not os.path.isfile(path_a):
            path_a = getattr(self, "_pb_last_loaded_path", None)
        if not path_b or not os.path.isfile(path_b):
            fallback_b = self.pb_compare_field.text().strip()
            path_b = fallback_b if fallback_b and os.path.isfile(fallback_b) else path_b
        label_a = os.path.basename(path_a) if path_a else "A"
        label_b = os.path.basename(path_b) if path_b else "B"
        return path_a, path_b, label_a, label_b

    def pb_toggle_compare_mode(self, checked=None):
        if checked is None:
            checked = self.btn_pb_compare_toggle.isChecked()
        if checked:
            self.pb_enter_compare_mode()
        else:
            self.pb_exit_compare_mode()

    def pb_enter_compare_mode(self):
        if not hasattr(self, "pb_preview_stack"):
            self.btn_pb_compare_toggle.setChecked(False)
            return
        path_a, path_b, label_a, label_b = self.pb_resolve_compare_paths()
        if not path_a or not os.path.isfile(path_a) or not path_b or not os.path.isfile(path_b):
            cmds.warning("[KRT] Pick a valid Compare A and Compare B (or Browse an 'Other...' B) first.")
            self.btn_pb_compare_toggle.setChecked(False)
            return

        want_wipe = self.pb_compare_mode_combo.currentText().startswith("Wipe")
        use_wipe = want_wipe and hasattr(self, "pb_wipe_compare") and self.pb_wipe_compare.is_available()
        if want_wipe and not use_wipe:
            cmds.warning(
                "[KRT] Wipe/Slider compare needs PySide6/Qt6 multimedia, which "
                "isn't available in this Maya's Qt install - showing Side-by-"
                "Side instead.")

        if use_wipe:
            self.pb_wipe_compare.load(path_a, path_b, label_a=label_a, label_b=label_b)
            self.pb_wipe_compare.play()
            self.pb_preview_stack.setCurrentIndex(3)
            self.btn_pb_compare_toggle.setChecked(True)
            return

        if not HAS_MULTIMEDIA:
            cmds.warning("[KRT] Compare mode needs embedded playback (QtMultimedia), which isn't available here.")
            self.btn_pb_compare_toggle.setChecked(False)
            return

        # Move the single "current" video widget over into the compare
        # page's left-hand container so the same media player drives it
        # in either mode, rather than needing a second player just for
        # the current clip.
        self.pb_compare_current_container.layout().addWidget(self.pb_video_widget, 1)
        self.pb_load_media(self.pb_media_player, path_a)
        self.pb_load_media(self.pb_compare_media_player, path_b)
        self.pb_preview_stack.setCurrentIndex(2)
        self.btn_pb_compare_toggle.setChecked(True)

    def pb_exit_compare_mode(self):
        self.btn_pb_compare_toggle.setChecked(False)
        if not hasattr(self, "pb_preview_stack"):
            return
        if hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.stop()
        if HAS_MULTIMEDIA:
            # Move the "current" video widget back to its normal single-
            # video playback page.
            parent_widget = self.pb_preview_stack.widget(1)
            if parent_widget is not None and self.pb_video_widget.parentWidget() is not parent_widget:
                parent_widget.layout().addWidget(self.pb_video_widget)
            if self.pb_compare_media_player is not None:
                self.pb_compare_media_player.stop()
        self.pb_preview_stack.setCurrentIndex(1 if self._pb_has_loaded_media() else 0)

    def pb_load_media(self, player, path):
        """Small shared helper - loads `path` into `player` (a
        QMediaPlayer), the same call pattern already used by
        pb_on_combo_changed for the single-video page."""
        if player is None or not path:
            return
        try:
            url = QtCore.QUrl.fromLocalFile(path)
            if IS_PYSIDE6:
                player.setSource(url)
            elif QMediaContent is not None:
                player.setMedia(QMediaContent(url))
            player.play()
        except Exception:
            pass

    def pb_transport_play(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.play()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.play()
            self.pb_compare_media_player.play()
        else:
            self.pb_media_player.play()

    def pb_transport_pause(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.pause()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.pause()
            self.pb_compare_media_player.pause()
        else:
            self.pb_media_player.pause()

    def pb_transport_stop(self):
        idx = self.pb_preview_stack.currentIndex() if hasattr(self, "pb_preview_stack") else 1
        if idx == 3 and hasattr(self, "pb_wipe_compare"):
            self.pb_wipe_compare.stop()
        elif idx == 2 and getattr(self, "pb_compare_media_player", None) is not None:
            self.pb_media_player.stop()
            self.pb_compare_media_player.stop()
        else:
            self.pb_media_player.stop()

    def pb_use_selected_camera(self):
        sel = cmds.ls(sl=True, type="camera") or cmds.listRelatives(cmds.ls(sl=True) or [], shapes=True, type="camera") or []
        sel_transforms = cmds.ls(sl=True, type="transform") or []
        cam = None
        for t in sel_transforms:
            shapes = cmds.listRelatives(t, shapes=True, type="camera") or []
            if shapes:
                cam = t
                break
        if not cam:
            cmds.warning("Select a camera (or its transform) first.")
            return
        self.pb_camera_field.setText(cam)

    def pb_use_selected_group(self):
        sel = cmds.ls(sl=True) or []
        if not sel:
            cmds.warning("Select a group/node first.")
            return
        self.pb_group_field.setText(sel[0])

    def pb_get_settings_dict(self):
        return {
            "camera": self.pb_camera_field.text(),
            "group": self.pb_group_field.text(),
            "anim_path": self.pb_anim_field.text(),
            "output_path": self.pb_output_field.text(),
            "project": self.pb_project_field.text(),
            "character": self.pb_character_field.text(),
            "artist": self.pb_artist_field.text(),
            "controls_filter": self.pb_pattern_field.text(),
            "start_frame": self.pb_start_field.text(),
            "end_frame": self.pb_end_field.text(),
            "fps": self.pb_fps_field.text(),
            "resolution": self.pb_resolution_menu.currentText(),
            "gen_pos_x": self.pb_gen_pos_x.text(),
            "gen_pos_y": self.pb_gen_pos_y.text(),
            "gen_pos_z": self.pb_gen_pos_z.text(),
            "gen_rot_x": self.pb_gen_rot_x.text() if hasattr(self, "pb_gen_rot_x") else "0.0",
            "gen_rot_y": self.pb_gen_rot_y.text() if hasattr(self, "pb_gen_rot_y") else "0.0",
            "gen_rot_z": self.pb_gen_rot_z.text() if hasattr(self, "pb_gen_rot_z") else "0.0",
            "gen_focal_length": self.pb_gen_focal_length.text(),
            "gen_camera_scale": self.pb_gen_camera_scale.text(),
            "gen_near_clip": self.pb_gen_near_clip.text(),
            "gen_far_clip": self.pb_gen_far_clip.text(),
            "gen_auto_clip": self.pb_gen_auto_clip_chk.isChecked(),
            "compare_path": self.pb_compare_field.text() if hasattr(self, "pb_compare_field") else "",
            "compare_mode": self.pb_compare_mode_combo.currentText() if hasattr(self, "pb_compare_mode_combo") else "Wipe / Slider",
        }

    def pb_apply_settings_dict(self, pb_data):
        if not pb_data:
            return
        self.pb_camera_field.setText(pb_data.get("camera", ""))
        self.pb_group_field.setText(pb_data.get("group", ""))
        self.pb_anim_field.setText(pb_data.get("anim_path", ""))
        self.pb_output_field.setText(pb_data.get("output_path", ""))
        self.pb_project_field.setText(pb_data.get("project", ""))
        self.pb_character_field.setText(pb_data.get("character", ""))
        self.pb_artist_field.setText(pb_data.get("artist", ""))
        self.pb_pattern_field.setText(pb_data.get("controls_filter", "*_ctl"))
        if pb_data.get("start_frame"): self.pb_start_field.setText(pb_data.get("start_frame"))
        if pb_data.get("end_frame"): self.pb_end_field.setText(pb_data.get("end_frame"))
        if pb_data.get("fps"): self.pb_fps_field.setText(pb_data.get("fps"))
        resolution = pb_data.get("resolution")
        if resolution:
            idx = self.pb_resolution_menu.findText(resolution)
            if idx >= 0: self.pb_resolution_menu.setCurrentIndex(idx)
        if pb_data.get("gen_pos_x") is not None: self.pb_gen_pos_x.setText(pb_data.get("gen_pos_x"))
        if pb_data.get("gen_pos_y") is not None: self.pb_gen_pos_y.setText(pb_data.get("gen_pos_y"))
        if pb_data.get("gen_pos_z") is not None: self.pb_gen_pos_z.setText(pb_data.get("gen_pos_z"))
        if hasattr(self, "pb_gen_rot_x"):
            if pb_data.get("gen_rot_x") is not None: self.pb_gen_rot_x.setText(pb_data.get("gen_rot_x"))
            if pb_data.get("gen_rot_y") is not None: self.pb_gen_rot_y.setText(pb_data.get("gen_rot_y"))
            if pb_data.get("gen_rot_z") is not None: self.pb_gen_rot_z.setText(pb_data.get("gen_rot_z"))
        if pb_data.get("gen_focal_length"): self.pb_gen_focal_length.setText(pb_data.get("gen_focal_length"))
        if pb_data.get("gen_camera_scale"): self.pb_gen_camera_scale.setText(pb_data.get("gen_camera_scale"))
        if pb_data.get("gen_near_clip"): self.pb_gen_near_clip.setText(pb_data.get("gen_near_clip"))
        if pb_data.get("gen_far_clip"): self.pb_gen_far_clip.setText(pb_data.get("gen_far_clip"))
        if "gen_auto_clip" in pb_data: self.pb_gen_auto_clip_chk.setChecked(bool(pb_data.get("gen_auto_clip")))
        if hasattr(self, "pb_compare_field") and pb_data.get("compare_path") is not None:
            self.pb_compare_field.setText(pb_data.get("compare_path"))
        if hasattr(self, "pb_compare_mode_combo") and pb_data.get("compare_mode"):
            idx = self.pb_compare_mode_combo.findText(pb_data.get("compare_mode"))
            if idx >= 0: self.pb_compare_mode_combo.setCurrentIndex(idx)
        if hasattr(self, "pb_compare_a_combo"):
            self.pb_refresh_compare_combos()
        # Camera field's textChanged is already wired to keep the live
        # view in sync - re-push it explicitly too, in case the text
        # didn't actually change (setText is a no-op signal-wise then).
        if hasattr(self, "pb_camera_view"):
            self.pb_on_camera_field_changed(self.pb_camera_field.text())

    def pb_copy_settings(self):
        """Request #2: copies every Playblast tab field on this rig into a
        class-level clipboard, shared by every open KRT session/rig, so it
        can be pasted into a different rig's Playblast tab with one click."""
        type(self)._pb_settings_clipboard = self.pb_get_settings_dict()
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Playblast settings copied - use Paste Settings on another rig to apply them.")

    def pb_paste_settings(self):
        """Request #2: applies the last Copy Settings' clipboard to this
        rig's Playblast tab. Camera/Group/Anim/Output/Compare are text
        paths - they're pasted as-is (they may point at nodes/files that
        don't exist on this rig/scene, same as typing them in by hand)."""
        clip = type(self)._pb_settings_clipboard
        if not clip:
            cmds.warning("[KRT] No Playblast settings have been copied yet - use Copy Settings first.")
            return
        self.pb_apply_settings_dict(clip)
        if hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText("Playblast settings pasted from clipboard.")

    def pb_browse_anim_json(self):
        """Stage 37: picks a Studio Library .anim clip - these are
        FOLDERS (e.g. "myWave.anim/"), not a single JSON file, so this
        uses a directory picker. Also auto-fills Start/End from the
        clip's own frame range (still editable) so the Playblast's
        capture range matches the clip by default."""
        start_dir = self.get_playblast_dir()
        res = cmds.fileDialog2(fileMode=3, caption="Select a Studio Library Animation (.anim) Folder",
                               startingDirectory=start_dir if os.path.exists(start_dir) else "")
        if not res:
            return
        anim_path = res[0].rstrip("/\\")
        self.pb_anim_field.setText(anim_path)

        if not self.pb_is_studiolibrary_anim_path(anim_path):
            cmds.warning(
                "[KRT] '{}' doesn't look like a Studio Library .anim item "
                "(expected pose.json + animation.ma/.mb inside it).".format(anim_path))
            return

        start_frame, end_frame = self.pb_get_anim_frame_range(anim_path)
        if start_frame is not None and end_frame is not None:
            self.pb_start_field.setText(str(int(start_frame)))
            self.pb_end_field.setText(str(int(end_frame)))
            if hasattr(self, "lbl_pb_status"):
                self.lbl_pb_status.setText(
                    "Animation clip selected: {} ({} - {})".format(
                        os.path.basename(anim_path), int(start_frame), int(end_frame)))

    def pb_browse_output_path(self):
        """Stage 36: optional explicit Save MP4 As... path, ported from the
        studio script's own output Browse button. Leaving the field blank
        keeps KRT's original auto-timestamped-into-the-playblasts-folder
        naming (see create_playblast)."""
        current = self.pb_output_field.text().strip()
        start_dir = os.path.dirname(current) if current else self.get_playblast_dir()
        selected = cmds.fileDialog2(
            fileMode=0, dialogStyle=2, caption="Save QC Playblast MP4",
            startingDirectory=start_dir if os.path.exists(start_dir) else "",
            fileFilter="MP4 Video (*.mp4)")
        if not selected:
            return
        out_path = selected[0]
        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
        self.pb_output_field.setText(out_path)

    def pb_refresh_from_scene(self, update_status=True):
        """Refresh From Scene (Stage 36, ported from the studio QC Playblast
        script): re-detects Project/Character/Artist from the scene's
        filename, and Start/End/FPS from the scene itself. Project is only
        auto-filled if the field is currently empty - a manually-typed
        project name is never overwritten, since (unlike the single-project
        studio script) KRT is used across multiple shows/characters."""
        if not hasattr(self, "pb_project_field"):
            return

        scene_path = cmds.file(query=True, sceneName=True) or ""
        scene_stem = os.path.splitext(os.path.basename(scene_path))[0] if scene_path else "Untitled"

        current_project = self.pb_project_field.text().strip()
        if not current_project:
            current_project = self.edit_rig_name.text().strip() if hasattr(self, "edit_rig_name") else ""
            current_project = current_project or "Untitled Project"
            self.pb_project_field.setText(current_project)

        character = self.pb_parse_character_from_filename(scene_stem, project_name=current_project)
        artist = self.pb_parse_artist_from_filename(scene_stem)

        start_frame = int(round(cmds.playbackOptions(query=True, minTime=True)))
        end_frame = int(round(cmds.playbackOptions(query=True, maxTime=True)))
        fps = self.pb_get_scene_fps()

        self.pb_character_field.setText(character)
        self.pb_artist_field.setText(artist)
        self.pb_start_field.setText(str(start_frame))
        self.pb_end_field.setText(str(end_frame))
        self.pb_fps_field.setText(self.pb_format_fps(fps))

        if update_status and hasattr(self, "lbl_pb_status"):
            self.lbl_pb_status.setText(
                "Refreshed from scene: {} | {}-{} | {} FPS".format(
                    scene_stem, start_frame, end_frame, self.pb_format_fps(fps)))

    def pb_get_output_resolution(self):
        """(width, height), or (None, None) for "Current Viewport" - i.e.
        don't force a size, matching KRT's original playblast behavior."""
        if not hasattr(self, "pb_resolution_menu"):
            return None, None
        selected = self.pb_resolution_menu.currentText()
        if "720" in selected:
            return 1280, 720
        if "1080" in selected:
            return 1920, 1080
        if "VGA" in selected:
            return 640, 480
        if "Square" in selected:
            return 1024, 1024
        return None, None

    def pb_run_playblast(self):
        """Run a playblast with whatever the Playblast tab currently holds.
        Returns (success, error_msg, output_path).

        Split out of pb_create_clicked so the AYON publish dialog can make a
        QC movie itself without duplicating the field-gathering, and without
        the button handler's popups/preview side-effects.
        """
        try:
            start = int(self.pb_start_field.text().strip())
        except Exception:
            start = None
        try:
            end = int(self.pb_end_field.text().strip())
        except Exception:
            end = None
        try:
            fps = float(self.pb_fps_field.text().strip())
            if fps <= 0:
                fps = None
        except Exception:
            fps = None
        width, height = self.pb_get_output_resolution()
        return self.create_playblast(
            self.pb_camera_field.text(), self.pb_group_field.text(),
            self.pb_anim_field.text(), self.pb_pattern_field.text(),
            start_frame=start, end_frame=end, width=width, height=height, fps=fps,
            project_name=self.pb_project_field.text().strip(),
            character_name=self.pb_character_field.text().strip(),
            artist_name=self.pb_artist_field.text().strip(),
            output_path_override=self.pb_output_field.text().strip())

    def pb_create_clicked(self):
        try:
            start = int(self.pb_start_field.text().strip())
        except Exception:
            start = None
        try:
            end = int(self.pb_end_field.text().strip())
        except Exception:
            end = None
        try:
            fps = float(self.pb_fps_field.text().strip())
            if fps <= 0:
                fps = None
        except Exception:
            fps = None

        width, height = self.pb_get_output_resolution()

        self.lbl_pb_status.setText("Creating playblast...")
        QtWidgets.QApplication.processEvents()
        success, err, out_path = self.create_playblast(
            self.pb_camera_field.text(), self.pb_group_field.text(),
            self.pb_anim_field.text(), self.pb_pattern_field.text(),
            start_frame=start, end_frame=end, width=width, height=height, fps=fps,
            project_name=self.pb_project_field.text().strip(),
            character_name=self.pb_character_field.text().strip(),
            artist_name=self.pb_artist_field.text().strip(),
            output_path_override=self.pb_output_field.text().strip())
        if not success:
            self.lbl_pb_status.setText("Failed - see Script Editor.")
            cmds.warning("[KRT] Playblast failed: {}".format(err))
            try:
                cmds.confirmDialog(
                    title="Playblast Error", message=(err or "")[-6000:],
                    button=["OK"], defaultButton="OK", icon="critical")
            except Exception:
                pass
            return
        self.lbl_pb_status.setText("Created: {}".format(out_path))
        self.refresh_playblast_list(select_path=out_path)
        if out_path:
            self.pb_play_path(out_path)

    def refresh_playblast_list(self, select_path=None):
        """Repopulate the bottom bar's Playblast dropdown. `select_path`, if
        given (e.g. right after Create Playblast), is selected afterward -
        otherwise the current selection is kept if it's still in the list."""
        if not hasattr(self, "pb_combo"):
            return
        prev_path = select_path or self.pb_combo.currentData()
        self.pb_combo.blockSignals(True)
        self.pb_combo.clear()
        d = self.get_playblast_dir()
        select_index = -1
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.lower().endswith((".mov", ".avi", ".mp4"))]
            files.sort(reverse=True)
            for fn in files:
                full = os.path.join(d, fn).replace("\\", "/")
                self.pb_combo.addItem(fn, full)
                if prev_path and full == prev_path:
                    select_index = self.pb_combo.count() - 1
            if self.pb_combo.count() == 0:
                self.pb_combo.addItem("(no playblasts yet)", "")
        else:
            self.pb_combo.addItem("(no playblasts yet)", "")
        self.pb_combo.blockSignals(False)
        if select_index >= 0:
            self.pb_combo.setCurrentIndex(select_index)
        elif select_path:
            # Just-created file didn't match anything (shouldn't normally
            # happen) - default to the newest entry instead of nothing.
            self.pb_combo.setCurrentIndex(0)
        self.pb_refresh_compare_combos()

    def pb_on_combo_changed(self, index):
        path = self.pb_combo.itemData(index)
        if path and os.path.isfile(path):
            self.pb_play_path(path)

    def pb_play_current_selection(self):
        path = self.pb_combo.currentData()
        if not path:
            cmds.warning("No playblast selected.")
            return
        self.pb_play_path(path)

    def pb_play_path(self, path):
        if not path or not os.path.isfile(path):
            cmds.warning("Playblast file not found: {}".format(path))
            return
        if HAS_MULTIMEDIA and self.pb_media_player is not None:
            url = QtCore.QUrl.fromLocalFile(path)
            if IS_PYSIDE6:
                self.pb_media_player.setSource(url)
            elif QMediaContent is not None:
                self.pb_media_player.setMedia(QMediaContent(url))
            else:
                # Older PySide2 without QMediaContent available - can't wire
                # up embedded playback reliably, fall back to the OS player.
                try:
                    os.startfile(path)
                except Exception as e:
                    cmds.warning("Could not open playblast: {}".format(e))
                return
            self.pb_media_player.play()
            self.lbl_pb_status.setText("Playing: {}".format(os.path.basename(path)))
            self._pb_last_loaded_path = path
            # Stage 39: picking a playblast to review switches the preview
            # screen off the live camera view and onto the video page (or
            # keeps compare mode's page if that's active).
            if hasattr(self, "pb_preview_stack") and not self.btn_pb_compare_toggle.isChecked():
                self.pb_preview_stack.setCurrentIndex(1)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                cmds.warning("Could not open playblast: {}".format(e))
