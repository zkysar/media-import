"""Helper: load `dji-import` (no .py extension) as a Python module."""

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "dji-import"


def load() -> object:
    if "dji_import" in sys.modules:
        return sys.modules["dji_import"]
    loader = importlib.machinery.SourceFileLoader("dji_import", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("dji_import", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["dji_import"] = module
    loader.exec_module(module)
    return module
