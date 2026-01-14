# Modular Flow System

This directory contains modular flow configurations for the state machine constructor.

## Overview

The flow system allows you to create customized conversation flows without modifying Python code. Each flow is a complete configuration that defines:

- **States**: Conversation states with goals, transitions, and rules
- **Phases**: Optional sequential phases (like SPIN: Situation → Problem → Implication → Need-Payoff)
- **Priorities**: Order of processing in `apply_rules()`
- **Variables**: Flow-specific parameters for template substitution

## Directory Structure

```
flows/
├── _base/                    # Shared base components
│   ├── states.yaml           # Base states (greeting, success, soft_close, etc.)
│   ├── mixins.yaml           # Reusable rule blocks
│   └── priorities.yaml       # Default processing priorities
│
├── spin_selling/             # SPIN Selling flow
│   ├── flow.yaml             # Main configuration
│   └── states.yaml           # SPIN-specific states
│
└── [your_flow]/              # Your custom flow
    ├── flow.yaml
    └── states.yaml
```

## Creating a Custom Flow

### 1. Create flow directory

```bash
mkdir -p src/yaml_config/flows/my_flow
```

### 2. Create flow.yaml

```yaml
# flows/my_flow/flow.yaml
flow:
  name: my_flow
  version: "1.0"
  description: "My custom flow"

  # Variables for template substitution
  variables:
    entry_state: my_first_state
    company_name: "MyCompany"

  # Optional phases (omit if no sequential phases needed)
  phases:
    order: [phase1, phase2, phase3]
    mapping:
      phase1: state_phase1
      phase2: state_phase2
      phase3: state_phase3
    post_phases_state: closing  # Where to go after last phase
    skip_conditions:
      phase3: [has_high_interest]  # Conditions to skip phase3

  # Entry points for different scenarios
  entry_points:
    default: greeting
    hot_lead: closing
```

### 3. Create states.yaml

```yaml
# flows/my_flow/states.yaml
states:
  # Abstract base state (not used directly)
  _my_base:
    abstract: true
    extends: _base_phase  # Inherit from base
    mixins:
      - price_handling
      - exit_intents
    parameters:
      default_price_action: deflect_and_continue

  # Concrete state using inheritance
  state_phase1:
    extends: _my_base
    goal: "Understand the situation"
    phase: phase1
    required_data:
      - company_size
    transitions:
      data_complete: state_phase2
    rules:
      unclear: probe_situation  # State-specific rule
```

## Key Concepts

### State Inheritance (`extends`)

States can inherit from other states:

```yaml
my_state:
  extends: _base_phase    # Inherits all rules, transitions
  goal: "My custom goal"  # Override specific fields
  transitions:
    custom: custom_state  # Add new transitions
```

### Mixins

Mixins are reusable rule/transition blocks:

```yaml
# In mixins.yaml
mixins:
  price_handling:
    rules:
      price_question: answer_with_facts
      pricing_details: answer_with_facts

# In states.yaml
my_state:
  mixins:
    - price_handling  # Apply mixin rules
```

### Parameter Substitution

Use `{{param}}` for dynamic values:

```yaml
# In flow.yaml
variables:
  entry_state: spin_situation
  default_action: deflect_and_continue

# In states.yaml
transitions:
  agreement: "{{entry_state}}"  # Resolved to spin_situation

rules:
  price_question:
    - when: can_answer_price
      then: answer_with_facts
    - "{{default_action}}"  # Resolved to deflect_and_continue
```

### Conditional Rules

Rules can have conditions:

```yaml
rules:
  price_question:
    - when: can_answer_price      # First condition
      then: answer_with_facts
    - when: should_answer_directly
      then: answer_with_facts
    - deflect_and_continue        # Default fallback
```

## Available Base Components

### Base States (`_base/states.yaml`)

| State | Description |
|-------|-------------|
| `_base_greeting` | Abstract base for greeting states |
| `_base_terminal` | Abstract base for terminal states |
| `_base_phase` | Abstract base for phase states (includes common mixins) |
| `greeting` | Entry point state |
| `success` | Successful completion (final) |
| `soft_close` | Soft close with option to return |
| `presentation` | Product presentation |
| `handle_objection` | Objection handling |
| `close` | Closing (get contact info) |

### Mixins (`_base/mixins.yaml`)

| Mixin | Description |
|-------|-------------|
| `price_handling` | Rules for price questions |
| `product_questions` | Rules for feature/integration questions |
| `objection_handling` | Transitions for objections |
| `dialogue_repair` | Rules for stuck/unclear situations |
| `exit_intents` | Transitions for rejection/farewell |
| `close_shortcuts` | Fast path to close (demo_request) |
| `social_intents` | Rules for gratitude/small_talk |

## Loading a Flow

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

# Load flow
loader = ConfigLoader()
flow = loader.load_flow("my_flow")

# Create StateMachine with flow
sm = StateMachine(flow=flow)

# Access flow properties
print(flow.phase_order)      # ['phase1', 'phase2', 'phase3']
print(flow.post_phases_state)  # 'closing'
print(sm.states_config)      # Resolved states dict
```

## Example: BANT Flow

```yaml
# flows/bant/flow.yaml
flow:
  name: bant
  version: "1.0"
  description: "BANT qualification flow"

  phases:
    order: [budget, authority, need, timeline]
    mapping:
      budget: bant_budget
      authority: bant_authority
      need: bant_need
      timeline: bant_timeline
    post_phases_state: proposal

  entry_points:
    default: greeting
    inbound_lead: bant_budget

# flows/bant/states.yaml
states:
  _bant_base:
    abstract: true
    extends: _base_phase
    parameters:
      default_price_action: answer_with_facts  # BANT is more direct

  bant_budget:
    extends: _bant_base
    goal: "Understand budget constraints"
    phase: budget
    required_data: [budget_range]
```

## Example: Support Flow (No Phases)

```yaml
# flows/support/flow.yaml
flow:
  name: support
  version: "1.0"
  description: "Customer support flow"

  # No phases - direct question answering
  phases: null

  entry_points:
    default: greeting

# flows/support/states.yaml
states:
  greeting:
    goal: "Greet and understand the issue"
    transitions:
      question_features: answer
      question_integrations: answer
    rules:
      greeting: greet_back

  answer:
    goal: "Provide helpful answer"
    transitions:
      gratitude: success
      farewell: success
    rules:
      question_features: answer_from_knowledge
      question_integrations: answer_from_knowledge
```

## Testing Your Flow

```python
import pytest
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

def test_my_flow_loads():
    loader = ConfigLoader()
    flow = loader.load_flow("my_flow")

    assert flow.name == "my_flow"
    assert "my_first_state" in flow.states

def test_my_flow_with_state_machine():
    loader = ConfigLoader()
    flow = loader.load_flow("my_flow")
    sm = StateMachine(flow=flow)

    assert sm.phase_order == ["phase1", "phase2", "phase3"]
```

## Migration from Hardcoded States

1. Create your flow directory
2. Copy relevant states from `states/sales_flow.yaml`
3. Replace duplicated rules with `extends` and `mixins`
4. Add `flow.yaml` with phases configuration
5. Test that behavior matches original

The SPIN Selling flow (`flows/spin_selling/`) is a complete example of migration.
