"""KRT_02 restructure: split big modules into packages (+ mixins for giant classes).
Text slicing is line-based on AST ranges so comments/formatting survive."""
import ast, os, re, sys, builtins, shutil

SRC = os.path.expanduser("~/mnt/KRT_02")
OUT = os.path.expanduser("~/krt_split")
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__class__"}

# ----------------------------------------------------------------------------
# PLAN: package -> {file: [top-level names]}, and class splits
# ----------------------------------------------------------------------------
PLAN = {
 "utils": {
   "paths": ["get_versioned_path"],
   "control_shapes": ["export_control_shapes","import_control_shapes","find_guide_model","apply_control_shapes_library"],
   "materials": ["_is_intermediate","_mesh_shapes_for_export","_compress_face_ranges","_shading_engines_for_shape_api",
                 "_shading_engines_for_shape_fallback","_shading_engines_for_mesh","_walk_shader_network","_capture_node_data",
                 "_capture_node_connections","export_material_data","_ensure_material_node","_set_material_attr",
                 "_resolve_mesh_by_short_name","import_material_data"],
   "skin": ["canonical_skincluster_name","find_mesh_skincluster","ensure_skin_influences","_load_skin_file_data",
            "read_skin_file_meshes","ensure_skin_ready_for_import","find_mismatched_skinclusters","rename_mismatched_skinclusters",
            "_bind_poses_for_joints","re_skin_meshes"],
   "crash_log": ["_krt_log_dir","_crash_log_path","_session_marker_path","log_crash","mark_session_start",
                 "mark_session_clean_exit","check_last_session_health"],
   "fast_skin": ["_fast_collect_influence_weights","_fast_apply_influence_weights","fast_export_skin","fast_import_skin"],
 },
 "dialogs": {
   "save_dialogs": ["AdvancedSaveDialog","SaveCommentDialog","BuildProgressDialog","SimpleCodeEditorDialog"],
   "path_tools": ["PathReplaceDialog","CreateFolderStructureDialog","_looks_like_file_path","collect_json_file_paths","replace_json_file_paths"],
   "ayon_publish": ["source_file_hash","AyonPublishDialog"],
 },
 "widgets": {
   "style": ["type_accent","type_icon","type_bg_tint","style_readonly_path_field","is_script_file_ref","panel_run_label","prompt_skincluster_naming_check"],
   "dialogs": ["ErrorDialog","GraphNodeOrderDialog"],
   "flow_layout": ["FlowLayout"],
   "drag_drop": ["DragDropContainer"],
   "cache_mixin": ["CacheMixin"],
   "tweaker_group": ["TweakerVertexGroup","_NoteVerticalResizeHandle"],
   "sortable_panel": ["SortablePanel"],
   "bubble_panel": ["ModuleBubble","_BubbleDropGap","BubbleDropArea","SortableBubblePanel"],
   "lod_loader": ["LodLoaderBubble","LodLoaderPanel"],
   "playblast_widgets": ["PBCameraViewWidget","PBWipeCompareWidget"],
 },
 "graph": {
   "catalog": ["_MGEAR_COMPONENT_CACHE","list_mgear_components","clear_mgear_component_cache","list_plebe_templates","_find_guide_root"],
   "items": ["RigWire","bezier_path","RigNode"],
   "dialogs": ["CustomScriptDialog","AutoScriptEditDialog","PlebeTemplateDialog","NodeSearchPopup"],
   "view": ["NodeGraphView"],
   "guide_settings": ["CustomStepListEditor","GuideSettingsPanel"],
   "widget": ["ModuleGraphWidget"],
 },
 "workspace": {
   "core": ["CurrentPageStackedWidget","SessionWorkspace"],
 },
}

