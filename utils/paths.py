"""Auto-split from utils.py."""
from ._shared import *

# Stage 42: the studio-wide folder every rig lives under. Used as the
# starting directory for EVERY browse dialog when no Rig Root is set yet,
# and as the default parent in the Initialize Project dialog.
DEFAULT_RIGS_ROOT = r"P:\rigging_team\Rigging_local_share\all_Rigs"


def get_versioned_path(file_path, get_latest=False):
    directory = os.path.dirname(file_path)
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    base_name = re.sub(r'_v\d+$', '', base_name)
    
    if not os.path.exists(directory):
        if get_latest: return file_path 
        return os.path.join(directory, "{}_v001{}".format(base_name, ext)).replace('\\', '/')

    highest_version = 0
    pattern = re.compile(r"^{}_v(\d+){}$".format(re.escape(base_name), re.escape(ext)))

    if os.path.exists(directory):
        for f in os.listdir(directory):
            match = pattern.match(f)
            if match:
                version = int(match.group(1))
                if version > highest_version:
                    highest_version = version

    if get_latest:
        if highest_version == 0: return file_path
        latest_name = "{}_v{:03d}{}".format(base_name, highest_version, ext)
        return os.path.join(directory, latest_name).replace('\\', '/')
    else:
        next_version = highest_version + 1
        new_name = "{}_v{:03d}{}".format(base_name, next_version, ext)
        return os.path.join(directory, new_name).replace('\\', '/')
