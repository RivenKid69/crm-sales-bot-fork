"""Legacy import aliases for canonical `src.*` namespace."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import threading
import warnings
from typing import Optional

_ALIAS_ROOTS = frozenset(
    {
        "blackboard",
        "config_loader",
        "state_machine",
        "settings",
        "feature_flags",
        "context_envelope",
        "conditions",
    }
)

_install_lock = threading.RLock()
_installed = False
_warned_roots: set[str] = set()


def _canonical_name(fullname: str) -> Optional[str]:
    if fullname.startswith("src."):
        return None
    root = fullname.split(".", 1)[0]
    if root not in _ALIAS_ROOTS:
        return None
    return f"src.{fullname}"


def _warn_legacy_import(fullname: str) -> None:
    root = fullname.split(".", 1)[0]
    if root in _warned_roots:
        return
    _warned_roots.add(root)
    warnings.warn(
        f"Legacy import '{root}' is deprecated; use 'src.{root}' instead.",
        DeprecationWarning,
        stacklevel=3,
    )


def _bind_alias(alias_name: str, module: object) -> None:
    existing = sys.modules.get(alias_name)
    if existing is None:
        sys.modules[alias_name] = module
        return
    if existing is not module:
        raise ImportError(
            f"Import alias conflict for '{alias_name}': {existing!r} != {module!r}"
        )


class _LegacyAliasLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, canonical: str):
        self._fullname = fullname
        self._canonical = canonical

    def create_module(self, spec):  # type: ignore[override]
        module = importlib.import_module(self._canonical)
        _bind_alias(self._fullname, module)
        _warn_legacy_import(self._fullname)
        return module

    def exec_module(self, module):  # type: ignore[override]
        return None


class _LegacyAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):  # type: ignore[override]
        canonical = _canonical_name(fullname)
        if canonical is None:
            return None

        canonical_spec = importlib.util.find_spec(canonical)
        if canonical_spec is None:
            return None

        is_package = canonical_spec.submodule_search_locations is not None
        spec = importlib.machinery.ModuleSpec(
            name=fullname,
            loader=_LegacyAliasLoader(fullname, canonical),
            is_package=is_package,
        )
        spec.origin = canonical_spec.origin
        if is_package and canonical_spec.submodule_search_locations is not None:
            spec.submodule_search_locations = list(canonical_spec.submodule_search_locations)
        return spec


def _alias_already_loaded_modules() -> None:
    for name, module in list(sys.modules.items()):
        if not name.startswith("src."):
            continue
        legacy = name[4:]
        root = legacy.split(".", 1)[0]
        if root in _ALIAS_ROOTS:
            _bind_alias(legacy, module)


def install_legacy_import_aliases() -> None:
    """Install import aliases so legacy names map to canonical `src.*` modules."""
    global _installed

    with _install_lock:
        if _installed:
            return

        if not any(isinstance(finder, _LegacyAliasFinder) for finder in sys.meta_path):
            sys.meta_path.insert(0, _LegacyAliasFinder())

        _alias_already_loaded_modules()
        _installed = True


def alias_roots() -> frozenset[str]:
    """Return configured legacy alias roots."""
    return _ALIAS_ROOTS