# Giant classes -> mixin groups. Unlisted methods stay in the core class.
CLASS_SPLITS = {
 ("graph","ModuleGraphWidget"): {
   "positions": ["_make_apply_positions_row","clear_selected_node_guide_positions","capture_node_guide_positions",
      "capture_all_guide_positions","apply_node_guide_positions","_apply_node_guide_positions","capture_all_live_state",
      "_guide_transforms","_guide_key","_read_guide_placement","_capture_position_baseline","_node_position_reference",
      "_node_position_moved","_set_position_watch_ui","_refresh_position_watch","on_position_watch_clicked"],
   "component_settings": ["_refresh_mgear_settings_group","_static_locator_names_for_type","_list_attach_points",
      "_invalidate_attach_points_cache","capture_node_component_settings","apply_node_component_settings",
      "sync_node_main_settings_from_guide","_refresh_attach_point_combo","_snap_attach_point_text","on_attach_point_combo_changed",
      "open_mgear_component_settings","change_selected_node_template","_style_rgb_button","pick_component_rgb_color",
      "grab_selected_as_ui_host","edit_selected_node_joint_names","change_selected_node_sgt_path","apply_main_settings_live"],
   "scripts": ["_update_script_label","open_custom_script_dialog","edit_fan_joint_script","edit_stretchy_joint_script",
      "show_script_error_dialog","reset_script_error","run_node_custom_script","run_node_auto_scripts",
      "browse_control_shapes_library","apply_control_shapes_library_to"],
   "io": ["compute_default_guide_path","refresh_default_guide_path","_guide_browse_start_dir","browse_path",
      "_populate_guide_versions_menu","show_guide_path_menu","save_all_guides","load_all_guides","serialize_node",
      "deserialize_node","get_graph_config_data","_apply_graph_config_data"],
   "undo": ["_clear_undo_history","_push_undo_snapshot","_cancel_last_undo_snapshot","_maybe_snapshot_before_edit",
      "_restore_selection_by_uuid","undo","redo"],
   "build": ["_plebe_instance","plebe_import_fbx","plebe_fix_fbx_naming","plebe_constrain_to_rig","plebe_skin_to_rig",
      "_resolve_attach_parent","_build_plebe_guide","_build_custom_sgt_guide","_build_custom_script_node",
      "build_node_guide","execute_graph_nodes"],
 },
 ("workspace","SessionWorkspace"): {
   "lods": ["change_selected_lod_color","show_lod_context_menu","delete_current_lod_shortcut","delete_selected_lod",
      "create_lod_workspace","get_current_lod_container","on_lod_selection_changed","filter_panels","setup_default_panels",
      "clear_all_panels","_find_lod_row_by_name","add_lod_loader_panel","build_lod_sequence"],
   "pages": ["page_file","page_rig","refresh_module_list","on_list_item_renamed","_track_selection_order","sync_list_to_graph",
      "sync_graph_to_list","open_ayon_publish_dialog","open_path_replace_dialog","page_docs","_docs_html","page_profile",
      "on_notes_changed","save_user_notes","_scripts_lib_current_path","page_scripts","browse_scripts_lib_path",
      "set_scripts_lib_path","refresh_scripts_lib_list","filter_scripts_lib_list","open_scripts_lib_item",
      "open_selected_scripts_lib_item","show_selected_scripts_lib_item","show_rig_header_menu","refresh_comment_view"],
   "panels": ["add_panel","add_module_panel","duplicate_panel","delete_panel","_push_panel_undo","serialize_panel_data",
      "restore_panel_from_data","undo_last_panel_delete"],
   "build": ["reset_scene_and_ui","reset_namespace_only","restore_namespace_preamble","refresh_all_cache_ui",
      "clear_all_caches_current_pipeline","on_delete_all_caches","clear_all_caches_current_lod","remove_caches_from",
      "_begin_fast_build","_end_fast_build","build_till_panel","cache_steps_enabled","ignore_errors_enabled",
      "_open_scene_tolerant","run_full_build","_report_build_timings","load_cache_only","build_from_cache"],
   "pipeline_io": ["get_current_pipeline_data","get_publishable_files","perform_autosave","get_current_publish_dir",
      "browse_pipeline_json","load_pipeline_from_file","populate_pipeline_versions_menu","_save_pipeline_assets",
      "save_maya_file_logic","save_json_file_logic","publish_asset_logic"],
   "executors": ["run_mgear_sgt","open_script_externally","run_script","run_script_global","import_3d_logic","organize_lod_logic",
      "delete_by_name_logic","zero_out_logic","parent_logic","resolve_instance_transforms","create_instances_logic",
      "delete_instances_by_panel_logic","load_skin_cluster_logic","_load_tweaker_module","run_reskin_logic","run_tweaker_logic",
      "get_tweaker_target_meshes"],
   "playblast": "PREFIX:pb_,get_playblast_dir,create_auto_camera_from_group,create_playblast,page_playblast,refresh_playblast_list",
 },
}
MIXIN_CLASSNAME = {"ModuleGraphWidget":"Graph", "SessionWorkspace":"Workspace"}

# ----------------------------------------------------------------------------
def read(p): return open(p, encoding="utf-8").read()
def node_start(n): 
    return min([n.lineno] + [d.lineno for d in getattr(n,"decorator_list",[])])

def top_segments(src):
    """[(node, text)] top-level, each text includes comments since previous node."""
    lines = src.splitlines(keepends=True); tree = ast.parse(src); out=[]; prev=0
    for n in tree.body:
        s = node_start(n)-1; e = n.end_lineno
        # pull leading comment/blank lines back to prev end
        out.append((n, "".join(lines[prev:e]))); prev=e
    return tree, out

