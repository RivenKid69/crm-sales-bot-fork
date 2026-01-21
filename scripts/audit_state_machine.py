#!/usr/bin/env python3
"""
State Machine Deep Audit Script

Validates:
1. Intent coverage (classifier vs transitions/rules)
2. Dead-ends and unreachable states
3. Infinite loops detection
4. Priority conflicts (rules vs transitions, mixins)
5. Unresolved parameters
6. Condition existence in registry
7. Semantic issues

Run: python scripts/audit_state_machine.py
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_loader import ConfigLoader, FlowConfig
from src.conditions.state_machine.registry import sm_registry


@dataclass
class Issue:
    """Represents a found issue."""
    severity: str  # HIGH, MEDIUM, LOW
    title: str
    location: str  # file:line or state/flow
    description: str
    consequence: str
    reproduction: str = ""
    recommendation: str = ""
    impact_percent: float = 0.0  # Estimated % of dialogues affected


@dataclass
class AuditReport:
    """Audit results."""
    issues: List[Issue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def add(self, issue: Issue):
        self.issues.append(issue)

    def by_severity(self, severity: str) -> List[Issue]:
        return [i for i in self.issues if i.severity == severity]

    def print_report(self):
        print("\n" + "=" * 80)
        print("STATE MACHINE AUDIT REPORT")
        print("=" * 80)

        # Summary
        high = len(self.by_severity("HIGH"))
        medium = len(self.by_severity("MEDIUM"))
        low = len(self.by_severity("LOW"))

        print(f"\nSUMMARY: {high} HIGH, {medium} MEDIUM, {low} LOW issues found\n")

        # Stats
        if self.stats:
            print("STATISTICS:")
            for key, value in self.stats.items():
                print(f"  {key}: {value}")
            print()

        # Issues by severity
        for severity in ["HIGH", "MEDIUM", "LOW"]:
            issues = self.by_severity(severity)
            if issues:
                print(f"\n{'=' * 40}")
                print(f"[{severity}] ISSUES ({len(issues)})")
                print("=" * 40)

                for i, issue in enumerate(issues, 1):
                    print(f"\n{i}. {issue.title}")
                    print(f"   Location: {issue.location}")
                    print(f"   What: {issue.description}")
                    print(f"   Consequence: {issue.consequence}")
                    if issue.reproduction:
                        print(f"   Reproduction: {issue.reproduction}")
                    if issue.recommendation:
                        print(f"   Recommendation: {issue.recommendation}")
                    if issue.impact_percent > 0:
                        print(f"   Impact: ~{issue.impact_percent:.1f}% of dialogues")


class StateMachineAuditor:
    """Deep auditor for State Machine configuration."""

    # Intents from classifier (prompts.py)
    CLASSIFIER_INTENTS = {
        # Greetings and communication
        "greeting", "agreement", "gratitude", "farewell", "small_talk",
        # Price questions
        "price_question", "pricing_details", "objection_price",
        # Product questions
        "question_features", "question_integrations", "comparison",
        # Contact requests
        "callback_request", "contact_provided", "demo_request", "consultation_request",
        # SPIN data
        "situation_provided", "problem_revealed", "implication_acknowledged",
        "need_expressed", "no_problem", "no_need", "info_provided",
        # Objections
        "objection_no_time", "objection_timing", "objection_think",
        "objection_complexity", "objection_competitor", "objection_trust",
        "objection_no_need", "rejection",
        # Dialogue control
        "unclear", "go_back", "correct_info",
    }

    # Special intents that may appear in transitions but not from classifier
    SPECIAL_TRANSITION_KEYS = {
        "data_complete", "any", "go_back",
    }

    def __init__(self):
        self.loader = ConfigLoader()
        self.report = AuditReport()
        self.flows: Dict[str, FlowConfig] = {}
        self.registered_conditions: Set[str] = set()

    def load_all_flows(self) -> List[str]:
        """Load all available flows."""
        flows_dir = self.loader.config_dir / "flows"
        flow_names = []

        for flow_dir in flows_dir.iterdir():
            if flow_dir.is_dir() and not flow_dir.name.startswith("_"):
                flow_file = flow_dir / "flow.yaml"
                if flow_file.exists():
                    try:
                        self.flows[flow_dir.name] = self.loader.load_flow(flow_dir.name, validate=False)
                        flow_names.append(flow_dir.name)
                    except Exception as e:
                        self.report.add(Issue(
                            severity="HIGH",
                            title=f"Flow load error: {flow_dir.name}",
                            location=str(flow_file),
                            description=str(e),
                            consequence="Flow cannot be used",
                            recommendation="Fix YAML syntax or reference errors"
                        ))

        return flow_names

    def get_registered_conditions(self) -> Set[str]:
        """Get all conditions registered in sm_registry."""
        # Import conditions module to trigger registration
        try:
            import src.conditions.state_machine.conditions  # noqa
        except Exception:
            pass

        return set(sm_registry.list_all())

    def audit(self):
        """Run full audit."""
        print("Loading flows...")
        flow_names = self.load_all_flows()
        print(f"Loaded {len(flow_names)} flows: {', '.join(flow_names)}")

        print("Getting registered conditions...")
        self.registered_conditions = self.get_registered_conditions()
        print(f"Found {len(self.registered_conditions)} registered conditions")

        # Run all checks
        self._check_intent_coverage()
        self._check_dead_ends()
        self._check_unreachable_states()
        self._check_cycles()
        self._check_priority_conflicts()
        self._check_unresolved_parameters()
        self._check_condition_existence()
        self._check_semantic_issues()
        self._check_terminal_states()
        self._check_mixin_conflicts()

        # Statistics
        self.report.stats = {
            "Total flows": len(self.flows),
            "Classifier intents": len(self.CLASSIFIER_INTENTS),
            "Registered conditions": len(self.registered_conditions),
        }

        for flow_name, flow in self.flows.items():
            self.report.stats[f"States in {flow_name}"] = len(flow.states)

    def _check_intent_coverage(self):
        """Check intent coverage between classifier and transitions/rules."""

        # Collect all intents used in transitions/rules across all flows
        used_intents: Set[str] = set()
        intent_locations: Dict[str, List[str]] = defaultdict(list)

        for flow_name, flow in self.flows.items():
            for state_name, state_config in flow.states.items():
                transitions = state_config.get("transitions", {})
                rules = state_config.get("rules", {})

                for intent in transitions.keys():
                    if intent not in self.SPECIAL_TRANSITION_KEYS:
                        used_intents.add(intent)
                        intent_locations[intent].append(f"{flow_name}/{state_name}")

                for intent in rules.keys():
                    used_intents.add(intent)
                    intent_locations[intent].append(f"{flow_name}/{state_name}")

        # Check for intents in classifier but not in any transition/rule
        uncovered = self.CLASSIFIER_INTENTS - used_intents - self.SPECIAL_TRANSITION_KEYS
        if uncovered:
            # Some uncovered intents are OK (handled by default logic)
            critical_uncovered = uncovered - {"farewell", "gratitude", "small_talk"}
            if critical_uncovered:
                self.report.add(Issue(
                    severity="MEDIUM",
                    title="Intents without explicit transitions/rules",
                    location="All flows",
                    description=f"Classifier intents without handlers: {sorted(critical_uncovered)}",
                    consequence="These intents will fall through to default action 'continue_current_goal'",
                    recommendation="Add transitions or rules for these intents in _base/states.yaml or specific flows",
                    impact_percent=5.0
                ))

        # Check for intents used in transitions/rules but not in classifier
        unknown = used_intents - self.CLASSIFIER_INTENTS - self.SPECIAL_TRANSITION_KEYS
        # Filter out BANT-specific intents
        bant_intents = {"budget_confirmed", "authority_confirmed", "need_confirmed",
                       "timeline_confirmed", "decision_maker", "not_decision_maker",
                       "urgent_need", "no_rush", "no_budget"}
        unknown = unknown - bant_intents

        if unknown:
            self.report.add(Issue(
                severity="HIGH",
                title="Transitions/rules reference non-existent intents",
                location="Multiple flows",
                description=f"Unknown intents: {sorted(unknown)}",
                consequence="Transitions will never trigger - dead code",
                reproduction="Send any message; these transitions are unreachable",
                recommendation="Either add these intents to classifier or remove transitions",
                impact_percent=0.0  # No impact, just dead code
            ))

    def _check_dead_ends(self):
        """Check for states without outgoing transitions (except finals)."""
        for flow_name, flow in self.flows.items():
            for state_name, state_config in flow.states.items():
                if state_config.get("abstract"):
                    continue

                is_final = state_config.get("is_final", False)
                transitions = state_config.get("transitions", {})
                rules = state_config.get("rules", {})

                # A state is a dead-end if it has no transitions AND no rules
                # AND is not final AND is not success
                if not transitions and not rules and not is_final and state_name not in ("success",):
                    self.report.add(Issue(
                        severity="MEDIUM",
                        title=f"Potential dead-end state: {state_name}",
                        location=f"{flow_name}/states.yaml",
                        description=f"State '{state_name}' has no transitions or rules",
                        consequence="Dialogue may get stuck in this state",
                        recommendation="Add transitions or mark as is_final: true",
                        impact_percent=2.0
                    ))

    def _check_unreachable_states(self):
        """Check for states that cannot be reached from entry points."""
        for flow_name, flow in self.flows.items():
            # Build reachability graph
            reachable: Set[str] = set()
            to_visit = list(flow.entry_points.values())

            # Also add greeting as entry
            if "greeting" in flow.states:
                to_visit.append("greeting")

            while to_visit:
                state = to_visit.pop()
                if state in reachable:
                    continue
                reachable.add(state)

                state_config = flow.states.get(state, {})
                transitions = state_config.get("transitions", {})

                for target in transitions.values():
                    if isinstance(target, str):
                        if not target.startswith("{{"):  # Skip unresolved params
                            to_visit.append(target)
                    elif isinstance(target, list):
                        for rule in target:
                            if isinstance(rule, dict) and "then" in rule:
                                to_visit.append(rule["then"])
                            elif isinstance(rule, str) and not rule.startswith("{{"):
                                to_visit.append(rule)

            # Check for unreachable
            all_states = {s for s in flow.states.keys() if not flow.states[s].get("abstract")}
            unreachable = all_states - reachable

            if unreachable:
                self.report.add(Issue(
                    severity="LOW",
                    title=f"Unreachable states in {flow_name}",
                    location=f"{flow_name}/states.yaml",
                    description=f"States not reachable from entry: {sorted(unreachable)}",
                    consequence="Dead code, states will never be visited",
                    recommendation="Add transitions to these states or remove them",
                    impact_percent=0.0
                ))

    def _check_cycles(self):
        """Check for potential infinite cycles without exit conditions."""
        for flow_name, flow in self.flows.items():
            # Build adjacency list
            graph: Dict[str, Set[str]] = defaultdict(set)

            for state_name, state_config in flow.states.items():
                if state_config.get("abstract"):
                    continue

                transitions = state_config.get("transitions", {})
                for target in transitions.values():
                    if isinstance(target, str) and not target.startswith("{{"):
                        graph[state_name].add(target)
                    elif isinstance(target, list):
                        for rule in target:
                            if isinstance(rule, dict) and "then" in rule:
                                graph[state_name].add(rule["then"])
                            elif isinstance(rule, str) and not rule.startswith("{{"):
                                graph[state_name].add(rule)

            # Find cycles using DFS
            visited = set()
            rec_stack = set()
            cycles = []

            def find_cycle(node, path):
                visited.add(node)
                rec_stack.add(node)
                path.append(node)

                for neighbor in graph.get(node, []):
                    if neighbor not in visited:
                        if find_cycle(neighbor, path):
                            return True
                    elif neighbor in rec_stack:
                        # Found cycle
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        cycles.append(cycle)

                path.pop()
                rec_stack.remove(node)
                return False

            for node in graph:
                if node not in visited:
                    find_cycle(node, [])

            # Check if cycles have exit conditions
            for cycle in cycles:
                cycle_states = set(cycle[:-1])  # Remove duplicate end
                has_exit = False

                for state in cycle_states:
                    state_config = flow.states.get(state, {})
                    transitions = state_config.get("transitions", {})

                    # Check if any transition leads outside cycle
                    for target in transitions.values():
                        if isinstance(target, str) and target not in cycle_states:
                            has_exit = True
                            break
                        elif isinstance(target, list):
                            for rule in target:
                                then_state = rule.get("then") if isinstance(rule, dict) else rule
                                if then_state and then_state not in cycle_states:
                                    has_exit = True
                                    break

                    if has_exit:
                        break

                if not has_exit:
                    self.report.add(Issue(
                        severity="HIGH",
                        title=f"Potential infinite cycle in {flow_name}",
                        location=f"{flow_name}/states.yaml",
                        description=f"Cycle without exit: {' → '.join(cycle)}",
                        consequence="Dialogue can get stuck in infinite loop",
                        reproduction="Navigate to any state in cycle without progress data",
                        recommendation="Add exit transition (e.g., to soft_close) or data_complete condition",
                        impact_percent=5.0
                    ))

    def _check_priority_conflicts(self):
        """Check for priority conflicts between rules and transitions."""
        for flow_name, flow in self.flows.items():
            for state_name, state_config in flow.states.items():
                if state_config.get("abstract"):
                    continue

                transitions = state_config.get("transitions", {})
                rules = state_config.get("rules", {})

                # Check for same intent in both rules and transitions
                overlap = set(transitions.keys()) & set(rules.keys())

                for intent in overlap:
                    # This is actually OK - rules define action, transitions define state change
                    # But worth noting if they might conflict
                    rule_value = rules[intent]
                    trans_value = transitions[intent]

                    # If rule is a simple action and transition leads to different state
                    # This is expected behavior, but complex cases might confuse
                    if isinstance(rule_value, (list, dict)) or isinstance(trans_value, (list, dict)):
                        self.report.add(Issue(
                            severity="LOW",
                            title=f"Complex overlap in {state_name}",
                            location=f"{flow_name}/{state_name}",
                            description=f"Intent '{intent}' has complex logic in both rules and transitions",
                            consequence="Behavior might be unexpected; rules are checked before transitions",
                            recommendation="Document intended behavior or simplify",
                            impact_percent=1.0
                        ))

    def _check_unresolved_parameters(self):
        """Check for unresolved {{parameter}} placeholders."""
        param_pattern = re.compile(r'\{\{(\w+)\}\}')

        for flow_name, flow in self.flows.items():
            flow_vars = flow.variables

            for state_name, state_config in flow.states.items():
                if state_config.get("abstract"):
                    continue

                # Check all string values recursively
                def check_value(value, path):
                    if isinstance(value, str):
                        matches = param_pattern.findall(value)
                        for param in matches:
                            # Check if parameter has value
                            if param not in flow_vars and param not in state_config.get("parameters", {}):
                                self.report.add(Issue(
                                    severity="HIGH",
                                    title=f"Unresolved parameter: {{{{{param}}}}}",
                                    location=f"{flow_name}/{state_name}/{path}",
                                    description=f"Parameter '{param}' not defined in flow variables or state parameters",
                                    consequence="Transition will fail or use literal string '{{" + param + "}}'",
                                    recommendation=f"Add '{param}' to flow.yaml variables or state parameters",
                                    impact_percent=10.0
                                ))
                    elif isinstance(value, dict):
                        for k, v in value.items():
                            check_value(v, f"{path}.{k}")
                    elif isinstance(value, list):
                        for i, v in enumerate(value):
                            check_value(v, f"{path}[{i}]")

                check_value(state_config.get("transitions", {}), "transitions")
                check_value(state_config.get("rules", {}), "rules")

    def _check_condition_existence(self):
        """Check that all 'when:' conditions exist in registry."""
        for flow_name, flow in self.flows.items():
            for state_name, state_config in flow.states.items():
                if state_config.get("abstract"):
                    continue

                def check_conditions(value, path):
                    if isinstance(value, dict):
                        if "when" in value:
                            condition = value["when"]
                            if condition not in self.registered_conditions:
                                # Check for special conditions handled in state_machine.py
                                special_conditions = {"is_final", "objection_limit_reached",
                                                    "has_all_required_data"}
                                if condition not in special_conditions:
                                    self.report.add(Issue(
                                        severity="HIGH",
                                        title=f"Unknown condition: {condition}",
                                        location=f"{flow_name}/{state_name}/{path}",
                                        description=f"Condition '{condition}' not found in sm_registry",
                                        consequence="Condition will always return False or raise error",
                                        recommendation=f"Register condition in conditions.py or fix typo",
                                        impact_percent=15.0
                                    ))
                        for k, v in value.items():
                            check_conditions(v, f"{path}.{k}")
                    elif isinstance(value, list):
                        for i, v in enumerate(value):
                            check_conditions(v, f"{path}[{i}]")

                check_conditions(state_config.get("transitions", {}), "transitions")
                check_conditions(state_config.get("rules", {}), "rules")

    def _check_semantic_issues(self):
        """Check for semantic/logical issues."""

        # Issue: situation_provided in bant_budget should stay in budget
        for flow_name, flow in self.flows.items():
            if "bant" in flow_name:
                budget_state = flow.states.get("bant_budget", {})
                transitions = budget_state.get("transitions", {})

                # Check if progress intents go to next phase regardless of data
                progress_intents = ["situation_provided", "problem_revealed"]
                for intent in progress_intents:
                    if intent in transitions:
                        # This is handled by phase_progress mixin, which is intentional
                        # But document that semantic might be wrong
                        pass

        # Check objection limits
        # max_consecutive_objections: 3, max_total_objections: 5
        # ConversationGuard max_same_state: 4
        # These should be coordinated

        self.report.add(Issue(
            severity="LOW",
            title="Potential limit coordination issue",
            location="constants.yaml",
            description="objection limit (3 consecutive) might conflict with max_same_state (4)",
            consequence="Client might hit objection limit before same_state guard",
            recommendation="Verify limits work together: 3 objections → soft_close before 4 same state",
            impact_percent=2.0
        ))

    def _check_terminal_states(self):
        """Check terminal states configuration."""
        for flow_name, flow in self.flows.items():
            # Check soft_close
            soft_close = flow.states.get("soft_close", {})
            if soft_close:
                is_final = soft_close.get("is_final", False)
                transitions = soft_close.get("transitions", {})

                if not is_final and transitions:
                    # soft_close is not final but has transitions - this is OK
                    # Check if transitions actually work
                    exit_intents = ["agreement", "demo_request", "callback_request",
                                   "price_question", "question_features"]
                    working_exits = [i for i in exit_intents if i in transitions]

                    if working_exits:
                        self.report.stats[f"{flow_name} soft_close exits"] = working_exits
                    else:
                        self.report.add(Issue(
                            severity="MEDIUM",
                            title=f"soft_close has no working exit transitions in {flow_name}",
                            location=f"{flow_name}/soft_close",
                            description="soft_close is_final=false but exits might not work",
                            consequence="Client cannot recover from soft_close",
                            recommendation="Verify exit transitions trigger on positive intents",
                            impact_percent=5.0
                        ))

    def _check_mixin_conflicts(self):
        """Check for mixin ordering conflicts."""
        # Load base mixins
        mixins_file = self.loader.config_dir / "flows" / "_base" / "mixins.yaml"
        if mixins_file.exists():
            with open(mixins_file) as f:
                mixins_data = yaml.safe_load(f)

            mixins = mixins_data.get("mixins", {})

            # Check for overlapping rules/transitions in mixins
            rule_sources: Dict[str, List[str]] = defaultdict(list)
            trans_sources: Dict[str, List[str]] = defaultdict(list)

            for mixin_name, mixin_config in mixins.items():
                for rule in mixin_config.get("rules", {}).keys():
                    rule_sources[rule].append(mixin_name)
                for trans in mixin_config.get("transitions", {}).keys():
                    trans_sources[trans].append(mixin_name)

            # Find overlaps
            for intent, sources in rule_sources.items():
                if len(sources) > 1:
                    self.report.add(Issue(
                        severity="LOW",
                        title=f"Mixin rule overlap: {intent}",
                        location="_base/mixins.yaml",
                        description=f"Intent '{intent}' defined in multiple mixins: {sources}",
                        consequence="Last mixin in list wins; might be unexpected",
                        recommendation="Document intended priority or consolidate",
                        impact_percent=1.0
                    ))


def main():
    """Run audit and print report."""
    auditor = StateMachineAuditor()
    auditor.audit()
    auditor.report.print_report()

    # Return exit code based on severity
    if auditor.report.by_severity("HIGH"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
