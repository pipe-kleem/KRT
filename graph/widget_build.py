"""ModuleGraphWidget - build methods (mixin, auto-split from graph.py)."""
from ._shared import *
from .catalog import _find_guide_root
from .items import RigNode


class GraphBuildMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    # =====================================================
    # mGear Rig Plebe (character-template biped import) integration
    # =====================================================

    def _plebe_instance(self, node):
        """Build a headless mgear.shifter.plebes.Plebes() instance for
        `node`, with its selected character template already loaded.

        Plebes.set_template() also pushes the template's help text into a
        native Maya scrollField that only exists after .gui() has been run
        (self.help), so calling it directly on a bare Plebes() raises. We
        replicate just the JSON-loading half of it here instead.
        """
        try:
            from mgear.shifter import plebes as mg_plebes
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        plebe_template_path = self.workspace.resolve_path(node.plebe_template_path or "")   # Stage 41
        if not plebe_template_path or not os.path.exists(plebe_template_path):
            cmds.warning(f"'{node.display_title}' has no valid Plebe character template set. "
                         "Right-click it isn't available - use 'Change Template...' in the Node tab.")
            return None

        plebe = mg_plebes.Plebes()
        try:
            with open(plebe_template_path) as f:
                plebe.template = json.load(f)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to load Plebe character template: {node.plebe_template_path}")
            return None
        return plebe

    def plebe_import_fbx(self, node):
        """Right-click action: import the character FBX (mesh/skeleton) that
        will later be aligned/constrained/skinned to the Shifter rig."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.import_fbx()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to import character FBX - see Script Editor for details.")

    def plebe_fix_fbx_naming(self, node):
        """Right-click action: fix FBXASCxxx-mangled names left behind by
        some FBX importers, matching mGear Plebe's own 'Fix Naming' step."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.fix_fbx_naming()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to fix FBX naming - see Script Editor for details.")

    def plebe_constrain_to_rig(self, node):
        """Right-click action: constrain the imported character skeleton to
        the built Shifter rig, using the node's character template mapping."""
        plebe = self._plebe_instance(node)
        if not plebe:
            return
        try:
            plebe.constrain_to_rig()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to constrain character to rig - see Script Editor for details.")

    def plebe_skin_to_rig(self, node):
        """Right-click action: transfer the character's skin weights onto
        the Shifter rig's own joints. Select the skinned geometry first.

        mGear's own dialog exposes an 'Export Only' checkbox that skips the
        unbind/rebind step; this headless invocation always performs the
        full re-skin (equivalent to that checkbox being off), since there is
        no GUI checkbox to read here.
        """
        plebe = self._plebe_instance(node)
        if not plebe:
            return

        class _ExportOnlyShim(object):
            def getValue(self):
                return False

        plebe.export_only_check = _ExportOnlyShim()
        try:
            plebe.skin_to_rig()
        except Exception:
            traceback.print_exc()
            cmds.warning("Failed to skin character to rig - see Script Editor for details.")

    def _resolve_attach_parent(self, node, parent_node, parent_root, pm):
        """The actual PyNode `node` should attach under when its guide gets
        built: the specific 'Attach Under' locator if it currently exists,
        otherwise the parent's whole guide root, silently."""
        attach_target = node.parent_local_target
        if attach_target and cmds.objExists(attach_target):
            return pm.PyNode(attach_target)
        return pm.PyNode(parent_root)

    def _build_plebe_guide(self, node):
        """Plebe-node counterpart to build_node_guide(). Imports mGear's
        standard biped guide template ('Build Guides' equivalent for a
        Plebe node) and, if the node's 'Align Guides Automatically' toggle
        is on, aligns it using the node's character template mapping.

        mGear's biped guide root is built as literally "guide" (it is not
        parameterized like Shifter component guides). By default, if one
        already exists in the scene, it's adopted instead of importing a
        second one - only one Plebe biped can usefully share that name. If
        this node's "Build in Separate Guide Group" is checked, a new import
        is forced instead; Maya then auto-numbers the fresh group (guide1,
        guide2, ...) since "guide" is already taken, so the new root is
        found by diffing the scene's top-level guide transforms before/after
        the import rather than assuming the literal name "guide".
        """
        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        plebe = self._plebe_instance(node)
        if not plebe:
            return None

        try:
            from mgear.shifter import io as sh_io
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        if cmds.objExists("guide") and not node.build_separate_guide_group:
            cmds.warning("A guide named 'guide' already exists in the scene - adopting it "
                         f"for '{node.display_title}' instead of importing a new biped template.")
            node.maya_guide_root = cmds.ls("guide", long=True)[0]
        else:
            before = {n for n in (cmds.ls(assemblies=True, long=True) or [])
                     if cmds.attributeQuery("ismodel", node=n, exists=True)}
            try:
                sh_io.import_sample_template("biped.sgt")
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Failed to import mGear's biped guide template for '{node.display_title}'.")
                return None

            after = {n for n in (cmds.ls(assemblies=True, long=True) or [])
                    if cmds.attributeQuery("ismodel", node=n, exists=True)}
            new_roots = list(after - before)
            if new_roots:
                node.maya_guide_root = new_roots[0]
            elif cmds.objExists("guide"):
                # Fallback for older mGear builds where the diff above finds
                # nothing (e.g. "ismodel" not queryable pre-creation) but a
                # plain "guide" still appeared.
                node.maya_guide_root = cmds.ls("guide", long=True)[0]

        if not node.maya_guide_root or not cmds.objExists(node.maya_guide_root):
            cmds.warning("Biped guide import did not produce a recognizable guide root - see Script Editor.")
            node.maya_guide_root = None
            return None
        node.update_display()
        self._invalidate_attach_points_cache()

        # Auto-replace this biped's control shapes from its Control Shapes
        # Library, right away - before align/custom-script - so anything
        # that inspects the guide afterward already sees the real shapes.
        self.apply_control_shapes_library_to(node.maya_guide_root, self.workspace.resolve_path(node.control_shapes_library or ""))

        if node.align_guides_auto:
            try:
                plebe.align_guides()
            except Exception:
                traceback.print_exc()
                cmds.warning(f"Auto-align failed for '{node.display_title}' - guide was still "
                             "imported. See Script Editor for details.")

        # Stage 28: reapply any hand-moved guide positions LAST, after
        # align - so a saved manual tweak (the whole point of capturing it)
        # isn't immediately overwritten by the template's own auto-align.
        self.apply_node_guide_positions(node)

        self.run_node_custom_script(node, "guides")
        return node.maya_guide_root

    def _build_custom_sgt_guide(self, node, mg_shifter, pm):
        """Custom-.sgt-node counterpart to build_node_guide(). Imports the
        user's own saved partial guide template (an mGear component .sgt
        file they hand-tweaked and re-exported from Shifter's own Guide
        Manager) via mgear.shifter.io.import_partial_guide(), grafting it
        under this node's resolved parent - same "Attach Under"/
        parent_local_target handling build_node_guide uses for a normal
        catalog component.

        Unlike a catalog component (drawn fresh from a blank ComponentGuide
        via drawFromUI), a .sgt file already carries its own fully-exported
        guide dict - side, name, connector, even its own control-shape
        buffer curves - from whenever it was saved, so there's no
        comp_side/comp_name/connector-inheritance step here; the file's own
        settings win as-is. import_partial_guide()/draw_guide() don't hand
        back the new root's name directly, so it's found the same way
        _build_plebe_guide finds its import: diffing the scene's transforms
        before/after, then keeping only whichever new node's parent already
        existed (the actual top of the freshly-grafted subtree).
        """
        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        custom_sgt_path = self.workspace.resolve_path(node.custom_sgt_path or "")   # Stage 41
        if not custom_sgt_path or not os.path.exists(custom_sgt_path):
            cmds.warning(f"'{node.display_title}' has no valid .sgt file set - "
                         "use Change File... in the Node tab to pick one.")
            return None

        try:
            from mgear.shifter import io as sh_io
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return None

        # Same parent resolution build_node_guide uses for a normal
        # component: recursively build the graph parent's guide first, then
        # prefer a specific chosen locator (Attach Under) over its whole
        # guide root.
        parent_node = self.get_parent_node(node)
        parent_pynode = None
        if parent_node:
            parent_root = parent_node.maya_guide_root or self.build_node_guide(parent_node, mg_shifter, pm)
            if parent_root and cmds.objExists(parent_root):
                parent_pynode = self._resolve_attach_parent(node, parent_node, parent_root, pm)
        elif not node.build_separate_guide_group:
            existing_root = _find_guide_root()
            if existing_root:
                parent_pynode = pm.PyNode(existing_root)
        # else: no graph parent and "Build in Separate Guide Group" is on
        # (or nothing exists yet) - leave parent_pynode None so draw_guide()
        # creates its own fresh top-level guide hierarchy.

        before = set(cmds.ls(type="transform", long=True) or [])

        try:
            sh_io.import_partial_guide(filePath=custom_sgt_path, initParent=parent_pynode)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to import custom .sgt guide for '{node.display_title}' - "
                         "see Script Editor. (If it was grafted onto an existing guide, make "
                         "sure Attach Under points at an actual guide locator, not just the "
                         "whole guide root.)")
            return None

        after = set(cmds.ls(type="transform", long=True) or [])
        new_nodes = after - before
        if not new_nodes:
            cmds.warning(f"Custom .sgt import for '{node.display_title}' did not add any new nodes - see Script Editor.")
            return None

        # The top of the freshly-grafted subtree: a new node whose parent is
        # NOT itself one of the new nodes (either it's a fresh top-level
        # assembly, or it hangs off whatever already-existing parent we
        # passed in).
        roots = []
        for n in new_nodes:
            parents = cmds.listRelatives(n, parent=True, fullPath=True)
            if not parents or parents[0] not in new_nodes:
                roots.append(n)
        # Prefer one that's actually mGear guide-flavored (has ismodel or
        # comp_type) over any incidental new transform - and, matching
        # mGear's own guide_manager.inspect_settings() (which walks UP from
        # a selection checking comp_type before ever falling back to
        # ismodel), a comp_type root wins over an ismodel root when a .sgt
        # import produces both as siblings among `roots`. Getting this
        # backwards is exactly why a Custom Module node could end up with
        # maya_guide_root pointed at a plain model/group node instead of its
        # real component root - which has no comp_type, so the "⚙ Settings"
        # button (open_mgear_component_settings) never had anything to key
        # off and the Main/Component Settings tabs stayed blank even
        # though the guide itself built and drew correctly. `roots` (and
        # `new_nodes`) come from set subtraction, so their iteration order
        # isn't guaranteed - sorting keeps which one gets picked stable
        # across runs when more than one candidate of the same kind exists.
        preferred_comp = sorted(r for r in roots
                                if cmds.attributeQuery("comp_type", node=r, exists=True))
        preferred_model = sorted(r for r in roots
                                 if cmds.attributeQuery("ismodel", node=r, exists=True))
        node.maya_guide_root = (preferred_comp or preferred_model or sorted(roots) or sorted(new_nodes))[0]

        if not node.maya_guide_root or not cmds.objExists(node.maya_guide_root):
            cmds.warning(f"Custom .sgt import for '{node.display_title}' did not produce a recognizable guide root.")
            node.maya_guide_root = None
            return None
        node.update_display()
        self._invalidate_attach_points_cache()
        self.apply_node_guide_positions(node)

        self.run_node_custom_script(node, "guides")
        return node.maya_guide_root

    def _build_custom_script_node(self, node, mg_shifter, pm):
        """Stage 26: Custom-Script-node counterpart to build_node_guide() /
        _build_custom_sgt_guide() - except this node type never imports or
        draws any guide at all. Its parent chain is still built first,
        exactly like a real component, so it still holds its place in build
        order (Build Till Here, ordered LOD builds, etc all still see it in
        sequence) - it just never sets maya_guide_root, since there's no
        guide transform to point at.

        Because of that, this node can NOT be used as an "Attach Under"
        parent for a real component below it in the graph - there's no
        guide locator to attach to, so a child parented under it just falls
        back to whatever whole-scene guide root already exists (same as
        having no parent at all). It's meant as a standalone/leaf step for
        the script's own side effects (scene cleanup, an export, calling
        into another tool, enforcing order between two branches, etc), not
        as a hierarchy node other guides graft onto.

        Stage 30: by default this still waits on its own graph-parent chain
        (exactly the behavior above), but the user can instead pick ANY
        other node in the graph as the thing to wait on
        (node.custom_script_trigger_node_uuid, set via CustomScriptDialog's
        "Trigger after module" combo) - useful when the script's real
        dependency isn't this node's own wire-parent (e.g. two unrelated
        branches where one still needs to run after the other). When set,
        that chosen node's guide is built first instead of the graph
        parent's. A stale/deleted target (uuid no longer matches any node
        in the scene) falls back to the graph-parent behavior with a
        warning, rather than silently building nothing.
        """
        trigger_node = None
        if node.custom_script_trigger_node_uuid:
            trigger_node = next(
                (n for n in self.graph_view.scene.items()
                 if isinstance(n, RigNode) and n.uuid == node.custom_script_trigger_node_uuid),
                None,
            )
            if trigger_node is None:
                cmds.warning(
                    f"'{node.display_title}': its chosen trigger module no longer exists in the "
                    "graph - falling back to its own graph parent. Re-pick a trigger module in "
                    "Custom Script settings if this wasn't intended."
                )

        if trigger_node is not None:
            if not (trigger_node.maya_guide_root and cmds.objExists(trigger_node.maya_guide_root)):
                self.build_node_guide(trigger_node, mg_shifter, pm)
        else:
            parent_node = self.get_parent_node(node)
            if parent_node and not (parent_node.maya_guide_root and cmds.objExists(parent_node.maya_guide_root)):
                self.build_node_guide(parent_node, mg_shifter, pm)

        self.run_node_custom_script(node, "guides")
        return None

    # =====================================================
    # Real mGear guide / rig building, driven by the graph
    # =====================================================

    def build_node_guide(self, node, mg_shifter, pm):
        """Ensure `node`'s mGear component guide exists in the scene
        (recursively building its parent chain first), returning the long
        name of its guide root transform, or None on failure/cancel (or, for
        a Stage 26 Custom Script node, always - it has no guide of its own).

        This is the single source of truth used by both the graph editor's
        "Build Guides" button and the Rig Builder Workspace module panel's
        "Add from Graph Editor" bubbles.
        """
        if node.module_type == PLEBE_MODULE_TYPE:
            return self._build_plebe_guide(node)
        if node.module_type == CUSTOM_SGT_MODULE_TYPE:
            return self._build_custom_sgt_guide(node, mg_shifter, pm)
        if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
            return self._build_custom_script_node(node, mg_shifter, pm)

        if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
            return node.maya_guide_root

        parent_node = self.get_parent_node(node)
        parent_pynode = None
        if parent_node:
            parent_root = parent_node.maya_guide_root or self.build_node_guide(parent_node, mg_shifter, pm)
            if parent_root and cmds.objExists(parent_root):
                # If a specific guide locator on the parent was chosen (the
                # Attach Under dropdown, or the popup shown right after
                # dragging a connection) - e.g. a "chest" locator rather than
                # the whole spine guide - attach there instead. Same effect
                # as dragging a component onto a specific locator in
                # Shifter's own Guide Manager outliner; the inheritance walk
                # just below climbs back up from whichever transform this is
                # to find the owning component's side/connector/etc.
                parent_pynode = self._resolve_attach_parent(node, parent_node, parent_root, pm)

        rig_guide = mg_shifter.guide.Rig()
        comp_guide = rig_guide.getComponentGuide(node.module_type)
        if not comp_guide:
            cmds.warning(f"Unknown mGear Shifter component type: {node.module_type}")
            return None

        if not parent_pynode:
            # "Build in Separate Guide Group" forces a brand-new top-level
            # guide even if one already exists in the scene, instead of
            # merging into it - Maya auto-numbers the new group (guide1,
            # guide2, ...) since the name "guide" is already taken.
            existing_root = None if node.build_separate_guide_group else _find_guide_root()
            if existing_root:
                rig_guide.model = pm.PyNode(existing_root)
                parent_pynode = rig_guide.model
            else:
                rig_guide.initialHierarchy()
                parent_pynode = rig_guide.model
        else:
            # Same inheritance Shifter's own "Draw Component" applies when a
            # component is dropped onto an existing one.
            walker = parent_pynode
            while walker:
                if walker.hasAttr("ismodel"):
                    break
                if walker.hasAttr("comp_type"):
                    p_type = walker.attr("comp_type").get()
                    if p_type in comp_guide.connectors:
                        comp_guide.setParamDefValue("connector", p_type)
                    comp_guide.setParamDefValue("comp_side", walker.attr("comp_side").get())
                    comp_guide.setParamDefValue("ui_host", walker.attr("ui_host").get())
                    comp_guide.setParamDefValue("ctlGrp", walker.attr("ctlGrp").get())
                    break
                walker = walker.getParent()

        # The side chosen on the graph node always wins over whatever was
        # just inherited (or the component's own default).
        comp_guide.setParamDefValue("comp_side", node.side)
        if node.custom_name and node.custom_name != node.module_type:
            comp_guide.setParamDefValue("comp_name", node.custom_name)

        # Stage 27: mGear's own "Main Settings" fields, fed in from the Node
        # tab exactly like mGear's own Settings dialog would set them, before
        # drawFromUI actually draws the guide. ui_host/ctlGrp only override
        # the just-inherited value above when the user actually set one on
        # this node - an empty field keeps the existing inherit-from-parent
        # behavior (unchanged since before Stage 27) rather than clearing it.
        comp_guide.setParamDefValue("comp_index", node.comp_index)
        comp_guide.setParamDefValue("connector", node.connector)
        comp_guide.setParamDefValue("useIndex", node.use_joint_index)
        comp_guide.setParamDefValue("parentJointIndex", node.parent_joint_index)
        comp_guide.setParamDefValue("joint_names", node.joint_names)
        comp_guide.setParamDefValue("joint_rot_offset_x", node.joint_rot_offset_x)
        comp_guide.setParamDefValue("joint_rot_offset_y", node.joint_rot_offset_y)
        comp_guide.setParamDefValue("joint_rot_offset_z", node.joint_rot_offset_z)
        if node.ui_host:
            comp_guide.setParamDefValue("ui_host", node.ui_host)
        if node.ctl_group:
            comp_guide.setParamDefValue("ctlGrp", node.ctl_group)
        comp_guide.setParamDefValue("Override_Color", node.override_colors)
        comp_guide.setParamDefValue("Use_RGB_Color", node.use_rgb_colors)
        comp_guide.setParamDefValue("color_fk", node.color_fk_index)
        comp_guide.setParamDefValue("color_ik", node.color_ik_index)
        comp_guide.setParamDefValue("RGB_fk", list(node.color_fk_rgb))
        comp_guide.setParamDefValue("RGB_ik", list(node.color_ik_rgb))

        try:
            ok = comp_guide.drawFromUI(parent_pynode, False)
        except Exception:
            traceback.print_exc()
            cmds.warning(f"Failed to draw guide for '{node.module_type}' ({node.display_title}).")
            return None

        if not ok or not comp_guide.root:
            # User cancelled a modal step (e.g. chain section-count dialog).
            return None

        new_root = comp_guide.root.longName()
        node.maya_guide_root = new_root
        node.update_display()
        # This node's own new root, AND its parent's root (this guide just
        # became one more of the parent's descendants, so a fresh "Attach
        # Under" list on the parent needs to see it too).
        self._invalidate_attach_points_cache()
        self.apply_node_guide_positions(node)

        # Note: the Control Shapes Library is only applied for a Plebe biped
        # node (see _build_plebe_guide) - its "*_controlBuffer" curves are
        # named after biped UI controls (legUI_L0_ctl, spineUI_C0_ctl, ...)
        # that only exist on a full biped guide, so applying it here for an
        # arbitrary single Shifter component would just be a wasted import.
        self.run_node_custom_script(node, "guides")
        return new_root

    def execute_graph_nodes(self, action):
        selected_items = self.workspace.rig_list.selectedItems()
        uuid_to_node = {item.uuid: item for item in self.graph_view.scene.items() if isinstance(item, RigNode)}

        if not selected_items:
            if action != "rig":
                # "Build Guides" still needs an explicit sidebar pick - there's
                # no sensible "build every guide in the graph" fallback for it
                # the way there is for "Build Modules" below.
                cmds.warning("No modules selected in the left sidebar to build!")
                return
            # "Build Modules (From Sidebar Selection)" with nothing actually
            # selected: instead of doing nothing, build every module whose
            # guide is currently built in the scene (i.e. everything sitting
            # under a guide group's "ismodel" root right now) - this mirrors
            # what Shifter's own "build from all guides in the scene" does,
            # just scoped to modules this graph already knows about.
            nodes = [n for n in uuid_to_node.values()
                     if n.maya_guide_root and cmds.objExists(n.maya_guide_root)]
            if not nodes:
                cmds.warning("Nothing selected in the left sidebar, and no modules have a "
                             "built guide in the scene to build from either.")
                return
            cmds.warning(f"No modules selected in the sidebar - building all {len(nodes)} "
                         "module(s) with an existing guide in the scene instead.")
        else:
            selected_uuids = {item.data(QtCore.Qt.UserRole) for item in selected_items}

            # Build in the order the modules were actually selected (tracked in
            # workspace.selection_order as selection changes), not scene/list
            # order - falling back to rig_list's own order for anything that
            # somehow isn't in the tracked history.
            ordered_uuids = [u for u in self.workspace.selection_order if u in selected_uuids]
            ordered_uuids += [u for u in selected_uuids if u not in ordered_uuids]

            nodes = [uuid_to_node[u] for u in ordered_uuids if u in uuid_to_node]

        if not nodes:
            cmds.warning("No matching module nodes found in the graph editor to build!")
            return

        try:
            from mgear import shifter as mg_shifter
            import mgear.pymaya as pm
        except ImportError:
            cmds.error("mGear is not installed/loaded in this Maya session.")
            return

        # Still guarantees a parent is ever built before its selected child
        # (guides can't attach to a guide that doesn't exist yet) - but this
        # is a stable reorder, so two selected nodes with no hierarchy
        # relationship to each other keep the relative order you selected
        # them in.
        nodes = self._sorted_by_hierarchy(nodes)

        if action == "guides":
            cmds.undoInfo(openChunk=True)
            # Stage 31: hold the placement watcher while guides are actually
            # being drawn - a progress dialog's processEvents() can otherwise
            # fire a tick mid-build and flash red off a half-built guide.
            self._pos_watch_suspended = True
            try:
                for node in nodes:
                    self.build_node_guide(node, mg_shifter, pm)
            finally:
                self._pos_watch_suspended = False
                cmds.undoInfo(closeChunk=True)
            self.workspace.refresh_module_list()
            self.update_attr_editor()
            # Stage 31, request #3: any Guide Settings the rigger set before
            # a guide existed go onto the new guide FIRST - refresh_from_
            # scene() would otherwise pull mGear's freshly-built defaults
            # straight back over them.
            self.guide_settings_panel.push_pending_to_scene()
            self.guide_settings_panel.refresh_from_scene()
            # Freshly built = nothing has been moved since, so settle the
            # light immediately rather than waiting for the next tick.
            self._refresh_position_watch()

        elif action == "rig":
            # Stage 26: a Custom Script node has no guide by design, so it
            # never belongs in Shifter's own buildFromSelection() and was
            # never really "missing a guide" to begin with - it just runs
            # its own script (if set to fire at "modules") alongside
            # whatever real components get built this pass.
            script_only_nodes = [n for n in nodes if n.module_type == CUSTOM_SCRIPT_MODULE_TYPE]
            roots, missing = [], []
            for node in nodes:
                if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                    continue
                if node.maya_guide_root and cmds.objExists(node.maya_guide_root):
                    roots.append(node.maya_guide_root)
                else:
                    missing.append(node.display_title)

            # Stage 30 fix: "i am checking in scene. the script havent run"
            # - a script-only node set to run "After Build Modules" WITH a
            # Trigger-after-module dependency was reporting a trigger note
            # that meant nothing in practice: this branch ran the script
            # for any selected script-only node unconditionally, whether or
            # not its chosen trigger module was actually part of THIS same
            # build pass. If the trigger module wasn't separately selected
            # (or its guide didn't even exist yet), the script still fired
            # right away - the "waits for X" label was aspirational, not
            # real. Force the trigger target's guide to exist and its root
            # into THIS pass's Shifter build selection (if it isn't there
            # already) before the script gets its turn below, so "waits
            # for X" is actually true - X gets built, in this exact same
            # pass, before the script runs.
            for node in script_only_nodes:
                if node.custom_script_when != "modules" or not node.custom_script_trigger_node_uuid:
                    continue
                target = self.get_node_by_uuid(node.custom_script_trigger_node_uuid)
                if not target:
                    cmds.warning(f"'{node.display_title}': its Trigger-after module no longer exists in "
                                 "the graph - its script will run without waiting on anything this pass.")
                    continue
                if target.module_type == CUSTOM_SCRIPT_MODULE_TYPE:
                    continue  # another script-only node has nothing to "build"
                target_root = target.maya_guide_root if (target.maya_guide_root and cmds.objExists(target.maya_guide_root)) \
                    else self.build_node_guide(target, mg_shifter, pm)
                if target_root and target_root not in roots:
                    roots.append(target_root)

            if missing:
                cmds.warning("Skipped (guide not built yet - run 'Build Guides' first): " + ", ".join(missing))
            if not roots and not script_only_nodes:
                cmds.warning("None of the selected modules have a built guide yet.")
                return

            if roots:
                cmds.select(roots, replace=True)
                try:
                    mg_shifter.Rig().buildFromSelection()
                except Exception:
                    traceback.print_exc()
                    cmds.error("Shifter build failed - see Script Editor for details.")
                    return

            for node in nodes:
                if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE or node.maya_guide_root in roots:
                    self.run_node_custom_script(node, "modules")
                    self.run_node_auto_scripts(node, "modules")
