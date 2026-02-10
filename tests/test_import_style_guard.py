"""Static guard preventing new bare imports for canonical src.* modules."""

import ast
from pathlib import Path

BANNED_ROOT_IMPORTS = {
    "blackboard",
    "config_loader",
    "state_machine",
    "settings",
    "feature_flags",
    "context_envelope",
    "conditions",
}

SCAN_PATHS = [Path("src"), Path("tests"), Path("scripts"), Path("conftest.py")]

def _python_files() -> list[Path]:
    files: list[Path] = []
    for path in SCAN_PATHS:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files

def test_no_bare_imports_for_canonical_modules() -> None:
    violations: list[str] = []

    for file_path in _python_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in BANNED_ROOT_IMPORTS:
                        violations.append(f"{file_path}:{node.lineno} import {alias.name}")

            if isinstance(node, ast.ImportFrom):
                if node.level != 0 or not node.module:
                    continue
                root = node.module.split(".", 1)[0]
                if root in BANNED_ROOT_IMPORTS:
                    violations.append(f"{file_path}:{node.lineno} from {node.module}")

    assert not violations, "Bare imports found:\n" + "\n".join(violations)