def rewrite_relative(text):
    return re.sub(r"^(\s*from )\.(\w)", r"\1..\2", text, flags=re.M)

def bound_names(node):
    names=set()
    if isinstance(node,(ast.Import,ast.ImportFrom)):
        for a in node.names: names.add((a.asname or a.name).split(".")[0])
    elif isinstance(node,(ast.FunctionDef,ast.ClassDef)): names.add(node.name)
    elif isinstance(node,ast.Assign):
        for t in node.targets:
            for x in ast.walk(t):
                if isinstance(x,ast.Name): names.add(x.id)
    elif isinstance(node,(ast.Try,ast.If,ast.With)):
        for x in ast.walk(node):
            if isinstance(x,(ast.Import,ast.ImportFrom,ast.Assign,ast.FunctionDef,ast.ClassDef)) and x is not node:
                names|=bound_names(x)
    return names

def used_names(text):
    t=ast.parse(text); used=set()
    for x in ast.walk(t):
        if isinstance(x,ast.Name): used.add(x.id)
    defined=set()
    for n in t.body: defined|=bound_names(n)
    # names assigned anywhere inside (locals) are not module deps; be conservative: only subtract top-level
    return used-defined-BUILTINS

def class_method_segments(src, cls_node):
    lines=src.splitlines(keepends=True)
    body=cls_node.body
    header="".join(lines[cls_node.lineno-1: node_start(body[0])-1])
    segs=[]; prev=node_start(body[0])-1
    for b in body:
        e=b.end_lineno; segs.append((b,"".join(lines[prev:e]))); prev=e
    return header, segs

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"w",encoding="utf-8",newline="\n") as f: f.write(text)

# ----------------------------------------------------------------------------
if os.path.exists(OUT): shutil.rmtree(OUT)
os.makedirs(OUT)
report=[]

