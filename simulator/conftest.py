import sys
import types

# Collecting the sim_control package imports lvgl before test modules can stub it.
sys.modules.setdefault("lvgl", types.SimpleNamespace())
