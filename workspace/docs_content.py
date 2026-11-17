# -*- coding: utf-8 -*-
"""Text of the Documentation tab.

TOPICS is an ordered list of (id, section, title, html). Inside a topic, <a href="krt:other_id">text</a>
jumps to another topic (the viewer on the Documentation tab handles the krt: links, and has Back / Home).
To document a new feature: add a topic here (or a paragraph in an existing one), link it from related topics
with a 'See also' line, and add the topic to the right section. The 'What's new' topic is generated from
changelog.py, so it is always current.
"""

STYLE = """
<style>
 h2 { color: #2bb5a8; margin-top: 4px; margin-bottom: 6px; }
 h3 { color: #4fc3f7; margin-top: 14px; margin-bottom: 2px; }
 p, li { color: #cccccc; line-height: 1.5; }
 code { background:#2a2a2a; padding: 1px 5px; color:#f0c674; }
 a { color: #64b5f6; text-decoration: none; }
 .see { color: #888; margin-top: 16px; }
 .red { color: #ef9a9a; } .green { color: #a5d6a7; }
</style>
"""


def see(*ids):
    """'See also' line with links to other topics (titles resolved at render time)."""
    return '<p class="see">See also: ' + " &middot; ".join('<a href="krt:%s">@%s@</a>' % (i, i) for i in ids) + "</p>"


