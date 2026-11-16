"""KRT changelog - shown in the UI (the version button in the top bar).

Add a new entry at the TOP of ENTRIES every time __version__ is bumped:
    {"version": "46.5", "date": "YYYY-MM-DD HH:MM", "changes": ["...", "..."]}
Keep it newest-first. The newest entry should match __version__ in __init__.py.
"""

ENTRIES = [
    {"version": "46.47", "date": "2026-11-18 15:00", "changes": [
        "CHECK PC2 IN BLENDER: while the temporary Blender file is open the button turns into DELETE / SAVE TEMP BLENDER FILE. Delete closes Blender and deletes the temp files. Save brings Blender to the front and opens its Save As window; after saving, the PC2 files are copied next to the file (<name>_pc2), the caches are repointed there, and Blender asks whether to stay or close. The button returns to normal when Blender closes.",
    ]},
    {"version": "46.46", "date": "2026-11-18 14:00", "changes": [
        "CHECK PC2 IN BLENDER: (1) any error now opens a window with the full text and a Copy to clipboard button, to send; (2) it asks first what you want to see - Blender file, Render, or Both; Render makes a quick Workbench preview sequence in background Blender and plays it in a Maya window with a slider; (3) when the Blender file opens, the scene range and current frame are set, a Timeline is made visible and zoomed to the range, and a message in Blender tells how many meshes got a PC2 cache.",
    ]},
    {"version": "46.45", "date": "2026-11-18 13:00", "changes": [
        "CHECK PC2 IN BLENDER: fixed 'none of the meshes match' - names like geo_x_lod_0 existing in both Maya and Blender were wrongly compared with the geo_ prefix removed on one side only. Added a progress window showing every step (reading Blender names, matching, loading animation, recording cache, writing each PC2, opening Blender); ESC cancels. The no-match message now lists example Blender names.",
    ]},
    {"version": "46.44", "date": "2026-11-18 12:00", "changes": [
        "Rig Build Workspace: new KRT File row at the very top (above Rig Name) showing the full path of the loaded KRT json - light red when a newer version of that file exists (an old file is loaded), light green when it is the latest. Re-checked on load / save / opening the tab, plus a Refresh button.",
    ]},
    {"version": "46.43", "date": "2026-11-18 11:00", "changes": [
        "Rig & Model Status: rig files published in a sub-folder of rigMain (e.g. rigMain/rigging/v001/chariotdriver_a_Rig_built.ma, or rigMain/hero) now count as the rig too; the newest rig file of rigMain/vNN and those sub-folders is used.",
    ]},
    {"version": "46.42", "date": "2026-11-18 10:00", "changes": [
        "New white/black button CHECK PC2 IN BLENDER after Publish Krishna: loads the test animation (Playblast tab .anim) on the rig, exports PC2 for the Maya meshes that exist in the Blender panel's .blend, undoes the animation, and opens a temporary copy of that .blend in Blender with the PC2 applied by the pipeline tool's own Apply PC2 Caches & Rotate code, for a manual check. The temp copy and PC2 files are deleted when Blender closes; the server file is only read.",
    ]},
    {"version": "46.41", "date": "2026-11-17 22:30", "changes": [
        "Blender panel wrinkle window: it no longer closes by itself or with the X button - it stays until you press Wrinkles OK (import the ABC) or Wrinkles NOT OK (delete the ABC).",
    ]},
    {"version": "46.40", "date": "2026-11-17 22:00", "changes": [
        "Blender panel, Blend -> ABC: new information popup after the export and before the wrinkle window - lists every mesh that is hidden in the .blend (eye icon, monitor icon or hidden collection) and so was not exported; press OK to continue. Also: when the ABC path is empty, the ABC goes into the Rig Root's existing model folder whether it is spelled model, Model or MODEL.",
    ]},
    {"version": "46.39", "date": "2026-11-17 21:00", "changes": [
        "Rig & Model Status: models of props, locations and many characters were shown as 'No model' because they live in workfileModel_lod (not workfileMaster_model). Both folders are now checked and the newest .blend counts.",
    ]},
    {"version": "46.38", "date": "2026-11-17 20:00", "changes": [
        "Switch Version (the ... menu) and the Versions button now list EVERY file of the same kind in the file's folder, newest first, each with its saved date - even if the name is different or has no version number. Applies to Skin JSON, Tweaker, Control Shapes, Material, Joint Positions, Script / Global Script, Import 3D, Import 3D + LOD, the ABC of the Blender panel and CC Import (3D files .ma/.mb/.fbx/.obj/.abc are listed together). Script and Import panels also gained Switch Version in their ... menu. The Blender File field is unchanged. Read only: the folder is only listed.",
    ]},
    {"version": "46.37", "date": "2026-11-17 19:00", "changes": [
        "Rig & Model Status: new date filter - Any date, Today, Yesterday, Last 7 days, Last 30 days, or Between two dates. Shows only assets whose model, CC or rig file was saved in that period; counts follow the filter.",
    ]},
    {"version": "46.36", "date": "2026-11-17 18:00", "changes": [
        "Rig & Model Status: the CC cell now turns red when the rig is older than the .ccProject file (CC comes with modeling) or when there is no rig, green otherwise.",
    ]},
    {"version": "46.35", "date": "2026-11-17 17:00", "changes": [
        "Rig & Model Status: the Type column is now a highlighted tag - characters (cyan), props (orange), locations (purple), any other type (grey-blue) - so the asset kind stands out at a glance.",
    ]},
    {"version": "46.34", "date": "2026-11-17 16:30", "changes": [
        "Installer: the earlier duplicate-button clean-up only matched one exact annotation, so old KRT buttons stayed and new ones piled up. It now finds every shelf button on every shelf whose label, annotation or command mentions KRT, deletes them by full UI path, then adds exactly one.",
    ]},
    {"version": "46.33", "date": "2026-11-17 15:30", "changes": [
        "Fix: KRT failed to launch (SessionWorkspace has no attribute _status_menu) - restored the Rig & Model Status right-click menu and Copy table methods.",
    ]},
    {"version": "46.32", "date": "2026-11-17 15:00", "changes": [
        "Rig & Model Status: every asset now has a Type (characters / props / locations ... read from its folder path under kl_assets/assets). The dropdown can show all types or just one, the Type column is shown and copied, and the filter box matches the type too.",
    ]},
    {"version": "46.31", "date": "2026-11-17 14:00", "changes": [
        "Rig & Model Status > Copy table now copies aligned plain text (title, header, one line per asset: model / CC / rig version + date and status) without file paths, so it reads cleanly in a .txt file.",
    ]},
    {"version": "46.30", "date": "2026-11-17 13:00", "changes": [
        "Rig & Model Status: new Copy table button - copies all rows of the current view (filter and sort applied) with model / CC / rig paths as tab-separated text, ready to paste into Excel or send.",
    ]},
    {"version": "46.29", "date": "2026-11-17 12:00", "changes": [
        "Rig & Model Status: right-click a row to copy the model, CC or rig file path, or open its folder (read only - nothing on the server is changed).",
    ]},
    {"version": "46.28", "date": "2026-11-17 11:00", "changes": [
        "Drag-and-drop installer: no longer adds another KRT shelf button each time. Before adding its button it removes every earlier KRT launch button from all shelves, so there is always exactly one.",
    ]},
    {"version": "46.27", "date": "2026-11-17 10:00", "changes": [
        "Rig & Model Status: assets inside group folders (e.g. parshuramsubassets/bhargavakid_a) are now listed, and a new CC column shows the newest .ccProject (workfileCc_model) with its version/date, red if older than the model. A rig older than the model or the CC file is marked outdated.",
    ]},
    {"version": "46.26", "date": "2026-11-16 23:00", "changes": [
        "Rig & Model Status now reads the real kl_assets publish folders (P:/kl_assets/KL_ASSETS/assets/<category>/<asset>/publish/...): model = latest workfileMaster_model vNN .blend, rig = latest rigMain vNN .ma. Read only - it only lists folders and reads file names, paths and dates.",
    ]},
    {"version": "46.25", "date": "2026-11-16 22:00", "changes": [
        "Documentation tab rewritten and brought fully up to date: topic list on the left, linked pages with 'See also' links between related features (Blender panel, Compare tool, Version colours, Facial Shape Extract, CC Import, Utilities, Rig & Model Status, PanelScripts and more), Back / Home buttons, and a What's new page generated from this changelog. Text lives in workspace/docs_content.py.",
    ]},
    {"version": "46.24", "date": "2026-11-16 21:00", "changes": [
        "New sidebar tab: Rig & Model Status. Pick a project at the top (or browse to one) and see every asset with its latest model version/date and latest rig version/date, counts of assets/models/rigs, and a filter, an only-outdated toggle and a Refresh button. A row turns red when the rig is older than the model (or has no rig) and green when it is up to date.",
    ]},
    {"version": "46.23", "date": "2026-11-16 19:00", "changes": [
        "Version colours are now light red (newer version exists) and light green (latest). Works on Script / Global Script panels too, including locked path fields and scripts without _vNN in the name (a sibling name_vNN.py counts as a newer version); the colour is re-applied whenever the script field locks or unlocks.",
    ]},
    {"version": "46.22", "date": "2026-11-16 18:00", "changes": [
        "Every file panel (script, import 3D, skin JSON, tweaker, control shapes, material, joint positions, joint transfer, CC import): the path field turns dark red when a newer version exists and green when it is the latest, and a new Versions button (left click) lists all versions with their saved date to switch between. The check runs on load, on edits and when the panel runs.",
    ]},
    {"version": "46.21", "date": "2026-11-16 15:00", "changes": [
        "Import 3D + LOD Organize (Blender): new Versions button after the Blender File field - click it to see every version of the .blend with its saved date and switch to one. The ABC path now has Switch Version in the panel's ... menu too.",
    ]},
    {"version": "46.20", "date": "2026-11-16 12:00", "changes": [
        "Import 3D + LOD Organize (Blender): the Blender File field turns red when a newer version of the file exists (next _vNN file or next vNN folder) and green when it is the latest. New Refresh button after the field; the check also runs automatically when the KRT json is loaded and when the panel is built.",
    ]},
    {"version": "46.19", "date": "2026-11-14 19:00", "changes": [
        "Script / Tools Library: the Copy script / Run script buttons now always show their names (fixed size and colours).",
        "Switch Version menus (panels, guide path, whole pipeline JSON): every version now shows the date and time it was saved, and the loaded one is ticked.",
        "Add Panel menus (right-click Add Panel Above/Below and the Add New Panel button): new search box at the top - type to filter, Enter picks the first match.",
    ]},
    {"version": "46.18", "date": "2026-11-14 16:00", "changes": [
        "Rigging Workspace > Script / Tools Library: removed double-click-to-open; every script row now has its own 'Copy script' and 'Run script' buttons.",
        "Panel scripts (Breathing, Facial Shape Extract, CC Import + Auto Setup, Joint Transfer, Finger Fix, Joint Positions and their helpers, and the Blender tool) moved into the PanelScripts folder next to Tweaker.py, with a README listing which script belongs to which panel.",
    ]},
    {"version": "46.17", "date": "2026-11-14 12:00", "changes": [
        "New panel: Facial Shape Extract. Give it a Source mesh (carries the facial blendShape) and Target meshes (Get Selected); it wraps the targets to the source and builds a blendShape on each target with every source shape, re-driven by the source rig's connections.",
    ]},
    {"version": "46.16", "date": "2026-11-14 10:00", "changes": [
        "Fixes 'attempted relative import beyond top-level package' in other tools (e.g. Auto Setup from the shelf): if the KRT folder itself is on sys.path, KRT now removes it when it loads. Only the PARENT folder belongs on the path.",
    ]},
    {"version": "46.15", "date": "2026-11-13 22:00", "changes": [
        "CC import: Auto Setup is now found from the Maya shelf button / shelf file that launches it (any install path), and AutoSetupMain is accepted as .py, .pyc, .pyd or a package.",
    ]},
    {"version": "46.14", "date": "2026-11-13 20:00", "changes": [
        "Compare tool: click a mesh name in the results (old or new side) to select that mesh in Maya.",
    ]},
    {"version": "46.13", "date": "2026-11-13 18:00", "changes": [
        "CC import: Auto Setup detection is much broader - Python's own import lookup, Program Files / AppData / Documents, then every drive (time-limited). If it still cannot be found KRT asks once for the AutoSetupForMaya folder and remembers it.",
    ]},
    {"version": "46.12", "date": "2026-11-13 16:00", "changes": [
        "CC import: Auto Setup is now found automatically wherever it is installed (already loaded in Maya, Maya script/module/Python paths, user maya folders, C:/pipeline), instead of only two fixed folders. KRT_AUTOSETUP_PATH can override it.",
    ]},
    {"version": "46.11", "date": "2026-11-13 14:00", "changes": [
        "Blender panel: meshes that carry hair particle systems (eyebrow, head hair, eyelashes) were coming into Maya as an empty transform with no shape. The export now turns on their emitter mesh in memory, so they arrive with their geometry.",
    ]},
    {"version": "46.10", "date": "2026-11-12 15:00", "changes": [
        "New permanent Python Path row under Rig Root (default P:/rigging_team/Pipeline_share/RigUtils). Always present, not saved in KRT files, editable with Browse and Reset, saved per user and added to sys.path so scripts can import UniUtils.",
    ]},
    {"version": "46.9", "date": "2026-11-12 12:00", "changes": [
        "Removed the auto-loaded rig library folder (rigutils: UniUtils, rig_lib, Fan, ...). KRT no longer imports it when the window opens, and script panels no longer start with those helpers.",
    ]},
    {"version": "46.8", "date": "2026-11-07 10:00", "changes": [
        "Import 3D, Import 3D + LOD Organize and the Blender panel: new 'Delete AI models (*ai_lod*)' checkbox, ON by default. Untick it to keep AI models. Import 3D deletes only the AI objects its own import added.",
    ]},
    {"version": "46.7", "date": "2026-11-06 20:00", "changes": [
        "Blender panel: new 'Compare Old vs New ABC' button - opens the mesh comparison / QC toolkit with the new ABC (panel path) and the previous ABC already referenced and selected. Old = the ABC the panel pointed at before the last Blend->ABC run, else the next lower _vNNN in the folder.",
    ]},
    {"version": "46.6", "date": "2026-11-06 19:00", "changes": [
        "Blender panel: Asset Name is filled automatically from the file name (KL_kvaspidershape_a_workfileModel_lod_v01 -> kvaspidershape_a).",
        "Blender panel: if the wrinkles are rejected (NOT OK / window closed) the exported ABC is deleted and the path field is NOT changed. The path is only set after the ABC is really imported.",
    ]},
    {"version": "46.5", "date": "2026-11-06 18:00", "changes": [
        "New panel: Import 3D + LOD Organize + Blender. Same as Import 3D + LOD Organize, plus a Blender File field and a one-time 'Blend -> ABC' button (not part of the build) with a 'Skip wrinkle check' option. Tool scripts are in the blend_abc_tool folder.",
    ]},
    {"version": "46.4", "date": "2026-11-06 14:20", "changes": [
        "Publish: if the scene has no rigMain set, the open scene can now be published as rigMain as-is (no rebuild or Rig Sets step needed).",
        "Publish: new option to create the rig sets on the spot with the Rig Sets rules, through AYON's creator.",
        "Publish: step-by-step '>>' log lines around the rebuild, to find where Maya crashes.",
        "New Changelog window (this one) from the version button in the top bar.",
    ]},
    {"version": "46.3", "date": "2026-10-05", "changes": [
        "Baseline release bundled into the Kleem Toolkit (earlier history is in PROGRESS.md).",
    ]},
]
