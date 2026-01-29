"""
Симулятор диалогов для тестирования CRM Sales Bot.

Использование:
    python -m src.simulator -n 50 -o report.txt

E2E тестирование:
    python -m src.simulator --e2e
    python -m src.simulator --e2e-flow challenger
"""

from src.simulator.personas import Persona, PERSONAS
from src.simulator.noise import add_noise
from src.simulator.client_agent import ClientAgent
from src.simulator.runner import SimulationRunner, SimulationResult
from src.simulator.metrics import MetricsCollector, SimulationMetrics
from src.simulator.report import ReportGenerator, generate_e2e_report, generate_e2e_text_report
from src.simulator.e2e_scenarios import E2EScenario, ALL_SCENARIOS, get_scenario_by_flow
from src.simulator.e2e_evaluator import E2EResult, E2EEvaluator, evaluate_batch

__all__ = [
    # Core simulation
    'Persona',
    'PERSONAS',
    'add_noise',
    'ClientAgent',
    'SimulationRunner',
    'SimulationResult',
    'MetricsCollector',
    'SimulationMetrics',
    'ReportGenerator',
    # E2E testing
    'E2EScenario',
    'ALL_SCENARIOS',
    'get_scenario_by_flow',
    'E2EResult',
    'E2EEvaluator',
    'evaluate_batch',
    'generate_e2e_report',
    'generate_e2e_text_report',
]