for pkg, files in PLAN.items():
    src=read(os.path.join(SRC,pkg+".py")); tree, segs = top_segments(src)
    # _shared: imports + everything not assigned to a file
    assigned={n for names in files.values() for n in names}
    shared_parts=[]; shared_names=set(); file_parts={f:[] for f in files}; name_to_file={}
    for n,text in segs:
        bn=bound_names(n)
        target=None
        for f,names in files.items():
            if bn & set(names): target=f
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            if pkg=="dialogs" and "ayon_api" in text:
                file_parts["ayon_publish"].insert(0, text.lstrip("\n")); continue
            shared_parts.append(rewrite_relative(text)); shared_names|=bn
        elif target: 
            file_parts[target].append(text)
            for b in bn: name_to_file[b]=target
        else:
            shared_parts.append(text); shared_names|=bn
            if not isinstance(n, ast.Expr): report.append(f"{pkg}: unassigned top-level {sorted(bn)} -> _shared")
    if pkg=="dialogs": shared_names.discard("ayon_api"); shared_names.discard("EntityHub")
    shared_names={x for x in shared_names if x}
    shared_src="".join(shared_parts).rstrip()+"\n\n__all__ = "+repr(sorted(shared_names))+"\n"
    write(os.path.join(OUT,pkg,"_shared.py"), '"""Shared imports/constants/helpers for the %s package (auto-split from %s.py)."""\n'%(pkg,pkg)+shared_src)

    # class splits
    mixin_files={}   # file -> text
    mixin_classes={} # file -> classname
    for (p,cls),groups in CLASS_SPLITS.items():
        if p!=pkg: continue
        cls_node=[n for n,_ in segs if isinstance(n,ast.ClassDef) and n.name==cls][0]
        header, msegs = class_method_segments(src, cls_node)
        def group_of(name):
            for g,names in groups.items():
                if isinstance(names,str):
                    spec=names.split(":")[1].split(",")
                    if any(name.startswith(s) for s in spec if s.endswith("_")) or name in spec: return g
                elif name in names: return g
            return None
        core=[]; grouped={g:[] for g in groups}
        for b,text in msegs:
            g=group_of(b.name) if isinstance(b,ast.FunctionDef) else None
            (grouped[g] if g else core).append(text)
        base_prefix=MIXIN_CLASSNAME[cls]
        mixin_names=[]
        for g,texts in grouped.items():
            if not texts: continue
            cname=f"{base_prefix}{''.join(w.title() for w in g.split('_'))}Mixin"
            mixin_names.append((g,cname))
            body="".join(texts)
            body=body.replace(f"super({cls}, self)","super()")
            body=re.sub(rf"\b{cls}\.", "type(self).", body)
            fname = {"ModuleGraphWidget":"widget_"}.get(cls,"")+g
            txt=(f'"""{cls} - {g} methods (mixin, auto-split from {pkg}.py)."""\n'
                 f"from ._shared import *\n\n\nclass {cname}(object):\n"
                 f'    """Mixed into {cls}; all methods here expect to run on a {cls} instance."""\n\n'+body)
            mixin_files[fname]=txt; mixin_classes[fname]=cname
        # rewrite class header bases
        m=re.match(r"(class\s+\w+\()(.*?)(\):.*)", header, flags=re.S)
        new_header=m.group(1)+", ".join(c for _,c in mixin_names)+", "+m.group(2)+m.group(3)
        core_text=new_header+"".join(core)
        # replace class text in its target file
        tgt=name_to_file[cls]
        file_parts[tgt]=[core_text if re.search(rf"^class {cls}\(", t, re.M) else t for t in file_parts[tgt]]
        mixin_imports="".join(f"from .{f} import {c}\n" for f,c in ((f,mixin_classes[f]) for f in mixin_files))
        file_parts[tgt].insert(0, mixin_imports)
    for f,txt in mixin_files.items():
        write(os.path.join(OUT,pkg,f+".py"), txt)

    # write class/function files with dependency imports
    file_texts={}
    for f,parts in file_parts.items():
        body="".join(parts)
        file_texts[f]=body
    for f,txt in mixin_files.items():
        file_texts["MIXIN:"+f]=txt
    # compute cross-file deps
    all_defined={}
    for f,names in files.items():
        for n in names: all_defined[n]=f
    final={}
    for f,body in file_texts.items():
        used=used_names(body)
        deps={}
        for u in used:
            if u in all_defined and all_defined[u]!=f: deps.setdefault(all_defined[u],set()).add(u)
        missing=[u for u in used if u not in shared_names and u not in all_defined and u not in mixin_classes.values()
                 and not re.search(rf"^\s*(import|from) .*\b{u}\b", body, re.M)]
        # strip local vars: names bound inside functions are also 'used'; filter by checking they're not assigned anywhere
        t=ast.parse(body); stores=set()
        for x in ast.walk(t):
            if isinstance(x,ast.Name) and isinstance(x.ctx,(ast.Store,ast.Del)): stores.add(x.id)
            if isinstance(x,(ast.FunctionDef,ast.Lambda)):
                a=x.args; stores|={q.arg for q in a.args+a.kwonlyargs+a.posonlyargs}
                if a.vararg: stores.add(a.vararg.arg)
                if a.kwarg: stores.add(a.kwarg.arg)
            if isinstance(x,ast.ExceptHandler) and x.name: stores.add(x.name)
            if isinstance(x,(ast.FunctionDef,ast.ClassDef)): stores.add(x.name)
            if isinstance(x,ast.Import) or isinstance(x,ast.ImportFrom):
                for al in x.names: stores.add((al.asname or al.name).split(".")[0])
            if isinstance(x,ast.comprehension):
                for y in ast.walk(x.target):
                    if isinstance(y,ast.Name): stores.add(y.id)
            if isinstance(x,(ast.Global,ast.Nonlocal)): stores|=set(x.names)
        missing=[u for u in missing if u not in stores]
        if missing: report.append(f"{pkg}/{f}.py: UNRESOLVED names {sorted(missing)}")
        dep_lines="".join(f"from .{df} import {', '.join(sorted(ns))}\n" for df,ns in sorted(deps.items()))
        hdr=f'"""Auto-split from {pkg}.py."""\nfrom ._shared import *\n'+dep_lines+"\n\n"
        final[f]=hdr+body.lstrip("\n")
        for df in deps: report.append(f"DEP {pkg}: {f} -> {df}")
    for f,txt in final.items():
        if not f.startswith("MIXIN:"): write(os.path.join(OUT,pkg,f+".py"), txt)
    # __init__: re-export
    init=['"""%s package - re-exports so `from .%s import X` keeps working."""'%(pkg,pkg),"from ._shared import *"]
    for f,names in files.items(): init.append(f"from .{f} import {', '.join(names)}")
    for f,c in mixin_classes.items(): init.append(f"from .{f} import {c}")
    write(os.path.join(OUT,pkg,"__init__.py"), "\n".join(init)+"\n")

# cycles
edges={}
for r in report:
    if r.startswith("DEP"):
        _,rest=r.split(" ",1); pkg,ab=rest.split(": "); a,b=ab.split(" -> "); edges.setdefault(pkg,set()).add((a,b))
for pkg,es in edges.items():
    for a,b in es:
        if (b,a) in es: report.append(f"CYCLE {pkg}: {a} <-> {b}")
print("\n".join(r for r in report if not r.startswith("DEP")))
print("\n".join(sorted(r for r in report if r.startswith("DEP"))))
