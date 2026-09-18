import sys
from .compat import QtWidgets

# 1. Cleanly eliminate lingering interface elements and stop ongoing background threads
for w in QtWidgets.QApplication.topLevelWidgets():
    if w.objectName() == "KRT_Window":
        w.close()
        w.deleteLater()

# 2. Safely wipe memory cache without leaving orphaned active UI elements behind
modules_to_delete = [mod for mod in sys.modules if mod.startswith('KRT')]
for mod in modules_to_delete:
    del sys.modules[mod]

# 3. Import fresh and launch the tool natively inside Maya
import KRT.main as krt
krt.run_tool()