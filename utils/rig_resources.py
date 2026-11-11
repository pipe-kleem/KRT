"""Files KRT's rig tools need, shipped INSIDE KRT (Stage 61).

Everything lives under  KRT/resources/rig_utils/  so moving to another PC or
server means copying one folder. resource() returns the in-KRT copy and only
falls back to the old P: share path if the copy is missing.

    from KRT.utils import rig_resources; rig_resources.report()

report() says which files are local, and lists any absolute paths found
inside the .ma files (textures / nested references) that would still point
outside KRT.
"""
import os
import re

KRT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = os.path.join(KRT_DIR, "resources", "rig_utils").replace("\\", "/")
OLD_SHARE = "P:/rigging_team/Pipeline_share/RigUtils"

# relative path inside rig_utils/  (same layout as the old share)
FULLBODY_REF = "FullBodyJntTransfer/FullBodyJntTransfer_01.ma"
SPHERE_JSON = "FullBodyJntTransfer/sphere_02.json"
HAND_RIG = "HandSetup/Hand_Build_v01.ma"
TONGUE = "Tongue.py"
FINGER_ATTR = "Universal_Hand_Attribute_AutoChar_v5.py"   # kva "FingerAttr" panel
ALL = (FULLBODY_REF, SPHERE_JSON, HAND_RIG, TONGUE, FINGER_ATTR)
_TEXTURE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".exr", ".hdr", ".bmp")


def resource(rel):
    """In-KRT copy if it exists, otherwise the old share path."""
    local = RESOURCE_DIR + "/" + rel
    if os.path.isfile(local):
        return local
    return OLD_SHARE + "/" + rel


def read(rel):
    """Source text of a script resource, for exec() inside a KRT script
    panel - runs in that panel's namespace, so UniUtils/utils helpers work:
        from KRT.utils import rig_resources
        exec(rig_resources.read("Tongue.py"))
    """
    path = resource(rel)
    if not os.path.isfile(path):
        raise IOError("KRT resource not found: " + path)
    with open(path, "r") as f:
        return f.read()


def is_local(rel):
    return os.path.isfile(RESOURCE_DIR + "/" + rel)


# Absolute Windows/UNC paths in a Maya ASCII file: file -r ..., textures, caches
_ABS_PATH = re.compile(r'"((?:[A-Za-z]:|//|\\\\)[^"]+)"')


def external_paths(ma_path):
    found = set()
    try:
        with open(ma_path, "r", errors="ignore") as f:
            for line in f:
                if ("file " in line or "fileTextureName" in line or ".ftn" in line
                        or "cachePath" in line or "filename" in line.lower()):
                    found.update(m.replace("\\", "/") for m in _ABS_PATH.findall(line))
    except IOError:
        pass
    return sorted(found)


def report():
    print("[KRT resources] folder: " + RESOURCE_DIR)
    for rel in ALL:
        print("  {:<6} {}".format("OK" if is_local(rel) else "MISSING", rel))
        if is_local(rel) and rel.endswith(".ma"):
            paths = external_paths(RESOURCE_DIR + "/" + rel)
            textures = [p for p in paths if p.lower().endswith(_TEXTURE_EXT)]
            for p in paths:
                if p not in textures:
                    print("         still points outside KRT: " + p)
            if textures:
                # helper rigs - a missing texture only prints a warning
                print("         ({} texture path(s) outside KRT - harmless)".format(len(textures)))
    missing = [r for r in ALL if not is_local(r)]
    if missing:
        print("[KRT resources] missing files fall back to " + OLD_SHARE)
    return not missing
