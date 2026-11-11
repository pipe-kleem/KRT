"""KRT changelog - shown in the UI (the version button in the top bar).

Add a new entry at the TOP of ENTRIES every time __version__ is bumped:
    {"version": "46.5", "date": "YYYY-MM-DD HH:MM", "changes": ["...", "..."]}
Keep it newest-first. The newest entry should match __version__ in __init__.py.
"""

ENTRIES = [
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
