"""Connect to a running DaVinci Resolve Studio through its external scripting API
(Preferences → System → General → External scripting using: Local). Returns the `resolve` object or raises with the reason."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Blackmagic's documented install locations (README "Configuration"); env vars of the same names override them.
_DEFAULTS = {
    "darwin": ("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
               "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"),
    "linux": ("/opt/resolve/Developer/Scripting", "/opt/resolve/libs/Fusion/fusionscript.so"),
}


def resolve_app(host: str = "127.0.0.1"):
    api, lib = _DEFAULTS.get(sys.platform, ("", ""))
    api = os.environ.setdefault("RESOLVE_SCRIPT_API", api)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib)
    modules = str(Path(api) / "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    dvr = importlib.import_module("DaVinciResolveScript")
    resolve = dvr.scriptapp("Resolve", host)
    if resolve is None:
        raise RuntimeError("Resolve did not answer: is it running, and is External scripting set to Local?")
    return resolve
