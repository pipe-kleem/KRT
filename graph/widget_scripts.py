"""ModuleGraphWidget - scripts methods (mixin, auto-split from graph.py)."""
from ._shared import *
from .dialogs import AutoScriptEditDialog, CustomScriptDialog
from .items import RigNode


class GraphScriptsMixin(object):
    """Mixed into ModuleGraphWidget; all methods here expect to run on a ModuleGraphWidget instance."""


    def _update_script_label(self, node):
        """Stage 30: 'i think custom script not running. i need prof that it
        is running.' - a plain colored dot, impossible to miss, giving an
        unambiguous answer at a glance instead of having to infer it from
        wording: 🔴 red = last run actually failed (unchanged - already had
        its own bold red text), 🟢 green = the script has run successfully
        at least once (custom_script_ran, now tracked for every node type
        with a script, not just Custom Script nodes - see
        run_node_custom_script), 🔵 blue = a script IS attached and set to
        run, but hasn't fired yet this session (e.g. its trigger point
        hasn't happened, or the guide/rig hasn't been (re)built since the
        script last changed - see CustomScriptDialog.apply_to_node, which
        resets custom_script_ran back to False whenever the code changes,
        since a past 'ran' only proves the OLD code ran)."""
        has_error = bool(node.custom_script_last_error)
        self.btn_script_error.setVisible(has_error)
        self.btn_script_reset.setVisible(has_error)
        if has_error:
            self.lbl_script_state.setText("🔴 Script: last run FAILED - see Show Error")
            self.lbl_script_state.setStyleSheet("color: #ff8888; border: none; font-weight: bold;")
        elif node.custom_script_when == "none" or not node.custom_script_code.strip():
            self.lbl_script_state.setText("Script: none")
            self.lbl_script_state.setStyleSheet("color: #aaa; border: none;")
        else:
            when_label = "after Build Guides" if node.custom_script_when == "guides" else "after Build Modules"
            trigger_note = ""
            if node.module_type == CUSTOM_SCRIPT_MODULE_TYPE and node.custom_script_trigger_node_uuid:
                target = next(
                    (n for n in self.graph_view.scene.items()
                     if isinstance(n, RigNode) and n.uuid == node.custom_script_trigger_node_uuid),
                    None,
                )
                # Plain name+side only - NOT target.display_title, which
                # carries the TARGET's own icon/checkmark/script-status dot
                # baked into its text. Using display_title here made this
                # node's OWN status line show a stray unrelated green/blue
                # dot that actually belonged to the target node, not to
                # this trigger relationship - confusing regardless of
                # whether this node's own script had run or not.
                trigger_note = f", waits for '{target.custom_name} [{target.side}]'" if target \
                    else ", waits for a deleted module"
            dot = "🟢" if node.custom_script_ran else "🔵"
            ran_note = "has run ✓" if node.custom_script_ran else "has NOT run yet this session"
            self.lbl_script_state.setText(
                f"{dot} Script: {node.custom_script_lang.upper()}, runs {when_label}{trigger_note} - {ran_note}"
            )
            self.lbl_script_state.setStyleSheet(
                "color: #8fd694; border: none;" if node.custom_script_ran else "color: #6fb8ff; border: none;"
            )

    def open_custom_script_dialog(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to attach a custom script to.")
            return
        node = selected[0]
        all_nodes = [i for i in self.graph_view.scene.items() if isinstance(i, RigNode) and i is not node]
        dialog = CustomScriptDialog(node, self.workspace.main_window, all_nodes=all_nodes)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            dialog.apply_to_node()
            self._update_script_label(node)
            self.workspace.refresh_module_list()

    def edit_fan_joint_script(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to edit its Fan Joint script.")
            return
        node = selected[0]
        dialog = AutoScriptEditDialog("Fan Joint Script - {}".format(node.display_title),
                                       node.fan_joint_script, DEFAULT_FAN_JOINT_SCRIPT, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            node.fan_joint_script = dialog.result_code()

    def edit_stretchy_joint_script(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            cmds.warning("Select exactly one module node to edit its Stretchy Joint script.")
            return
        node = selected[0]
        dialog = AutoScriptEditDialog("Stretchy Joint Script - {}".format(node.display_title),
                                       node.stretchy_joint_script, DEFAULT_STRETCHY_JOINT_SCRIPT, self.workspace.main_window)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            self._push_undo_snapshot()
            node.stretchy_joint_script = dialog.result_code()

    def show_script_error_dialog(self):
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1 or not selected[0].custom_script_last_error:
            return
        node = selected[0]
        from .widgets import ErrorDialog
        dialog = ErrorDialog("Custom Script Error", f"Custom script failed - {node.display_title}",
                             node.custom_script_last_error, self.workspace.main_window, allow_retry=True)
        result = dialog.exec() if IS_PYSIDE6 else dialog.exec_()
        if getattr(dialog, "retry", False):
            self.run_node_custom_script(node, node.custom_script_when)
            self._update_script_label(node)

    def reset_script_error(self):
        """Restore the script status back to normal without re-running -
        matches the Rig Builder Workspace panel's own ↺ reset button.
        Editing and re-saving the script (see CustomScriptDialog.apply_to_node)
        clears the same flag automatically, as an alternative to this."""
        selected = [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]
        if len(selected) != 1:
            return
        node = selected[0]
        node.custom_script_last_error = ""
        node.update_display()
        self._update_script_label(node)

    def run_node_custom_script(self, node, phase):
        """Run `node`'s attached script if it is set to fire at `phase`
        ('guides' or 'modules'). Failures are reported but never abort the
        larger build - a broken per-module script shouldn't nuke a batch build.
        A failure is recorded on the node (⚠ marker on the graph, red border,
        "Show Error"/"↺" controls in the Node tab) so it's discoverable after
        the fact rather than only in the moment via the Script Editor."""
        if node.custom_script_when != phase or not node.custom_script_code.strip():
            return
        try:
            if node.custom_script_lang == "mel":
                import maya.mel as mel
                mel.eval(node.custom_script_code)
            else:
                exec(node.custom_script_code, self.workspace.shared_namespace)
        except Exception:
            node.custom_script_last_error = traceback.format_exc()
            traceback.print_exc()
            cmds.warning(f"Custom script failed for '{node.display_title}' ({phase}) - see Script Editor "
                         "or the Node tab's 'Show Error' button.")
        else:
            node.custom_script_last_error = ""
            # Stage 26 introduced this only for a Custom Script node (which
            # has no guide of its own, so this was its only "did it actually
            # run" signal). Stage 30: "i need proof that it is running" -
            # now tracked for EVERY node type with an attached script, not
            # just Custom Script nodes, so any component's Scripts tab can
            # show a real ran/not-run/error status instead of just an error
            # state. See _update_script_label / RigNode.update_display for
            # where this actually gets shown.
            node.custom_script_ran = True
        node.update_display()
        if node in [i for i in self.graph_view.scene.selectedItems() if isinstance(i, RigNode)]:
            self._update_script_label(node)

    def run_node_auto_scripts(self, node, phase):
        """Stage 19: Fan Joint / Stretchy Joint, each independently toggled
        and independently editable (Node tab, Plebe nodes only). Both always
        run as Python at the 'modules' phase (right after this node's rig is
        actually built) - there's no per-script "when" picker like the
        custom script has, since these act on real built joints and only
        ever make sense at that one point. Only meaningful for a Plebe node;
        a regular Shifter component or Custom Module node never has these
        enabled (module_type check below is the actual guard, not just the
        Node tab hiding the checkboxes)."""
        if phase != "modules" or node.module_type != PLEBE_MODULE_TYPE:
            return
        for enabled, script, label in (
            (node.fan_joint_enabled, node.fan_joint_script, "Fan Joint"),
            (node.stretchy_joint_enabled, node.stretchy_joint_script, "Stretchy Joint"),
        ):
            if not enabled or not script.strip():
                continue
            try:
                exec(script, self.workspace.shared_namespace)
            except Exception:
                traceback.print_exc()
                cmds.warning(f"{label} script failed for '{node.display_title}' - see Script Editor.")

    def browse_control_shapes_library(self):
        start = self.workspace.resolve_path(self.edit_control_shapes_lib.text().strip())
        start_dir = os.path.dirname(start) if start else self.workspace.rig_root()
        res = cmds.fileDialog2(
            fm=1, ff="Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb);;All Files (*.*)",
            caption="Choose Control Shapes Library",
            dir=start_dir if os.path.exists(start_dir) else "")
        if res:
            self.edit_control_shapes_lib.setText(self.workspace.relativize_path(res[0]))   # Stage 41
            # setText() alone doesn't fire editingFinished, so the node
            # wouldn't otherwise pick up a Browse-selected path until some
            # unrelated edit happened to trigger a save.
            self.on_attr_changed()

    def apply_control_shapes_library_to(self, guide_model, lib_path):
        """Merge `lib_path`'s Control Shapes Library into `guide_model`'s
        controllers_org. Safe to call repeatedly - skips entirely once
        already applied for this exact library path."""
        if not lib_path or not guide_model or not cmds.objExists(guide_model):
            return
        marker_attr = guide_model + ".krt_ctlShapesLibApplied"
        try:
            if cmds.attributeQuery("krt_ctlShapesLibApplied", node=guide_model, exists=True):
                if cmds.getAttr(marker_attr) == lib_path:
                    return
            else:
                cmds.addAttr(guide_model, longName="krt_ctlShapesLibApplied", dataType="string")
            apply_control_shapes_library(lib_path, guide_model)
            cmds.setAttr(marker_attr, lib_path, type="string")
        except Exception:
            traceback.print_exc()
            cmds.warning("Could not apply Control Shapes Library - see Script Editor.")
