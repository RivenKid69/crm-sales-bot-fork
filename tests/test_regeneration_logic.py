import pytest
from unittest.mock import MagicMock
from src.generator import ResponseGenerator
import logging

def test_regeneration_considers_all_histories():
    # Mock LLM
    llm = MagicMock()
    
    # We want to simulate:
    # 1. First generation returns a duplicate of 'external_history'
    # 2. Regeneration attempt 1 returns a duplicate of 'internal_history'
    # 3. Regeneration attempt 2 returns a unique response
    
    external_history = [{"bot": "Дубликат из внешней истории"}]
    internal_history = ["Дубликат из внутренней памяти"]
    unique_response = "Я уникальный ответ на русском языке"
    
    # Setup LLM side effects
    llm.generate.side_effect = [
        "Дубликат из внешней истории", # First generate
        "Дубликат из внутренней памяти", # First retry
        unique_response,      # Second retry
    ]
    
    generator = ResponseGenerator(llm)
    # Inject internal history
    generator._response_history = list(internal_history)
    
    # Context
    context = {
        "history": external_history,
        "user_message": "привет"
    }
    
    # Execute
    result = generator.generate(action="greet", context=context)
    
    # Verification
    print(f"DEBUG: Actual: '{result}', Expected: '{unique_response}'")
    assert result == unique_response
    assert llm.generate.call_count == 3

def test_fallback_selects_best_among_all_histories():
    # Mock LLM
    llm = MagicMock()
    
    # Simulation: Everything is a duplicate, but we want the one that is "least duplicate"
    # across BOTH histories.
    
    # Threshold is 0.8
    # Exact match: Jaccard = 1.0
    # Almost exact: "Точное совпадение очень" (tokens: точное, совпадение, очень)
    # vs "Точное совпадение" (tokens: точное, совпадение)
    # Intersection = 2, Union = 3. Sim = 2/3 = 0.66. Actually 0.66 < 0.8.
    
    # To be > 0.8:
    # "Точное совпадение аа" (3 tokens) vs "Точное совпадение" (2 tokens)
    # Intersection = 2. Union = 3. Sim = 0.66. Still too low.
    
    # Let's use many words to make it > 0.8
    # Base: "раз два три четыре пять шесть семь восемь девять десять" (10 words)
    # Target: "раз два три четыре пять шесть семь восемь девять десять одиннадцать" (11 words)
    # Intersection = 10. Union = 11. Sim = 10/11 = 0.909 > 0.8. Match!
    
    base = "раз два три четыре пять шесть семь восемь девять десять"
    dup1 = base + " одиннадцать" # 0.909
    dup2 = base + " двенадцать"   # 0.909
    dup3 = base + " тринадцать"    # 0.909
    dup4 = base + " четырнадцать"  # 0.909
    
    external_history = [{"bot": base}]
    internal_history = [] # Keep it simple
    
    llm.generate.side_effect = [
        base, # Initial
        dup1, # Retry 1
        dup2, # Retry 2
        dup3, # Retry 3
        dup4, # Retry 4
    ]
    
    generator = ResponseGenerator(llm)
    
    context = {
        "history": external_history,
        "user_message": "тест"
    }
    
    # Execute
    result = generator.generate(action="test", context=context)
    print(f"DEBUG Fallback: Actual: '{result}'")
    
    # It should exhaust and return dup4 (as they all have same similarity to base, 
    # but the loop updates best_response if max_sim < best_similarity.
    # Actually if they all are 0.909, only the first one might be kept or the last depending on < vs <=.
    # In my code: if max_sim < best_similarity: best_response = cleaned
    
    # Verify exhaustion
    assert llm.generate.call_count == 5
    assert result in [dup1, dup2, dup3, dup4]

if __name__ == "__main__":
    try:
        from feature_flags import flags
        flags.set_override("response_diversity", False)
        flags.set_override("response_deduplication", True)
    except ImportError:
        pass

    test_regeneration_considers_all_histories()
    test_fallback_selects_best_among_all_histories()
    print("SUCCESS: Regeneration tests passed!")
