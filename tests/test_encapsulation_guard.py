# tests/test_encapsulation_guard.py

"""
CI Encapsulation Guard — prevents regression of private-attr access violations.

Scans src/blackboard/sources/ and src/blackboard/orchestrator.py for patterns
that access private attributes across ownership boundaries:
- blackboard._<attr>  (sources/orchestrator reaching into blackboard internals)
- _state_machine._<attr>  (reaching into state_machine internals)
- state_machine._<attr>  (same, different variable name)

Allowed exceptions:
- self._<attr> (accessing own private attrs)
- Comments and docstrings
- TYPE_CHECKING blocks
"""

import re
import pytest
from pathlib import Path


SRC_ROOT = Path(__file__).parent.parent / "src"

# Files that must be encapsulation-clean
GUARDED_FILES = [
    SRC_ROOT / "blackboard" / "sources",   # entire directory
    SRC_ROOT / "blackboard" / "orchestrator.py",
]

# Regex patterns for encapsulation violations
VIOLATION_PATTERNS = [
    # blackboard._foo  (not blackboard.__dunder__)
    (r'\bblackboard\._(?!_)\w+', "blackboard._<private> access"),
    # state_machine._foo  (any variable named *state_machine*)
    (r'\bstate_machine\._(?!_)\w+', "state_machine._<private> access"),
    # _state_machine._foo (self._state_machine._attr)
    (r'_state_machine\._(?!_)\w+', "_state_machine._<private> access"),
]

# Lines matching these patterns are allowed (comments, docstrings, strings)
SKIP_LINE_PATTERNS = [
    re.compile(r'^\s*#'),          # comment lines
    re.compile(r'^\s*"""'),        # docstring start
    re.compile(r"^\s*'''"),        # docstring start (single-quote)
    re.compile(r'^\s*".*"'),      # string-only lines
    re.compile(r"^\s*'.*'"),      # string-only lines
]


def _collect_python_files():
    """Collect all Python files from guarded paths."""
    files = []
    for path in GUARDED_FILES:
        if path.is_dir():
            files.extend(path.glob("*.py"))
        elif path.is_file():
            files.append(path)
    return sorted(files)


def _is_skip_line(line: str) -> bool:
    """Check if line is a comment or docstring (not real code)."""
    stripped = line.strip()
    if not stripped:
        return True
    for pat in SKIP_LINE_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _scan_file(filepath: Path):
    """Scan a single file for encapsulation violations."""
    violations = []
    in_docstring = False

    with open(filepath) as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()

            # Track docstring blocks
            triple_double = stripped.count('"""')
            triple_single = stripped.count("'''")
            if triple_double == 1 or triple_single == 1:
                in_docstring = not in_docstring
                continue
            if triple_double >= 2 or triple_single >= 2:
                # Single-line docstring: """..."""
                continue

            if in_docstring:
                continue

            if _is_skip_line(line):
                continue

            for pattern, description in VIOLATION_PATTERNS:
                matches = re.findall(pattern, line)
                for match in matches:
                    # Skip self._attr (own private access is fine)
                    if f"self.{match}" in line or f"self.{match.split('.', 1)[-1]}" in line:
                        continue
                    violations.append(
                        f"{filepath.relative_to(SRC_ROOT)}:{lineno}: "
                        f"{description} → {match}"
                    )

    return violations


class TestEncapsulationGuard:
    """CI guard: no private-attr access across ownership boundaries."""

    def test_no_private_attr_violations_in_sources(self):
        """Scan all knowledge sources for encapsulation violations."""
        all_violations = []
        for filepath in _collect_python_files():
            violations = _scan_file(filepath)
            all_violations.extend(violations)

        if all_violations:
            report = "\n".join(all_violations)
            pytest.fail(
                f"Encapsulation violations found ({len(all_violations)}):\n{report}\n\n"
                "Fix: use ContextSnapshot fields or public API instead of private attrs."
            )

    def test_guarded_files_exist(self):
        """Verify that guarded paths actually exist (sanity check)."""
        for path in GUARDED_FILES:
            assert path.exists(), f"Guarded path does not exist: {path}"
