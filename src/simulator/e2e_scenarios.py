"""
E2E Scenarios for Sales Technique Testing.

Defines 20 unique sales techniques as test scenarios for the e2e testing framework.
Each scenario specifies the flow to use, expected phases, and success criteria.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class E2EScenario:
    """
    E2E test scenario configuration.

    Attributes:
        id: Unique scenario identifier (01-20)
        name: Human-readable name of the technique
        flow: Flow name to load (e.g., "spin_selling", "challenger")
        technique: Short description of the technique
        phases: Expected phases the bot should progress through
        expected_outcome: Expected final outcome ("success", "soft_close", etc.)
        persona: Client persona to use (default: "happy_path")
        description: Detailed description of the technique
    """
    id: str
    name: str
    flow: str
    technique: str
    phases: List[str]
    expected_outcome: str
    persona: str = "happy_path"
    description: str = ""


# =============================================================================
# 20 SALES TECHNIQUES
# =============================================================================

ALL_SCENARIOS: List[E2EScenario] = [
    # 01. SPIN Selling (existing flow)
    E2EScenario(
        id="01",
        name="SPIN Selling",
        flow="spin_selling",
        technique="SPIN",
        phases=["situation", "problem", "implication", "need_payoff"],
        expected_outcome="success",
        persona="happy_path",
        description="Situation->Problem->Implication->Need-Payoff methodology"
    ),

    # 02. BANT
    E2EScenario(
        id="02",
        name="BANT",
        flow="bant",
        technique="BANT",
        phases=["budget", "authority", "need", "timeline"],
        expected_outcome="success",
        persona="happy_path",
        description="Budget->Authority->Need->Timeline qualification"
    ),

    # 03. Challenger Sale
    E2EScenario(
        id="03",
        name="Challenger Sale",
        flow="challenger",
        technique="Challenger",
        phases=["teach", "tailor", "take_control"],
        expected_outcome="soft_close",
        persona="skeptic",
        description="Challenge assumptions, provoke rethinking"
    ),

    # 04. Solution Selling
    E2EScenario(
        id="04",
        name="Solution Selling",
        flow="solution",
        technique="Solution",
        phases=["pain_discovery", "solution_mapping", "value_proof"],
        expected_outcome="success",
        persona="happy_path",
        description="Deep pain exploration, show how we solve it"
    ),

    # 05. Consultative Selling
    E2EScenario(
        id="05",
        name="Consultative Selling",
        flow="consultative",
        technique="Consultative",
        phases=["understand", "advise", "recommend"],
        expected_outcome="success",
        persona="technical",
        description="Act as consultant/expert, not salesperson"
    ),

    # 06. Sandler Method
    E2EScenario(
        id="06",
        name="Sandler Method",
        flow="sandler",
        technique="Sandler",
        phases=["bonding", "upfront_contract", "pain_funnel", "budget", "decision"],
        expected_outcome="soft_close",
        persona="skeptic",
        description="Pain funnel methodology, deep pain qualification"
    ),

    # 07. MEDDIC
    E2EScenario(
        id="07",
        name="MEDDIC",
        flow="meddic",
        technique="MEDDIC",
        phases=["metrics", "economic_buyer", "decision_criteria", "decision_process", "identify_pain", "champion"],
        expected_outcome="success",
        persona="technical",
        description="B2B deal qualification methodology"
    ),

    # 08. SNAP Selling
    E2EScenario(
        id="08",
        name="SNAP Selling",
        flow="snap",
        technique="SNAP",
        phases=["simple", "invaluable", "align", "priority"],
        expected_outcome="success",
        persona="busy",
        description="Keep it Simple, be iNvaluable, Always Align, raise Priority"
    ),

    # 09. Value-Based Selling
    E2EScenario(
        id="09",
        name="Value-Based Selling",
        flow="value",
        technique="Value-Based",
        phases=["discover_value", "quantify_impact", "present_roi"],
        expected_outcome="success",
        persona="price_sensitive",
        description="Focus on ROI, savings, and profit"
    ),

    # 10. Inbound Sales
    E2EScenario(
        id="10",
        name="Inbound Sales",
        flow="inbound",
        technique="Inbound",
        phases=["identify", "connect", "explore", "advise"],
        expected_outcome="success",
        persona="happy_path",
        description="Help, don't sell aggressively (customer came to us)"
    ),

    # 11. AIDA
    E2EScenario(
        id="11",
        name="AIDA",
        flow="aida",
        technique="AIDA",
        phases=["attention", "interest", "desire", "action"],
        expected_outcome="success",
        persona="happy_path",
        description="Attention->Interest->Desire->Action marketing classic"
    ),

    # 12. FAB (Features-Advantages-Benefits)
    E2EScenario(
        id="12",
        name="FAB Selling",
        flow="fab",
        technique="FAB",
        phases=["feature", "advantage", "benefit"],
        expected_outcome="soft_close",
        persona="technical",
        description="Translate features into advantages and benefits"
    ),

    # 13. NEAT Selling
    E2EScenario(
        id="13",
        name="NEAT Selling",
        flow="neat",
        technique="NEAT",
        phases=["needs", "economic_impact", "access_authority", "timeline"],
        expected_outcome="success",
        persona="happy_path",
        description="Modernized BANT focusing on economic impact"
    ),

    # 14. Gap Selling
    E2EScenario(
        id="14",
        name="Gap Selling",
        flow="gap",
        technique="Gap",
        phases=["current_state", "future_state", "gap_analysis", "solution_fit"],
        expected_outcome="success",
        persona="happy_path",
        description="Show gap between 'now' and 'should be'"
    ),

    # 15. Command of the Sale
    E2EScenario(
        id="15",
        name="Command of Sale",
        flow="command",
        technique="Command",
        phases=["establish_authority", "control_conversation", "guide_to_close"],
        expected_outcome="soft_close",
        persona="aggressive",
        description="Seller leads and controls the process"
    ),

    # 16. Social Selling
    E2EScenario(
        id="16",
        name="Social Selling",
        flow="social",
        technique="Social",
        phases=["build_trust", "share_value", "engage", "convert"],
        expected_outcome="success",
        persona="happy_path",
        description="Build trust through social proof and value sharing"
    ),

    # 17. Customer Centric Selling
    E2EScenario(
        id="17",
        name="Customer Centric",
        flow="customer_centric",
        technique="Customer-Centric",
        phases=["listen", "understand", "empower", "support"],
        expected_outcome="success",
        persona="happy_path",
        description="Customer at center, we help them decide"
    ),

    # 18. Relationship Selling
    E2EScenario(
        id="18",
        name="Relationship Selling",
        flow="relationship",
        technique="Relationship",
        phases=["connect", "build_rapport", "nurture", "partnership"],
        expected_outcome="success",
        persona="happy_path",
        description="Build long-term relationships, not one-time deals"
    ),

    # 19. Transactional Selling
    E2EScenario(
        id="19",
        name="Transactional Selling",
        flow="transactional",
        technique="Transactional",
        phases=["quick_qualification", "direct_offer", "fast_close"],
        expected_outcome="soft_close",
        persona="busy",
        description="Fast, to the point, no fluff"
    ),

    # 20. Demo First
    E2EScenario(
        id="20",
        name="Demo First",
        flow="demo_first",
        technique="Demo-First",
        phases=["hook", "demo", "qa", "close"],
        expected_outcome="success",
        persona="technical",
        description="Show product first, talk later"
    ),
]


def get_scenario_by_id(scenario_id: str) -> Optional[E2EScenario]:
    """Get scenario by ID."""
    for scenario in ALL_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    return None


def get_scenario_by_flow(flow_name: str) -> Optional[E2EScenario]:
    """Get scenario by flow name."""
    for scenario in ALL_SCENARIOS:
        if scenario.flow == flow_name:
            return scenario
    return None


def get_scenarios_by_persona(persona: str) -> List[E2EScenario]:
    """Get all scenarios using a specific persona."""
    return [s for s in ALL_SCENARIOS if s.persona == persona]


def get_scenarios_by_outcome(expected_outcome: str) -> List[E2EScenario]:
    """Get all scenarios expecting a specific outcome."""
    return [s for s in ALL_SCENARIOS if s.expected_outcome == expected_outcome]


# Export
__all__ = [
    "E2EScenario",
    "ALL_SCENARIOS",
    "get_scenario_by_id",
    "get_scenario_by_flow",
    "get_scenarios_by_persona",
    "get_scenarios_by_outcome",
]