TOPICS = [
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Getting started â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
("overview", "Getting started", "Overview", """
<h2>Overview</h2>
<p>KRT (Kleem Rigging Tool) is a module-based biped / creature rig-building pipeline on top of mGear Shifter.
A rig is assembled as a sequence of <b>panels</b> inside a <b>LOD workspace</b> - each panel is one step (run a
script, import a model, load a skinCluster, build a module...) - plus a <b>Module Graph</b> where the mGear guide
components live and connect to each other.</p>
<p>Use the topic list on the left, or the links inside a page. Pages that are related to each other have a
<i>See also</i> line at the bottom. <b>Back</b> and <b>Home</b> are above the page.</p>
<h3>Where things are</h3>
<ul>
<li>Left icon bar: <a href="krt:t_file">File</a>, <a href="krt:t_rig">Rig Build Workspace</a>,
<a href="krt:t_graph">Module Graph</a>, <a href="krt:t_lib">Rigging Workspace (script library)</a>,
<a href="krt:t_pb">Playblast</a>, <a href="krt:t_status">Rig &amp; Model Status</a>, Documentation, Profile.</li>
<li>Rig Name / Rig Root / Utilities rows at the top of the Rig Build Workspace: <a href="krt:t_root">Rig Root &amp; Utilities</a>.</li>
<li>Every panel type: <a href="krt:p_all">Panel types</a>.</li>
</ul>
""" + see("whatsnew", "p_all", "versions")),

("whatsnew", "Getting started", "What's new (changelog)", "@@CHANGELOG@@"),

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
("t_file", "Tabs", "File", """
<h2>File</h2>
<p>Save / Load the current pipeline as a KRT JSON, auto-save settings, the recent-files list and the session
comments. A rig session's whole state - LODs, panels, the Module Graph and the Guide Settings tab - is written to
or read from this file.</p>
<p><b>Versions:</b> saving creates a new <code>_vNNN</code> JSON next to the old ones; the Switch Version menu of the
whole pipeline shows every version <b>with the date and time it was saved</b> and ticks the loaded one. When a KRT JSON is
loaded, every file panel re-checks whether a newer file exists (see <a href="krt:versions">Version colours</a>).</p>
""" + see("versions", "t_rig", "t_status")),

("t_rig", "Tabs", "Rig Build Workspace", """
<h2>Rig Build Workspace</h2>
<p>The main step-by-step builder. The left sidebar lists your <b>LODs</b>; each LOD holds its own stack of panels
that run top-to-bottom when you build. The <b>Rig Name / Rig Root / Utilities</b> rows are at the top
(<a href="krt:t_root">details</a>). Under them is the <b>search box</b> that filters panels by title, path or type.</p>
<h3>KRT File row</h3>
<p>The first row shows the <b>full path of the loaded KRT json</b>. <span class="red">Light red</span> = you have an OLD file loaded (a newer <code>_vNNN</code> exists - hover to see it), <span class="green">light green</span> = latest, grey = not saved yet. It re-checks when a file is loaded or saved, when you open this tab, and on <b>Refresh</b>.</p>
<h3>Working with panels</h3>
<ul>
<li>Right-click a panel or use its <b>...</b> menu: Add Panel Above / Below, Duplicate, Copy / Cut / Paste, Undo Delete,
Build Till Here / From Here, Replace All Paths, Switch Version and type-specific actions.</li>
<li><b>Add Panel menus</b> (right-click Add Panel Above/Below and the Add New Panel dropdown) have a <b>search box</b> at
the top - type part of a panel name to filter the list.</li>
<li>Each panel has a checkbox (on = part of the build), a RUN-style button for running just that step, and a
<b>Cache</b> option so unchanged steps can be skipped.</li>
<li>Panels whose path field is a file show a <b>Versions</b> button and a red / green field colour:
<a href="krt:versions">Version colours</a>.</li>
</ul>
""" + see("p_all", "versions", "t_root", "t_graph")),

("t_root", "Tabs", "Rig Root & Utilities", """
<h2>Rig Root &amp; Utilities</h2>
<h3>Rig Root</h3>
<p>The folder of this rig (for example <code>.../all_Rigs/akritavrana_a</code>). Panel paths can be stored relative to it
(<b>Paths: Relative</b> button). <b>Initialize Project</b> creates the standard sub-folders.</p>
<h3>Utilities (permanent row)</h3>
<p>Always present, cannot be deleted, not saved in KRT files. Default <code>P:\\rigging_team\\Pipeline_share\\RigUtils</code>.
The text is read-only; use <b>...</b> to browse to another folder or <b>Reset</b> to go back to the default. The folder is
added to <code>sys.path</code> so scripts can <code>import UniUtils</code>, etc. KRT only reads from this server folder - it never
writes there. The choice is remembered per user.</p>
""" + see("t_rig", "p_script")),

("t_graph", "Tabs", "Module Graph Editor", """
<h2>Module Graph Editor</h2>
<p>A node-graph view of the mGear guide components (arms, legs, spine, a full Plebe biped template, or a Custom Module from
a <code>.sgt</code> file). Drag from a node's right edge to another node to parent them; Tab or double-click empty canvas to
search for a component. Ctrl+drag pans, Shift+click multi-selects, Ctrl+Z / Ctrl+Shift+Z undo / redo graph changes.</p>
<p>The <b>Guide Settings</b> panel holds the rig-wide Shifter options and Custom Steps and is saved with the normal pipeline
JSON. A node can open mGear's own full Settings window. A red mark on a node means its custom script errored last build.</p>
""" + see("p_bubbles", "t_rig")),

("t_lib", "Tabs", "Rigging Workspace (script library)", """
<h2>Rigging Workspace - Script / Tools Library</h2>
<p>A browsable library of your own scripts and tools, independent of any pipeline file. The folder is remembered per user.
Every script row has its own <b>Copy script</b> button (puts the text on the clipboard) and <b>Run script</b> button (runs it now
in Maya); <i>Show in Explorer</i> jumps to the file. There is no double-click-to-open any more.</p>
""" + see("t_root", "p_script")),

("t_pb", "Tabs", "Playblast", """
<h2>Playblast</h2>
<p>Create and review playblasts without leaving KRT. Give it a camera, or a group whose bounding box it should auto-frame with
a temporary camera; set start / end frame and click Create Playblast. The result plays back in the preview, and every past
playblast of this session stays in the dropdown. The Animation (.anim) field loads a Studio Library clip onto controls that
match the Controls Filter (for example <code>*_ctl</code>) before capturing; Browse fills Start / End from the clip. Needs the
studio's Studio Library (mutils) install to be reachable.</p>
"""),

("t_status", "Tabs", "Rig & Model Status", """
<h2>Rig &amp; Model Status</h2>
<p>One table with every asset of a project: its <b>latest model</b> (version, date) and <b>latest rig</b> (version, date).</p>
<ul>
<li><b>Project</b> is kl_assets (<code>P:\\kl_assets\\KL_ASSETS\\assets</code>); the dropdown filters by asset <b>Type</b> (characters, props, locations... - taken from the folder under <code>assets</code>); the <b>Type</b> column shows it for every asset, and the Filter box matches it too. The Type cell is a highlighted tag: characters = cyan, props = orange, locations = purple, anything else = grey-blue.</li>
<li>Model = the newest <code>.blend</code> of the highest <code>vNN</code> folder in <code>&lt;asset&gt;/publish/workfile/workfileMaster_model/</code> (<code>workfileModel_lod/</code> is ignored);
Rig = the newest <code>.ma</code> / <code>.mb</code> in <code>&lt;asset&gt;/publish/rig/rigMain/vNN/</code> <i>or</i> in a sub-folder of rigMain such as <code>rigMain/rigging/vNNN/</code> (the <code>*_Rig_built.ma</code> files) or <code>rigMain/hero/</code>; whichever is newest counts. Hover a cell for the file path.</li>
<li>Assets inside group folders (for example <code>parshuramsubassets/bhargavakid_a</code>) are found too - any folder that has a <code>publish</code> folder is an asset.</li>
<li><b>CC</b> columns: newest <code>.ccProject</code> in <code>publish/workfile/workfileCc_model/vNN/</code>; the CC cell is red when the rig is older than it (or there is no rig), green otherwise. The rig counts as old if it is older than the newest model <i>or</i> CC file.</li>
<li>The count line shows assets, models, rigs, up to date, outdated and missing.</li>
<li><b>Date filter</b> (next to the filter box): Any date, Today, Yesterday, Last 7 days, Last 30 days, or Between dates (two date pickers appear). Only assets whose model, CC or rig file was saved in that period are shown; the counts follow the filter.</li>
<li><b>Filter</b> by asset name, <b>Only outdated</b> toggle, and <b>Refresh</b> to re-scan (also refreshes when you open the tab).</li>
<li>A row is <span class="red">red</span> when the latest model file is newer than the latest rig file (or there is no rig) and
<span class="green">green</span> when the rig is at least as new as the model. Grey = no model.</li>
<li><b>Copy table</b> copies every row currently shown (filter and sort applied) as neatly aligned plain text (asset, model / CC / rig version and date, status - no file paths), so it reads well in a .txt file, chat or mail. Use right-click to copy a file path.</li>
<li><b>Right-click a row</b> to copy the model, CC or rig file path (or open its folder). Hover a cell to see the path.</li>
<li><b>Read only:</b> this server folder is only listed - KRT reads names, paths and dates and never changes anything there.</li>
</ul>
<p>Comparison is by file save date (the rig file does not record which model version it was built on).</p>
""" + see("t_file", "versions")),

("t_profile", "Tabs", "Profile", """
<h2>Profile</h2>
<p>Your own persistent notes (auto-saved, per user). At launch KRT warns if the last session did not close cleanly and
offers to restore the newest auto-saved backup.</p>
"""),

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Panels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
("p_all", "Panel types", "Panel types - overview", """
<h2>Panel types</h2>
<p>Every type has its own icon and tint. Fields marked read-only (brown) are only set by Browse / Save / Switch Version.</p>
<ul>
<li><a href="krt:p_script">Script and Global Script</a></li>
<li><a href="krt:p_import3d">Import 3D Model</a> and <a href="krt:p_blender">Import 3D + LOD Organize (Blender)</a></li>
<li><a href="krt:p_skin">Skin JSON</a>, <a href="krt:p_shapes">Control Shapes</a>, <a href="krt:p_tweaker">Tweaker</a></li>
<li><a href="krt:p_bubbles">Module Bubbles</a> and <a href="krt:p_lodloader">LOD Loader</a></li>
<li><a href="krt:p_cc">CC Import</a>, <a href="krt:p_facial">Facial Shape Extract</a>, <a href="krt:p_joint">Joint Transfer / Finger Fix / Joint Positions</a>, <a href="krt:p_breathing">Breathing</a></li>
<li><a href="krt:p_publish">Publish</a>, <a href="krt:p_misc">Material, Note, Delete and other helper panels</a></li>
</ul>
<p>Scripts that power the special panels live in the <a href="krt:panelscripts">PanelScripts folder</a>.</p>
""" + see("versions", "t_rig")),

("p_script", "Panel types", "Script / Global Script", """
<h2>Script</h2>
<p>Runs a Python or MEL file (or pasted code). <b>Script</b> runs in KRT's private namespace for this session tab.
<b>Maya Global Script</b> runs into Maya's real <code>__main__</code>, so anything it defines can still be called from the Script
Editor afterwards. A field that holds a <code>.py</code> / <code>.mel</code> path locks itself (right-click Clear to type code
instead); raw pasted code stays editable. Every LOD starts with one Global Script panel.</p>
<p>The field is coloured and has a <b>Versions</b> button also for scripts: <code>name.py</code> is flagged when a sibling
<code>name_v02.py</code> exists (<a href="krt:versions">Version colours</a>). Scripts can <code>import</code> from the
<a href="krt:t_root">Utilities</a> folder.</p>
""" + see("versions", "t_root", "t_lib")),

("p_import3d", "Panel types", "Import 3D Model", """
<h2>Import 3D Model</h2>
<p>Imports <code>.ma .mb .fbx .obj .abc</code>, picking the importer from the extension. The related <b>Import 3D + LOD
Organize</b> variant also organizes the result into LOD groups. Both have <b>Delete AI models (*ai_lod*)</b> (ON by default) - untick to
keep AI models; Import 3D deletes only the AI objects its own import added. Path field is read-only and version-aware.</p>
""" + see("p_blender", "versions")),

("p_blender", "Panel types", "Import 3D + LOD Organize (Blender)", """
<h2>Import 3D + LOD Organize (Blender)</h2>
<p>Like Import 3D + LOD Organize, plus a <b>Blender File</b> field and a one-time <b>Blend -&gt; ABC</b> button (not part of the build).</p>
<ul>
<li><b>Blend -&gt; ABC:</b> exports the .blend to Alembic with headless Blender, runs the wrinkle check (tick <i>Skip wrinkle check</i>
to skip it), then imports. If the wrinkles are rejected the exported ABC is deleted and the path is not changed.</li>
<li><b>Asset Name</b> is filled from the file name automatically (<code>KL_x_workfileModel_lod_v01</code> -&gt; <code>x</code>).</li>
<li><b>Hair / eyebrow / eyelash meshes</b> (emitters with hair particle systems) are exported with their geometry - the exporter
turns on their emitter mesh in memory, so they no longer arrive as an empty transform.</li>
<li><b>Wrinkle window:</b> stays open until you answer - the X button does nothing; press <i>Wrinkles OK</i> (imports the ABC) or <i>NOT OK</i> (deletes the ABC). Its temporary frames are deleted when it closes.</li>
<li><b>Hidden meshes:</b> after the export, before the wrinkle window, an information popup lists every mesh that is hidden in the .blend (eye icon, monitor icon or hidden collection) and was therefore not exported. Press OK to continue.</li>
<li><b>ABC folder:</b> the ABC is saved next to the current ABC path, or into the Rig Root's existing <code>model</code> / <code>Model</code> folder (whatever its spelling).</li>
<li><b>Compare Old vs New ABC</b> opens the <a href="krt:compare">mesh Compare tool</a> with the new ABC and the previous one preselected.</li>
<li><b>Blender File field:</b> <span class="red">light red</span> = a newer .blend exists, <span class="green">light green</span> = latest.
<b>Refresh</b> re-checks; <b>Versions</b> lists every .blend with date to switch. The ABC path has Switch Version in the ... menu.</li>
</ul>
<p>Tool scripts: <code>PanelScripts/blend_abc_tool</code>.</p>
""" + see("compare", "versions", "p_import3d", "panelscripts")),

("compare", "Panel types", "Mesh Compare tool", """
<h2>Mesh Compare (Old vs New ABC)</h2>
<p>Compares two ABC / mesh sets and lists differences. <b>Click a mesh name</b> in the results (on the old or the new side) to select
that mesh in Maya. Opened from the Blender panel with the new ABC and the previous version already chosen (old = the ABC the panel
pointed at before the last Blend-&gt;ABC, otherwise the next lower <code>_vNNN</code> in the folder).</p>
""" + see("p_blender")),

("p_skin", "Panel types", "Skin JSON", """
<h2>Skin JSON</h2>
<p>Saves / loads a skinCluster as KRT's own <code>.jSkin</code> / <code>.json</code>, with a Meshes field to scope it and a Joints field
plus Bind All for a quick bind. Save / Load checks the involved meshes for skinCluster naming mismatches and offers to fix them.
Path field is read-only, version-aware, with date-stamped Switch Version.</p>
""" + see("versions", "p_tweaker")),

("p_shapes", "Panel types", "Control Shapes", """
<h2>Control Shapes</h2>
<p>Saves / loads control-curve shapes (CV positions) as KRT JSON, matched to controls by name on import. Read-only, version-aware field.</p>
""" + see("versions")),

("p_tweaker", "Panel types", "Tweaker", """
<h2>Tweaker</h2>
<p>Runs the studio Tweaker weighting setup (<code>PanelScripts/Tweaker.py</code>). A panel holds one or more <b>vertex groups</b>; each has
its own Vertices, Additional Meshes and settings (Use Bind Scale, Influence Radius, Full Weight Radius, Falloff) and a x to remove it;
<b>+ Add Vertex Group</b> adds more. Its skin file is saved / loaded like the Skin JSON panel.</p>
""" + see("p_skin", "panelscripts")),

("p_bubbles", "Panel types", "Module Bubbles", """
<h2>Module Bubbles</h2>
<p>Holds module "bubbles" pulled from the Module Graph (or a raw script / <code>.sgt</code>). The green LOAD draws every bubble's guide,
builds them together in one Shifter build, runs each node's post-build script, then cleans up the guides it used.</p>
""" + see("t_graph", "p_lodloader")),

("p_lodloader", "Panel types", "LOD Loader", """
<h2>LOD Loader</h2>
<p>A compact panel that builds other LODs as an ordinary step in this LOD's order (button reads <b>RUN</b>). Pick which LODs it contains;
it follows renames automatically. Running it does not switch the LOD you are looking at - only clicking a bubble name navigates.
It takes part in Build Till Here in its correct position.</p>
""" + see("p_bubbles", "t_rig")),

("p_cc", "Panel types", "CC Import", """
<h2>CC Import (Character Creator)</h2>
<p>Imports a CC FBX and drives Reallusion <b>Auto Setup for Maya</b>. Auto Setup is <b>found automatically</b> on any PC: it checks what is
already loaded in Maya, the shelf button / shelf file that launches it (any install path, even with several buttons), Maya script / module
/ Python paths, common install locations and then the drives. If still not found KRT asks once for the AutoSetupForMaya folder and remembers it.
<code>KRT_AUTOSETUP_PATH</code> overrides the search. <code>AutoSetupMain</code> may be .py, .pyc, .pyd or a package.</p>
""" + see("versions", "panelscripts")),

("p_facial", "Panel types", "Facial Shape Extract", """
<h2>Facial Shape Extract</h2>
<p>Give it one <b>Source</b> mesh (carries the facial blendShape) and one or more <b>Target</b> meshes (<b>Get Selected</b>). The button
(<b>EXTRACT SHAPES</b>) wraps the targets to the source and builds a blendShape on each target with every source shape, re-driven by
the source rig's connections. Script: <code>PanelScripts/facial_shape_extract.py</code>.</p>
""" + see("panelscripts")),

("p_joint", "Panel types", "Joint Transfer / Finger Fix / Joint Positions", """
<h2>Joint Transfer, Finger Fix, Joint Positions</h2>
<p><b>Joint Transfer</b> and <b>Finger Fix</b> run step sets against a reference rig (they share the helpers <code>rig_resources</code>,
<code>rig_reference</code>, <code>step_runner</code>). <b>Joint Positions</b> saves / loads joint positions from a JSON. Their file fields are
version-aware. Scripts are in <a href="krt:panelscripts">PanelScripts</a>.</p>
""" + see("versions", "panelscripts")),

("p_breathing", "Panel types", "Breathing", """
<h2>Breathing</h2>
<p>Builds the breathing setup from a Body and Meshes selection (<code>PanelScripts/breathing.py</code>).</p>
""" + see("panelscripts")),

("p_publish", "Panel types", "Publish", """
<h2>Publish</h2>
<p>Validates the publish folder and publishes the finished rig. If the scene has no <code>rigMain</code>, the open scene can be published as
rigMain as-is; the rig sets can be created on the spot with the Rig Sets rules through AYON's creator. Step-by-step <code>&gt;&gt;</code> log lines
around the rebuild help locate a Maya crash.</p>
"""),

("p_misc", "Panel types", "Material, Note, Delete and helpers", """
<h2>Helper panels</h2>
<p><b>Material</b> saves / loads material assignments (version-aware field). <b>Note</b> is a coloured text block that is never run.
<b>Delete</b> / <b>Zero Out</b> / <b>Parent</b> / <b>Instance</b> style panels perform that one clean-up or scene action when run.</p>
""" + see("p_all")),

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Features â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
("versions", "Features", "Version colours & Versions button", """
<h2>Version colours &amp; Versions button</h2>
<p>Every file panel (Script, Global Script, Import 3D, Skin JSON, Tweaker, Control Shapes, Material, Joint Positions, Joint Transfer,
CC Import, and the Blender File and ABC of the Blender panel) checks its file:</p>
<ul>
<li><span class="red">Light red</span> text + border: a <b>newer version exists</b> (next <code>_vNN</code> file, or next <code>vNN</code> folder).</li>
<li><span class="green">Light green</span>: this is the <b>latest</b> version. No colour: unknown (no version in the name, or file missing).</li>
<li>The check runs when the panel is built, when a KRT JSON is loaded, when you edit the path, when the panel runs, and on <b>Refresh</b>.</li>
<li><b>Versions</b> button (left click) and <b>Switch Version</b> in the ... menu: list <b>every file of the same kind in that folder</b> (newest first) with its saved date, even when the name differs or has no version number; the current one is ticked; pick one to switch. 3D files (.ma .mb .fbx .obj .abc) are listed together. The Blender File field is the exception - it keeps its own version list.</li>
<li>Scripts without <code>_vNN</code> in the name count as old when a sibling <code>name_vNN.py</code> exists.</li>
</ul>
<p>Hover the field for the path of the newer file. Directory listings are cached for a few seconds so many panels do not slow the server.</p>
""" + see("p_blender", "p_script", "t_file")),

("panelscripts", "Features", "PanelScripts folder", """
<h2>PanelScripts folder</h2>
<p>Everything that powers a special panel is kept together in <code>KRT/PanelScripts</code> so it can be updated in one place: Tweaker,
Facial Shape Extract, Breathing, CC Import + Auto Setup, Joint Transfer, Finger Fix, Joint Positions, their helpers, and
<code>blend_abc_tool</code> (headless Blender export, wrinkle check, mesh compare). Generic panels (Script, Model, Skin, Shapes, Material)
use <code>utils/</code>. A new panel's script goes in this folder and is imported with <code>from ..PanelScripts import name</code>.</p>
""" + see("p_all")),


("p_fan", "Panel types", "Fan + Stretchy", """
<h2>FAN + STRETCHY</h2>
<p>Builds the <b>fan joints</b> (body and hands) and the <b>stretchy muscle joints</b> on a CC character. Add it from the panel menu:
<i>Add Fan + Stretchy Panel</i>. Scripts: <code>PanelScripts/fan_stretchy</code> (<code>Fan.py</code>, <code>stretchy.py</code>,
<code>stretchyFanAttrExport.py</code>, <code>tool.py</code>).</p>
<ul>
<li><b>Body fan</b> - arms, legs, neck and face fan joints (the right side is mirrored from the left).</li>
<li><b>Hand fan</b> - fan joints on all fingers.</li>
<li><b>Stretchy joints</b> - trapezius, deltoid, biceps and triceps muscle joints.</li>
</ul>
<p>RUN builds the ticked parts. Everything is first built from the <b>default data</b> inside the scripts. If the panel has a <b>data file</b>
(JSON), its saved values are applied on top. Without a saved file the default data is used.</p>
<p><b>Saving your tweaks:</b> adjust the fan / stretchy attributes in the scene, then use the panel's <b>...</b> menu &gt; <i>Save Fan + Stretchy Data</i>
(Overwrite or New Version). It stores the same attributes that <code>stretchyFanAttrExport.py</code> prints, as a JSON in the rig's <b>Script</b> folder
(<code>Script</code>, <code>script</code>, <code>Scripts</code> - whichever already exists; a <code>Scripts</code> folder is created only if none exists).
Saving keeps values of parts that are not in the current scene.</p>
""" + see("p_all", "panelscripts")),

("pc2check", "Features", "Check PC2 in Blender", """
<h2>CHECK PC2 IN BLENDER</h2>
<p>The white / black button after <b>Publish Krishna</b>. Use it at the end of a rig, before publishing, to test that the PC2 export
works in Blender. First it asks what you want to see: <b>Blender file</b>, <b>Render</b> or <b>Both</b>.</p>
<ol>
<li>It takes the <b>Blender File</b> of the <a href="krt:p_blender">Import 3D + LOD Organize (Blender)</a> panel and reads its mesh names (headless Blender).</li>
<li>It loads the test animation of the Playblast tab (<code>.anim</code>, Controls Filter) on the rig controls of the <b>current Maya scene</b>.</li>
<li>It exports PC2 (the same method as the studio Cache Exporter) only for the Maya meshes whose name exists in that Blender file
(exact name, or with / without the <code>geo_</code> prefix).</li>
<li>It undoes the test animation. Then:
<ul><li><b>Blender file</b>: opens a <b>temporary copy</b> of the .blend in a normal Blender window, applies the PC2 with the pipeline tool's own
code (<i>Apply PC2 Caches &amp; Rotate</i>), sets the scene range and the current frame, and makes sure a <b>Timeline</b> is visible and zoomed to the
range - just drag the playhead to check. A message in Blender says how many meshes got a cache.</li>
<li><b>Render</b>: renders a quick preview sequence (Workbench, up to about 48 frames) in background Blender and plays it in a Maya window with a slider.
If the file has no camera, one is made that frames the character.</li></ul></li>
<li>While the temporary Blender is open, the button reads <b>DELETE / SAVE TEMP BLENDER FILE</b>. <b>Delete</b> closes Blender and deletes the temporary files. <b>Save</b> jumps to Blender and opens its Save As window; after saving, the PC2 files are copied next to the saved .blend (folder <code>&lt;name&gt;_pc2</code>), the caches are repointed there, and Blender asks whether to stay or close.</li>
<li>Temporary copies, PC2 files and preview frames are deleted when Blender / the preview window is closed. The server .blend is only read.</li>
</ol>
<p>A <b>progress window</b> shows each step; ESC cancels. If anything fails, an <b>error window</b> opens with the full text and a
<b>Copy to clipboard</b> button - paste it to whoever is helping. The Blender version that has the pipeline addon installed is used. Needs Studio Library
(mutils) for the .anim, like the Playblast tab.</p>
""" + see("p_blender", "t_pb")),

("tips", "Features", "Tips & troubleshooting", """
<h2>Tips</h2>
<ul>
<li>If KRT says it did not close normally last time, accepting restores the newest auto-saved backup.</li>
<li>Only the <i>parent</i> folder of KRT belongs on <code>sys.path</code>; if the KRT folder itself is there KRT removes it when it loads.</li>
<li>If <code>import UniUtils</code> fails, check the <a href="krt:t_root">Utilities</a> row path.</li>
<li>A Blender panel that exports empty hair transforms is fixed - re-run Blend -&gt; ABC.</li>
</ul>
<p style="color:#666;font-size:11px;">KRT owner / contact: Vishal Nagpal &lt;vishalnagpal878@gmail.com&gt;</p>
"""),
]


def _title_map():
    return {t[0]: t[2] for t in TOPICS}


def changelog_html():
    try:
        from .. import changelog
        entries = changelog.ENTRIES
    except Exception:
        entries = []
    out = ["<h2>What's new</h2><p>Generated from the changelog - always current.</p>"]
    for e in entries:
        out.append("<h3>v%s <span style='color:#888;font-size:11px'>%s</span></h3><ul>%s</ul>" % (
            e.get("version", ""), e.get("date", ""), "".join("<li>%s</li>" % c for c in e.get("changes", []))))
    return "".join(out)


def render(topic_id):
    """Full HTML for one topic (links resolved, changelog filled in)."""
    titles = _title_map()
    for tid, _sec, _title, html in TOPICS:
        if tid == topic_id:
            if html == "@@CHANGELOG@@":
                html = changelog_html()
            for k, v in titles.items():
                html = html.replace("@%s@" % k, v)
            return STYLE + html
    return STYLE + "<p>Topic not found.</p>"
