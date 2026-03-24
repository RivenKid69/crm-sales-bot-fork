from __future__ import annotations

from typing import Any, Callable


def is_terminal_field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def normalize_terminal_requirement_spec(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict):
        required_any = list(spec.get("required_any") or [])
        required_all = list(spec.get("required_all") or [])
        required_if_true_raw = spec.get("required_if_true") or {}
        required_if_true = {
            str(field): list(fields or [])
            for field, fields in required_if_true_raw.items()
            if isinstance(fields, (list, tuple, set))
        }
        return {
            "required_any": required_any,
            "required_all": required_all,
            "required_if_true": required_if_true,
        }
    if isinstance(spec, (list, tuple, set)):
        return {
            "required_any": [],
            "required_all": list(spec),
            "required_if_true": {},
        }
    return {
        "required_any": [],
        "required_all": [],
        "required_if_true": {},
    }


def terminal_requirement_field_names(spec: Any) -> list[str]:
    normalized = normalize_terminal_requirement_spec(spec)
    ordered_fields: list[str] = []
    seen: set[str] = set()

    for field in normalized["required_any"]:
        field_name = str(field)
        if field_name not in seen:
            seen.add(field_name)
            ordered_fields.append(field_name)

    for field in normalized["required_all"]:
        field_name = str(field)
        if field_name not in seen:
            seen.add(field_name)
            ordered_fields.append(field_name)

    for dependent_fields in normalized["required_if_true"].values():
        for field in dependent_fields:
            field_name = str(field)
            if field_name not in seen:
                seen.add(field_name)
                ordered_fields.append(field_name)

    return ordered_fields


def active_terminal_requirement_field_names(
    spec: Any,
    *,
    get_value: Callable[[str], Any] | None = None,
    satisfied_overrides: set[str] | None = None,
) -> list[str]:
    normalized = normalize_terminal_requirement_spec(spec)
    get_value = get_value or (lambda _field: None)
    overrides = set(satisfied_overrides or ())
    ordered_fields: list[str] = []
    seen: set[str] = set()

    for field in normalized["required_any"]:
        field_name = str(field)
        if field_name not in seen:
            seen.add(field_name)
            ordered_fields.append(field_name)

    for field in normalized["required_all"]:
        field_name = str(field)
        if field_name not in seen:
            seen.add(field_name)
            ordered_fields.append(field_name)

    for trigger_field, dependent_fields in normalized["required_if_true"].items():
        trigger_value = True if trigger_field in overrides else get_value(trigger_field)
        if not bool(trigger_value):
            continue
        for field in dependent_fields:
            field_name = str(field)
            if field_name not in seen:
                seen.add(field_name)
                ordered_fields.append(field_name)

    return ordered_fields


def missing_terminal_fields(
    spec: Any,
    *,
    has_field: Callable[[str], bool],
    get_value: Callable[[str], Any] | None = None,
    satisfied_overrides: set[str] | None = None,
) -> list[str]:
    normalized = normalize_terminal_requirement_spec(spec)
    get_value = get_value or (lambda _field: None)
    overrides = set(satisfied_overrides or ())
    missing: list[str] = []

    required_any = normalized["required_any"]
    if required_any and not any(field in overrides or has_field(field) for field in required_any):
        missing.append(str(required_any[0]))

    for field in normalized["required_all"]:
        if field in overrides:
            continue
        if not has_field(field):
            missing.append(str(field))

    for trigger_field, dependent_fields in normalized["required_if_true"].items():
        trigger_value = True if trigger_field in overrides else get_value(trigger_field)
        if not bool(trigger_value):
            continue
        for field in dependent_fields:
            if field in overrides:
                continue
            if not has_field(field):
                missing.append(str(field))

    seen: set[str] = set()
    ordered_missing: list[str] = []
    for field in missing:
        if field not in seen:
            seen.add(field)
            ordered_missing.append(field)
    return ordered_missing


def terminal_requirements_satisfied(
    spec: Any,
    *,
    has_field: Callable[[str], bool],
    get_value: Callable[[str], Any] | None = None,
    satisfied_overrides: set[str] | None = None,
) -> bool:
    return not missing_terminal_fields(
        spec,
        has_field=has_field,
        get_value=get_value,
        satisfied_overrides=satisfied_overrides,
    )
