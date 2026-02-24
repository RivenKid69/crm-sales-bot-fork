"""Debug: trace what LLM generates and what gets stripped for prices."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot
from src.generator import ResponseGenerator

# Monkey-patch to capture raw LLM output
_original_generate = ResponseGenerator.generate

def patched_generate(self, action, context):
    # Before calling, set debug flag
    self._debug_raw_responses = []

    # Monkey-patch llm.generate to capture raw output
    _orig_llm = self.llm.generate
    def capture_llm(*args, **kwargs):
        result = _orig_llm(*args, **kwargs)
        self._debug_raw_responses.append(result)
        return result
    self.llm.generate = capture_llm

    result = _original_generate(self, action, context)

    # Restore
    self.llm.generate = _orig_llm

    print("=== RAW LLM OUTPUTS ===")
    for i, raw in enumerate(self._debug_raw_responses):
        print(f"  [attempt {i}]: {raw[:300]}...")
    print(f"=== FINAL OUTPUT ===")
    print(f"  {result[:300]}")
    return result

ResponseGenerator.generate = patched_generate

llm = OllamaLLM()
bot = SalesBot(llm, flow_name="autonomous")

# Skip greeting
bot.process("Привет")

# Ask price question
result = bot.process("Сколько стоит ваша система?")
print(f"\nFinal bot response: {result['response']}")
