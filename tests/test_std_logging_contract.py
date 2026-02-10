"""Contract guard for stdlib logging.Logger kwargs usage.

This test enforces that loggers created via ``logging.getLogger(...)`` use only
official stdlib keyword arguments when calling logger methods.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List, Set


ALLOWED_LOG_KWARGS = {"exc_info", "stack_info", "stacklevel", "extra"}
LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
ROOT_SCAN_PATHS = [Path("src"), Path("tests"), Path("scripts"), Path("conftest.py")]


def _root_python_files() -> List[Path]:
    files: List[Path] = []
    for path in sorted(Path(".").iterdir()):
        if path.is_file() and path.suffix == ".py" and path.name != "conftest.py":
            files.append(path)
    return files


def _python_files() -> List[Path]:
    files: List[Path] = []
    for path in ROOT_SCAN_PATHS:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    files.extend(_root_python_files())
    return files


def _resolve_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _logging_aliases(tree: ast.AST) -> tuple[Set[str], Set[str]]:
    logging_modules: Set[str] = set()
    get_logger_aliases: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    logging_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module != "logging":
                continue
            for alias in node.names:
                if alias.name == "getLogger":
                    get_logger_aliases.add(alias.asname or alias.name)

    return logging_modules, get_logger_aliases


def _is_get_logger_call(
    call: ast.Call,
    logging_modules: Set[str],
    get_logger_aliases: Set[str],
) -> bool:
    if isinstance(call.func, ast.Name):
        return call.func.id in get_logger_aliases

    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return (
            call.func.value.id in logging_modules
            and call.func.attr == "getLogger"
        )

    return False


def _collect_std_loggers(
    tree: ast.AST,
    logging_modules: Set[str],
    get_logger_aliases: Set[str],
) -> Set[str]:
    logger_refs: Set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if not _is_get_logger_call(node.value, logging_modules, get_logger_aliases):
            continue
        for target in node.targets:
            target_name = _resolve_name(target)
            if target_name:
                logger_refs.add(target_name)

    return logger_refs


def _logger_ref_from_call(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    return _resolve_name(call.func.value)


def _violations_for_file(path: Path) -> Iterable[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    logging_modules, get_logger_aliases = _logging_aliases(tree)
    std_loggers = _collect_std_loggers(tree, logging_modules, get_logger_aliases)
    if not std_loggers:
        return []

    violations: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOGGER_METHODS:
            continue

        logger_ref = _logger_ref_from_call(node)
        if logger_ref not in std_loggers:
            continue

        forbidden = sorted(
            kw.arg for kw in node.keywords
            if kw.arg is not None and kw.arg not in ALLOWED_LOG_KWARGS
        )
        if forbidden:
            violations.append(
                f"{path}:{node.lineno} logger.{node.func.attr} forbidden kwargs: {', '.join(forbidden)}"
            )

    return violations


def test_std_logging_logger_kwargs_contract() -> None:
    violations: List[str] = []
    for path in _python_files():
        violations.extend(_violations_for_file(path))

    assert not violations, "Std logging kwargs contract violated:\n" + "\n".join(violations)
