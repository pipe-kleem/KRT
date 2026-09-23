"""SessionWorkspace - executors methods (mixin, auto-split from workspace.py)."""
from ._shared import *


class WorkspaceExecutorsMixin(object):
    """Mixed into SessionWorkspace; all methods here expect to run on a SessionWorkspace instance."""


    def run_mgear_sgt(self, sgt_path):
        try: from mgear.shifter import io, guide_manager
        except ImportError: return False, "mGear not found or not loaded."
        if not os.path.exists(sgt_path): return False, f"SGT Path not found: {sgt_path}"
        try:
            io.import_guide_template(sgt_path)
            guide_node = cmds.ls("guide")
            if guide_node:
                cmds.select(guide_node); QtWidgets.QApplication.processEvents()
                guide_manager.build_from_selection(); cmds.delete(guide_node); return True, ""
            return False, "Guide node not found after SGT import."
        except Exception as e:
            log_crash("Custom Module (.sgt): {}".format(sgt_path), e)
            return False, traceback.format_exc()

    def open_script_externally(self, path):
        """Open `path` in VS Code if it's on this machine's PATH, else fall
        back to KRT's own simple in-Maya editor (Stage 17). Shared by the
        Rigging Workspace's script library list and by a SCRIPT/
        GLOBAL_SCRIPT panel's 'Edit code in VS Code' action - that action
        used to just show an error when VS Code wasn't found; now it opens
        the fallback editor instead."""
        if not path or not os.path.isfile(path):
            cmds.warning("File not found: {}".format(path))
            return
        has_code = shutil.which("code") or shutil.which("code.cmd")
        if has_code:
            try:
                subprocess.Popen('code "{}"'.format(path), shell=True)
                return
            except Exception:
                traceback.print_exc()
        dialog = SimpleCodeEditorDialog(path, self.main_window)
        if IS_PYSIDE6: dialog.exec()
        else: dialog.exec_()

    def publish_namespace_to_maya(self):
        """Copy KRT's shared script namespace into Maya's real global one.

        A SCRIPT panel runs with `exec(code, self.shared_namespace)` - a dict
        private to this KRT session tab. That is deliberate (one pipeline's
        helpers can't collide with another's), but it means anything the
        script defines or imports is invisible to Maya's Script Editor:
        typing `UniUtils` there gives NameError even though the panel ran
        fine. This copies the names across so the Script Editor sees exactly
        what the panel set up. Opt-in per panel - see the 🌐 checkbox.
        """
        import __main__ as maya_main
        published = 0
        for key, value in list(self.shared_namespace.items()):
            if key.startswith("__"):
                continue
            maya_main.__dict__[key] = value
            published += 1
        print(f"[KRT] Published {published} name(s) to Maya's global namespace "
              f"(Script Editor can now see them).")
        return published

    def run_script(self, path_or_code, func_call="", share_global=False):
        try:
            # Stage 41: inline scripts can build paths off the Rig Root
            # instead of hardcoding P:/... -> e.g. os.path.join(RIG_ROOT, "guides/x.sgt")
            self.shared_namespace["RIG_ROOT"] = self.rig_root()
            if not path_or_code.strip():
                if func_call:
                    exec(func_call, self.shared_namespace)
                return True, "" 
                
            if os.path.exists(path_or_code):
                if path_or_code.endswith(".mel"):
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    mel.eval(script_code)
                    if func_call: mel.eval(func_call)
                else:
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    exec(script_code, self.shared_namespace)
                    if func_call: exec(func_call, self.shared_namespace)
                if share_global: self.publish_namespace_to_maya()
                return True, ""
            else:
                exec(path_or_code, self.shared_namespace)
                if func_call: exec(func_call, self.shared_namespace)
                if share_global: self.publish_namespace_to_maya()
                return True, ""
        except Exception as e:
            log_crash("Custom script: {}".format(path_or_code[:120]), e)
            return False, traceback.format_exc()

    def run_script_global(self, path_or_code, func_call=""):
        """Stage 17: the "Default Script (Maya Global)" panel type. Identical
        to run_script() except Python code executes into Maya's REAL global
        namespace (__main__.__dict__ - the same dict Maya's own Script
        Editor uses) instead of self.shared_namespace, a dict private to
        this one KRT session/tab.

        The problem this solves: a dependency script (helper functions,
        imported modules) run through a normal SCRIPT panel only exists
        inside KRT's own isolated namespace - anything else in Maya
        (the Script Editor, another tool, a manually-run snippet) can't see
        it, so the user ends up re-running the same script by hand outside
        KRT too. Running it here instead makes it show up everywhere in
        Maya, exactly like typing it into the Script Editor would.

        MEL has no such distinction - mel.eval() already always runs in
        MEL's own single global scope, KRT-scoped or not, so the .mel
        branch below is identical to run_script()'s.

        Stage 25: a normal SCRIPT panel's shared_namespace is pre-seeded
        with cmds/mel/om (see reset_scene_and_ui) so a script can call
        cmds.something(...) straight away with no import of its own. Maya's
        REAL __main__ namespace has no such thing by default - a script
        that relies on that convenience (works fine as a normal SCRIPT
        panel, since that convenience is exactly why it worked) would hit a
        bare NameError the moment it touched cmds/mel/om here and silently
        fail before doing anything, which is exactly what "the script in
        the global panel isn't initializing, but the normal script panel
        works fine" looks like from the UI - no crash dialog if the script
        happens to only warn/print, or a real error that never got
        surfaced from a panel already in a good state. Seeding __main__
        with the same three names removes that gap, so a script behaves
        identically whether it runs as a SCRIPT or a GLOBAL_SCRIPT panel."""
        import __main__ as maya_main
        maya_main.__dict__.setdefault('cmds', cmds)
        maya_main.__dict__.setdefault('mel', mel)
        maya_main.__dict__.setdefault('om', om)
        try:
            if not path_or_code.strip():
                if func_call:
                    exec(func_call, maya_main.__dict__)
                return True, ""

            if os.path.exists(path_or_code):
                if path_or_code.endswith(".mel"):
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    mel.eval(script_code)
                    if func_call: mel.eval(func_call)
                else:
                    with open(path_or_code, 'r') as f: script_code = f.read()
                    exec(script_code, maya_main.__dict__)
                    if func_call: exec(func_call, maya_main.__dict__)
                self._mirror_maya_globals_into_shared(maya_main)
                return True, ""
            else:
                exec(path_or_code, maya_main.__dict__)
                if func_call: exec(func_call, maya_main.__dict__)
                self._mirror_maya_globals_into_shared(maya_main)
                return True, ""
        except Exception as e:
            log_crash("Default script (Maya global): {}".format(path_or_code[:120]), e)
            return False, traceback.format_exc()

    def _mirror_maya_globals_into_shared(self, maya_main):
        """After a GLOBAL_SCRIPT runs, make its names visible to the ordinary
        SCRIPT panels too.

        Without this, moving a helper library to a "Maya Global" panel put it
        in __main__ but NOT in shared_namespace, so the very next CUSTOM
        SCRIPT panel calling one of its functions died with NameError. A
        global script is meant to be a superset of a normal one, not a
        separate island.
        """
        for key, value in list(maya_main.__dict__.items()):
            if key.startswith("__"):
                continue
            self.shared_namespace[key] = value

    def import_3d_logic(self, path):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try:
            path_lower = path.lower()
            if path_lower.endswith(".abc"):
                if not cmds.pluginInfo('AbcImport', query=True, loaded=True): cmds.loadPlugin('AbcImport')
                cmds.AbcImport(path, mode="import")
            elif path_lower.endswith(".fbx"):
                if not cmds.pluginInfo('fbxmaya', query=True, loaded=True): cmds.loadPlugin('fbxmaya')
                cmds.file(path, i=True, type="FBX", ignoreVersion=True, mergeNamespacesOnClash=False, namespace=":")
            elif path_lower.endswith(".obj"):
                if not cmds.pluginInfo('objExport', query=True, loaded=True): cmds.loadPlugin('objExport')
                cmds.file(path, i=True, type="OBJ", ignoreVersion=True, mergeNamespacesOnClash=False, namespace=":")
            else: cmds.file(path, i=True)
            return True, ""
        except Exception as e:
            return False, str(e)

    def organize_lod_logic(self, asset_name, delete_ai_lod=True):
        """Organize every mesh currently in the scene into
        <asset_name>/<asset_name>_geo/<asset_name>_lod_<N> groups, folding
        any *_ai_lod naming into its own group (or deleting it outright if
        delete_ai_lod is on). This is the rigger's own organize_and_convert_lod
        script, kept exactly as given - only wrapped to return (success,
        message) like every other panel's Run logic, and with its own
        top-level error handling so a bad object can't silently abort the
        rest of the pass.

        Meant to run right after an Import 3D Model step on the same
        panel (the Import 3D + LOD Organize panel) - it works over
        whatever meshes are CURRENTLY in the scene, not just the ones a
        specific import just added, matching the original script's own
        behavior.
        """
        asset_name = (asset_name or "").strip()
        if not asset_name:
            return False, "No Asset Name given - type the asset's name first."

        try:
            # Part 1: Gather and ensure top-level groups
            meshes = cmds.ls(type="mesh")
            if not meshes:
                return False, "No polygon objects found in the scene."

            transforms = list(set(cmds.listRelatives(meshes, p=True, f=True) or []))
            to_group = [t for t in transforms if t.split("|")[-1] != asset_name and "|{}|".format(asset_name) not in t]

            top_grp = cmds.ls(asset_name, long=True)[0] if cmds.objExists(asset_name) else cmds.group(em=True, n=asset_name)
            for obj in to_group:
                try: cmds.parent(obj, top_grp)
                except Exception: pass

            geo_grp_name = "{}_geo".format(asset_name)
            geo_grp = next((c for c in (cmds.listRelatives(top_grp, c=True, f=True) or [])
                             if c.split("|")[-1] == geo_grp_name), None)
            if not geo_grp:
                geo_grp = cmds.group(em=True, n=geo_grp_name, p=top_grp)

            # Part 2: Parse and Sort LODs
            deleted_count = 0
            for mesh in cmds.listRelatives(top_grp, c=True, type="transform", f=True) or []:
                short_name = mesh.split("|")[-1]
                if short_name == geo_grp_name or not cmds.objExists(mesh):
                    continue

                # Handle AI LOD deletion
                if re.search(r"ai_lod", short_name, re.I) and delete_ai_lod:
                    cmds.delete(mesh)
                    deleted_count += 1
                    continue

                # Match prefix/suffix or fallback to AI LOD naming patterns
                match = re.search(r"(\d+)_lod|_lod_(\d+)", short_name, re.I)
                if match:
                    idx = match.group(1) or match.group(2)
                    lod_name = "{}_lod_{}".format(asset_name, idx)
                elif re.search(r"ai_lod", short_name, re.I):
                    lod_name = "{}_ai_lod".format(asset_name)
                else:
                    continue

                tgt_grp = cmds.ls("{}|{}".format(geo_grp, lod_name), l=True) or \
                    [cmds.group(em=True, n=lod_name, p=geo_grp)]
                try:
                    cmds.parent(mesh, tgt_grp[0])
                except Exception as e:
                    cmds.warning("[KRT] Could not parent {}: {}".format(short_name, e))

            msg = "LOD hierarchy generated successfully for '{}'.".format(asset_name)
            if delete_ai_lod and deleted_count:
                msg += " (Deleted {} AI LOD object(s))".format(deleted_count)
            cmds.inViewMessage(amg="<hl>{}</hl>".format(msg), pos="midCenter", fade=True)
            cmds.warning("[KRT] " + msg)
            return True, ""
        except Exception as e:
            return False, "LOD organize failed: {}".format(e)

    def delete_by_name_logic(self, names_text):
        """Delete every named object - the Delete panel's Run. Comma-
        separated names, same convention as every other multi-name field
        in KRT (Meshes/Joints/etc). A name that doesn't exist is reported
        and skipped, not fatal - a typo in one name shouldn't block
        deleting the rest."""
        names = [n.strip() for n in (names_text or "").split(",") if n.strip()]
        if not names:
            return False, "No object name(s) given - type one or more names (comma-separated)."
        missing = [n for n in names if not cmds.objExists(n)]
        existing = [n for n in names if cmds.objExists(n)]
        if not existing:
            return False, "None of these objects exist in the scene: {}".format(", ".join(names))
        try:
            cmds.delete(existing)
        except Exception as e:
            return False, "Failed to delete {}: {}".format(", ".join(existing), e)
        msg = "Deleted: {}".format(", ".join(existing))
        if missing:
            msg += "  (not found, skipped: {})".format(", ".join(missing))
        cmds.warning("[KRT] " + msg)
        return True, ""

    def zero_out_logic(self, names_text):
        """"Zero out" the named object(s)/control(s) - the Zero Out panel's
        Run. Rather than just resetting translate/rotate/scale on the
        object itself (which would snap it back to the origin), this
        creates an offset group above each object that absorbs its
        current world transform, then zeroes the object's own channels.
        The object doesn't move - its current position/rotation/scale is
        now held entirely on the new "<obj>_offset" group, and the
        object's own translate/rotate/scale channels read the clean
        default (0/0/0, 0/0/0, 1/1/1), exactly like a freshly-built
        rig control. Comma-separated names. A locked or connected (e.g.
        constrained) attribute on the object is skipped rather than
        failing the whole object, matching how zeroing a control by hand
        in the Channel Box behaves."""
        names = [n.strip() for n in (names_text or "").split(",") if n.strip()]
        if not names:
            return False, "No object name(s) given - type one or more names (comma-separated)."
        missing = [n for n in names if not cmds.objExists(n)]
        existing = [n for n in names if cmds.objExists(n)]
        if not existing:
            return False, "None of these objects exist in the scene: {}".format(", ".join(names))

        zeroed, already_zeroed, failed = [], [], []
        for obj in existing:
            try:
                if not cmds.objExists(obj):
                    failed.append(obj)
                    continue

                short_name = obj.split("|")[-1]
                parent_list = cmds.listRelatives(obj, parent=True, fullPath=True) or []
                parent = parent_list[0] if parent_list else None

                # Re-running Zero Out on a control that's already sitting
                # directly under its own "<obj>_offset" group should be a
                # no-op, not stack a second offset group on top of it.
                if parent and parent.split("|")[-1] == "{}_offset".format(short_name):
                    already_zeroed.append(obj)
                    continue

                # Unique offset group name, in case "<obj>_offset" is
                # already taken by something unrelated.
                offset_name = "{}_offset".format(short_name)
                base_offset_name = offset_name
                suffix = 1
                while cmds.objExists(offset_name):
                    offset_name = "{}{}".format(base_offset_name, suffix)
                    suffix += 1

                # Create the offset group and snap it onto the object's
                # current world transform (translate/rotate/scale/pivot),
                # so the object visually stays exactly where it is.
                offset_grp = cmds.group(empty=True, name=offset_name)
                world_matrix = cmds.xform(obj, query=True, worldSpace=True, matrix=True)
                cmds.xform(offset_grp, worldSpace=True, matrix=world_matrix)

                # Put the offset group where the object used to be in the
                # hierarchy, then put the object under the offset group.
                # cmds.parent preserves each node's world transform by
                # default, so nothing jumps.
                if parent:
                    cmds.parent(offset_grp, parent)
                cmds.parent(obj, offset_grp)

                # Now the object's own local transform is (at most, minus
                # float error) already identity - explicitly clean it to
                # exact 0/0/0, 0/0/0, 1/1/1 on whatever's settable.
                for attr, val in (("translateX", 0), ("translateY", 0), ("translateZ", 0),
                                   ("rotateX", 0), ("rotateY", 0), ("rotateZ", 0),
                                   ("scaleX", 1), ("scaleY", 1), ("scaleZ", 1)):
                    if not cmds.attributeQuery(attr, node=obj, exists=True):
                        continue
                    plug = "{}.{}".format(obj, attr)
                    try:
                        if cmds.getAttr(plug, lock=True) or cmds.listConnections(plug, source=True, destination=False):
                            continue
                        cmds.setAttr(plug, val)
                    except Exception:
                        pass

                zeroed.append(obj)
            except Exception:
                traceback.print_exc()
                failed.append(obj)

        if not zeroed and not already_zeroed:
            return False, "Nothing could be zeroed - see the Script Editor for details."

        msg_parts = []
        if zeroed:
            msg_parts.append("Zeroed out (offset group created): {}".format(", ".join(zeroed)))
        if already_zeroed:
            msg_parts.append("Already zeroed, skipped: {}".format(", ".join(already_zeroed)))
        msg = "  ".join(msg_parts)
        if failed:
            msg += "  (failed: {})".format(", ".join(failed))
        if missing:
            msg += "  (not found, skipped: {})".format(", ".join(missing))
        cmds.warning("[KRT] " + msg)
        return True, ""

    def parent_logic(self, children_text, parent_text):
        """Parent every listed child under the given parent - the Parent
        panel's Run. Children is comma-separated (Maya's own parent
        command accepts more than one child at once); Parent is a single
        object name. A child already under this parent is left alone
        (cmds.parent() errors on a no-op reparent) rather than failing
        the whole call."""
        children = [c.strip() for c in (children_text or "").split(",") if c.strip()]
        parent = (parent_text or "").strip()
        if not children:
            return False, "No child object(s) given - type one or more names (comma-separated)."
        if not parent:
            return False, "No Parent object given."
        if not cmds.objExists(parent):
            return False, "Parent object '{}' does not exist in the scene.".format(parent)
        missing = [c for c in children if not cmds.objExists(c)]
        existing = [c for c in children if cmds.objExists(c)]
        if not existing:
            return False, "None of these child objects exist in the scene: {}".format(", ".join(children))

        parent_short = parent.split("|")[-1]
        current_parents = {}
        for c in existing:
            p = cmds.listRelatives(c, parent=True, fullPath=True) or []
            current_parents[c] = p[0].split("|")[-1] if p else None
        to_parent = [c for c in existing if current_parents.get(c) != parent_short]
        already = [c for c in existing if c not in to_parent]

        failed = []
        if to_parent:
            try:
                cmds.parent(to_parent, parent)
            except Exception:
                # One bad child (a shape node, an object under itself, an
                # instanced/duplicate short name) shouldn't block the rest -
                # fall back to parenting one at a time.
                for c in to_parent:
                    try:
                        cmds.parent(c, parent)
                    except Exception as e:
                        failed.append((c, str(e)))

        succeeded = [c for c in to_parent if c not in [f[0] for f in failed]]
        if not succeeded and not already:
            return False, "Failed to parent: {}".format("; ".join("{} ({})".format(c, e) for c, e in failed))

        msg_parts = []
        if succeeded: msg_parts.append("Parented under '{}': {}".format(parent, ", ".join(succeeded)))
        if already: msg_parts.append("Already under '{}': {}".format(parent, ", ".join(already)))
        if missing: msg_parts.append("Not found, skipped: {}".format(", ".join(missing)))
        if failed: msg_parts.append("Failed: {}".format(", ".join(c for c, e in failed)))
        cmds.warning("[KRT] " + "  ".join(msg_parts))
        return True, ""

    def resolve_instance_transforms(self, script_code, func_call=""):
        """Runs an optional custom script (path to a .py file, or raw
        pasted code - identical convention to a SCRIPT panel's field) and
        returns whatever list of transform dicts it leaves behind in a
        variable called `transforms`. Returns KRT's own built-in 3-preset
        list (from the user's original create_and_transform_instances_by_name
        script) when no custom script is given, or when a custom script
        doesn't define `transforms`. Raises on a script error, same as
        run_script/run_script_global - the caller (create_instances_logic)
        is responsible for catching it."""
        script_code = (script_code or "").strip()
        if not script_code:
            return list(self.INSTANCE_DEFAULT_TRANSFORMS)

        ns = {'__name__': '__main__', 'cmds': cmds, 'mel': mel, 'om': om}
        if os.path.exists(script_code):
            with open(script_code, 'r') as f:
                code_text = f.read()
        else:
            code_text = script_code
        exec(code_text, ns)
        if func_call and func_call.strip():
            exec(func_call.strip(), ns)

        transforms = ns.get("transforms")
        if not transforms:
            return list(self.INSTANCE_DEFAULT_TRANSFORMS)
        return transforms

    def create_instances_logic(self, target_name, script_code="", func_call="", panel_uuid=""):
        """Instances `target_name` once per entry in the resolved transform
        list (see resolve_instance_transforms), applying each entry's
        tx/ty/tz/rx/ry/rz - identical logic to the user's own
        create_and_transform_instances_by_name(), just driven by KRT's UI
        instead of being hardcoded to one object name. The ORIGINAL object
        is left completely untouched, exactly like cmds.instance() always
        does. Every created instance is tagged with panel_uuid (if given)
        so "Delete All Instances" can find them again later, even after a
        save/reload."""
        target_name = (target_name or "").strip()
        if not target_name:
            return False, "No object given - type or Get Selected an object name to instance."
        if not cmds.objExists(target_name):
            return False, "Object '{}' does not exist in the scene.".format(target_name)

        try:
            transforms = self.resolve_instance_transforms(script_code, func_call)
        except Exception as e:
            log_crash("Instance Object: custom script", e)
            return False, "Custom instance script failed: {}".format(traceback.format_exc())

        if not transforms:
            return False, "No transforms to instance with (custom script left 'transforms' empty)."

        created = []
        try:
            for t in transforms:
                inst_nodes = cmds.instance(target_name, smartTransform=True)
                obj_name = inst_nodes[0]
                cmds.setAttr(
                    "{}.translate".format(obj_name),
                    float(t.get("tx", 0.0)), float(t.get("ty", 0.0)), float(t.get("tz", 0.0)),
                    type="double3")
                cmds.setAttr(
                    "{}.rotate".format(obj_name),
                    float(t.get("rx", 0.0)), float(t.get("ry", 0.0)), float(t.get("rz", 0.0)),
                    type="double3")
                if panel_uuid:
                    if not cmds.attributeQuery(self.INSTANCE_TAG_ATTR, node=obj_name, exists=True):
                        cmds.addAttr(obj_name, longName=self.INSTANCE_TAG_ATTR, dataType="string")
                    tag_plug = "{}.{}".format(obj_name, self.INSTANCE_TAG_ATTR)
                    cmds.setAttr(tag_plug, panel_uuid, type="string")
                    cmds.setAttr(tag_plug, lock=True)
                created.append(obj_name)
        except Exception as e:
            log_crash("Instance Object: create_instances_logic", e)
            if created:
                cmds.select(created, replace=True)
            return False, "Failed after creating {} instance(s) of '{}': {}".format(
                len(created), target_name, e)

        cmds.select(created, replace=True)
        cmds.warning("[KRT] Created {} instance(s) of '{}': {}".format(
            len(created), target_name, ", ".join(created)))
        return True, ""

    def delete_instances_by_panel_logic(self, panel_uuid):
        """Deletes every instance tagged with panel_uuid (see
        create_instances_logic) - Delete All Instances. Scans every
        transform in the scene for the tag rather than keeping an
        in-memory list, so this still works correctly after a JSON
        save/reload, a scene reopen, or a KRT restart."""
        if not panel_uuid:
            return False, "This panel has no id to look up instances by."
        tagged = []
        for node in (cmds.ls(type="transform") or []):
            plug = "{}.{}".format(node, self.INSTANCE_TAG_ATTR)
            if not cmds.attributeQuery(self.INSTANCE_TAG_ATTR, node=node, exists=True):
                continue
            try:
                if cmds.getAttr(plug) == panel_uuid:
                    tagged.append(node)
            except Exception:
                continue
        if not tagged:
            return False, "No instances created by this panel were found in the scene."
        try:
            cmds.delete(tagged)
        except Exception as e:
            return False, "Failed to delete some instances: {}".format(e)
        cmds.warning("[KRT] Deleted {} instance(s): {}".format(len(tagged), ", ".join(tagged)))
        return True, ""

    def load_skin_cluster_logic(self, path, meshes=None, show_popup=True):
        if not os.path.exists(path): return False, f"File not found: {path}"
        try:
            from ..utils import ensure_skin_ready_for_import, fast_import_skin
            # Use cmds.select (not pm.select) to avoid pymel's spurious
            # "Cannot find Maya documentation" error on installs without docs.
            mesh_list = []
            if meshes and meshes.strip() != "":
                mesh_list = [m.strip() for m in meshes.split(",") if m.strip()]
                if mesh_list:
                    cmds.select(mesh_list, replace=True)

            # Before mgear's own import runs: make sure every mesh this file
            # covers already has every influence the file expects on its
            # CURRENT skinCluster (found by history, not name). mgear's
            # importSkin silently drops the weight for any influence that
            # isn't already present instead of adding it, which is what was
            # corrupting a mesh on re-import whenever its current skin was
            # missing a joint that existed when the skin was saved (a newly
            # added influence, a different bind setup, etc - requests #1/#3).
            #
            # NOTE: mgear's importSkin() always processes every object
            # stored in the file, regardless of the current selection or
            # this panel's Meshes field (that field only decides what gets
            # *selected* beforehand, which importSkin itself ignores) - so
            # this pre-pass intentionally covers the whole file too, not
            # just `mesh_list`, to match what will actually be imported.
            #
            # Stage 16, request #1: the naming-convention check moved from
            # KRT's own launch (scanning the whole scene every time) to
            # right here, scoped to just the mesh(es) this file actually
            # covers - same "whole file, not just the Meshes field" scope
            # as the influence pre-pass above, for the same reason.
            file_meshes = read_skin_file_meshes(path)
            prompt_skincluster_naming_check(
                self.main_window, file_meshes, show_popup=show_popup)

            # Disable Maya's undo queue for the actual weight-writing work
            # below (influence adds + the weight import itself). A heavy
            # character mesh can be skinned to 500+ joints, and every
            # skinCluster edit on a mesh that size is, by default, fully
            # undoable - Maya's undo system snapshots the WHOLE weight
            # array (not just what changed) for each one. Importing a
            # file like that was observed ballooning Maya's memory into
            # the 100+ GB range and crashing the machine outright. Nobody
            # is going to want to undo an import one internal step at a
            # time anyway - a bad import gets fixed by re-importing, not
            # by walking back through hundreds of undo entries - so undo
            # is turned off for this whole load and always restored after,
            # success or failure.
            undo_was_on = cmds.undoInfo(query=True, state=True)
            if undo_was_on:
                cmds.undoInfo(state=False)
            try:
                ensure_skin_ready_for_import(path)

                # fast_import_skin() (utils.py) - same .jSkin/.gSkin file
                # mgear's own importSkin() would read, just fast on heavy
                # meshes (see the "Fast SkinCluster save/import" section
                # there); any vertex-count mismatch, or any error in the
                # fast path itself, falls back to mgear's own importSkin()
                # automatically.
                fast_import_skin(path)
            finally:
                if undo_was_on:
                    cmds.undoInfo(state=True)
            return True, ""
        except Exception as e:
            log_crash("Skin import: {}".format(path), e)
            return False, str(e)

    def _load_tweaker_module(self):
        """Dynamically (re)load PanelScripts/Tweaker.py, which sits beside
        the KRT package itself, so the tweaker algorithm can be hand-edited
        there later without touching KRT's own code (request #5). Returns
        the loaded module, or None (and a Script Editor warning) if it
        can't be found/loaded."""
        try:
            import importlib.util
            # NOTE: this file lives in KRT/workspace/, so go up TWO levels to reach the package root
            krt_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script_path = os.path.join(krt_dir, "PanelScripts", "Tweaker.py")
            if not os.path.isfile(script_path):
                cmds.warning("[KRT] PanelScripts/Tweaker.py not found next to the KRT package.")
                return None
            spec = importlib.util.spec_from_file_location("krt_panel_tweaker", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            traceback.print_exc()
            return None

    def run_reskin_logic(self, meshes, controls=None, scale_value=1.0):
        """Scale zero or more controls up, re-skin the given meshes, then put
        every control back exactly where it was - the SkinCluster panel's
        Re-Skin option.

        `controls` is a list. An empty/None list means "no scaling" - the
        caller (the panel's execute()) is the one deciding whether to call
        this at all based on whether any control was listed, since an
        empty list here still performs a plain re-skin if asked to.

        The point of the scaling is that the re-bind recomputes each
        influence's bind matrix from the CURRENT pose, so temporarily scaling
        a control changes what the rebound skin considers its rest state.
        Which is also why the restore is in a `finally`: if the re-skin
        itself throws halfway through, the rigger must not be left with a
        control silently stuck at 10x scale. Every control that exists gets
        its scale read up front - if any listed control doesn't exist, the
        whole call fails before anything is touched (no half-scaled scene).

        Returns (success, message)."""
        from ..utils import re_skin_meshes

        meshes = [m.strip() for m in (meshes or []) if m and m.strip()]
        if not meshes:
            meshes = cmds.ls(selection=True) or []
        if not meshes:
            return False, ("No meshes to re-skin - fill the SkinCluster panel's Meshes field "
                           "or select the skinned mesh(es) first.")

        controls = [c.strip() for c in (controls or []) if c and c.strip()]

        # Read every control's current scale before touching anything, so a
        # missing/unreadable control fails the whole call up front rather
        # than leaving earlier controls in the list scaled with no way back.
        originals = {}
        for control in controls:
            if not cmds.objExists(control):
                return False, "Re-Skin scale control '{}' does not exist in the scene.".format(control)
            try:
                originals[control] = cmds.getAttr(control + ".scale")[0]
            except Exception:
                return False, "Could not read the current scale of '{}'.".format(control)

        scaled = []  # controls actually changed, so only these get restored
        try:
            if controls and float(scale_value) != 1.0:
                for control in controls:
                    try:
                        cmds.setAttr(control + ".scale", scale_value, scale_value, scale_value)
                        scaled.append(control)
                    except Exception as e:
                        return False, ("Could not scale '{}' to {} (is it locked or connected?): {}"
                                       .format(control, scale_value, e))
            done, errors = re_skin_meshes(meshes)
        finally:
            # Always put every scaled control back, even when the re-skin
            # blew up half way. Only the ones actually moved, though - a
            # control with a locked scale shouldn't be poked (and warned
            # about) for a restore that isn't needed.
            for control in scaled:
                try:
                    cmds.setAttr(control + ".scale", *originals[control])
                except Exception:
                    cmds.warning("[KRT] Re-skin finished but '{}' could not be scaled back to {} "
                                 "- check it by hand.".format(control, tuple(originals[control])))

        if errors and not done:
            return False, "Re-skin failed:\n" + "\n".join(errors)
        msg = "Re-skinned {} mesh(es).".format(done)
        if controls:
            msg += " (scaled {} to {} during the rebind, then restored {})".format(
                ", ".join("'{}'".format(c) for c in controls), scale_value,
                "them" if len(controls) > 1 else "it")
        if errors:
            msg += "\nSkipped/failed:\n" + "\n".join(errors)
        cmds.warning("[KRT] " + msg)
        return True, msg

    def run_tweaker_logic(self, vertex_names, additional_meshes, use_bind_scale=True,
                           bind_scale=0.01, influence_radius=0.08, full_weight_radius=0.0001,
                           falloff=2.0):
        """Create a Tweaker setup (PanelScripts/Tweaker.py's own
        create_tweaker_setup) from `vertex_names`, then bind any
        `additional_meshes` to the same offsets via its
        add_additional_tweaker_meshes - the Tweaker panel's CREATE button.

        Every field here mirrors the values already used in the pipeline's
        real TweakerMain() calling convention (see the .txt example that
        was handed off): falloff_mode is always "center", control_size/
        offset/direction and follicle_scale_source are always the same -
        only the values that actually vary call to call (bind scale and
        whether the bind uses it, influence/full-weight radius, falloff)
        are exposed on the panel. bind_scale used to be a fixed 0.01 here;
        the real TweakerMain() now takes it as its own settable value, so
        the panel does too - 0.01 is just this function's default.
        """
        tweaker = self._load_tweaker_module()
        if not tweaker:
            return False, "Could not load PanelScripts/Tweaker.py - see Script Editor."
        if not vertex_names:
            return False, "No vertex names provided."

        try:
            tweaker.create_tweaker_setup(
                vertex_name=vertex_names,
                bind_scale=bind_scale,
                use_bind_scale=use_bind_scale,
                influence_radius=influence_radius,
                full_weight_radius=full_weight_radius,
                falloff=falloff,
                falloff_mode="center",
                control_size=0.02,
                control_offset_y=0.0,
                control_direction="-z",
                copy_plane_skin=True,
                follicle_scale_source="local_C0_ctl",
            )

            if additional_meshes:
                source_mesh = vertex_names[0].split(".vtx[")[0]
                other_sources = set(
                    v.split(".vtx[")[0] for v in vertex_names
                    if v.split(".vtx[")[0] != source_mesh)
                if other_sources:
                    cmds.warning(
                        "[KRT] Tweaker vertices span multiple meshes ({} and {}); "
                        "Additional Meshes will be bound to {} only.".format(
                            source_mesh, ", ".join(other_sources), source_mesh))
                tweaker.add_additional_tweaker_meshes(
                    additional_meshes=additional_meshes,
                    source_mesh=source_mesh,
                    bind_scale=bind_scale,
                    use_bind_scale=False,
                )
            return True, ""
        except Exception:
            return False, traceback.format_exc()

    def get_tweaker_target_meshes(self, vertex_names, additional_meshes):
        """Resolve the actual Tweaker-created duplicate mesh(es) - the ones
        that hold the real skinCluster, not the original source meshes -
        for a Tweaker panel's Vertices/Additional Meshes fields, via
        PanelScripts/Tweaker.py's own system_names() naming convention.
        Used to auto-fill the Tweaker panel's own Meshes field on a
        successful Create (SortablePanel._execute_tweaker), and as the
        Save Skin action's fallback when that Meshes field is left empty
        (e.g. an older panel/session that predates it)."""
        tweaker = self._load_tweaker_module()
        if not tweaker:
            return []

        sources = []
        seen = set()
        for v in vertex_names:
            src = v.split(".vtx[")[0]
            if src and src not in seen:
                seen.add(src); sources.append(src)
        for m in additional_meshes:
            if m and m not in seen:
                seen.add(m); sources.append(m)

        targets = []
        for src in sources:
            if not cmds.objExists(src):
                continue
            try:
                _, target, _, _, _, _, _ = tweaker.system_names(src)
            except Exception:
                continue
            if cmds.objExists(target) and target not in targets:
                targets.append(target)
        return targets
