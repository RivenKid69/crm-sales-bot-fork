#!/usr/bin/env python3
"""
Скрипт валидации условий и конфигурации.

Выполняет:
1. ConditionRegistries.validate_all() - проверка всех условий во всех реестрах
2. RuleResolver.validate_config() - проверка конфигурации rules/transitions

Используется в CI для раннего обнаружения ошибок в конфигурации.

Использование:
    python scripts/validate_conditions.py
    python scripts/validate_conditions.py --verbose
    python scripts/validate_conditions.py --generate-docs
    python scripts/validate_conditions.py --output-format json

Коды возврата:
    0 - валидация прошла успешно
    1 - найдены ошибки
    2 - критическая ошибка (импорт/инициализация)

Part of Phase 8: Tooling + CI (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import sys
import os
import argparse
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Добавляем путь к корню проекта и src
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_path = os.path.join(_project_root, "src")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)
os.chdir(_project_root)


@dataclass
class ValidationSummary:
    """Сводка результатов валидации."""
    conditions_total: int = 0
    conditions_passed: int = 0
    conditions_failed: int = 0
    conditions_errors: int = 0

    config_rules_checked: int = 0
    config_transitions_checked: int = 0
    config_errors: int = 0
    config_warnings: int = 0

    registries_validated: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Проверка успешности валидации."""
        return (
            self.conditions_failed == 0 and
            self.conditions_errors == 0 and
            self.config_errors == 0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь."""
        return {
            "is_valid": self.is_valid,
            "conditions": {
                "total": self.conditions_total,
                "passed": self.conditions_passed,
                "failed": self.conditions_failed,
                "errors": self.conditions_errors,
            },
            "config": {
                "rules_checked": self.config_rules_checked,
                "transitions_checked": self.config_transitions_checked,
                "errors": self.config_errors,
                "warnings": self.config_warnings,
            },
            "registries": self.registries_validated,
        }


def create_context_factories() -> Dict[str, callable]:
    """
    Создаёт фабрики контекстов для каждого домена.

    Returns:
        Словарь {имя_реестра: фабрика_контекста}
    """
    from src.conditions.state_machine.context import EvaluatorContext
    from src.conditions.policy.context import PolicyContext
    from src.conditions.fallback.context import FallbackContext
    from src.conditions.personalization.context import PersonalizationContext
    from src.conditions.base import SimpleContext

    return {
        "shared": lambda: SimpleContext(
            collected_data={"company_size": 10, "pain_category": "manual_work"},
            state="spin_situation",
            turn_number=5
        ),
        "state_machine": lambda: EvaluatorContext.create_test_context(
            collected_data={"company_size": 10, "pain_category": "manual_work"},
            state="spin_situation",
            turn_number=5,
            current_intent="price_question"
        ),
        "policy": lambda: PolicyContext.create_test_context(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=5
        ),
        "fallback": lambda: FallbackContext.create_test_context(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=5
        ),
        "personalization": lambda: PersonalizationContext.create_test_context(
            collected_data={"company_size": 10, "pain_category": "manual_work"},
            state="presentation",
            turn_number=5
        ),
    }


def validate_conditions(verbose: bool = False) -> tuple:
    """
    Валидация всех условий во всех реестрах.

    Args:
        verbose: Подробный вывод

    Returns:
        (summary_dict, errors_list, warnings_list)
    """
    from src.conditions import ConditionRegistries

    ctx_factories = create_context_factories()
    results = ConditionRegistries.validate_all(ctx_factories)

    summary = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "registries": []
    }

    all_errors = []
    all_warnings = []

    for registry_name, result in results.items():
        summary["registries"].append(registry_name)
        summary["passed"] += len(result.passed)
        summary["failed"] += len(result.failed)
        summary["errors"] += len(result.errors)
        summary["total"] += result.total_count

        if verbose:
            print(f"\n  [{registry_name}] {len(result.passed)} passed, "
                  f"{len(result.failed)} failed, {len(result.errors)} errors")

        for fail in result.failed:
            error_msg = f"[{registry_name}] Condition '{fail['name']}' failed: {fail.get('reason', 'unknown')}"
            all_errors.append(error_msg)
            if verbose:
                print(f"    FAIL: {fail['name']} - {fail.get('reason', '')}")

        for err in result.errors:
            error_msg = f"[{registry_name}] Condition '{err['name']}' error: {err.get('error', 'unknown')}"
            all_errors.append(error_msg)
            if verbose:
                print(f"    ERROR: {err['name']} - {err.get('error', '')}")

    return summary, all_errors, all_warnings


def validate_config(verbose: bool = False) -> tuple:
    """
    Валидация конфигурации rules/transitions.

    Args:
        verbose: Подробный вывод

    Returns:
        (summary_dict, errors_list, warnings_list)
    """
    from src.conditions.state_machine.registry import sm_registry
    from src.rules.resolver import RuleResolver
    from src.config import SALES_STATES

    resolver = RuleResolver(sm_registry)

    # Известные состояния
    known_states = set(SALES_STATES.keys())

    # Валидация (без глобальных правил - они встроены в каждое состояние)
    result = resolver.validate_config(
        states_config=SALES_STATES,
        global_rules={},  # Глобальные правила встроены в SALES_STATES
        known_states=known_states
    )

    summary = {
        "rules_checked": result.checked_rules,
        "transitions_checked": result.checked_transitions,
        "errors": len(result.errors),
        "warnings": len(result.warnings),
        "is_valid": result.is_valid
    }

    all_errors = []
    all_warnings = []

    if verbose and result.errors:
        print(f"\n  Config errors:")

    for error in result.errors:
        error_msg = f"[{error.state}] {error.error_type}: {error.message}"
        if error.rule_name:
            error_msg += f" (rule: {error.rule_name})"
        all_errors.append(error_msg)
        if verbose:
            print(f"    ERROR: {error_msg}")

    if verbose and result.warnings:
        print(f"\n  Config warnings:")

    for warning in result.warnings:
        warning_msg = f"[{warning.state}] {warning.error_type}: {warning.message}"
        if warning.rule_name:
            warning_msg += f" (rule: {warning.rule_name})"
        all_warnings.append(warning_msg)
        if verbose:
            print(f"    WARN: {warning_msg}")

    return summary, all_errors, all_warnings


def get_stats(verbose: bool = False) -> Dict[str, Any]:
    """
    Получение статистики по всем реестрам.

    Args:
        verbose: Подробный вывод

    Returns:
        Статистика
    """
    from src.conditions import ConditionRegistries

    stats = ConditionRegistries.get_stats()

    if verbose:
        print(f"\n  Total registries: {stats['total_registries']}")
        print(f"  Total conditions: {stats['total_conditions']}")

        for name, reg_stats in stats['registries'].items():
            print(f"\n  [{name}] {reg_stats['total_conditions']} conditions")
            for cat, count in reg_stats.get('conditions_by_category', {}).items():
                print(f"    - {cat}: {count}")

    return stats


def generate_documentation(output_path: Optional[str] = None) -> str:
    """
    Генерация документации по условиям.

    Args:
        output_path: Путь для сохранения (если указан)

    Returns:
        Сгенерированная документация
    """
    from src.conditions import ConditionRegistries

    docs = ConditionRegistries.generate_documentation()

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(docs)
        print(f"Documentation saved to: {output_path}")

    return docs


def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(
        description="Validate conditional rules configuration"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--generate-docs',
        metavar='PATH',
        nargs='?',
        const='docs/CONDITIONS.md',
        help='Generate documentation (default: docs/CONDITIONS.md)'
    )
    parser.add_argument(
        '--output-format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show statistics, skip validation'
    )

    args = parser.parse_args()

    exit_code = 0
    summary = ValidationSummary()
    all_errors = []
    all_warnings = []

    try:
        # Заголовок
        if args.output_format == 'text':
            print("=" * 60)
            print("CONDITIONAL RULES VALIDATION")
            print("=" * 60)

        # Генерация документации
        if args.generate_docs:
            if args.output_format == 'text':
                print(f"\nGenerating documentation to {args.generate_docs}...")
            generate_documentation(args.generate_docs)
            if args.output_format == 'text':
                print("Done!")

        # Только статистика
        if args.stats_only:
            if args.output_format == 'text':
                print("\n## STATISTICS")
                print("-" * 40)
            stats = get_stats(verbose=True)
            if args.output_format == 'json':
                print(json.dumps(stats, indent=2, ensure_ascii=False))
            return 0

        # Валидация условий
        if args.output_format == 'text':
            print("\n## VALIDATING CONDITIONS")
            print("-" * 40)

        cond_summary, cond_errors, cond_warnings = validate_conditions(
            verbose=args.verbose
        )

        summary.conditions_total = cond_summary['total']
        summary.conditions_passed = cond_summary['passed']
        summary.conditions_failed = cond_summary['failed']
        summary.conditions_errors = cond_summary['errors']
        summary.registries_validated = cond_summary['registries']

        all_errors.extend(cond_errors)
        all_warnings.extend(cond_warnings)

        if args.output_format == 'text':
            print(f"\n  Conditions: {summary.conditions_passed}/{summary.conditions_total} passed")
            if summary.conditions_failed > 0:
                print(f"  Failed: {summary.conditions_failed}")
            if summary.conditions_errors > 0:
                print(f"  Errors: {summary.conditions_errors}")

        # Валидация конфигурации
        if args.output_format == 'text':
            print("\n## VALIDATING CONFIG")
            print("-" * 40)

        config_summary, config_errors, config_warnings = validate_config(
            verbose=args.verbose
        )

        summary.config_rules_checked = config_summary['rules_checked']
        summary.config_transitions_checked = config_summary['transitions_checked']
        summary.config_errors = config_summary['errors']
        summary.config_warnings = config_summary['warnings']

        all_errors.extend(config_errors)
        all_warnings.extend(config_warnings)

        if args.output_format == 'text':
            print(f"\n  Rules checked: {summary.config_rules_checked}")
            print(f"  Transitions checked: {summary.config_transitions_checked}")
            if summary.config_errors > 0:
                print(f"  Errors: {summary.config_errors}")
            if summary.config_warnings > 0:
                print(f"  Warnings: {summary.config_warnings}")

        # Итоговый результат
        if args.output_format == 'text':
            print("\n" + "=" * 60)
            if summary.is_valid:
                print("RESULT: PASSED")
                print("All conditions and config are valid!")
            else:
                print("RESULT: FAILED")
                print(f"Errors found: {len(all_errors)}")
                if all_errors:
                    print("\nErrors:")
                    for err in all_errors:
                        print(f"  - {err}")
                exit_code = 1
            print("=" * 60)

        elif args.output_format == 'json':
            output = {
                "summary": summary.to_dict(),
                "errors": all_errors,
                "warnings": all_warnings,
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
            if not summary.is_valid:
                exit_code = 1

    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure you're running from the project root directory")
        exit_code = 2
    except Exception as e:
        print(f"Critical error: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 2

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
