import maya.cmds as cmds

WINDOW_NAME = "VertexSkinWeightChecker"


def get_skin_cluster(mesh):
    history = cmds.listHistory(mesh) or []
    skin_clusters = cmds.ls(history, type="skinCluster")
    if skin_clusters:
        return skin_clusters[0]
    return None


def check_vertex_weights(*args):

    selection = cmds.ls(sl=True, fl=True)

    if not selection:
        cmds.warning("Please select at least one vertex.")
        return

    cmds.textScrollList("weightList", e=True, removeAll=True)

    for component in selection:

        if ".vtx[" not in component:
            continue

        mesh = component.split(".")[0]

        skin_cluster = get_skin_cluster(mesh)

        if not skin_cluster:
            cmds.textScrollList(
                "weightList",
                e=True,
                append="{} : No SkinCluster Found".format(component)
            )
            continue

        influences = cmds.skinPercent(
            skin_cluster,
            component,
            query=True,
            transform=None
        )

        weights = cmds.skinPercent(
            skin_cluster,
            component,
            query=True,
            value=True
        )

        cmds.textScrollList(
            "weightList",
            e=True,
            append="--------------------------------------------------"
        )

        cmds.textScrollList(
            "weightList",
            e=True,
            append="Vertex : {}".format(component)
        )

        count = 0

        for joint, weight in zip(influences, weights):

            if weight > 0.0:
                count += 1

                cmds.textScrollList(
                    "weightList",
                    e=True,
                    append="{}   =   {:.6f}".format(joint, weight)
                )

        cmds.textScrollList(
            "weightList",
            e=True,
            append="Total Influencing Joints : {}".format(count)
        )


def create_ui():

    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    cmds.window(
        WINDOW_NAME,
        title="Vertex Skin Weight Checker",
        widthHeight=(600, 400)
    )

    cmds.columnLayout(adjustableColumn=True)

    cmds.separator(h=10)

    cmds.button(
        label="Check Selected Vertex Weights",
        height=40,
        command=check_vertex_weights
    )

    cmds.separator(h=10)

    cmds.text(
        label="Select one or more vertices and click the button."
    )

    cmds.separator(h=10)

    cmds.textScrollList(
        "weightList",
        allowMultiSelection=False,
        height=300
    )

    cmds.showWindow(WINDOW_NAME)


create_ui()