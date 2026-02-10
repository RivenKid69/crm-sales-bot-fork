"""Guards for legacy->canonical import identity."""

import importlib
import sys
from pathlib import Path

from src.import_aliases import alias_roots

def _is_alias_family(name: str) -> bool:
    for root in alias_roots():
        if name == root or name.startswith(f"{root}."):
            return True
        if name == f"src.{root}" or name.startswith(f"src.{root}."):
            return True
    return False

def test_legacy_roots_resolve_to_canonical_modules() -> None:
    for root in sorted(alias_roots()):
        canonical = importlib.import_module(f"src.{root}")
        legacy = importlib.import_module(root)
        assert legacy is canonical

def test_no_duplicate_module_objects_for_same_file() -> None:
    # Force-import representative nested modules via both namespaces.
    paired_modules = [
        "blackboard.orchestrator",
        "blackboard.sources.intent_processor",
        "config_loader",
        "state_machine",
        "settings",
        "feature_flags",
        "context_envelope",
        "conditions.policy.context",
        "conditions.state_machine.context",
    ]
    for legacy_name in paired_modules:
        canonical_name = f"src.{legacy_name}"
        canonical = importlib.import_module(canonical_name)
        legacy = importlib.import_module(legacy_name)
        assert legacy is canonical

    by_file: dict[Path, dict[int, list[str]]] = {}
    for name, module in list(sys.modules.items()):
        if not _is_alias_family(name):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        key = Path(module_file).resolve()
        by_file.setdefault(key, {}).setdefault(id(module), []).append(name)

    duplicates = {
        str(path): groups
        for path, groups in by_file.items()
        if len(groups) > 1
    }
    assert not duplicates, f"Duplicate module objects detected for same file: {duplicates}"
