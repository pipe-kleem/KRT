"""SessionWorkspace - Initialize Project (Stage 42, mixin).

One button that turns a rig NAME into a working session:
    <all_Rigs>/<rig_name>/{cc_rig,controlShape,guides,model,module,
                           playblasts,rig,scripts,skinCluster}
plus the utils.py template copied into scripts/, the Rig Root set to that
folder, and the default panel stack created with paths already filled in
RELATIVE to the root (scripts/utils.py, model/export.abc, ...).
"""
from ._shared import *
from ..dialogs import ProjectInitDialog
from ..utils.paths import DEFAULT_RIGS_ROOT


class WorkspaceProjectInitMixin(object):

    # Folder layout, taken from the user's existing rigs (parshuram_a) plus
    # guides/ and playblasts/. Order is alphabetical = how Explorer shows it.
    PROJECT_FOLDERS = [
        "cc_rig", "controlShape", "guides", "model", "module",
        "playblasts", "rig", "scripts", "skinCluster",
    ]

    # Inline scripts below build their paths from RIG_ROOT, which
    # WorkspaceExecutorsMixin.run_script() injects into the shared namespace.
    # That keeps them correct if the rig folder is ever moved or renamed -
    # unlike the hardcoded absolute paths these were copied from.
    LOAD_GUIDE_CODE = (
        "from mgear.shifter import io\n"
        "import os\n"
        "io.import_guide_template(os.path.join(RIG_ROOT, \"guides\", \"{rig}.sgt\"))\n"
    )
    EXPORT_GUIDE_CODE = (
        "from mgear.shifter import io\n"
        "import os\n"
        "io.export_guide_template(os.path.join(RIG_ROOT, \"guides\", \"{rig}.sgt\"))\n"
    )
    ORGANIZE_LOD_CODE = 'organize_and_convert_lod("{rig}", delete_ai_lod=True)\n0'
    PARENT_RIG_CODE = 'cmds.parent("rig", "{rig}")\ncmds.setAttr("rig.jnt_vis", 0)'
    DISPLAY_SWITCH_CODE = (
        'import maya.cmds as cmds\n'
        '\n'
        'ctrl = "global_C0_ctl"\n'
        'attr = "Display"\n'
        '\n'
        '# add enum attr\n'
        'if not cmds.attributeQuery(attr, node=ctrl, exists=True):\n'
        '    cmds.addAttr(ctrl, ln=attr, at="enum", en="Normal:Template:Reference", k=True)\n'
        '\n'
        'src = ctrl + "." + attr\n'
        '\n'
        '# connect to all *_a_geo\n'
        'for geo in cmds.ls("*_a_geo", type="transform"):\n'
        '    cmds.setAttr(geo + ".overrideEnabled", 1)\n'
        '\n'
        '    dst = geo + ".overrideDisplayType"\n'
        '\n'
        '    old = cmds.listConnections(dst, s=True, d=False, p=True) or []\n'
        '    for o in old:\n'
        '        cmds.disconnectAttr(o, dst)\n'
        '\n'
        '    cmds.connectAttr(src, dst, f=True)\n'
        '\n'
        'cmds.select(ctrl)\n'
        'print("Done: global_C0_ctl.Display connected to *_a_geo overrideDisplayType")\n'
        'cmds.setAttr(ctrl + ".Display", 2)\n'
    )

    # Rewritten 2026-09-21 to go through AYON's own creator.
    #
    # A hand-made objectSet named "rigMain" is invisible to the official AYON
    # publisher: it looks for an INSTANCE NODE carrying AYON attributes
    # (creator identifier, product type/name, folder, task...), not just a set
    # with the right name. ayon-maya's CreateRig
    # (io.openpype.creators.maya.rig) makes that node and puts four companion
    # sets inside it - _controls_SET, _out_SET, _skeletonAnim_SET,
    # _skeletonMesh_SET - which is exactly the layout this script used to
    # build by hand. So: let AYON create the structure, then fill it.
    RIG_SETS_CODE = '''"""Create the AYON rig instance, then fill its sets.

Sets are created by ayon-maya's own creator so the official AYON publisher
detects the instance. Membership rules are KRT's:
    *ctl      -> <product>_controls_SET
    geo*      -> <product>_out_SET
    *geo      -> <product>_skeletonMesh_SET
    joints    -> <product>_skeletonAnim_SET
    char_*_a  -> the instance node itself
"""
import maya.cmds as cmds

CREATOR_ID = "io.openpype.creators.maya.rig"
VARIANT = "Main"          # product name becomes "rigMain"


def _find_ayon_rig_instance(create_context):
    for inst in list(create_context.instances):
        try:
            if inst.creator_identifier == CREATOR_ID:
                return inst
        except Exception:
            continue
    return None


def create_ayon_rig_instance(variant=VARIANT):
    """Return the instance node name, or None if AYON is not available."""
    try:
        from ayon_core.pipeline import registered_host
        from ayon_core.pipeline.create import CreateContext
    except ImportError:
        cmds.warning("[KRT] ayon_core not importable - is Maya running inside AYON?")
        return None

    host = registered_host()
    if host is None:
        cmds.warning("[KRT] No AYON host registered - launch Maya through AYON so the "
                     "rig instance can be created properly.")
        return None

    context = CreateContext(host)

    existing = _find_ayon_rig_instance(context)
    if existing is not None:
        node = existing.get("instance_node")
        print("Reusing existing AYON rig instance: {}".format(node))
        return node

    instance = context.create(CREATOR_ID, variant, pre_create_data={"use_selection": False})
    context.save_changes()
    node = instance.get("instance_node") if instance else None
    print("Created AYON rig instance: {}".format(node))
    return node


def _child_sets(instance_node):
    """The four companion sets AYON's CreateRig puts inside the instance."""
    found = {}
    for member in (cmds.sets(instance_node, query=True) or []):
        short = member.split("|")[-1].split(":")[-1]
        for suffix in ("_controls_SET", "_out_SET", "_skeletonAnim_SET", "_skeletonMesh_SET"):
            if short.endswith(suffix):
                found[suffix] = member
    return found


def _add(pattern, target_set, node_type="transform"):
    if not target_set:
        print("Skipped '{}' - target set missing.".format(pattern))
        return
    if node_type == "joint":
        items = cmds.ls(type="joint", long=True) or []
    else:
        items = cmds.ls(pattern, type=node_type, long=True) or []
    if not items:
        print("Warning: nothing matched '{}'.".format(pattern))
        return
    cmds.sets(items, forceElement=target_set)
    print("Added {} item(s) matching '{}' to {}".format(len(items), pattern, target_set))


def organize_rig_sets():
    instance_node = create_ayon_rig_instance()
    if not instance_node:
        cmds.warning("[KRT] Rig sets NOT created - without the AYON instance the publisher "
                     "would not see them. Fix the AYON session and run this step again.")
        return None

    sets = _child_sets(instance_node)
    missing = [s for s in ("_controls_SET", "_out_SET", "_skeletonAnim_SET", "_skeletonMesh_SET")
               if s not in sets]
    if missing:
        cmds.warning("[KRT] AYON instance '{}' is missing: {}".format(instance_node, missing))

    _add("*ctl", sets.get("_controls_SET"))
    _add("geo*", sets.get("_out_SET"))
    _add("*geo", sets.get("_skeletonMesh_SET"))
    _add("(all joints)", sets.get("_skeletonAnim_SET"), node_type="joint")

    # The rig content itself goes in the instance node.
    roots = cmds.ls("char_*_a", type="transform", long=True) or []
    if roots:
        cmds.sets(roots, forceElement=instance_node)
        print("Added {} root(s) to {}".format(len(roots), instance_node))
    else:
        print("Warning: no 'char_*_a' root found to add to {}.".format(instance_node))

    print("--- Rig set organization complete ({}) ---".format(instance_node))
    return instance_node


organize_rig_sets()
'''

    # (title, type, path-or-code, active)
    # "{rig}" is replaced with the rig name. A path is pre-filled even when
    # the file doesn't exist yet: it is where that step reads from, and where
    # its "Save (New Version)" writes to. The two guide panels ship OFF -
    # they are manual tools (and now runnable by their own button while off,
    # see SortablePanel.execute(force=True)).
    DEFAULT_PANELS = [
        ("MAYA GLOBAL SCRIPT",   "GLOBAL_SCRIPT", "",                                True),
        ("LOAD SCRIPT PANEL",    "SCRIPT",        "scripts/utils.py",                True),   # share_global forced on below
        ("LOAD MODEL (.ma file)", "IMPORT_3D",    "model/export.abc",                True),
        ("CUSTOM SCRIPT",        "SCRIPT",        ORGANIZE_LOD_CODE,                 True),
        ("LOAD MODULE",          "MODULE",        None,                              True),
        ("Load_Guide",           "SCRIPT",        LOAD_GUIDE_CODE,                   False),
        ("Export_Guide",         "SCRIPT",        EXPORT_GUIDE_CODE,                 False),
        ("LOAD SKINCLUSTER",     "JSON",          "skinCluster/skinCluster.jSkin",   True),
        ("CONTROL SHAPES",       "SHAPES",        "controlShape/controlShapes.json", True),
        ("CUSTOM SCRIPT",        "SCRIPT",        PARENT_RIG_CODE,                   True),
        ("Display Switch",       "SCRIPT",        DISPLAY_SWITCH_CODE,               True),
        ("Rig Sets",             "SCRIPT",        RIG_SETS_CODE,                     True),
        ("PUBLISH PATH",         "PUBLISH",       ".",                               True),
    ]

    # Stage 56: project types. A CHARACTER starts as the prop stack plus the
    # CC Import panel (OFF); character-only scripts get added to
    # CHARACTER_EXTRA_PANELS as they are written. Each entry is
    # (insert_after_title, panel_tuple) so it lands at the right place.
    PROJECT_TYPES = ("prop", "character")
    # Tongue.py ships in KRT/resources/rig_utils (P: share as fallback);
    # exec() runs it in the panel's own namespace like a pasted script.
    TONGUE_CODE = ('from KRT.utils import rig_resources\n'
                   'exec(rig_resources.read(rig_resources.TONGUE))')
    FAN_STRETCHY_CODE = 'UniUtils.run_Fan()\nUniUtils.run_stretchy()'
    CC_EXTRAS_CODE = ('import maya.mel as mel\n'
                      'mel.eval("teethCtrlAdded();")\n'
                      'mel.eval("extraSliders();")\n'
                      'UniUtils.updateEpicSpine()\n'
                      'UniUtils.switchFix()')

    CHARACTER_EXTRA_PANELS = [
        # CC IMPORT is a one-off prep step (writes cc_rig/cc_built_<ver>.ma),
        # so it stays OFF and early. Stage 63: the CC chain the build runs
        # comes AFTER the model is loaded + LOD-organised ("CUSTOM SCRIPT"
        # = the first panel of that title, the organize-LOD one), because
        # ORGANISE CC RIG swaps the CC meshes in for the model's geo.
        ("LOAD SCRIPT PANEL",     ("CC IMPORT", "CC_IMPORT", "", False)),
        ("CUSTOM SCRIPT",         ("CC .MA FILE", "IMPORT_3D", "cc_rig/cc_built_v001.ma", True)),
        # Stage 66: the slow/manual fixes ship OFF; JOINT POSITIONS loads
        # their saved result. Model update: tick them ON and run - JOINT
        # POSITIONS then saves a new version instead of loading.
        ("CC .MA FILE",           ("JOINT TRANSFER", "JOINT_TRANSFER", "", False)),
        ("JOINT TRANSFER",        ("FINGER FIX", "FINGER_FIX", "", False)),
        ("FINGER FIX",            ("CC EXTRAS", "SCRIPT", CC_EXTRAS_CODE, True)),
        ("CC EXTRAS",             ("JOINT POSITIONS", "JOINT_POS", "cc_rig/joint_positions_v001.json", True)),
        ("JOINT POSITIONS",       ("CC JOINT POSE FIX", "SCRIPT", "@template:character/cc_joint_pose_fix.py", True)),
        ("CC JOINT POSE FIX",     ("TONGUE JOINT FIX", "SCRIPT", TONGUE_CODE, True)),
        ("TONGUE JOINT FIX",      ("FAN + STRETCHY JOINTS", "SCRIPT", FAN_STRETCHY_CODE, True)),
        ("FAN + STRETCHY JOINTS", ("ORGANISE CC RIG", "SCRIPT", "@template:character/cc_organise.py", True)),
        # Stage 64: a per-rig file (seeded from templates/character/scripts/
        # at Initialize, see _copy_character_scripts), then the one-liners
        # merged into a single panel, and the normals fix just before Rig Sets.
        ("ORGANISE CC RIG",       ("BREATHING", "BREATHING", "geo_{char}_cc_base_body_lod_0", True)),
        ("Display Switch",        ("DISPLAY NORMALS FIX", "SCRIPT", "DisplayingNormalsFix()", True)),
    ]

    def default_panels_for(self, rig_type="prop"):
        panels = list(self.DEFAULT_PANELS)
        if rig_type == "character":
            for after_title, entry in self.CHARACTER_EXTRA_PANELS:
                idx = next((i for i, p in enumerate(panels) if p[0] == after_title), len(panels) - 1)
                panels.insert(idx + 1, entry)
        return panels

    def _krt_package_dir(self):
        """KRT/ itself - this file sits in KRT/workspace/, so go up two."""
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def open_project_init_dialog(self):
        dlg = ProjectInitDialog(
            self.PROJECT_FOLDERS,
            parent=self.main_window,
            default_parent_dir=os.path.dirname(self.rig_root()) if self.rig_root() else DEFAULT_RIGS_ROOT,
        )
        accepted = dlg.exec() if IS_PYSIDE6 else dlg.exec_()
        if not accepted:
            return
        name = dlg.rig_name()
        root = dlg.rig_root()
        if not name or not root:
            cmds.warning("[KRT] Initialize Project: no rig name given.")
            return
        self.initialize_project(
            root, name,
            copy_utils=dlg.chk_utils.isChecked(),
            make_panels=dlg.chk_panels.isChecked(),
            open_folder=dlg.chk_open_folder.isChecked(),
            rig_type=dlg.rig_type(),
        )

    def initialize_project(self, root, rig_name, copy_utils=True,
                           make_panels=True, open_folder=False, rig_type="prop"):
        """Create the folder structure, seed scripts/utils.py, point the Rig
        Root at it and (optionally) build the default panel stack.

        Nothing here overwrites: an existing folder is left alone, and an
        existing scripts/utils.py is never replaced.
        """
        root = root.replace("\\", "/").rstrip("/")
        created, existing = [], []
        try:
            for folder in [""] + self.PROJECT_FOLDERS:
                path = os.path.join(root, folder).replace("\\", "/") if folder else root
                if os.path.isdir(path):
                    if folder:
                        existing.append(folder)
                else:
                    os.makedirs(path)
                    if folder:
                        created.append(folder)
        except Exception:
            cmds.warning("[KRT] Initialize Project failed while creating folders:\n{}".format(
                traceback.format_exc()))
            return False

        # scripts/utils.py from the bundled template
        if copy_utils:
            dest = os.path.join(root, "scripts", "utils.py").replace("\\", "/")
            src = os.path.join(self._krt_package_dir(), "templates", "utils.py")
            if os.path.isfile(dest):
                cmds.warning("[KRT] scripts/utils.py already exists - left untouched.")
            elif not os.path.isfile(src):
                cmds.warning("[KRT] utils.py template not found at {} - skipped.".format(src))
            else:
                try:
                    shutil.copy2(src, dest)
                    cmds.warning("[KRT] Copied utils.py template -> scripts/utils.py")
                except Exception:
                    cmds.warning("[KRT] Could not copy utils.py template:\n{}".format(
                        traceback.format_exc()))

        if copy_utils and rig_type == "character":
            self._copy_character_scripts(root)

        # Rig Root: from here on every panel path is stored relative to it.
        self.set_rig_root(root, relativize_existing=False)

        if hasattr(self, "edit_rig_name") and not self.edit_rig_name.text().strip().startswith(rig_name):
            self.edit_rig_name.setText("{}_rig".format(rig_name))

        if make_panels:
            self._create_default_project_panels(rig_name=rig_name, rig_type=rig_type)
        self._refresh_path_mode_button()

        # Playblast output, if that tab has been built in this session.
        if hasattr(self, "pb_output_field") and not self.pb_output_field.text().strip():
            self.pb_output_field.setText("playblasts")

        cmds.warning("[KRT] Project ready: {}  (created: {} | already there: {})".format(
            root, ", ".join(created) or "none", ", ".join(existing) or "none"))

        if open_folder:
            try:
                os.startfile(root.replace("/", "\\"))
            except Exception:
                pass
        return True

    def _copy_character_scripts(self, root):
        """Stage 64: every file in KRT/templates/character/scripts/ is seeded
        into <rig>/scripts/ for a CHARACTER project (e.g. Breathing_Setup_Fixed.py),
        so each rig gets its own editable copy. Never overwrites."""
        src_dir = os.path.join(self._krt_package_dir(), "templates", "character", "scripts")
        if not os.path.isdir(src_dir):
            return
        for name in sorted(os.listdir(src_dir)):
            src = os.path.join(src_dir, name)
            dest = os.path.join(root, "scripts", name).replace("\\", "/")
            if not os.path.isfile(src) or name.startswith(".") or name.lower() == "readme.txt":
                continue
            if os.path.isfile(dest):
                cmds.warning("[KRT] scripts/{} already exists - left untouched.".format(name))
                continue
            try:
                if name.lower().endswith((".py", ".mel")):
                    # fill {rig}/{char} with plain replace - .format() would
                    # trip over every other brace in a real script
                    rig = os.path.basename(root)
                    with open(src, "r") as f:
                        text = f.read()
                    text = text.replace("{rig}", rig).replace("{char}", re.sub(r"_[a-z]$", "", rig))
                    with open(dest, "w") as f:
                        f.write(text)
                else:
                    shutil.copy2(src, dest)
                cmds.warning("[KRT] Copied character script -> scripts/" + name)
            except Exception:
                cmds.warning("[KRT] Could not copy {}:\n{}".format(name, traceback.format_exc()))

    def default_rig_token(self):
        """What "{rig}" becomes in the default panels' inline scripts.

        The rig folder's own name when there is a Rig Root (that is what the
        top group is called in every one of these rigs); "**" as a visible
        placeholder on a brand-new empty session, so it is obvious the name
        still has to be filled in."""
        root = self.rig_root()
        return os.path.basename(root.rstrip("/")) if root else "**"

    def _template_text(self, value):
        """'@template:character/x.py' -> that file's text (KRT/templates/),
        so long default scripts live as real .py files you can open/edit."""
        if not value.startswith("@template:"):
            return value
        path = os.path.join(self._krt_package_dir(), "templates", value[len("@template:"):])
        try:
            with open(path, "r") as f:
                return f.read()
        except IOError:
            cmds.warning("[KRT] default script template missing: " + path)
            return "# missing template: " + value

    def _create_default_project_panels(self, rig_name=None, rig_type="prop"):
        """Replace the current LOD's panels with the standard stack."""
        container = self.get_current_lod_container()
        if not container:
            cmds.warning("[KRT] No LOD selected - panels not created. Add a LOD, then run Initialize Project again.")
            return
        while container.layout.count():
            item = container.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rig = rig_name or self.default_rig_token()
        panels = self.default_panels_for(rig_type)
        for title, p_type, value, active in panels:
            if p_type == "MODULE":
                pan = self.add_module_panel(title)
            else:
                text = self._template_text(value or "")
                # .format() only where a {rig} token exists: some default
                # scripts contain their own "{}" placeholders, which .format()
                # would either consume or choke on.
                # {char} = rig name minus a trailing "_a" (kva_a -> kva), the
                # prefix the model's geo uses (geo_kva_..._lod_0).
                if "{rig}" in text or "{char}" in text:
                    text = text.format(rig=rig, char=re.sub(r"_[a-z]$", "", rig))
                pan = self.add_panel(title, p_type, text)
            if pan is not None and not active and hasattr(pan, "checkbox"):
                pan.checkbox.setChecked(False)
            # The utils library panel shares its namespace with Maya by
            # default: it exists to provide helpers, and a helper you cannot
            # call from the Script Editor is half a helper.
            if (pan is not None and title == "LOAD SCRIPT PANEL"
                    and hasattr(pan, "chk_share_global")):
                pan.chk_share_global.setChecked(True)
        cmds.warning("[KRT] Default {} panel stack created ({} panels) for '{}'.".format(
            rig_type, len(panels), rig))
