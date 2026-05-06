"""Helper: load `media-import` (no .py extension) as a Python module."""

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "media-import"


def load() -> object:
    if "media_import" in sys.modules:
        return sys.modules["media_import"]
    loader = importlib.machinery.SourceFileLoader("media_import", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("media_import", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["media_import"] = module
    loader.exec_module(module)
    return module
