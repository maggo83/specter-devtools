import sys
import types

# Collecting the sim_control package imports lvgl before test modules can stub it.
sys.modules.setdefault("lvgl", types.SimpleNamespace())
sys.modules.setdefault("utime", types.SimpleNamespace(ticks_ms=lambda: 0, ticks_diff=lambda a, b: a - b))
