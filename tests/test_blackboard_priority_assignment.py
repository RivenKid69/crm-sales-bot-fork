# tests/test_blackboard_priority_assignment.py

def test_go_back_over_data_complete_priority():
    """Explicit go_back should win over data_complete when both are proposed."""
    from src.config_loader import ConfigLoader
    from src.state_machine import StateMachine
    from src.blackboard.orchestrator import create_orchestrator
    from src.blackboard.source_registry import SourceRegistry, register_builtin_sources

    # Reset and re-register to ensure clean state
    SourceRegistry.reset()
    register_builtin_sources()

    loader = ConfigLoader()
    config = loader.load()
    flow = loader.load_flow("spin_selling")

    sm = StateMachine(config=config, flow=flow)
    sm.transition_to("spin_implication")
    sm.collected_data["implication_probed"] = True  # required_data collected

    orch = create_orchestrator(sm, flow)
    decision = orch.process_turn(intent="go_back", extracted_data={}, context_envelope=None)

    assert decision.next_state == "spin_problem"
