"""
Type shims for occasional missing types in certain edge cases.
"""

from . import deadcells
from typing import Dict, Any

def shims_for(name: str) -> Dict[str, Any]:
    match name:
        case "deadcells":
            return deadcells.TYPES
    raise ValueError("No such shim library! Maybe open a PR to add one?")